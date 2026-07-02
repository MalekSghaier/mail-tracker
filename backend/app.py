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

import psycopg2
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from ollama_client import generer_resume

load_dotenv()
app = FastAPI(title="Mail Detector POC")

THRESHOLD_MINUTES = int(os.getenv("ALERT_THRESHOLD_MINUTES", 2))
RECHECK_MINUTES = int(os.getenv("REMINDER_RECHECK_MINUTES", 1))


def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT", 5432),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


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
def get_alerts():
    """Retourne uniquement les mails en attente sans statut de rappel.
    Quand le délai de re-check est écoulé, remet le mail entièrement à
    zéro (reminder_done=NULL, alert_acked=FALSE) pour qu'il réapparaisse
    comme un nouveau popup sans statut."""
    conn = get_conn()
    cur = conn.cursor()

    # Remet à zéro les mails dont le délai de re-check est écoulé.
    # reminder_done repasse à NULL → le prochain poll le traite comme
    # un mail sans réponse, ce qui déclenche un nouveau popup.
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

    # Seuls les mails actifs sans statut apparaissent dans la barre.
    # Catégorie 1 : en attente (déclenche les popups)
    # reminder_done IS NULL garantit que si l'utilisateur a répondu depuis la
    # page web, l'alerte n'apparaît plus ici — même si alert_acked est encore FALSE.
    cur.execute(
        """SELECT tracking_id, sender_email, recipient_email, cc_email, subject, ai_summary,
                  sent_at, reminder_done
           FROM email_log
           WHERE opened_at IS NULL
           AND alert_acked = FALSE
           AND reminder_done IS NULL
           AND sent_at < NOW() - (%s * INTERVAL '1 minute')""",
        (THRESHOLD_MINUTES,),
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

    # Catégorie 2 : vu sans réponse au rappel (silencieux dans le panneau)
    # La catégorie "not_validated" (reminder_done=FALSE, recheck en attente)
    # n'est pas renvoyée : ces mails disparaissent du panneau jusqu'à ce que
    # le recheck les réinitialise en "pending" avec reminder_done=NULL.
    cur.execute(
        """SELECT tracking_id, sender_email, recipient_email, cc_email, subject, ai_summary,
                  sent_at, reminder_done
           FROM email_log
           WHERE alert_acked = TRUE
           AND reminder_done IS NULL
           AND opened_at IS NULL""",
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


@app.post("/api/alerts/{tracking_id}/ack")
def ack_alert(tracking_id: str):
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
def set_reminder(tracking_id: str, payload: ReminderAnswer):
    """Appelé quand l'employé répond Oui/Non à 'Rappel effectué ?'.
    Si Non : planifie une ré-alerte automatique après REMINDER_RECHECK_MINUTES."""
    conn = get_conn()
    cur = conn.cursor()
    if payload.done:
        # Oui : enregistre la réponse, annule tout recheck programmé
        cur.execute(
            """UPDATE email_log
               SET reminder_done = TRUE,
                   reminder_answered_at = NOW(),
                   reminder_recheck_at = NULL
               WHERE tracking_id = %s""",
            (tracking_id,),
        )
    else:
        # Non : enregistre la réponse ET planifie une ré-alerte
        cur.execute(
            """UPDATE email_log
               SET reminder_done = FALSE,
                   reminder_answered_at = NOW(),
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
def get_states(payload: TrackingIds):
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
def get_alert_status(tracking_id: str):
    """Endpoint léger pour le polling JS de la page web.
    Retourne uniquement l'état actuel du rappel et de l'ouverture."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """SELECT reminder_done, reminder_answered_at, opened_at
           FROM email_log WHERE tracking_id = %s""",
        (tracking_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return {"error": "not found"}
    return {
        "reminder_done": row[0],
        "reminder_answered_at": str(row[1]) if row[1] else None,
        "opened_at": str(row[2]) if row[2] else None,
    }


@app.post("/api/alerts/{tracking_id}/finally-done")
def finally_done(tracking_id: str):
    """Appelé depuis la page web quand l'employé clique 'J'ai finalement
    fait le rappel'. Passe reminder_done à TRUE et annule le recheck."""
    conn = get_conn()
    cur = conn.cursor()
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
def get_history():
    """Retourne l'historique complet de tous les mails suivis."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """SELECT tracking_id, sender_email, recipient_email, cc_email,
                  subject, ai_summary, sent_at, opened_at,
                  alert_acked, reminder_done, reminder_answered_at
           FROM email_log
           ORDER BY
              CASE
                WHEN reminder_done = FALSE                              THEN 1
                WHEN reminder_done IS NULL AND alert_acked = FALSE      THEN 2
                WHEN reminder_done IS NULL AND alert_acked = TRUE       THEN 3
                WHEN opened_at IS NOT NULL AND reminder_done IS NULL    THEN 4
                WHEN reminder_done = TRUE                               THEN 5
                ELSE 6
              END ASC,
              sent_at DESC"""
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
    """Page web affichant le contenu d'un mail + l'historique complet."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """SELECT tracking_id, sender_email, recipient_email, cc_email,
                  subject, body, ai_summary, sent_at, opened_at,
                  alert_acked, reminder_done, reminder_answered_at
           FROM email_log WHERE tracking_id = %s""",
        (tracking_id,),
    )
    row = cur.fetchone()
    cur.execute(
        """SELECT tracking_id, sender_email, recipient_email, cc_email,
                  subject, ai_summary, sent_at, opened_at,
                  alert_acked, reminder_done
           FROM email_log 
           ORDER BY
              CASE
                WHEN reminder_done = FALSE                              THEN 1
                WHEN reminder_done IS NULL AND alert_acked = FALSE      THEN 2
                WHEN reminder_done IS NULL AND alert_acked = TRUE       THEN 3
                WHEN opened_at IS NOT NULL AND reminder_done IS NULL    THEN 4
                WHEN reminder_done = TRUE                               THEN 5
                ELSE 6
              END ASC,
              sent_at DESC"""
    )
    history = cur.fetchall()
    cur.close()
    conn.close()

    if not row:
        return HTMLResponse("<h1>Mail introuvable</h1>", status_code=404)

    def fmt_date(d):
        if not d:
            return "—"
        try:
            return str(d)[:16].replace("T", " ")
        except Exception:
            return str(d)[:16]

    def status_badge(opened, acked, reminder):
        if opened:
            return '<span class="badge badge-opened">Ouvert</span>'
        if reminder is True:
            return '<span class="badge badge-yes">Rappel fait</span>'
        if reminder is False:
            return '<span class="badge badge-no">Rappel non fait</span>'
        if acked:
            return '<span class="badge badge-acked">Vu — sans réponse</span>'
        return '<span class="badge badge-pending">En attente</span>'

    body_content = html_module.escape(row[5] or "").replace("&lt;p&gt;", "").replace("&lt;/p&gt;", "")
    body_display = (row[5] or "").replace("<p>", "").replace("</p>", "")

    history_rows = ""
    for h in history:
        tid = str(h[0])
        is_current = "row-current" if tid == str(tracking_id) else ""
        history_rows += f"""
        <tr class="{is_current}" onclick="window.location='/mail/{tid}'">
            <td class="td-subject">{html_module.escape(h[4] or "")}</td>
            <td>{html_module.escape(h[1])}</td>
            <td>{html_module.escape(h[2])}</td>
            <td>{fmt_date(h[6])}</td>
            <td>{status_badge(h[7], h[8], h[9])}</td>
        </tr>"""

    return HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Mail Detector — {html_module.escape(row[4] or '')}</title>
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

  /* ── Header ── */
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

  /* ── Layout ── */
  .container {{ max-width: 1100px; margin: 0 auto; padding: 40px; }}

  /* ── Section label ── */
  .section-label {{
    font-size: 10px; font-weight: 700; letter-spacing: .14em;
    text-transform: uppercase; color: var(--gold);
    margin-bottom: 16px;
    display: flex; align-items: center; gap: 8px;
  }}
  .section-label::after {{
    content: ''; flex: 1;
    height: 1px; background: var(--border);
  }}

  /* ── Mail card ── */
  .mail-card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 16px;
    overflow: hidden;
    margin-bottom: 48px;
    animation: fadeUp .4s ease both;
  }}
  .mail-card-header {{
    padding: 28px 32px 24px;
    border-bottom: 1px solid var(--border);
    display: flex; gap: 24px; align-items: flex-start;
  }}
  .mail-accent-bar {{
    width: 4px; border-radius: 4px;
    background: linear-gradient(to bottom, var(--gold), var(--gold-dim));
    align-self: stretch; flex-shrink: 0;
  }}
  .mail-meta {{ flex: 1; }}
  .mail-subject {{
    font-size: 20px; font-weight: 600;
    color: var(--text); line-height: 1.3;
    margin-bottom: 16px;
  }}
  .mail-field {{
    display: flex; gap: 8px;
    font-size: 13px; margin-bottom: 6px;
  }}
  .mail-field-key {{
    color: var(--meta); width: 80px; flex-shrink: 0;
  }}
  .mail-field-val {{ color: var(--text); }}

  .mail-body-section {{
    padding: 24px 32px 28px;
  }}
  .mail-body-label {{
    font-size: 10px; font-weight: 600; letter-spacing: .12em;
    text-transform: uppercase; color: var(--meta);
    margin-bottom: 14px;
  }}
  .mail-body-text {{
    font-family: 'Inter', sans-serif;
    font-size: 14px; color: var(--text);
    line-height: 1.8;
    padding: 20px;
    background: var(--surface);
    border-radius: 10px;
    border: 1px solid var(--border);
    white-space: pre-wrap;
  }}
  .mail-summary-section {{
    padding: 0 32px 28px;
    display: flex; gap: 12px; align-items: flex-start;
  }}
  .summary-icon {{
    width: 28px; height: 28px;
    background: rgba(212,175,90,.12);
    border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    color: var(--gold); font-size: 13px; flex-shrink: 0;
    margin-top: 2px;
  }}
  .summary-text {{
    font-size: 13px; color: var(--meta);
    font-style: italic; line-height: 1.6;
  }}

  /* ── Status row ── */
  .mail-status-row {{
    padding: 16px 32px;
    background: var(--surface);
    border-top: 1px solid var(--border);
    display: flex; gap: 16px; align-items: center; flex-wrap: wrap;
  }}

  /* ── Badges ── */
  .badge {{
    display: inline-flex; align-items: center; gap: 5px;
    padding: 4px 10px; border-radius: 20px;
    font-size: 11px; font-weight: 600; letter-spacing: .03em;
  }}
  .badge::before {{ content: '●'; font-size: 8px; }}
  .badge-opened  {{ background: rgba(90,156,240,.15); color: var(--blue); }}
  .badge-yes     {{ background: rgba(72,178,128,.15); color: var(--green); }}
  .badge-no      {{ background: rgba(212,96,96,.15);  color: var(--red); }}
  .badge-acked   {{ background: rgba(136,136,160,.12); color: var(--meta); }}
  .badge-pending {{ background: rgba(232,160,64,.15); color: var(--amber); }}

  /* ── Historique ── */
  .history-table-wrap {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 16px;
    overflow: hidden;
    animation: fadeUp .4s .12s ease both;
  }}
  table {{
    width: 100%; border-collapse: collapse;
    font-size: 13px;
  }}
  thead {{
    background: var(--surface);
    border-bottom: 1px solid var(--border);
  }}
  thead th {{
    padding: 12px 20px;
    text-align: left;
    font-size: 10px; font-weight: 700;
    letter-spacing: .12em; text-transform: uppercase;
    color: var(--meta);
  }}
  tbody tr {{
    border-bottom: 1px solid var(--border);
    cursor: pointer;
    transition: background .15s;
  }}
  tbody tr:last-child {{ border-bottom: none; }}
  tbody tr:hover {{ background: rgba(255,255,255,.03); }}
  tbody tr.row-current {{ background: rgba(212,175,90,.07); }}
  tbody tr.row-current td.td-subject {{ color: var(--gold); font-weight: 600; }}
  td {{ padding: 14px 20px; color: var(--text); vertical-align: middle; }}
  td.td-subject {{ max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}

  .reminder-not-done {{
    display: flex; flex-direction: column; gap: 10px;
  }}
  .reminder-not-done-row {{
    display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
  }}
  .btn-finally-done {{
    display: inline-flex; align-items: center; gap: 8px;
    padding: 9px 20px;
    background: rgba(212,175,90,.12);
    color: var(--gold);
    border: 1px solid rgba(212,175,90,.3);
    border-radius: 30px;
    font-family: 'Inter', sans-serif;
    font-size: 13px; font-weight: 600;
    cursor: pointer;
    transition: opacity .15s, transform .1s;
    align-self: flex-start;
  }}
  .btn-finally-done:hover {{ opacity: .8; transform: translateY(-1px); }}
  .recheck-notice {{
    font-size: 12px; color: var(--amber);
    display: flex; align-items: center; gap: 6px;
  }}

  /* ── Section rappel ── */
  .mail-reminder-section {{
    padding: 20px 32px 24px;
    display: flex; align-items: center; gap: 20px;
    border-top: 1px solid var(--border);
    flex-wrap: wrap;
  }}
  .reminder-label {{
    font-size: 13px; color: var(--meta);
    flex-shrink: 0;
  }}
  .reminder-buttons {{ display: flex; gap: 10px; }}
  .btn-reminder {{
    display: inline-flex; align-items: center; gap: 7px;
    padding: 8px 20px;
    border: none; border-radius: 30px;
    font-family: 'Inter', sans-serif;
    font-size: 13px; font-weight: 600;
    cursor: pointer;
    transition: opacity .15s, transform .1s;
  }}
  .btn-reminder:hover {{ opacity: .85; transform: translateY(-1px); }}
  .btn-reminder:active {{ transform: translateY(0); }}
  .btn-oui {{
    background: rgba(72,178,128,.18);
    color: var(--green);
    border: 1px solid rgba(72,178,128,.35);
  }}
  .btn-non {{
    background: rgba(212,96,96,.15);
    color: var(--red);
    border: 1px solid rgba(212,96,96,.3);
  }}
  .btn-check {{ font-size: 14px; color: var(--green); }}
  .btn-cross {{ font-size: 14px; color: var(--red); }}
  .reminder-done {{
    display: flex; align-items: center; gap: 10px;
    font-size: 13px; font-weight: 600;
    padding: 8px 16px; border-radius: 30px;
  }}
  .reminder-yes {{
    background: rgba(72,178,128,.12);
    color: var(--green);
    border: 1px solid rgba(72,178,128,.25);
  }}
  .reminder-no {{
    background: rgba(212,96,96,.12);
    color: var(--red);
    border: 1px solid rgba(212,96,96,.25);
  }}
  .reminder-icon {{ font-size: 15px; }}
  .reminder-question {{ display: flex; align-items: center; gap: 16px; }}

  /* ── Animation ── */
  @keyframes fadeUp {{
    from {{ opacity: 0; transform: translateY(14px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
  }}
</style>
<script>
// Polling temps réel : synchronise l'état du rappel avec le backend toutes les 3s.
// Si l'état a changé (ex. répondu depuis le panneau de l'agent), la section se
// met à jour sans rechargement de page.
(function startPolling() {{
  const tid = '{str(tracking_id)}';
  let lastState = '{str(row[10])}'; // valeur initiale connue au chargement

  setInterval(async () => {{
    try {{
      const resp = await fetch(`/api/alerts/${{tid}}/status`);
      if (!resp.ok) return;
      const data = await resp.json();
      const newState = String(data.reminder_done);

      if (newState !== lastState) {{
        lastState = newState;
        const section = document.getElementById('reminder-section');
        if (!section) return;

        const dt = data.reminder_answered_at
          ? new Date(data.reminder_answered_at).toLocaleString('fr-FR', {{
              day:'2-digit', month:'2-digit', year:'numeric',
              hour:'2-digit', minute:'2-digit'
            }})
          : '—';

        if (data.reminder_done === true) {{
          section.innerHTML = `
            <div class="reminder-done reminder-yes">
              <span class="reminder-icon">✓</span>
              <span>Rappel effectué — répondu le ${{dt}}</span>
            </div>`;
        }} else if (data.reminder_done === false) {{
          section.innerHTML = `
            <div class="reminder-not-done">
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
        }} else {{
          section.innerHTML = `
            <div class="reminder-question">
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
      }}
    }} catch(e) {{ /* réseau indisponible — on réessaie au prochain tick */ }}
  }}, 3000);
}})();
// Polling du tableau d'historique : recharge /api/history toutes les 3s
(function startHistoryPolling() {{
  const currentTid = '{str(tracking_id)}';

  function fmtDate(d) {{
    if (!d) return '—';
    return String(d).slice(0, 16).replace('T', ' ');
  }}

  function escapeHtml(s) {{
    const div = document.createElement('div');
    div.textContent = s || '';
    return div.innerHTML;
  }}

  function statusBadge(opened, acked, reminder) {{
    if (opened) return '<span class="badge badge-opened">Ouvert</span>';
    if (reminder === true) return '<span class="badge badge-yes">Rappel fait</span>';
    if (reminder === false) return '<span class="badge badge-no">Rappel non fait</span>';
    if (acked) return '<span class="badge badge-acked">Vu — sans réponse</span>';
    return '<span class="badge badge-pending">En attente</span>';
  }}

  async function refreshHistory() {{
    try {{
      const resp = await fetch('/api/history');
      if (!resp.ok) return;
      const rows = await resp.json();
      const tbody = document.getElementById('history-tbody');
      if (!tbody) return;
      tbody.innerHTML = rows.map(h => {{
        const isCurrent = h.tracking_id === currentTid ? 'row-current' : '';
        return `<tr class="${{isCurrent}}" onclick="window.location='/mail/${{h.tracking_id}}'">
            <td class="td-subject">${{escapeHtml(h.subject)}}</td>
            <td>${{escapeHtml(h.sender)}}</td>
            <td>${{escapeHtml(h.recipient)}}</td>
            <td>${{fmtDate(h.sent_at)}}</td>
            <td>${{statusBadge(h.opened_at, h.alert_acked, h.reminder_done)}}</td>
        </tr>`;
      }}).join('');
    }} catch(e) {{}}
  }}

  setInterval(refreshHistory, 3000);
}})();

async function submitReminder(trackingId, done) {{
  const section = document.getElementById('reminder-section');
  section.style.opacity = '0.5';
  section.style.pointerEvents = 'none';

  try {{
    const resp = await fetch(`/api/alerts/${{trackingId}}/reminder`, {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ done }})
    }});

    if (resp.ok) {{
      const data = await resp.json();
      const now = new Date().toLocaleString('fr-FR', {{
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit'
      }});
      if (done) {{
        section.innerHTML = `
          <div class="reminder-done reminder-yes">
            <span class="reminder-icon">✓</span>
            <span>Rappel effectué — répondu le ${{now}}</span>
          </div>`;
      }} else {{
        section.innerHTML = `
          <div class="reminder-not-done">
            <div class="reminder-not-done-row">
              <div class="reminder-done reminder-no">
                <span class="reminder-icon">✗</span>
                <span>Rappel non effectué — répondu le ${{now}}</span>
              </div>
              <button class="btn-finally-done" onclick="finallyDone('${{trackingId}}')">
                <span>✓</span> J'ai finalement fait le rappel
              </button>
            </div>
            <div class="recheck-notice">↻ Une nouvelle alerte sera envoyée automatiquement dans ${{data.recheck_in_minutes}} min.</div>
          </div>`;
      }}
      section.style.opacity = '1';
      section.style.pointerEvents = 'auto';
    }}
  }} catch(e) {{
    section.style.opacity = '1';
    section.style.pointerEvents = 'auto';
  }}
}}

async function finallyDone(trackingId) {{
  const section = document.getElementById('reminder-section');
  section.style.opacity = '0.5';
  section.style.pointerEvents = 'none';

  try {{
    const resp = await fetch(`/api/alerts/${{trackingId}}/finally-done`, {{
      method: 'POST'
    }});

    if (resp.ok) {{
      const now = new Date().toLocaleString('fr-FR', {{
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit'
      }});
      section.innerHTML = `
        <div class="reminder-done reminder-yes">
          <span class="reminder-icon">✓</span>
          <span>Rappel effectué — répondu le ${{now}}</span>
        </div>`;
    }}
    section.style.opacity = '1';
    section.style.pointerEvents = 'auto';
  }} catch(e) {{
    section.style.opacity = '1';
    section.style.pointerEvents = 'auto';
  }}
}}
setInterval(refreshHistory, 3000);
</script>
</head>
<body>
<header class="header">
  <div class="header-logo">✉</div>
  <span class="header-title">Mail Detector</span>
  <span class="header-sub">ARS Tunisie</span>
</header>

<main class="container">
  <div class="section-label">Contenu du mail</div>

  <div class="mail-card">
    <div class="mail-card-header">
      <div class="mail-accent-bar"></div>
      <div class="mail-meta">
        <div class="mail-subject">{html_module.escape(row[4] or '—')}</div>
        <div class="mail-field"><span class="mail-field-key">De</span><span class="mail-field-val">{html_module.escape(row[1])}</span></div>
        <div class="mail-field"><span class="mail-field-key">À</span><span class="mail-field-val">{html_module.escape(row[2])}</span></div>
        {'<div class="mail-field"><span class="mail-field-key">Cc</span><span class="mail-field-val">' + html_module.escape(row[3]) + '</span></div>' if row[3] else ''}
        <div class="mail-field"><span class="mail-field-key">Envoyé</span><span class="mail-field-val">{fmt_date(row[7])}</span></div>
        {'<div class="mail-field"><span class="mail-field-key">Ouvert</span><span class="mail-field-val">' + fmt_date(row[8]) + '</span></div>' if row[8] else ''}
      </div>
    </div>

    <div class="mail-body-section">
      <div class="mail-body-label">Contenu</div>
      <div class="mail-body-text">{html_module.escape(body_display)}</div>
    </div>

    {'<div class="mail-summary-section"><div class="summary-icon">✦</div><div class="summary-text">' + html_module.escape(row[6]) + '</div></div>' if row[6] else ''}

    <div class="mail-status-row">
      {status_badge(row[8], row[9], row[10])}
      <span style="font-size:12px;color:var(--meta);">
        {'Rappel répondu le ' + fmt_date(row[11]) if row[11] else "Aucune réponse au rappel pour l'instant"}
      </span>
    </div>

    <div class="mail-reminder-section" id="reminder-section">
      {_reminder_html(str(tracking_id), row[10], row[11], fmt_date)}
    </div>
  </div>

  <div class="section-label">Historique des mails ({len(history)} entrées)</div>

  <div class="history-table-wrap">
    <table>
      <thead>
        <tr>
          <th>Sujet</th>
          <th>Expéditeur</th>
          <th>Destinataire</th>
          <th>Envoyé</th>
          <th>Statut</th>
        </tr>
      </thead>
      <tbody id="history-tbody">{history_rows}</tbody>
    </table>
  </div>
</main>
</body>
</html>""")