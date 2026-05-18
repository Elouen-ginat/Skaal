# Non-regression deploy: credentials & worker setup

The `Non-regression deploy` workflow (`.github/workflows/nonregression.yml`)
provisions real infrastructure on every supported `Target` after each merge to
`main`. This document is the checklist a maintainer follows to wire the
GitHub-Actions worker up to AWS, GCP, and Pulumi.

The design goal is **no long-lived secrets in GitHub**: AWS and GCP both
authenticate via OIDC, exchanging the run's `id-token` for a short-lived
session. The only stored secret is the optional `PULUMI_ACCESS_TOKEN` used to
persist the Pulumi state backend; if you run with `pulumi login --local`,
that can be dropped too.

## Repository configuration

### GitHub Variables (`Settings → Variables → Actions`)

| Name                              | Example                  | Purpose                            |
|-----------------------------------|--------------------------|------------------------------------|
| `SKAAL_NONREGRESSION_AWS_REGION`  | `us-east-1`              | AWS region for the throwaway stack |
| `SKAAL_NONREGRESSION_GCP_PROJECT` | `skaal-nonregression`    | GCP project that hosts the stack   |
| `SKAAL_NONREGRESSION_GCP_REGION`  | `us-central1`            | GCP region for Cloud Run           |

### GitHub Secrets (`Settings → Secrets → Actions`)

| Name                                  | Required for | Notes                                                                 |
|---------------------------------------|--------------|-----------------------------------------------------------------------|
| `AWS_NONREGRESSION_ROLE_ARN`          | AWS job      | IAM role the OIDC provider can assume. See "AWS setup" below.         |
| `GCP_WORKLOAD_IDENTITY_PROVIDER`      | GCP job      | Full resource name of the WIF provider, e.g. `projects/.../providers/github`. |
| `GCP_NONREGRESSION_SERVICE_ACCOUNT`   | GCP job      | Service-account email the WIF provider is bound to.                   |
| `PULUMI_ACCESS_TOKEN`                 | AWS + GCP    | Token for the Pulumi Cloud state backend. Omit if you switch to `pulumi login --local`. |

## AWS setup (OIDC)

1. **Add GitHub as an OIDC provider** in IAM (one-time, account-wide):

   ```bash
   aws iam create-open-id-connect-provider \
     --url https://token.actions.githubusercontent.com \
     --client-id-list sts.amazonaws.com \
     --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
   ```

2. **Create the role** the workflow assumes. Trust policy (replace
   `OWNER/Skaal`):

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{
       "Effect": "Allow",
       "Principal": {
         "Federated": "arn:aws:iam::ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
       },
       "Action": "sts:AssumeRoleWithWebIdentity",
       "Condition": {
         "StringEquals": {
           "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
         },
         "StringLike": {
           "token.actions.githubusercontent.com:sub": "repo:OWNER/Skaal:ref:refs/heads/main"
         }
       }
     }]
   }
   ```

3. **Attach a least-privilege managed policy.** For the `todo_api` example the
   role needs: Lambda + IAM (function role passing), API Gateway, DynamoDB,
   CloudWatch Logs, ECR (for the container image), and tagging. Start from
   the policies under `docs/deploy/aws/` and trim. Do **not** attach
   `AdministratorAccess` — orphaned resources from a failed teardown cost
   real money.

4. **Store the role ARN** as the `AWS_NONREGRESSION_ROLE_ARN` repo secret.

## GCP setup (Workload Identity Federation)

1. **Enable APIs** in the target project:

   ```bash
   gcloud services enable \
     iamcredentials.googleapis.com \
     run.googleapis.com \
     cloudbuild.googleapis.com \
     firestore.googleapis.com \
     artifactregistry.googleapis.com
   ```

2. **Create the WIF pool and provider** (one-time, project-scoped):

   ```bash
   gcloud iam workload-identity-pools create skaal-nonregression \
     --location=global --display-name="Skaal non-regression"

   gcloud iam workload-identity-pools providers create-oidc github \
     --workload-identity-pool=skaal-nonregression \
     --location=global \
     --issuer-uri="https://token.actions.githubusercontent.com" \
     --attribute-mapping='google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref' \
     --attribute-condition='assertion.repository=="OWNER/Skaal"'
   ```

3. **Create the service account** with the smallest set of roles that lets
   the example deploy (Cloud Run admin, Firestore admin, Artifact Registry
   writer, Service-account-user on itself).

4. **Bind the WIF principal to the service account** so the OIDC token can
   impersonate it (restricted to merges into `main`):

   ```bash
   gcloud iam service-accounts add-iam-policy-binding \
     SA_EMAIL \
     --role=roles/iam.workloadIdentityUser \
     --member="principalSet://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/skaal-nonregression/attribute.ref/refs/heads/main"
   ```

5. **Store the provider name and SA email** as `GCP_WORKLOAD_IDENTITY_PROVIDER`
   and `GCP_NONREGRESSION_SERVICE_ACCOUNT` repo secrets.

## Local target

The `local` job runs without cloud credentials — it provisions inside the
runner's filesystem and serves on `127.0.0.1:8000`. No secrets required.

## Running it locally

To reproduce the workflow on your laptop:

```bash
# Local target only (no creds required):
SKAAL_NONREGRESSION_LOCAL=1 \
  uv run pytest tests/nonregression/test_local_deploy.py

# AWS (with ambient `aws sso login` or `AWS_PROFILE`):
SKAAL_NONREGRESSION_AWS=1 \
  uv run pytest tests/nonregression/test_aws_deploy.py

# GCP (with `gcloud auth application-default login`):
SKAAL_NONREGRESSION_GCP=1 \
SKAAL_NONREGRESSION_GCP_PROJECT=my-skaal-sandbox \
GOOGLE_APPLICATION_CREDENTIALS=$HOME/.config/gcloud/application_default_credentials.json \
  uv run pytest tests/nonregression/test_gcp_deploy.py
```

Setting `SKAAL_RUN_NONREGRESSION=1` opts every gate in at once — that's the
flag the CI workflow exports.

## Teardown guarantees

Every test wraps its deployed stack in `tests/nonregression/conftest.py`'s
`deployed_stack(...)` context manager. The `finally` clause runs
`skaal destroy --yes --env <env> <app_spec>`; if the CLI invocation fails,
it falls back to the Pulumi automation API to destroy and remove the stack.
If both fail, the test itself fails with `pytrace=False` and a message
naming the dangling stack, so the maintainer is alerted before drift
accumulates.

If you spot an orphaned stack from an aborted CI run, destroy it manually:

```bash
pulumi -C .skaal/build/<env> stack select <env>
pulumi -C .skaal/build/<env> destroy --yes
pulumi -C .skaal/build/<env> stack rm <env> --yes
```
