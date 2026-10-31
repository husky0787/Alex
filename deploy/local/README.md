# API on local Kubernetes

This disposable k3d environment runs the real API, PostgreSQL 17.6, a local JWKS
server and a narrow RDS Data API/SQS transport fixture. It requires no AWS or Clerk
credentials and does not run analysis agents. Task 7 is tracked by issue #9.

Use Docker, k3d **5.9.0**, and uv on the same machine. The runner pins k3s to
**v1.35.5-k3s1**. API builds pin the Python base digest and uv version, and install
API dependencies from `backend/uv.lock` with `--frozen`. Build from the repository
root with a unique source revision tag; preserve the resulting image ID with the
test evidence. Do not reuse a tag for different source revisions.

```sh
docker build --platform linux/amd64 -f backend/api/Dockerfile -t alex-api:<revision> backend
docker pull postgres:17.6
docker pull rancher/k3s:v1.35.5-k3s1
uv run --no-project deploy/local/run.py up --image alex-api:<revision>
uv run --no-project deploy/local/run.py recovery --image alex-api:<revision>
uv run --no-project deploy/local/run.py down
```

`<revision>` is a placeholder: replace it with your Git commit or other immutable
build label. Optional `--k3d /path/to/k3d` and `--postgres-image <cached-reference>`
support tools/images already installed on a builder. An existing PostgreSQL
container is never reused; only its image can be loaded into the new cluster.
The API and dependency manifests use `imagePullPolicy: Never`; the runner loads
the selected images before creating workloads. Cluster system images may require
network access on first startup.

The runner owns only cluster `alex-task07` and namespace `alex-local`. It does not
change the user's default kubeconfig. The API is exposed at
`http://127.0.0.1:18080`; Kubernetes management binds `127.0.0.1:16443`. On a remote
builder, forward the API port over an authenticated SSH connection:

```sh
ssh -N -L 18080:127.0.0.1:18080 <user>@<builder>
```

The frontend may use this API base URL, but the fixture signs local test tokens;
real Clerk browser sign-in is not part of this smoke test. `smoke.py` creates
fresh users through the real API and exercises valid signatures, missing/invalid/
expired/forged tokens, cross-user account/job denial, JSON errors, CORS, persisted
accounts and a cash-only analysis job. The queue records that job locally; it
does not claim an agent processed it.

`/health` is process liveness. `/ready` executes a bounded database connectivity
probe and returns 503 without database error details on failure. It is not an
end-to-end check of JWKS, queue or market data. Two API replicas use readiness,
liveness and startup probes, requests/limits, a read-only root, a non-root UID and
no service-account token. ConfigMaps hold non-secret settings; generated Secrets
hold disposable database credentials. The private signing key stays on the host
and never enters the application image or API Pod. Test fixture code is mounted
as a ConfigMap, not baked into the production API image.

The recovery command deletes one API Pod, verifies its replacement, deploys an
intentionally missing image, checks `ProgressDeadlineExceeded` while old replicas
remain available, and explicitly rolls back. Kubernetes does not automatically
undo a failed rollout. It also stops the database transport fixture and checks
that API readiness drops without a liveness restart, then restores the fixture
and reruns authenticated smoke tests. Evidence and disposable credentials stay
under ignored `.local/kubernetes/task07/`; do not commit that directory.

PostgreSQL uses `emptyDir`, intentionally losing test data when its Pod or cluster
is deleted. This is not a production storage configuration. The local SQL bridge
implements only parameterized `ExecuteStatement` and does not emulate IAM,
Secrets Manager, Aurora auto-pause, Data API limits or transactions. SQS behavior
is limited to recording `SendMessage`. TLS/CloudFront, real Clerk session issuance,
EKS workload identity, durable storage, autoscaling and AWS agents remain separate
validation tasks. No local fixture credentials or service URLs should be deployed
to AWS.

References: [k3d local port mapping](https://k3d.io/stable/usage/exposing_services/),
[Kubernetes deployment progress and rollback](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/).
