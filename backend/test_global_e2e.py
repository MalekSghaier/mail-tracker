# test_global_e2e.py
"""Test global de bout en bout — couvre tous les scénarios principaux
après migration SQLAlchemy (M8 point 2) : flux employé, flux admin,
tâches Celery, authentification."""
import time
import uuid
import requests

BASE = "http://localhost:8000"

# Remplace par des identifiants réels existants dans ta base
EMPLOYEE_USERNAME = "test"
EMPLOYEE_PASSWORD = "123456789"
ADMIN_USERNAME = "ARS_Tunisie"
ADMIN_PASSWORD = "W*MSp2O2-a4/"
MILTER_SECRET = "6d002424f43a261423922368fd4fb4905ea8d3f4ffcd5689a1b037935979b43a" 

PASSED = []
FAILED = []


def check(label, condition, detail=""):
    if condition:
        PASSED.append(label)
        print(f"✅ {label}")
    else:
        FAILED.append(label)
        print(f"❌ {label} — {detail}")


# ============ 1. FLUX EMPLOYÉ ============
print("\n=== 1. Connexion employé ===")
resp = requests.post(f"{BASE}/api/auth/login", json={"username": EMPLOYEE_USERNAME, "password": EMPLOYEE_PASSWORD})
check("Login employé", resp.status_code == 200, resp.text)
user_token = resp.json().get("access_token")

print("\n=== 2. Vérification du token ===")
resp = requests.get(f"{BASE}/api/auth/verify", headers={"Authorization": f"Bearer {user_token}"})
check("Verify token employé", resp.status_code == 200, resp.text)

print("\n=== 3. Enregistrement d'un mail (simule le milter) ===")
resp = requests.post(
    f"{BASE}/api/emails/register",
    json={
        "sender_email": EMPLOYEE_USERNAME + "@gmail.com", 
        "recipient_email": "client@test.com",
        "subject": "Test E2E global",
        "body": "Contenu de test pour le test global.",
    },
    headers={"X-Milter-Secret": MILTER_SECRET},
)
check("register_email", resp.status_code == 200, resp.text)
tracking_id = resp.json().get("tracking_id")
print(f"tracking_id créé : {tracking_id}")

print("\n=== 4. Pixel de tracking (hit immédiat, doit être ignoré) ===")
resp = requests.get(f"{BASE}/track/{tracking_id}")
check("track pixel (scan)", resp.status_code == 200, resp.text)

print("\n=== 5. Ack de l'alerte ===")
resp = requests.post(f"{BASE}/api/alerts/{tracking_id}/ack", headers={"Authorization": f"Bearer {user_token}"})
check("ack_alert", resp.status_code == 200, resp.text)

print("\n=== 6. Statut de l'alerte ===")
resp = requests.get(f"{BASE}/api/alerts/{tracking_id}/status", headers={"Authorization": f"Bearer {user_token}"})
check("get_alert_status", resp.status_code == 200, resp.text)

print("\n=== 7. Réponse au rappel (Non) ===")
resp = requests.post(
    f"{BASE}/api/alerts/{tracking_id}/reminder",
    json={"done": False},
    headers={"Authorization": f"Bearer {user_token}"},
)
check("set_reminder (false)", resp.status_code == 200, resp.text)

print("\n=== 8. J'ai finalement fait le rappel ===")
resp = requests.post(f"{BASE}/api/alerts/{tracking_id}/finally-done", headers={"Authorization": f"Bearer {user_token}"})
check("finally_done", resp.status_code == 200, resp.text)

print("\n=== 9. États en lot (states) ===")
resp = requests.post(
    f"{BASE}/api/alerts/states",
    json={"ids": [tracking_id]},
    headers={"Authorization": f"Bearer {user_token}"},
)
check("get_states", resp.status_code == 200 and tracking_id in resp.json(), resp.text)

print("\n=== 10. Historique ===")
resp = requests.get(f"{BASE}/api/history", headers={"Authorization": f"Bearer {user_token}"})
check("get_history", resp.status_code == 200 and isinstance(resp.json(), list), resp.text)

