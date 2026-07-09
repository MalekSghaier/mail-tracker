"""
Backend du POC Mail Detector — appelé par le MILTER (pas par sender.py).
Lancer avec : uvicorn app:app --reload --port 8000 --host 0.0.0.0

--host 0.0.0.0 est nécessaire pour que le serveur Zimbra (sur une autre
machine que ton PC) puisse joindre ce backend.
"""
import html as html_module
import os
import uuid
from datetime import datetime, timedelta
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from ollama_client import generer_resume
from fastapi import HTTPException, Depends
from auth import hash_password, verify_password, create_access_token, get_current_admin, get_current_user
from fastapi import Depends
from auth import hash_password, verify_password, create_access_token, get_current_admin, get_current_user
from admin_page import router as admin_router
from db import get_conn
from auth import hash_password, verify_password, create_access_token, get_current_admin, get_current_user, build_alerts_filter

load_dotenv()
app = FastAPI(title="Mail Detector POC")
app.include_router(admin_router)

THRESHOLD_MINUTES = int(os.getenv("ALERT_THRESHOLD_MINUTES", 2))
RECHECK_MINUTES = int(os.getenv("REMINDER_RECHECK_MINUTES", 1))


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
def register_email(payload: EmailRegister):
    """Appelé par le milter Zimbra à chaque mail sortant intercepté."""
    tracking_id = str(uuid.uuid4())

    # Résumé IA — synchrone pour ce POC (en prod finale : Celery, voir mail_detector.md)
    ai_summary = generer_resume(payload.body)

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO email_log
           (tracking_id, sender_email, recipient_email, cc_email, subject, body, ai_summary)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (tracking_id, payload.sender_email, payload.recipient_email, payload.cc_email,
         payload.subject, payload.body, ai_summary),
    )
    conn.commit()
    cur.close()
    conn.close()
    return {"tracking_id": tracking_id}


@app.get("/track/{tracking_id}")
def track(tracking_id: str):
    """Le pixel. Chargé par le client mail quand le mail est ouvert."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """UPDATE email_log SET opened_at = NOW()
           WHERE tracking_id = %s AND opened_at IS NULL""",
        (tracking_id,),
    )
    conn.commit()
    cur.close()
    conn.close()
    return FileResponse("pixel.png", media_type="image/png")


@app.get("/api/alerts")
def get_alerts(user=Depends(get_current_user)):
    """Retourne uniquement les mails en attente sans statut de rappel,
    filtrés selon le rôle métier de l'utilisateur connecté :
    superadmin (tout), dept_admin (son département), employee (ses mails)."""
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """UPDATE email_log
           SET alert_acked = FALSE,
               reminder_done = NULL,
               reminder_answered_at = NULL,
               reminder_recheck_at = NULL
           WHERE reminder_done = FALSE
           AND reminder_recheck_at IS NOT NULL
           AND reminder_recheck_at < NOW()"""
    )
    conn.commit()

    filter_sql, filter_params = build_alerts_filter(user)

    cur.execute(
        f"""SELECT tracking_id, sender_email, recipient_email, cc_email, subject, ai_summary,
                  sent_at, reminder_done
           FROM email_log
           WHERE opened_at IS NULL
           AND alert_acked = FALSE
           AND reminder_done IS NULL
           AND sent_at < NOW() - (%s * INTERVAL '1 minute')
           {filter_sql}""",
        (THRESHOLD_MINUTES, *filter_params),
    )
    results = [
        {
            "tracking_id": str(r[0]),
            "sender": r[1],
            "recipient": r[2],
            "cc": r[3] or "",
            "subject": r[4] or "",
            "summary": r[5] or "",
            "sent_at": str(r[6]),
            "reminder_done": r[7],
            "category": "pending",
        }
        for r in cur.fetchall()
    ]

    cur.execute(
        f"""SELECT tracking_id, sender_email, recipient_email, cc_email, subject, ai_summary,
                  sent_at, reminder_done
           FROM email_log
           WHERE alert_acked = TRUE
           AND reminder_done IS NULL
           AND opened_at IS NULL
           {filter_sql}""",
        filter_params,
    )
    for r in cur.fetchall():
        results.append({
            "tracking_id": str(r[0]),
            "sender": r[1],
            "recipient": r[2],
            "cc": r[3] or "",
            "subject": r[4] or "",
            "summary": r[5] or "",
            "sent_at": str(r[6]),
            "reminder_done": r[7],
            "category": "seen_no_answer",
        })

    cur.close()
    conn.close()
    return results



@app.get("/api/auth/verify")
def verify_token(user=Depends(get_current_user)):
    """Endpoint léger utilisé par l'agent au démarrage pour vérifier
    silencieusement si le token sauvegardé est encore valide."""
    return {"ok": True, "sub": user.get("sub"), "role": user.get("role")}



@app.post("/api/alerts/{tracking_id}/ack")
def ack_alert(tracking_id: str, user=Depends(get_current_user)):
    """Appelé par l'agent C#/.NET après affichage du popup."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE email_log SET alert_acked = TRUE WHERE tracking_id = %s", (tracking_id,))
    conn.commit()
    cur.close()
    conn.close()
    return {"ok": True}


