"""Command-line interface for REMS."""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import structlog

from rems import __version__
from rems.collector import APICollector
from rems.config import settings
from rems.diagnostic import DiagnosticEngine
from rems.evaluators import EvaluationOrchestrator
from rems.models import init_db
from rems.recommendations import RecommendationEngine
from rems.reports import ReportGenerator

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


def setup_llm():
    """Set up the LangChain LLM and Embeddings for evaluation."""
    from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

    if not settings.google_api_key:
        logger.warning("GOOGLE_API_KEY not set, evaluation will fail")
        return None, None

    llm = ChatGoogleGenerativeAI(
        model=settings.evaluation_model,
        google_api_key=settings.google_api_key,
        temperature=0.0,    # Deterministic JSON output → fewer OutputParserExceptions
        max_retries=6,      # More retries on transient timeouts
    )
    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001",
        google_api_key=settings.google_api_key,
    )

    return llm, embeddings


def cmd_init_db(args):
    """Initialize the database."""
    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialized successfully")


def cmd_collect(args):
    """Collect interactions from the chatbot API."""
    collector = APICollector()

    try:
        if args.file:
            # Load from file
            interactions = collector.load_from_file(args.file)
        else:
            # Fetch from API
            start_date = datetime.fromisoformat(args.start) if args.start else None
            end_date = datetime.fromisoformat(args.end) if args.end else None
            interactions = collector.fetch_interactions(
                start_date=start_date,
                end_date=end_date,
                limit=args.limit,
            )

        if args.store:
            stored_ids = collector.store_interactions(interactions)
            logger.info("Stored interactions", count=len(stored_ids))
        else:
            logger.info("Collected interactions (not stored)", count=len(interactions))

    finally:
        collector.close()


def cmd_evaluate(args):
    """Run an evaluation."""
    llm, embeddings = setup_llm()
    collector = APICollector()

    try:
        # Load interactions
        if args.file:
            interactions = collector.load_from_file(args.file)
        else:
            start_date = datetime.fromisoformat(args.start) if args.start else None
            end_date = datetime.fromisoformat(args.end) if args.end else None
            interactions = collector.fetch_interactions(
                start_date=start_date,
                end_date=end_date,
                limit=args.limit,
            )

        if not interactions:
            logger.error("No interactions to evaluate")
            return

        # Run evaluation
        orchestrator = EvaluationOrchestrator(llm=llm, embeddings=embeddings)
        summary = orchestrator.evaluate(
            interactions=interactions,
            name=args.name,
            store_results=not args.no_store,
        )

        # Generate recommendations
        recommendation_engine = RecommendationEngine()
        recommendations = recommendation_engine.generate_recommendations(
            summary,
            store_in_db=not args.no_store,
        )

        # Update summary with recommendations
        summary.recommendations = recommendations

        # Export recommendations to YAML
        yaml_path = recommendation_engine.export_to_yaml(
            summary,
            recommendations,
            output_path=Path(args.recommendations) if args.recommendations else None,
        )
        logger.info("Recommendations exported", path=str(yaml_path))

        # Generate reports
        if not args.no_report:
            report_generator = ReportGenerator(
                output_dir=Path(args.output) if args.output else None
            )
            output_files = report_generator.generate(
                summary,
                recommendations,
                formats=args.formats.split(",") if args.formats else ["pdf", "html"],
            )
            for fmt, path in output_files.items():
                logger.info(f"Report generated: {fmt}", path=str(path))

        # Print summary
        print("\n" + "=" * 60)
        print("EVALUATION SUMMARY")
        print("=" * 60)
        print(f"Interactions evaluated: {summary.interaction_count}")
        print(f"Overall score: {summary.overall_score:.2%}")
        print(f"Quality level: {summary.quality_level.upper()}")
        print(f"Retrieval score: {summary.retrieval_score:.2%}")
        print(f"Generation score: {summary.generation_score:.2%}")
        if summary.metrics.hallucination_rate:
            print(f"Hallucination rate: {summary.metrics.hallucination_rate:.2%}")
        print(f"Recommendations: {len(recommendations)}")
        print("=" * 60)

    finally:
        collector.close()


