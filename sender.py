"""
Envoie un mail de test via le SMTP ulytech, en injectant le pixel
lui-même (pas de milter — fonctionne avec de simples identifiants de
boîte mail, sans accès admin serveur).

Lancer avec : python sender.py
"""
import os
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests
from dotenv import load_dotenv

load_dotenv()
API_BASE = os.getenv("TRACKING_BASE_URL", "http://localhost:8000")


def envoyer_mail_test(sender_email, recipient_email, subject, body_html, cc_email=None):
    # 1. Enregistrer l'e-mail auprès du backend (génère tracking_id + résumé IA via Ollama)
    resp = requests.post(
        f"{API_BASE}/api/emails/register",
        json={
            "sender_email": sender_email,
            "recipient_email": recipient_email,
            "cc_email": cc_email,
            "subject": subject,
            "body": body_html,
        },
    )
    resp.raise_for_status()
    tracking_id = resp.json()["tracking_id"]

    # 2. Injecter le pixel dans le corps HTML
    pixel_tag = f'<img src="{API_BASE}/track/{tracking_id}" width="1" height="1" style="display:none">'
    html_final = body_html + pixel_tag

    # 3. Construire et envoyer le mail via le SMTP ulytech (identifiants boîte mail uniquement)
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = recipient_email
    if cc_email:
        msg["Cc"] = cc_email
    msg.attach(MIMEText(html_final, "html"))

    destinataires_reels = [recipient_email] + ([cc_email] if cc_email else [])

    smtp_port = int(os.getenv("SMTP_PORT"))
    if smtp_port == 465:
        # OVH (et beaucoup d'hébergeurs) : SSL direct, pas de starttls()
        with smtplib.SMTP_SSL(os.getenv("SMTP_HOST"), smtp_port) as server:
            server.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD"))
            server.sendmail(sender_email, destinataires_reels, msg.as_string())
    else:
        # Port 587 classique : STARTTLS
        with smtplib.SMTP(os.getenv("SMTP_HOST"), smtp_port) as server:
            server.starttls()
            server.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD"))
            server.sendmail(sender_email, destinataires_reels, msg.as_string())

    print(f"Mail envoyé à {recipient_email}" + (f" (cc: {cc_email})" if cc_email else "") + f". tracking_id = {tracking_id}")
    print("N'ouvre pas ce mail tout de suite si tu veux voir l'alerte se déclencher !")


if __name__ == "__main__":
    moi = os.getenv("SMTP_USER")  # tu es l'expéditeur ET le destinataire pour ce test

    messages_test = [
        ("Test Mail Detector 1 — ne pas ouvrir", "<p>Premier mail de test : merci de valider le devis n°1.</p>", None),
        ("Test Mail Detector 2 — ne pas ouvrir", "<p>Deuxième mail de test : le rapport mensuel est prêt.</p>", None),
        ("Test Mail Detector 3 — ne pas ouvrir", "<p>Troisième mail de test : la réunion est prévue vendredi.</p>", None),
        ("Test Mail Detector 4 — avec Cc — ne pas ouvrir", "<p>Quatrième mail de test : ceci teste l'affichage du Cc dans le popup.</p>", moi),
    ]

    for subject, body, cc in messages_test:
        envoyer_mail_test(moi, moi, subject, body, cc_email=cc)
        time.sleep(2)  # éviter d'envoyer tous les mails à la même seconde exacte