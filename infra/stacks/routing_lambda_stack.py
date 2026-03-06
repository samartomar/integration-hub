"""Routing Lambda stack: integration router Lambda deployment."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aws_cdk import Duration, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from constructs import Construct

if TYPE_CHECKING:
    from infra.stacks.foundation_stack import FoundationStack


class RoutingLambdaStack(Stack):
    """Stack containing the integration router Lambda function."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        foundation: FoundationStack,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Grant Lambda basic execution (CloudWatch Logs) + VPC ENI (required for VPC-attached Lambda)
        foundation.integration_router_lambda_role.add_to_principal_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                ],
                resources=["*"],
            )
        )
        foundation.integration_router_lambda_role.add_to_principal_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ec2:CreateNetworkInterface",
                    "ec2:DescribeNetworkInterfaces",
                    "ec2:DeleteNetworkInterface",
                    "ec2:AssignPrivateIpAddresses",
                    "ec2:UnassignPrivateIpAddresses",
                ],
                resources=["*"],
            )
        )

        # Deploy routing Lambda
        self.router_lambda: lambda_.Function = lambda_.Function(
            self,
            "RouterLambda",
            function_name="integration-router",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.handler",
            code=lambda_.Code.from_asset("lambdas/router"),
            role=foundation.integration_router_lambda_role,
            vpc=foundation.vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            security_groups=[foundation.lambda_sg],
            timeout=Duration.seconds(15),
        )
