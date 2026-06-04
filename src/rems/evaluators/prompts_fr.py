"""French legal domain prompts for Ragas evaluators."""

from ragas.metrics._faithfulness import (
    NLIStatementInput, 
    NLIStatementOutput, 
    StatementFaithfulnessAnswer,
    StatementGeneratorInput,
    StatementGeneratorOutput,
    NLIStatementPrompt,
    StatementGeneratorPrompt
)
from ragas.metrics._answer_relevance import (
    ResponseRelevanceInput,
    ResponseRelevanceOutput,
    ResponseRelevancePrompt
)
from ragas.metrics._context_precision import (
    QAC,
    Verification,
    ContextPrecisionPrompt
)

# axis A & C: Instructions domaine + Langue
LEGAL_DOMAIN_INSTRUCTION = (
    "Tu évalues un chatbot réglementaire français spécialisé en LCB-FT, fiscalité et droit des sociétés. "
    "Un article de loi mal numéroté ou un décret inexistant = hallucination grave."
)

# Faithfulness - NLI Statement Prompt
# axis B: Exemples few-shot domaine
nli_statement_prompt_fr = NLIStatementPrompt()
nli_statement_prompt_fr.instruction = f"{LEGAL_DOMAIN_INSTRUCTION} Évalue la fidélité des affirmations basées sur le contexte fourni. Réponds 1 si l'affirmation peut être directement déduite du contexte, 0 sinon."
nli_statement_prompt_fr.examples = [
    (
        NLIStatementInput(
            context="Le Code monétaire et financier (CMF) détaille les obligations de vigilance LCB-FT. L'article L561-5 impose l'identification du client avant l'entrée en relation d'affaires.",
            statements=[
                "L'article L561-5 du CMF concerne l'identification du client.",
                "Le seuil de déclaration Tracfin est de 15 000€.",
                "L'article L999-9 du CMF interdit le blanchiment."
            ]
        ),
        NLIStatementOutput(
            statements=[
                StatementFaithfulnessAnswer(
                    statement="L'article L561-5 du CMF concerne l'identification du client.",
                    reason="Le contexte mentionne explicitement que l'article L561-5 impose l'identification du client.",
                    verdict=1
                ),
                StatementFaithfulnessAnswer(
                    statement="Le seuil de déclaration Tracfin est de 15 000€.",
                    reason="Cette information n'est pas présente dans le contexte. De plus, il n'existe pas de seuil monétaire général pour les déclarations de soupçon Tracfin.",
                    verdict=0
                ),
                StatementFaithfulnessAnswer(
                    statement="L'article L999-9 du CMF interdit le blanchiment.",
                    reason="Le contexte ne mentionne pas d'article L999-9. L'invention d'un numéro d'article inexistant est une hallucination grave.",
                    verdict=0
                )
            ]
        )
    )
]

# Faithfulness - Statement Generator Prompt
statement_generator_prompt_fr = StatementGeneratorPrompt()
statement_generator_prompt_fr.instruction = "Analyse la complexité de chaque phrase dans la réponse. Décompose chaque phrase en une ou plusieurs affirmations simples et indépendantes. N'utilise aucun pronom. Formate en JSON."
statement_generator_prompt_fr.examples = [
    (
        StatementGeneratorInput(
            question="Quelles sont les obligations de vigilance ?",
            answer="Elles comprennent l'identification du bénéficiaire effectif et la vérification de son identité sur la base de documents probants."
        ),
        StatementGeneratorOutput(
            statements=[
                "Les obligations de vigilance comprennent l'identification du bénéficiaire effectif.",
                "Les obligations de vigilance comprennent la vérification de l'identité du bénéficiaire effectif.",
                "La vérification de l'identité du bénéficiaire effectif se fait sur la base de documents probants."
            ]
        )
    )
]

