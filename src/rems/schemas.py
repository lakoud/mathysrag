"""Pydantic schemas for data validation and transfer."""

from datetime import datetime

from pydantic import BaseModel, Field, AliasChoices


class JuridicalHallucinationAnalysis(BaseModel):
    reference_check: str = Field(description="explication claire (articles présents ou absents)")
    semantic_check: str = Field(description="explication des éventuels contresens")

class JuridicalHallucinationOutput(BaseModel):
    """Schema forcing valid JSON output from the Hallucination Evaluation."""
    juridical_hallucination: bool
    fabricated_articles: list[str] = Field(default_factory=list)
    detected_references: list[str] = Field(default_factory=list)
    hallucination_type: list[str] = Field(default_factory=list, description="List of hallucination types like 'reference_fabrication', 'semantic_hallucination'")
    analysis: JuridicalHallucinationAnalysis
    confidence_score: float = Field(ge=0.0, le=1.0)


class DocumentSchema(BaseModel):
    """Schema for a retrieved document."""

    content: str
    source: str | None = Field(default=None, validation_alias=AliasChoices('source', 'reference'))
    rank: int | None = None
    score: float | None = None
    metadata: dict | None = None


class InteractionSchema(BaseModel):
    """Schema for a chatbot interaction."""

    id: str | None = None
    query: str
    response: str
    retrieved_documents: list[DocumentSchema] = Field(default_factory=list)
    session_id: str | None = None
    user_id: str | None = None
    metadata: dict | None = None
    created_at: datetime | None = None


class EvaluationResultSchema(BaseModel):
    """Schema for evaluation results of a single interaction."""

    interaction_id: str
    faithfulness: float | None = None
    answer_relevancy: float | None = None
    context_precision: float | None = None
    context_relevancy: float | None = None
    has_hallucination: bool | None = None
    hallucination_details: dict | None = None
    overall_score: float | None = None
    details: dict | None = None


class EvaluationMetrics(BaseModel):
    """Aggregate metrics for an evaluation run."""

    # Retrieval metrics
    avg_context_precision: float | None = None
    avg_context_relevancy: float | None = None

    # Generation metrics
    avg_faithfulness: float | None = None
    avg_answer_relevancy: float | None = None

    # Hallucination stats
    hallucination_rate: float | None = None
    total_hallucinations: int = 0

    # Score distributions
    score_distribution: dict[str, int] | None = None


class RecommendationSchema(BaseModel):
    """Schema for a recommendation."""

    component: str  # retriever, generator
    issue: str
    suggestion: str
    priority: str  # critical, high, medium, low
    parameter_adjustments: dict | None = None


class EvaluationSummary(BaseModel):
    """Summary of an evaluation run."""

    evaluation_id: str
    evaluation_date: datetime
    interaction_count: int
    overall_score: float
    retrieval_score: float
    generation_score: float
    metrics: EvaluationMetrics
    recommendations: list[RecommendationSchema]
    quality_level: str  # excellent, good, acceptable, poor, critical


class DiagnosticIssueResponse(BaseModel):
    """Serialisable response for a single diagnosed issue."""

    evaluation_id: str
    evaluation_date: datetime
    component: str          # retriever, generator, indexing
    symptom: str
    severity: str           # critical, high, medium, low
    metric_name: str
    metric_value: float
    threshold: float
    probable_causes: list[str]


class RecommendationResponse(BaseModel):
    """Serialisable response for a persisted recommendation row."""

    id: str
    evaluation_id: str
    created_at: datetime
    component: str
    issue: str
    suggestion: str
    priority: str           # critical, high, medium, low
    parameter_adjustments: dict | None = None