def cmd_web(args):
    """Launch the web interface."""
    import subprocess

    logger.info("Launching web interface...", host=args.host, port=args.port)

    # Get the path to the web app
    from rems.web import app
    import os

    app_path = os.path.dirname(app.__file__)
    app_file = os.path.join(app_path, "app.py")

    # Launch streamlit
    subprocess.run([
        sys.executable, "-m", "streamlit", "run",
        app_file,
        "--server.port", str(args.port),
        "--server.address", args.host,
        "--browser.gatherUsageStats", "false",
    ])


def cmd_api(args):
    """Launch the REST API."""
    import uvicorn
    logger.info("Launching REST API...", host=args.host, port=args.port)
    uvicorn.run("rems.api:app", host=args.host, port=args.port, reload=args.reload)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="REMS - RAG Evaluation & Monitoring System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version", action="version", version=f"REMS {__version__}"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init-db command
    init_parser = subparsers.add_parser("init-db", help="Initialize the database")
    init_parser.set_defaults(func=cmd_init_db)

    # collect command
    collect_parser = subparsers.add_parser(
        "collect", help="Collect interactions from the chatbot"
    )
    collect_parser.add_argument(
        "--file", "-f", help="Load interactions from a JSON file instead of API"
    )
    collect_parser.add_argument(
        "--start", "-s", help="Start date (ISO format)"
    )
    collect_parser.add_argument(
        "--end", "-e", help="End date (ISO format)"
    )
    collect_parser.add_argument(
        "--limit", "-l", type=int, help="Maximum number of interactions"
    )
    collect_parser.add_argument(
        "--store", action="store_true", help="Store collected interactions in database"
    )
    collect_parser.set_defaults(func=cmd_collect)

    # evaluate command
    eval_parser = subparsers.add_parser(
        "evaluate", help="Run an evaluation on interactions"
    )
    eval_parser.add_argument(
        "--file", "-f", help="Load interactions from a JSON file"
    )
    eval_parser.add_argument(
        "--start", "-s", help="Start date filter (ISO format)"
    )
    eval_parser.add_argument(
        "--end", "-e", help="End date filter (ISO format)"
    )
    eval_parser.add_argument(
        "--limit", "-l", type=int, help="Maximum number of interactions to evaluate"
    )
    eval_parser.add_argument(
        "--name", "-n", help="Name for this evaluation run"
    )
    eval_parser.add_argument(
        "--output", "-o", help="Output directory for reports"
    )
    eval_parser.add_argument(
        "--recommendations", "-r", help="Output path for recommendations YAML"
    )
    eval_parser.add_argument(
        "--formats", help="Report formats (comma-separated: pdf,html)"
    )
    eval_parser.add_argument(
        "--no-store", action="store_true", help="Don't store results in database"
    )
    eval_parser.add_argument(
        "--no-report", action="store_true", help="Don't generate reports"
    )
    eval_parser.set_defaults(func=cmd_evaluate)

    # web command
    web_parser = subparsers.add_parser(
        "web", help="Launch the web interface (Streamlit dashboard)"
    )
    web_parser.add_argument(
        "--port", "-p", type=int, default=8501, help="Port for the web server"
    )
    web_parser.add_argument(
        "--host", default="localhost", help="Host for the web server"
    )
    web_parser.set_defaults(func=cmd_web)

    # api command
    api_parser = subparsers.add_parser(
        "api", help="Launch the REST API server"
    )
    api_parser.add_argument(
        "--port", "-p", type=int, default=8000, help="Port for the API server"
    )
    api_parser.add_argument(
        "--host", default="localhost", help="Host for the API server"
    )
    api_parser.add_argument(
        "--reload", action="store_true", help="Enable auto-reload for development"
    )
    api_parser.set_defaults(func=cmd_api)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
