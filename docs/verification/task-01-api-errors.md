# Task 01: API errors and user isolation

Issue: [#3](https://github.com/husky0787/Alex/issues/3). Verified locally on 2026-10-25.

## Result

CloudFront configuration now preserves origin `403`/`404` status codes and bodies. Both `/api` and `/api/*` go to API Gateway, forward Authorization, and have zero cache TTL. Error-cache minimum TTL is also zero. API responses are never rewritten by the static-page function.

The default S3 behavior uses a viewer-request CloudFront Function to resolve clean page URLs to their actual Next.js export objects: `/dashboard` becomes `/dashboard.html`, and `/accounts/<id>` uses `/accounts/[id].html` (URI-encoded brackets). The browser URL and query string remain available to the client-side router. Assets remain unchanged; unknown pages are not redirected to the homepage.

Five API operations now re-raise intentional HTTP errors before handling unexpected failures: update profile, create account, analyze, reset accounts, and populate test data. A missing profile stays `404`; a genuine database failure stays a sanitized JSON `500`.

## Reproduced defects and verification

| Check | Before | After |
| --- | --- | --- |
| Terraform origin error contract | Failed: both 403/404 mapped to 200 + index.html | Passed: no response replacement |
| Five profile-required API operations | Five failing subcases: expected 404, got 500 | All return JSON 404 |
| Static routing | Missing exact `/api` routing and static-only function association | Mocked plan passes all five assertions |
| API HTTP suite | Regression reproduced before implementation | 10 test methods pass, including parameterized subcases |
| Edge JavaScript + production export | Routing edge cases failed before implementation | 16 tests pass; exported page targets exist |
| Terraform | — | `validate`, mocked `test`, and changed-file `fmt -check` pass |
| Frontend | — | Production build, TypeScript checks and static export pass |

The HTTP suite exercises real FastAPI routing, Clerk bearer/JWT verification with ephemeral RS256 keys, and database adapters. It substitutes the external JWKS HTTP response and AWS Data API/SQS boundaries; it does not bypass authentication or replace ownership checks. Cases cover missing/malformed/expired/forged tokens, own profile/accounts/positions/jobs, other-user account/position writes and reads, nonexistent routes/resources, validation errors, and sanitized database failures. No real AWS request is allowed by the suite.

Existing non-blocking warnings: an unused `Link` import in `frontend/components/ErrorBoundary.tsx`, and deprecated Pydantic `Field(example=...)` usage in existing schemas. No dependency version was upgraded; the Terraform lockfile only gained the checksum for the tested Windows provider package.

## Run locally

Prerequisites: Node/npm, uv with Python 3.12, Terraform >= 1.7 (mock-provider tests), and the locked AWS provider installed. The checked environment used Node 24.15.0, Python 3.12.14, Terraform 1.16.4, and AWS provider 5.100.0.

From `backend/api`:

```sh
uv sync --locked --package api
uv run --locked --package api -m unittest test_error_contract -v
```

From `frontend`:

```sh
npm ci --no-audit --no-fund
npm run build
```

The build requires `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`. For this offline export check, set it to the test-only placeholder `pk_test_Y2xlcmsuZXhhbXBsZS50ZXN0JA`. This is not a working Clerk instance and must not be used for deployment. For example, PowerShell: `$env:NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY='pk_test_Y2xlcmsuZXhhbXBsZS50ZXN0JA'`.

From `terraform/7_frontend`:

```sh
terraform init -backend=false -input=false
terraform fmt -check main.tf tests/routing.tftest.hcl
node --test tests/static_routes.test.cjs tests/export_routes.test.cjs
```

From `backend/api`, run the isolated Terraform validator/test runner:

```sh
uv run --project .. --locked --package api ../../terraform/7_frontend/tests/run_tests.py
```

The runner copies the module into a temporary tree, excludes local state and variable files, and creates a test-only Lambda ZIP there. It reuses the initialized provider directory. Remote state and AWS resources are mocked; no `apply`, deployment ZIP, or live database is used.

On the checked Windows machine, uv is at `D:/learn/production/.tools/uv/uv.exe`, with `UV_CACHE_DIR=D:/learn/production/.tools/uv-cache` to avoid a cross-drive cache rename error.

## Deferred cloud acceptance

This change has **not been deployed**. The local test matrix proves application behavior and planned infrastructure configuration; it does not prove a deployed CloudFront response or a live Clerk login.

During the separately planned short cloud acceptance window, deploy the real Lambda package and frontend built with the actual public Clerk key, publish the function/distribution changes, and invalidate old cached responses. Verify through the deployed CloudFront hostname:

- Sign in as user A: own profile, accounts, positions and jobs load.
- No token or expired token: a protected API returns an error status and JSON.
- User A accessing user B's account/position/job: JSON 403, without B's data.
- Unknown API, including `/api`: JSON 404, not 200 or homepage HTML.
- Refresh `/dashboard` and `/accounts/<id>` directly: the intended page loads and account ID reaches the client-side router.
- `/_next/` assets still load; an unknown static page is not a successful homepage.

CloudFront's native error response for an unknown static page may be HTML with an error status. The JSON requirement applies to API routes.

References: [CloudFront status/error behavior](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/HTTPStatusCodes.html), [viewer-request URI rewriting](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/example_cloudfront_functions_url_rewrite_single_page_apps_section.html), [Terraform provider mocking](https://developer.hashicorp.com/terraform/language/tests/mocking).
