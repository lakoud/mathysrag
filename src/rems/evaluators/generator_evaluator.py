"""Generator Evaluator - Evaluates the quality of LLM responses."""

import structlog
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import AnswerRelevancy, Faithfulness
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper

from rems.evaluators.base import BaseEvaluator
from rems.schemas import EvaluationResultSchema, InteractionSchema

logger = structlog.get_logger()


class GeneratorEvaluator(BaseEvaluator):
    """Evaluator for response generation performance (Faithfulness, Answer Relevancy)."""

    name: str = "generator"

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
        """Evaluate generation metrics for interactions."""
        if not interactions:
            return {}

        logger.info("Running generator evaluation", interaction_count=len(interactions))

        # Prepare dataset for Ragas (robust names for both legacy and modern metrics)
        data = {
            "question": [i.query for i in interactions],
            "user_input": [i.query for i in interactions],
            "answer": [i.response for i in interactions],
            "response": [i.response for i in interactions],
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
            faithfulness = Faithfulness(llm=ragas_llm)
            answer_relevancy = AnswerRelevancy(llm=ragas_llm, embeddings=ragas_emb) if ragas_emb else None
            
            # Application des prompts personnalisés pour le domaine juridique FR
            from rems.evaluators.prompts_fr import FRENCH_PROMPTS
            
            # Faithfulness
            faith_prompts = FRENCH_PROMPTS.get("faithfulness", {})
            if "nli_statements_prompt" in faith_prompts:
                faithfulness.nli_statements_prompt = faith_prompts["nli_statements_prompt"]
            if "statement_generator_prompt" in faith_prompts:
                faithfulness.statement_generator_prompt = faith_prompts["statement_generator_prompt"]
            
            metrics.append(faithfulness)
            
            # Answer Relevancy
            if answer_relevancy:
                rel_prompts = FRENCH_PROMPTS.get("answer_relevancy", {})
                if "response_relevance_prompt" in rel_prompts:
                    answer_relevancy.response_relevance_prompt = rel_prompts["response_relevance_prompt"]
                metrics.append(answer_relevancy)

        if not metrics:
            logger.warning("No LLM provided for generator evaluation, skipping")
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
        logger.debug("Generator Ragas columns", columns=df.columns.tolist())

        # Map results back to interactions
        eval_results: dict[str, EvaluationResultSchema] = {}
        for idx, interaction in enumerate(interactions):
            interaction_id = self._get_interaction_id(interaction, idx)
            row = df.iloc[idx]

            faithfulness = self._sanitize_float(
                row.get("faithfulness") or row.get("faithfulness_score")
            )
            # Legacy column names
            answer_relevancy = self._sanitize_float(
                row.get("answer_relevancy") or row.get("answer_relevance") or row.get("answer_relevancy_score")
            )

            # Simple hallucination check
            has_hallucination = False
            if faithfulness is not None and faithfulness < 0.5:
                has_hallucination = True

            eval_results[interaction_id] = EvaluationResultSchema(
                interaction_id=interaction_id,
                faithfulness=faithfulness,
                answer_relevancy=answer_relevancy,
                has_hallucination=has_hallucination,
                details=self._sanitize_dict({
                    "evaluator": self.name,
                    "metrics": {
                        "faithfulness": faithfulness,
                        "answer_relevancy": answer_relevancy,
                    },
                }),
            )

        logger.info(
            "Generator evaluation complete",
            evaluated_count=len(interactions),
            avg_faithfulness=self._sanitize_float(row.get("faithfulness")),
        )

        return eval_results