class ReminderAnswer(BaseModel):
    done: bool


@app.post("/api/alerts/{tracking_id}/reminder")
def set_reminder(tracking_id: str, payload: ReminderAnswer, user=Depends(get_current_user)):
    conn = get_conn()
    cur = conn.cursor()
    filter_sql, filter_params = build_alerts_filter(user)
    cur.execute(f"SELECT 1 FROM email_log WHERE tracking_id = %s {filter_sql}",
                (tracking_id, *filter_params))
    if not cur.fetchone():
        cur.close(); conn.close()
        raise HTTPException(status_code=404, detail="Mail introuvable")

    if payload.done:
        cur.execute(
            """UPDATE email_log
               SET reminder_done = TRUE, reminder_answered_at = NOW(), reminder_recheck_at = NULL
               WHERE tracking_id = %s""",
            (tracking_id,),
        )
    else:
        cur.execute(
            """UPDATE email_log
               SET reminder_done = FALSE, reminder_answered_at = NOW(),
                   reminder_recheck_at = NOW() + (%s * INTERVAL '1 minute')
               WHERE tracking_id = %s""",
            (RECHECK_MINUTES, tracking_id),
        )
    conn.commit()
    cur.close()
    conn.close()
    return {"ok": True, "recheck_in_minutes": None if payload.done else RECHECK_MINUTES}


class TrackingIds(BaseModel):
    ids: list


