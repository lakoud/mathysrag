"""Evaluation Orchestrator - Coordinates all evaluators and aggregates results."""

import math
from datetime import datetime, timezone
from uuid import uuid4

import structlog

from rems.config import settings
from rems.evaluators.generator_evaluator import GeneratorEvaluator
from rems.evaluators.retrieval_evaluator import RetrievalEvaluator
from rems.evaluators.juridical_hallucination_evaluator import JuridicalHallucinationEvaluator
from rems.models import Evaluation, EvaluationResult, get_session
from rems.schemas import (
    EvaluationMetrics,
    EvaluationResultSchema,
    EvaluationSummary,
    InteractionSchema,
    RecommendationSchema,
)

logger = structlog.get_logger()

# Component weights for overall score calculation
RETRIEVAL_WEIGHT = 0.35
GENERATION_WEIGHT = 0.65


class EvaluationOrchestrator:
    """Orchestrates the evaluation process across all evaluators."""

    def __init__(self, llm=None, embeddings=None):
        """
        Initialize the orchestrator with evaluators.

        Args:
            llm: Modern Ragas LLM (InstructorLLM)
            embeddings: Modern Ragas Embeddings (BaseRagasEmbedding)
        """
        self.retrieval_evaluator = RetrievalEvaluator(llm=llm, embeddings=embeddings)
        self.generator_evaluator = GeneratorEvaluator(llm=llm, embeddings=embeddings)
        self.hallucination_evaluator = JuridicalHallucinationEvaluator(llm=llm)

    def evaluate(
        self,
        interactions: list[InteractionSchema],
        name: str | None = None,
        description: str | None = None,
        store_results: bool = True,
        evaluation_id: str | None = None,
    ) -> EvaluationSummary:
        """
        Run a complete evaluation on a list of interactions.

        Args:
            interactions: List of interactions to evaluate
            name: Optional name for this evaluation run
            description: Optional description
            store_results: Whether to store results in database

        Returns:
            EvaluationSummary with all metrics and recommendations
        """
        logger.info(
            "Starting evaluation",
            interaction_count=len(interactions),
            name=name,
        )

        # Run evaluators
        retrieval_results = self.retrieval_evaluator.evaluate(interactions)
        generator_results = self.generator_evaluator.evaluate(interactions)
        hallucination_results = self.hallucination_evaluator.evaluate(interactions)

        # Merge results
        merged_results = self._merge_results(retrieval_results, generator_results, hallucination_results)

        # Calculate aggregate metrics
        metrics = self._calculate_metrics(merged_results)

        # Calculate component and overall scores
        retrieval_score = self._calculate_retrieval_score(metrics)
        generation_score = self._calculate_generation_score(metrics)
        overall_score = (
            retrieval_score * RETRIEVAL_WEIGHT +
            generation_score * GENERATION_WEIGHT
        )

        # Determine quality level
        quality_level = self._get_quality_level(overall_score)

        # Store results if requested
        if store_results:
            evaluation_id = self._store_results(
                interactions=interactions,
                results=merged_results,
                metrics=metrics,
                overall_score=overall_score,
                retrieval_score=retrieval_score,
                generation_score=generation_score,
                name=name,
                description=description,
                evaluation_id=evaluation_id,
            )
        else:
            if not evaluation_id:
                evaluation_id = str(uuid4())

        # Create summary (recommendations will be added by RecommendationEngine)
        summary = EvaluationSummary(
            evaluation_id=evaluation_id,
            evaluation_date=datetime.now(timezone.utc),
            interaction_count=len(interactions),
            overall_score=overall_score,
            retrieval_score=retrieval_score,
            generation_score=generation_score,
            metrics=metrics,
            recommendations=[],  # Filled by RecommendationEngine
            quality_level=quality_level,
        )

        logger.info(
            "Evaluation complete",
            evaluation_id=evaluation_id,
            overall_score=overall_score,
            quality_level=quality_level,
        )

        return summary

    def _merge_results(
        self,
        retrieval_results: dict[str, EvaluationResultSchema],
        generator_results: dict[str, EvaluationResultSchema],
        hallucination_results: dict[str, EvaluationResultSchema] = None,
    ) -> dict[str, EvaluationResultSchema]:
        """Merge results from all evaluators."""
        merged: dict[str, EvaluationResultSchema] = {}

        all_ids = set(retrieval_results.keys()) | set(generator_results.keys())
        if hallucination_results:
            all_ids |= set(hallucination_results.keys())

        for interaction_id in all_ids:
            retrieval = retrieval_results.get(interaction_id)
            generator = generator_results.get(interaction_id)
            hallucination = hallucination_results.get(interaction_id) if hallucination_results else None

            # Start with generator results if available (has more fields)
            if generator:
                result = generator.model_copy()
            else:
                result = EvaluationResultSchema(interaction_id=interaction_id)

            # Add retrieval metrics
            if retrieval:
                result.context_precision = retrieval.context_precision
                result.context_relevancy = retrieval.context_relevancy

            # Add hallucination metrics
            if hallucination:
                result.has_hallucination = hallucination.has_hallucination
                result.hallucination_details = hallucination.hallucination_details

            # Recalculate overall score with all metrics
            scores = [
                s for s in [
                    result.faithfulness,
                    result.answer_relevancy,
                    result.context_precision,
                    result.context_relevancy,
                ] if s is not None
            ]
            if scores:
                result.overall_score = sum(scores) / len(scores)

            merged[interaction_id] = result

        return merged

    def _calculate_metrics(
        self, results: dict[str, EvaluationResultSchema]
    ) -> EvaluationMetrics:
        """Calculate aggregate metrics from individual results."""
        if not results:
            return EvaluationMetrics()

        values = list(results.values())

        # Calculate averages
        context_precisions = [r.context_precision for r in values if r.context_precision is not None]
        context_relevancies = [r.context_relevancy for r in values if r.context_relevancy is not None]
        faithfulness_scores = [r.faithfulness for r in values if r.faithfulness is not None]
        answer_relevancies = [r.answer_relevancy for r in values if r.answer_relevancy is not None]

        # Hallucination stats
        hallucinations = [r for r in values if r.has_hallucination]
        total_hallucinations = len(hallucinations)
        hallucination_rate = total_hallucinations / len(values) if values else 0

        # Score distribution
        overall_scores = [r.overall_score for r in values if r.overall_score is not None]
        distribution = {
            "excellent": len([s for s in overall_scores if s >= settings.threshold_excellent]),
            "good": len([s for s in overall_scores if settings.threshold_good <= s < settings.threshold_excellent]),
            "acceptable": len([s for s in overall_scores if settings.threshold_acceptable <= s < settings.threshold_good]),
            "poor": len([s for s in overall_scores if settings.threshold_poor <= s < settings.threshold_acceptable]),
            "critical": len([s for s in overall_scores if s < settings.threshold_poor]),
        }

        return EvaluationMetrics(
            avg_context_precision=sum(context_precisions) / len(context_precisions) if context_precisions else None,
            avg_context_relevancy=sum(context_relevancies) / len(context_relevancies) if context_relevancies else None,
            avg_faithfulness=sum(faithfulness_scores) / len(faithfulness_scores) if faithfulness_scores else None,
            avg_answer_relevancy=sum(answer_relevancies) / len(answer_relevancies) if answer_relevancies else None,
            hallucination_rate=hallucination_rate,
            total_hallucinations=total_hallucinations,
            score_distribution=distribution,
        )

    def _calculate_retrieval_score(self, metrics: EvaluationMetrics) -> float:
        """Calculate retrieval component score."""
        scores = [
            s for s in [metrics.avg_context_precision, metrics.avg_context_relevancy]
            if s is not None
        ]
        return sum(scores) / len(scores) if scores else 0.0

    def _calculate_generation_score(self, metrics: EvaluationMetrics) -> float:
        """Calculate generation component score."""
        scores = [
            s for s in [metrics.avg_faithfulness, metrics.avg_answer_relevancy]
            if s is not None
        ]
        return sum(scores) / len(scores) if scores else 0.0

    def _get_quality_level(self, score: float) -> str:
        """Determine quality level from overall score."""
        if score >= settings.threshold_excellent:
            return "excellent"
        elif score >= settings.threshold_good:
            return "good"
        elif score >= settings.threshold_acceptable:
            return "acceptable"
        elif score >= settings.threshold_poor:
            return "poor"
        else:
            return "critical"

    @staticmethod
    def _sanitize_score(value: float | None) -> float | None:
        """Replace NaN with None so PostgreSQL JSON does not reject the value."""
        if value is None:
            return None
        return None if math.isnan(value) else value

    def _sanitize_metrics(self, metrics: EvaluationMetrics) -> dict:
        """Return a metrics dict with NaN values replaced by None."""
        raw = metrics.model_dump()
        return {
            k: (self._sanitize_score(v) if isinstance(v, float) else v)
            for k, v in raw.items()
        }

    def _store_results(
        self,
        interactions: list[InteractionSchema],
        results: dict[str, EvaluationResultSchema],
        metrics: EvaluationMetrics,
        overall_score: float,
        retrieval_score: float,
        generation_score: float,
        name: str | None,
        description: str | None,
        evaluation_id: str | None = None,
    ) -> str:
        """Store evaluation results in the database."""
        from rems.models.database import Interaction as InteractionModel
        from sqlalchemy import select

        with get_session() as session:
