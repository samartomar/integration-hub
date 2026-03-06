"""Foundation stack: VPC, security groups, IAM roles, and EventBridge bus."""

from __future__ import annotations

from typing import Any

from aws_cdk import CfnOutput, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_events as events
from aws_cdk import aws_iam as iam
from constructs import Construct


class FoundationStack(Stack):
    """Stack containing foundational infrastructure: VPC, security groups, IAM roles."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs: Any) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # VPC with 2 AZs
        vpc: ec2.Vpc = ec2.Vpc(
            self,
            "Vpc",
            max_azs=2,
        )

        # Security groups
        lambda_sg: ec2.SecurityGroup = ec2.SecurityGroup(
            self,
            "LambdaSg",
            vpc=vpc,
            security_group_name="lambda_sg",
            description="Security group for Lambda functions",
            allow_all_outbound=True,
        )

        aurora_sg: ec2.SecurityGroup = ec2.SecurityGroup(
            self,
            "AuroraSg",
            vpc=vpc,
            security_group_name="aurora_sg",
            description="Security group for Aurora",
            allow_all_outbound=True,
        )

        # CodeBuild SG (for pipeline migrations - access to Aurora in VPC)
        codebuild_sg: ec2.SecurityGroup = ec2.SecurityGroup(
            self,
            "CodeBuildSg",
            vpc=vpc,
            security_group_name="integrationhub-codebuild-sg",
            description="CodeBuild in VPC for pipeline migrations",
            allow_all_outbound=True,
        )
        self.codebuild_sg = codebuild_sg

        # POC / Ops Access - SSM bastion SG (in Foundation to avoid cross-stack cycle)
        bastion_sg: ec2.SecurityGroup = ec2.SecurityGroup(
            self,
            "BastionSg",
            vpc=vpc,
            security_group_name="integrationhub-ssm-sg",
            description="POC / Ops Access - SSM bastion. Remove or restrict for prod.",
            allow_all_outbound=True,
        )

        # Expose for cross-stack reference
        self.vpc: ec2.Vpc = vpc
        self.aurora_sg: ec2.SecurityGroup = aurora_sg
        self.lambda_sg: ec2.SecurityGroup = lambda_sg
        self.bastion_sg: ec2.SecurityGroup = bastion_sg

        # IAM roles (trust relationships only, no policies)
        lambda_principal: iam.ServicePrincipal = iam.ServicePrincipal("lambda.amazonaws.com")

        integration_router_lambda_role: iam.Role = iam.Role(
            self,
            "IntegrationRouterLambdaRole",
            role_name="integration_router_lambda_role",
            assumed_by=lambda_principal,
        )
        self.integration_router_lambda_role: iam.Role = integration_router_lambda_role

        iam.Role(
            self,
            "AiToolLambdaRole",
            role_name="ai_tool_lambda_role",
            assumed_by=lambda_principal,
        )

        iam.Role(
            self,
            "AuditLambdaRole",
            role_name="audit_lambda_role",
            assumed_by=lambda_principal,
        )

        # EventBridge bus for integration events
        event_bus: events.EventBus = events.EventBus(
            self,
            "IntegrationEventBus",
            event_bus_name="integration-hub-events",
        )
        event_bus.grant_put_events_to(integration_router_lambda_role)
        self.event_bus: events.EventBus = event_bus
        # Rule for endpoint.upserted -> EndpointVerifierLambda is in DataPlaneStack

        # Outputs
        CfnOutput(
            self,
            "VpcId",
            value=vpc.vpc_id,
            description="VPC ID",
            export_name="vpc-id",
        )

        CfnOutput(
            self,
            "LambdaSecurityGroupId",
            value=lambda_sg.security_group_id,
            description="Lambda security group ID",
            export_name="lambda-security-group-id",
        )
