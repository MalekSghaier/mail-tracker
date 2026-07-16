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


@celery_app.task
def reset_expired_reminders():
    from db import get_db
    from models import EmailLog
    from datetime import datetime

    with get_db() as db:
        db.query(EmailLog).filter(
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

    return {"ok": True}