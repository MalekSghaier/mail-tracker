"""Script de test pour H5 — vérifie que le pixel renvoie bien les
en-têtes anti-cache attendus."""
import requests
import uuid

tracking_id = str(uuid.uuid4())

resp = requests.get(f"http://localhost:8000/track/{tracking_id}")

print(f"Status          : {resp.status_code}")
print(f"Cache-Control    : {resp.headers.get('Cache-Control')}")
print(f"Pragma           : {resp.headers.get('Pragma')}")
print(f"Expires          : {resp.headers.get('Expires')}")
print(f"Content-Type     : {resp.headers.get('Content-Type')}")
print(f"Taille du body   : {len(resp.content)} octets")

attendu = "no-store, no-cache, must-revalidate, max-age=0"
if resp.headers.get('Cache-Control') == attendu:
    print("\n✅ H5 corrigé : Cache-Control est bien présent et correct.")
else:
    print(f"\n❌ H5 PAS corrigé : Cache-Control attendu '{attendu}', reçu '{resp.headers.get('Cache-Control')}'")