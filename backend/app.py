import html as html_module
import os
import uuid as uuid_lib
from datetime import datetime, timedelta
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends, Header, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from ollama_client import generer_resume
from admin_page import router as admin_router
from db import get_db
from auth import hash_password, verify_password, create_access_token, get_current_admin, get_current_user, revoke_token
from tasks import compute_summary_task
from contextlib import asynccontextmanager
from sqlalchemy import or_
from models import EmailLog, Admin, AppUser, Session

load_dotenv()

MILTER_SHARED_SECRET = os.getenv("MILTER_SHARED_SECRET")
THRESHOLD_MINUTES = int(os.getenv("ALERT_THRESHOLD_MINUTES", 2))
RECHECK_MINUTES = int(os.getenv("REMINDER_RECHECK_MINUTES", 1))
PIXEL_ANTISCAN_DELAY_SECONDS = 5

app = FastAPI(title="Mail Detector POC")
app.include_router(admin_router)


def verify_milter_secret(x_milter_secret: str = Header(None)):
    if not MILTER_SHARED_SECRET:
        raise HTTPException(status_code=500, detail="MILTER_SHARED_SECRET non configuré côté serveur")
    if x_milter_secret != MILTER_SHARED_SECRET:
        raise HTTPException(status_code=401, detail="Secret invalide")


class EmailRegister(BaseModel):
    sender_email: str
    recipient_email: str
    cc_email: str | None = None
    subject: str
    body: str


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/emails/register")
def register_email(payload: EmailRegister, _=Depends(verify_milter_secret)):  
    tracking_id = str(uuid_lib.uuid4())

    with get_db() as db:
        mail = EmailLog(
            tracking_id=uuid_lib.UUID(tracking_id),
            sender_email=payload.sender_email,
            recipient_email=payload.recipient_email,
            cc_email=payload.cc_email,
            subject=payload.subject,
            body=payload.body,
        )
        db.add(mail)

    compute_summary_task.delay(tracking_id, payload.body)

    return {"tracking_id": tracking_id}

@app.get("/track/{tracking_id}")
def track(tracking_id: str):
    with get_db() as db:
        mail = db.query(EmailLog).filter(EmailLog.tracking_id == uuid_lib.UUID(tracking_id)).first()
        if mail and mail.opened_at is None and mail.sent_at:
            cutoff = datetime.now() - timedelta(seconds=PIXEL_ANTISCAN_DELAY_SECONDS)
            if mail.sent_at < cutoff:
                mail.opened_at = datetime.now()

    return FileResponse(
        "pixel.png",
        media_type="image/png",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )

def _apply_role_filter(query, user: dict):
    """Équivalent ORM de build_alerts_filter — appliqué directement sur
    une requête SQLAlchemy plutôt que par concaténation de SQL texte."""
    account_role = user.get("account_role", "employee")

    if account_role == "superadmin":
        return query

    if account_role == "dept_admin":
        department = user.get("department")
        if not department:
            return query.filter(False)
        with get_db() as db:
            emails = [r.email for r in db.query(AppUser.email).filter(AppUser.department == department).all()]
        return query.filter(EmailLog.sender_email.in_(emails))

    email = user.get("email")
    if not email:
        return query.filter(False)
    return query.filter(EmailLog.sender_email == email)

@app.get("/api/alerts")
def get_alerts(user=Depends(get_current_user)):

    with get_db() as db:
        pending_q = db.query(EmailLog).filter(
            EmailLog.opened_at.is_(None),
            EmailLog.alert_acked.is_(False),
            EmailLog.reminder_done.is_(None),
        )
        cutoff = datetime.now() - timedelta(minutes=THRESHOLD_MINUTES)
        pending_q = pending_q.filter(EmailLog.sent_at < cutoff)
        pending_q = _apply_role_filter(pending_q, user)

        results = [
            {
                "tracking_id": str(r.tracking_id), "sender": r.sender_email,
                "recipient": r.recipient_email, "cc": r.cc_email or "",
                "subject": r.subject or "", "summary": r.ai_summary or "",
                "sent_at": str(r.sent_at), "reminder_done": r.reminder_done,
                "category": "pending",
            }
            for r in pending_q.all()
        ]

        seen_q = db.query(EmailLog).filter(
            EmailLog.alert_acked.is_(True),
            EmailLog.reminder_done.is_(None),
            EmailLog.opened_at.is_(None),
        )
        seen_q = _apply_role_filter(seen_q, user)

        for r in seen_q.all():
            results.append({
                "tracking_id": str(r.tracking_id), "sender": r.sender_email,
                "recipient": r.recipient_email, "cc": r.cc_email or "",
                "subject": r.subject or "", "summary": r.ai_summary or "",
                "sent_at": str(r.sent_at), "reminder_done": r.reminder_done,
                "category": "seen_no_answer",
            })

    return results

@app.get("/api/auth/verify")
def verify_token(user=Depends(get_current_user)):
    return {"ok": True, "sub": user.get("sub"), "role": user.get("role")}

