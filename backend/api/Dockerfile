# Build context: backend. Runtime contains only API dependencies and sources.
ARG PYTHON_IMAGE=public.ecr.aws/docker/library/python:3.12-slim@sha256:1148dbb014615300fa7e713b2f94f550c0d1c69780c0805f84f093ceee34dd0b
FROM ${PYTHON_IMAGE} AS build
ARG UV_VERSION=0.13.6
RUN pip install --no-cache-dir uv==${UV_VERSION}
WORKDIR /build
COPY pyproject.toml uv.lock ./
COPY api/pyproject.toml api/pyproject.toml
COPY database/pyproject.toml database/pyproject.toml
COPY market_data/pyproject.toml market_data/pyproject.toml
COPY scheduler/pyproject.toml scheduler/pyproject.toml
COPY database/src database/src
COPY market_data/market_data market_data/market_data
RUN uv sync --frozen --package api --no-dev --no-editable

FROM ${PYTHON_IMAGE}
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=build /build/.venv /app/.venv
COPY api/main.py /app/main.py
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
