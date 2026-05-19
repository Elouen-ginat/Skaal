# Non-regression deploy: maintainer runbook

The `Non-regression deploy` workflow in `.github/workflows/nonregression.yml`
deploys real infrastructure on `main`. This is the shortest path to wiring the
required GitHub variables and cloud identity.

Goal: no long-lived AWS or GCP keys in GitHub. AWS and GCP both use GitHub OIDC.
The only optional stored secret is `PULUMI_ACCESS_TOKEN` when using Pulumi Cloud.

## What you must create

### GitHub variables

Add these under `Settings -> Secrets and variables -> Actions -> Variables`:

- `SKAAL_NONREGRESSION_GCP_PROJECT`
- `SKAAL_NONREGRESSION_AWS_REGION` if you do not want the default `us-east-1`
- `SKAAL_NONREGRESSION_GCP_REGION` if you do not want the default `us-central1`

### GitHub secrets

Add these under `Settings -> Secrets and variables -> Actions -> Secrets`:

- `AWS_NONREGRESSION_ROLE_ARN`
- `GCP_WORKLOAD_IDENTITY_PROVIDER`
- `GCP_NONREGRESSION_SERVICE_ACCOUNT`
- `PULUMI_ACCESS_TOKEN` only if using Pulumi Cloud as the state backend

## AWS setup

### 1. Create the GitHub OIDC provider once per AWS account

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

### 2. Create or update the IAM role trust policy

Save this as `trust-policy.json`. Replace `ACCOUNT_ID` with your AWS account ID.
The repo slug is already filled in for this repository.

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
        "token.actions.githubusercontent.com:sub": "repo:Elouen-ginat/Skaal:ref:refs/heads/main"
      }
    }
  }]
}
```

Create the role:

```bash
aws iam create-role \
  --role-name skaal-nonregression-gha \
  --assume-role-policy-document file://trust-policy.json
```

If the role already exists:

```bash
aws iam update-assume-role-policy \
  --role-name skaal-nonregression-gha \
  --policy-document file://trust-policy.json
```

### 3. Attach the permissions policy

The repo ships a ready-to-attach least-privilege policy at
[`notes/nonregression-aws-policy.json`](nonregression-aws-policy.json). It
covers everything the AWS deploy path provisions for `examples/todo_api`
and `examples/nonregression_kitchen_sink` — Lambda, API Gateway v2,
DynamoDB, RDS, S3, ECR, IAM (`CreateRole` / `PassRole` scoped to
`role/skaal-*`), EventBridge, EventBridge Scheduler, SQS, Secrets Manager,
CloudWatch Logs, and the read-only `tag:GetResources` for the deep leak
sweep.

Attach it as an inline policy on the role:

```bash
aws iam put-role-policy \
  --role-name skaal-nonregression-gha \
  --policy-name skaal-nonregression \
  --policy-document file://notes/nonregression-aws-policy.json
```

The `iam:CreateRole` / `iam:PassRole` statements are scoped to
`arn:aws:iam::*:role/skaal-*` so this role can only create / hand off
roles that follow Skaal's naming convention. Do not attach
`AdministratorAccess` — the throwaway stack should not be able to delete
your other AWS resources if the test goes wrong.

### 4. Copy the role ARN into GitHub

Read it with:

```bash
aws iam get-role --role-name skaal-nonregression-gha --query 'Role.Arn' --output text
```

Store that value as `AWS_NONREGRESSION_ROLE_ARN`.

## GCP setup

### 1. Enable the required APIs

```bash
gcloud services enable \
  iamcredentials.googleapis.com \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  firestore.googleapis.com \
  artifactregistry.googleapis.com
```

### 2. Create the workload identity pool and provider

```bash
gcloud iam workload-identity-pools create skaal-nonregression \
  --location=global \
  --display-name="Skaal non-regression"

gcloud iam workload-identity-pools providers create-oidc github \
  --workload-identity-pool=skaal-nonregression \
  --location=global \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
  --attribute-condition="assertion.repository==\"Elouen-ginat/Skaal\""
```

### 3. Create the service account

```bash
gcloud iam service-accounts create skaal-nonregression \
  --display-name="Skaal non-regression deploy"
