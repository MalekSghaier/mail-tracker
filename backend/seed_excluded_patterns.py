"""
Script à lancer une fois pour peupler les motifs d'exclusion initiaux.
Peut être relancé sans risque (ignore les doublons).
"""
from db import get_db
from models import ImapExcludedPattern

DEFAULT_PATTERNS = [
    ("noreply", "Adresses no-reply génériques"),
    ("no-reply", "Adresses no-reply génériques (variante avec tiret)"),
    ("notifications", "Notifications automatiques génériques"),
    ("newsletter", "Newsletters génériques"),
    ("linkedin.com", "Notifications LinkedIn"),
    ("tanitjobs.com", "Alertes emploi Tanitjobs"),
]

with get_db() as db:
    for pattern, description in DEFAULT_PATTERNS:
        existing = db.query(ImapExcludedPattern).filter(ImapExcludedPattern.pattern == pattern).first()
        if not existing:
            db.add(ImapExcludedPattern(pattern=pattern, description=description))
            print(f"Ajouté : {pattern}")
        else:
            print(f"Déjà présent : {pattern}")

print("Terminé.")