@app.post("/api/alerts/states")
def get_states(payload: TrackingIds, user=Depends(get_current_user)):
    """Retourne l'état actuel (alert_acked, reminder_done) pour une liste
    de tracking_ids — y compris ceux déjà ackés. Utilisé par l'agent pour
    synchroniser son état local avec la base en temps quasi-réel."""
    if not payload.ids:
        return {}
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """SELECT tracking_id, alert_acked, reminder_done
           FROM email_log
           WHERE tracking_id = ANY(%s)""",
        (payload.ids,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {
        str(r[0]): {"alert_acked": r[1], "reminder_done": r[2]}
        for r in rows
    }


@app.get("/api/alerts/{tracking_id}/status")
def get_alert_status(tracking_id: str, user=Depends(get_current_user)):
    conn = get_conn()
    cur = conn.cursor()
    filter_sql, filter_params = build_alerts_filter(user)
    cur.execute(
        f"""SELECT reminder_done, reminder_answered_at, opened_at
           FROM email_log WHERE tracking_id = %s {filter_sql}""",
        (tracking_id, *filter_params),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Mail introuvable")
    return {
        "reminder_done": row[0],
        "reminder_answered_at": str(row[1]) if row[1] else None,
        "opened_at": str(row[2]) if row[2] else None,
    }


@app.post("/api/alerts/{tracking_id}/finally-done")
def finally_done(tracking_id: str, user=Depends(get_current_user)):
    """Appelé depuis la page web quand l'employé clique 'J'ai finalement
    fait le rappel'. Passe reminder_done à TRUE et annule le recheck."""
    conn = get_conn()
    cur = conn.cursor()
    filter_sql, filter_params = build_alerts_filter(user)
    cur.execute(f"SELECT 1 FROM email_log WHERE tracking_id = %s {filter_sql}",
                (tracking_id, *filter_params))
    if not cur.fetchone():
        cur.close(); conn.close()
        raise HTTPException(status_code=404, detail="Mail introuvable")

    cur.execute(
        """UPDATE email_log
           SET reminder_done = TRUE,
               reminder_answered_at = NOW(),
               reminder_recheck_at = NULL
           WHERE tracking_id = %s""",
        (tracking_id,),
    )
    conn.commit()
    cur.close()
    conn.close()
    return {"ok": True}


@app.get("/api/history")
def get_history(user=Depends(get_current_user)):
    conn = get_conn()
    cur = conn.cursor()
    filter_sql, filter_params = build_alerts_filter(user)
    cur.execute(
        f"""SELECT tracking_id, sender_email, recipient_email, cc_email,
                  subject, ai_summary, sent_at, opened_at,
                  alert_acked, reminder_done, reminder_answered_at
           FROM email_log
           WHERE 1=1
           {filter_sql}
           ORDER BY
              CASE
                WHEN reminder_done = FALSE                              THEN 1
                WHEN reminder_done IS NULL AND alert_acked = FALSE      THEN 2
                WHEN reminder_done IS NULL AND alert_acked = TRUE       THEN 3
                WHEN opened_at IS NOT NULL AND reminder_done IS NULL    THEN 4
                WHEN reminder_done = TRUE                               THEN 5
                ELSE 6
              END ASC,
              sent_at DESC""",
        filter_params,
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {
            "tracking_id": str(r[0]),
            "sender": r[1],
            "recipient": r[2],
            "cc": r[3] or "",
            "subject": r[4] or "",
            "summary": r[5] or "",
            "sent_at": str(r[6]) if r[6] else "",
            "opened_at": str(r[7]) if r[7] else None,
            "alert_acked": r[8],
            "reminder_done": r[9],
            "reminder_answered_at": str(r[10]) if r[10] else None,
        }
        for r in rows
    ]

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
    account_role: str = "employee"  # 'employee' | 'dept_admin' | 'superadmin'


@app.post("/api/admin/login")
def admin_login(payload: AdminLogin):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, password_hash FROM admins WHERE username = %s", (payload.username,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row or not verify_password(payload.password, row[1]):
        raise HTTPException(status_code=401, detail="Identifiants invalides")
    token = create_access_token(subject=payload.username, role="admin", extra={"admin_id": row[0]})
    return {"access_token": token, "token_type": "bearer"}


@app.post("/api/admin/users")
def create_user(payload: UserCreate, admin=Depends(get_current_admin)):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM app_users WHERE username = %s", (payload.username,))
    if cur.fetchone():
        cur.close()
        conn.close()
        raise HTTPException(status_code=409, detail="Ce nom d'utilisateur existe déjà")
    cur.execute(
        """INSERT INTO app_users (username, email, password_hash, department, account_role, created_by_admin_id)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
        (payload.username, payload.email, hash_password(payload.password),
         payload.department, payload.account_role, admin["admin_id"]),
    )
    user_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return {"id": user_id, "username": payload.username}


@app.get("/api/admin/users")
def list_users(admin=Depends(get_current_admin)):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, username, email, is_active, created_at, department, account_role "
        "FROM app_users ORDER BY created_at DESC"
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {
            "id": r[0], "username": r[1], "email": r[2], "is_active": r[3],
            "created_at": str(r[4]), "department": r[5], "account_role": r[6],
        }
        for r in rows
    ]


@app.delete("/api/admin/users/{user_id}")
def deactivate_user(user_id: int, admin=Depends(get_current_admin)):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE app_users SET is_active = FALSE WHERE id = %s", (user_id,))
    conn.commit()
    cur.close()
    conn.close()
    return {"ok": True}

@app.post("/api/admin/users/{user_id}/activate")
def activate_user(user_id: int, admin=Depends(get_current_admin)):
    """Réactive un utilisateur précédemment désactivé."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE app_users SET is_active = TRUE WHERE id = %s", (user_id,))
    conn.commit()
    cur.close()
    conn.close()
    return {"ok": True}

class UserRoleUpdate(BaseModel):
    department: str | None = None
    account_role: str | None = None  # 'employee' | 'dept_admin' | 'superadmin'

@app.patch("/api/admin/users/{user_id}/role")
def update_user_role(user_id: int, payload: UserRoleUpdate, admin=Depends(get_current_admin)):
    if payload.account_role and payload.account_role not in ("employee", "dept_admin", "superadmin"):
        raise HTTPException(status_code=400, detail="Rôle invalide")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """UPDATE app_users
           SET department = COALESCE(%s, department),
               account_role = COALESCE(%s, account_role)
           WHERE id = %s""",
        (payload.department, payload.account_role, user_id),
    )
    conn.commit()
    cur.close()
    conn.close()
    return {"ok": True}


@app.get("/api/admin/stats")
def get_admin_stats(admin=Depends(get_current_admin)):
    """Statistiques affichées en haut du tableau de bord admin."""
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        "SELECT COUNT(*), COUNT(*) FILTER (WHERE is_active), "
        "COUNT(*) FILTER (WHERE NOT is_active) FROM app_users"
    )
    total_users, active_users, inactive_users = cur.fetchone()

    cur.execute("SELECT COUNT(*) FROM email_log")
    total_emails = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM email_log WHERE opened_at IS NOT NULL")
    opened_emails = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM email_log WHERE reminder_done = TRUE")
    reminder_done = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM email_log WHERE reminder_done = FALSE")
    reminder_not_done = cur.fetchone()[0]

    cur.close()
    conn.close()
    return {
        "users": {"total": total_users, "active": active_users, "inactive": inactive_users},
        "emails": {
            "total": total_emails,
            "opened": opened_emails,
            "reminder_done": reminder_done,
            "reminder_not_done": reminder_not_done,
        },
    }


