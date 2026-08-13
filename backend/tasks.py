"""
Worker Celery — calcule le résumé IA (Ollama) en arrière-plan, et exécute
des tâches périodiques de maintenance.
"""
import os
import sys
from celery import Celery
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv()

DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "mailtracker")

BROKER_URL = f"sqla+postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
RESULT_BACKEND_URL = f"db+postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

celery_app = Celery("mail_detector", broker=BROKER_URL, backend=RESULT_BACKEND_URL)
celery_app.conf.result_expires = 3600
celery_app.conf.beat_schedule = {
    "reset-expired-reminders-every-30s": {
        "task": "tasks.reset_expired_reminders",
        "schedule": 30.0,
    },
    "sync-imap-accounts-every-5min": {        
        "task": "tasks.sync_all_imap_accounts",
        "schedule": 300.0,  # 5 minutes
    },
    "reset-expired-imap-reminders-every-30s": {
        "task": "tasks.reset_expired_imap_reminders",
        "schedule": 30.0,
    },
        "cleanup-stale-sessions-daily": {
        "task": "tasks.cleanup_stale_sessions",
        "schedule": 86400.0,  # une fois par jour
    },
}

celery_app.conf.task_routes = {
    "tasks.sync_account_task": {"queue": "imap_sync"},
    "tasks.sync_all_imap_accounts": {"queue": "imap_sync"},
    "tasks.reset_expired_reminders": {"queue": "maintenance"},
    "tasks.reset_expired_imap_reminders": {"queue": "maintenance"},
    "tasks.compute_summary_task": {"queue": "maintenance"},      
    "tasks.compute_imap_summary_task": {"queue": "maintenance"},  
    "tasks.cleanup_stale_sessions": {"queue": "maintenance"}, 
}


@celery_app.task(bind=True, max_retries=3, default_retry_delay=10)
def compute_summary_task(self, tracking_id: str, body: str):
    from ollama_client import generer_resume
    from db import get_db
    from models import EmailLog
    import uuid

    try:
        ai_summary = generer_resume(body)
    except Exception as exc:
        print(f"[compute_summary_task] tentative échouée pour {tracking_id}: {exc}")
        raise self.retry(exc=exc)

    with get_db() as db:
        mail = db.query(EmailLog).filter(EmailLog.tracking_id == uuid.UUID(tracking_id)).first()
        if mail:
            mail.ai_summary = ai_summary

    return {"tracking_id": tracking_id, "ok": True}


@celery_app.task(bind=True, max_retries=3, default_retry_delay=10)
def compute_imap_summary_task(self, tracking_id: str, body: str, has_attachment: bool = False):
    from ollama_client import generer_resume
    from db import get_db
    from models import ReceivedMailLog
    import uuid

    piece_jointe_note = " Une pièce jointe a été envoyée." if has_attachment else ""

    if not body or not body.strip():
        ai_summary = (
            "L'expéditeur a envoyé une pièce jointe, sans texte dans le corps du message."
            if has_attachment else ""
        )
    else:
        try:
            ai_summary = generer_resume(body).strip() + piece_jointe_note
        except Exception as exc:
            print(f"[compute_imap_summary_task] tentative échouée pour {tracking_id}: {exc}")
            raise self.retry(exc=exc)

    with get_db() as db:
        mail = db.query(ReceivedMailLog).filter(ReceivedMailLog.tracking_id == uuid.UUID(tracking_id)).first()
        if mail:
            mail.ai_summary = ai_summary

    return {"tracking_id": tracking_id, "ok": True}


@celery_app.task
def reset_expired_reminders():
    from db import get_db
    from models import EmailLog
    from datetime import datetime
    from cache import invalidate_prefix

    with get_db() as db:
        updated = db.query(EmailLog).filter(         
            EmailLog.reminder_done.is_(False),
            EmailLog.reminder_recheck_at.isnot(None),
            EmailLog.reminder_recheck_at < datetime.now(),
        ).update(
            {
                EmailLog.alert_acked: False,
                EmailLog.reminder_done: None,
                EmailLog.reminder_answered_at: None,
                EmailLog.reminder_recheck_at: None,
            },
            synchronize_session=False,
        )

    if updated:
        invalidate_prefix("alerts:")
        invalidate_prefix("history:")
        invalidate_prefix("mail:")
        invalidate_prefix("state:")

    return {"ok": True, "updated": updated}

