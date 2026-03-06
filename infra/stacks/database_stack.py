"""Database stack: Aurora PostgreSQL Serverless v2 with schemas.

No public internet access for Aurora (project rule). Access via Lambda in VPC or SSM port-forward.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aws_cdk import CfnOutput, CustomResource, Duration, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_rds as rds
from aws_cdk import custom_resources as cr
from constructs import Construct

if TYPE_CHECKING:
    from infra.stacks.foundation_stack import FoundationStack


class DatabaseStack(Stack):
    """Stack containing Aurora PostgreSQL Serverless v2 and database schemas."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        foundation: FoundationStack,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        vpc: ec2.IVpc = foundation.vpc
        aurora_sg: ec2.ISecurityGroup = foundation.aurora_sg

        # Aurora: private subnets only, no public internet access
        aurora_sg.add_ingress_rule(
            foundation.lambda_sg,
            ec2.Port.tcp(5432),
            "Lambda access",
        )
        bastion_sg = getattr(foundation, "bastion_sg", None)
        if bastion_sg:
            aurora_sg.add_ingress_rule(
                bastion_sg,
                ec2.Port.tcp(5432),
                "SSM bastion (ops access via port-forward)",
            )
        codebuild_sg = getattr(foundation, "codebuild_sg", None)
        if codebuild_sg:
            aurora_sg.add_ingress_rule(
                codebuild_sg,
                ec2.Port.tcp(5432),
                "CodeBuild pipeline (migrations)",
            )

        cluster: rds.DatabaseCluster = rds.DatabaseCluster(
            self,
            "Cluster",
            engine=rds.DatabaseClusterEngine.aurora_postgres(
                version=rds.AuroraPostgresEngineVersion.VER_15_10,
            ),
            credentials=rds.Credentials.from_generated_secret("clusteradmin"),
            writer=rds.ClusterInstance.serverless_v2(
                "writer",
                publicly_accessible=False,
            ),
            serverless_v2_min_capacity=0.5,
            serverless_v2_max_capacity=2,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            security_groups=[aurora_sg],
            default_database_name="integrationhub",
            iam_authentication=False,
            cloudwatch_logs_exports=["postgresql"],
            enable_data_api=True,
        )

        # Schema creation custom resource
        schema_handler: lambda_.Function = lambda_.Function(
            self,
            "SchemaInitHandler",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.on_event",
            code=lambda_.Code.from_asset("lambdas/schema_init"),
            timeout=Duration.seconds(60),
            tracing=lambda_.Tracing.ACTIVE,
        )
        schema_handler.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["xray:PutTraceSegments", "xray:PutTelemetryRecords"],
                resources=["*"],
            )
        )
        schema_handler.add_to_role_policy(
            iam.PolicyStatement(
                actions=["rds-data:ExecuteStatement", "secretsmanager:GetSecretValue"],
                resources=["*"],
            )
        )

        schema_provider: cr.Provider = cr.Provider(
            self,
            "SchemaProvider",
            on_event_handler=schema_handler,
        )

        cluster_secret = cluster.secret
        if not cluster_secret:
            raise ValueError("Aurora cluster must have credentials secret")
        schema_resource: CustomResource = CustomResource(
            self,
            "SchemaResource",
            service_token=schema_provider.service_token,
            properties={
                "ClusterArn": cluster.cluster_arn,
                "SecretArn": cluster_secret.secret_arn,
                "Database": "integrationhub",
                "Schemas": ["control_plane", "data_plane"],
            },
        )
        schema_resource.node.add_dependency(cluster)

        self.cluster: rds.DatabaseCluster = cluster

        # Outputs
        CfnOutput(
            self,
            "Endpoint",
            value=cluster.cluster_endpoint.hostname,
            description="DB endpoint",
            export_name="endpoint",
        )
        CfnOutput(
            self,
            "Port",
            value=str(cluster.cluster_endpoint.port),
            description="DB port",
            export_name="port",
        )
        CfnOutput(
            self,
            "SecretArn",
            value=cluster_secret.secret_arn,
            description="Database credentials secret ARN (username: clusteradmin)",
            export_name="secret-arn",
        )
        CfnOutput(
            self,
            "DatabaseName",
            value="integrationhub",
            description="Database name",
            export_name="database-name",
        )
