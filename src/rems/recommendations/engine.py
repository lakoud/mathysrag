"""Recommendation Engine - Generates improvement recommendations."""

from pathlib import Path

import structlog
import yaml

from rems.config import settings
from rems.diagnostic.engine import Component, DiagnosedIssue, DiagnosticEngine, Severity
from rems.models import Recommendation, get_session
from rems.schemas import EvaluationSummary, RecommendationSchema

logger = structlog.get_logger()


# Mapping from diagnosed issues to specific recommendations
RECOMMENDATION_RULES: dict[str, dict] = {
    # Retriever recommendations
    "low_context_precision": {
        "suggestion": "Réduire le nombre de documents récupérés (top_k) ou augmenter le seuil de similarité",
        "parameter_adjustments": {
            "retriever.top_k": {"action": "decrease", "suggested_value": 3},
            "retriever.similarity_threshold": {"action": "increase", "suggested_value": 0.75},
        },
    },
    "low_context_relevancy": {
        "suggestion": "Optimiser le chunking des documents ou améliorer les embeddings",
        "parameter_adjustments": {
            "indexing.chunk_size": {"action": "adjust", "suggested_value": 512},
            "indexing.chunk_overlap": {"action": "adjust", "suggested_value": 50},
        },
    },
    # Generator recommendations
    "low_faithfulness": {
        "suggestion": "Ajouter des instructions explicites dans le prompt pour citer les sources et ne pas inventer",
        "parameter_adjustments": {
            "generator.temperature": {"action": "decrease", "suggested_value": 0.3},
            "generator.system_prompt": {
                "action": "append",
                "suggested_value": (
                    "IMPORTANT: Base ta réponse UNIQUEMENT sur les documents fournis. "
                    "Si l'information n'est pas dans les documents, dis-le explicitement. "
                    "Ne jamais inventer d'informations."
                ),
            },
        },
    },
    "low_answer_relevancy": {
        "suggestion": "Améliorer le prompt pour guider vers des réponses plus directes et pertinentes",
        "parameter_adjustments": {
            "generator.system_prompt": {
                "action": "append",
                "suggested_value": (
                    "Réponds de manière concise et directe à la question posée. "
                    "Évite les digressions."
                ),
            },
        },
    },
    "high_hallucination_rate": {
        "suggestion": "Réduire la température du LLM et renforcer les guardrails du prompt",
        "parameter_adjustments": {
            "generator.temperature": {"action": "decrease", "suggested_value": 0.2},
            "generator.max_tokens": {"action": "decrease", "suggested_value": 1024},
            "generator.system_prompt": {
                "action": "append",
                "suggested_value": (
                    "RÈGLE ABSOLUE: Tu ne dois JAMAIS inventer de texte de loi, d'article, "
                    "de date ou de référence. Si tu n'as pas l'information exacte dans le contexte, "
                    "réponds 'Je n'ai pas cette information dans les documents fournis.'"
                ),
            },
        },
    },
}


