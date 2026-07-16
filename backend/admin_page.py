"""
Interface web admin — gestion des comptes utilisateurs abonnés (ARS).

Route : GET /admin

À brancher dans app.py :
    from admin_page import router as admin_router
    app.include_router(admin_router)

Endpoints backend nécessaires (à ajouter dans app.py si absents) :
    POST /api/admin/users/{id}/activate   → réactive un utilisateur désactivé
    GET  /api/admin/stats                  → statistiques (users + mails)
"""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/admin", response_class=HTMLResponse)
def admin_page():
    return HTMLResponse(content="""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Mail Detector — Administration</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    --bg:        #0a0a10;
    --bg-glow:   radial-gradient(circle at 20% 0%, rgba(212,175,90,.07), transparent 40%),
                 radial-gradient(circle at 80% 100%, rgba(90,120,240,.05), transparent 45%);
    --surface:   #17171f;
    --card:      #1b1b25;
    --card-2:    #1e1e29;
    --border:    #2a2a38;
    --gold:      #d4af5a;
    --gold-dim:  #a07c30;
    --text:      #e8e8f0;
    --meta:      #8888a0;
    --green:     #48b280;
    --red:       #d46060;
    --blue:      #5a9cf0;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background-color: var(--bg);
    background-image: var(--bg-glow);
    color: var(--text);
    font-family: 'Inter', sans-serif;
    font-size: 14px;
    min-height: 100vh;
  }
  .header {
    border-bottom: 1px solid var(--border);
    padding: 18px 40px;
    display: flex; align-items: center; gap: 12px;
  }
  .header-logo {
    width: 32px; height: 32px;
    background: linear-gradient(135deg, var(--gold), var(--gold-dim));
    border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    font-size: 16px;
    box-shadow: 0 4px 14px rgba(212,175,90,.25);
  }
  .header-title { font-size: 15px; font-weight: 600; }
  .header-sub { font-size: 12px; color: var(--meta); margin-left: auto; }

  .container { max-width: 1200px; margin: 0 auto; padding: 48px 24px 80px; }

  /* ---------------- LOGIN ---------------- */
  #login-view {
    max-width: 380px;
    margin: 8vh auto 0;
  }
  .login-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 40px 36px;
    box-shadow: 0 24px 60px rgba(0,0,0,.45);
    animation: floatIn .5s cubic-bezier(.16,1,.3,1) both;
  }
  .login-badge {
    width: 52px; height: 52px;
    border-radius: 14px;
    background: linear-gradient(135deg, var(--gold), var(--gold-dim));
    display: flex; align-items: center; justify-content: center;
    font-size: 24px;
    margin: 0 auto 20px;
    box-shadow: 0 8px 24px rgba(212,175,90,.3);
  }
  .login-title { text-align: center; font-size: 19px; font-weight: 700; margin-bottom: 6px; }
  .login-subtitle { text-align: center; font-size: 12.5px; color: var(--meta); margin-bottom: 28px; }

  .field { margin-bottom: 18px; }
  .field label {
    display: block; font-size: 11.5px; font-weight: 600;
    letter-spacing: .03em; color: var(--meta);
    margin-bottom: 7px;
  }
  .field input {
    width: 100%;
    background: var(--surface);
    border: 1.5px solid var(--border);
    border-radius: 10px;
    padding: 11px 14px;
    color: var(--text);
    font-size: 14px;
    font-family: inherit;
    transition: border-color .15s, box-shadow .15s;
  }
  .field input:focus {
    outline: none;
    border-color: var(--gold-dim);
    box-shadow: 0 0 0 3px rgba(212,175,90,.15);
  }

  .btn {
    font-family: inherit;
    cursor: pointer;
    border: none;
    border-radius: 30px;
    font-weight: 600;
    font-size: 13.5px;
    transition: opacity .15s, transform .1s, filter .15s;
    position: relative;
  }
  .btn:hover { filter: brightness(1.08); transform: translateY(-1px); }
  .btn:active { transform: translateY(0); }
  .btn-primary {
    background: linear-gradient(135deg, var(--gold), var(--gold-dim));
    color: #17171a;
    padding: 12px 20px;
    width: 100%;
    margin-top: 6px;
    box-shadow: 0 6px 20px rgba(212,175,90,.22);
  }
  .btn-primary[disabled] { pointer-events: none; opacity: .85; }
  .btn-primary .spinner { display: none; }
  .btn-primary.loading .btn-label { visibility: hidden; }
  .btn-primary.loading .spinner {
    display: block;
    position: absolute; top: 50%; left: 50%;
    width: 16px; height: 16px;
    margin: -8px 0 0 -8px;
    border: 2px solid rgba(23,23,26,.35);
    border-top-color: #17171a;
    border-radius: 50%;
    animation: spin .7s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  @keyframes floatIn {
    from { opacity: 0; transform: translateY(16px) scale(.98); }
    to   { opacity: 1; transform: translateY(0) scale(1); }
  }

  .btn-danger {
    background: rgba(212,96,96,.12);
    color: var(--red);
    border: 1px solid rgba(212,96,96,.3);
    padding: 6px 14px;
    font-size: 12px;
  }
  .btn-success {
    background: rgba(72,178,128,.12);
    color: var(--green);
    border: 1px solid rgba(72,178,128,.3);
    padding: 6px 14px;
    font-size: 12px;
  }
  .error-msg {
    color: var(--red);
    font-size: 12.5px;
    margin-top: 14px;
    text-align: center;
    display: none;
  }

  /* ---------------- DASHBOARD ---------------- */
  #dashboard-view { display: none; }
  .section-label {
    font-size: 10px; font-weight: 700; letter-spacing: .14em;
    text-transform: uppercase; color: var(--gold);
    margin: 36px 0 14px;
    display: flex; align-items: center; gap: 8px;
  }
  .section-label:first-child { margin-top: 0; }
  .section-label::after { content: ''; flex: 1; height: 1px; background: var(--border); }

  .card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 28px;
  }

  /* ---- stats ---- */
  .stats-row {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 14px;
  }
  .stat-card {
    background: var(--card-2);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 18px 20px;
  }
  .stat-value { font-size: 26px; font-weight: 700; color: var(--text); line-height: 1.1; }
  .stat-label { font-size: 11.5px; color: var(--meta); margin-top: 6px; }
  .stat-card.accent .stat-value { color: var(--gold); }
  .stat-card.green .stat-value { color: var(--green); }
  .stat-card.red .stat-value { color: var(--red); }
  .stat-card.blue .stat-value { color: var(--blue); }

  /* ---- add user form ---- */
  .form-row { display: flex; gap: 12px; align-items: flex-end; flex-wrap: wrap; }
  .form-row > div { flex: 1; min-width: 150px; }
  .form-row label {
    display: block; font-size: 11.5px; font-weight: 600;
    color: var(--meta); margin-bottom: 7px;
  }
  .form-row input {
    width: 100%;
    background: var(--surface);
    border: 1.5px solid var(--border);
    border-radius: 10px;
    padding: 10px 13px;
    color: var(--text);
    font-size: 13.5px;
    font-family: inherit;
    transition: border-color .15s, box-shadow .15s;
  }
  .form-row input:focus {
    outline: none;
    border-color: var(--gold-dim);
    box-shadow: 0 0 0 3px rgba(212,175,90,.15);
  }
  .form-row select {
    width: 100%;
    background: var(--surface);
    border: 1.5px solid var(--border);
    border-radius: 10px;
    padding: 10px 13px;
    color: var(--text);
    font-size: 13.5px;
    font-family: inherit;
    transition: border-color .15s, box-shadow .15s;
    cursor: pointer;
  }
  .form-row select:focus {
    outline: none;
    border-color: var(--gold-dim);
    box-shadow: 0 0 0 3px rgba(212,175,90,.15);
  }
  #add-user-btn { padding: 10px 24px; white-space: nowrap; }
  .msg-ok, .msg-err { font-size: 12.5px; margin-top: 12px; display: none; }
  .msg-ok { color: var(--green); }
  .msg-err { color: var(--red); }

  /* ---- table ---- */
  .table-scroll { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; min-width: 760px; }
  thead th {
    text-align: left; padding: 12px 16px;
    font-size: 10px; font-weight: 700; letter-spacing: .1em;
    text-transform: uppercase; color: var(--meta);
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
  }
  tbody tr { border-bottom: 1px solid var(--border); transition: opacity .2s; }
  tbody tr:last-child { border-bottom: none; }
  tbody tr.row-inactive { opacity: .45; }
  tbody tr.row-inactive .username-cell { text-decoration: line-through; text-decoration-color: var(--meta); }
  td { padding: 13px 16px; vertical-align: middle; white-space: nowrap; }
  .username-cell { font-weight: 600; }
  .badge-active { color: var(--green); font-size: 12px; font-weight: 600; white-space: nowrap; }
  .badge-inactive { color: var(--meta); font-size: 12px; white-space: nowrap; }
  .role-badge {
    display: inline-block; padding: 3px 9px; border-radius: 20px;
    font-size: 11px; font-weight: 600; white-space: nowrap;
  }
  .role-employee { background: rgba(136,136,160,.12); color: var(--meta); }
  .role-dept_admin { background: rgba(90,156,240,.14); color: var(--blue); }
  .role-superadmin { background: rgba(212,175,90,.16); color: var(--gold); }
  .btn-edit {
    background: var(--surface);
    color: var(--text);
    border: 1px solid var(--border);
    padding: 6px 12px;
    font-size: 12px;
    margin-right: 8px;
  }

  .logout-link {
    font-size: 12px; color: var(--meta); cursor: pointer;
    text-decoration: underline; margin-left: auto;
  }
  .empty-state { padding: 32px; text-align: center; color: var(--meta); font-size: 13px; }

  /* ---------------- MODALE DE CONFIRMATION ---------------- */
  .modal-overlay {
    position: fixed; inset: 0;
    background: rgba(6,6,10,.65);
    backdrop-filter: blur(3px);
    display: none;
    align-items: center; justify-content: center;
    z-index: 1000;
    animation: fadeIn .15s ease both;
  }
  .modal-overlay.visible { display: flex; }
  @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }

  .modal-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 18px;
    padding: 30px 30px 24px;
    width: 100%;
    max-width: 340px;
    box-shadow: 0 30px 70px rgba(0,0,0,.5);
    animation: modalPop .18s cubic-bezier(.16,1,.3,1) both;
  }
  @keyframes modalPop {
    from { opacity: 0; transform: scale(.94) translateY(6px); }
    to   { opacity: 1; transform: scale(1) translateY(0); }
  }
  .modal-icon {
    width: 44px; height: 44px;
    border-radius: 12px;
    background: rgba(212,96,96,.12);
    border: 1px solid rgba(212,96,96,.25);
    color: var(--red);
    display: flex; align-items: center; justify-content: center;
    font-size: 20px;
    margin-bottom: 16px;
  }
  .modal-title { font-size: 15.5px; font-weight: 700; margin-bottom: 8px; }
  .modal-message { font-size: 13px; color: var(--meta); line-height: 1.5; margin-bottom: 24px; }
  .modal-actions { display: flex; gap: 10px; }
  .modal-actions .btn { flex: 1; padding: 10px 0; font-size: 13px; }
  .btn-ghost {
    background: var(--surface);
    color: var(--text);
    border: 1px solid var(--border);
  }
  .btn-ghost:hover { filter: brightness(1.15); }
  .modal-actions .btn-danger-solid {
    background: linear-gradient(135deg, #e07373, var(--red));
    color: #fff;
    border: none;
    box-shadow: 0 6px 18px rgba(212,96,96,.25);
  }
</style>
</head>
<body>

<header class="header">
  <div class="header-logo">✉</div>
  <span class="header-title">Mail Detector — Administration</span>
  <span class="header-sub" id="admin-name"></span>
</header>

<div class="container">

  <!-- LOGIN -->
  <div id="login-view">
    <div class="login-card">
      <div class="login-badge">✉</div>
      <div class="login-title">Administration</div>
      <div class="login-subtitle">Accès réservé aux administrateurs ARS</div>

      <div class="field">
        <label>Nom d'utilisateur</label>
        <input id="login-username" type="text" autocomplete="username">
      </div>
      <div class="field">
        <label>Mot de passe</label>
        <input id="login-password" type="password" autocomplete="current-password">
      </div>

      <button class="btn btn-primary" id="login-btn" onclick="doLogin()">
        <span class="btn-label">Se connecter</span>
        <span class="spinner"></span>
      </button>
      <div class="error-msg" id="login-error">Identifiants invalides.</div>
    </div>
  </div>

  <!-- DASHBOARD -->
  <div id="dashboard-view">

    <div class="section-label">Vue d'ensemble</div>
    <div class="stats-row" id="stats-row">
      <!-- rempli en JS -->
    </div>

    <div class="section-label">Ajouter un utilisateur</div>
    <div class="card">
      <div class="form-row">
        <div>
          <label>Nom d'utilisateur</label>
          <input id="new-username" type="text">
        </div>
        <div>
          <label>Email (optionnel)</label>
          <input id="new-email" type="email">
        </div>
        <div>
          <label>Mot de passe</label>
          <input id="new-password" type="password">
        </div>
        <div>
          <label>Département</label>
          <input id="new-department" type="text" placeholder="ex: IT, RH, Finance">
        </div>
        <div>
          <label>Rôle</label>
          <select id="new-role">
            <option value="employee">Employé</option>
            <option value="dept_admin">Chef de département</option>
            <option value="superadmin">Super admin (voit tout)</option>
          </select>
        </div>
        <button class="btn btn-primary" id="add-user-btn" onclick="addUser()">
          <span class="btn-label">Ajouter</span>
          <span class="spinner"></span>
        </button>
      </div>
      <div class="msg-ok" id="add-ok">Utilisateur créé.</div>
      <div class="msg-err" id="add-err"></div>
    </div>

    <div class="section-label">
      Utilisateurs abonnés
      <span class="logout-link" onclick="logout()">Se déconnecter</span>
    </div>
    <div class="card" style="padding:0; overflow:hidden;">
      <div class="table-scroll">
        <table>
          <thead>
            <tr><th>Nom d'utilisateur</th><th>Email</th><th>Département</th><th>Rôle</th><th>Statut</th><th>Créé le</th><th></th></tr>
          </thead>
          <tbody id="users-tbody"></tbody>
        </table>
      </div>
      <div class="empty-state" id="empty-state" style="display:none;">Aucun utilisateur pour l'instant.</div>
    </div>
  </div>

</div>

<!-- MODALE DE CONFIRMATION -->
<div class="modal-overlay" id="confirm-overlay">
  <div class="modal-card">
    <div class="modal-icon">⚠</div>
    <div class="modal-title" id="confirm-title">Confirmer l'action</div>
    <div class="modal-message" id="confirm-message"></div>
    <div class="modal-actions">
      <button class="btn btn-ghost" id="confirm-cancel">Annuler</button>
      <button class="btn btn-danger-solid" id="confirm-ok">Confirmer</button>
    </div>
  </div>
</div>

<!-- MODALE D'ÉDITION RÔLE / DÉPARTEMENT -->
<div class="modal-overlay" id="edit-overlay">
  <div class="modal-card">
    <div class="modal-icon" style="background:rgba(212,175,90,.12);border-color:rgba(212,175,90,.25);color:var(--gold);">✎</div>
    <div class="modal-title">Modifier le rôle</div>
    <div class="modal-message" id="edit-username-label"></div>
    <div class="field">
      <label>Département</label>
      <input id="edit-department" type="text" placeholder="ex: IT, RH, Finance">
    </div>
    <div class="field" style="margin-bottom:8px;">
      <label>Rôle</label>
      <select id="edit-role" style="width:100%;background:var(--surface);border:1.5px solid var(--border);border-radius:10px;padding:11px 14px;color:var(--text);font-size:14px;font-family:inherit;">
        <option value="employee">Employé</option>
        <option value="dept_admin">Chef de département</option>
        <option value="superadmin">Super admin (voit tout)</option>
      </select>
    </div>
    <div class="modal-actions" style="margin-top:20px;">
      <button class="btn btn-ghost" id="edit-cancel">Annuler</button>
      <button class="btn btn-primary" id="edit-save" style="flex:1;">Enregistrer</button>
    </div>
  </div>
</div>

<script>
let token = localStorage.getItem('admin_token') || null;

function showDashboard() {
  document.getElementById('login-view').style.display = 'none';
  document.getElementById('dashboard-view').style.display = 'block';
  loadStats();
  loadUsers();
}

function showLogin() {
  document.getElementById('login-view').style.display = 'block';
  document.getElementById('dashboard-view').style.display = 'none';
}

function setButtonLoading(btn, loading) {
  btn.classList.toggle('loading', loading);
  btn.disabled = loading;
}

async function doLogin() {
  const username = document.getElementById('login-username').value.trim();
  const password = document.getElementById('login-password').value;
  const errEl = document.getElementById('login-error');
  const btn = document.getElementById('login-btn');
  errEl.style.display = 'none';

  if (!username || !password) {
    errEl.textContent = "Merci de renseigner les deux champs.";
    errEl.style.display = 'block';
    return;
  }

  setButtonLoading(btn, true);
  try {
    const resp = await fetch('/api/admin/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });
    if (!resp.ok) {
      errEl.textContent = 'Identifiants invalides.';
      errEl.style.display = 'block';
      return;
    }
    const data = await resp.json();
    token = data.access_token;
    localStorage.setItem('admin_token', token);
    document.getElementById('admin-name').textContent = username;
    showDashboard();
  } catch (e) {
    errEl.textContent = 'Serveur injoignable.';
    errEl.style.display = 'block';
  } finally {
    setButtonLoading(btn, false);
  }
}

async function logout() {
  try {
    await fetch('/api/auth/logout', {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + token }
    });
  } catch (e) {
  
  }
  token = null;
  localStorage.removeItem('admin_token');
  showLogin();
}

async function authFetch(url, options = {}) {
  options.headers = Object.assign({}, options.headers, { 'Authorization': 'Bearer ' + token });
  const resp = await fetch(url, options);
  if (resp.status === 401 || resp.status === 403) {
    logout();
    throw new Error('Session expirée');
  }
  return resp;
}

async function loadStats() {
  try {
    const resp = await authFetch('/api/admin/stats');
    const s = await resp.json();
    const row = document.getElementById('stats-row');
    row.innerHTML = `
      <div class="stat-card accent">
        <div class="stat-value">${s.users.total}</div>
        <div class="stat-label">Abonnés au total</div>
      </div>
      <div class="stat-card green">
        <div class="stat-value">${s.users.active}</div>
        <div class="stat-label">Comptes actifs</div>
      </div>
      <div class="stat-card red">
        <div class="stat-value">${s.users.inactive}</div>
        <div class="stat-label">Comptes désactivés</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">${s.emails.total}</div>
        <div class="stat-label">Mails suivis</div>
      </div>
      <div class="stat-card blue">
        <div class="stat-value">${s.emails.opened}</div>
        <div class="stat-label">Mails ouverts</div>
      </div>
      <div class="stat-card red">
        <div class="stat-value">${s.emails.reminder_not_done}</div>
        <div class="stat-label">Rappels non faits</div>
      </div>
    `;
  } catch (e) { /* géré par authFetch */ }
}

const ROLE_LABELS = {
  employee: 'Employé',
  dept_admin: 'Chef de département',
  superadmin: 'Super admin',
};

let usersOffset = 0;
const USERS_PAGE_SIZE = 50;

async function loadUsers(offset = 0) {
  try {
    const resp = await authFetch(`/api/admin/users?limit=${USERS_PAGE_SIZE}&offset=${offset}`);
    const data = await resp.json();
    const users = data.items;
    usersOffset = data.offset;
    const tbody = document.getElementById('users-tbody');
    const emptyState = document.getElementById('empty-state');

    if (users.length === 0) {
      tbody.innerHTML = '';
      emptyState.style.display = 'block';
      renderUsersPagination(data.total, data.limit, data.offset);
      return;
    }
    emptyState.style.display = 'none';

    tbody.innerHTML = users.map(u => `
      <tr class="${u.is_active ? '' : 'row-inactive'}">
        <td class="username-cell">${escapeHtml(u.username)}</td>
        <td>${escapeHtml(u.email || '—')}</td>
        <td>${escapeHtml(u.department || '—')}</td>
        <td><span class="role-badge role-${u.account_role}">${ROLE_LABELS[u.account_role] || u.account_role}</span></td>
        <td>${u.is_active ? '<span class="badge-active">● Actif</span>' : '<span class="badge-inactive">● Désactivé</span>'}</td>
        <td>${String(u.created_at).slice(0,16).replace('T',' ')}</td>
        <td style="white-space:nowrap;">
          <button class="btn btn-edit" onclick='openEditRole(${JSON.stringify(u)})'>Modifier</button>
          ${u.is_active
              ? `<button class="btn btn-danger" onclick="deactivateUser(${u.id})">Désactiver</button>`
              : `<button class="btn btn-success" onclick="activateUser(${u.id})">Réactiver</button>`}
        </td>
      </tr>
    `).join('');

    renderUsersPagination(data.total, data.limit, data.offset);
  } catch (e) { /* déjà géré par authFetch */ }
}

function renderUsersPagination(total, limit, offset) {
  let bar = document.getElementById('users-pagination');
  if (!bar) {
    bar = document.createElement('div');
    bar.id = 'users-pagination';
    bar.style.cssText = 'display:flex; gap:12px; align-items:center; margin-top:16px; font-size:13px; color:var(--meta);';
    document.getElementById('users-tbody').closest('table').after(bar);
  }
  const hasPrev = offset > 0;
  const hasNext = offset + limit < total;
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + limit, total);
  bar.innerHTML = `
    <button class="btn" ${hasPrev ? '' : 'disabled'} onclick="loadUsers(${Math.max(0, offset - limit)})">← Précédent</button>
    <span>${from}–${to} sur ${total}</span>
    <button class="btn" ${hasNext ? '' : 'disabled'} onclick="loadUsers(${offset + limit})">Suivant →</button>
  `;
}


let editingUserId = null;

function openEditRole(user) {
  editingUserId = user.id;
  document.getElementById('edit-username-label').textContent = `Utilisateur : ${user.username}`;
  document.getElementById('edit-department').value = user.department || '';
  document.getElementById('edit-role').value = user.account_role || 'employee';
  document.getElementById('edit-overlay').classList.add('visible');
}

function closeEditRole() {
  document.getElementById('edit-overlay').classList.remove('visible');
  editingUserId = null;
}

document.getElementById('edit-cancel').addEventListener('click', closeEditRole);
document.getElementById('edit-overlay').addEventListener('click', (e) => {
  if (e.target.id === 'edit-overlay') closeEditRole();
});

document.getElementById('edit-save').addEventListener('click', async () => {
  if (!editingUserId) return;
  const department = document.getElementById('edit-department').value.trim();
  const account_role = document.getElementById('edit-role').value;
  try {
    await authFetch(`/api/admin/users/${editingUserId}/role`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ department: department || null, account_role })
    });
    closeEditRole();
    loadUsers();
  } catch (e) {}
});

async function addUser() {
  const username = document.getElementById('new-username').value.trim();
  const email = document.getElementById('new-email').value.trim();
  const password = document.getElementById('new-password').value;
  const department = document.getElementById('new-department').value.trim();
  const account_role = document.getElementById('new-role').value;
  const okEl = document.getElementById('add-ok');
  const errEl = document.getElementById('add-err');
  const btn = document.getElementById('add-user-btn');
  okEl.style.display = 'none';
  errEl.style.display = 'none';

  if (!username || !password) {
    errEl.textContent = "Nom d'utilisateur et mot de passe requis.";
    errEl.style.display = 'block';
    return;
  }

  setButtonLoading(btn, true);
  try {
    const resp = await authFetch('/api/admin/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username, email: email || null, password,
        department: department || null, account_role
      })
    });
    if (resp.ok) {
      okEl.style.display = 'block';
      document.getElementById('new-username').value = '';
      document.getElementById('new-email').value = '';
      document.getElementById('new-password').value = '';
      document.getElementById('new-department').value = '';
      document.getElementById('new-role').value = 'employee';
      loadUsers();
      loadStats();
    } else {
      const data = await resp.json();
      errEl.textContent = data.detail || 'Erreur lors de la création.';
      errEl.style.display = 'block';
    }
  } catch (e) {
  } finally {
    setButtonLoading(btn, false);
  }
}

async function deactivateUser(id) {
  const ok = await showConfirm(
    "Cet utilisateur ne pourra plus se connecter à l'agent tant qu'il ne sera pas réactivé.",
    { title: "Désactiver cet utilisateur ?", confirmLabel: "Désactiver" }
  );
  if (!ok) return;
  try {
    await authFetch(`/api/admin/users/${id}`, { method: 'DELETE' });
    loadUsers();
    loadStats();
  } catch (e) {}
}

async function activateUser(id) {
  try {
    await authFetch(`/api/admin/users/${id}/activate`, { method: 'POST' });
    loadUsers();
    loadStats();
  } catch (e) {}
}

function escapeHtml(s) {
  const div = document.createElement('div');
  div.textContent = s || '';
  return div.innerHTML;
}

/* ---- modale de confirmation personnalisée (remplace window.confirm) ---- */
function showConfirm(message, { title = "Confirmer l'action", confirmLabel = "Confirmer" } = {}) {
  return new Promise((resolve) => {
    const overlay = document.getElementById('confirm-overlay');
    const titleEl = document.getElementById('confirm-title');
    const msgEl = document.getElementById('confirm-message');
    const okBtn = document.getElementById('confirm-ok');
    const cancelBtn = document.getElementById('confirm-cancel');

    titleEl.textContent = title;
    msgEl.textContent = message;
    okBtn.textContent = confirmLabel;
    overlay.classList.add('visible');

    function cleanup(result) {
      overlay.classList.remove('visible');
      okBtn.removeEventListener('click', onOk);
      cancelBtn.removeEventListener('click', onCancel);
      overlay.removeEventListener('click', onOverlayClick);
      document.removeEventListener('keydown', onKeydown);
      resolve(result);
    }
    function onOk() { cleanup(true); }
    function onCancel() { cleanup(false); }
    function onOverlayClick(e) { if (e.target === overlay) cleanup(false); }
    function onKeydown(e) { if (e.key === 'Escape') cleanup(false); }

    okBtn.addEventListener('click', onOk);
    cancelBtn.addEventListener('click', onCancel);
    overlay.addEventListener('click', onOverlayClick);
    document.addEventListener('keydown', onKeydown);
  });
}

if (token) {
  showDashboard();
} else {
  showLogin();
}
</script>
</body>
</html>""")