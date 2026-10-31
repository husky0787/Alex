# Alex: from course application to an evidenced engineering project

Alex starts from Ed Donner's **AI in Production** course. The personal extension adds traceable daily market data, recoverable ETL, frozen analysis prices, research provenance, Kubernetes operations and controlled delivery. The goal is a reproducible engineering demonstration, not trading advice or a claim of production traffic.

Start with the [architecture](architecture.md), [short evidence walkthrough](walkthrough.mp4), [walkthrough transcript](walkthrough.md), [latest acceptance record](../verification/task-11-showcase.md) and [rebuild/cleanup runbook](../../deploy/showcase/README.md). The video presents recorded results; it is not a recording of the user's browser. Run the actual app using the runbook to inspect interactive behavior.

## What came from the course, and what changed

| Course foundation | Personal engineering contribution | Evidence |
| --- | --- | --- |
| Next.js, Clerk, FastAPI, accounts and portfolio UI | Preserve API error status/JSON; dated market-history view; Dashboard login-state race regression | [Task1](../verification/task-01-api-errors.md), [Task4](../verification/task-04-universe-history.md), [Task11](../verification/task-11-showcase.md) |
| Aurora and AWS infrastructure examples | Dedicated API/ETL roles, owned acceptance databases, reviewed lifecycle/cleanup | [Task9](../verification/task-09-eks-acceptance.md) |
| Portfolio agent orchestration | Required verified-price snapshot; agents share the same immutable price basis; no fabricated fallback prices | [Task5](../verification/task-05-analysis-price-snapshots.md), [Task11](../verification/task-11-showcase.md) |
| Researcher, embeddings and vector search | Source URL/capture-time/research-ID contracts, read-back receipts and honest unavailable-research behavior | [Task6](../verification/task-06-aws-acceptance.md) |
| No personal daily-market ETL in the original guide flow |20-symbol universe,90-day backfill, raw archive, quarantine, idempotency, durable recovery, coverage and scheduling | [Task2](../verification/task-02-verified-price.md), [Task3](../verification/task-03-quality-recovery.md), [Task8](../verification/task-08-scheduled-etl.md) |
| Serverless application deployment | FastAPI Deployment and ETL CronJob on local Kubernetes and bounded EKS; separate workload permissions, HPA, alarms, rollback | [Task7](../verification/task-07-local-kubernetes-api.md), [Task9](../verification/task-09-eks-acceptance.md) |
| Manual deployment scripts | Pinned CI gates, immutable image digests, GitHub OIDC/ECR and failed-rollout recovery | [Task10](../verification/task-10-cicd.md) |

## Evidence map

| Capability | What was actually exercised | Scope/limit |
| --- | --- | --- |
| Real data end to end | Massive → validation → storage → API → dated UI;1,280 prices across20 symbols | Daily bars, not live quotes; provider provenance is not independent price certification |
| Bad-data isolation | Deliberately invalid response rejected and quarantined; valid-price count unchanged | Injected fault, not a claimed provider incident |
| Missing dates and recovery | Missing-window detection/backfill and interrupted-run recovery; error reasons and quality failures remain visible | Integration/fault drills documented in Task3/4/8 |
| Repeat safety | EKS manual Job and controller CronJob kept prices/observations at1,280/1,280 | Does not imply exactly-once delivery of all cloud messages |
| Alert delivery | Failed ETL and zero healthy ALB targets delivered actual notifications to SQS | Test receiver, not an on-call team's response-time measurement |
| Rollback | Invalid image/digest failed; previous healthy image restored and authenticated smoke passed | EKS operator drill and separate hosted-runner CI drill |
| Full application analysis | Normal Brave/Clerk login, fictional holdings, real SQS/Planner/Bedrock specialists, attributed research and saved UI results | Task11 uses local API/market DB; Task9 separately establishes EKS |

## A concise interview explanation

“I extended a course-based multi-agent portfolio application with a daily market-data pipeline and Kubernetes deployment. I implemented provenance and quality checks, quarantine and backfill, immutable price snapshots and controlled CI/CD. In bounded AWS acceptance, I verified1,280 market records, workload permission isolation, real alert delivery and failed-release rollback; a separate real-Clerk workflow completed and persisted report, chart and retirement outputs.”

Use the linked evidence to explain failures and tradeoffs. Do not describe the system as always-on, high-traffic, automatically deployed to EKS, financially audited, or built entirely from scratch. Final billing reconciliation remains independent. The original AWS application may still exist, but its older deployment is not the newly validated personal platform.
