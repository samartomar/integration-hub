"""Pipeline stack: CodePipeline with GitHub source, Build, Migrate, Deploy."""

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


class PipelineStack(Stack):
    """CI/CD pipeline: GitHub -> Build (test, lint) -> Migrate (alembic in VPC) -> Deploy (cdk)."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        github_owner: str,
        github_repo: str,
        github_branch: str = "main",
        connection_arn: str,
        foundation: FoundationStack | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        source_output = codepipeline.Artifact("SourceOutput")

        # S3 cache bucket for faster rebuilds (pip, npm, Docker layers)
        cache_bucket = s3.Bucket(
            self,
            "CacheBucket",
            bucket_name=None,  # auto-generate
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # Source: GitHub via CodeStar connection
        source_action = codepipeline_actions.CodeStarConnectionsSourceAction(
            action_name="GitHub_Source",
            owner=github_owner,
            repo=github_repo,
            branch=github_branch,
            connection_arn=connection_arn,
            output=source_output,
        )

        # Build: unit tests + lint (MEDIUM = 2x faster, S3 cache for pip/npm)
        build_project = codebuild.PipelineProject(
            self,
            "BuildProject",
            project_name="poc-py-build",
            build_spec=codebuild.BuildSpec.from_source_filename("tooling/pipelines/buildspec-build.yml"),
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
                compute_type=codebuild.ComputeType.MEDIUM,
                privileged=True,  # Required for docker run (Lambda bundling)
            ),
            cache=codebuild.Cache.bucket(cache_bucket, prefix="build"),
        )
        cache_bucket.grant_read_write(build_project)

        build_output = codepipeline.Artifact("BuildOutput")
        build_action = codepipeline_actions.CodeBuildAction(
            action_name="Build",
            project=build_project,
            input=source_output,
            outputs=[build_output],
        )

        # Migrate: CodeBuild in VPC (Aurora access), runs alembic + cdk deploy
        migrate_env = codebuild.BuildEnvironment(
            build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
            compute_type=codebuild.ComputeType.MEDIUM,
        )
        migrate_kwargs: dict = {
            "project_name": "poc-py-migrate",
            "build_spec": codebuild.BuildSpec.from_source_filename("tooling/pipelines/buildspec-migrate.yml"),
            "environment": migrate_env,
            "cache": codebuild.Cache.bucket(cache_bucket, prefix="migrate"),
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
            migrate_role.add_managed_policy(
                iam.ManagedPolicy.from_aws_managed_policy_name("AdministratorAccess")
            )

        migrate_action = codepipeline_actions.CodeBuildAction(
            action_name="Migrate",
            project=migrate_project,
            input=build_output,
        )

        # Pipeline
        pipeline = codepipeline.Pipeline(
            self,
            "Pipeline",
            pipeline_name="poc-py-pipeline",
            restart_execution_on_update=True,
        )

        pipeline.add_stage(stage_name="Source", actions=[source_action])
        pipeline.add_stage(stage_name="Build", actions=[build_action])
        pipeline.add_stage(stage_name="Migrate", actions=[migrate_action])

        # Output
        CfnOutput(
            self,
            "PipelineUrl",
            value=f"https://{self.region}.console.aws.amazon.com/codesuite/codepipeline/pipelines/poc-py-pipeline/view",
            description="CodePipeline URL",
            export_name="PipelineUrl",
        )
