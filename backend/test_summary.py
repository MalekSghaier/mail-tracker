# test_summary.py
from ollama_client import generer_resume

# Simule un mail professionnel
body = """
Bonjour Malek,

Nous avons besoin de valider les spécifications techniques du projet avant la réunion de demain.
Pouvez-vous confirmer que le document a été mis à jour avec les nouvelles exigences ?

Merci,
Safouene
"""

resume = generer_resume(body)
print(f"Résumé: {resume}")