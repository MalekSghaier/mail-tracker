"""
Backend du POC Mail Detector — appelé par le MILTER (pas par sender.py).
Lancer avec : uvicorn app:app --reload --port 8000 --host 0.0.0.0

--host 0.0.0.0 est nécessaire pour que le serveur Zimbra (sur une autre
machine que ton PC) puisse joindre ce backend.
"""
import os
import uuid
from datetime import datetime, timedelta

import psycopg2
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ollama_client import generer_resume

load_dotenv()
app = FastAPI(title="Mail Detector POC")

THRESHOLD_MINUTES = int(os.getenv("ALERT_THRESHOLD_MINUTES", 2))


def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT", 5432),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


class EmailRegister(BaseModel):
    sender_email: str
    recipient_email: str
    cc_email: str | None = None
    subject: str
    body: str


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/emails/register")
def register_email(payload: EmailRegister):
    """Appelé par le milter Zimbra à chaque mail sortant intercepté."""
    tracking_id = str(uuid.uuid4())

    # Résumé IA — synchrone pour ce POC (en prod finale : Celery, voir mail_detector.md)
    ai_summary = generer_resume(payload.body)

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO email_log
           (tracking_id, sender_email, recipient_email, cc_email, subject, body, ai_summary)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (tracking_id, payload.sender_email, payload.recipient_email, payload.cc_email,
         payload.subject, payload.body, ai_summary),
    )
    conn.commit()
    cur.close()
    conn.close()
    return {"tracking_id": tracking_id}


@app.get("/track/{tracking_id}")
def track(tracking_id: str):
    """Le pixel. Chargé par le client mail quand le mail est ouvert."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """UPDATE email_log SET opened_at = NOW()
           WHERE tracking_id = %s AND opened_at IS NULL""",
        (tracking_id,),
    )
    conn.commit()
    cur.close()
    conn.close()
    return FileResponse("pixel.png", media_type="image/png")


@app.get("/api/alerts")
def get_alerts():
    """Liste des mails non ouverts depuis plus de ALERT_THRESHOLD_MINUTES."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """SELECT tracking_id, sender_email, recipient_email, cc_email, subject, ai_summary,
                  sent_at, reminder_done
           FROM email_log
           WHERE opened_at IS NULL
           AND alert_acked = FALSE
           AND sent_at < NOW() - (%s * INTERVAL '1 minute')""",
        (THRESHOLD_MINUTES,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {
            "tracking_id": r[0],
            "sender": r[1],
            "recipient": r[2],
            "cc": r[3] or "",
            "subject": r[4],
            "summary": r[5] or "",
            "sent_at": str(r[6]),
            "reminder_done": r[7],  # null / true / false
        }
        for r in rows
    ]


@app.post("/api/alerts/{tracking_id}/ack")
def ack_alert(tracking_id: str):
    """Appelé par l'agent C#/.NET après affichage du popup."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE email_log SET alert_acked = TRUE WHERE tracking_id = %s", (tracking_id,))
    conn.commit()
    cur.close()
    conn.close()
    return {"ok": True}


class ReminderAnswer(BaseModel):
    done: bool


@app.post("/api/alerts/{tracking_id}/reminder")
def set_reminder(tracking_id: str, payload: ReminderAnswer):
    """Appelé quand l'employé répond Oui/Non à 'T'as fait le rappel ?'.
    Persisté en base pour permettre un historique ultérieur."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """UPDATE email_log
           SET reminder_done = %s, reminder_answered_at = NOW()
           WHERE tracking_id = %s""",
        (payload.done, tracking_id),
    )
    conn.commit()
    cur.close()
    conn.close()
    return {"ok": True}