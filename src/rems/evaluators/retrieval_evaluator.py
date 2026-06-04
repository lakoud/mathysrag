"""Retrieval Evaluator - Evaluates the quality of document retrieval."""

import structlog
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import ContextPrecision, ContextRelevance
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper

from rems.evaluators.base import BaseEvaluator
from rems.schemas import EvaluationResultSchema, InteractionSchema

logger = structlog.get_logger()


class RetrievalEvaluator(BaseEvaluator):
    """Evaluator for retrieval performance (Context Precision, Context Relevancy)."""

    name: str = "retrieval"

    def __init__(self, llm=None, embeddings=None):
        """
        Initialize with LLM and embeddings.

        Args:
            llm: LangChain LLM instance
            embeddings: LangChain embeddings instance
        """
        self.llm = llm
        self.embeddings = embeddings

    def evaluate(
        self, interactions: list[InteractionSchema]
    ) -> dict[str, EvaluationResultSchema]:
        """Evaluate retrieval metrics for interactions."""
        if not interactions:
            return {}

        logger.info("Running retrieval evaluation", interaction_count=len(interactions))

        # Prepare dataset for Ragas (robust names for both legacy and modern metrics)
        data = {
            "question": [i.query for i in interactions],
            "user_input": [i.query for i in interactions],
            "contexts": [
                [doc.content for doc in i.retrieved_documents]
                if i.retrieved_documents
                else []
                for i in interactions
            ],
            "retrieved_contexts": [
                [doc.content for doc in i.retrieved_documents]
                if i.retrieved_documents
                else []
                for i in interactions
            ],
            "ground_truth": [getattr(i, "reference", i.response) or "" for i in interactions],
            "reference": [getattr(i, "reference", i.response) or "" for i in interactions],
        }
        dataset = Dataset.from_dict(data)

        # Wrap for legacy metrics
        ragas_llm = LangchainLLMWrapper(self.llm) if self.llm else None
        ragas_emb = LangchainEmbeddingsWrapper(self.embeddings) if self.embeddings else None

        # Initialize legacy metrics
        metrics = []
        if ragas_llm:
            context_precision = ContextPrecision(llm=ragas_llm)
            context_relevance = ContextRelevance(llm=ragas_llm)
            
            # Application des prompts personnalisés pour le domaine juridique FR
            from rems.evaluators.prompts_fr import FRENCH_PROMPTS
            
            # Context Precision
            cp_prompts = FRENCH_PROMPTS.get("context_precision", {})
            if "context_precision_prompt" in cp_prompts:
                context_precision.context_precision_prompt = cp_prompts["context_precision_prompt"]
            
            # Context Relevance (templates NV)
            cr_prompts = FRENCH_PROMPTS.get("context_relevance", {})
            if "template_relevance1" in cr_prompts:
                context_relevance.template_relevance1 = cr_prompts["template_relevance1"]
            if "template_relevance2" in cr_prompts:
                context_relevance.template_relevance2 = cr_prompts["template_relevance2"]
                
            metrics.append(context_precision)
            metrics.append(context_relevance)

        if not metrics:
            logger.warning("No LLM provided for retrieval evaluation, skipping")
            return {
                self._get_interaction_id(i, idx): EvaluationResultSchema(
                    interaction_id=self._get_interaction_id(i, idx)
                )
                for idx, i in enumerate(interactions)
            }

        # Run evaluation
        results = evaluate(dataset=dataset, metrics=metrics)
        df = results.to_pandas()
        
        # Log columns for debugging if metrics are missing
        logger.debug("Retrieval Ragas columns", columns=df.columns.tolist())

        # Map results back to interactions
        eval_results: dict[str, EvaluationResultSchema] = {}
        for idx, interaction in enumerate(interactions):
            interaction_id = self._get_interaction_id(interaction, idx)
            row = df.iloc[idx]

            # Try common variations of metric names in result columns
            precision_score = self._sanitize_float(
                row.get("context_precision") or row.get("context_precision_score")
            )
            relevancy_score = self._sanitize_float(
                row.get("context_relevance") or 
                row.get("context_relevancy") or 
                row.get("context_relevance_score") or
                row.get("nv_context_relevance")
            )

            eval_results[interaction_id] = EvaluationResultSchema(
                interaction_id=interaction_id,
                context_precision=precision_score,
                context_relevancy=relevancy_score,
                details=self._sanitize_dict({
                    "evaluator": self.name,
                    "metrics": {
                        "context_precision": precision_score,
                        "context_relevancy": relevancy_score,
                    },
                }),
            )

        logger.info(
            "Retrieval evaluation complete",
            evaluated_count=len(interactions),
            avg_precision=self._sanitize_float(row.get("context_precision")),
        )

        return eval_results