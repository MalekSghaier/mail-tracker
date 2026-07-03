"""
Script à lancer une seule fois, en local, pour créer le tout premier compte
admin ARS. Ensuite les admins se connectent via POST /api/admin/login et
ajoutent des users via POST /api/admin/users — plus besoin de ce script.
"""
import getpass
import os

import psycopg2
from dotenv import load_dotenv

from auth import hash_password

load_dotenv()


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
    if secret != os.getenv("ADMIN_SECRET_KEY"):
        print("Clé secrète incorrecte. Abandon.")
        return

    username = input("Nom d'utilisateur admin : ").strip()
    password = getpass.getpass("Mot de passe admin : ")
    password2 = getpass.getpass("Confirmer le mot de passe : ")
    if password != password2:
        print("Les mots de passe ne correspondent pas.")
        return

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO admins (username, password_hash) VALUES (%s, %s) RETURNING id",
        (username, hash_password(password)),
    )
    admin_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    print(f"Admin créé avec l'id {admin_id}.")


if __name__ == "__main__":
    main()