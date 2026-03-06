"""Prod deploy role: allows dev account CodeBuild to assume and deploy to prod.

Deploy this stack ONCE in the prod account (176772326927).
The dev account's prod pipeline CodeBuild will assume this role to run cdk deploy.

Deploy:
  cdk deploy ProdDeployRoleStack --profile prod  # or your IAM Identity Center profile for prod
"""

from __future__ import annotations

from typing import Any

from aws_cdk import Stack
from aws_cdk import aws_iam as iam
from constructs import Construct

# Dev account where the pipelines run
DEV_ACCOUNT_ID = "674763518102"


class ProdDeployRoleStack(Stack):
    """Role in prod account that dev CodeBuild can assume for cross-account deploy."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        dev_account_id: str = DEV_ACCOUNT_ID,
        dev_role_pattern: str = "ProdPipelineStack-*",
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Role that dev account's ProdPipelineStack CodeBuild can assume
        principal = iam.AccountPrincipal(dev_account_id)
        restricted = iam.PrincipalWithConditions(
            principal,
            {"ArnLike": {"aws:PrincipalArn": f"arn:aws:iam::{dev_account_id}:role/{dev_role_pattern}"}},
        )
        deploy_role = iam.Role(
            self,
            "ProdDeployRole",
            role_name="ProdDeployRole",
            assumed_by=restricted,
            description="Allows dev pipeline CodeBuild to deploy CDK stacks to prod",
        )
        deploy_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AdministratorAccess")
        )
