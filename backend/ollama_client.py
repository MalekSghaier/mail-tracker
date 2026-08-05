"""
Appelle Ollama (local) pour générer un résumé court du corps du mail.
Nécessite qu'Ollama tourne déjà (ollama serve) avec le modèle téléchargé.
"""
import re
import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:3b"  # Changé de llama3.2:1b à qwen2.5:3b

# Mots à ignorer dans la vérification de cohérence
STOPWORDS = {
    "le", "la", "les", "un", "une", "des", "de", "du", "et", "ou", "à", "au",
    "aux", "ce", "cette", "ces", "pour", "par", "sur", "dans", "avec", "que",
    "qui", "est", "sont", "a", "ont", "se", "son", "sa", "ses", "en", "il",
    "elle", "vous", "nous", "merci", "bonjour", "cordialement", "the", "a",
    "an", "of", "to", "and", "or", "is", "are", "in", "on", "for", "with",
}

def _mots_significatifs(texte: str) -> set:
    mots = re.findall(r"[a-zàâäéèêëïîôùûüç]{4,}", texte.lower())
    return set(mots) - STOPWORDS

def _resume_coherent(body_text: str, resume: str) -> bool:
    """Vérification basique anti-hallucination."""
    mots_body = _mots_significatifs(body_text)
    mots_resume = _mots_significatifs(resume)
    if not mots_body or not mots_resume:
        return True
    return len(mots_body & mots_resume) > 0

def generer_resume(body_text: str) -> str:
    """Génère un résumé en une phrase générale."""
    if not body_text or not body_text.strip():
        return ""

    # Nettoie le body pour éviter les balises HTML, URLs, etc.
    body_clean = re.sub(r"<[^>]+>", " ", body_text)
    body_clean = re.sub(r"https?://\S+", "", body_clean)
    body_clean = re.sub(r"\s+", " ", body_clean).strip()
    
    # Tronque si trop long pour éviter de saturer le contexte
    if len(body_clean) > 3000:
        body_clean = body_clean[:3000] + "..."

    prompt = (
        "Voici un e-mail. Résume-le en une phrase courte et générale (10-15 mots) "
        "qui donne le sujet principal. Ne réponds pas au message, ne donne pas d'avis, "
        "ne répète pas le texte. Juste une phrase résumant le sujet.\n\n"
        f"Message : « {body_clean} »\n"
        "Résumé :"
    )

    fallback = " ".join(body_clean.split()[:20]) + "..."

    try:
        resp = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": 30,  # Résumé court
                    "top_k": 20,
                    "top_p": 0.8,
                },
                "keep_alive": "5m",
            },
            timeout=60,
        )
        resp.raise_for_status()
        resume = resp.json().get("response", "").strip()
        print(f"[ollama_client] Résumé généré pour body de {len(body_text)} caractères: {resume!r}")

        # Si le résumé est vide, trop court ou incohérent, on utilise le fallback
        if not resume or len(resume.split()) < 3:
            print(f"[ollama_client] Résumé trop court, fallback utilisé")
            return fallback

        if not _resume_coherent(body_clean, resume):
            print(f"[ollama_client] Résumé incohérent, fallback utilisé")
            return fallback

        # Nettoie le résumé
        resume = re.sub(r'^["\']+|["\']+$', '', resume).strip()
        if len(resume) > 200:
            resume = resume[:200] + "..."

        return resume

    except requests.exceptions.Timeout:
        print("[ollama_client] Timeout Ollama")
        return fallback
    except requests.exceptions.ConnectionError:
        print("[ollama_client] Connexion impossible à Ollama")
        return fallback
    except Exception as e:
        print(f"[ollama_client] Erreur inattendue : {e}")
        return fallback