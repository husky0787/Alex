# Alex Issues So Far

Last updated: 2026-09-01

This document records the issues encountered while working through Guides 5 and 6, their root causes, the fixes applied, and the verification results.

## Current Status

| Area | Status | Notes |
| --- | --- | --- |
| Aurora PostgreSQL | Working | Cluster and Data API were verified after the database was recreated. |
| Database schema | Working | All 17 migration statements completed. |
| Seed and test data | Working | 22 ETFs and the Guide 6 test user were loaded. |
| Tagger local test | Working | VTI classification succeeds, including retry coverage for invalid model output. |
| Retirement local test | Working | Test completed with status 200 after the Data API became available. |
| Lambda packages | Working | All five agent ZIP files were built successfully. |
| OpenAI tracing | Disabled for local tests | Bedrock inference still works; only optional OpenAI trace export is disabled. |
| LangFuse | Not configured yet | This is introduced in Guide 8. |

## 1. Terraform Was Run from the Wrong Directory

### Symptom

From `backend/tagger`, this command failed:

```bash
cd terraform/5_database
terraform apply
```

The shell reported that the directory did not exist, then Terraform reported `No configuration files`.

### Root Cause

`terraform/5_database` is relative to the repository root, not to `backend/tagger`. Because `cd` failed, `terraform apply` ran in the wrong directory.

### Correct Command

From the repository root:

```bash
cd terraform/5_database
terraform apply
```

From `backend/tagger`:

```bash
cd ../../terraform/5_database
terraform apply
```

Always stop after a failed `cd`; do not run Terraform in the unintended directory.

## 2. Aurora Data API Was Not Available

### Symptoms

Database calls failed with one of these errors:

```text
DBClusterNotFoundFault: DBCluster alex-aurora-cluster not found
HttpEndpointNotEnabledException: HttpEndpoint is not enabled for resource ...
```

This affected database tests, migrations, Tagger updates, and the Retirement agent.

### Root Cause

The original Aurora cluster had been destroyed. During recreation, the cluster either did not exist yet or was not fully available to the Data API. A later Retirement failure was transient: AWS subsequently reported the cluster as `available` with the HTTP endpoint enabled.

### Resolution and Verification

The database infrastructure was recreated from `terraform/5_database`. The following were then verified:

- The cluster status was `available`.
- `HttpEndpointEnabled` was `true`.
- `uv run test_data_api.py` completed successfully.
- The expected database tables were present.

If this error returns, check the live AWS state before changing code:

```bash
aws rds describe-db-clusters \
  --db-cluster-identifier alex-aurora-cluster \
  --query 'DBClusters[0].{Status:Status,HttpEndpointEnabled:HttpEndpointEnabled,DBClusterArn:DBClusterArn}'
```

## 3. Stale Secrets Manager ARN After Database Recreation

### Symptom

The Data API test failed with:

```text
SecretsErrorException: The secret ... wasn't found
```

### Root Cause

Recreating the Terraform database generated a new Secrets Manager secret with a new ARN suffix. The root `.env` file still referenced the secret belonging to the destroyed cluster.

### Resolution

The current secret ARN was obtained from Terraform output and written to the root `.env` file. Do not copy an old ARN from terminal history.

```bash
cd terraform/5_database
terraform output
```

Then confirm that these values in `.env` match the current Terraform outputs:

```text
DB_CLUSTER_ARN=...
DB_SECRET_ARN=...
```

The actual secret value and full ARN are intentionally not recorded in this document.

## 4. Database Schema, Seed Data, and Test Data

### Symptom

The Reporter test failed while inserting a job:

```text
insert or update on table "jobs" violates foreign key constraint
"jobs_clerk_user_id_fkey"
```

### Root Cause

The `jobs.clerk_user_id` value used by `test_simple.py` must already exist in the users table. Loading the 22 ETF seed records does not create the Guide 6 test user (`test_user_001`).

### Resolution

After migrations, the database was reset with test data:

```bash
cd backend/database
uv run reset_db.py --with-test-data
```

This command is destructive: it resets database contents before loading seed and test data. It should only be run when losing the current development data is acceptable.

The test user was then confirmed to exist.

## 5. Tagger Rejected Invalid Structured Model Output

### Symptom

Nova Pro returned a valid-looking classification for VTI, but its sector percentages summed to `103.1` instead of `100.0`. Pydantic rejected the result:

```text
Sector allocations must sum to 100.0, got 103.10000000000001
```

The original handler logged the error but still returned status 200 with:

```text
Tagged: 0 instruments
Updated: []
```

### Root Cause

LLM output is probabilistic. The validation correctly detected an inconsistent allocation, but the retry policy only handled rate-limit errors. The OpenAI Agents SDK surfaced structured-output validation failures as `ModelBehaviorError`, so the invalid result was not retried. The batch also treated a complete classification failure as a successful request.

