"""
Appelle Ollama (local) pour générer un résumé court du corps du mail.
Nécessite qu'Ollama tourne déjà (ollama serve) avec le modèle 'mistral' téléchargé.
"""
import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "mistral"


def generer_resume(body_text: str) -> str:
    if not body_text or not body_text.strip():
        return ""

    prompt = (
        "Résume ce message en une seule phrase courte, en français, "
        "sans introduction ni commentaire :\n\n"
        f"{body_text}"
    )

    try:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": MODEL, "prompt": prompt, "stream": False},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except Exception as e:
        # En cas d'échec (Ollama pas démarré, modèle absent...), on retombe
        # sur un résumé simple plutôt que de bloquer l'enregistrement du mail.
        print(f"[ollama_client] échec génération résumé IA : {e}")
        return body_text.strip()[:150]