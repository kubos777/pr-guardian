FROM python:3.11-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first (cache layer)
COPY pyproject.toml ./
RUN uv sync --no-dev --frozen 2>/dev/null || uv sync --no-dev

# Copy source code
COPY . .

# Create data directory for SQLite
RUN mkdir -p /app/data

ENV PYTHONPATH="/app:/app/agent-core:/app/github-integration"
ENV PYTHONUNBUFFERED=1