### Fix

The following changes were made in `backend/tagger/agent.py`:

- Retry both `RateLimitError` and `ModelBehaviorError`.
- Retry invalid classifications up to five attempts.
- Raise an error when every requested instrument fails instead of returning a false success.

A focused regression test was added at `backend/tagger/test_retry.py` for:

- Invalid first response followed by a valid response.
- Five invalid responses resulting in a failure.

### Verification

```bash
cd backend/tagger
uv run test_retry.py
uv run test_simple.py
```

Results:

- Both retry tests passed.
- The VTI local test returned status 200.
- One instrument was tagged and VTI was updated.

## 6. OpenAI Tracing Returned 401

### Symptom

Agent runs using Bedrock printed a non-fatal warning:

```text
Tracing client error 401: Incorrect API key provided: sk-...
```

### Root Cause

Nova Pro inference runs through LiteLLM and AWS Bedrock. Separately, the OpenAI Agents SDK attempts to export tracing telemetry to OpenAI when tracing is enabled. The `.env` file contained a placeholder OpenAI key, so only trace export failed.

This was not a Bedrock authentication failure and did not cause the LLM classification error.

### Resolution

Disable optional OpenAI tracing for local Bedrock tests:

```bash
OPENAI_AGENTS_DISABLE_TRACING=1 uv run test_simple.py
```

`backend/tagger/test_simple.py` now disables tracing by default unless the environment explicitly overrides it.

OpenAI tracing is used for agent-run telemetry such as timing, model calls, tool calls, and errors. LangFuse is a separate observability integration covered in Guide 8.

## 7. Retirement Test Hit a Transient Data API Error

### Symptom

The Retirement test failed before invoking the agent because creating its database job raised `HttpEndpointNotEnabledException`.

### Diagnosis

After the failure, read-only AWS checks showed:

- Aurora status: `available`
- Data API HTTP endpoint: enabled
- Database connection test: passed
- `test_user_001`: present

No later cluster modification event explained a configuration change, so the exact transient AWS timing condition could not be proven.

### Verification

The unchanged Retirement test was rerun and passed with status 200, produced the retirement analysis, and deleted its temporary test job. No code workaround was added because the database configuration was healthy.

## 8. uv Hardlink Warning

### Symptom

During dependency installation, uv reported:

```text
Failed to hardlink files; falling back to full copy.
```

### Root Cause

In Codespaces, the uv cache and project virtual environment can be on different filesystems. Hardlinks cannot cross filesystem boundaries, so uv copies files instead.

### Impact and Resolution

This is harmless. It can make installation slightly slower and consume more disk space, but it does not affect application behavior.

Suppress the warning with either:

```bash
UV_LINK_MODE=copy uv run test_simple.py
```

or:

```bash
export UV_LINK_MODE=copy
```

## 9. Lambda Packaging Cleanup Permission Error

### Symptom

`backend/package_docker.py` reported that the Tagger package was created, then failed while deleting its temporary directory:

```text
PermissionError: [Errno 13] Permission denied: 'remove_none_from_dict.py'
PermissionError: [Errno 1] Operation not permitted: '/tmp/.../package/cohere/core'
```

It also printed a nested uv environment warning.

### Root Cause

This was a local Linux filesystem ownership problem, not an AWS IAM permission problem. The Lambda Docker container wrote some mounted files as `nobody:nogroup`, while the host process ran as `codespace`. The host could create the ZIP but could not remove all container-created temporary files afterward.

The `VIRTUAL_ENV ... does not match the project environment path` warning was unrelated.

### Fix

The Docker packaging scripts for all five Lambda agents now pass the host UID and GID on POSIX systems:

```text
docker run --user <host-uid>:<host-gid> ...
```

Updated scripts:

- `backend/tagger/package_docker.py`
- `backend/reporter/package_docker.py`
- `backend/charter/package_docker.py`
- `backend/retirement/package_docker.py`
- `backend/planner/package_docker.py`

Windows behavior remains unchanged because UID/GID arguments are only added on POSIX systems.

### Verification

From `backend`:

```bash
UV_LINK_MODE=copy uv run package_docker.py
```

All five packages completed successfully:

- Tagger
- Reporter
- Charter
- Retirement
- Planner

## Remaining Notes

- Guide 6 Lambda deployment and remote `test_full.py` verification are still separate from the successful local tests and ZIP packaging.
- LangFuse activation belongs to Guide 8. The five Lambda agents already contain observability integration points, but credentials and deployment configuration are not yet complete.
- Aurora Serverless is the largest ongoing project cost. Check AWS billing regularly and destroy `terraform/5_database` when it is no longer needed.
- Do not commit `.env`, Terraform state, AWS credentials, API keys, or secret values.
