"""API stack: HTTP API (v2) with routing_lambda and audit_lambda."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from aws_cdk import BundlingOptions, CfnOutput, Duration, Stack
from aws_cdk import aws_apigatewayv2 as apigwv2
from aws_cdk import aws_apigatewayv2_integrations as apigwv2_integrations
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_secretsmanager as secretsmanager
from constructs import Construct

if TYPE_CHECKING:
    from infra.stacks.database_stack import DatabaseStack
    from infra.stacks.foundation_stack import FoundationStack


def _python_bundling(
    entry: str,
) -> lambda_.AssetCode:
    """Bundle Lambda with psycopg2-binary (native dependency)."""
    return lambda_.Code.from_asset(
        entry,
        bundling=BundlingOptions(
            image=lambda_.Runtime.PYTHON_3_11.bundling_image,
            command=[
                "bash",
                "-c",
                "cd /asset-input && pip install -r requirements.txt -t /asset-output && "
                "cp -au /asset-input/. /asset-output/",
            ],
            user="root",
        ),
    )


class ApiStack(Stack):
    """Stack containing HTTP API (v2), routing_lambda, and audit_lambda."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        foundation: FoundationStack,
        database: DatabaseStack,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        vpc = foundation.vpc
        lambda_sg = foundation.lambda_sg
        db_secret = database.cluster.secret
        if not db_secret:
            raise ValueError("Database cluster must have credentials secret")
        secret = secretsmanager.Secret.from_secret_complete_arn(
            self,
            "DbSecret",
            secret_complete_arn=db_secret.secret_arn,
        )

        # Shared policy: CloudWatch Logs + VPC ENI + Secrets Manager
        def add_lambda_base_policy(role: iam.IRole) -> None:
            role.add_to_principal_policy(
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
            role.add_to_policy(
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
            secret.grant_read(role)

        # --- routing_lambda ---
        routing_role = iam.Role(
            self,
            "RoutingLambdaRole",
            role_name="api_routing_lambda_role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        )
        add_lambda_base_policy(routing_role)

        backend_lambda_path = str(Path(__file__).resolve().parents[2] / "apps" / "api" / "src" / "lambda")
        routing_code = _python_bundling(backend_lambda_path)
        routing_lambda = lambda_.Function(
            self,
            "RoutingLambda",
            function_name="routing_lambda",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="routing_lambda.handler",
            code=routing_code,
            role=routing_role,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            security_groups=[lambda_sg],
            timeout=Duration.seconds(15),
            environment={
                "DB_SECRET_ARN": secret.secret_arn,
                "VENDOR_MAX_BINARY_BYTES": "5242880",  # 5 MB
            },
        )

        # --- audit_lambda ---
        audit_role = iam.Role(
            self,
            "AuditLambdaRole",
            role_name="api_audit_lambda_role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        )
        add_lambda_base_policy(audit_role)

        audit_code = _python_bundling(backend_lambda_path)
        audit_lambda = lambda_.Function(
            self,
            "AuditLambda",
            function_name="audit_lambda",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="audit_lambda.handler",
            code=audit_code,
            role=audit_role,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            security_groups=[lambda_sg],
            timeout=Duration.seconds(15),
            environment={
                "DB_SECRET_ARN": secret.secret_arn,
            },
        )

        # --- HTTP API (v2) ---
        http_api = apigwv2.HttpApi(
            self,
            "HttpApi",
            api_name="integration-api-v2",
        )

        routing_integration = apigwv2_integrations.HttpLambdaIntegration(
            "RoutingIntegration",
            routing_lambda,
            payload_format_version=apigwv2.PayloadFormatVersion.VERSION_2_0,
        )
        http_api.add_routes(
            path="/transaction",
            methods=[apigwv2.HttpMethod.POST],
            integration=routing_integration,
        )

        audit_integration = apigwv2_integrations.HttpLambdaIntegration(
            "AuditIntegration",
            audit_lambda,
            payload_format_version=apigwv2.PayloadFormatVersion.VERSION_2_0,
        )
        http_api.add_routes(
            path="/audit",
            methods=[apigwv2.HttpMethod.GET],
            integration=audit_integration,
        )
        http_api.add_routes(
            path="/audit/{proxy+}",
            methods=[apigwv2.HttpMethod.GET],
            integration=audit_integration,
        )

        # --- Outputs ---
        CfnOutput(
            self,
            "ApiEndpointUrl",
            value=http_api.api_endpoint,
            description="HTTP API endpoint URL",
            export_name="api-endpoint-url",
        )