@app.post("/api/alerts/{tracking_id}/ack")
def ack_alert(tracking_id: str, user=Depends(get_current_user)):
    with get_db() as db:
        mail = db.query(EmailLog).filter(EmailLog.tracking_id == uuid_lib.UUID(tracking_id)).first()
        if mail:
            mail.alert_acked = True
    return {"ok": True}

class ReminderAnswer(BaseModel):
    done: bool

@app.post("/api/alerts/{tracking_id}/reminder")
def set_reminder(tracking_id: str, payload: ReminderAnswer, user=Depends(get_current_user)):
    with get_db() as db:
        query = db.query(EmailLog).filter(EmailLog.tracking_id == uuid_lib.UUID(tracking_id))
        query = _apply_role_filter(query, user)
        mail = query.first()
        if not mail:
            raise HTTPException(status_code=404, detail="Mail introuvable")

        if payload.done:
            mail.reminder_done = True
            mail.reminder_answered_at = datetime.now()
            mail.reminder_recheck_at = None
        else:
            mail.reminder_done = False
            mail.reminder_answered_at = datetime.now()
            mail.reminder_recheck_at = datetime.now() + timedelta(minutes=RECHECK_MINUTES)

    return {"ok": True, "recheck_in_minutes": None if payload.done else RECHECK_MINUTES}


class TrackingIds(BaseModel):
    ids: list[uuid_lib.UUID]

@app.post("/api/alerts/states")
def get_states(payload: TrackingIds, user=Depends(get_current_user)):
    if not payload.ids:
        return {}
    with get_db() as db:
        uuids = [uuid_lib.UUID(i) for i in payload.ids]
        query = db.query(EmailLog).filter(EmailLog.tracking_id.in_(uuids))
        query = _apply_role_filter(query, user)
        rows = query.all()
        result = {            
          str(r.tracking_id): {"alert_acked": r.alert_acked, "reminder_done": r.reminder_done}            
          for r in rows        
        }
    return result

@app.get("/api/alerts/{tracking_id}/status")
def get_alert_status(tracking_id: str, user=Depends(get_current_user)):
    with get_db() as db:
        query = db.query(EmailLog).filter(EmailLog.tracking_id == uuid_lib.UUID(tracking_id))
        query = _apply_role_filter(query, user)
        mail = query.first()

        if not mail:
            raise HTTPException(status_code=404, detail="Mail introuvable")

        result = {
            "reminder_done": mail.reminder_done,
            "reminder_answered_at": str(mail.reminder_answered_at) if mail.reminder_answered_at else None,
            "opened_at": str(mail.opened_at) if mail.opened_at else None,
        }
    return result

@app.post("/api/alerts/{tracking_id}/finally-done")
def finally_done(tracking_id: str, user=Depends(get_current_user)):

    with get_db() as db:
        query = db.query(EmailLog).filter(EmailLog.tracking_id == uuid_lib.UUID(tracking_id))
        query = _apply_role_filter(query, user)
        mail = query.first()
        if not mail:
            raise HTTPException(status_code=404, detail="Mail introuvable")

        mail.reminder_done = True
        mail.reminder_answered_at = datetime.now()
        mail.reminder_recheck_at = None

    return {"ok": True}

@app.get("/api/history")
def get_history(user=Depends(get_current_user), limit: int = 50, offset: int = 0):
    with get_db() as db:
        query = db.query(EmailLog)
        query = _apply_role_filter(query, user)
        rows = query.all()

        def sort_key(r):
            if r.reminder_done is False:
                priority = 1
            elif r.reminder_done is None and not r.alert_acked:
                priority = 2
            elif r.reminder_done is None and r.alert_acked:
                priority = 3
            elif r.opened_at is not None and r.reminder_done is None:
                priority = 4
            elif r.reminder_done is True:
                priority = 5
            else:
                priority = 6
            return (priority, -(r.sent_at.timestamp() if r.sent_at else 0))

        rows = sorted(rows, key=sort_key)
        total = len(rows)
        rows = rows[offset:offset + limit]

        result = [
            {
                "tracking_id": str(r.tracking_id), "sender": r.sender_email,
                "recipient": r.recipient_email, "cc": r.cc_email or "",
                "subject": r.subject or "", "summary": r.ai_summary or "",
                "sent_at": str(r.sent_at) if r.sent_at else "",
                "opened_at": str(r.opened_at) if r.opened_at else None,
                "alert_acked": r.alert_acked, "reminder_done": r.reminder_done,
                "reminder_answered_at": str(r.reminder_answered_at) if r.reminder_answered_at else None,
            }
            for r in rows
        ]
    return {"total": total, "limit": limit, "offset": offset, "items": result}


class AdminLogin(BaseModel):
    username: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class UserCreate(BaseModel):
    username: str
    password: str
    email: str | None = None
    department: str | None = None
    account_role: str = "employee"

