"""
imap_checker.py — Scénario B : vérifie l'état lu/non-lu des mails reçus
sur des comptes surveillés. Host/port IMAP viennent du .env (config
d'infrastructure fixe). Les motifs d'expéditeurs à exclure viennent de
la base (imap_excluded_patterns) — modifiables par un admin sans
redéploiement.
"""
import os
import imaplib
import email
from email.header import decode_header
from datetime import datetime, timedelta
from dotenv import load_dotenv

from db import get_db
from models import ImapAccount, ReceivedMailLog, ImapExcludedPattern
from crypto_utils import decrypt_secret

load_dotenv()

IMAP_HOST = os.getenv("IMAP_HOST")
IMAP_PORT = int(os.getenv("IMAP_PORT", 993))

if not IMAP_HOST:
    raise RuntimeError(
        "IMAP_HOST n'est pas défini dans .env. Ajoute IMAP_HOST et "
        "IMAP_PORT avant de lancer la synchronisation IMAP."
    )

LOOKBACK_DAYS = 30


def _decode_mime_str(value: str | None) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    decoded = ""
    for text, charset in parts:
        if isinstance(text, bytes):
            decoded += text.decode(charset or "utf-8", errors="replace")
        else:
            decoded += text
    return decoded


def _get_excluded_patterns(db) -> list[str]:
    """Charge les motifs d'exclusion actifs depuis la base — rechargés à
    chaque synchronisation, donc une modification par un admin prend
    effet dès la prochaine vérification, sans redémarrage du serveur."""
    rows = db.query(ImapExcludedPattern).filter(ImapExcludedPattern.is_active.is_(True)).all()
    return [r.pattern.lower() for r in rows]


def _is_excluded_sender(sender: str | None, patterns: list[str]) -> bool:
    if not sender or not patterns:
        return False
    sender_lower = sender.lower()
    return any(pattern in sender_lower for pattern in patterns)


def _fetch_inbox_state(account: ImapAccount, excluded_patterns: list[str]) -> list[dict]:
    """Se connecte au compte IMAP, liste les mails récents de INBOX et
    leur état \\Seen, en excluant les expéditeurs correspondant aux
    motifs actifs."""
    password = decrypt_secret(account.encrypted_password)

    imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    try:
        imap.login(account.email, password)
        imap.select("INBOX", readonly=True)

        since_date = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime("%d-%b-%Y")
        status, data = imap.search(None, f'(SINCE "{since_date}")')
        if status != "OK":
            return []

        uids = data[0].split()
        results = []
        for uid in uids:
            status, msg_data = imap.fetch(uid, "(FLAGS RFC822.HEADER INTERNALDATE)")
            if status != "OK" or not msg_data or msg_data[0] is None:
                continue

            flags = ()
            header_data = None

            for part in msg_data:
                if isinstance(part, tuple):
                    line, literal = part
                    found_flags = imaplib.ParseFlags(line)
                    if found_flags:
                        flags = found_flags
                    header_data = literal
                elif isinstance(part, bytes):
                    found_flags = imaplib.ParseFlags(part)
                    if found_flags:
                        flags = found_flags

            is_seen = b"\\Seen" in flags

            sender = subject = None
            received_at = None
            if header_data:
                msg = email.message_from_bytes(header_data)
                sender = _decode_mime_str(msg.get("From"))
                subject = _decode_mime_str(msg.get("Subject"))
                date_str = msg.get("Date")
                if date_str:
                    try:
                        received_at = email.utils.parsedate_to_datetime(date_str)
                        if received_at.tzinfo is not None:
                            received_at = received_at.replace(tzinfo=None)
                    except Exception:
                        received_at = None

            if _is_excluded_sender(sender, excluded_patterns):
                continue

            results.append({
                "uid": uid.decode("utf-8"),
                "sender": sender,
                "subject": subject,
                "received_at": received_at,
                "is_seen": is_seen,
            })
        return results
    finally:
        try:
            imap.close()
        except Exception:
            pass
        imap.logout()


def sync_account(account_id: int) -> None:
    with get_db() as db:
        account = db.query(ImapAccount).filter(ImapAccount.id == account_id, ImapAccount.is_active.is_(True)).first()
        if not account:
            return

        excluded_patterns = _get_excluded_patterns(db)

        try:
            messages = _fetch_inbox_state(account, excluded_patterns)
        except Exception as exc:
            print(f"[imap_checker] échec connexion IMAP pour {account.email}: {exc}")
            return

        for msg in messages:
            existing = db.query(ReceivedMailLog).filter(
                ReceivedMailLog.imap_account_id == account.id,
                ReceivedMailLog.message_uid == msg["uid"],
            ).first()

            if existing:
                existing.is_seen = msg["is_seen"]
                existing.last_checked_at = datetime.now()
            else:
                entry = ReceivedMailLog(
                    imap_account_id=account.id,
                    message_uid=msg["uid"],
                    sender_email=msg["sender"],
                    subject=msg["subject"],
                    received_at=msg["received_at"],
                    is_seen=msg["is_seen"],
                )
                db.add(entry)