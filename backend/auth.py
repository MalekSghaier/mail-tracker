import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from db import get_conn

JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError(
        "JWT_SECRET n'est pas défini. Définis cette variable d'environnement "
        "avant de démarrer l'application (aucune valeur par défaut n'est "
        "utilisée pour des raisons de sécurité)."
    )
JWT_ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60 * 24 * 365 * 10))


bearer_scheme = HTTPBearer(auto_error=False)


# ---------- mots de passe ----------

def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---------- JWT ----------

def create_access_token(subject: str, role: str, extra: dict | None = None) -> str:
    """role = 'admin' ou 'user'"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expiré")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token invalide")


# ---------- dependencies FastAPI ----------

def _get_payload(creds: HTTPAuthorizationCredentials | None) -> dict:
    if creds is None or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_token(creds.credentials)


def get_current_admin(creds: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> dict:
    """Valide le token, puis relit systématiquement is_active en base
    pour ce compte admin — même logique que get_current_user, pour que
    la désactivation d'un admin soit effective immédiatement, pas
    seulement après expiration du token."""
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
    """Valide le token, puis — pour les comptes 'user' (employés abonnés à
    l'agent) — relit le département et le rôle métier DEPUIS LA BASE à
    chaque requête plutôt que de faire confiance au JWT.

    Pourquoi : le JWT est une photo prise au moment du login (valide jusqu'à
    24h). Si un admin ARS change le département de quelqu'un, le rétrograde
    de "chef de département" à "employé", ou désactive son compte, on veut
    que ça s'applique IMMÉDIATEMENT — pas seulement après l'expiration du
    token. Le JWT ne sert donc qu'à prouver qui est l'utilisateur (son
    user_id) ; ses droits d'accès sont toujours vérifiés en base.
    """
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
    """Construit le filtre SQL à appliquer sur email_log selon le rôle
    métier de l'utilisateur connecté (account_role, relu en base par
    get_current_user) :

      - superadmin : aucun filtre → voit toutes les alertes de l'ARS
      - dept_admin : voit les mails envoyés par les employés de SON département
      - employee   : ne voit que ses propres mails envoyés 

    Retourne (clause_sql, params). clause_sql est un fragment à insérer
    tel quel dans la requête appelante (ex: "AND sender_email = %s"), ou
    une chaîne vide si aucun filtre n'est nécessaire.
    """
    account_role = user.get("account_role", "employee")

    if account_role == "superadmin":
        return "", []

    if account_role == "dept_admin":
        department = user.get("department")
        if not department:
            # Chef de département sans département assigné : par prudence,
            # ne voit rien plutôt que de tout voir par défaut.
            return "AND FALSE", []
        return (
            "AND sender_email IN (SELECT email FROM app_users WHERE department = %s)",
            [department],
        )

    # employee (comportement par défaut, y compris si account_role est absent)
    email = user.get("email")
    if not email:
        return "AND FALSE", []
    return "AND sender_email = %s", [email]