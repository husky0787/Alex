# Alex | Multi-Agent Portfolio Intelligence Platform

Alex is a course-based portfolio intelligence application extended with verified daily market data, recoverable ETL, frozen analysis prices, research provenance, Kubernetes operations and controlled delivery. Authenticated users manage holdings and retrieve persistent reports, charts and retirement projections.

**Start here:** [project showcase and contribution boundaries](docs/showcase/README.md) · [full architecture, including data engineering and Kubernetes](docs/showcase/architecture.md) · [45-second evidence walkthrough](docs/showcase/walkthrough.mp4) · [reproduce and clean up](deploy/showcase/README.md) · [real authenticated acceptance](docs/verification/task-11-showcase.md).

The foundation is Ed Donner's *AI in Production* course. The linked evidence separates course features from personal additions, real tests from injected fixtures, and historical acceptance from currently deployed services. The acceptance environments are temporary; this repository does not promise an always-on public demo.

## Architecture

The original serverless application path is below. The [full component map](docs/showcase/architecture.md) also shows the Kubernetes API/ETL alternative and distinguishes the separate acceptance environments.

```mermaid
flowchart LR
    Browser[Browser] -->|Sign in| Clerk[Clerk]
    Browser -->|HTTPS| CloudFront[CloudFront]
    CloudFront -->|Static application| S3[S3]
    CloudFront -->|/api/*| API[API Gateway]
    API -->|JWT-validated request| APILambda[FastAPI Lambda]
    APILambda -->|Data API| Aurora[(Aurora Serverless v2<br/>PostgreSQL)]
    APILambda -->|Create analysis job| Queue[SQS]

    Queue --> Planner[Planner Lambda]
    Operator[Explicit classification preflight] --> Tagger[Tagger Lambda]
    Tagger -->|Reference data| Aurora
    Planner --> Reporter[Reporter Lambda]
    Planner --> Charter[Charter Lambda]
    Planner --> Retirement[Retirement Lambda]
    Reporter -->|Markdown report| Aurora
    Charter -->|Recharts JSON| Aurora
    Retirement -->|Projection output| Aurora
    Reporter -->|Research context| Vectors[(S3 Vectors)]

    Scheduler[EventBridge Scheduler<br/>optional] --> SchedulerLambda[Scheduler Lambda]
    SchedulerLambda -->|Function URL| Researcher[Researcher<br/>container-image Lambda]
    Researcher -->|Playwright MCP research| Web[Web sources]
    Researcher -->|Ingest research| Ingest[Ingest Lambda]
    Ingest -->|Embeddings| SageMaker[SageMaker endpoint]
    SageMaker --> Ingest
    Ingest --> Vectors
```

## System Behavior

1. A signed-in user submits an analysis request through the API.
2. The API freezes holdings and verified daily prices in a job snapshot, creates the job in Aurora and sends its ID to SQS.
3. The Planner uses that fixed snapshot and coordinates Reporter, Charter and Retirement. Tagger classification is a separate preflight in the validated flow; missing required prices fail explicitly instead of being generated.
4. Reporter, Charter, and Retirement persist their outputs in separate job payloads. The client polls job status and renders the completed result.
5. Independently, the optional scheduled Researcher gathers market context through a Playwright MCP server and adds embedded documents to the S3 Vectors knowledge base.

## Engineering Highlights

- **Asynchronous orchestration:** SQS decouples request handling from long-running agent execution; a dead-letter queue retains messages that exhaust retry attempts.
- **Specialized workloads:** the Planner delegates narrative reporting, charts and retirement projections to independently deployable Lambda functions; Tagger classifies instruments separately.
- **Data engineering and operations:** daily market ingestion, quality quarantine, backfill and idempotency; API/ETL Kubernetes workloads with bounded EKS acceptance, workload IAM, alerts and rollback.
- **Durable, isolated outputs:** agents write to dedicated Aurora JSONB job fields rather than requiring a shared in-memory result merger.
- **AI integration:** OpenAI Agents SDK runs against Amazon Bedrock; the Tagger uses structured outputs, while tool-oriented agents use purpose-built data and retrieval tools.
- **Knowledge retrieval:** financial research is embedded by SageMaker and indexed in S3 Vectors for semantic retrieval.
- **Infrastructure as code:** Terraform components retain independent local state, allowing individual services to be deployed and destroyed independently.
- **Operational visibility:** CloudWatch logs cover Lambda execution; LangFuse tracing is supported when its optional environment variables are configured.

