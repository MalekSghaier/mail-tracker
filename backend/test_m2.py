"""Vérifie que GET /api/alerts n'a plus d'effet de bord (M2), et que le
reset des rappels expirés est bien pris en charge par Celery Beat en
tâche de fond, indépendamment de tout appel HTTP."""
import time
import uuid
import requests
from datetime import datetime, timezone, timedelta
from db import get_db
from models import EmailLog
from auth import create_access_token

# 1. Génère un token valide directement
TOKEN = create_access_token(
    subject="test_m2_script",
    role="user",
    extra={"user_id": None, "account_role": "superadmin"},
)

# 2. Crée un mail avec reminder_recheck_at déjà expiré (dans le passé)
tracking_id = uuid.uuid4()
now = datetime.now(timezone.utc)
with get_db() as db:
    mail = EmailLog(
        tracking_id=tracking_id,
        sender_email="bob@ulytechai.com",
        recipient_email="x@y.com",
        subject="test M2",
        body="contenu",
        sent_at=now - timedelta(minutes=10),
        reminder_done=False,
        reminder_recheck_at=now - timedelta(minutes=1),
    )
    db.add(mail)
print(f"Mail de test créé (reminder_recheck_at déjà expiré) : {tracking_id}")

# 3. Appelle GET /api/alerts
resp = requests.get(
    "http://localhost:8000/api/alerts",
    headers={"Authorization": f"Bearer {TOKEN}"},
)
print(f"GET /api/alerts -> status {resp.status_code}")
if resp.status_code != 200:
    print(f"Réponse : {resp.text}")

# 4. Vérifie immédiatement après (sans attendre Celery Beat) que la
#    ligne N'A PAS été modifiée par le GET lui-même
with get_db() as db:
    mail = db.query(EmailLog).filter(EmailLog.tracking_id == tracking_id).first()
    reminder_done = mail.reminder_done
    reminder_recheck_at = mail.reminder_recheck_at

print(f"Juste après le GET -> reminder_done={reminder_done}, reminder_recheck_at={reminder_recheck_at}")
if reminder_done is False and reminder_recheck_at is not None:
    print("✅ M2 corrigé : le GET seul n'a pas modifié la ligne.")
else:
    print("❌ M2 PAS corrigé : le GET a modifié la ligne directement.")

# 5. Attend que Celery Beat tourne (toutes les 30s) et revérifie
print("\nAttente de 35s pour laisser Celery Beat agir...")
time.sleep(35)

with get_db() as db:
    mail = db.query(EmailLog).filter(EmailLog.tracking_id == tracking_id).first()
    reminder_done = mail.reminder_done
    reminder_recheck_at = mail.reminder_recheck_at

print(f"Après 35s -> reminder_done={reminder_done}, reminder_recheck_at={reminder_recheck_at}")
if reminder_done is None and reminder_recheck_at is None:
    print("✅ Celery Beat a bien fait le reset en tâche de fond.")
else:
    print("❌ Celery Beat n'a pas fonctionné comme attendu.")