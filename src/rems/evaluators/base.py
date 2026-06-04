"""Base evaluator class."""

import math
from abc import ABC, abstractmethod
from typing import Any

import structlog

from rems.schemas import EvaluationResultSchema, InteractionSchema

logger = structlog.get_logger()


class BaseEvaluator(ABC):
    """Abstract base class for all evaluators."""

    name: str = "base"

    @abstractmethod
    def evaluate(
        self, interactions: list[InteractionSchema]
    ) -> dict[str, EvaluationResultSchema]:
        """
        Evaluate a list of interactions.

        Args:
            interactions: List of interactions to evaluate

        Returns:
            Dictionary mapping interaction IDs to their evaluation results
        """
        pass

    def _get_interaction_id(self, interaction: InteractionSchema, index: int) -> str:
        """Get or generate an ID for an interaction."""
        return interaction.id or f"interaction_{index}"

    @staticmethod
    def _sanitize_float(value: float | None) -> float | None:
        """Replace NaN / Inf with None to keep JSON valid for PostgreSQL."""
        if value is None:
            return None
        try:
            return None if (math.isnan(value) or math.isinf(value)) else value
        except (TypeError, ValueError):
            return None

    def _sanitize_dict(self, data: Any) -> Any:
        """Recursively replace NaN floats in dicts/lists so the data is JSON-safe."""
        if isinstance(data, dict):
            return {k: self._sanitize_dict(v) for k, v in data.items()}
        if isinstance(data, list):
            return [self._sanitize_dict(v) for v in data]
        if isinstance(data, float):
            return self._sanitize_float(data)
        return data
