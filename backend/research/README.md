# Attributed research

`alex-research` supplies the shared ingestion/search contract used by ingestion, Researcher and Reporter. Install each consuming project using `uv sync --locked`; their editable source paths are relative and portable.

Researcher captures final source URLs and UTC navigation times from Playwright, passes only observed URLs to ingestion, and requires an ingestion receipt. Its `/research` response is now an object with `status`, `content` and `research` receipts. An unpersisted run returns HTTP 503, including scheduled `/research/auto` runs. Direct ingestion clients must send this contract:

```json
{
  "text": "Summary based on the source page",
  "metadata": {
    "research_id": "unique-research-id",
    "topic": "AAPL",
    "sources": [{"url": "https://www.apple.com/newsroom/", "fetched_at": "2026-10-27T12:00:00+00:00"}]
  }
}
```

HTTP retries keep the same ID and payload. Direct callers are responsible for their source observations and must not reuse an ID for different content. Source attribution is not a factual verification service. Search excludes legacy records without valid provenance. The MiniLM adapter accepts a 384-dimensional sentence vector or mean-pools the single input's token vectors; existing first-token embeddings require re-ingestion into a new index.

Configure `RESEARCH_AWS_REGION` (default `DEFAULT_AWS_REGION` or `us-east-1`), `SAGEMAKER_ENDPOINT`, `VECTOR_BUCKET` and `INDEX_NAME`. If no bucket is supplied, the existing account-based Alex naming convention is used. `BEDROCK_REGION` is independent of vector storage.

Reporter saves `research.status`, `reason`, `retrieved_at` and full `results` in the report payload. Missing research produces an explicit holdings-only report without a model narrative. Price snapshots remain the source of portfolio valuation.

## Local verification

From the repository root, with Python 3.12 selected:

```text
uv run --project backend --locked --package api backend/tests/test_research_chain.py
uv run --project backend/researcher --locked backend/tests/test_researcher_receipts.py
```

For the existing worker contract test, set `SNAPSHOT_AGENT=reporter` and run:

```text
uv run --project backend/planner --locked backend/tests/test_snapshot_workers.py
```

These tests substitute browser/model/AWS transports. They do not prove cloud permissions, browser compatibility, source relevance or live model quality.

## Build and deployment

```text
uv run --project backend/ingest --locked backend/ingest/package.py
docker build --platform linux/amd64 -f backend/researcher/Dockerfile -t alex-researcher:task06 backend
uv run --project backend/reporter --locked backend/reporter/package_docker.py
```

The ingestion builder selects Linux wheels instead of copying a Windows environment. Researcher uses the **backend** build context and a Dockerfile-specific allowlist to exclude `.env`, credentials, `.venv` and private data. Reporter packaging includes both local shared packages.

Terraform 3 now declares the actual vector bucket/index in addition to the existing ordinary S3 bucket. Configure text and sources as non-filterable metadata, dimension 384 and cosine distance. Before applying to another account, inspect/import any manually created resources; changing index metadata/pooling is not an in-place migration. Never delete an existing index to make a plan succeed.

The account's current state and remaining cloud acceptance steps are in `docs/verification/task-06-research-chain.md`. Do not deploy just the snapshot-dependent Reporter over an application still creating legacy jobs; coordinate the task 5 API/worker rollout or use an isolated acceptance function/job.