@app.post("/api/auth/login")
def user_login(payload: UserLogin):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, password_hash, is_active FROM app_users WHERE username = %s",
        (payload.username,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row or not verify_password(payload.password, row[1]):
        raise HTTPException(status_code=401, detail="Identifiants invalides")
    if not row[2]:
        raise HTTPException(status_code=403, detail="Compte désactivé")
    token = create_access_token(subject=payload.username, role="user", extra={"user_id": row[0]})
    return {"access_token": token, "token_type": "bearer"}

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

@app.get("/api/mail/{tracking_id}")
def get_mail_json(tracking_id: str, user=Depends(get_current_user)):
    conn = get_conn()
    cur = conn.cursor()
    filter_sql, filter_params = build_alerts_filter(user)

    cur.execute(
        f"""SELECT tracking_id, sender_email, recipient_email, cc_email,
                  subject, body, ai_summary, sent_at, opened_at,
                  alert_acked, reminder_done, reminder_answered_at
           FROM email_log
           WHERE tracking_id = %s {filter_sql}""",
        (tracking_id, *filter_params),
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Mail introuvable")

    cur.execute(
        f"""SELECT tracking_id, sender_email, recipient_email, cc_email,
                  subject, ai_summary, sent_at, opened_at,
                  alert_acked, reminder_done
           FROM email_log
           WHERE 1=1 {filter_sql}
           ORDER BY
              CASE
                WHEN reminder_done = FALSE                              THEN 1
                WHEN reminder_done IS NULL AND alert_acked = FALSE      THEN 2
                WHEN reminder_done IS NULL AND alert_acked = TRUE       THEN 3
                WHEN opened_at IS NOT NULL AND reminder_done IS NULL    THEN 4
                WHEN reminder_done = TRUE                               THEN 5
                ELSE 6
              END ASC,
              sent_at DESC""",
        filter_params,
    )
    history = cur.fetchall()
    cur.close()
    conn.close()

    return {
        "mail": {
            "tracking_id": str(row[0]),
            "sender": row[1],
            "recipient": row[2],
            "cc": row[3] or "",
            "subject": row[4] or "",
            "body": row[5] or "",
            "summary": row[6] or "",
            "sent_at": str(row[7]) if row[7] else "",
            "opened_at": str(row[8]) if row[8] else None,
            "alert_acked": row[9],
            "reminder_done": row[10],
            "reminder_answered_at": str(row[11]) if row[11] else None,
        },
        "history": [
            {
                "tracking_id": str(h[0]),
                "sender": h[1],
                "recipient": h[2],
                "cc": h[3] or "",
                "subject": h[4] or "",
                "summary": h[5] or "",
                "sent_at": str(h[6]) if h[6] else "",
                "opened_at": str(h[7]) if h[7] else None,
                "alert_acked": h[8],
                "reminder_done": h[9],
            }
            for h in history
        ],
    }

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

async function loadMail() {{
  try {{
    const resp = await authFetch(`/api/mail/${{tid}}`);
    document.getElementById('loading-view').style.display = 'none';
    if (!resp.ok) {{
      document.getElementById('content-view').innerHTML = '<h1>Mail introuvable ou accès refusé</h1>';
      document.getElementById('content-view').style.display = 'block';
      document.getElementById('login-view').style.display = 'none';
      return;
    }}
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

setInterval(() => {{ if (token) loadMail(); }}, 3000);
</script>
</body>
</html>""")