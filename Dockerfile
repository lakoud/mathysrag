# Stage 1: Builder
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

# Set environment variables for uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Copy dependency files first for caching
COPY pyproject.toml uv.lock ./

# Install dependencies only (cached layer)
RUN uv sync --no-dev --no-install-project

# Copy the rest of the source code
COPY src/ ./src/
COPY README.md ./

# Sync the project itself
RUN uv sync --no-dev

# Stage 2: Runtime
FROM python:3.12-slim-bookworm AS runtime

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    REMS_REPORTS_DIR=/app/reports \
    REMS_DATABASE_URL=postgresql://rems:rems_pass@postgres:5432/rems

# Install system dependencies for WeasyPrint
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    libharfbuzz0b \
    libpangoft2-1.0-0 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy virtual environment and source code from builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/pyproject.toml /app/pyproject.toml

# Expose ports
EXPOSE 8000 8501

# Default command (can be overridden in docker-compose)
CMD ["rems", "api", "--host", "0.0.0.0", "--port", "8000"]
