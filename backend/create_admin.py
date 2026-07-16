"""
Script à lancer une seule fois, en local, pour créer le tout premier compte
admin ARS.
"""
import getpass
import hmac
import os

from dotenv import load_dotenv

from auth import hash_password
from db import get_db
from models import Admin

load_dotenv()

MIN_PASSWORD_LENGTH = 8


def main():
    secret = getpass.getpass("ADMIN_SECRET_KEY: ")
    expected_secret = os.getenv("ADMIN_SECRET_KEY", "")
    if not expected_secret or not hmac.compare_digest(secret, expected_secret):
        print("Clé secrète incorrecte. Abandon.")
        return

    username = input("Nom d'utilisateur admin : ").strip()
    if not username:
        print("Le nom d'utilisateur ne peut pas être vide.")
        return

    password = getpass.getpass("Mot de passe admin : ")
    password2 = getpass.getpass("Confirmer le mot de passe : ")
    if password != password2:
        print("Les mots de passe ne correspondent pas.")
        return
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"Le mot de passe doit contenir au moins {MIN_PASSWORD_LENGTH} caractères.")
        return

    with get_db() as db:
        existing = db.query(Admin).filter(Admin.username == username).first()
        if existing:
            print(f"Le nom d'utilisateur '{username}' existe déjà. Abandon.")
            return

        admin = Admin(username=username, password_hash=hash_password(password))
        db.add(admin)
        db.flush()  # pour récupérer admin.id avant le commit final
        print(f"Admin créé avec l'id {admin.id}.")


if __name__ == "__main__":
    main()