@app.get("/imap-mail/{tracking_id}", response_class=HTMLResponse)
def imap_mail_detail_page(tracking_id: str):
    return HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>Mail Detector — Mail reçu</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg:#0e0e14; --surface:#17171f; --card:#1e1e28; --border:#2a2a38;
    --gold:#d4af5a; --gold-dim:#a07c30; --text:#e8e8f0; --meta:#8888a0;
    --green:#48b280; --red:#d46060; --amber:#e8a040;
  }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ background:var(--bg); color:var(--text); font-family:'Inter',sans-serif; font-size:14px; }}
  .header {{ border-bottom:1px solid var(--border); padding:18px 40px; display:flex; align-items:center; gap:12px; }}
  .header-logo {{ width:32px; height:32px; background:linear-gradient(135deg,var(--gold),var(--gold-dim)); border-radius:8px; display:flex; align-items:center; justify-content:center; }}
  .container {{ max-width:1000px; margin:0 auto; padding:40px; }}
  #login-view {{ max-width:380px; margin:8vh auto 0; }}
  .login-card {{ background:var(--card); border:1px solid var(--border); border-radius:20px; padding:40px 36px; }}
  .field {{ margin-bottom:18px; }}
  .field label {{ display:block; font-size:11.5px; color:var(--meta); margin-bottom:7px; }}
  .field input {{ width:100%; background:var(--surface); border:1.5px solid var(--border); border-radius:10px; padding:11px 14px; color:var(--text); font-family:inherit; }}
  .btn {{ font-family:inherit; cursor:pointer; border:none; border-radius:30px; font-weight:600; font-size:13.5px; }}
  .btn-primary {{ background:linear-gradient(135deg,var(--gold),var(--gold-dim)); color:#17171a; padding:12px 20px; width:100%; }}
  .error-msg {{ color:var(--red); font-size:12.5px; margin-top:14px; text-align:center; display:none; }}
  .section-label {{ font-size:10px; font-weight:700; letter-spacing:.14em; text-transform:uppercase; color:var(--gold); margin-bottom:16px; display:flex; gap:8px; }}
  .section-label::after {{ content:''; flex:1; height:1px; background:var(--border); }}
  .mail-card {{ background:var(--card); border:1px solid var(--border); border-radius:16px; overflow:hidden; margin-bottom:48px; }}
  .mail-card-header {{ padding:28px 32px 24px; border-bottom:1px solid var(--border); display:flex; gap:24px; }}
  .mail-accent-bar {{ width:4px; border-radius:4px; background:linear-gradient(to bottom,var(--gold),var(--gold-dim)); align-self:stretch; }}
  .mail-subject {{ font-size:20px; font-weight:600; margin-bottom:16px; }}
  .mail-field {{ display:flex; gap:8px; font-size:13px; margin-bottom:6px; }}
  .mail-field-key {{ color:var(--meta); width:100px; flex-shrink:0; }}
  .mail-status-row {{ padding:16px 32px; background:var(--surface); border-top:1px solid var(--border); display:flex; gap:16px; align-items:center; flex-wrap:wrap; }}
  .badge {{ display:inline-flex; align-items:center; gap:5px; padding:4px 10px; border-radius:20px; font-size:11px; font-weight:600; }}
  .badge::before {{ content:'●'; font-size:8px; }}
  .badge-yes {{ background:rgba(72,178,128,.15); color:var(--green); }}
  .badge-no {{ background:rgba(212,96,96,.15); color:var(--red); }}
  .badge-acked {{ background:rgba(136,136,160,.12); color:var(--meta); }}
  .badge-pending {{ background:rgba(232,160,64,.15); color:var(--amber); }}
  .mail-reminder-section {{ padding:20px 32px 24px; display:flex; align-items:center; gap:20px; border-top:1px solid var(--border); flex-wrap:wrap; }}
  .reminder-buttons {{ display:flex; gap:10px; }}
  .btn-reminder {{ display:inline-flex; align-items:center; gap:7px; padding:8px 20px; border:none; border-radius:30px; font-family:inherit; font-size:13px; font-weight:600; cursor:pointer; }}
  .btn-oui {{ background:rgba(72,178,128,.18); color:var(--green); border:1px solid rgba(72,178,128,.35); }}
  .btn-non {{ background:rgba(212,96,96,.15); color:var(--red); border:1px solid rgba(212,96,96,.3); }}
  .reminder-done {{ display:flex; align-items:center; gap:10px; font-size:13px; font-weight:600; padding:8px 16px; border-radius:30px; }}
  .reminder-yes {{ background:rgba(72,178,128,.12); color:var(--green); border:1px solid rgba(72,178,128,.25); }}
  .reminder-no {{ background:rgba(212,96,96,.12); color:var(--red); border:1px solid rgba(212,96,96,.25); }}
  .btn-finally-done {{ display:inline-flex; align-items:center; gap:8px; padding:9px 20px; background:rgba(212,175,90,.12); color:var(--gold); border:1px solid rgba(212,175,90,.3); border-radius:30px; font-family:inherit; font-size:13px; font-weight:600; cursor:pointer; }}
  .recheck-notice {{ font-size:12px; color:var(--amber); }}
  .history-table-wrap {{ background:var(--card); border:1px solid var(--border); border-radius:16px; overflow:hidden; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  thead {{ background:var(--surface); border-bottom:1px solid var(--border); }}
  thead th {{ padding:12px 20px; text-align:left; font-size:10px; font-weight:700; text-transform:uppercase; color:var(--meta); }}
  tbody tr {{ border-bottom:1px solid var(--border); cursor:pointer; }}
  tbody tr:hover {{ background:rgba(255,255,255,.03); }}
  tbody tr.row-current td {{ color:var(--gold); font-weight:600; }}
  td {{ padding:14px 20px; }}
</style>
</head>
<body>
<header class="header"><div class="header-logo">✉</div><span>Mail Detector — Mails reçus</span></header>
<main class="container">
  <div id="loading-view" style="text-align:center;padding:60px 0;color:var(--meta);">Chargement…</div>
  <div id="login-view" style="display:none;">
    <div class="login-card">
      <div class="field"><label>Nom d'utilisateur</label><input id="login-username" type="text"></div>
      <div class="field"><label>Mot de passe</label><input id="login-password" type="password"></div>
      <button class="btn btn-primary" onclick="doLogin()">Se connecter</button>
      <div class="error-msg" id="login-error">Identifiants invalides.</div>
    </div>
  </div>
  <div id="content-view" style="display:none;">
    <div class="section-label">Mail reçu</div>
    <div class="mail-card">
      <div class="mail-card-header"><div class="mail-accent-bar"></div><div id="mail-meta"></div></div>
      <div id="mail-summary-section"></div>
      <div class="mail-status-row" id="mail-status-row"></div>
      <div class="mail-reminder-section" id="reminder-section"></div>
    </div>
    <div class="section-label" id="history-label">Mails non lus du département</div>
    <div class="history-table-wrap">
      <table>
        <thead><tr><th>Employé</th><th>Expéditeur</th><th>Sujet</th><th>Reçu</th><th>Statut</th></tr></thead>
        <tbody id="history-tbody"></tbody>
      </table>
    </div>
  </div>
</main>
<script>
const mid = '{tracking_id}';
let token = localStorage.getItem('user_token') || null;
function escapeHtml(s) {{ const d=document.createElement('div'); d.textContent=s||''; return d.innerHTML; }}
function fmtDate(d) {{ return d ? String(d).slice(0,16).replace('T',' ') : '—'; }}
function statusBadge(is_seen, acked, reminder) {{
  if (is_seen) return '<span class="badge badge-yes">Lu</span>';
  if (reminder === true) return '<span class="badge badge-yes">Rappel fait</span>';
  if (reminder === false) return '<span class="badge badge-no">Rappel non fait</span>';
  if (acked) return '<span class="badge badge-acked">Vu — sans réponse</span>';
  return '<span class="badge badge-pending">Non lu</span>';
}}
async function authFetch(url, options={{}}) {{
  options.headers = Object.assign({{}}, options.headers, {{'Authorization':'Bearer '+token}});
  const r = await fetch(url, options);
  if (r.status===401||r.status===403) {{ token=null; localStorage.removeItem('user_token'); showLogin(); throw new Error('expiré'); }}
  return r;
}}
function showLogin() {{
  document.getElementById('loading-view').style.display='none';
  document.getElementById('login-view').style.display='block';
  document.getElementById('content-view').style.display='none';
}}
async function doLogin() {{
  const username = document.getElementById('login-username').value.trim();
  const password = document.getElementById('login-password').value;
  const errEl = document.getElementById('login-error');
  try {{
    const r = await fetch('/api/auth/login', {{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{username,password}})}});
    if (!r.ok) {{ errEl.style.display='block'; return; }}
    const d = await r.json();
    token = d.access_token;
    localStorage.setItem('user_token', token);
    loadMail();
  }} catch(e) {{ errEl.textContent='Serveur injoignable.'; errEl.style.display='block'; }}
}}
function renderReminder(reminder_done, reminder_at) {{
  const dt = fmtDate(reminder_at);
  if (reminder_done === true) return `<div class="reminder-done reminder-yes">✓ Relance effectuée — ${{dt}}</div>`;
  if (reminder_done === false) return `<div><div class="reminder-done reminder-no">✗ Relance non effectuée — ${{dt}}</div>
    <button class="btn-finally-done" onclick="finallyDone()">✓ Relance finalement faite</button>
    <div class="recheck-notice">↻ Nouvelle alerte automatique.</div></div>`;
  return `<span>Avez-vous relancé l'employé ?</span><div class="reminder-buttons">
    <button class="btn-reminder btn-oui" onclick="submitReminder(true)">✓ Oui</button>
    <button class="btn-reminder btn-non" onclick="submitReminder(false)">✗ Non</button></div>`;
}}
function renderMail(mail, history) {{
  let metaHtml = `
    <div class="mail-subject">${{escapeHtml(mail.subject || '—')}}</div>
    <div class="mail-field"><span class="mail-field-key">Employé</span>${{escapeHtml(mail.employee_username)}} (${{escapeHtml(mail.department||'')}})</div>
    <div class="mail-field"><span class="mail-field-key">De</span>${{escapeHtml(mail.sender)}}</div>
    <div class="mail-field"><span class="mail-field-key">À</span>${{escapeHtml(mail.recipient)}}</div>`;
  if (mail.cc) {{
    metaHtml += `<div class="mail-field"><span class="mail-field-key">Cc</span>${{escapeHtml(mail.cc)}}</div>`;
  }}
  metaHtml += `<div class="mail-field"><span class="mail-field-key">Reçu</span>${{fmtDate(mail.received_at)}}</div>`;
  document.getElementById('mail-meta').innerHTML = metaHtml;

  const summarySection = document.getElementById('mail-summary-section');
  summarySection.innerHTML = mail.summary
    ? `<div class="mail-summary-section"><div class="summary-icon">✦</div><div class="summary-text">${{escapeHtml(mail.summary)}}</div></div>`
    : '';

  document.getElementById('mail-status-row').innerHTML = statusBadge(mail.is_seen, mail.supervisor_acked, mail.reminder_done);
  document.getElementById('reminder-section').innerHTML = renderReminder(mail.reminder_done, mail.reminder_answered_at);
  document.getElementById('history-label').textContent = `Mails non lus du département (${{history.length}})`;
  document.getElementById('history-tbody').innerHTML = history.map(h => {{
      const isCurrent = h.tracking_id === mid ? 'row-current' : '';
      return `<tr class="${{isCurrent}}" onclick="window.location='/imap-mail/${{h.tracking_id}}'">
        <td>${{escapeHtml(h.employee_username)}}</td><td>${{escapeHtml(h.sender)}}</td>
        <td>${{escapeHtml(h.subject)}}</td><td>${{fmtDate(h.received_at)}}</td>
        <td>${{statusBadge(h.is_seen, false, h.reminder_done)}}</td></tr>`;
  }}).join('');
}}
async function loadMail() {{
  try {{
    const r = await authFetch(`/api/imap-mail/${{mid}}`);
    document.getElementById('loading-view').style.display='none';
    if (!r.ok) {{
      document.getElementById('content-view').innerHTML = '<h1>Mail introuvable ou accès refusé</h1>';
      document.getElementById('content-view').style.display='block';
      return;
    }}
    const data = await r.json();
    renderMail(data.mail, data.history);
    document.getElementById('login-view').style.display='none';
    document.getElementById('content-view').style.display='block';
  }} catch(e) {{}}
}}
async function submitReminder(done) {{
  await authFetch(`/api/imap-alerts/${{mid}}/reminder`, {{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{done}})}});
  await loadMail();
}}
async function finallyDone() {{
  await authFetch(`/api/imap-alerts/${{mid}}/finally-done`, {{method:'POST'}});
  await loadMail();
}}
if (token) loadMail(); else {{ document.getElementById('loading-view').style.display='none'; document.getElementById('login-view').style.display='block'; }}
setInterval(() => {{ if (token) loadMail(); }}, 3000);
</script>
</body>
</html>""")