```

Grant it only the roles needed for the GCP deploy path, typically:

- Cloud Run admin
- Firestore admin
- Artifact Registry writer
- Service Account User on itself

### 4. Bind the GitHub principal to the service account

Find the project number and service account email:

```bash
gcloud config get-value project
gcloud projects describe PROJECT_ID --format="value(projectNumber)"
gcloud iam service-accounts list --format="value(email)" --filter="email:skaal-nonregression@"
```

Then bind the `main` branch principal:

```bash
gcloud iam service-accounts add-iam-policy-binding SA_EMAIL \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/skaal-nonregression/attribute.ref/refs/heads/main"
```

### 5. Copy the two GitHub secret values

Store these in GitHub Secrets:

- `GCP_WORKLOAD_IDENTITY_PROVIDER` = `projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/skaal-nonregression/providers/github`
- `GCP_NONREGRESSION_SERVICE_ACCOUNT` = `SA_EMAIL`

Also set `SKAAL_NONREGRESSION_GCP_PROJECT` to the active project ID in GitHub Variables.

## Pulumi

If the workflow uses Pulumi Cloud state, add `PULUMI_ACCESS_TOKEN` as a GitHub Secret.
If the workflow uses local state, skip this.

## Local target

The `local` non-regression job needs no cloud credentials.

## Troubleshooting

### `Could not assume role with OIDC: Request ARN is invalid`

`AWS_NONREGRESSION_ROLE_ARN` is set to a value that is not a valid IAM role
ARN. Re-read it with:

```bash
aws iam get-role --role-name skaal-nonregression-gha --query 'Role.Arn' --output text
```

The output must start with `arn:aws:iam::` followed by a 12-digit account
id, `:role/`, and the role name. Copy that exact string into the secret —
any trailing whitespace, newline, or accidental quoting fails the regex
that `aws-actions/configure-aws-credentials` runs.

### `skaal deploy ... returned non-zero exit status 1` with no detail

The `_run` helper in `tests/nonregression/conftest.py` attaches the
captured stdout/stderr as a PEP 678 note. If you don't see it in the pytest
failure section, you are on a pytest older than 7.4 — upgrade or re-run
with `-rA` to force notes to render.

### Interactive confirmation prompt aborts the deploy

`skaal deploy` defaults to prompting for confirmation. The non-regression
suite passes `--yes`; if you reproduce the workflow's deploy step manually
you must do the same, or run inside a TTY.

## Optional local repro

```bash
SKAAL_NONREGRESSION_LOCAL=1 uv run pytest tests/nonregression/test_local_deploy.py
SKAAL_NONREGRESSION_AWS=1 uv run pytest tests/nonregression/test_aws_deploy.py
SKAAL_NONREGRESSION_GCP=1 SKAAL_NONREGRESSION_GCP_PROJECT=my-sandbox uv run pytest tests/nonregression/test_gcp_deploy.py
```

## Leak detection

Every test wraps its stack in `deployed_stack(...)` from
`tests/nonregression/conftest.py`. After teardown, the helper runs a
two-tier leak sweep before the test is allowed to pass:

1. **Pulumi-state sweep (always on).** Reads the stack state after destroy
   and lists every resource still tracked beyond the stack root. A clean
   destroy leaves only `pulumi:pulumi:Stack`; anything else is a leak.
   Runs unconditionally — no cloud SDK needed because the state file is
   local to the runner.
2. **Provider-side tag sweep (opt-in).** When
   `SKAAL_NONREGRESSION_DEEP_LEAK_CHECK=1` is set:
   - AWS: calls `resourcegroupstaggingapi:GetResources` filtering on
     `skaal:app` + `skaal:env`, expects zero matches.
   - GCP: calls Cloud Asset Inventory `searchAllResources` filtering on
     `labels.skaal_app` + `labels.skaal_env`, expects zero matches.

The CI workflow exports `SKAAL_NONREGRESSION_DEEP_LEAK_CHECK=1` on the
`aws` and `gcp` jobs. The local job does not — it relies on the
Pulumi-state sweep alone.

### Extra IAM permissions required for the deep sweep

Add these to the role bound to the workflow's OIDC principal:

- AWS: `tag:GetResources` on `*`.
- GCP: `cloudasset.assets.searchAllResources` on the project (granted by
  `roles/cloudasset.viewer`).

These are read-only and scoped to the project / account that hosts the
throwaway stack. They are needed at every run, not just on failure.

## Cleanup if a run leaks infrastructure

The Pulumi-state sweep prints the URNs it found stuck. Use them to drive
manual cleanup:

```bash
pulumi -C .skaal/build/<env> stack select <env>
pulumi -C .skaal/build/<env> destroy --yes
pulumi -C .skaal/build/<env> stack rm <env> --yes
```

If the deep sweep flags resources that the Pulumi state does not, the
state file and reality have drifted. Open the leak report, find each
ARN / resource name, and delete it directly through the provider console
or CLI. File a bug — Skaal's destroy path should never miss a resource
it tagged.
