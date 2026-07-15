import os
import secrets
import hashlib
from datetime import datetime, timezone

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from db import get_conn

bearer_scheme = HTTPBearer(auto_error=False)


# ---------- mots de passe ----------

def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---------- tokens opaques 256 bits, stockés hachés (voir M8) ----------

def _hash_token(token: str) -> str:
    """SHA-256 est suffisant ici (pas bcrypt) : le token est déjà une
    valeur aléatoire à haute entropie (256 bits), contrairement à un mot
    de passe humain à faible entropie qui a besoin d'un ralentissement
    volontaire (salt + coût bcrypt) contre le brute-force. Un hash rapide
    et déterministe est justement ce qu'il faut ici, pour pouvoir
    retrouver la session par une recherche directe en base."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(subject: str, role: str, extra: dict | None = None) -> str:
    """Crée un token opaque de 256 bits (32 octets), retourné en clair
    UNE SEULE FOIS au client. Seul son hash SHA-256 est conservé en base
    — si la base fuit, les tokens stockés sont inutilisables tels quels,
    contrairement à un stockage en clair. Sans expiration (conforme au
    cadrage mail_detector.md) : la révocation se fait uniquement via
    suppression explicite de la session (logout, désactivation de compte)."""
    token = secrets.token_hex(32)  
    token_hash = _hash_token(token)

    admin_id = (extra or {}).get("admin_id")
    user_id = (extra or {}).get("user_id")

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO sessions (token_hash, role, subject, admin_id, user_id)
               VALUES (%s, %s, %s, %s, %s)""",
            (token_hash, role, subject, admin_id, user_id),
        )
        cur.close()

    return token


def revoke_token(token: str) -> None:
    """Supprime une session — révocation immédiate et définitive."""
    token_hash = _hash_token(token)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM sessions WHERE token_hash = %s", (token_hash,))
        cur.close()


def _load_session(token: str) -> dict:
    """Hache le token reçu et cherche la correspondance en base — jamais
    de comparaison sur le token en clair, jamais de token en clair stocké."""
    token_hash = _hash_token(token)

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT role, subject, admin_id, user_id
               FROM sessions WHERE token_hash = %s""",
            (token_hash,),
        )
        row = cur.fetchone()
        cur.close()

    if not row:
        raise HTTPException(status_code=401, detail="Token invalide")

    role, subject, admin_id, user_id = row
    payload = {"sub": subject, "role": role}
    if admin_id:
        payload["admin_id"] = admin_id
    if user_id:
        payload["user_id"] = user_id
    return payload


# ---------- dependencies FastAPI ----------

def _get_payload(creds: HTTPAuthorizationCredentials | None) -> dict:
    if creds is None or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _load_session(creds.credentials)


def get_current_admin(creds: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> dict:
    """Valide le token, puis relit systématiquement is_active en base
    pour ce compte admin — même logique que get_current_user, pour que
    la désactivation d'un admin soit effective immédiatement."""
    payload = _get_payload(creds)
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Accès admin requis")

    admin_id = payload.get("admin_id")
    if not admin_id:
        raise HTTPException(status_code=401, detail="Token invalide")

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT is_active FROM admins WHERE id = %s", (admin_id,))
        row = cur.fetchone()
        cur.close()

    if not row:
        raise HTTPException(status_code=401, detail="Compte introuvable")
    if not row[0]:
        raise HTTPException(status_code=403, detail="Compte désactivé")

    return payload


def get_current_user(creds: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> dict:
    """Valide le token, puis — pour les comptes 'user' — relit le
    département et le rôle métier DEPUIS LA BASE à chaque requête plutôt
    que de faire confiance au contenu du token."""
    payload = _get_payload(creds)
    if payload.get("role") not in ("admin", "user"):
        raise HTTPException(status_code=403, detail="Accès refusé")

    if payload.get("role") == "user" and payload.get("user_id"):
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT email, department, account_role, is_active FROM app_users WHERE id = %s",
                (payload["user_id"],),
            )
            row = cur.fetchone()
            cur.close()

        if not row:
            raise HTTPException(status_code=401, detail="Compte introuvable")
        if not row[3]:
            raise HTTPException(status_code=403, detail="Compte désactivé")

        payload["email"] = row[0]
        payload["department"] = row[1]
        payload["account_role"] = row[2] or "employee"

    return payload


def build_alerts_filter(user: dict) -> tuple[str, list]:

    account_role = user.get("account_role", "employee")

    if account_role == "superadmin":
        return "", []

    if account_role == "dept_admin":
        department = user.get("department")
        if not department:
            return "AND FALSE", []
        return (
            "AND sender_email IN (SELECT email FROM app_users WHERE department = %s)",
            [department],
        )

    email = user.get("email")
    if not email:
        return "AND FALSE", []
    return "AND sender_email = %s", [email]