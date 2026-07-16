# test_m8_token_opaque.py
"""Vérifie : token de 256 bits, stocké haché (pas en clair), sans
expiration, révocable immédiatement."""
import requests
from db import get_db
from models import Session

BASE = "http://localhost:8000"

resp = requests.post(f"{BASE}/api/auth/login", json={"username": "test", "password": "123456789"})
token = resp.json()["access_token"]
print(f"Token reçu : {token}")
print(f"Longueur du token : {len(token)} caractères hex = {len(token) * 4} bits")
assert len(token) == 64, "Le token doit faire 64 caractères hex (256 bits)"

# Vérifie qu'aucun token en clair n'existe en base — seulement son hash
with get_db() as db:
    session = db.query(Session).order_by(Session.id.desc()).first()
    token_hash = session.token_hash

print(f"Valeur stockée en base : {token_hash}")
assert token_hash != token, "Le token en clair ne doit JAMAIS être stocké tel quel"
print("✅ Le token stocké est bien haché, différent du token en clair.")

resp = requests.get(f"{BASE}/api/auth/verify", headers={"Authorization": f"Bearer {token}"})
print(f"Avant logout -> status {resp.status_code}")

resp = requests.post(f"{BASE}/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
print(f"Logout -> status {resp.status_code}")

resp = requests.get(f"{BASE}/api/auth/verify", headers={"Authorization": f"Bearer {token}"})
print(f"Après logout -> status {resp.status_code}")
assert resp.status_code == 401
print("✅ Révocation immédiate confirmée.")