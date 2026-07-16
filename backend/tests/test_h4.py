"""Script de test pour H4 — vérifie le filtre anti-scanner à 5 secondes
sur le pixel de tracking."""
import time
import uuid
import requests
from datetime import datetime, timezone
from db import get_db
from models import EmailLog


def test_case(label, delay_seconds):
    tracking_id = uuid.uuid4()
    with get_db() as db:
        mail = EmailLog(
            tracking_id=tracking_id,
            sender_email="bob@ulytechai.com",
            recipient_email="x@y.com",
            subject=label,
            body="contenu test",
        )
        db.add(mail)

    if delay_seconds:
        time.sleep(delay_seconds)

    resp = requests.get(f"http://localhost:8000/track/{tracking_id}")

    with get_db() as db:
        mail = db.query(EmailLog).filter(EmailLog.tracking_id == tracking_id).first()
        sent_at = mail.sent_at
        opened_at = mail.opened_at

    ecart = None
    if opened_at and sent_at:
        ecart = (opened_at - sent_at).total_seconds()

    print(f"\n--- {label} (délai {delay_seconds}s) ---")
    print(f"status pixel : {resp.status_code}")
    print(f"sent_at      : {sent_at}")
    print(f"opened_at    : {opened_at}")
    print(f"écart        : {ecart}")


test_case("Cas 1 - hit immédiat (scan présumé)", 0)
test_case("Cas 2 - hit après 6s (ouverture réelle présumée)", 6)