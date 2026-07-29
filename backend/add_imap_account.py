"""
Script à lancer manuellement pour enregistrer un compte IMAP à surveiller
(Scénario B). Host/port IMAP sont fixés globalement dans .env (IMAP_HOST,
IMAP_PORT) — seuls l'identité et le mot de passe du compte sont demandés
ici. Le mot de passe est chiffré avant stockage — jamais en clair en base.
"""
import getpass
from db import get_db
from models import ImapAccount
from crypto_utils import encrypt_secret


def main():
    label = input("Nom complet (ex: Naim Boughanmi) : ").strip()
    email_addr = input("Email (ex: naim.boughanmi@arstunisie.com) : ").strip()
    password = getpass.getpass("Mot de passe IMAP : ")

    with get_db() as db:
        existing = db.query(ImapAccount).filter(ImapAccount.email == email_addr).first()
        if existing:
            print(f"Un compte existe déjà pour {email_addr}. Abandon.")
            return

        account = ImapAccount(
            label=label,
            email=email_addr,
            encrypted_password=encrypt_secret(password),
        )
        db.add(account)
        db.flush()
        print(f"Compte IMAP créé pour {label} (id={account.id}).")


if __name__ == "__main__":
    main()