"""
Résumé extractif — sans LLM, rapide et déterministe. Sélectionne la
ligne/phrase la plus informative du corps du mail plutôt que de générer
du texte, pour éviter tout risque d'hallucination et de lenteur/charge CPU.
"""
import re

STOPWORDS = {
    "le", "la", "les", "un", "une", "des", "de", "du", "et", "ou", "à", "au",
    "aux", "ce", "cette", "ces", "pour", "par", "sur", "dans", "avec", "que",
    "qui", "est", "sont", "a", "ont", "se", "son", "sa", "ses", "en", "il",
    "elle", "vous", "nous", "merci", "bonjour", "cordialement", "the", "a",
    "an", "of", "to", "and", "or", "is", "are", "in", "on", "for", "with",
}

# Lignes de politesse/formule sans valeur informative — exclues d'office
LIGNES_IGNOREES = {
    "bonjour", "cordialement", "merci", "bien à vous", "salutations",
    "meilleures salutations", "regards", "best regards", "sincerely",
}


def _decouper_phrases(texte: str) -> list[str]:
    """Découpe d'abord par ligne (les mails structurés mettent souvent une
    information par ligne, sans ponctuation de fin de phrase), puis par
    ponctuation de fin de phrase à l'intérieur de chaque ligne."""
    lignes = [l.strip() for l in texte.split("\n") if l.strip()]
    phrases = []
    for ligne in lignes:
        if ligne.lower().strip(" .:") in LIGNES_IGNOREES:
            continue
        sous_phrases = re.split(r"(?<=[.!?])\s+", ligne)
        for sp in sous_phrases:
            sp = sp.strip()
            if len(sp) > 10:
                phrases.append(sp)
    return phrases


def _score_phrase(phrase: str, mots_frequents: dict) -> float:
    mots = re.findall(r"[a-zàâäéèêëïîôùûüç]{4,}", phrase.lower())
    mots = [m for m in mots if m not in STOPWORDS]
    if not mots:
        return 0.0
    score = sum(mots_frequents.get(m, 0) for m in mots) / len(mots)
    return score


def generer_resume_extractif(body_text: str, has_attachment: bool = False, max_length: int = 160) -> str:
    """Extrait la ligne/phrase la plus représentative du corps du mail.
    Ne génère rien : renvoie du texte réellement présent dans le mail.
    Si une pièce jointe est détectée, l'indique explicitement plutôt que
    de risquer un résumé vide ou peu pertinent."""
    piece_jointe_note = " Une pièce jointe a été envoyée." if has_attachment else ""

    if not body_text or not body_text.strip():
        if has_attachment:
            return "L'expéditeur a envoyé une pièce jointe, sans texte dans le corps du message."
        return ""

    phrases = _decouper_phrases(body_text)
    if not phrases:
        # Aucune phrase claire détectée : on prend les premiers mots (pas
        # tout le texte) pour rester un vrai résumé, pas une copie brute.
        mots = body_text.strip().split()
        resume = " ".join(mots[:18])
        if len(mots) > 18:
            resume += "…"
        return resume + piece_jointe_note

    tous_mots = re.findall(r"[a-zàâäéèêëïîôùûüç]{4,}", body_text.lower())
    tous_mots = [m for m in tous_mots if m not in STOPWORDS]
    frequences: dict[str, int] = {}
    for m in tous_mots:
        frequences[m] = frequences.get(m, 0) + 1

    candidates = phrases[:5] if len(phrases) > 5 else phrases
    meilleure = max(candidates, key=lambda p: _score_phrase(p, frequences))

    if len(meilleure) > max_length:
        meilleure = meilleure[:max_length].rsplit(" ", 1)[0] + "…"

    return meilleure + piece_jointe_note