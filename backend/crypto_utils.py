"""
chiffrement symétrique (Fernet/AES) des identifiants
IMAP sensibles, avant stockage en base.
"""
import os
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

_KEY = os.getenv("IMAP_ENCRYPTION_KEY")
if not _KEY:
    raise RuntimeError(
        "IMAP_ENCRYPTION_KEY n'est pas défini. Génère une clé avec : "
        "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\" "
        "et ajoute-la dans .env."
    )

_fernet = Fernet(_KEY.encode())


def encrypt_secret(plain_text: str) -> str:
    """Chiffre une valeur sensible (mot de passe IMAP) avant stockage."""
    return _fernet.encrypt(plain_text.encode("utf-8")).decode("utf-8")


def decrypt_secret(encrypted_text: str) -> str:
    """Déchiffre une valeur stockée — utilisé uniquement au moment de la
    connexion IMAP, jamais exposé ailleurs (logs, réponses API)."""
    return _fernet.decrypt(encrypted_text.encode("utf-8")).decode("utf-8")