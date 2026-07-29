# test_scenario_b.py
import requests
from auth import create_access_token

ADMIN_USERNAME = "REDACTED_USERNAME"

# Simule un token admin pour le test (ou fais un vrai login /api/admin/login)
resp = requests.post("http://localhost:8000/api/admin/login", json={"username": ADMIN_USERNAME, "password": "REDACTED_PASSWORD"})
token = resp.json()["access_token"]

resp = requests.get("http://localhost:8000/api/admin/imap-alerts", headers={"Authorization": f"Bearer {token}"})
print(resp.status_code)
print(resp.json())