print("\n=== 11. Détail d'un mail ===")
resp = requests.get(f"{BASE}/api/mail/{tracking_id}", headers={"Authorization": f"Bearer {user_token}"})
check("get_mail_json", resp.status_code == 200 and "mail" in resp.json() and "history" in resp.json(), resp.text)

print("\n=== 12. Page HTML du mail (coquille statique) ===")
resp = requests.get(f"{BASE}/mail/{tracking_id}")
check("mail_detail_page", resp.status_code == 200, resp.text)

print("\n=== 13. Logout employé + révocation ===")
resp = requests.post(f"{BASE}/api/auth/logout", headers={"Authorization": f"Bearer {user_token}"})
check("logout employé", resp.status_code == 200, resp.text)
resp = requests.get(f"{BASE}/api/auth/verify", headers={"Authorization": f"Bearer {user_token}"})
check("token révoqué après logout", resp.status_code == 401, resp.text)


# ============ 2. FLUX ADMIN ============
print("\n=== 14. Connexion admin ===")
resp = requests.post(f"{BASE}/api/admin/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
check("Login admin", resp.status_code == 200, resp.text)
admin_token = resp.json().get("access_token")

print("\n=== 15. Création d'un utilisateur ===")
new_username = f"e2e_test_{uuid.uuid4().hex[:6]}"
resp = requests.post(
    f"{BASE}/api/admin/users",
    json={
        "username": new_username,
        "password": "TestPass123",
        "email": f"{new_username}@ulytechai.com",
        "department": "IT",
        "account_role": "employee",
    },
    headers={"Authorization": f"Bearer {admin_token}"},
)
check("create_user", resp.status_code == 200, resp.text)
new_user_id = resp.json().get("id")

print("\n=== 16. Liste des utilisateurs ===")
resp = requests.get(f"{BASE}/api/admin/users", headers={"Authorization": f"Bearer {admin_token}"})
check("list_users", resp.status_code == 200 and any(u["username"] == new_username for u in resp.json()), resp.text)

print("\n=== 17. Modification du rôle ===")
resp = requests.patch(
    f"{BASE}/api/admin/users/{new_user_id}/role",
    json={"account_role": "dept_admin", "department": "RH"},
    headers={"Authorization": f"Bearer {admin_token}"},
)
check("update_user_role", resp.status_code == 200, resp.text)

print("\n=== 18. Désactivation utilisateur ===")
resp = requests.delete(f"{BASE}/api/admin/users/{new_user_id}", headers={"Authorization": f"Bearer {admin_token}"})
check("deactivate_user", resp.status_code == 200, resp.text)

print("\n=== 19. Réactivation utilisateur ===")
resp = requests.post(f"{BASE}/api/admin/users/{new_user_id}/activate", headers={"Authorization": f"Bearer {admin_token}"})
check("activate_user", resp.status_code == 200, resp.text)

print("\n=== 20. Statistiques admin ===")
resp = requests.get(f"{BASE}/api/admin/stats", headers={"Authorization": f"Bearer {admin_token}"})
check("get_admin_stats", resp.status_code == 200 and "users" in resp.json() and "emails" in resp.json(), resp.text)

print("\n=== 21. Page HTML admin ===")
resp = requests.get(f"{BASE}/admin")
check("admin_page", resp.status_code == 200, resp.text)


# ============ 3. TÂCHE CELERY compute_summary_task ============
print("\n=== 22. Résumé IA (Celery, attente 15s) ===")
time.sleep(15)
resp = requests.get(f"{BASE}/api/mail/{tracking_id}", headers={"Authorization": f"Bearer {admin_token}"})
summary_present = resp.status_code == 200 and resp.json()["mail"].get("summary")
check("compute_summary_task a rempli ai_summary", summary_present, "résumé toujours vide après 15s — vérifie Ollama/worker")


# ============ RÉSUMÉ ============
print(f"\n{'='*50}")
print(f"RÉSULTAT : {len(PASSED)} passés, {len(FAILED)} échoués")
if FAILED:
    print("Échecs :")
    for f in FAILED:
        print(f"  - {f}")
else:
    print("🎉 Tous les tests sont passés.")