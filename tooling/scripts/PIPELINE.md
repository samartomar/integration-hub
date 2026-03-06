# CI/CD Pipelines

Two pipelines: **Dev** (continuous development) and **Prod** (production releases).

## Overview

| Pipeline | Branch | Target | Trigger |
|----------|--------|--------|---------|
| **Dev**  | `develop` | Dev account (674763518102) | Push/merge to `develop` |
| **Prod** | `main`    | Prod account (176772326927) | Merge to `main` |

Both pipelines use the same CodeStar connection. Pipelines run in the dev account; the prod pipeline assumes a role in the prod account to deploy.

## Pipeline URLs

- **Dev**: [poc-py-pipeline](https://us-west-2.console.aws.amazon.com/codesuite/codepipeline/pipelines/poc-py-pipeline/view)
- **Prod**: [poc-py-pipeline-prod](https://us-west-2.console.aws.amazon.com/codesuite/codepipeline/pipelines/poc-py-pipeline-prod/view)

To get the URL programmatically:

```powershell
aws cloudformation describe-stacks --stack-name PipelineStack `
  --query "Stacks[0].Outputs[?OutputKey=='PipelineUrl'].OutputValue" --output text
aws cloudformation describe-stacks --stack-name ProdPipelineStack `
  --query "Stacks[0].Outputs[?OutputKey=='PipelineUrl'].OutputValue" --output text
```

---

## One-Time Setup: Prod Deploy Role

Before the prod pipeline can deploy, you must create a role in the **prod account** that the dev account's CodeBuild can assume.

### Why this is needed

CodeBuild runs in the dev account. IAM Identity Center gives *your user* access to both accounts, but CodeBuild uses a *service role* in the dev account—it does not use your SSO credentials. Cross-account deploy requires a dedicated role in prod that trusts the dev CodeBuild role.

### Deploy ProdDeployRoleStack in prod

1. Ensure CDK is bootstrapped in the prod account (use same qualifier as dev):
   ```powershell
   cdk bootstrap aws://176772326927/us-west-2 --qualifier intghub --profile prod
   ```
   (Use your IAM Identity Center profile for prod, e.g. `prod` or `aws-org-prod`.)

2. Deploy the role stack to prod:
   ```powershell
   cdk deploy ProdDeployRoleStack --profile prod --require-approval never
   ```

3. Confirm the role exists:
   ```powershell
   aws iam get-role --role-name ProdDeployRole --profile prod
   ```

---

## One-Time Setup: Prod Infrastructure

The prod pipeline deploys stacks to the prod account. Before the first pipeline run:

1. Deploy core stacks to **prod** (from your machine, with prod profile):
   ```powershell
   $env:USE_PREBUNDLED = "1"
   cdk deploy FoundationStack DatabaseStack OpsAccessStack --profile prod --require-approval never
   cdk deploy DataPlaneStack --profile prod --require-approval never
   ```

2. (Optional) Run migrations once if needed: SSM port-forward to prod bastion, or run `run-migrations.ps1` with prod DB env.

3. Admin routes use JWT (no x-admin-secret); configure IdP and API Gateway authorizer.

### VPC peering for prod migrations

The prod pipeline's Migrate stage runs in the dev account's VPC. To connect to prod Aurora for migrations, you need **VPC peering** between dev and prod:

- Peer dev VPC ↔ prod VPC
- Allow prod Aurora security group to accept connections from dev CodeBuild security group (or peering CIDR)

Without peering, migrations will fail when they try to reach prod Aurora. The first deploy can still succeed if you run migrations manually in prod before enabling the pipeline.

---

## Deploy the Pipelines (dev account)

From the dev account (default credentials or `--profile dev`):

```powershell
cdk deploy PipelineStack ProdPipelineStack --require-approval never
```

To change the dev branch (e.g. from `develop` to `dev`), edit `app.py` and redeploy `PipelineStack`.

---

## Workflow

1. **Development**: Work on feature branches, merge to `develop` → dev pipeline deploys to dev account.
2. **Release**: Merge `develop` into `main` → prod pipeline deploys to prod account.

---

## Stages

| Stage    | Description |
|----------|-------------|
| **Source** | GitHub (CodeStar connection), branch per pipeline |
| **Build**  | Unit tests (`pytest`), lint (`ruff`), type check (`mypy`), Lambda bundling |
| **Migrate** | Alembic migrations + CDK deploy (dev: local; prod: assume role, deploy to prod) |

## Buildspecs

- `buildspec-build.yml` – tests, ruff, mypy, parallel Lambda bundling (shared)
- `buildspec-migrate.yml` – dev: alembic + cdk deploy to dev
- `buildspec-migrate-prod.yml` – prod: assume role, alembic, cdk deploy to prod

---

## Shared database with different schema

The default setup gives each account its own Aurora instance. To use a **shared database with a different schema**:

- Run Aurora in one account (e.g. dev) and configure prod Lambdas to use it via VPC peering and shared secret.
- Use different schema names (e.g. `integrationhub` vs `integrationhub_prod`) via Alembic or `DB_NAME` env.
- This requires custom infra (cross-account secret access, VPC peering) and is not covered by the default buildspecs.

---

## Troubleshooting

### Pipeline shows wrong branch / old commit

Redeploy the pipeline stack so the source action picks up the branch:

```powershell
cdk deploy PipelineStack --require-approval never   # for dev
cdk deploy ProdPipelineStack --require-approval never # for prod
```

### Prod pipeline fails: "Access Denied" or "Unable to assume role"

1. Confirm `ProdDeployRoleStack` is deployed in the prod account.
2. Confirm the trust policy allows `arn:aws:iam::674763518102:role/ProdPipelineStack-*`.
3. Redeploy `ProdPipelineStack` in dev so the Migrate project role ARN is correct.

### Migrations fail in prod pipeline

- Ensure VPC peering between dev and prod so CodeBuild can reach prod Aurora.
- Or run migrations manually in prod (SSM port-forward or bastion) before enabling the pipeline.
