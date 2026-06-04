"""Juridical Hallucination Evaluator - Detects legal hallucinations in RAG responses."""

import structlog
from typing import Dict

from langchain_core.prompts import ChatPromptTemplate
from pydantic import ValidationError

from rems.evaluators.base import BaseEvaluator
from rems.schemas import EvaluationResultSchema, InteractionSchema, JuridicalHallucinationOutput
from rems.evaluators.lcbft_prompts import SYSTEM_PROMPT_EVALUATOR_LCBFT

logger = structlog.get_logger()


class JuridicalHallucinationEvaluator(BaseEvaluator):
    """Evaluator specifically designed for deep legal hallucination detection."""

    name: str = "juridical_hallucination"

    def __init__(self, llm=None, embeddings=None):
        """
        Initialize with LLM.
        
        Args:
            llm: Langchain LLM to use
            embeddings: Langchain embeddings (not strictly required here)
        """
        self.llm = llm
        
        # We need an LLM that supports structured output (e.g. ChatOpenAI, ChatAnthropic, ChatGoogleGenerativeAI)
        if self.llm and hasattr(self.llm, "with_structured_output"):
            self.structured_llm = self.llm.with_structured_output(JuridicalHallucinationOutput)
        else:
            self.structured_llm = None
            logger.warning("Agent LLM does not support `with_structured_output`, falling back to unstructured (not recommended for strict JSON).")

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT_EVALUATOR_LCBFT),
            ("user", "Contexte (documents RAG) :\n{context}\n\nRéponse générée :\n{answer}")
        ])

    def evaluate(self, interactions: list[InteractionSchema]) -> Dict[str, EvaluationResultSchema]:
        """Evaluate generation metrics for interactions to find juridical hallucinations."""
        if not interactions:
            return {}

        if not self.structured_llm:
            logger.warning("No structured LLM provided, skipping JuridicalHallucinationEvaluator")
            return {
                self._get_interaction_id(i, idx): EvaluationResultSchema(
                    interaction_id=self._get_interaction_id(i, idx)
                )
                for idx, i in enumerate(interactions)
            }

        logger.info("Running juridical hallucination evaluation", interaction_count=len(interactions))
        eval_results: Dict[str, EvaluationResultSchema] = {}

        chain = self.prompt | self.structured_llm

        for idx, interaction in enumerate(interactions):
            interaction_id = self._get_interaction_id(interaction, idx)
            
            context = "\n---\n".join([doc.content for doc in interaction.retrieved_documents]) if interaction.retrieved_documents else "Aucun contexte fourni."
            answer = interaction.response
            
            try:
                # Execution
                result: JuridicalHallucinationOutput = chain.invoke({
                    "context": context,
                    "answer": answer
                })
                
                hallucination_detected = result.juridical_hallucination
                details = result.model_dump()
                
            except Exception as e:
                logger.error("Error during juridical hallucination evaluation", interaction_id=interaction_id, error=str(e))
                hallucination_detected = False  # default
                details = {"error": str(e), "status": "failed"}

            eval_results[interaction_id] = EvaluationResultSchema(
                interaction_id=interaction_id,
                has_hallucination=hallucination_detected,
                hallucination_details=details,
                details={
                    "evaluator": self.name,
                    "metrics": {
                        "juridical_hallucination": hallucination_detected
                    }
                }
            )

        return eval_results
