"""
Worker Celery — calcule le résumé IA (Ollama) en arrière-plan, hors du
chemin critique de register_email(), et exécute des tâches périodiques
de maintenance (reset des rappels expirés, voir M2).

Broker : transport SQLAlchemy de Kombu, qui réutilise directement la base
Postgres existante comme file d'attente — pas besoin de Redis/Memurai/WSL.

Lancer le worker (Windows, pool=solo obligatoire) :
    celery -A tasks worker --loglevel=info --pool=solo

Lancer le scheduler Beat (pour les tâches périodiques) :
    celery -A tasks beat --loglevel=info
"""
import os
from celery import Celery
import sys
from dotenv import load_dotenv
from db import get_conn



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
        "schedule": 30.0,  # secondes
    },
}


@celery_app.task(bind=True, max_retries=3, default_retry_delay=10)
def compute_summary_task(self, tracking_id: str, body: str):
    """Calcule le résumé IA et le persiste en base. Retry automatique
    (3 fois, 10s d'intervalle) si Ollama est indisponible ou timeout."""
    from ollama_client import generer_resume

    try:
        ai_summary = generer_resume(body)
    except Exception as exc:
        print(f"[compute_summary_task] tentative échouée pour {tracking_id}: {exc}")
        raise self.retry(exc=exc)

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE email_log SET ai_summary = %s WHERE tracking_id = %s",
            (ai_summary, tracking_id),
        )
        cur.close()
    return {"tracking_id": tracking_id, "ok": True}


@celery_app.task
def reset_expired_reminders():
    """Tâche périodique : réinitialise les mails dont le délai de recheck
    de rappel est dépassé. Anciennement fait à l'intérieur de
    GET /api/alerts (anti-pattern REST, voir M2) — sorti dans cette tâche
    planifiée indépendante via Celery Beat, pour que GET /api/alerts
    reste une lecture pure sans effet de bord."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """UPDATE email_log
               SET alert_acked = FALSE,
                   reminder_done = NULL,
                   reminder_answered_at = NULL,
                   reminder_recheck_at = NULL
               WHERE reminder_done = FALSE
               AND reminder_recheck_at IS NOT NULL
               AND reminder_recheck_at < NOW()"""
        )
        cur.close()
    return {"ok": True}