@app.post("/api/admin/login")
def admin_login(payload: AdminLogin):
    with get_db() as db:
        admin = db.query(Admin).filter(Admin.username == payload.username).first()
        if not admin or not verify_password(payload.password, admin.password_hash):
            raise HTTPException(status_code=401, detail="Identifiants invalides")
        admin_id = admin.id

    token = create_access_token(subject=payload.username, role="admin", extra={"admin_id": admin_id})
    return {"access_token": token, "token_type": "bearer"}

@app.post("/api/admin/users")
def create_user(payload: UserCreate, admin=Depends(get_current_admin)):
    with get_db() as db:
        existing = db.query(AppUser).filter(AppUser.username == payload.username).first()
        if existing:
            raise HTTPException(status_code=409, detail="Ce nom d'utilisateur existe déjà")

        user = AppUser(
            username=payload.username,
            email=payload.email,
            password_hash=hash_password(payload.password),
            department=payload.department,
            account_role=payload.account_role,
            created_by_admin_id=admin["admin_id"],
        )
        db.add(user)
        db.flush()  # pour récupérer user.id avant le commit final
        user_id = user.id

    return {"id": user_id, "username": payload.username}

@app.get("/api/admin/users")
def list_users(admin=Depends(get_current_admin), limit: int = 50, offset: int = 0):
    with get_db() as db:
        total = db.query(AppUser).count()
        users = ( 
          db.query(AppUser)
          .order_by(AppUser.created_at.desc())
          .offset(offset)
          .limit(limit)
          .all()
        )
        
        result = [
            {
                "id": u.id, "username": u.username, "email": u.email, "is_active": u.is_active,
                "created_at": str(u.created_at), "department": u.department, "account_role": u.account_role,
            }
            for u in users
        ]
    return {"total": total, "limit": limit, "offset": offset, "items": result}


@app.delete("/api/admin/users/{user_id}")
def deactivate_user(user_id: int, admin=Depends(get_current_admin)):
    with get_db() as db:
        user = db.query(AppUser).filter(AppUser.id == user_id).first()
        if user:
            user.is_active = False
    return {"ok": True}

@app.post("/api/admin/users/{user_id}/activate")
def activate_user(user_id: int, admin=Depends(get_current_admin)):
    with get_db() as db:
        user = db.query(AppUser).filter(AppUser.id == user_id).first()
        if user:
            user.is_active = True
    return {"ok": True}

class UserRoleUpdate(BaseModel):
    department: str | None = None
    account_role: str | None = None

@app.patch("/api/admin/users/{user_id}/role")
def update_user_role(user_id: int, payload: UserRoleUpdate, admin=Depends(get_current_admin)):
    if payload.account_role and payload.account_role not in ("employee", "dept_admin", "superadmin"):
        raise HTTPException(status_code=400, detail="Rôle invalide")

    with get_db() as db:
        user = db.query(AppUser).filter(AppUser.id == user_id).first()
        if user:
            if payload.department is not None:
                user.department = payload.department
            if payload.account_role is not None:
                user.account_role = payload.account_role
    return {"ok": True}

@app.get("/api/admin/stats")
def get_admin_stats(admin=Depends(get_current_admin)):
    with get_db() as db:
        total_users = db.query(AppUser).count()
        active_users = db.query(AppUser).filter(AppUser.is_active.is_(True)).count()
        inactive_users = db.query(AppUser).filter(AppUser.is_active.is_(False)).count()

        total_emails = db.query(EmailLog).count()
        opened_emails = db.query(EmailLog).filter(EmailLog.opened_at.isnot(None)).count()
        reminder_done = db.query(EmailLog).filter(EmailLog.reminder_done.is_(True)).count()
        reminder_not_done = db.query(EmailLog).filter(EmailLog.reminder_done.is_(False)).count()

    return {
        "users": {"total": total_users, "active": active_users, "inactive": inactive_users},
        "emails": {
            "total": total_emails, "opened": opened_emails,
            "reminder_done": reminder_done, "reminder_not_done": reminder_not_done,
        },
    }