@celery_app.task
def sync_all_imap_accounts():
    """Synchronise tous les comptes IMAP actifs"""
    from db import get_db
    from models import ImapAccount
    from imap_checker import sync_account

    with get_db() as db:
        account_ids = [a.id for a in db.query(ImapAccount).filter(ImapAccount.is_active.is_(True)).all()]

    for account_id in account_ids:
        sync_account_task.delay(account_id)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=30)
def sync_account_task(self, account_id: int):
    from imap_checker import sync_account
    try:
        sync_account(account_id)
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task
def reset_expired_imap_reminders():
    from db import get_db
    from models import ReceivedMailLog
    from datetime import datetime
    from cache import invalidate_prefix

    with get_db() as db:
        updated = db.query(ReceivedMailLog).filter(    # <-- assigner ici
            ReceivedMailLog.reminder_done.is_(False),
            ReceivedMailLog.reminder_recheck_at.isnot(None),
            ReceivedMailLog.reminder_recheck_at < datetime.now(),
        ).update(
            {
                ReceivedMailLog.supervisor_acked: False,
                ReceivedMailLog.reminder_done: None,
                ReceivedMailLog.reminder_answered_at: None,
                ReceivedMailLog.reminder_recheck_at: None,
            },
            synchronize_session=False,
        )

    if updated:
        invalidate_prefix("imap-alerts:")
        invalidate_prefix("imap-history:")
        invalidate_prefix("imap-mail:")

    return {"ok": True, "updated": updated}


@celery_app.task
def cleanup_stale_sessions():
    """F36 : purge périodique de la table sessions.
    1. Supprime toujours les sessions dont le compte lié (admin ou user)
       est désactivé ou n'existe plus — ces sessions sont déjà inutilisables
       (is_active revérifié à chaque requête dans auth.py), donc les garder
       n'a aucune valeur fonctionnelle, juste de l'accumulation.
    2. Supprime en plus les sessions plus vieilles que SESSION_MAX_AGE_DAYS
       si ce réglage est explicitement activé (> 0 dans .env) — désactivé
       par défaut pour respecter le choix produit "pas d'expiration de
       session" documenté dans auth.py."""
    from db import get_db
    from models import Session, Admin, AppUser
    from datetime import datetime, timedelta

    session_max_age_days = int(os.getenv("SESSION_MAX_AGE_DAYS", 0))
    deleted_count = 0

    with get_db() as db:
        # Sessions admin dont le compte est désactivé
        inactive_admin_ids = [
            a.id for a in db.query(Admin.id).filter(Admin.is_active.is_(False)).all()
        ]
        if inactive_admin_ids:
            deleted_count += (
                db.query(Session)
                .filter(Session.admin_id.in_(inactive_admin_ids))
                .delete(synchronize_session=False)
            )

        # Sessions admin orphelines (compte supprimé)
        deleted_count += (
            db.query(Session)
            .filter(Session.admin_id.isnot(None))
            .filter(~Session.admin_id.in_(db.query(Admin.id)))
            .delete(synchronize_session=False)
        )

        # Sessions user dont le compte est désactivé
        inactive_user_ids = [
            u.id for u in db.query(AppUser.id).filter(AppUser.is_active.is_(False)).all()
        ]
        if inactive_user_ids:
            deleted_count += (
                db.query(Session)
                .filter(Session.user_id.in_(inactive_user_ids))
                .delete(synchronize_session=False)
            )

        # Sessions user orphelines (compte supprimé)
        deleted_count += (
            db.query(Session)
            .filter(Session.user_id.isnot(None))
            .filter(~Session.user_id.in_(db.query(AppUser.id)))
            .delete(synchronize_session=False)
        )

        # Rétention par âge, uniquement si explicitement activée
        if session_max_age_days > 0:
            cutoff = datetime.now() - timedelta(days=session_max_age_days)
            deleted_count += (
                db.query(Session)
                .filter(Session.created_at < cutoff)
                .delete(synchronize_session=False)
            )

    return {"ok": True, "deleted": deleted_count}