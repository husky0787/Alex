# Controlled delivery

Every main-branch push and pull request update runs PostgreSQL market-data integration, API JWT/ownership contracts, frontend tests/lint/type-check/build and release failure tests. Only after both backend and frontend pass does CI build the API/ETL image from the locked backend workspace. Actions are pinned to commit SHAs; ordinary jobs have only `contents: read`, no cloud credentials and no paid-model calls.

CI builds the checked-out commit and its parent, records their Git revisions, image IDs and archive SHA256 values, then deploys immutable registry digests to disposable k3d. The runner verifies one healthy release and an intentionally missing digest. The shared release tool restores the previous healthy template on failure, rechecks readiness, and returns a nonzero exit code even after recovery. Authenticated smoke tests run after both outcomes. It refuses mutable tags, unhealthy rollback baselines and concurrent template overwrites. No database migration runs during image rollout; existing fixture data and schema remain in place.

## Manual AWS delivery

Main CI now retains tested image archives for three days, without obtaining AWS
credentials or publishing on push. Use the separate [manual EKS workflow](../cd/README.md)
to release an exact successful main CI revision to temporary real EKS.

Task 10's original ECR-only controlled release has been superseded by this manual
workflow. Its `terraform/10_ci` IAM/ECR setup remains separate and is not used or
deleted by the new CD module. `ALEX_RELEASE_COMMIT` no longer triggers deployment.
The original `acceptance.py --ecr` operator tool remains available for reproducing
historical Task 10 evidence; it deploys to runner k3d, not EKS.
## Existing EKS environments

`release.py` also accepts an operator's explicit EKS kubeconfig/context, namespace and reachable API URL:

```text
uv run --no-project deploy/ci/release.py --kubeconfig PRIVATE_KUBECONFIG --context EXPLICIT_CONTEXT --namespace alex-cloud --image ECR_URL@sha256:DIGEST --commit FULL_COMMIT --url HTTPS_API --evidence PRIVATE_EVIDENCE_JSON
```

Run from a Linux deployment host with network access and namespace-scoped Kubernetes `get/patch/watch` access to the API Deployment. API image and its previous healthy image must both use digests. This tool performs no EKS provisioning, endpoint firewall changes or migrations; the ECR-only GitHub role deliberately cannot perform these operations. The new CD workflow provisions its own isolated EKS acceptance stack. Releasing into any other existing EKS environment still requires an explicitly scoped operator step.

## Database and evidence boundaries

Schema changes use expand/contract: first add compatible nullable columns/tables or compatible defaults, verify both old and new application images on that schema, and only remove old fields in a later release after the rollback window. Destructive migrations are never coupled to image rollback. This task has no schema migration; the delivery drill checks schema equality and persisted API behavior.

Public Actions artifacts contain only safe release JSON and, for successful main CI runs, compressed immutable image archives and their checksum/commit manifest. Ordinary CI does not retain large container archives. Artifacts exclude fixture credentials, signing keys, kubeconfig, raw data and all `.env` files. The Docker context is allowlisted. GitHub run logs retain individual test outcomes; release JSON records commit, previous/new image, target environment, status and UTC times. Container archives expire after three days unless cleaned earlier, public evidence after fourteen; durable verification summaries belong in `docs/verification/`. If image artifacts have expired or been removed, rerun the entire selected workflow to rebuild and revalidate them before publishing.

The acceptance runner deletes its own cluster/registry in `finally`; GitHub also disposes the hosted VM. To remove AWS setup, disable the commit allowlist, verify tagged ownership, explicitly archive/delete images in `alex-ci-api`, then review and apply destruction of **only** `terraform/10_ci`. Do not remove an externally supplied OIDC provider or unrelated repositories.

Keep Terraform state in a private backup or secure handoff; it is not committed. When moving computers, restore that state (or deliberately import the owned resources) before applying. An empty repository can remain alongside IAM/OIDC configuration for later releases without retaining billable image storage.

References: [GitHub AWS OIDC](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws), [workflow permissions](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax), [Kubernetes rollout behavior](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/).
