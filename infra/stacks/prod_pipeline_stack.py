"""Prod pipeline: watches main branch, deploys to prod account via cross-account role."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_codebuild as codebuild
from aws_cdk import aws_codepipeline as codepipeline
from aws_cdk import aws_codepipeline_actions as codepipeline_actions
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from constructs import Construct

if TYPE_CHECKING:
    from infra.stacks.foundation_stack import FoundationStack


class ProdPipelineStack(Stack):
    """Prod CI/CD pipeline: GitHub main -> Build -> Migrate (cross-account) -> Deploy to prod."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        github_owner: str,
        github_repo: str,
        connection_arn: str,
        foundation: FoundationStack | None = None,
        prod_account_id: str,
        prod_deploy_role_arn: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        source_output = codepipeline.Artifact("SourceOutput")

        cache_bucket = s3.Bucket(
            self,
            "CacheBucket",
            bucket_name=None,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # Source: main branch only
        source_action = codepipeline_actions.CodeStarConnectionsSourceAction(
            action_name="GitHub_Source",
            owner=github_owner,
            repo=github_repo,
            branch="main",
            connection_arn=connection_arn,
            output=source_output,
        )

        # Build: shared project (same buildspec as dev)
        build_project = codebuild.PipelineProject(
            self,
            "BuildProject",
            project_name="poc-py-build-prod",
            build_spec=codebuild.BuildSpec.from_source_filename("tooling/pipelines/buildspec-build.yml"),
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
                compute_type=codebuild.ComputeType.MEDIUM,
                privileged=True,  # Required for docker run (Lambda bundling)
            ),
            cache=codebuild.Cache.bucket(cache_bucket, prefix="build-prod"),
        )
        cache_bucket.grant_read_write(build_project)

        build_output = codepipeline.Artifact("BuildOutput")
        build_action = codepipeline_actions.CodeBuildAction(
            action_name="Build",
            project=build_project,
            input=source_output,
            outputs=[build_output],
        )

        # Migrate: assumes prod role, runs alembic + cdk deploy in prod
        migrate_env = codebuild.BuildEnvironment(
            build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
            compute_type=codebuild.ComputeType.MEDIUM,
            environment_variables={
                "PROD_ACCOUNT_ID": codebuild.BuildEnvironmentVariable(
                    value=prod_account_id, type=codebuild.BuildEnvironmentVariableType.PLAINTEXT
                ),
                "PROD_DEPLOY_ROLE_ARN": codebuild.BuildEnvironmentVariable(
                    value=prod_deploy_role_arn, type=codebuild.BuildEnvironmentVariableType.PLAINTEXT
                ),
            },
        )
        migrate_kwargs: dict = {
            "project_name": "poc-py-migrate-prod",
            "build_spec": codebuild.BuildSpec.from_source_filename("tooling/pipelines/buildspec-migrate-prod.yml"),
            "environment": migrate_env,
            "cache": codebuild.Cache.bucket(cache_bucket, prefix="migrate-prod"),
        }
        if foundation:
            migrate_kwargs["vpc"] = foundation.vpc
            migrate_kwargs["security_groups"] = [foundation.codebuild_sg]
            migrate_kwargs["subnet_selection"] = ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            )
        migrate_project = codebuild.PipelineProject(
            self,
            "MigrateProject",
            **migrate_kwargs,
        )
        cache_bucket.grant_read_write(migrate_project)
        migrate_role = migrate_project.role
        if migrate_role:
            # Allow assume prod deploy role
            migrate_role.add_to_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["sts:AssumeRole"],
                    resources=[prod_deploy_role_arn],
                )
            )
            # Basic permissions for CodeBuild (cache, logs); CDK deploy uses assumed role
            migrate_role.add_managed_policy(
                iam.ManagedPolicy.from_aws_managed_policy_name("CloudWatchLogsFullAccess")
            )

        migrate_action = codepipeline_actions.CodeBuildAction(
            action_name="Migrate",
            project=migrate_project,
            input=build_output,
        )

        pipeline = codepipeline.Pipeline(
            self,
            "Pipeline",
            pipeline_name="poc-py-pipeline-prod",
            restart_execution_on_update=True,
        )

        pipeline.add_stage(stage_name="Source", actions=[source_action])
        pipeline.add_stage(stage_name="Build", actions=[build_action])
        pipeline.add_stage(stage_name="Migrate", actions=[migrate_action])

        CfnOutput(
            self,
            "PipelineUrl",
            value=f"https://{self.region}.console.aws.amazon.com/codesuite/codepipeline/pipelines/poc-py-pipeline-prod/view",
            description="Prod CodePipeline URL",
            export_name="ProdPipelineUrl",
        )
