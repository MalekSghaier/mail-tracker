"""
imap_checker.py — Scénario B : vérifie l'état lu/non-lu des mails reçus
sur des comptes surveillés. Host/port IMAP viennent du .env (config
d'infrastructure fixe). Les motifs d'expéditeurs à exclure viennent de
la base (imap_excluded_patterns) — modifiables par un admin sans
redéploiement.

Suivi d'UIDVALIDITY (correction F10) : les UID IMAP ne sont uniques que
tant que l'UIDVALIDITY de la boîte ne change pas. Chaque ligne
ReceivedMailLog est taguée avec l'UIDVALIDITY sous laquelle son UID a
été observé, et TOUT matching (lecture ET écriture) se fait sur le
triplet (compte, uid, uidvalidity). Si le serveur réattribue un jour
les UID, l'ancien enregistrement n'est jamais retrouvé ni écrasé par
erreur — un nouvel enregistrement est simplement créé.
"""
import os
import imaplib
import email
import re
import logging
from email.header import decode_header
from datetime import datetime, timedelta
from dotenv import load_dotenv

from db import get_db
from models import ImapAccount, ReceivedMailLog, ImapExcludedPattern
from crypto_utils import decrypt_secret


logger = logging.getLogger(__name__)


load_dotenv()

IMAP_HOST = os.getenv("IMAP_HOST")
IMAP_PORT = int(os.getenv("IMAP_PORT", 993))

if not IMAP_HOST:
    raise RuntimeError(
        "IMAP_HOST n'est pas défini dans .env. Ajoute IMAP_HOST et "
        "IMAP_PORT avant de lancer la synchronisation IMAP."
    )

LOOKBACK_DAYS = int(os.getenv("IMAP_LOOKBACK_DAYS", 30))
RETRY_COOLDOWN_MINUTES = int(os.getenv("IMAP_RETRY_COOLDOWN_MINUTES", 10))


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


def _read_uidvalidity(imap: imaplib.IMAP4_SSL) -> int | None:
    """Lit l'UIDVALIDITY de la boîte actuellement sélectionnée (doit être
    appelé juste après un SELECT/EXAMINE)."""
    typ, data = imap.response("UIDVALIDITY")
    if not data or data[0] is None:
        return None
    try:
        return int(data[0])
    except (TypeError, ValueError):
        return None


def _get_current_uidvalidity(account: ImapAccount) -> int | None:
    """Ouvre une connexion IMAP dédiée juste pour lire l'UIDVALIDITY
    courante (utilisé par le script de backfill)."""
    password = decrypt_secret(account.encrypted_password)
    imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    try:
        imap.login(account.email, password)
        imap.select("INBOX", readonly=True)
        return _read_uidvalidity(imap)
    finally:
        try:
            imap.close()
        except Exception:
            pass
        imap.logout()


def _fetch_inbox_state(account: ImapAccount, excluded_patterns: list[str],
                        existing_rows: list[ReceivedMailLog]) -> tuple[list[dict], int | None]:
    """Se connecte une seule fois, lit l'UIDVALIDITY courante, puis calcule
    known_uids/uids_missing_body à partir de cette valeur (et non plus
    passés en paramètre) pour garantir qu'on ne compare jamais des UID
    appartenant à deux epochs UIDVALIDITY différentes."""
    password = decrypt_secret(account.encrypted_password)

    imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    try:
        imap.login(account.email, password)
        imap.select("INBOX", readonly=True)
        current_uidvalidity = _read_uidvalidity(imap)

        known_uids = {
            r.message_uid for r in existing_rows
            if r.uidvalidity == current_uidvalidity
        }
        uids_missing_body = {
            r.message_uid for r in existing_rows
            if r.uidvalidity == current_uidvalidity and not r.body
        }

        since_date = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime("%d-%b-%Y")
        status, data = imap.search(None, f'(SINCE "{since_date}")')
        if status != "OK":
            return [], current_uidvalidity

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
        return results, current_uidvalidity
    finally:
        try:
            imap.close()
        except Exception:
            pass
        imap.logout()


