# Alex Issues So Far

Last updated: 2026-09-03

This document records the issues encountered while working through Guides 5, 6, 7, and 8, their root causes, the fixes applied, and the verification results.

## Current Status

| Area | Status | Notes |
| --- | --- | --- |
| Aurora PostgreSQL | Working | Cluster and Data API were verified after the database was recreated. |
| Database schema | Working | All 17 migration statements completed. |
| Seed and test data | Working | 22 ETFs and the Guide 6 test user were loaded. |
| Tagger local test | Working | VTI classification succeeds, including retry coverage for invalid model output. |
| Retirement local test | Working | Test completed with status 200 after the Data API became available. |
| Lambda packages | Working | All five agent ZIP files were built successfully. |
| Next.js local frontend | Working | Dependencies were rebuilt after a truncated SWC binary caused a native crash. |
| Dashboard local API loading | Working | Clerk authentication and all initial dashboard API requests were verified. |
| CloudWatch Agent Performance dashboard | Working | Lambda activity is visible in `alex-agent-performance`. |
| CloudWatch AI Model Usage dashboard | Bedrock working | The dashboard now queries the deployed Bedrock region and exact inference-profile model ID. SageMaker panels remain empty because the configured endpoint is not currently deployed in `us-east-1`. |
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

## 10. Next.js Failed with `Bus error (core dumped)`

### Symptom

The FastAPI backend started successfully, but the Next.js process stopped immediately:

```text
Frontend: > next dev
Frontend: Bus error (core dumped)
Frontend failed to start
```

The preceding uv hardlink and nested virtual-environment messages were warnings and were unrelated to the crash.

### Root Cause

The installed Next.js SWC native binaries were truncated. The active glibc binary was only `25,387,078` bytes, while the official `@next/swc-linux-x64-gnu@15.5.3` package contains a `142,917,576` byte binary. Its ELF header pointed beyond the end of the local file, and loading it directly exited with status 135 (`SIGBUS`).

An isolated download of the same package loaded successfully with Node.js 24.14.0, proving that the Node.js version and CPU architecture were not the cause. The likely trigger was the first `npm install` being interrupted by an `EAI_AGAIN` registry lookup failure and leaving partially extracted optional packages behind.

### Fix

Run the clean install from `frontend`, where `package-lock.json` is located:

```bash
cd frontend
npm ci --cache /tmp/alex-npm-repair-cache --prefer-online
```

Running `npm ci` from `scripts` fails with `EUSAGE` because that directory does not contain a lockfile.

### Verification

- 493 packages were installed successfully.
- The SWC binary size was `142,917,576` bytes.
- Requiring `@next/swc-linux-x64-gnu` succeeded.
- Next.js 15.5.3 compiled the application and served `/` with HTTP 200.

## 11. Dashboard Remained on an Empty Loading Skeleton

### Symptom

After Clerk sign-in, `/dashboard` displayed the navigation, `Dashboard` heading, disclaimer, and footer, but none of the dashboard cards or settings. The content area remained on its text-free loading skeleton indefinitely.

### Diagnosis

The infrastructure and token were checked independently before changing code:

- Clerk was loaded and reported an active user and session.
- `getToken()` returned an RS256 JWT with the expected issuer and `http://localhost:3000` authorized party.
- The token timestamps were valid, and its key ID existed in the configured Clerk JWKS.
- The public JWKS endpoint returned HTTP 200.
- Aurora Data API queries succeeded and all five expected tables existed.
- FastAPI health and authentication rejection checks responded normally.
- No dashboard request reached `/api/user` while the skeleton was stuck.

### Root Cause

The dashboard data effect returned before requesting a token whenever its Clerk hook state had not yet synchronized after the development Account Portal handoff. Although the underlying Clerk client already had a valid user and session, the early return left `loading` set to `true` and provided no retry or terminal state.

Local development also depended on the browser reaching FastAPI directly on port 8000. This is fragile in Codespaces because the frontend and backend ports may be forwarded independently.

### Fix

The Guide 7 frontend now:

