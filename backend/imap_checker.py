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
import re
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


def _fetch_inbox_state(account: ImapAccount, excluded_patterns: list[str],
                        known_uids: set[str], uids_missing_body: set[str]) -> list[dict]:
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
            uid_str = uid.decode("utf-8")
            is_known = uid_str in known_uids
            # Récupère le corps complet si le mail est nouveau, OU s'il est
            # déjà connu mais que son corps n'a jamais été capturé (mails
            # synchronisés avant l'ajout de body/ai_summary au modèle).
            needs_full_fetch = (not is_known) or (uid_str in uids_missing_body)

            fetch_parts = "(FLAGS RFC822 INTERNALDATE)" if needs_full_fetch else "(FLAGS)"
            status, msg_data = imap.fetch(uid, fetch_parts)
            if status != "OK" or not msg_data or msg_data[0] is None:
                continue

            flags = ()
            raw_message = None
            for part in msg_data:
                if isinstance(part, tuple):
                    line, literal = part
                    found_flags = imaplib.ParseFlags(line)
                    if found_flags:
                        flags = found_flags
                    raw_message = literal
                elif isinstance(part, bytes):
                    found_flags = imaplib.ParseFlags(part)
                    if found_flags:
                        flags = found_flags

            is_seen = b"\\Seen" in flags

            if not needs_full_fetch:
                results.append({"uid": uid_str, "is_seen": is_seen, "needs_update_only": True})
                continue

            sender = subject = cc = None
            received_at = None
            body_text = ""
            has_attachment = False
            if raw_message:
                msg = email.message_from_bytes(raw_message)
                sender = _decode_mime_str(msg.get("From"))
                subject = _decode_mime_str(msg.get("Subject"))
                cc = _decode_mime_str(msg.get("Cc"))
                date_str = msg.get("Date")
                if date_str:
                    try:
                        received_at = email.utils.parsedate_to_datetime(date_str)
                        if received_at.tzinfo is not None:
                            received_at = received_at.replace(tzinfo=None)
                    except Exception:
                        received_at = None
                body_text_raw = _extract_body_text(msg)
                body_text = _clean_body_for_summary(body_text_raw)
                has_attachment = _has_attachment(msg)

            if not is_known and _is_excluded_sender(sender, excluded_patterns):
                continue

            results.append({
                "uid": uid_str, "sender": sender, "cc": cc, "subject": subject,
                "received_at": received_at, "is_seen": is_seen, "body": body_text,
                "has_attachment": has_attachment,
                "needs_update_only": False, "is_known": is_known,
            })
        return results
    finally:
        try:
            imap.close()
        except Exception:
            pass
        imap.logout()

def _clean_body_for_summary(text: str) -> str:
    """Nettoie le texte brut des mails reçus (newsletters marketing) avant
    résumé IA — enlève URLs, liens de désabonnement, espaces multiples, et
    tronque à une longueur raisonnable. N'affecte pas le body stocké en
    base pour affichage, seulement celui envoyé à generer_resume."""
    if not text:
        return text

    # Supprime les URLs (souvent la source de bruit dans les newsletters)
    cleaned = re.sub(r"https?://\S+", "", text)

    # Supprime les lignes typiques de désabonnement / mentions légales
    cleaned = re.sub(
        r"(?i)(se désabonner|unsubscribe|désinscri\w*|politique de confidentialit\w*|"
        r"tous droits réservés|all rights reserved|voir dans le navigateur|view in browser).*",
        "", cleaned
    )

    # Réduit les espaces/sauts de ligne multiples
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # Tronque : un résumé n'a pas besoin de plus de ~2000 caractères de contexte,
    # et ça réduit le bruit pour un petit modèle 1B.
    return cleaned[:2000]


