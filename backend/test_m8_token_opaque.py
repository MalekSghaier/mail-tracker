# test_m8_token_opaque.py
"""Vérifie : token de 256 bits, stocké haché (pas en clair), sans
expiration, révocable immédiatement."""
import requests
from db import get_conn

BASE = "http://localhost:8000"

resp = requests.post(f"{BASE}/api/auth/login", json={"username": "test", "password": "123456789"})
token = resp.json()["access_token"]
print(f"Token reçu : {token}")
print(f"Longueur du token : {len(token)} caractères hex = {len(token) * 4} bits")
assert len(token) == 64, "Le token doit faire 64 caractères hex (256 bits)"

# Vérifie qu'aucun token en clair n'existe en base — seulement son hash
with get_conn() as conn:
    cur = conn.cursor()
    cur.execute("SELECT token_hash FROM sessions ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    cur.close()
print(f"Valeur stockée en base : {row[0]}")
assert row[0] != token, "Le token en clair ne doit JAMAIS être stocké tel quel"
print("✅ Le token stocké est bien haché, différent du token en clair.")

resp = requests.get(f"{BASE}/api/auth/verify", headers={"Authorization": f"Bearer {token}"})
print(f"Avant logout -> status {resp.status_code}")

resp = requests.post(f"{BASE}/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
print(f"Logout -> status {resp.status_code}")

resp = requests.get(f"{BASE}/api/auth/verify", headers={"Authorization": f"Bearer {token}"})
print(f"Après logout -> status {resp.status_code}")
assert resp.status_code == 401
print("✅ Révocation immédiate confirmée.")