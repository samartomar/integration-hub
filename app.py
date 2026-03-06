#!/usr/bin/env python3
"""AWS CDK v2 application entry point."""

from __future__ import annotations

import os

from aws_cdk import App, Environment

from infra.env_config import load_env_config
from infra.stacks.data_plane_stack import DataPlaneStack
from infra.stacks.database_stack import DatabaseStack
from infra.stacks.foundation_stack import FoundationStack
from infra.stacks.ops_access_stack import OpsAccessStack
from infra.stacks.pipeline_stack import PipelineStack
from infra.stacks.portal_stack import PortalStack
from infra.stacks.prod_deploy_role_stack import ProdDeployRoleStack
from infra.stacks.prod_pipeline_stack import ProdPipelineStack

# Accounts
PROD_ACCOUNT_ID = "176772326927"
DEFAULT_REGION = "us-west-2"
# CloudFront + ACM for portals require us-east-1
PORTAL_REGION = "us-east-1"

app: App = App()

# Single source of truth: packages/env-config/env-config.json (always picked up)
# Override with -c flags or env vars (ENVIRONMENT, CUSTOM_DOMAIN_ROOT, CUSTOM_DOMAIN_HOSTED_ZONE_ID)
_env_config = load_env_config(
    context_overrides={
        "Environment": app.node.try_get_context("Environment"),
        "CustomDomainRoot": app.node.try_get_context("CustomDomainRoot"),
        "CustomDomainHostedZoneId": app.node.try_get_context("CustomDomainHostedZoneId"),
    },
    env_overrides={
        "ENVIRONMENT": os.environ.get("ENVIRONMENT"),
        "CUSTOM_DOMAIN_ROOT": os.environ.get("CUSTOM_DOMAIN_ROOT"),
        "CUSTOM_DOMAIN_HOSTED_ZONE_ID": os.environ.get("CUSTOM_DOMAIN_HOSTED_ZONE_ID"),
    },
)
custom_domain_root = _env_config["customDomainRoot"]
custom_domain_hosted_zone_id = _env_config["customDomainHostedZoneId"] or None
environment = _env_config["environment"]

# Inject into app context so DataPlaneStack (and other stacks) can read via try_get_context
app.node.set_context("Environment", environment)
app.node.set_context("CustomDomainRoot", custom_domain_root)
if custom_domain_hosted_zone_id:
    app.node.set_context("CustomDomainHostedZoneId", custom_domain_hosted_zone_id)

foundation: FoundationStack = FoundationStack(app, "FoundationStack")
database: DatabaseStack = DatabaseStack(app, "DatabaseStack", foundation=foundation)
OpsAccessStack(app, "OpsAccessStack", foundation=foundation)
data_plane: DataPlaneStack = DataPlaneStack(
    app, "DataPlaneStack", foundation=foundation, database=database
)

# Portal stack (Admin + Vendor): S3 + CloudFront. Required us-east-1 for ACM.
# When CustomDomainRoot set: cip/partners (prod) or cip.dev/partners.dev (dev)
if custom_domain_root:
    PortalStack(
        app,
        "PortalStack",
        custom_domain_root=custom_domain_root,
        hosted_zone_id=custom_domain_hosted_zone_id,
        environment=environment,
        env=Environment(region=PORTAL_REGION),
    )

# Dev pipeline - continuous development (branch: develop)
PipelineStack(
    app,
    "PipelineStack",
    github_owner="samartomar",
    github_repo="integration-hub",
    github_branch="main",
    connection_arn="arn:aws:codeconnections:us-west-2:674763518102:connection/a4712769-a210-4d9a-9eed-8f244e3cc48d",
    foundation=foundation,
)

# Prod deploy role - deploy ONCE in prod account before ProdPipelineStack
ProdDeployRoleStack(
    app,
    "ProdDeployRoleStack",
    env=Environment(account=PROD_ACCOUNT_ID, region=DEFAULT_REGION),
)

# Prod pipeline - main branch -> deploy to prod account
ProdPipelineStack(
    app,
    "ProdPipelineStack",
    github_owner="samartomar",
    github_repo="integration-hub",
    connection_arn="arn:aws:codeconnections:us-west-2:674763518102:connection/a4712769-a210-4d9a-9eed-8f244e3cc48d",
    foundation=foundation,
    prod_account_id=PROD_ACCOUNT_ID,
    prod_deploy_role_arn=f"arn:aws:iam::{PROD_ACCOUNT_ID}:role/ProdDeployRole",
)

if __name__ == "__main__":
    app.synth()
