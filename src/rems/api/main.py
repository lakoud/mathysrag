"""FastAPI application for REMS."""

from contextlib import asynccontextmanager
from typing import List, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

import structlog

from rems.collector import APICollector
from rems.cli import setup_llm
from rems.diagnostic import DiagnosticEngine
from rems.evaluators import EvaluationOrchestrator
from rems.recommendations import RecommendationEngine
from rems.reports import ReportGenerator
from rems.schemas import (
    DiagnosticIssueResponse,
    EvaluationMetrics,
    EvaluationSummary,
    InteractionSchema,
    RecommendationResponse,
    RecommendationSchema,
)
from rems.models import get_session, Evaluation
from rems.models.database import Recommendation

logger = structlog.get_logger()

# Request Models
class CollectRequest(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    limit: Optional[int] = None
    store: bool = True
    interactions: Optional[List[InteractionSchema]] = None

class EvaluateRequest(BaseModel):
    name: Optional[str] = None
    limit: Optional[int] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    store_results: bool = True
    interactions: Optional[List[InteractionSchema]] = None

class EvaluateResponse(BaseModel):
    evaluation_id: str
    status: str
    message: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting REMS API")
    yield
    logger.info("Shutting down REMS API")

app = FastAPI(
    title="REMS API",
    description="REST API for RAG Evaluation & Monitoring System",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/collect", status_code=status.HTTP_201_CREATED)
def collect_interactions(request: CollectRequest):
    """Collect interactions from the chatbot API."""
    logger.info("Collecting interactions", request=request.model_dump())
    collector = APICollector()
    try:
        from datetime import datetime
        start_dt = datetime.fromisoformat(request.start_date) if request.start_date else None
        end_dt = datetime.fromisoformat(request.end_date) if request.end_date else None
        
        # Priority to provided interactions
        if request.interactions:
            logger.info("Using provided interactions from request body")
            interactions = request.interactions
        else:
            interactions = collector.fetch_interactions(
                start_date=start_dt,
                end_date=end_dt,
                limit=request.limit,
            )
        
        stored_ids = []
        documents_count = 0
        if request.store and interactions:
            # Count total documents across all interactions before storing
            for interaction in interactions:
                documents_count += len(interaction.retrieved_documents)
            
            stored_ids = collector.store_interactions(interactions)
            
        return {
            "status": "success",
            "imported": {
                "interactions_count": len(stored_ids),
                "documents_count": documents_count,
                "interaction_ids": stored_ids
            },
            "message": f"{len(stored_ids)} interactions importées avec succès"
        }
    except Exception as e:
        logger.error("Error collecting interactions", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        collector.close()


def background_evaluate(
    evaluation_id: str,
    interactions: list,
    request_name: str | None,
    store_results: bool
):
    """Background task for running evaluation."""
    logger.info("Starting background evaluation", evaluation_id=evaluation_id)
    llm, embeddings = setup_llm()
    if not llm or not embeddings:
        logger.error("LLM not configured properly. Cannot run background evaluation.")
        with get_session() as db:
            eval_db = db.query(Evaluation).filter(Evaluation.id == evaluation_id).first()
            if eval_db:
                eval_db.metrics = {"status": "failed", "error": "LLM not configured"}
                db.commit()
        return

    try:
        with get_session() as db:
            eval_db = db.query(Evaluation).filter(Evaluation.id == evaluation_id).first()
            if eval_db:
                eval_db.metrics = {"status": "running"}
                db.commit()

        orchestrator = EvaluationOrchestrator(llm=llm, embeddings=embeddings)
        summary = orchestrator.evaluate(
            interactions=interactions,
            name=request_name,
            store_results=store_results,
            evaluation_id=evaluation_id,
        )
        
        recommendation_engine = RecommendationEngine()
        recommendation_engine.generate_recommendations(
            summary,
            store_in_db=store_results,
        )
        logger.info("Background evaluation completed", evaluation_id=evaluation_id)
    except Exception as e:
        logger.error("Error running background evaluation", error=str(e))
        with get_session() as db:
            eval_db = db.query(Evaluation).filter(Evaluation.id == evaluation_id).first()
            if eval_db:
                eval_db.metrics = {"status": "failed", "error": str(e)}
                db.commit()

@app.post("/evaluate", response_model=EvaluateResponse, status_code=status.HTTP_202_ACCEPTED)
def evaluate_interactions(request: EvaluateRequest, background_tasks: BackgroundTasks):
    """Run an evaluation on collected interactions asynchronously."""
    logger.info("Scheduling background evaluation", request=request.model_dump())
    
    collector = APICollector()
    try:
        from datetime import datetime
        start_dt = datetime.fromisoformat(request.start_date) if request.start_date else None
        end_dt = datetime.fromisoformat(request.end_date) if request.end_date else None
        
        # Priority to provided interactions
        if request.interactions:
            logger.info("Using provided interactions from request body")
            interactions = request.interactions
        else:
            interactions = collector.fetch_interactions(
                start_date=start_dt,
                end_date=end_dt,
                limit=request.limit,
            )
        
        if not interactions:
            raise HTTPException(status_code=404, detail="No interactions found to evaluate")
            
        import uuid
        evaluation_id = str(uuid.uuid4())
        
        if request.store_results:
            with get_session() as db:
                from datetime import timezone
                evaluation = Evaluation(
                    id=evaluation_id,
                    name=request.name,
                    interaction_count=len(interactions),
                    completed_at=None,
                    metrics={"status": "pending"}
                )
                db.add(evaluation)
                db.commit()
                
        background_tasks.add_task(
            background_evaluate,
            evaluation_id,
            interactions,
            request.name,
            request.store_results,
        )
        
        return EvaluateResponse(
            evaluation_id=evaluation_id,
            status="accepted",
            message="Evaluation has been scheduled and is running in the background."
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error scheduling evaluation", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        collector.close()


@app.get("/evaluations/{evaluation_id}")
def get_evaluation_details(evaluation_id: str):
    """Get detailed information for a specific evaluation."""
    try:
        with get_session() as db:
            eval_db = db.query(Evaluation).filter(Evaluation.id == evaluation_id).first()
            if not eval_db:
                raise HTTPException(status_code=404, detail="Evaluation not found")
            
            # Calculate quality level
            score = eval_db.overall_score or 0.0
            if score >= 0.90:
                q_level = "excellent"
            elif score >= 0.75:
                q_level = "good"
            elif score >= 0.60:
                q_level = "acceptable"
            elif score >= 0.40:
                q_level = "poor"
            else:
                q_level = "critical"
            
            # Formulate result
            results = []
            for res in eval_db.results:
                results.append({
                    "interaction_id": res.interaction_id,
                    "query": res.interaction.query if res.interaction else None,
                    "response": res.interaction.response if res.interaction else None,
                    "faithfulness": res.faithfulness,
                    "answer_relevancy": res.answer_relevancy,
                    "context_precision": res.context_precision,
                    "context_relevancy": res.context_relevancy,
                    "has_hallucination": res.has_hallucination,
                    "overall_score": res.overall_score,
                    "details": res.details
                })
            
            recommendations = []
            for rec in eval_db.recommendations:
                recommendations.append({
                    "component": rec.component,
                    "issue": rec.issue,
                    "suggestion": rec.suggestion,
                    "priority": rec.priority,
                    "parameter_adjustments": rec.parameter_adjustments
                })
                
            return {
                "evaluation_id": eval_db.id,
                "evaluation_date": eval_db.created_at,
                "name": eval_db.name,
                "interaction_count": eval_db.interaction_count,
                "overall_score": eval_db.overall_score,
                "retrieval_score": eval_db.retrieval_score,
                "generation_score": eval_db.generation_score,
                "quality_level": q_level,
                "metrics": eval_db.metrics or {},
                "results": results,
                "recommendations": recommendations
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving evaluation details", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/evaluations")
def get_evaluations(limit: int = 10, skip: int = 0):
    """Get recent evaluation summaries."""
    try:
        with get_session() as db:
            evaluations_db = db.query(Evaluation).order_by(
                Evaluation.created_at.desc()
            ).offset(skip).limit(limit).all()
            
            # Build responses manually if schemas fail to parse ORM directly
            results = []
            for eval_db in evaluations_db:
                # Calculate quality level
                score = eval_db.overall_score or 0.0
                if score >= 0.90:
                    q_level = "excellent"
                elif score >= 0.75:
                    q_level = "good"
                elif score >= 0.60:
                    q_level = "acceptable"
                elif score >= 0.40:
                    q_level = "poor"
                else:
                    q_level = "critical"
                    
                results.append({
                    "evaluation_id": eval_db.id,
                    "evaluation_date": eval_db.created_at,
                    "interaction_count": eval_db.interaction_count,
                    "overall_score": eval_db.overall_score,
                    "retrieval_score": eval_db.retrieval_score,
                    "generation_score": eval_db.generation_score,
                    "quality_level": q_level,
                    "metrics": eval_db.metrics or {},
                    "recommendations": []  # Let's skip loading all recommendations to keep it simple, or map them if needed
                })
            return results
    except Exception as e:
        logger.error("Error retrieving evaluations", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _quality_level(score: float | None) -> str:
    """Convert an overall score to a quality-level label."""
    s = score or 0.0
    if s >= 0.90:
        return "excellent"
    if s >= 0.75:
        return "good"
    if s >= 0.60:
        return "acceptable"
    if s >= 0.40:
        return "poor"
    return "critical"


def _build_evaluation_summary(eval_db: Evaluation) -> EvaluationSummary:
    """Build an EvaluationSummary from an ORM Evaluation row."""
    raw_metrics = eval_db.metrics or {}
    metrics = EvaluationMetrics(
        avg_context_precision=raw_metrics.get("avg_context_precision"),
        avg_context_relevancy=raw_metrics.get("avg_context_relevancy"),
        avg_faithfulness=raw_metrics.get("avg_faithfulness"),
        avg_answer_relevancy=raw_metrics.get("avg_answer_relevancy"),
        hallucination_rate=raw_metrics.get("hallucination_rate"),
        total_hallucinations=raw_metrics.get("total_hallucinations", 0),
        score_distribution=raw_metrics.get("score_distribution"),
    )
    recommendations = [
        RecommendationSchema(
            component=r.component,
            issue=r.issue,
            suggestion=r.suggestion,
            priority=r.priority,
            parameter_adjustments=r.parameter_adjustments,
        )
        for r in eval_db.recommendations
    ]
    return EvaluationSummary(
        evaluation_id=eval_db.id,
        evaluation_date=eval_db.created_at,
        interaction_count=eval_db.interaction_count,
        overall_score=eval_db.overall_score or 0.0,
        retrieval_score=eval_db.retrieval_score or 0.0,
        generation_score=eval_db.generation_score or 0.0,
        metrics=metrics,
        recommendations=recommendations,
        quality_level=_quality_level(eval_db.overall_score),
    )


# ---------------------------------------------------------------------------
# GET /diagnostics
# ---------------------------------------------------------------------------

@app.get("/diagnostics", response_model=list[DiagnosticIssueResponse])
def get_diagnostics(
    severity: Optional[str] = Query(None, description="Filter by severity (critical, high, medium, low)"),
    component: Optional[str] = Query(None, description="Filter by component (retriever, generator, indexing)"),
    start_date: Optional[str] = Query(None, description="Filter evaluations created on or after this ISO-8601 date"),
    end_date: Optional[str] = Query(None, description="Filter evaluations created on or before this ISO-8601 date"),
    limit: int = Query(50, ge=1, le=500),
    skip: int = Query(0, ge=0),
):
    """Return diagnosed issues derived from stored evaluation results."""
    try:
        start_dt = datetime.fromisoformat(start_date) if start_date else None
        end_dt = datetime.fromisoformat(end_date) if end_date else None

        diagnostic_engine = DiagnosticEngine()
        issues: list[DiagnosticIssueResponse] = []

        with get_session() as db:
            query = db.query(Evaluation)
            if start_dt:
                query = query.filter(Evaluation.created_at >= start_dt)
            if end_dt:
                query = query.filter(Evaluation.created_at <= end_dt)
            evaluations = query.order_by(Evaluation.created_at.desc()).all()

            for eval_db in evaluations:
                # Only diagnose evaluations that completed successfully
                raw_metrics = eval_db.metrics or {}
                if raw_metrics.get("status") not in (None, "completed"):
                    continue
                try:
                    summary = _build_evaluation_summary(eval_db)
                    diagnosed = diagnostic_engine.diagnose(summary)
                except Exception as diag_err:
                    logger.warning(
                        "Could not diagnose evaluation",
                        evaluation_id=eval_db.id,
                        error=str(diag_err),
                    )
                    continue

                for issue in diagnosed:
                    if severity and issue.severity.value != severity:
                        continue
                    if component and issue.component.value != component:
                        continue
                    issues.append(
                        DiagnosticIssueResponse(
                            evaluation_id=eval_db.id,
                            evaluation_date=eval_db.created_at,
                            component=issue.component.value,
                            symptom=issue.symptom,
                            severity=issue.severity.value,
                            metric_name=issue.metric_name,
                            metric_value=issue.metric_value,
                            threshold=issue.threshold,
                            probable_causes=issue.probable_causes,
                        )
                    )

        # Paginate after collecting all filtered issues
        return issues[skip: skip + limit]

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving diagnostics", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# GET /recommendations
# ---------------------------------------------------------------------------

@app.get("/recommendations", response_model=list[RecommendationResponse])
def get_recommendations(
    severity: Optional[str] = Query(None, description="Filter by priority/severity (critical, high, medium, low)"),
    component: Optional[str] = Query(None, description="Filter by component (retriever, generator, indexing)"),
    start_date: Optional[str] = Query(None, description="Filter recommendations created on or after this ISO-8601 date"),
    end_date: Optional[str] = Query(None, description="Filter recommendations created on or before this ISO-8601 date"),
    evaluation_id: Optional[str] = Query(None, description="Limit results to a specific evaluation"),
    limit: int = Query(50, ge=1, le=500),
    skip: int = Query(0, ge=0),
):
    """Return persisted recommendations, optionally filtered."""
    try:
        start_dt = datetime.fromisoformat(start_date) if start_date else None
        end_dt = datetime.fromisoformat(end_date) if end_date else None

        with get_session() as db:
            query = db.query(Recommendation)
            if severity:
                query = query.filter(Recommendation.priority == severity)
            if component:
                query = query.filter(Recommendation.component == component)
            if evaluation_id:
                query = query.filter(Recommendation.evaluation_id == evaluation_id)
            if start_dt:
                query = query.filter(Recommendation.created_at >= start_dt)
            if end_dt:
                query = query.filter(Recommendation.created_at <= end_dt)

            recs = query.order_by(Recommendation.created_at.desc()).offset(skip).limit(limit).all()

            return [
                RecommendationResponse(
                    id=r.id,
                    evaluation_id=r.evaluation_id,
                    created_at=r.created_at,
                    component=r.component,
                    issue=r.issue,
                    suggestion=r.suggestion,
                    priority=r.priority,
                    parameter_adjustments=r.parameter_adjustments,
                )
                for r in recs
            ]

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving recommendations", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# GET /reports/{evaluation_id}
# ---------------------------------------------------------------------------

@app.get("/reports/{evaluation_id}")
def get_report(
    evaluation_id: str,
    format: str = Query("html", description="Report format: pdf or html"),
):
    """Generate and download an evaluation report in PDF or HTML format."""
    format = format.lower()
    if format not in ("pdf", "html"):
        raise HTTPException(status_code=400, detail="Unsupported format. Use 'pdf' or 'html'.")

    try:
        import uuid
        try:
            uuid.UUID(evaluation_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid evaluation_id format (must be a UUID)")

        with get_session() as db:
            eval_db = db.query(Evaluation).filter(Evaluation.id == evaluation_id).first()
            if not eval_db:
                raise HTTPException(status_code=404, detail="Evaluation not found")

            summary = _build_evaluation_summary(eval_db)
            recommendations = summary.recommendations

        generator = ReportGenerator()

        if format == "pdf" and not generator.pdf_available:
            raise HTTPException(
                status_code=503,
                detail=(
                    "PDF generation is not available on this server. "
                    "Install WeasyPrint + GTK+ runtime and restart the service. "
                    "Use format=html as an alternative."
                ),
            )

        output_files = generator.generate(summary, recommendations, formats=[format])
        file_path = output_files.get(format)

        if not file_path or not file_path.exists():
            raise HTTPException(status_code=500, detail="Report generation failed — file not found.")

        media_type = "application/pdf" if format == "pdf" else "text/html"
        filename = f"evaluation_report_{evaluation_id[:8]}.{format}"

        logger.info(
            "Streaming report",
            evaluation_id=evaluation_id,
            format=format,
            path=str(file_path),
        )
        return FileResponse(
            path=str(file_path),
            media_type=media_type,
            filename=filename,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error generating report", evaluation_id=evaluation_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
