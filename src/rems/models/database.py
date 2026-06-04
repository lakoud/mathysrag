"""SQLAlchemy database models for REMS."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class Interaction(Base):
    """Represents a single chatbot interaction (query + response)."""

    __tablename__ = "interactions"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Core interaction data
    query: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[str] = mapped_column(Text, nullable=False)

    # Optional metadata
    session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    # Relationships
    retrieved_documents: Mapped[list["RetrievedDocument"]] = relationship(
        back_populates="interaction", cascade="all, delete-orphan"
    )
    evaluation_results: Mapped[list["EvaluationResult"]] = relationship(
        back_populates="interaction", cascade="all, delete-orphan"
    )


class RetrievedDocument(Base):
    """Documents retrieved by the RAG system for an interaction."""

    __tablename__ = "retrieved_documents"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    interaction_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("interactions.id", ondelete="CASCADE")
    )

    # Document content
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(String(500), nullable=True)
    rank: Mapped[int | None] = mapped_column(nullable=True)

    # Optional retrieval metadata
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    # Relationships
    interaction: Mapped["Interaction"] = relationship(back_populates="retrieved_documents")


class Evaluation(Base):
    """Represents a batch evaluation run."""

    __tablename__ = "evaluations"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Evaluation metadata
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    interaction_count: Mapped[int] = mapped_column(default=0)

    # Aggregate scores
    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    retrieval_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    generation_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Detailed metrics (JSON blob for flexibility)
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    results: Mapped[list["EvaluationResult"]] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan"
    )
    recommendations: Mapped[list["Recommendation"]] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan"
    )


class EvaluationResult(Base):
    """Evaluation results for a single interaction."""

    __tablename__ = "evaluation_results"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    evaluation_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("evaluations.id", ondelete="CASCADE")
    )
    interaction_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("interactions.id", ondelete="CASCADE")
    )

    # Individual metrics
    faithfulness: Mapped[float | None] = mapped_column(Float, nullable=True)
    answer_relevancy: Mapped[float | None] = mapped_column(Float, nullable=True)
    context_precision: Mapped[float | None] = mapped_column(Float, nullable=True)
    context_relevancy: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Hallucination detection
    has_hallucination: Mapped[bool | None] = mapped_column(nullable=True)
    hallucination_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Overall score for this interaction
    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Additional details
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    evaluation: Mapped["Evaluation"] = relationship(back_populates="results")
    interaction: Mapped["Interaction"] = relationship(back_populates="evaluation_results")


class Recommendation(Base):
    """Recommendations generated from an evaluation."""

    __tablename__ = "recommendations"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    evaluation_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("evaluations.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Recommendation details
    component: Mapped[str] = mapped_column(String(50), nullable=False)  # retriever, generator
    issue: Mapped[str] = mapped_column(Text, nullable=False)
    suggestion: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False)  # critical, high, medium, low

    # Optional: specific parameter adjustments
    parameter_adjustments: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    evaluation: Mapped["Evaluation"] = relationship(back_populates="recommendations")
