# scripts/backfill_uidvalidity.py
from db import get_db
from models import ImapAccount, ReceivedMailLog
from imap_checker import _get_current_uidvalidity

with get_db() as db:
    accounts = db.query(ImapAccount).filter(ImapAccount.is_active.is_(True)).all()
    for account in accounts:
        try:
            uidval = _get_current_uidvalidity(account)
        except Exception as exc:
            print(f"[backfill] échec pour {account.email}: {exc}")
            continue
        # Met à jour le compte
        account.last_uidvalidity = uidval
        # Remplit les anciennes lignes qui n'ont pas encore de uidvalidity
        db.query(ReceivedMailLog).filter(
            ReceivedMailLog.imap_account_id == account.id,
            ReceivedMailLog.uidvalidity.is_(None),
        ).update({"uidvalidity": uidval})
        print(f"[backfill] {account.email}: uidvalidity={uidval}")