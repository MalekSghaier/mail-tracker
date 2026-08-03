from imap_checker import sync_account
from db import get_db
from models import ImapAccount

with get_db() as db:
    accounts = db.query(ImapAccount).all()
    for a in accounts:
        sync_account(a.id)