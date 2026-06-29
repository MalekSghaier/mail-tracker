"""
Appelle Ollama (local) pour générer un résumé court du corps du mail.
Nécessite qu'Ollama tourne déjà (ollama serve) avec le modèle téléchargé.
"""
import re

import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3.2:1b"

# Mots à ignorer dans la vérification de cohérence (trop fréquents pour être discriminants)
STOPWORDS = {
    "le", "la", "les", "un", "une", "des", "de", "du", "et", "ou", "à", "au",
    "aux", "ce", "cette", "ces", "pour", "par", "sur", "dans", "avec", "que",
    "qui", "est", "sont", "a", "ont", "se", "son", "sa", "ses", "en", "il",
    "elle", "vous", "nous", "merci", "bonjour",
}


def _mots_significatifs(texte: str) -> set:
    mots = re.findall(r"[a-zàâäéèêëïîôùûüç]{4,}", texte.lower())
    return set(mots) - STOPWORDS


def _resume_coherent(body_text: str, resume: str) -> bool:
    """Vérification basique anti-hallucination : le résumé doit partager au
    moins un mot significatif avec le texte d'origine. Imparfait mais
    suffisant pour rejeter les résumés complètement inventés."""
    mots_body = _mots_significatifs(body_text)
    mots_resume = _mots_significatifs(resume)
    if not mots_body or not mots_resume:
        return True  # pas assez de matière pour juger, on laisse passer
    return len(mots_body & mots_resume) > 0


def generer_resume(body_text: str) -> str:
    if not body_text or not body_text.strip():
        return ""

    prompt = (
        "Voici un e-mail professionnel reçu par un employé. Ta tâche est UNIQUEMENT de "
        "résumer ce message en une phrase, du point de vue d'un observateur extérieur. "
        "Ne réponds JAMAIS au message, n'invente AUCUN contenu, ne donne aucun avis.\n\n"
        "Exemple :\n"
        "Message : « Bonjour, peux-tu m'envoyer le rapport mensuel avant 17h ? »\n"
        "Résumé : Demande d'envoi du rapport mensuel avant 17h.\n\n"
        "Maintenant, résume ce message de la même façon (une seule phrase, "
        "rien d'autre) :\n"
        f"« {body_text} »\n"
        "Résumé :"
    )

    fallback = re.sub(r"<[^>]+>", "", body_text).strip()[:150]

    try:
        resp = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.1},  # moins de "créativité" = moins d'hallucination
            },
            timeout=90,
        )
        resp.raise_for_status()
        resume = resp.json().get("response", "").strip()

        if not resume or not _resume_coherent(body_text, resume):
            print(f"[ollama_client] résumé rejeté (incohérent) : {resume!r} — fallback utilisé")
            return fallback

        return resume
    except Exception as e:
        # En cas d'échec (Ollama pas démarré, modèle absent...), on retombe
        # sur un résumé simple plutôt que de bloquer l'enregistrement du mail.
        print(f"[ollama_client] échec génération résumé IA : {e}")
        return fallback