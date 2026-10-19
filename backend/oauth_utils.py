import os
import msal
from dotenv import load_dotenv

load_dotenv()

TENANT_ID = os.getenv("AZURE_TENANT_ID")
CLIENT_ID = os.getenv("AZURE_CLIENT_ID")
CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")
SCOPE = ["https://outlook.office365.com/.default"]

OAUTH_DOMAINS = [
    d.strip().lower()
    for d in os.getenv("OAUTH_DOMAINS", "arstunisie.com").split(",")
    if d.strip()
]


def _uses_oauth(email_address: str) -> bool:
    return email_address.rsplit("@", 1)[-1].lower() in OAUTH_DOMAINS


_app = None


def _get_app():
    global _app
    if _app is None:
        if not (TENANT_ID and CLIENT_ID and CLIENT_SECRET):
            raise RuntimeError(
                "AZURE_TENANT_ID, AZURE_CLIENT_ID et AZURE_CLIENT_SECRET "
                "doivent être définis dans .env"
            )
        _app = msal.ConfidentialClientApplication(
            CLIENT_ID,
            authority=f"https://login.microsoftonline.com/{TENANT_ID}",
            client_credential=CLIENT_SECRET,
        )
    return _app


def get_access_token() -> str:
    result = _get_app().acquire_token_for_client(scopes=SCOPE)
    if "access_token" not in result:
        raise RuntimeError(
            f"Échec obtention du jeton OAuth : {result.get('error')} - "
            f"{result.get('error_description')}"
        )
    return result["access_token"]