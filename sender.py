"""
Envoie un mail de test via le SMTP ulytech, en injectant le pixel
lui-même (pas de milter — fonctionne avec de simples identifiants de
boîte mail, sans accès admin serveur).

Lancer avec : python sender.py
"""
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests
from dotenv import load_dotenv

load_dotenv()
API_BASE = os.getenv("TRACKING_BASE_URL", "http://localhost:8000")


def envoyer_mail_test(sender_email, recipient_email, subject, body_html):
    # 1. Enregistrer l'e-mail auprès du backend (génère tracking_id + résumé IA via Ollama)
    resp = requests.post(
        f"{API_BASE}/api/emails/register",
        json={
            "sender_email": sender_email,
            "recipient_email": recipient_email,
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
    msg.attach(MIMEText(html_final, "html"))

    smtp_port = int(os.getenv("SMTP_PORT"))
    if smtp_port == 465:
        # OVH (et beaucoup d'hébergeurs) : SSL direct, pas de starttls()
        with smtplib.SMTP_SSL(os.getenv("SMTP_HOST"), smtp_port) as server:
            server.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD"))
            server.sendmail(sender_email, recipient_email, msg.as_string())
    else:
        # Port 587 classique : STARTTLS
        with smtplib.SMTP(os.getenv("SMTP_HOST"), smtp_port) as server:
            server.starttls()
            server.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD"))
            server.sendmail(sender_email, recipient_email, msg.as_string())

    print(f"Mail envoyé à {recipient_email}. tracking_id = {tracking_id}")
    print("N'ouvre pas ce mail tout de suite si tu veux voir l'alerte se déclencher !")


if __name__ == "__main__":
    moi = os.getenv("SMTP_USER")  # tu es l'expéditeur ET le destinataire pour ce test
    envoyer_mail_test(
        sender_email=moi,
        recipient_email=moi,
        subject="Test Mail Detector — ne pas ouvrir tout de suite",
        body_html="<p>Ceci est un test du système de suivi d'ouverture des e-mails.</p>",
    )