## Technology Stack

| Area | Technologies |
| --- | --- |
| Application | Python 3.12, FastAPI, Pydantic, OpenAI Agents SDK |
| AI and retrieval | Amazon Bedrock, SageMaker, S3 Vectors, Playwright MCP |
| Compute and integration | AWS Lambda, API Gateway, SQS, EventBridge, ECR |
| Data | Aurora Serverless v2 PostgreSQL, RDS Data API, Secrets Manager |
| Frontend | Next.js, React, TypeScript, Clerk, Recharts |
| Delivery and observability | Terraform, Docker, CloudFront, CloudWatch, LangFuse |

## Run Locally

For the validated personal-project flow, use the [isolated showcase runbook](deploy/showcase/README.md). The commands below are the original application entry points and require their own matching deployed configuration; they do not create the showcase or its market database.

### Prerequisites

- Node.js 20+ and npm
- [uv](https://docs.astral.sh/uv/)
- Docker Desktop
- Terraform 1.5+
- AWS CLI configured with credentials that can access the provisioned development resources

### Configuration

Create a root `.env` from [`.env.example`](.env.example) and configure the backend and AWS integration values. Create `frontend/.env.local` with the Clerk keys and the local API URL. Do not commit either file.

### Start the application

```bash
cd scripts
uv run run_local.py
```

The runner starts the FastAPI service at `http://localhost:8000` and the Next.js application at `http://localhost:3000`. Interactive API documentation is available at `http://localhost:8000/docs`.

### Run tests

Use mocked local tests before testing deployed resources:

```bash
cd backend
uv run test_simple.py
```

After AWS resources are configured, exercise the deployed flow:

```bash
cd backend
uv run test_full.py
```

Individual agents also provide `test_simple.py` and `test_full.py` within their respective directories.

## Deploy to AWS

The following is the original guide deployment order. For the personal extension, choose the [showcase](deploy/showcase/README.md), [EKS](deploy/eks/README.md) or [controlled CI](deploy/ci/README.md) runbook and its corresponding state; do not apply all of them as one environment.

Terraform is intentionally split into independent components. Each component maintains its own local state and requires a `terraform.tfvars` file created from its corresponding example before it is applied.

Deploy the components in dependency order:

1. `terraform/2_sagemaker`
2. `terraform/3_ingestion`
3. `terraform/4_researcher`
4. `terraform/5_database`
5. `terraform/6_agents`
6. `terraform/7_frontend`
7. `terraform/8_enterprise`

Package and update the agent Lambdas with Docker before applying the agent infrastructure:

```bash
cd backend
uv run package_docker.py
uv run deploy_all_lambdas.py
```

Build and deploy the API/frontend infrastructure and static site:

```bash
cd scripts
uv run deploy.py
```

The deployment scripts check for Docker, Terraform, npm, and AWS CLI availability. Review Terraform plans and AWS costs before applying changes. Destroy unused components when development pauses, especially the database tier.

## Security and Operating Boundaries

- Clerk JWTs are validated by the API Lambda before application data is accessed.
- Database credentials are stored in AWS Secrets Manager; Lambda permissions are defined through IAM policies.
- Pydantic validation and agent output validation are used to constrain application inputs and generated data.
- CloudWatch logs support failure investigation, and optional LangFuse tracing records agent execution details.
- The current Researcher Function URL is public in Terraform. Restrict or authenticate it before exposing the system to untrusted traffic.
- Alex is for informational purposes only and does not provide financial, investment, or trading advice.

## Repository Layout

```text
backend/      Lambda functions, agents, API, ingestion, and shared database code
frontend/     Next.js application and Clerk integration
terraform/    Independently managed AWS infrastructure components
scripts/      Local development and frontend deployment entry points
guides/       Architecture and operating reference material
```

## License

Distributed under the [MIT License](LICENSE).