def _clean_body_for_summary(text: str) -> str:
    if not text:
        return text

    cleaned = re.sub(r"https?://\S+", "", text)
    cleaned = re.sub(
        r"(?i)(se désabonner|unsubscribe|désinscri\w*|politique de confidentialit\w*|"
        r"tous droits réservés|all rights reserved|voir dans le navigateur|view in browser).*",
        "", cleaned
    )
    cleaned = _strip_signature(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
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

        try:
            messages, current_uidvalidity = _fetch_inbox_state(account, excluded_patterns, existing_rows)
        except Exception as exc:
            logger.error("Échec connexion IMAP pour %s", account.email, exc_info=True)
            return

        if current_uidvalidity is None:
            # On ne sait pas sous quelle epoch on se trouve : matcher
            # quand même serait risquer exactement la corruption qu'on
            # cherche à éviter. On préfère sauter ce cycle plutôt que de
            # deviner.
            logger.warning("UIDVALIDITY introuvable pour %s, sync annulée pour ce cycle", account.email)
            return

        if account.last_uidvalidity is not None and current_uidvalidity != account.last_uidvalidity:
            logger.warning(
                "UIDVALIDITY a changé pour %s (%s -> %s). Les anciens UID ne seront plus matchés (comportement attendu, pas une erreur).",
                account.email, account.last_uidvalidity, current_uidvalidity,
            )

        account.last_uidvalidity = current_uidvalidity

        for msg in messages:
            existing = db.query(ReceivedMailLog).filter(
                ReceivedMailLog.imap_account_id == account.id,
                ReceivedMailLog.message_uid == msg["uid"],
                ReceivedMailLog.uidvalidity == current_uidvalidity,
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
                    existing.summary_requested_at = datetime.now()
                    new_summaries.append((str(existing.tracking_id), msg["body"], msg.get("has_attachment", False)))
            else:
                entry = ReceivedMailLog(
                    imap_account_id=account.id,
                    message_uid=msg["uid"],
                    uidvalidity=current_uidvalidity,
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
                    entry.summary_requested_at = datetime.now()
                    new_summaries.append((str(entry.tracking_id), msg["body"], msg.get("has_attachment", False)))

        
        stuck = (
            db.query(ReceivedMailLog)
            .filter(
                ReceivedMailLog.imap_account_id == account.id,
                ReceivedMailLog.ai_summary.is_(None),
                ReceivedMailLog.body.isnot(None),
                ReceivedMailLog.body != "",
            )
            .filter(
                (ReceivedMailLog.summary_requested_at.is_(None))
                | (ReceivedMailLog.summary_requested_at < datetime.now() - timedelta(minutes=RETRY_COOLDOWN_MINUTES))
            )
            .all()
        )
        for entry in stuck:
            already_queued = any(tid == str(entry.tracking_id) for tid, _, _ in new_summaries)
            if not already_queued:
                entry.summary_requested_at = datetime.now()
                retry_summaries.append((str(entry.tracking_id), entry.body, False))

    from tasks import compute_imap_summary_task
    for tracking_id, body, has_attachment in new_summaries + retry_summaries:
        compute_imap_summary_task.delay(tracking_id, body, has_attachment)


def _extract_body_text(msg) -> str:
    """Extrait le texte brut du corps (privilégie text/plain, replie sur text/html nettoyé)."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.is_multipart():
                continue
            # Une partie avec un nom de fichier est une pièce jointe,
            # même sans Content-Disposition: attachment explicite.
            if part.get_filename():
                continue
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition") or ""):
                try:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
                except Exception:
                    continue
        for part in msg.walk():
            if part.is_multipart() or part.get_filename():
                continue
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
    """Détecte si le mail contient une pièce jointe : Content-Disposition
    attachment, OU toute partie non-multipart portant un nom de fichier
    (indépendamment de son Content-Type)."""
    if not msg.is_multipart():
        return False
    for part in msg.walk():
        if part.is_multipart():
            continue
        disposition = str(part.get("Content-Disposition") or "")
        if "attachment" in disposition.lower():
            return True
        if part.get_filename():
            return True
    return False


_SIGNATURE_MARKERS = re.compile(
    r"(?i)^\s*(cordialement|bien à vous|salutations professionnelles|"
    r"best regards|sincerely)\b"
)
_SIGNATURE_PHONE = re.compile(r"^\s*\+?\d[\d\s]{7,}\d\s*$")


def _strip_signature(text: str) -> str:
    """Coupe le texte au début du bloc signature, détecté uniquement
    dans les dernières lignes du message (pas en recherche libre sur
    tout le corps). Évite de tronquer du contenu légitime contenant
    incidemment un mot-clé de signature ou une suite de chiffres
    (référence, IBAN partiel, etc.) plus tôt dans le texte."""
    if not text:
        return text

    lines = text.split("\n")
    # Fenêtre de recherche : dernier tiers du message, au moins 6 lignes
    tail_start = max(0, len(lines) - max(6, len(lines) // 3))

    for i in range(tail_start, len(lines)):
        line = lines[i]
        if _SIGNATURE_MARKERS.match(line) or _SIGNATURE_PHONE.match(line):
            return "\n".join(lines[:i]).strip()

    return text