@app.post("/api/auth/login")
def user_login(payload: UserLogin):
    with get_db() as db:
        user = db.query(AppUser).filter(AppUser.username == payload.username).first()
        if not user or not verify_password(payload.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Identifiants invalides")
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Compte désactivé")
        user_id = user.id

    token = create_access_token(subject=payload.username, role="user", extra={"user_id": user_id})
    return {"access_token": token, "token_type": "bearer"}

@app.post("/api/auth/logout")
def logout(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token manquant")
    token = authorization.removeprefix("Bearer ")
    revoke_token(token)
    return {"ok": True}

@app.get("/api/mail/{tracking_id}")
def get_mail_json(tracking_id: str, user=Depends(get_current_user)):
    with get_db() as db:
        query = db.query(EmailLog).filter(EmailLog.tracking_id == uuid_lib.UUID(tracking_id))
        query = _apply_role_filter(query, user)
        mail = query.first()
        if not mail:
            raise HTTPException(status_code=404, detail="Mail introuvable")

        history_query = db.query(EmailLog)
        history_query = _apply_role_filter(history_query, user)
        history_rows = history_query.all()

        def sort_key(r):
            if r.reminder_done is False:
                priority = 1
            elif r.reminder_done is None and not r.alert_acked:
                priority = 2
            elif r.reminder_done is None and r.alert_acked:
                priority = 3
            elif r.opened_at is not None and r.reminder_done is None:
                priority = 4
            elif r.reminder_done is True:
                priority = 5
            else:
                priority = 6
            return (priority, -(r.sent_at.timestamp() if r.sent_at else 0))

        history_rows = sorted(history_rows, key=sort_key)

        mail_data = {
            "tracking_id": str(mail.tracking_id), "sender": mail.sender_email,
            "recipient": mail.recipient_email, "cc": mail.cc_email or "",
            "subject": mail.subject or "", "body": mail.body or "",
            "summary": mail.ai_summary or "",
            "sent_at": str(mail.sent_at) if mail.sent_at else "",
            "opened_at": str(mail.opened_at) if mail.opened_at else None,
            "alert_acked": mail.alert_acked, "reminder_done": mail.reminder_done,
            "reminder_answered_at": str(mail.reminder_answered_at) if mail.reminder_answered_at else None,
        }
        history_data = [
            {
                "tracking_id": str(h.tracking_id), "sender": h.sender_email,
                "recipient": h.recipient_email, "cc": h.cc_email or "",
                "subject": h.subject or "", "summary": h.ai_summary or "",
                "sent_at": str(h.sent_at) if h.sent_at else "",
                "opened_at": str(h.opened_at) if h.opened_at else None,
                "alert_acked": h.alert_acked, "reminder_done": h.reminder_done,
            }
            for h in history_rows
        ]

    return {"mail": mail_data, "history": history_data}



def _reminder_html(tracking_id: str, reminder_done, reminder_at, fmt_date) -> str:
    """Génère le bloc HTML du rappel selon l'état actuel."""
    tid = tracking_id
    if reminder_done is True:
        return (
            f'<div class="reminder-done reminder-yes">'
            f'<span class="reminder-icon">✓</span>'
            f'<span>Rappel effectué — répondu le {fmt_date(reminder_at)}</span>'
            f'</div>'
        )
    if reminder_done is False:
        return (
            f'<div class="reminder-not-done">'
            f'<div class="reminder-not-done-row">'
            f'<div class="reminder-done reminder-no">'
            f'<span class="reminder-icon">✗</span>'
            f'<span>Rappel non effectué — répondu le {fmt_date(reminder_at)}</span>'
            f'</div>'
            f'<button class="btn-finally-done" onclick="finallyDone(\'{tid}\')">'
            f'<span>✓</span> J\'ai finalement fait le rappel'
            f'</button>'
            f'</div>'
            f'<div class="recheck-notice">↻ Une nouvelle alerte sera envoyée automatiquement.</div>'
            f'</div>'
        )
    return (
        f'<div class="reminder-question">'
        f'<span class="reminder-label">Rappel effectué ?</span>'
        f'<div class="reminder-buttons">'
        f'<button class="btn-reminder btn-oui" onclick="submitReminder(\'{tid}\', true)">'
        f'<span class="btn-check">✓</span> Oui'
        f'</button>'
        f'<button class="btn-reminder btn-non" onclick="submitReminder(\'{tid}\', false)">'
        f'<span class="btn-cross">✗</span> Non'
        f'</button>'
        f'</div>'
        f'</div>'
    )


@app.get("/mail/{tracking_id}", response_class=HTMLResponse)
def mail_detail_page(tracking_id: str):
    """Coquille HTML statique — ne contient AUCUNE donnée de mail.
    Les données réelles sont chargées côté client via /api/mail/{tracking_id}
    après authentification (le token est stocké dans localStorage)."""
    return HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Mail Detector</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg:       #0e0e14;
    --surface:  #17171f;
    --card:     #1e1e28;
    --border:   #2a2a38;
    --gold:     #d4af5a;
    --gold-dim: #a07c30;
    --text:     #e8e8f0;
    --meta:     #8888a0;
    --green:    #48b280;
    --red:      #d46060;
    --blue:     #5a9cf0;
    --amber:    #e8a040;
  }}
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html {{ scroll-behavior: smooth; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: 'Inter', sans-serif;
    font-size: 14px;
    line-height: 1.6;
    min-height: 100vh;
  }}
  .header {{
    border-bottom: 1px solid var(--border);
    padding: 18px 40px;
    display: flex;
    align-items: center;
    gap: 12px;
    position: sticky;
    top: 0;
    background: rgba(14,14,20,.92);
    backdrop-filter: blur(12px);
    z-index: 100;
  }}
  .header-logo {{
    width: 32px; height: 32px;
    background: linear-gradient(135deg, var(--gold), var(--gold-dim));
    border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    font-size: 16px;
  }}
  .header-title {{ font-size: 15px; font-weight: 600; color: var(--text); }}
  .header-sub {{ font-size: 12px; color: var(--meta); margin-left: auto; }}
  .container {{ max-width: 1100px; margin: 0 auto; padding: 40px; }}

  /* ---- login ---- */
  #login-view {{ max-width: 380px; margin: 8vh auto 0; }}
  .login-card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 40px 36px;
    box-shadow: 0 24px 60px rgba(0,0,0,.45);
  }}
  .login-badge {{
    width: 52px; height: 52px;
    border-radius: 14px;
    background: linear-gradient(135deg, var(--gold), var(--gold-dim));
    display: flex; align-items: center; justify-content: center;
    font-size: 24px;
    margin: 0 auto 20px;
  }}
  .login-title {{ text-align: center; font-size: 19px; font-weight: 700; margin-bottom: 6px; }}
  .login-subtitle {{ text-align: center; font-size: 12.5px; color: var(--meta); margin-bottom: 28px; }}
  .field {{ margin-bottom: 18px; }}
  .field label {{
    display: block; font-size: 11.5px; font-weight: 600;
    letter-spacing: .03em; color: var(--meta); margin-bottom: 7px;
  }}
  .field input {{
    width: 100%;
    background: var(--surface);
    border: 1.5px solid var(--border);
    border-radius: 10px;
    padding: 11px 14px;
    color: var(--text);
    font-size: 14px;
    font-family: inherit;
  }}
  .field input:focus {{ outline: none; border-color: var(--gold-dim); }}
  .btn {{
    font-family: inherit; cursor: pointer; border: none;
    border-radius: 30px; font-weight: 600; font-size: 13.5px;
  }}
  .btn-primary {{
    background: linear-gradient(135deg, var(--gold), var(--gold-dim));
    color: #17171a; padding: 12px 20px; width: 100%; margin-top: 6px;
  }}
  .error-msg {{ color: var(--red); font-size: 12.5px; margin-top: 14px; text-align: center; display: none; }}

  /* ---- section label ---- */
  .section-label {{
    font-size: 10px; font-weight: 700; letter-spacing: .14em;
    text-transform: uppercase; color: var(--gold);
    margin-bottom: 16px;
    display: flex; align-items: center; gap: 8px;
  }}
  .section-label::after {{ content: ''; flex: 1; height: 1px; background: var(--border); }}

  /* ---- mail card ---- */
  .mail-card {{
    background: var(--card); border: 1px solid var(--border);
    border-radius: 16px; overflow: hidden; margin-bottom: 48px;
  }}
  .mail-card-header {{
    padding: 28px 32px 24px; border-bottom: 1px solid var(--border);
    display: flex; gap: 24px; align-items: flex-start;
  }}
  .mail-accent-bar {{
    width: 4px; border-radius: 4px;
    background: linear-gradient(to bottom, var(--gold), var(--gold-dim));
    align-self: stretch; flex-shrink: 0;
  }}
  .mail-meta {{ flex: 1; }}
  .mail-subject {{ font-size: 20px; font-weight: 600; color: var(--text); line-height: 1.3; margin-bottom: 16px; }}
  .mail-field {{ display: flex; gap: 8px; font-size: 13px; margin-bottom: 6px; }}
  .mail-field-key {{ color: var(--meta); width: 80px; flex-shrink: 0; }}
  .mail-field-val {{ color: var(--text); }}
  .mail-body-section {{ padding: 24px 32px 28px; }}
  .mail-body-label {{
    font-size: 10px; font-weight: 600; letter-spacing: .12em;
    text-transform: uppercase; color: var(--meta); margin-bottom: 14px;
  }}
  .mail-body-text {{
    font-family: 'Inter', sans-serif; font-size: 14px; color: var(--text);
    line-height: 1.8; padding: 20px; background: var(--surface);
    border-radius: 10px; border: 1px solid var(--border); white-space: pre-wrap;
  }}
  .mail-summary-section {{ padding: 0 32px 28px; display: flex; gap: 12px; align-items: flex-start; }}
  .summary-icon {{
    width: 28px; height: 28px; background: rgba(212,175,90,.12);
    border-radius: 8px; display: flex; align-items: center; justify-content: center;
    color: var(--gold); font-size: 13px; flex-shrink: 0; margin-top: 2px;
  }}
  .summary-text {{ font-size: 13px; color: var(--meta); font-style: italic; line-height: 1.6; }}
  .mail-status-row {{
    padding: 16px 32px; background: var(--surface); border-top: 1px solid var(--border);
    display: flex; gap: 16px; align-items: center; flex-wrap: wrap;
  }}
  .badge {{
    display: inline-flex; align-items: center; gap: 5px;
    padding: 4px 10px; border-radius: 20px; font-size: 11px; font-weight: 600; letter-spacing: .03em;
  }}
  .badge::before {{ content: '●'; font-size: 8px; }}
  .badge-opened  {{ background: rgba(90,156,240,.15); color: var(--blue); }}
  .badge-yes     {{ background: rgba(72,178,128,.15); color: var(--green); }}
  .badge-no      {{ background: rgba(212,96,96,.15);  color: var(--red); }}
  .badge-acked   {{ background: rgba(136,136,160,.12); color: var(--meta); }}
  .badge-pending {{ background: rgba(232,160,64,.15); color: var(--amber); }}

  .history-table-wrap {{ background: var(--card); border: 1px solid var(--border); border-radius: 16px; overflow: hidden; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  thead {{ background: var(--surface); border-bottom: 1px solid var(--border); }}
  thead th {{
    padding: 12px 20px; text-align: left; font-size: 10px; font-weight: 700;
    letter-spacing: .12em; text-transform: uppercase; color: var(--meta);
  }}
  tbody tr {{ border-bottom: 1px solid var(--border); cursor: pointer; transition: background .15s; }}
  tbody tr:last-child {{ border-bottom: none; }}
  tbody tr:hover {{ background: rgba(255,255,255,.03); }}
  tbody tr.row-current {{ background: rgba(212,175,90,.07); }}
  tbody tr.row-current td.td-subject {{ color: var(--gold); font-weight: 600; }}
  td {{ padding: 14px 20px; color: var(--text); vertical-align: middle; }}
  td.td-subject {{ max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}

  .reminder-not-done {{ display: flex; flex-direction: column; gap: 10px; }}
  .reminder-not-done-row {{ display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }}
  .btn-finally-done {{
    display: inline-flex; align-items: center; gap: 8px; padding: 9px 20px;
    background: rgba(212,175,90,.12); color: var(--gold);
    border: 1px solid rgba(212,175,90,.3); border-radius: 30px;
    font-family: 'Inter', sans-serif; font-size: 13px; font-weight: 600; cursor: pointer;
  }}
  .recheck-notice {{ font-size: 12px; color: var(--amber); display: flex; align-items: center; gap: 6px; }}
  .mail-reminder-section {{
    padding: 20px 32px 24px; display: flex; align-items: center; gap: 20px;
    border-top: 1px solid var(--border); flex-wrap: wrap;
  }}
  .reminder-label {{ font-size: 13px; color: var(--meta); flex-shrink: 0; }}
  .reminder-buttons {{ display: flex; gap: 10px; }}
  .btn-reminder {{
    display: inline-flex; align-items: center; gap: 7px; padding: 8px 20px;
    border: none; border-radius: 30px; font-family: 'Inter', sans-serif;
    font-size: 13px; font-weight: 600; cursor: pointer;
  }}
  .btn-oui {{ background: rgba(72,178,128,.18); color: var(--green); border: 1px solid rgba(72,178,128,.35); }}
  .btn-non {{ background: rgba(212,96,96,.15); color: var(--red); border: 1px solid rgba(212,96,96,.3); }}
  .btn-check {{ font-size: 14px; color: var(--green); }}
  .btn-cross {{ font-size: 14px; color: var(--red); }}
  .reminder-done {{
    display: flex; align-items: center; gap: 10px; font-size: 13px; font-weight: 600;
    padding: 8px 16px; border-radius: 30px;
  }}
  .reminder-yes {{ background: rgba(72,178,128,.12); color: var(--green); border: 1px solid rgba(72,178,128,.25); }}
  .reminder-no {{ background: rgba(212,96,96,.12); color: var(--red); border: 1px solid rgba(212,96,96,.25); }}
  .reminder-icon {{ font-size: 15px; }}
  .reminder-question {{ display: flex; align-items: center; gap: 16px; }}
</style>
</head>
<body>
<header class="header">
  <div class="header-logo">✉</div>
  <span class="header-title">Mail Detector</span>
  <span class="header-sub">ARS Tunisie</span>
</header>

<main class="container">
  <div id="loading-view" style="text-align:center; padding:60px 0; color:var(--meta);">
     Chargement…
  </div>
  <div id="login-view" style="display:none;">
    <div class="login-card">
      <div class="login-badge">✉</div>
      <div class="login-title">Connexion requise</div>
      <div class="login-subtitle">Connectez-vous pour voir ce mail</div>
      <div class="field">
        <label>Nom d'utilisateur</label>
        <input id="login-username" type="text" autocomplete="username">
      </div>
      <div class="field">
        <label>Mot de passe</label>
        <input id="login-password" type="password" autocomplete="current-password">
      </div>
      <button class="btn btn-primary" onclick="doLogin()">Se connecter</button>
      <div class="error-msg" id="login-error">Identifiants invalides.</div>
    </div>
  </div>

  <div id="content-view" style="display:none;">
    <div class="section-label">Contenu du mail</div>
    <div class="mail-card">
      <div class="mail-card-header">
        <div class="mail-accent-bar"></div>
        <div class="mail-meta" id="mail-meta"></div>
      </div>
      <div class="mail-body-section">
        <div class="mail-body-label">Contenu</div>
        <div class="mail-body-text" id="mail-body-text"></div>
      </div>
      <div id="mail-summary-section"></div>
      <div class="mail-status-row" id="mail-status-row"></div>
      <div class="mail-reminder-section" id="reminder-section"></div>
    </div>

    <div class="section-label" id="history-label">Historique des mails</div>
    <div class="history-table-wrap">
      <table>
        <thead>
          <tr><th>Sujet</th><th>Expéditeur</th><th>Destinataire</th><th>Envoyé</th><th>Statut</th></tr>
        </thead>
        <tbody id="history-tbody"></tbody>
      </table>
    </div>
  </div>

</main>

<script>
const tid = '{tracking_id}';
let token = localStorage.getItem('user_token') || null;
let mailLoadedOnce = false;
let pollInterval = null;

function escapeHtml(s) {{
  const div = document.createElement('div');
  div.textContent = s || '';
  return div.innerHTML;
}}

function fmtDate(d) {{
  if (!d) return '—';
  return String(d).slice(0, 16).replace('T', ' ');
}}

function statusBadge(opened, acked, reminder) {{
  if (opened) return '<span class="badge badge-opened">Ouvert</span>';
  if (reminder === true) return '<span class="badge badge-yes">Rappel fait</span>';
  if (reminder === false) return '<span class="badge badge-no">Rappel non fait</span>';
  if (acked) return '<span class="badge badge-acked">Vu — sans réponse</span>';
  return '<span class="badge badge-pending">En attente</span>';
}}

async function authFetch(url, options = {{}}) {{
  options.headers = Object.assign({{}}, options.headers, {{ 'Authorization': 'Bearer ' + token }});
  const resp = await fetch(url, options);
  if (resp.status === 401 || resp.status === 403) {{
    token = null;
    localStorage.removeItem('user_token');
    showLogin();
    throw new Error('Session expirée');
  }}
  return resp;
}}

function showLogin() {{
  document.getElementById('loading-view').style.display = 'none';
  document.getElementById('login-view').style.display =   'block';
  document.getElementById('content-view').style.display = 'none';
}}

async function doLogin() {{
  const username = document.getElementById('login-username').value.trim();
  const password = document.getElementById('login-password').value;
  const errEl = document.getElementById('login-error');
  errEl.style.display = 'none';
  try {{
    const resp = await fetch('/api/auth/login', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ username, password }})
    }});
    if (!resp.ok) {{
      errEl.style.display = 'block';
      return;
    }}
    const data = await resp.json();
    token = data.access_token;
    localStorage.setItem('user_token', token);
    loadMail();
  }} catch (e) {{
    errEl.textContent = 'Serveur injoignable.';
    errEl.style.display = 'block';
  }}
}}