<<<<<<< HEAD
            # Create evaluation record — sanitize NaN so PostgreSQL JSON accepts it
            try :
                    
                    evaluation = Evaluation(
                        name=name,
                        description=description,
                        interaction_count=len(interactions),
                        overall_score=self._sanitize_score(overall_score),
                        retrieval_score=self._sanitize_score(retrieval_score),
                        generation_score=self._sanitize_score(generation_score),
                        metrics=self._sanitize_metrics(metrics),
                        completed_at=datetime.now(timezone.utc),
            )
                    session.add(evaluation)
                    session.flush() 
                    print(f"Contenue: {evaluation.metrics}")

            except Exception as e:

                logger.error("Error occurred while storing evaluation results", exc_info=True)
                print(f"Error details: {e}")
            # Collect all interaction IDs from the results
            result_ids = list(results.keys())

            # Check which interaction IDs actually exist in the DB
            if result_ids:
                existing_rows = session.execute(
                    select(InteractionModel.id).where(
                        InteractionModel.id.in_(result_ids)
=======
            if evaluation_id:
                evaluation = session.query(Evaluation).filter(Evaluation.id == evaluation_id).first()
            else:
                evaluation = None
                
            if evaluation:
                evaluation.name = name
                evaluation.description = description
                evaluation.interaction_count = len(interactions)
                evaluation.overall_score = self._sanitize_score(overall_score)
                evaluation.retrieval_score = self._sanitize_score(retrieval_score)
                evaluation.generation_score = self._sanitize_score(generation_score)
                evaluation.metrics = self._sanitize_metrics(metrics)
                evaluation.completed_at = datetime.now(timezone.utc)
            else:
                # Create evaluation record — sanitize NaN so PostgreSQL JSON accepts it
                evaluation = Evaluation(
                    id=evaluation_id if evaluation_id else str(uuid4()),
                    name=name,
                    description=description,
                    interaction_count=len(interactions),
                    overall_score=self._sanitize_score(overall_score),
                    retrieval_score=self._sanitize_score(retrieval_score),
                    generation_score=self._sanitize_score(generation_score),
                    metrics=self._sanitize_metrics(metrics),
                    completed_at=datetime.now(timezone.utc),
                )
                session.add(evaluation)
                
            session.flush()

            # Collect all interaction IDs from the results
            result_ids = list(results.keys())

            # Filter valid UUID strings
            import uuid
            valid_uuid_strs = []
            for r_id in result_ids:
                try:
                    uuid.UUID(str(r_id))
                    valid_uuid_strs.append(r_id)
                except ValueError:
                    pass

            # Check which interaction IDs actually exist in the DB
            if valid_uuid_strs:
                existing_rows = session.execute(
                    select(InteractionModel.id).where(
                        InteractionModel.id.in_(valid_uuid_strs)
>>>>>>> 6b10b543ba67f8dd50dd88634c0095970aa0719d
                    )
                ).fetchall()
                existing_ids = {row[0] for row in existing_rows}
            else:
                existing_ids = set()

            skipped = 0
            for interaction_id, result in results.items():
                # Skip if this interaction was not stored in DB (e.g. from file upload)
                if interaction_id not in existing_ids:
                    skipped += 1
                    continue

                eval_result = EvaluationResult(
                    evaluation_id=evaluation.id,
                    interaction_id=interaction_id,
                    faithfulness=self._sanitize_score(result.faithfulness),
                    answer_relevancy=self._sanitize_score(result.answer_relevancy),
                    context_precision=self._sanitize_score(result.context_precision),
                    context_relevancy=self._sanitize_score(result.context_relevancy),
                    has_hallucination=result.has_hallucination,
                    hallucination_details=result.hallucination_details,
                    overall_score=self._sanitize_score(result.overall_score),
                    details=result.details,
                )
                session.add(eval_result)

            if skipped:
                logger.info(
                    "Skipped per-interaction results (interactions not in DB)",
                    skipped=skipped,
                    tip="Upload-mode evaluations only store the aggregate Evaluation record.",
                )

<<<<<<< HEAD
            return evaluation.id
=======
            return evaluation.id
>>>>>>> 6b10b543ba67f8dd50dd88634c0095970aa0719d