def sync_account(account_id: int) -> None:
    new_summaries = []
    retry_summaries = []

    with get_db() as db:
        account = db.query(ImapAccount).filter(ImapAccount.id == account_id, ImapAccount.is_active.is_(True)).first()
        if not account:
            return

        excluded_patterns = _get_excluded_patterns(db)

        existing_rows = db.query(ReceivedMailLog).filter(
            ReceivedMailLog.imap_account_id == account.id
        ).all()
        known_uids = {r.message_uid for r in existing_rows}
        uids_missing_body = {r.message_uid for r in existing_rows if not r.body}

        try:
            messages = _fetch_inbox_state(account, excluded_patterns, known_uids, uids_missing_body)
        except Exception as exc:
            print(f"[imap_checker] échec connexion IMAP pour {account.email}: {exc}")
            return

        for msg in messages:
            existing = db.query(ReceivedMailLog).filter(
                ReceivedMailLog.imap_account_id == account.id,
                ReceivedMailLog.message_uid == msg["uid"],
            ).first()

            if msg.get("needs_update_only"):
                if existing:
                    existing.is_seen = msg["is_seen"]
                    existing.last_checked_at = datetime.now()
                continue

            if existing:
                existing.is_seen = msg["is_seen"]
                existing.last_checked_at = datetime.now()
                if msg.get("body") or msg.get("has_attachment"):
                    existing.body = msg["body"]
                    existing.cc_email = msg.get("cc")
                    if not existing.subject:
                        existing.subject = msg.get("subject")
                    new_summaries.append((str(existing.tracking_id), msg["body"], msg.get("has_attachment", False)))
            else:
                entry = ReceivedMailLog(
                    imap_account_id=account.id,
                    message_uid=msg["uid"],
                    sender_email=msg.get("sender"),
                    cc_email=msg.get("cc"),
                    subject=msg.get("subject"),
                    body=msg.get("body"),
                    received_at=msg.get("received_at"),
                    is_seen=msg.get("is_seen", False),
                )
                db.add(entry)
                db.flush()
                if msg.get("body") or msg.get("has_attachment"):
                    new_summaries.append((str(entry.tracking_id), msg["body"], msg.get("has_attachment", False)))

        stuck = (
            db.query(ReceivedMailLog)
            .filter(
                ReceivedMailLog.imap_account_id == account.id,
                ReceivedMailLog.ai_summary.is_(None),
                ReceivedMailLog.is_seen.is_(False),
                ReceivedMailLog.body.isnot(None),
                ReceivedMailLog.body != "",
            )
            .all()
        )
        for entry in stuck:
            already_queued = any(tid == str(entry.tracking_id) for tid, _, _ in new_summaries)
            if not already_queued:
                retry_summaries.append((str(entry.tracking_id), entry.body, False))

    from tasks import compute_imap_summary_task
    for tracking_id, body, has_attachment in new_summaries + retry_summaries:
        compute_imap_summary_task.delay(tracking_id, body, has_attachment)
    

def _extract_body_text(msg) -> str:
    """Extrait le texte brut du corps (privilégie text/plain, replie sur text/html nettoyé)."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition") or ""):
                try:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
                except Exception:
                    continue
        for part in msg.walk():
            if part.get_content_type() == "text/html" and "attachment" not in str(part.get("Content-Disposition") or ""):
                try:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or "utf-8"
                    return re.sub("<[^<]+?>", "", payload.decode(charset, errors="replace"))
                except Exception:
                    continue
        return ""
    try:
        payload = msg.get_payload(decode=True)
        charset = msg.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")
    except Exception:
        return msg.get_payload() or ""


def _has_attachment(msg) -> bool:
    """Détecte si le mail contient une pièce jointe (Content-Disposition
    attachment, ou pièce jointe nommée sans disposition explicite)."""
    if not msg.is_multipart():
        return False
    for part in msg.walk():
        disposition = str(part.get("Content-Disposition") or "")
        if "attachment" in disposition.lower():
            return True
        if part.get_filename() and part.get_content_maintype() not in ("text", "multipart"):
            return True
    return False