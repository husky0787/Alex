# Controlled delivery

Every main-branch push and pull request update runs PostgreSQL market-data integration, API JWT/ownership contracts, frontend tests/lint/type-check/build and release failure tests. Only after both backend and frontend pass does CI build the API/ETL image from the locked backend workspace. Actions are pinned to commit SHAs; ordinary jobs have only `contents: read`, no cloud credentials and no paid-model calls.

CI builds the checked-out commit and its parent, records their Git revisions, image IDs and archive SHA256 values, then deploys immutable registry digests to disposable k3d. The runner verifies one healthy release and an intentionally missing digest. The shared release tool restores the previous healthy template on failure, rechecks readiness, and returns a nonzero exit code even after recovery. Authenticated smoke tests run after both outcomes. It refuses mutable tags, unhealthy rollback baselines and concurrent template overwrites. No database migration runs during image rollout; existing fixture data and schema remain in place.

## Controlled AWS publishing

`terraform/10_ci` provisions an ECR repository, lifecycle rule, IAM role/policy and (only when absent) the GitHub OIDC provider. The role can push/pull **only** `alex-ci-api`; registry authentication requires the AWS-defined wildcard resource. It cannot create EKS, access application secrets/data or delete images. Trust requires the exact `husky0787/Alex` repository, `alex-acceptance` environment and STS audience. Set `existing_oidc_provider_arn` to reuse an existing shared provider without importing it into this state.

This repository uses GitHub's immutable OIDC subject format. The verified API response (`GET repos/husky0787/Alex/actions/oidc/customization/sub`) reports prefix `repo:husky0787@180300086/Alex@1355610076`; Terraform appends `:environment:alex-acceptance`. Do not substitute older name-only examples or a wildcard. For a fork, explicitly verify its owner/repository IDs and update the exact trust condition before applying.

Configure the GitHub `alex-acceptance` environment with selected deployment branches (normally only `main`; explicitly allow a reviewed implementation branch for initial acceptance). Set these non-secret environment variables:

- `ALEX_RELEASE_ROLE_ARN`: Terraform's role output.
- `ALEX_ECR_REPOSITORY`: Terraform's repository URL.
- `ALEX_AWS_ACCOUNT_ID`: expected account, checked by the credentials action.

Publishing is disabled unless the repository variable **`ALEX_RELEASE_COMMIT` equals the full workflow commit SHA**. Once the workflow is merged, select an exact reviewed main commit and manually dispatch it; PR events cannot release. Environment branch rules permit only main. Initial implementation acceptance temporarily allowed the reviewed feature branch; that exception was removed after verification.

```text
gh variable set ALEX_RELEASE_COMMIT --repo husky0787/Alex --body FULL_MAIN_COMMIT
gh workflow run ci.yml --repo husky0787/Alex --ref main
```

If main changes between selection and dispatch, the mismatch prevents publishing. Remove the variable after the bounded acceptance. The release job waits for every test and local rollout to pass, obtains a 30-minute OIDC session, checks and loads the tested archives (no rebuild), pushes unique immutable tags and deploys the returned ECR digests into a new disposable runner cluster. No static AWS access key is stored in GitHub.

The hosted-runner cluster exercises delivery and rollback with PostgreSQL/JWKS/AWS transport fixtures. It is **not EKS** and does not claim a new Aurora/SQS integration or Clerk browser login. Task 9 separately records those scoped AWS integration checks. AWS cost for this workflow is small ECR storage/requests/transfer, not an EKS deployment. Review current credit, retention and total account consumption before enabling release. The ten-image lifecycle is a retention limit, not a cost cap. GitHub public-repository standard hosted runners are used.

## Existing EKS environments

`release.py` also accepts an operator's explicit EKS kubeconfig/context, namespace and reachable API URL:

```text
uv run --no-project deploy/ci/release.py --kubeconfig PRIVATE_KUBECONFIG --context EXPLICIT_CONTEXT --namespace alex-cloud --image ECR_URL@sha256:DIGEST --commit FULL_COMMIT --url HTTPS_API --evidence PRIVATE_EVIDENCE_JSON
```

Run from a Linux deployment host with network access and namespace-scoped Kubernetes `get/patch/watch` access to the API Deployment. API image and its previous healthy image must both use digests. This tool performs no EKS provisioning, endpoint firewall changes or migrations; the ECR-only GitHub role deliberately cannot perform these operations. EKS release execution remains an operator step in an approved cloud window. CI evidence must not be described as an automated EKS deployment.

## Database and evidence boundaries

Schema changes use expand/contract: first add compatible nullable columns/tables or compatible defaults, verify both old and new application images on that schema, and only remove old fields in a later release after the rollback window. Destructive migrations are never coupled to image rollback. This task has no schema migration; the delivery drill checks schema equality and persisted API behavior.

Public Actions artifacts contain only safe release JSON and, for an explicitly selected release commit, compressed immutable image archives and their checksum/commit manifest. Ordinary CI does not retain large container archives. Artifacts exclude fixture credentials, signing keys, kubeconfig, raw data and all `.env` files. The Docker context is allowlisted. GitHub run logs retain individual test outcomes; release JSON records commit, previous/new image, target environment, status and UTC times. Container archives expire after three days unless cleaned earlier, public evidence after fourteen; durable verification summaries belong in `docs/verification/`. If image artifacts have expired or been removed, rerun the entire selected workflow to rebuild and revalidate them before publishing.

The acceptance runner deletes its own cluster/registry in `finally`; GitHub also disposes the hosted VM. To remove AWS setup, disable the commit allowlist, verify tagged ownership, explicitly archive/delete images in `alex-ci-api`, then review and apply destruction of **only** `terraform/10_ci`. Do not remove an externally supplied OIDC provider or unrelated repositories.

Keep Terraform state in a private backup or secure handoff; it is not committed. When moving computers, restore that state (or deliberately import the owned resources) before applying. An empty repository can remain alongside IAM/OIDC configuration for later releases without retaining billable image storage.

References: [GitHub AWS OIDC](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws), [workflow permissions](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax), [Kubernetes rollout behavior](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/).
