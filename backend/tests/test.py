import requests

API_BASE = "http://localhost:8000"
TRACKING_ID = "138c6a3a-d36f-4acc-a315-5f36466435c3"
TOKEN = "a59e1e1fcb5fd0766999f1707ca5270a35f8695892281122d9c7fa8d9b86fe99"

resp = requests.post(
    f"{API_BASE}/api/imap-alerts/{TRACKING_ID}/ack",
    headers={"Authorization": f"Bearer {TOKEN}"},
)
print(resp.status_code, resp.json())