#!/usr/bin/env python
"""Simulate an evaluation with fake data for testing purposes."""

import random
from datetime import datetime, timezone

from rems.models import (
    Evaluation,
    EvaluationResult,
    Interaction,
    Recommendation,
    RetrievedDocument,
    get_session,
    init_db,
)


def simulate_evaluation():
    """Create a simulated evaluation with fake data."""
    print("Initializing database...")
    init_db()

    with get_session() as session:
        # Create sample interactions
        interactions_data = [
            {
                "query": "Quelle est la procédure de déclaration fiscale pour les entreprises ?",
                "response": "Selon l'article 12 du Code Général des Impôts, les entreprises doivent effectuer leur déclaration fiscale dans un délai de 3 mois suivant la clôture de l'exercice.",
                "docs": [
                    ("Article 12 - Délais de déclaration fiscale...", "code_impots.pdf"),
                    ("Article 13 - Modalités de transmission...", "code_impots.pdf"),
                ],
            },
            {
                "query": "Quelles sont les sanctions en cas de retard de déclaration ?",
                "response": "Une majoration de 10% est appliquée sur le montant des droits dus en cas de retard.",
                "docs": [
                    ("Article 1728 - Sanctions pour défaut de déclaration...", "code_impots.pdf"),
                ],
            },
            {
                "query": "Comment calculer la TVA récupérable ?",
                "response": "La TVA récupérable correspond à la TVA payée sur les achats professionnels.",
                "docs": [
                    ("Article 271 - Droit à déduction de TVA...", "code_impots.pdf"),
                ],
            },
            {
                "query": "Quel est le taux d'imposition sur les sociétés ?",
                "response": "Le taux normal de l'impôt sur les sociétés est de 25% depuis 2022.",
                "docs": [
                    ("Article 219 - Taux de l'impôt sur les sociétés...", "code_impots.pdf"),
                ],
            },
            {
                "query": "Quand doit-on payer la CFE ?",
                "response": "La CFE doit être payée au plus tard le 15 décembre de chaque année.",
                "docs": [
                    ("Article 1679 - Exigibilité de la CFE...", "code_impots.pdf"),
                ],
            },
        ]

        print(f"Creating {len(interactions_data)} interactions...")
        interactions = []
        for data in interactions_data:
            interaction = Interaction(
                query=data["query"],
                response=data["response"],
            )
            for content, source in data["docs"]:
                doc = RetrievedDocument(
                    content=content,
                    source=source,
                    rank=0,
                )
                interaction.retrieved_documents.append(doc)
            session.add(interaction)
            interactions.append(interaction)

        session.flush()

        # Create evaluation with simulated scores
        print("Creating simulated evaluation...")

        # Simulate realistic scores
        faithfulness_scores = [random.uniform(0.7, 0.95) for _ in interactions]
        relevancy_scores = [random.uniform(0.75, 0.92) for _ in interactions]
        precision_scores = [random.uniform(0.65, 0.88) for _ in interactions]

        avg_faithfulness = sum(faithfulness_scores) / len(faithfulness_scores)
        avg_relevancy = sum(relevancy_scores) / len(relevancy_scores)
        avg_precision = sum(precision_scores) / len(precision_scores)

        # One hallucination for testing
        faithfulness_scores[2] = 0.45  # Simulate a hallucination

        retrieval_score = avg_precision
        generation_score = (avg_faithfulness + avg_relevancy) / 2
        overall_score = retrieval_score * 0.35 + generation_score * 0.65

        hallucination_count = sum(1 for s in faithfulness_scores if s < 0.7)
        hallucination_rate = hallucination_count / len(interactions)

        # Score distribution
        all_scores = [(f * 0.6 + r * 0.4) for f, r in zip(faithfulness_scores, relevancy_scores)]
        distribution = {
            "excellent": len([s for s in all_scores if s >= 0.90]),
            "good": len([s for s in all_scores if 0.75 <= s < 0.90]),
            "acceptable": len([s for s in all_scores if 0.60 <= s < 0.75]),
            "poor": len([s for s in all_scores if 0.40 <= s < 0.60]),
            "critical": len([s for s in all_scores if s < 0.40]),
        }

        evaluation = Evaluation(
            name="Évaluation de test (simulée)",
            description="Évaluation avec données simulées pour tester l'interface",
            interaction_count=len(interactions),
            overall_score=overall_score,
            retrieval_score=retrieval_score,
            generation_score=generation_score,
            metrics={
                "avg_context_precision": avg_precision,
                "avg_context_relevancy": avg_precision,  # Same as precision for simulation
                "avg_faithfulness": avg_faithfulness,
                "avg_answer_relevancy": avg_relevancy,
                "hallucination_rate": hallucination_rate,
                "total_hallucinations": hallucination_count,
                "score_distribution": distribution,
            },
            completed_at=datetime.now(timezone.utc),
        )
        session.add(evaluation)
        session.flush()

        # Create evaluation results for each interaction
        print("Creating evaluation results...")
        for idx, interaction in enumerate(interactions):
            result = EvaluationResult(
                evaluation_id=evaluation.id,
                interaction_id=interaction.id,
                faithfulness=faithfulness_scores[idx],
                answer_relevancy=relevancy_scores[idx],
                context_precision=precision_scores[idx],
                context_relevancy=precision_scores[idx],
                has_hallucination=faithfulness_scores[idx] < 0.7,
                overall_score=all_scores[idx],
            )
            session.add(result)

        # Create recommendations
        print("Creating recommendations...")
        recommendations = [
            Recommendation(
                evaluation_id=evaluation.id,
                component="generator",
                issue="faithfulness trop faible sur certaines réponses: 45.0% (seuil: 70.0%)\n\nCauses probables:\n  - Température du LLM trop élevée\n  - Contexte insuffisant fourni au LLM",
                suggestion="Réduire la température du LLM et renforcer les instructions de citation des sources dans le prompt système",
                priority="high",
                parameter_adjustments={
                    "generator.temperature": {"action": "decrease", "suggested_value": 0.3},
                },
            ),
            Recommendation(
                evaluation_id=evaluation.id,
                component="retriever",
                issue=f"context_precision moyenne: {avg_precision:.1%} (seuil recommandé: 80%)\n\nCauses probables:\n  - Top-K potentiellement trop élevé\n  - Seuil de similarité à ajuster",
                suggestion="Augmenter le seuil de similarité pour filtrer les documents moins pertinents",
                priority="medium",
                parameter_adjustments={
                    "retriever.similarity_threshold": {"action": "increase", "suggested_value": 0.75},
                },
            ),
        ]
        for rec in recommendations:
            session.add(rec)

        print("\n" + "=" * 60)
        print("SIMULATION TERMINÉE")
        print("=" * 60)
        print(f"Interactions créées: {len(interactions)}")
        print(f"Score global: {overall_score:.1%}")
        print(f"Score retrieval: {retrieval_score:.1%}")
        print(f"Score génération: {generation_score:.1%}")
        print(f"Taux d'hallucination: {hallucination_rate:.1%}")
        print(f"Recommandations: {len(recommendations)}")
        print("=" * 60)
        print("\nOuvrez http://localhost:8501 pour voir les résultats!")


if __name__ == "__main__":
    simulate_evaluation()
