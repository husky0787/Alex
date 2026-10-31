# Task 7: local Kubernetes API verification

Verified on 2026-10-31 using a dedicated k3d cluster on the user's Linux Docker
builder. All four issue #9 acceptance areas passed. This is local Kubernetes
evidence, not EKS or a production deployment. PR #20 was merged first as
`52395b5208c0bd04d2bb992de314273750b48762`.

## Runtime and artifact

- k3d 5.9.0; k3s/Kubernetes `v1.35.5+k3s1`; Linux/amd64.
- Application image `alex-api:d264440`, built from the API/Dockerfile source at
  commit `d264440`. Docker image reference digest:
  `sha256:b48dfb05e953bcb426bea4056dee609d1222abbc537d268c6dac30da6eaee5ea`.
- Python base from the official ECR Docker-library mirror, amd64 manifest
  `sha256:1148dbb014615300fa7e713b2f94f550c0d1c69780c0805f84f093ceee34dd0b`.
  The manifest was checked against the public registry. API dependencies were
  installed with pinned uv 0.13.6 and `uv sync --frozen --package api --no-dev --no-editable`.
- Real PostgreSQL 17.6 in a separate disposable Pod. The builder's cached
  `m.daocloud.io/docker.io/library/postgres:17.6` image was reused; no existing
  PostgreSQL container or database was accessed.
- Two API replicas, Deployment/NodePort Service, loopback entry port 18080,
  resource requests/limits, non-root user, read-only root, dropped capabilities,
  disabled service-account token and separate generated ConfigMaps/Secrets.

## Executed results

| Test | Observed result |
| --- | --- |
| API regression suite | 12 tests passed, including readiness success/failure, safe diagnostic logging and independent liveness |
| Health and readiness | Both returned HTTP 200 through the local Kubernetes entry |
| Authentication | Fresh RS256-signed users were created through the real API; missing, malformed, expired and forged tokens all returned JSON 403 |
| Authorization | Another user's account reads/writes and job reads returned JSON 403; that user's own account list remained empty |
| Persistence and queue | Accounts and cash-only analysis snapshots persisted in PostgreSQL; four successful smoke runs left four records in the local queue table |
| CORS and unknown route | Allowed localhost preflight succeeded; unknown API route returned JSON 404 |
| Pod loss | Deleted one API Pod; Deployment created a different Pod and returned to two ready replicas; authenticated smoke passed again |
| Failed rollout | Missing image produced `ProgressDeadlineExceeded`; two previous replicas stayed available |
| Rollback | Explicit `rollout undo` restored `alex-api:d264440`; authenticated smoke passed again |
| Dependency outage | Scaling the SQL/JWKS fixture to zero removed API readiness without increasing API restart counts; restoring it returned readiness and passed smoke again |

The deliberately failed rollout returned:

```text
error: deployment "api" exceeded its progress deadline
```

The runner records checks rather than treating that nonzero exit alone as proof:
it also checks the Deployment condition, available replica count, restored image,
replacement Pod identity and authenticated HTTP behavior. Kubernetes does not
perform the rollback automatically.

## Scope and limitations

JWT validation uses the application's real Clerk middleware with a local JWKS and
host-generated signing key; no authentication dependency is bypassed. It does
not test real Clerk browser sign-in, account/session management or production
issuer/audience configuration. The API's existing validation policy is retained.

The transport fixture executes the real application schema on PostgreSQL using
bound parameters. It implements only RDS Data API `ExecuteStatement` and SQS
`SendMessage`, not AWS IAM, Secrets Manager, Data API transaction semantics,
Aurora auto-pause, queue delivery/retries or running agents. The queued analysis
used cash-only holdings; this test does not claim market-provider coverage.
EKS, TLS/CloudFront, durable volumes and workload identity remain later tasks.

The first setup exposed two k3d details now reflected in the runner: direct port
mapping is required with `--no-lb`, and default image-volume/tools initialization
must remain enabled. Nodes could not reach the registry from this network, so
pinned pause/CoreDNS images are loaded through the Docker host before workloads.
The actual container provides `kubectl` and `ctr` entrypoints directly. An initial
smoke assertion expected an object instead of the API's existing account list;
the assertion was corrected and the entire smoke rerun successfully.

## Cleanup and handoff

After evidence capture, `run.py down` successfully removed only `alex-task07`,
its network and attached image volume. The eleven unrelated containers observed
at the start remained running. Test PostgreSQL data was disposable `emptyDir`
storage and was removed with the cluster. The API image and source remain on the
builder; no task 7 AWS resources or paid model calls were created.

Private execution evidence is retained under `.local/kubernetes/` on the working
computer and builder, excluding credentials from Git. Reproduce with
[the local Kubernetes runbook](../../deploy/local/README.md). Standards review
found two issues (missing safe readiness diagnostics and inconsistent ownership
checks), both fixed; follow-up Standards and Spec reviews found no remaining
actionable code findings. The actual runtime results above were collected after
those fixes.