function renderReminderSection(reminder_done, reminder_answered_at) {{
  const dt = fmtDate(reminder_answered_at);
  if (reminder_done === true) {{
    return `<div class="reminder-done reminder-yes">
              <span class="reminder-icon">✓</span>
              <span>Rappel effectué — répondu le ${{dt}}</span>
            </div>`;
  }}
  if (reminder_done === false) {{
    return `<div class="reminder-not-done">
              <div class="reminder-not-done-row">
                <div class="reminder-done reminder-no">
                  <span class="reminder-icon">✗</span>
                  <span>Rappel non effectué — répondu le ${{dt}}</span>
                </div>
                <button class="btn-finally-done" onclick="finallyDone('${{tid}}')">
                  <span>✓</span> J'ai finalement fait le rappel
                </button>
              </div>
              <div class="recheck-notice">↻ Une nouvelle alerte sera envoyée automatiquement.</div>
            </div>`;
  }}
  return `<div class="reminder-question">
            <span class="reminder-label">Rappel effectué ?</span>
            <div class="reminder-buttons">
              <button class="btn-reminder btn-oui" onclick="submitReminder('${{tid}}', true)">
                <span class="btn-check">✓</span> Oui
              </button>
              <button class="btn-reminder btn-non" onclick="submitReminder('${{tid}}', false)">
                <span class="btn-cross">✗</span> Non
              </button>
            </div>
          </div>`;
}}

