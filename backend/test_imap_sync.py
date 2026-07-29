# test_imap_sync.py
from imap_checker import sync_account
from db import get_db
from models import ImapAccount

with get_db() as db:
    accounts = db.query(ImapAccount).all()
    for a in accounts:
        print(f"Sync pour {a.email} (id={a.id})...")
        sync_account(a.id)

print("Terminé — vérifie received_mail_log en base.")