- Calls `getToken()` from the dashboard effect instead of returning before the attempt.
- Ends the loading state explicitly when no token is available.
- Uses relative `/api/*` URLs in both development and production.
- Proxies `/api/*` from Next.js to `127.0.0.1:8000` only during development.
- Keeps static export enabled only for production, where CloudFront routes `/api/*` to API Gateway.

Updated files:

- `frontend/pages/dashboard.tsx`
- `frontend/lib/config.ts`
- `frontend/next.config.ts`

### Verification

After the change, the complete initial dashboard request chain succeeded:

```text
GET /api/user      200 OK
GET /api/accounts  200 OK
GET /api/jobs      200 OK
```

Additional verification:

- `npm run lint` completed with no errors; one pre-existing unused-import warning remains in `components/ErrorBoundary.tsx`.
- `tsc --noEmit` completed successfully.
- The local frontend and backend remained available at ports 3000 and 8000.

## 12. CloudWatch AI Model Usage Dashboard Had No Data

### Symptom

The `alex-agent-performance` dashboard displayed Lambda invocation and duration data, while all panels in `alex-ai-model-usage` appeared empty.

### Diagnosis

The working Agent Performance dashboard established that the Lambda functions had run and that CloudWatch access was working. Read-only AWS checks then found that the deployed Planner Lambda used:

```text
BEDROCK_REGION=us-west-2
BEDROCK_MODEL_ID=us.amazon.nova-pro-v1:0
```

However, the deployed AI Model Usage dashboard queried:

```text
region=us-east-1
ModelId=amazon.nova-pro-v1:0
```

CloudWatch Bedrock metrics are region-scoped and the `ModelId` dimension must match exactly. The dashboard's combination returned no data, while `us-west-2` with `us.amazon.nova-pro-v1:0` returned Bedrock invocation, token, and latency metrics.

### Root Cause

`terraform/8_enterprise/terraform.tfvars` did not match the Bedrock configuration deployed from Guide 6. It omitted the `us.` inference-profile prefix and selected the Lambda deployment region instead of the Bedrock runtime region.

The `region=us-east-1` value in the CloudWatch console URL was not the cause. Each metric widget has its own region, and the Bedrock widgets were incorrectly configured with `us-east-1`.

### Fix

The Guide 8 monitoring configuration was changed to:

```hcl
bedrock_region   = "us-west-2"
bedrock_model_id = "us.amazon.nova-pro-v1:0"
```

The same values were applied to `terraform/8_enterprise/terraform.tfvars.example` and the model variable default so that future deployments start with values consistent with Guide 6. Terraform then updated only `aws_cloudwatch_dashboard.ai_model_usage` in place.

### Verification

- The Terraform plan reported `0 to add, 1 to change, 0 to destroy`.
- The deployed dashboard JSON now uses `us-west-2` and `us.amazon.nova-pro-v1:0` for all three Bedrock panels.
- CloudWatch returned 13 recent datapoints, totaling 78,671 input tokens and 24,642 output tokens.
- Invocation latency data was also present; the latest checked point averaged about 3,214 ms.
- A final Terraform plan reported `No changes`.

When viewing historical data, select a time range that includes the most recent invocation. At verification time, the latest Bedrock datapoint was `2026-09-02 08:10 UTC`, so a three-day range displayed it.

### Separate SageMaker Status

The bottom SageMaker panels remain empty for a different reason: `alex-embedding-endpoint` does not currently exist in the configured `us-east-1` region, and no matching `AWS/SageMaker` invocation metrics were found there. Recreate the Guide 2 endpoint before expecting those panels to populate; this does not affect the repaired Bedrock panels.

## Remaining Notes

- Guide 6 Lambda deployment and remote `test_full.py` verification are still separate from the successful local tests and ZIP packaging.
- LangFuse activation belongs to Guide 8. The five Lambda agents already contain observability integration points, but credentials and deployment configuration are not yet complete.
- Aurora Serverless is the largest ongoing project cost. Check AWS billing regularly and destroy `terraform/5_database` when it is no longer needed.
- Do not commit `.env`, Terraform state, AWS credentials, API keys, or secret values.