# Answer Relevancy
response_relevance_prompt_fr = ResponseRelevancePrompt()
response_relevance_prompt_fr.instruction = "Génère une question pour la réponse donnée et identifie si la réponse est évasive, vague ou ambiguë. Donne 'noncommittal' à 1 si la réponse est évasive, 0 sinon."
response_relevance_prompt_fr.examples = [
    (
        ResponseRelevanceInput(response="Le blanchiment de capitaux est puni de cinq ans d'emprisonnement et de 375 000 euros d'amende."),
        ResponseRelevanceOutput(question="Quelle est la peine encourue pour blanchiment ?", noncommittal=0)
    ),
    (
        ResponseRelevanceInput(response="Je ne suis pas en mesure de confirmer l'existence de ce décret spécifique car mes données s'arrêtent en 2023."),
        ResponseRelevanceOutput(question="Le décret n°2024-123 est-il applicable ?", noncommittal=1)
    )
]

# Context Precision
context_precision_prompt_fr = ContextPrecisionPrompt()
context_precision_prompt_fr.instruction = f"{LEGAL_DOMAIN_INSTRUCTION} Évalue si le contexte fourni a été utile pour arriver à la réponse donnée. Réponds 1 si utile, 0 sinon."
context_precision_prompt_fr.examples = [
    (
        QAC(
            question="Qui doit effectuer la déclaration de soupçon ?",
            context="L'article L561-15 du CMF précise que les personnes mentionnées à l'article L561-2 sont tenues de déclarer à Tracfin les sommes inscrites dans leurs livres qui pourraient provenir d'une infraction.",
            answer="Ce sont les professionnels listés à l'article L561-2 du Code monétaire et financier."
        ),
        Verification(
            reason="Le contexte cite précisément l'article L561-15 qui renvoie à la liste des professionnels de l'article L561-2, ce qui permet de répondre directement à la question.",
            verdict=1
        )
    )
]

# Context Relevancy (NV Metrics templates)
template_relevance1_fr = (
    "### Instructions\n\n"
    "Tu es un expert mondial chargé d'évaluer le score de pertinence d'un contexte pour répondre à une question.\n"
    "Ton rôle est de déterminer si le contexte contient les informations appropriées pour répondre à la question.\n"
    "Ne te fie pas à tes connaissances préalables. Utilise uniquement ce qui est écrit.\n"
    "Suis les instructions suivantes :\n"
    "0. Si le contexte ne contient aucune information pertinente, réponds 0.\n"
    "1. Si le contexte contient partiellement des informations pertinentes, réponds 1.\n"
    "2. Si le contexte contient des informations pertinentes permettant de répondre, réponds 2.\n"
    "Réponds uniquement 0, 1 ou 2. Ne fournis aucune explication.\n\n"
    "### Question: {query}\n\n"
    "### Contexte: {context}\n\n"
    "Le score de pertinence est : "
)

template_relevance2_fr = (
    "En tant qu'expert spécialisé dans l'évaluation de la pertinence d'un contexte par rapport à une question, "
    "je dois déterminer dans quelle mesure le contexte est nécessaire pour répondre. Je me base uniquement sur le contexte fourni.\n\n"
    "0 : aucune information pertinente.\n"
    "1 : informations partiellement pertinentes.\n"
    "2 : informations pertinentes.\n\n"
    "### Question: {query}\n\n"
    "### Contexte: {context}\n\n"
    "Basé sur la question et le contexte, le score est : ["
)

# Mapping for easily applying prompts
FRENCH_PROMPTS = {
    "faithfulness": {
        "nli_statements_prompt": nli_statement_prompt_fr,
        "statement_generator_prompt": statement_generator_prompt_fr
    },
    "answer_relevancy": {
        "response_relevance_prompt": response_relevance_prompt_fr
    },
    "context_precision": {
        "context_precision_prompt": context_precision_prompt_fr
    },
    "context_relevance": {
        "template_relevance1": template_relevance1_fr,
        "template_relevance2": template_relevance2_fr
    }
}
