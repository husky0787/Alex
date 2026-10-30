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

The old course smoke scripts now use this same contract. `backend/ingest/test_ingest_s3vectors.py --document <captured-document.json>` requires genuine source metadata instead of writing unattributed sample company descriptions. `test_search_s3vectors.py "known topic" --expected-id <research-id>` fails if the known research is absent. `backend/researcher/test_local.py` runs the same receipt-checked service flow. These smoke commands invoke real services and are reserved for the later cloud acceptance window.

## Build and deployment

```text
uv run --project backend/ingest --locked backend/ingest/package.py
docker build --platform linux/amd64 --provenance=false -f backend/researcher/Dockerfile -t alex-researcher:task06 backend
uv run --no-project backend/reporter/package_docker.py
```

The ingestion builder selects Linux wheels instead of copying a Windows environment. Researcher uses the **backend** build context and a Dockerfile-specific allowlist to exclude `.env`, credentials, `.venv` and private data. Reporter packaging includes both local shared packages and installs the exported third-party dependencies with their locked hashes, without resolving extra dependencies. Reporter removes the unused `pydantic-ai` dependency and declares `logfire` directly for its observability integration.

On a Linux builder whose proxy listens on localhost, export the proxy variables in the build shell and use host networking. Reporter forwards set proxy environment variables by name (without printing their values):

```sh
uv run --no-project backend/reporter/package_docker.py --network host
docker build --platform linux/amd64 --provenance=false --network host \
  --build-arg HTTP_PROXY --build-arg HTTPS_PROXY --build-arg NO_PROXY \
  --build-arg http_proxy --build-arg https_proxy --build-arg no_proxy \
  -f backend/researcher/Dockerfile -t alex-researcher:task06 backend
```

The Docker daemon needs its own registry proxy configuration; build arguments only configure build steps. If the default Debian source is too slow, the Researcher build also accepts `--build-arg DEBIAN_MIRROR=https://<trusted-mirror>`; the mirror must serve both `/debian` and `/debian-security`. Debian package signature verification remains enabled. The default is `http://deb.debian.org`.

Reporter also forwards an explicitly set `PIP_INDEX_URL` for builders that need a different package index. Downloaded third-party files must still match the hashes exported from `uv.lock`. Researcher installs full Chromium, which MCP selects explicitly; the unused additional headless-shell binary is skipped using Playwright's [`--no-shell` option](https://playwright.dev/docs/browsers#chromium-new-headless-mode).

For parallel Reporter dependency installation, pass `--uv-binary /path/to/linux-amd64/uv`. The executable is mounted read-only and runs against the container's Python 3.12, with the same locked hashes and optional `PIP_INDEX_URL`. Without this option the builder uses pip. The packaging driver itself needs only the standard library; `--no-project` avoids installing the agent on the host. Set `UV_PYTHON` to an existing host interpreter if the checkout's preferred Python is unavailable.

Researcher's `browser-deps` target separates system dependencies from the browser download so retries reuse the completed layer. A trusted cache containing the official Chromium archive at its original relative URL can be selected with `--build-arg PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST=<cache-url>`. Omit this argument to use Playwright's normal download source. This build argument is not a runtime proxy setting.

If the initial `pip install uv` download times out, Researcher also accepts `--build-arg PIP_INDEX_URL=https://<trusted-index>/simple`. This only selects the bootstrap index; application dependencies still use `uv sync --frozen` and the committed lockfile.

After building, check actual Chromium/MCP navigation and source capture against an in-container fixture, with external networking disabled:

The Lambda image build disables provenance attestations as required by [AWS's container build instructions](https://docs.aws.amazon.com/lambda/latest/dg/python-image.html). This avoids publishing an attestation-bearing manifest list to Lambda. The smoke reads content with `browser_snapshot` after navigation, matching the Researcher's instructions; navigation alone can return a snapshot file link.

```sh
docker run --rm --network none --read-only --tmpfs /tmp:rw,size=512m \
  -e AWS_EC2_METADATA_DISABLED=true -e PYTHONPATH=/app \
  -v "$PWD/backend/tests/verify_research_container.py:/app/verify_research_container.py:ro" \
  --entrypoint uv alex-researcher:task06 run --no-sync /app/verify_research_container.py
```

This checks FastAPI health, the installed browser and the real MCP response format. It does not invoke a model or validate AWS permissions, ingestion or a cloud report.

Terraform 3 now declares the actual vector bucket/index in addition to the existing ordinary S3 bucket. Configure text and sources as non-filterable metadata, dimension 384 and cosine distance. Before applying to another account, inspect/import any manually created resources; changing index metadata/pooling is not an in-place migration. Never delete an existing index to make a plan succeed.

The account's current state and remaining cloud acceptance steps are in `docs/verification/task-06-research-chain.md`. Do not deploy just the snapshot-dependent Reporter over an application still creating legacy jobs; coordinate the task 5 API/worker rollout or use an isolated acceptance function/job.
