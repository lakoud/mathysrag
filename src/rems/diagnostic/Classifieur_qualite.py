def classify_qualite(data):
    f = data["faithfulness"]
    cp = data["context_precision"]
    ar = data["answer_relevancy"]

    if f is None or cp is None or ar is None:
        return "insufficient_data" 

    # Hallucination : le LLM invente malgré un bon contexte
    if f < 0.7 and cp >= 0.7:
        return "hallucination"

    # Retrieval failure : mauvais documents récupérés
    if cp < 0.7:
        return "retrieval_failure"

    # Off-topic : réponse hors sujet
    if ar < 0.6 and f >= 0.7:
        return "off_topic"

    # Low quality : réponse médiocre 
    if f < 0.75 or ar < 0.75:
        return "low_quality"

    # Acceptable : pas de problème majeur détecté
    return "acceptable"