class RecommendationEngine:
    """Generates recommendations based on diagnostic results."""

    def __init__(self, diagnostic_engine: DiagnosticEngine | None = None):
        """
        Initialize the recommendation engine.

        Args:
            diagnostic_engine: DiagnosticEngine instance (creates one if None)
        """
        self.diagnostic_engine = diagnostic_engine or DiagnosticEngine()

    def generate_recommendations(
        self,
        summary: EvaluationSummary,
        store_in_db: bool = True,
    ) -> list[RecommendationSchema]:
        """
        Generate recommendations based on evaluation summary.

        Args:
            summary: Evaluation summary with metrics
            store_in_db: Whether to store recommendations in database

        Returns:
            List of recommendations
        """
        # Run diagnostic
        issues = self.diagnostic_engine.diagnose(summary)

        if not issues:
            logger.info("No issues found, no recommendations to generate")
            return []

        # Generate recommendations for each issue
        recommendations: list[RecommendationSchema] = []

        for issue in issues:
            recommendation = self._issue_to_recommendation(issue)
            recommendations.append(recommendation)

        # Store in database if requested
        if store_in_db:
            self._store_recommendations(summary.evaluation_id, recommendations)

        logger.info(
            "Generated recommendations",
            count=len(recommendations),
            critical_count=len([r for r in recommendations if r.priority == "critical"]),
        )

        return recommendations

    def _issue_to_recommendation(self, issue: DiagnosedIssue) -> RecommendationSchema:
        """Convert a diagnosed issue to a recommendation."""
        # Get rule-based recommendation
        rule_key = self._get_rule_key(issue.metric_name, issue.threshold, issue.metric_value)
        rule = RECOMMENDATION_RULES.get(rule_key, {})

        # Build suggestion text
        suggestion = rule.get("suggestion", f"Investiguer le problème de {issue.metric_name}")

        # Add probable causes to the issue description
        causes_text = "\n".join(f"  - {cause}" for cause in issue.probable_causes[:3])
        full_issue = f"{issue.symptom}\n\nCauses probables:\n{causes_text}"

        return RecommendationSchema(
            component=issue.component.value,
            issue=full_issue,
            suggestion=suggestion,
            priority=issue.severity.value,
            parameter_adjustments=rule.get("parameter_adjustments"),
        )

    def _get_rule_key(
        self, metric_name: str, threshold: float, value: float
    ) -> str:
        """Determine the rule key based on metric and comparison."""
        if metric_name == "hallucination_rate":
            return "high_hallucination_rate" if value > threshold else ""
        else:
            return f"low_{metric_name}" if value < threshold else ""

    def _store_recommendations(
        self,
        evaluation_id: str,
        recommendations: list[RecommendationSchema],
    ) -> None:
        """Store recommendations in the database."""
        with get_session() as session:
            for rec in recommendations:
                db_rec = Recommendation(
                    evaluation_id=evaluation_id,
                    component=rec.component,
                    issue=rec.issue,
                    suggestion=rec.suggestion,
                    priority=rec.priority,
                    parameter_adjustments=rec.parameter_adjustments,
                )
                session.add(db_rec)

    def export_to_yaml(
        self,
        summary: EvaluationSummary,
        recommendations: list[RecommendationSchema],
        output_path: Path | None = None,
    ) -> Path:
        """
        Export recommendations to a YAML file.

        Args:
            summary: Evaluation summary
            recommendations: List of recommendations
            output_path: Output file path (uses settings default if None)

        Returns:
            Path to the generated YAML file
        """
        output_path = output_path or settings.recommendations_file

        # Build YAML structure
        data = {
            "evaluation_id": summary.evaluation_id,
            "evaluation_date": summary.evaluation_date.isoformat(),
            "overall_score": round(summary.overall_score, 3),
            "quality_level": summary.quality_level,
            "scores": {
                "retrieval": round(summary.retrieval_score, 3),
                "generation": round(summary.generation_score, 3),
            },
            "metrics": {
                "avg_context_precision": self._safe_round(summary.metrics.avg_context_precision),
                "avg_context_relevancy": self._safe_round(summary.metrics.avg_context_relevancy),
                "avg_faithfulness": self._safe_round(summary.metrics.avg_faithfulness),
                "avg_answer_relevancy": self._safe_round(summary.metrics.avg_answer_relevancy),
                "hallucination_rate": self._safe_round(summary.metrics.hallucination_rate),
                "total_hallucinations": summary.metrics.total_hallucinations,
            },
            "recommendations": [
                {
                    "component": rec.component,
                    "priority": rec.priority,
                    "issue": rec.issue,
                    "suggestion": rec.suggestion,
                    "parameter_adjustments": rec.parameter_adjustments,
                }
                for rec in recommendations
            ],
        }

        # Ensure parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write YAML
        with output_path.open("w", encoding="utf-8") as f:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )

        logger.info("Exported recommendations to YAML", path=str(output_path))
        return output_path

    def _safe_round(self, value: float | None, decimals: int = 3) -> float | None:
        """Safely round a value that might be None."""
        return round(value, decimals) if value is not None else None
