"""
Worker Celery — calcule le résumé IA (Ollama) en arrière-plan, hors du
chemin critique de register_email() (voir H3 de l'audit).

Broker : transport SQLAlchemy de Kombu, qui réutilise directement la base
Postgres existante comme file d'attente — pas besoin de Redis/Memurai/WSL.

Lancer le worker (Windows, pool=solo obligatoire) :
    celery -A tasks worker --loglevel=info --pool=solo
"""
import os
from celery import Celery
import sys
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


@celery_app.task(bind=True, max_retries=3, default_retry_delay=10)
def compute_summary_task(self, tracking_id: str, body: str):
    """Calcule le résumé IA et le persiste en base. Retry automatique
    (3 fois, 10s d'intervalle) si Ollama est indisponible ou timeout."""
    from ollama_client import generer_resume
    from db import get_conn

    try:
        ai_summary = generer_resume(body)
    except Exception as exc:
        print(f"[compute_summary_task] tentative échouée pour {tracking_id}: {exc}")
        raise self.retry(exc=exc)

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE email_log SET ai_summary = %s WHERE tracking_id = %s",
        (ai_summary, tracking_id),
    )
    conn.commit()
    cur.close()
    conn.close()
    return {"tracking_id": tracking_id, "ok": True}