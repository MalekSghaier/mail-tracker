import os
import secrets
import hashlib
from datetime import datetime, timezone

import bcrypt
from fastapi import Depends, HTTPException, status, Cookie, Response, Header

from db import get_db
from models import Admin, AppUser, Session



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

    with get_db() as db:
        session = Session(
            token_hash=token_hash,
            role=role,
            subject=subject,
            admin_id=admin_id,
            user_id=user_id,
        )
        db.add(session)

    return token


def revoke_token(token: str) -> None:
    """Supprime une session — révocation immédiate et définitive."""
    token_hash = _hash_token(token)
    with get_db() as db:
        db.query(Session).filter(Session.token_hash == token_hash).delete()


def _load_session(token: str) -> dict:
    """Hache le token reçu et cherche la correspondance en base — jamais
    de comparaison sur le token en clair, jamais de token en clair stocké."""
    token_hash = _hash_token(token)

    with get_db() as db:
        session = db.query(Session).filter(Session.token_hash == token_hash).first()
        if not session:
            raise HTTPException(status_code=401, detail="Token invalide")

        payload = {"sub": session.subject, "role": session.role}
        if session.admin_id:
            payload["admin_id"] = session.admin_id
        if session.user_id:
            payload["user_id"] = session.user_id
        return payload


COOKIE_NAME = "session_token"

def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=False,       # true en prod, False en dev (localhost)
        samesite="strict",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")

# ---------- dependencies FastAPI ----------

def _resolve_token(
    session_token: str | None = Cookie(default=None, alias=COOKIE_NAME),
    authorization: str | None = Header(default=None),
) -> str | None:
    """Le cookie httpOnly (panel admin) est prioritaire ; le header
    Authorization reste supporté pour les pages employé (/mail, /imap-mail)
    qui utilisent encore localStorage — non modifiées pour l'instant."""
    if session_token:
        return session_token
    if authorization and authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ")
    return None


def get_current_admin(
    session_token: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> dict:
    """Le panel admin est désormais 100% cookie httpOnly — pas de fallback
    sur le header Authorization ici, contrairement à get_current_user."""
    if not session_token:
        raise HTTPException(status_code=401, detail="Authentification requise")
    payload = _load_session(session_token)

    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Accès admin requis")

    admin_id = payload.get("admin_id")
    if not admin_id:
        raise HTTPException(status_code=401, detail="Token invalide")

    with get_db() as db:
        admin = db.query(Admin).filter(Admin.id == admin_id).first()
        if not admin:
            raise HTTPException(status_code=401, detail="Compte introuvable")
        if not admin.is_active:
            raise HTTPException(status_code=403, detail="Compte désactivé")

    return payload


def get_current_user(token: str | None = Depends(_resolve_token)) -> dict:
    if not token:
        raise HTTPException(status_code=401, detail="Authentification requise")
    payload = _load_session(token)

    if payload.get("role") not in ("admin", "user"):
        raise HTTPException(status_code=403, detail="Accès refusé")

    if payload.get("role") == "admin":
        payload["account_role"] = "superadmin"

    if payload.get("role") == "user" and payload.get("user_id"):
        with get_db() as db:
            user = db.query(AppUser).filter(AppUser.id == payload["user_id"]).first()
            if not user:
                raise HTTPException(status_code=401, detail="Compte introuvable")
            if not user.is_active:
                raise HTTPException(status_code=403, detail="Compte désactivé")

            payload["email"] = user.email
            payload["department"] = user.department
            payload["account_role"] = user.account_role or "employee"

    return payload