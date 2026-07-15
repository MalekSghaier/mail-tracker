"""
Script à lancer une seule fois, en local, pour créer le tout premier compte
admin ARS. Ensuite les admins se connectent via POST /api/admin/login et
ajoutent des users via POST /api/admin/users — plus besoin de ce script.
"""
import getpass
import hmac
import os

import psycopg2
from dotenv import load_dotenv

from auth import hash_password

load_dotenv()

MIN_PASSWORD_LENGTH = 8


def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT", 5432),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


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

    conn = get_conn()
    try:
        cur = conn.cursor()
        try:
            cur.execute("SELECT id FROM admins WHERE username = %s", (username,))
            if cur.fetchone():
                print(f"Le nom d'utilisateur '{username}' existe déjà. Abandon.")
                return

            cur.execute(
                "INSERT INTO admins (username, password_hash) VALUES (%s, %s) RETURNING id",
                (username, hash_password(password)),
            )
            admin_id = cur.fetchone()[0]
            conn.commit()
            print(f"Admin créé avec l'id {admin_id}.")
        finally:
            cur.close()
    finally:
        conn.close()


if __name__ == "__main__":
    main()