function renderMail(mail, history) {{
  document.title = 'Mail Detector — ' + (mail.subject || '');

  let metaHtml = `<div class="mail-subject">${{escapeHtml(mail.subject || '—')}}</div>
    <div class="mail-field"><span class="mail-field-key">De</span><span class="mail-field-val">${{escapeHtml(mail.sender)}}</span></div>
    <div class="mail-field"><span class="mail-field-key">À</span><span class="mail-field-val">${{escapeHtml(mail.recipient)}}</span></div>`;
  if (mail.cc) {{
    metaHtml += `<div class="mail-field"><span class="mail-field-key">Cc</span><span class="mail-field-val">${{escapeHtml(mail.cc)}}</span></div>`;
  }}
  metaHtml += `<div class="mail-field"><span class="mail-field-key">Envoyé</span><span class="mail-field-val">${{fmtDate(mail.sent_at)}}</span></div>`;
  if (mail.opened_at) {{
    metaHtml += `<div class="mail-field"><span class="mail-field-key">Ouvert</span><span class="mail-field-val">${{fmtDate(mail.opened_at)}}</span></div>`;
  }}
  document.getElementById('mail-meta').innerHTML = metaHtml;
  document.getElementById('mail-body-text').textContent = mail.body || '';

  const summarySection = document.getElementById('mail-summary-section');
  summarySection.innerHTML = mail.summary
    ? `<div class="mail-summary-section"><div class="summary-icon">✦</div><div class="summary-text">${{escapeHtml(mail.summary)}}</div></div>`
    : '';

  document.getElementById('mail-status-row').innerHTML = `
    ${{statusBadge(mail.opened_at, mail.alert_acked, mail.reminder_done)}}
    <span style="font-size:12px;color:var(--meta);">
      ${{mail.reminder_answered_at ? 'Rappel répondu le ' + fmtDate(mail.reminder_answered_at) : "Aucune réponse au rappel pour l'instant"}}
    </span>`;

  document.getElementById('reminder-section').innerHTML =
    renderReminderSection(mail.reminder_done, mail.reminder_answered_at);

  document.getElementById('history-label').textContent = `Historique des mails (${{history.length}} entrées)`;
  document.getElementById('history-tbody').innerHTML = history.map(h => {{
    const isCurrent = h.tracking_id === tid ? 'row-current' : '';
    return `<tr class="${{isCurrent}}" onclick="window.location='/mail/${{h.tracking_id}}'">
        <td class="td-subject">${{escapeHtml(h.subject)}}</td>
        <td>${{escapeHtml(h.sender)}}</td>
        <td>${{escapeHtml(h.recipient)}}</td>
        <td>${{fmtDate(h.sent_at)}}</td>
        <td>${{statusBadge(h.opened_at, h.alert_acked, h.reminder_done)}}</td>
    </tr>`;
  }}).join('');
}}
function reconnectClick() {{
  localStorage.removeItem('user_token');
  location.reload();
}}
async function loadMail() {{
  try {{
    const resp = await authFetch(`/api/mail/${{tid}}`);
    document.getElementById('loading-view').style.display = 'none';
    if (!resp.ok) {{
      if (mailLoadedOnce) {{
        // Le mail était accessible avant, et ne l'est plus : ça veut dire
        // que les droits de l'utilisateur ont changé entre-temps
        // (département modifié, compte désactivé, etc.). On arrête le
        // polling pour ne pas boucler sur une erreur, et on prévient
        // clairement au lieu d'afficher un message brut.
        if (pollInterval) clearInterval(pollInterval);
        document.getElementById('content-view').innerHTML =
          '<h1>Accès à ce mail révoqué</h1>' +
          '<p style="color:var(--meta);margin-top:12px;">' +
          'Vos droits ont changé (département ou compte modifié). ' +
          'Reconnectez-vous pour voir vos mails actuels.</p>' +
          '<button class="btn btn-primary" style="margin-top:20px;max-width:220px;" onclick="reconnectClick()">Se reconnecter</button>';
        document.getElementById('content-view').style.display = 'block';
        document.getElementById('login-view').style.display = 'none';
      }} else {{
        // Premier chargement et déjà en échec : cas normal (mauvais lien, etc.)
        document.getElementById('content-view').innerHTML = '<h1>Mail introuvable ou accès refusé</h1>';
        document.getElementById('content-view').style.display = 'block';
        document.getElementById('login-view').style.display = 'none';
      }}
      return;
    }}
    mailLoadedOnce = true;
    const data = await resp.json();
    renderMail(data.mail, data.history);
    document.getElementById('login-view').style.display = 'none';
    document.getElementById('content-view').style.display = 'block';
  }} catch (e) {{  }}
}}

async function submitReminder(trackingId, done) {{
  const section = document.getElementById('reminder-section');
  section.style.opacity = '0.5';
  section.style.pointerEvents = 'none';
  try {{
    await authFetch(`/api/alerts/${{trackingId}}/reminder`, {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ done }})
    }});
    await loadMail();
  }} finally {{
    section.style.opacity = '1';
    section.style.pointerEvents = 'auto';
  }}
}}

async function finallyDone(trackingId) {{
  const section = document.getElementById('reminder-section');
  section.style.opacity = '0.5';
  section.style.pointerEvents = 'none';
  try {{
    await authFetch(`/api/alerts/${{trackingId}}/finally-done`, {{ method: 'POST' }});
    await loadMail();
  }} finally {{
    section.style.opacity = '1';
    section.style.pointerEvents = 'auto';
  }}
}}

if (token) {{
  loadMail();
}} else {{
  document.getElementById('loading-view').style.display = 'none';
  document.getElementById('login-view').style.display = 'block';
}}

pollInterval = setInterval(() => {{ if (token) loadMail(); }}, 3000);
</script>
</body>
</html>""")