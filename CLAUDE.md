# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

REMS (RAG Evaluation & Monitoring System) is a Python module that evaluates and monitors the performance of an existing regulatory RAG chatbot. It operates as an external observer without modifying the chatbot itself.

Key features:
- RAGAS-based evaluation (Faithfulness, Context Precision, Answer Relevancy)
- Hallucination detection (faithfulness < 0.7 threshold)
- Diagnostic engine with root cause analysis
- Recommendations exported to YAML for manual application
- PDF/HTML reports with visualizations
- Streamlit web dashboard

## Development Commands

```bash
# Install dependencies
uv sync

# Initialize database (PostgreSQL must be running)
uv run rems init-db

# Launch web interface
uv run rems web                    # Default port 8501
uv run rems web --port 8080        # Custom port

# Run evaluation from JSON file
uv run rems evaluate --file test_interactions.json --name "My Evaluation"

# Run evaluation from chatbot API
uv run rems evaluate --start 2026-01-01 --end 2026-01-07 --limit 100

# Simulate evaluation (no LLM required, for testing)
uv run python scripts/simulate_evaluation.py

# Linting and type checking
uv run ruff check src/
uv run mypy src/
```

## Database Setup

```bash
# Start PostgreSQL (macOS)
brew services start postgresql@16

# Create database
createdb rems

# Initialize tables
uv run rems init-db
```

## Architecture

```
src/rems/
├── cli.py                 # CLI (init-db, collect, evaluate, web)
├── config.py              # Pydantic settings (env vars)
├── schemas.py             # Pydantic DTOs
├── models/
│   ├── database.py        # SQLAlchemy models (Interaction, Evaluation, etc.)
│   └── session.py         # Database session management
├── collector/
│   └── api_collector.py   # Fetches interactions from API or JSON file
├── evaluators/
│   ├── retrieval_evaluator.py   # Context Precision (RAGAS 0.4.x)
│   ├── generator_evaluator.py   # Faithfulness, Answer Relevancy
│   └── orchestrator.py          # Coordinates evaluators
├── diagnostic/
│   └── engine.py          # Root cause analysis rules
├── recommendations/
│   └── engine.py          # Generates suggestions + YAML export
├── reports/
│   ├── generator.py       # PDF/HTML via WeasyPrint
│   └── templates/         # Jinja2 templates
└── web/
    ├── app.py             # Streamlit main app
    └── pages/             # dashboard.py, history.py, evaluate.py
```

## Key Files

- `test_interactions.json` - Sample interactions for testing
- `scripts/simulate_evaluation.py` - Creates fake evaluation data (no LLM needed)
- `scripts/weekly_evaluation.sh` - Cron script for scheduled evaluations
- `recommendations.yaml` - Output file with actionable recommendations
- `reports/` - Generated PDF/HTML reports

## RAGAS 0.4.x Notes

Uses new class-based metric imports:
```python
from ragas.metrics._context_precision import ContextPrecision
from ragas.metrics._faithfulness import Faithfulness
from ragas.metrics._answer_relevance import ResponseRelevancy
```

Dataset columns: `user_input`, `response`, `retrieved_contexts` (not `question`, `answer`, `contexts`)

## Environment Variables

```env
REMS_DATABASE_URL=postgresql://user:password@localhost:5432/rems
REMS_CHATBOT_API_URL=http://localhost:8000
REMS_CHATBOT_API_KEY=your-api-key
REMS_GOOGLE_API_KEY=your-google-api-key
REMS_EVALUATION_MODEL=gemini-2.0-flash
REMS_REPORTS_DIR=./reports
REMS_RECOMMENDATIONS_FILE=./recommendations.yaml
```

## Domain Context

Regulatory/legal chatbot evaluation where:
- Accuracy is critical (legal consequences for errors)
- All responses must be traceable to source documents
- Hallucinations flagged when faithfulness < 0.7
- Quality levels: Excellent (≥90%), Good (75-89%), Acceptable (60-74%), Poor (40-59%), Critical (<40%)
