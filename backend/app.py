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
    """Liste des mails non ouverts depuis plus de ALERT_THRESHOLD_MINUTES."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """SELECT tracking_id, sender_email, recipient_email, cc_email, subject, ai_summary,
                  sent_at, reminder_done
           FROM email_log
           WHERE opened_at IS NULL
           AND alert_acked = FALSE
           AND sent_at < NOW() - (%s * INTERVAL '1 minute')""",
        (THRESHOLD_MINUTES,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {
            "tracking_id": r[0],
            "sender": r[1],
            "recipient": r[2],
            "cc": r[3] or "",
            "subject": r[4],
            "summary": r[5] or "",
            "sent_at": str(r[6]),
            "reminder_done": r[7],  # null / true / false
        }
        for r in rows
    ]


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
    Persisté en base pour permettre un historique ultérieur."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """UPDATE email_log
           SET reminder_done = %s, reminder_answered_at = NOW()
           WHERE tracking_id = %s""",
        (payload.done, tracking_id),
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
           ORDER BY sent_at DESC"""
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
           FROM email_log ORDER BY sent_at DESC"""
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

  /* ── Animation ── */
  @keyframes fadeUp {{
    from {{ opacity: 0; transform: translateY(14px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
  }}
</style>
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
        {'Rappel répondu le ' + fmt_date(row[11]) if row[11] else 'Aucune réponse au rappel pour l\'instant'}
      </span>
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
      <tbody>{history_rows}</tbody>
    </table>
  </div>
</main>
</body>
</html>""")