"""Data Plane stack: IntegrationHubVendorApi (REST) + IntegrationHubAdminApi (HTTP)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aws_cdk import BundlingOptions, CfnOutput, Duration, Stack
from aws_cdk import aws_apigateway as apigw
from aws_cdk import aws_apigatewayv2 as apigwv2
from aws_cdk import aws_apigatewayv2_authorizers as apigwv2_authorizers
from aws_cdk import aws_apigatewayv2_integrations as apigwv2_integrations
from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_cloudwatch_actions as cloudwatch_actions
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_secretsmanager as secretsmanager
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as sns_subs
from constructs import Construct

_EMF_NAMESPACE = "IntegrationHub/Routing"

if TYPE_CHECKING:
    from infra.stacks.database_stack import DatabaseStack
    from infra.stacks.foundation_stack import FoundationStack

_REPO_ROOT = Path(__file__).resolve().parents[2]
_AI_DIR = _REPO_ROOT / "packages" / "bedrock-assets"
_USE_PREBUNDLED = os.environ.get("USE_PREBUNDLED", "").strip().lower() in ("1", "true", "yes")
_LAYER_DIR = _REPO_ROOT / "packages" / "lambda-layers" / "integrationhub-common"
_LAYER_PREBUNDLED = _REPO_ROOT / ".bundled" / "integrationhub-common-layer"


def _load_bedrock_instruction() -> str:
    """Load agent system prompt from ai/agent-system-prompt.txt."""
    path = _AI_DIR / "agent-system-prompt.txt"
    if not path.exists():
        raise FileNotFoundError(f"Agent instruction file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def _bedrock_schema_to_function(raw: dict) -> dict:
    """Convert a tool schema dict to Bedrock function format."""
    props = raw.get("parameters", {})
    properties = props.get("properties", {})
    required = set(props.get("required", []))
    params: dict[str, dict] = {}
    for name, spec in properties.items():
        if not isinstance(spec, dict):
            continue
        params[name] = {
            "type": spec.get("type", "string"),
            "description": spec.get("description", ""),
            "required": name in required,
        }
    return {
        "name": raw.get("name", "Unknown"),
        "description": raw.get("description", ""),
        "parameters": params,
    }


def _build_bedrock_function_schema() -> dict:
    """Build functionSchema from ai/tool-schema.json and ai/list-operations-schema.json."""
    functions: list[dict] = []
    for filename in ("tool-schema.json", "list-operations-schema.json"):
        path = _AI_DIR / filename
        if not path.exists():
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        functions.append(_bedrock_schema_to_function(raw))
    if not functions:
        raise FileNotFoundError("No tool schema files found in ai/")
    return {"functions": functions}


def _common_layer_code() -> lambda_.Code:
    """
    Asset for integrationhub-common Lambda layer (shared third-party deps).
    When USE_PREBUNDLED=1, use .bundled/integrationhub-common-layer. Else Docker.
    """
    if _USE_PREBUNDLED and _LAYER_PREBUNDLED.exists():
        return lambda_.Code.from_asset(str(_LAYER_PREBUNDLED))
    return lambda_.Code.from_asset(
        str(_LAYER_DIR),
        bundling=BundlingOptions(
            image=lambda_.Runtime.PYTHON_3_11.bundling_image,
            command=[
                "bash",
                "-c",
                "cd /asset-input && pip install -r requirements.txt -t /asset-output/python",
            ],
            user="root",
        ),
    )


def _python_bundling(entry: str, pre_bundled_subdir: str | None = None) -> lambda_.AssetCode:
    """
    Bundle Lambda with psycopg2-binary and requests.
    When USE_PREBUNDLED=1, use .bundled/{pre_bundled_subdir} (no Docker).
    """
    if _USE_PREBUNDLED and pre_bundled_subdir:
        pre_path = _REPO_ROOT / ".bundled" / pre_bundled_subdir
        if pre_path.exists():
            return lambda_.Code.from_asset(str(pre_path))
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


class DataPlaneStack(Stack):
    """Data Plane: IntegrationHubVendorApi (REST) + IntegrationHubAdminApi (HTTP)."""

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

        # Resolve custom domain config early (for Lambda env vars)
        domain_root = (
            self.node.try_get_context("CustomDomainRoot") or ""
        ).strip()
        environment = (
            self.node.try_get_context("Environment") or "dev"
        ).strip().lower()
        if environment not in ("prod", "dev"):
            environment = "dev"
        domain_map: dict[str, str] = {}
        if domain_root:
            from infra.stacks.custom_domain_utils import resolve_domain_names
            domain_map = resolve_domain_names(domain_root, environment)

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

        # Shared Lambda layer: common third-party deps (psycopg2, jsonschema, etc.)
        common_layer = lambda_.LayerVersion(
            self,
            "IntegrationHubCommonLayer",
            layer_version_name="integrationhub-common",
            description="Shared Python deps: psycopg2-binary, jsonschema, PyJWT, requests, aws-xray-sdk",
            code=_common_layer_code(),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_11],
        )

        # Access log group for API (JSON format)
        access_log_group = logs.LogGroup(
            self,
            "ApiAccessLogs",
            log_group_name="/aws/apigateway/integrationhub-api",
            retention=logs.RetentionDays.ONE_MONTH,
        )

        # CORS: Admin API uses * to allow any origin (Amplify ui.*, main.*, etc.)
        # Vendor REST API uses cors_origins (env ADMIN_UI_ORIGIN or *)
        admin_ui_origin = os.environ.get("ADMIN_UI_ORIGIN", "").strip()

        # JWT auth: IDP/Okta configuration from context or env.
        # Supports split IdP settings per surface (admin/vendor/runtime) with
        # fallback to shared IdpIssuer/IdpAudience for backward compatibility.
        use_jwt_auth = str(self.node.try_get_context("UseJwtAuth") or "true").lower() in ("true", "1", "yes")
        shared_idp_issuer = (
            self.node.try_get_context("IdpIssuer")
            or os.environ.get("IDP_ISSUER")
            or "https://integrator-8163795.okta.com/oauth2/default"
        ).strip().rstrip("/") + "/"
        shared_idp_audience = (
            self.node.try_get_context("IdpAudience")
            or os.environ.get("IDP_AUDIENCE")
            or "api://default"
        ).strip()

        admin_idp_issuer = (
            self.node.try_get_context("AdminIdpIssuer")
            or os.environ.get("ADMIN_IDP_ISSUER")
            or shared_idp_issuer
        ).strip().rstrip("/") + "/"
        admin_idp_audience = (
            self.node.try_get_context("AdminIdpAudience")
            or os.environ.get("ADMIN_API_AUDIENCE")
            or shared_idp_audience
        ).strip()

        vendor_idp_issuer = (
            self.node.try_get_context("VendorIdpIssuer")
            or os.environ.get("VENDOR_IDP_ISSUER")
            or shared_idp_issuer
        ).strip().rstrip("/") + "/"
        vendor_idp_audience = (
            self.node.try_get_context("VendorIdpAudience")
            or os.environ.get("VENDOR_API_AUDIENCE")
            or shared_idp_audience
        ).strip()

        runtime_idp_issuer = (
            self.node.try_get_context("RuntimeIdpIssuer")
            or os.environ.get("RUNTIME_IDP_ISSUER")
            or shared_idp_issuer
        ).strip().rstrip("/") + "/"
        runtime_idp_audience = (
            self.node.try_get_context("RuntimeIdpAudience")
            or os.environ.get("RUNTIME_API_AUDIENCE")
            or shared_idp_audience
        ).strip()

        vendor_idp_jwks_url = (
            self.node.try_get_context("VendorIdpJwksUrl")
            or os.environ.get("VENDOR_IDP_JWKS_URL")
            or self.node.try_get_context("IdpJwksUrl")
            or os.environ.get("IDP_JWKS_URL")
            or f"{vendor_idp_issuer.rstrip('/')}/v1/keys"
        ).strip()
        idp_vendor_claims = (
            self.node.try_get_context("IdpVendorClaims")
            or os.environ.get("IDP_VENDOR_CLAIMS")
            or "lhcode,name,sub,entityId"
        ).strip() or "lhcode,name,sub,entityId"

        jwt_authorizer = None
        runtime_jwt_authorizer = None
        if use_jwt_auth and admin_idp_issuer and admin_idp_audience:
            jwt_authorizer = apigwv2_authorizers.HttpJwtAuthorizer(
                "IdpJwtAuthorizer",
                admin_idp_issuer,
                jwt_audience=[admin_idp_audience],
                identity_source=["$request.header.Authorization"],
                authorizer_name="IdpJwtAuthorizer",
            )
        # Each HttpApi needs its own authorizer instance; sharing causes
        # "Invalid authorizer ID" (CDK #20170).
        if use_jwt_auth and runtime_idp_issuer and runtime_idp_audience:
            # Each HttpApi needs its own authorizer instance; sharing causes "Invalid authorizer ID" (CDK #20170)
            runtime_jwt_authorizer = apigwv2_authorizers.HttpJwtAuthorizer(
                "RuntimeIdpJwtAuthorizer",
                runtime_idp_issuer,
                jwt_audience=[runtime_idp_audience],
                identity_source=["$request.header.Authorization"],
                authorizer_name="RuntimeIdpJwtAuthorizer",
            )

        # --- HTTP API (IntegrationHubAdminApi) ---
        admin_api = apigwv2.HttpApi(
            self,
            "IntegrationHubAdminApi",
            api_name="IntegrationHubAdminApi",
            description="Admin API - audit, registry, redrive (JWT auth)",
            default_authorizer=jwt_authorizer,
            cors_preflight=apigwv2.CorsPreflightOptions(
                allow_origins=["*"],  # POC: allow any origin for browser UI
                allow_methods=[
                    apigwv2.CorsHttpMethod.GET,
                    apigwv2.CorsHttpMethod.POST,
                    apigwv2.CorsHttpMethod.PUT,
                    apigwv2.CorsHttpMethod.PATCH,
                    apigwv2.CorsHttpMethod.DELETE,
                    apigwv2.CorsHttpMethod.OPTIONS,
                ],
                allow_headers=["content-type", "authorization", "x-vendor-code"],
                max_age=Duration.seconds(86400),
            ),
        )

        # Enable access logs (JSON) and request IDs via CfnStage
        default_stage = admin_api.default_stage
        if default_stage:
            cfn_stage = default_stage.node.default_child
            if cfn_stage and hasattr(cfn_stage, "access_log_settings"):
                log_format = json.dumps({
                    "requestId": "$context.requestId",
                    "requestTime": "$context.requestTime",
                    "httpMethod": "$context.httpMethod",
                    "routeKey": "$context.routeKey",
                    "status": "$context.status",
                    "protocol": "$context.protocol",
                    "responseLength": "$context.responseLength",
                    "integrationError": "$context.integrationErrorMessage",
                })
                cfn_stage.access_log_settings = apigwv2.CfnStage.AccessLogSettingsProperty(
                    destination_arn=access_log_group.log_group_arn,
                    format=log_format,
                )
                access_log_group.grant_write(
                    iam.ServicePrincipal("apigateway.amazonaws.com")
                )

        # --- Routing Lambda ---
        routing_role = iam.Role(
            self,
            "RoutingLambdaRole",
            role_name="data_plane_routing_lambda_role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        )
        routing_role.add_to_policy(
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
        routing_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["xray:PutTraceSegments", "xray:PutTelemetryRecords"],
                resources=["*"],
            )
        )
        routing_role.add_to_policy(
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
        secret.grant_read(routing_role)

        backend_lambda_path = str(_REPO_ROOT / "apps" / "api" / "src" / "lambda")
        routing_lambda = lambda_.Function(
            self,
            "RoutingLambda",
            function_name="integrationhub-routing",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="routing_lambda.handler",
            code=_python_bundling(backend_lambda_path, "backend-lambda"),
            layers=[common_layer],
            role=routing_role,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            security_groups=[lambda_sg],
            timeout=Duration.seconds(15),
            tracing=lambda_.Tracing.ACTIVE,
            environment={
                "DB_SECRET_ARN": secret.secret_arn,
                "DB_NAME": "integrationhub",
                "ADMIN_UI_ORIGIN": admin_ui_origin or "*",
                "VENDOR_MAX_BINARY_BYTES": "5242880",  # 5 MB
                # Tier-3 inbound JWT (IDP verification). Empty IDP_JWKS_URL = JWT disabled.
                "IDP_JWKS_URL": "",
                "IDP_ISSUER": runtime_idp_issuer,
                "IDP_AUDIENCE": runtime_idp_audience,
                "RUNTIME_API_AUDIENCE": runtime_idp_audience,
                "ADMIN_API_AUDIENCE": admin_idp_audience,
                "IDP_VENDOR_CLAIM": "lhcode",
                "IDP_ALLOWED_ALGS": "RS256",
            },
        )

        self.routing_lambda = routing_lambda
        routing_integration = apigwv2_integrations.HttpLambdaIntegration(
            "ExecuteIntegration",
            routing_lambda,
            payload_format_version=apigwv2.PayloadFormatVersion.VERSION_2_0,
        )

        # --- Vendor Registry Lambda (JWT auth, vendor-scoped) ---
        vendor_registry_role = iam.Role(
            self,
            "VendorRegistryLambdaRole",
            role_name="data_plane_vendor_registry_lambda_role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        )
        vendor_registry_role.add_to_policy(
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
        vendor_registry_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["xray:PutTraceSegments", "xray:PutTelemetryRecords"],
                resources=["*"],
            )
        )
        vendor_registry_role.add_to_policy(
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
        secret.grant_read(vendor_registry_role)
        vendor_registry_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "apigateway:CreateApiKey",
                    "apigateway:CreateUsagePlanKey",
                    "apigateway:GetUsagePlan",
                    "apigateway:GetUsagePlans",
                    "apigateway:DeleteApiKey",
                    "apigateway:POST",
                    "apigateway:GET",
                ],
                resources=["*"],
            )
        )

        vendor_registry_lambda = lambda_.Function(
            self,
            "VendorRegistryLambda",
            function_name="integrationhub-vendor-registry",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="vendor_registry_lambda.handler",
            code=_python_bundling(backend_lambda_path, "backend-lambda"),
            layers=[common_layer],
            role=vendor_registry_role,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            security_groups=[lambda_sg],
            timeout=Duration.seconds(15),
            tracing=lambda_.Tracing.ACTIVE,
            environment={
                "DB_SECRET_ARN": secret.secret_arn,
                "DB_NAME": "integrationhub",
                "ADMIN_API_BASE_URL": (
                    f"https://{domain_map['adminApi']}"
                    if domain_map.get("adminApi")
                    else (admin_api.api_endpoint or "")
                ),
                "IDP_ISSUER": vendor_idp_issuer,
                "IDP_AUDIENCE": vendor_idp_audience,
                "VENDOR_API_AUDIENCE": vendor_idp_audience,
                "VENDOR_ADMIN_TIMEOUT_MS": "4000",
                "VENDOR_MAX_BINARY_BYTES": "5242880",  # 5 MB
            },
        )

        vendor_registry_integration = apigw.LambdaIntegration(
            vendor_registry_lambda, proxy=True
        )

        # --- Onboarding Lambda (vendor self-registration, JWT-only identity) ---
        onboarding_role = iam.Role(
            self,
            "OnboardingLambdaRole",
            role_name="data_plane_onboarding_lambda_role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        )
        onboarding_role.add_to_policy(
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
        onboarding_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["xray:PutTraceSegments", "xray:PutTelemetryRecords"],
                resources=["*"],
            )
        )
        onboarding_role.add_to_policy(
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
        secret.grant_read(onboarding_role)

        onboarding_lambda = lambda_.Function(
            self,
            "OnboardingLambda",
            function_name="integrationhub-onboarding",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="onboarding_lambda.handler",
            code=_python_bundling(backend_lambda_path, "backend-lambda"),
            layers=[common_layer],
            role=onboarding_role,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            security_groups=[lambda_sg],
            timeout=Duration.seconds(15),
            tracing=lambda_.Tracing.ACTIVE,
            environment={
                "DB_SECRET_ARN": secret.secret_arn,
                "DB_NAME": "integrationhub",
                "ADMIN_UI_ORIGIN": admin_ui_origin or "*",
                "IDP_ISSUER": vendor_idp_issuer,
                "IDP_AUDIENCE": vendor_idp_audience,
                "VENDOR_API_AUDIENCE": vendor_idp_audience,
            },
        )

        apigwv2_integrations.HttpLambdaIntegration(
            "OnboardingIntegration",
            onboarding_lambda,
            payload_format_version=apigwv2.PayloadFormatVersion.VERSION_2_0,
        )

        # --- JWT Authorizer Lambda (REST API token authorizer) - no VPC (fetches JWKS from internet) ---
        vendor_jwt_authorizer_fn = None
        vendor_token_authorizer = None
        if use_jwt_auth and vendor_idp_issuer and vendor_idp_audience:
            jwt_auth_role = iam.Role(
                self,
                "JwtAuthorizerLambdaRole",
                role_name="integrationhub-jwt-authorizer-role",
                assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            )
            jwt_auth_role.add_to_policy(
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
            vendor_jwt_authorizer_fn = lambda_.Function(
                self,
                "JwtAuthorizerLambda",
                function_name="integrationhub-jwt-authorizer",
                runtime=lambda_.Runtime.PYTHON_3_11,
                handler="jwt_authorizer.handler",
                code=_python_bundling(backend_lambda_path, "backend-lambda"),
                layers=[common_layer],
                role=jwt_auth_role,
                timeout=Duration.seconds(10),
                environment={
                    "IDP_JWKS_URL": vendor_idp_jwks_url,
                    "IDP_ISSUER": vendor_idp_issuer,
                    "IDP_AUDIENCE": vendor_idp_audience,
                    "AUTH_BYPASS": "false",
                    "IDP_VENDOR_CLAIMS": idp_vendor_claims,
                },
            )
            vendor_token_authorizer = apigw.TokenAuthorizer(
                self,
                "VendorJwtTokenAuthorizer",
                handler=vendor_jwt_authorizer_fn,
                identity_source="method.request.header.Authorization",
                authorizer_name="VendorJwtAuthorizer",
                results_cache_ttl=Duration.minutes(5),
            )

        # --- REST API (Vendor-facing: execute + onboarding with JWT or API Key) ---
        rest_api = apigw.RestApi(
            self,
            "VendorRestApi",
            rest_api_name="IntegrationHubVendorApi",
            description="Vendor-facing REST API with API Key auth",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=[
                    "OPTIONS",
                    "GET",
                    "POST",
                    "PUT",
                    "DELETE",
                ],
                allow_headers=[
                    "content-type",
                    "x-vendor-code",
                    "authorization",
                ],
                allow_credentials=False,
            ),
            deploy=True,
            deploy_options=apigw.StageOptions(
                stage_name="prod",
                throttling_rate_limit=100,
                throttling_burst_limit=200,
                tracing_enabled=True,
                access_log_destination=apigw.LogGroupLogDestination(access_log_group),
                access_log_format=apigw.AccessLogFormat.json_with_standard_fields(
                    caller=False,
                    http_method=True,
                    ip=True,
                    protocol=True,
                    request_time=True,
                    resource_path=True,
                    response_length=True,
                    status=True,
                    user=True,
                ),
            ),
        )
        rest_api.node.add_dependency(access_log_group)
        access_log_group.grant_write(iam.ServicePrincipal("apigateway.amazonaws.com"))

        # Gateway responses: add CORS headers to 4XX/5XX (e.g. missing API key)
        # 5XX: custom body so clients get structured error instead of generic "Internal server error"
        for resp_type in [apigw.ResponseType.DEFAULT_4_XX, apigw.ResponseType.DEFAULT_5_XX]:
            templates = None
            if resp_type == apigw.ResponseType.DEFAULT_5_XX:
                templates = {
                    "application/json": (
                        '{"error":{"code":"GATEWAY_ERROR","message":"Service temporarily unavailable",'
                        '"details":{"hint":"Lambda invocation failed. Check X-Amzn-Requestid header for CloudWatch correlation."}}}'
                    ),
                }
            apigw.GatewayResponse(
                self,
                f"GatewayResponse{resp_type}",
                rest_api=rest_api,
                type=resp_type,
                response_headers={
                    "Access-Control-Allow-Origin": "'*'",
                    "Access-Control-Allow-Headers": "'content-type,x-vendor-code,authorization'",
                    "Access-Control-Allow-Methods": "'GET,POST,OPTIONS'",
                },
                templates=templates,
            )

        # Execute moved to Runtime API only (/v1/ai/execute, /v1/execute). Vendor API has no execute.
        v1 = rest_api.root.add_resource("v1")
        vendor_res = v1.add_resource("vendor")
        # Catch-all for vendor paths (JWT only)
        _vendor_proxy_kw: dict[str, Any] = {}
        if vendor_token_authorizer:
            _vendor_proxy_kw["authorizer"] = vendor_token_authorizer
        _vendor_proxy_kw["api_key_required"] = False
        vendor_proxy = vendor_res.add_resource("{proxy+}")
        vendor_proxy.add_method("GET", vendor_registry_integration, **_vendor_proxy_kw)
        vendor_proxy.add_method("POST", vendor_registry_integration, **_vendor_proxy_kw)
        vendor_proxy.add_method("PUT", vendor_registry_integration, **_vendor_proxy_kw)
        vendor_proxy.add_method("DELETE", vendor_registry_integration, **_vendor_proxy_kw)
        vendor_proxy.add_method("PATCH", vendor_registry_integration, **_vendor_proxy_kw)

        onboarding_res = v1.add_resource("onboarding").add_resource("register")
        _onboarding_method_kw: dict[str, Any] = {"api_key_required": False}
        if vendor_token_authorizer:
            _onboarding_method_kw["authorizer"] = vendor_token_authorizer
        onboarding_res.add_method(
            "POST",
            apigw.LambdaIntegration(onboarding_lambda, proxy=True),
            **_onboarding_method_kw,
        )

        # Usage Plan: IntegrationHubVendorPlan (no env to OnboardingLambda - avoids circular dep)
        usage_plan = apigw.UsagePlan(
            self,
            "IntegrationHubVendorPlan",
            name="IntegrationHubVendorPlan",
            description="Vendor API usage plan (vendor registry, onboarding)",
            throttle=apigw.ThrottleSettings(rate_limit=50, burst_limit=100),
            quota=apigw.QuotaSettings(limit=10000, period=apigw.Period.DAY),
            api_stages=[
                apigw.UsagePlanPerApiStage(
                    api=rest_api,
                    stage=rest_api.deployment_stage,
                )
            ],
        )
        # OnboardingLambda resolves USAGE_PLAN_ID at runtime by name to avoid:
        # OnboardingLambda -> UsagePlan -> RestApi Deployment -> OnboardingLambda

        # Control Plane admin: redrive failed transactions (TODO: enforce admin auth)
        admin_api.add_routes(
            path="/v1/admin/redrive/{transactionId}",
            methods=[apigwv2.HttpMethod.POST],
            integration=routing_integration,
        )

        # --- Audit Lambda ---
        audit_role = iam.Role(
            self,
            "AuditLambdaRole",
            role_name="data_plane_audit_lambda_role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        )
        audit_role.add_to_policy(
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
        audit_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["xray:PutTraceSegments", "xray:PutTelemetryRecords"],
                resources=["*"],
            )
        )
        audit_role.add_to_policy(
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
        secret.grant_read(audit_role)

        audit_lambda = lambda_.Function(
            self,
            "AuditLambda",
            function_name="integrationhub-audit",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="audit_lambda.handler",
            code=_python_bundling(backend_lambda_path, "backend-lambda"),
            layers=[common_layer],
            role=audit_role,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            security_groups=[lambda_sg],
            timeout=Duration.seconds(15),
            tracing=lambda_.Tracing.ACTIVE,
            environment={
                "DB_SECRET_ARN": secret.secret_arn,
                "DB_NAME": "integrationhub",
                "IDP_ISSUER": admin_idp_issuer,
                "IDP_AUDIENCE": admin_idp_audience,
                "ADMIN_API_AUDIENCE": admin_idp_audience,
            },
        )

        # --- Audit routes (same HttpApi) ---
        audit_integration = apigwv2_integrations.HttpLambdaIntegration(
            "AuditIntegration",
            audit_lambda,
            payload_format_version=apigwv2.PayloadFormatVersion.VERSION_2_0,
        )
        admin_api.add_routes(
            path="/v1/audit/transactions",
            methods=[apigwv2.HttpMethod.GET],
            integration=audit_integration,
        )
        admin_api.add_routes(
            path="/v1/audit/transactions/{transactionId}",
            methods=[apigwv2.HttpMethod.GET],
            integration=audit_integration,
        )
        admin_api.add_routes(
            path="/v1/audit/events",
            methods=[apigwv2.HttpMethod.GET],
            integration=audit_integration,
        )

        # --- Registry Lambda (Control Plane) ---
        registry_role = iam.Role(
            self,
            "RegistryLambdaRole",
            role_name="data_plane_registry_lambda_role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        )
        registry_role.add_to_policy(
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
        registry_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["xray:PutTraceSegments", "xray:PutTelemetryRecords"],
                resources=["*"],
            )
        )
        registry_role.add_to_policy(
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
        secret.grant_read(registry_role)
        foundation.event_bus.grant_put_events_to(registry_role)

        registry_lambda = lambda_.Function(
            self,
            "RegistryLambda",
            function_name="integrationhub-registry",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="registry_lambda.handler",
            code=_python_bundling(backend_lambda_path, "backend-lambda"),
            layers=[common_layer],
            role=registry_role,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            security_groups=[lambda_sg],
            timeout=Duration.seconds(15),
            tracing=lambda_.Tracing.ACTIVE,
            environment={
                "DB_SECRET_ARN": secret.secret_arn,
                "DB_NAME": "integrationhub",
                "EVENT_BUS_ARN": foundation.event_bus.event_bus_arn,
                "IDP_ISSUER": admin_idp_issuer,
                "IDP_AUDIENCE": admin_idp_audience,
                "ADMIN_API_AUDIENCE": admin_idp_audience,
            },
        )

        # --- Endpoint Verifier Lambda (EventBridge target for endpoint.upserted) ---
        endpoint_verifier_role = iam.Role(
            self,
            "EndpointVerifierLambdaRole",
            role_name="data_plane_endpoint_verifier_lambda_role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        )
        endpoint_verifier_role.add_to_policy(
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
        endpoint_verifier_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["xray:PutTraceSegments", "xray:PutTelemetryRecords"],
                resources=["*"],
            )
        )
        endpoint_verifier_role.add_to_policy(
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
        secret.grant_read(endpoint_verifier_role)

        endpoint_verifier_lambda = lambda_.Function(
            self,
            "EndpointVerifierLambda",
            function_name="integrationhub-endpoint-verifier",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="endpoint_verifier_lambda.handler",
            code=_python_bundling(backend_lambda_path, "backend-lambda"),
            layers=[common_layer],
            role=endpoint_verifier_role,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            security_groups=[lambda_sg],
            timeout=Duration.seconds(30),
            tracing=lambda_.Tracing.ACTIVE,
            environment={
                "DB_SECRET_ARN": secret.secret_arn,
                "DB_NAME": "integrationhub",
            },
        )

        # EventBridge rule: endpoint.upserted -> EndpointVerifierLambda
        endpoint_upserted_rule = events.Rule(
            self,
            "EndpointUpsertedRule",
            event_bus=foundation.event_bus,
            event_pattern=events.EventPattern(
                source=["integrationhub.registry"],
                detail_type=["endpoint.upserted"],
            ),
            description="Route endpoint.upserted events to EndpointVerifierLambda",
        )
        endpoint_upserted_rule.add_target(
            targets.LambdaFunction(endpoint_verifier_lambda)
        )

        # --- Registry routes (same HttpApi) ---
        registry_integration = apigwv2_integrations.HttpLambdaIntegration(
            "RegistryIntegration",
            registry_lambda,
            payload_format_version=apigwv2.PayloadFormatVersion.VERSION_2_0,
        )
        for route_path in [
            "/v1/registry/vendors",
            "/v1/registry/operations",
            "/v1/registry/allowlist",
            "/v1/registry/endpoints",
            "/v1/registry/auth-profiles",
        ]:
            admin_api.add_routes(
                path=route_path,
                methods=[apigwv2.HttpMethod.GET, apigwv2.HttpMethod.POST],
                integration=registry_integration,
            )
        admin_api.add_routes(
            path="/v1/registry/auth-profiles/{id}",
            methods=[apigwv2.HttpMethod.PATCH, apigwv2.HttpMethod.DELETE],
            integration=registry_integration,
        )
        admin_api.add_routes(
            path="/v1/registry/allowlist/{id}",
            methods=[apigwv2.HttpMethod.DELETE],
            integration=registry_integration,
        )
        admin_api.add_routes(
            path="/v1/registry/auth-profiles/test-connection",
            methods=[apigwv2.HttpMethod.POST],
            integration=registry_integration,
        )
        admin_api.add_routes(
            path="/v1/registry/auth-profiles/token-preview",
            methods=[apigwv2.HttpMethod.POST],
            integration=registry_integration,
        )
        admin_api.add_routes(
            path="/v1/registry/contracts",
            methods=[apigwv2.HttpMethod.GET, apigwv2.HttpMethod.POST],
            integration=registry_integration,
        )
        admin_api.add_routes(
            path="/v1/registry/operations/{operationCode}/canonical-version",
            methods=[apigwv2.HttpMethod.POST],
            integration=registry_integration,
        )
        admin_api.add_routes(
            path="/v1/registry/readiness",
            methods=[apigwv2.HttpMethod.GET],
            integration=registry_integration,
        )
        admin_api.add_routes(
            path="/v1/registry/readiness/batch",
            methods=[apigwv2.HttpMethod.POST],
            integration=registry_integration,
        )
        admin_api.add_routes(
            path="/v1/registry/usage",
            methods=[apigwv2.HttpMethod.GET],
            integration=registry_integration,
        )
        admin_api.add_routes(
            path="/v1/registry/mission-control/topology",
            methods=[apigwv2.HttpMethod.GET],
            integration=registry_integration,
        )
        admin_api.add_routes(
            path="/v1/registry/mission-control/activity",
            methods=[apigwv2.HttpMethod.GET],
            integration=registry_integration,
        )
        admin_api.add_routes(
            path="/v1/registry/policy-decisions",
            methods=[apigwv2.HttpMethod.GET],
            integration=registry_integration,
        )
        admin_api.add_routes(
            path="/v1/registry/policy-simulator",
            methods=[apigwv2.HttpMethod.GET],
            integration=registry_integration,
        )
        admin_api.add_routes(
            path="/v1/registry/platform/features",
            methods=[apigwv2.HttpMethod.GET],
            integration=registry_integration,
        )
        admin_api.add_routes(
            path="/v1/registry/platform/phases",
            methods=[apigwv2.HttpMethod.GET],
            integration=registry_integration,
        )
        admin_api.add_routes(
            path="/v1/registry/platform/settings/current-phase",
            methods=[apigwv2.HttpMethod.PUT],
            integration=registry_integration,
        )
        admin_api.add_routes(
            path="/v1/registry/platform/features/{featureCode}",
            methods=[apigwv2.HttpMethod.PUT],
            integration=registry_integration,
        )
        admin_api.add_routes(
            path="/v1/registry/feature-gates",
            methods=[apigwv2.HttpMethod.GET],
            integration=registry_integration,
        )
        admin_api.add_routes(
            path="/v1/registry/feature-gates/{gateKey}",
            methods=[apigwv2.HttpMethod.PUT],
            integration=registry_integration,
        )
        admin_api.add_routes(
            path="/v1/registry/change-requests",
            methods=[apigwv2.HttpMethod.GET],
            integration=registry_integration,
        )
        admin_api.add_routes(
            path="/v1/registry/change-requests/{id}/decision",
            methods=[apigwv2.HttpMethod.POST],
            integration=registry_integration,
        )
        admin_api.add_routes(
            path="/v1/registry/change-requests/{id}/approve",
            methods=[apigwv2.HttpMethod.POST],
            integration=registry_integration,
        )
        admin_api.add_routes(
            path="/v1/registry/change-requests/{id}/reject",
            methods=[apigwv2.HttpMethod.POST],
            integration=registry_integration,
        )
        admin_api.add_routes(
            path="/v1/mappings/canonical/operations",
            methods=[apigwv2.HttpMethod.GET],
            integration=registry_integration,
        )
        admin_api.add_routes(
            path="/v1/mappings/canonical/readiness",
            methods=[apigwv2.HttpMethod.GET],
            integration=registry_integration,
        )
        admin_api.add_routes(
            path="/v1/mappings/canonical/readiness/{operationCode}",
            methods=[apigwv2.HttpMethod.GET],
            integration=registry_integration,
        )
        admin_api.add_routes(
            path="/v1/mappings/canonical/preview",
            methods=[apigwv2.HttpMethod.POST],
            integration=registry_integration,
        )
        admin_api.add_routes(
            path="/v1/mappings/canonical/validate",
            methods=[apigwv2.HttpMethod.POST],
            integration=registry_integration,
        )
        admin_api.add_routes(
            path="/v1/mappings/canonical/promotion-artifact",
            methods=[apigwv2.HttpMethod.POST],
            integration=registry_integration,
        )
        admin_api.add_routes(
            path="/v1/mappings/canonical/promotion-artifact/markdown",
            methods=[apigwv2.HttpMethod.POST],
            integration=registry_integration,
        )
        admin_api.add_routes(
            path="/v1/mappings/canonical/proposal-package",
            methods=[apigwv2.HttpMethod.POST],
            integration=registry_integration,
        )
        admin_api.add_routes(
            path="/v1/mappings/canonical/proposal-package/markdown",
            methods=[apigwv2.HttpMethod.POST],
            integration=registry_integration,
        )
        admin_api.add_routes(
            path="/v1/mappings/canonical/fixtures",
            methods=[apigwv2.HttpMethod.GET],
            integration=registry_integration,
        )
        admin_api.add_routes(
            path="/v1/mappings/canonical/certify",
            methods=[apigwv2.HttpMethod.POST],
            integration=registry_integration,
        )
        admin_api.add_routes(
            path="/v1/mappings/canonical/scaffold-bundle",
            methods=[apigwv2.HttpMethod.POST],
            integration=registry_integration,
        )
        admin_api.add_routes(
            path="/v1/mappings/canonical/scaffold-bundle/markdown",
            methods=[apigwv2.HttpMethod.POST],
            integration=registry_integration,
        )

        # --- AI Tool Lambda (calls Integration Hub API only; validates control_plane) ---
        ai_tool_path = str(_REPO_ROOT / "lambdas" / "ai_tool")
        ai_tool_role = iam.Role(
            self,
            "AiToolLambdaRole",
            role_name="data_plane_ai_tool_lambda_role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        )
        ai_tool_role.add_to_policy(
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
        ai_tool_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["xray:PutTraceSegments", "xray:PutTelemetryRecords"],
                resources=["*"],
            )
        )
        ai_tool_role.add_to_policy(
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
        secret.grant_read(ai_tool_role)

        # Vendor API invoke URL; AI tool calls execute endpoint
        if domain_map.get("partnersApi"):
            vendor_api_url = f"https://{domain_map['partnersApi']}"
        else:
            vendor_api_url = (
                f"https://{rest_api.rest_api_id}.execute-api.{self.region}.amazonaws.com/"
                f"{rest_api.deployment_stage.stage_name}"
            )
        admin_api_url = (
            f"https://{domain_map['adminApi']}"
            if domain_map.get("adminApi")
            else (admin_api.api_endpoint or "")
        )
        ai_tool_lambda = lambda_.Function(
            self,
            "AiToolLambda",
            function_name="integrationhub-ai-tool",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.handler",
            code=_python_bundling(ai_tool_path, "ai-tool"),
            layers=[common_layer],
            role=ai_tool_role,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            security_groups=[lambda_sg],
            timeout=Duration.seconds(30),
            tracing=lambda_.Tracing.ACTIVE,
            environment={
                "DB_SECRET_ARN": secret.secret_arn,
                "DB_NAME": "integrationhub",
                "VENDOR_API_URL": vendor_api_url,
                "ADMIN_API_URL": admin_api_url,
            },
        )
        ai_tool_lambda.add_permission(
            "AllowBedrockInvoke",
            principal=iam.ServicePrincipal("bedrock.amazonaws.com"),
            action="lambda:InvokeFunction",
        )
        self.ai_tool_lambda = ai_tool_lambda

        # --- Bedrock Agent (PROMPT mode) - wired from CDK, no manual IDs ---
        agent_role = iam.Role(
            self,
            "BedrockAgentRole",
            role_name="integrationhub-bedrock-agent-role",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            description="Allows Bedrock Agent to invoke Lambda and write logs",
        )
        agent_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["lambda:InvokeFunction"],
                resources=[ai_tool_lambda.function_arn],
            )
        )
        agent_role.add_to_policy(
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
        function_schema = _build_bedrock_function_schema()
        instruction = _load_bedrock_instruction()
        _BEDROCK_TYPES = {"string", "number", "integer", "boolean", "array"}

        def _to_param_details(params: dict) -> dict:
            details = {}
            for name, p in params.items():
                t = p.get("type", "string")
                if t not in _BEDROCK_TYPES:
                    t = "string"
                details[name] = bedrock.CfnAgent.ParameterDetailProperty(
                    type=t,
                    description=p.get("description", ""),
                    required=p.get("required", False),
                )
            return details

        functions = [
            bedrock.CfnAgent.FunctionProperty(
                name=f["name"],
                description=f.get("description", ""),
                parameters=_to_param_details(f.get("parameters", {})),
            )
            for f in function_schema["functions"]
        ]
        action_group = bedrock.CfnAgent.AgentActionGroupProperty(
            action_group_name="ExecuteIntegrationGroup",
            description="Execute integrations via the Integration Hub API",
            action_group_state="ENABLED",
            action_group_executor=bedrock.CfnAgent.ActionGroupExecutorProperty(
                lambda_=ai_tool_lambda.function_arn,
            ),
            function_schema=bedrock.CfnAgent.FunctionSchemaProperty(
                functions=functions,
            ),
        )
        bedrock_agent = bedrock.CfnAgent(
            self,
            "CentralIntegrationAgent",
            agent_name="CentralIntegrationAgent",
            agent_resource_role_arn=agent_role.role_arn,
            foundation_model="anthropic.claude-3-sonnet-20240229-v1:0",
            instruction=instruction,
            idle_session_ttl_in_seconds=300,
            description="Integration Hub assistant - executes integrations via ExecuteIntegration tool",
            action_groups=[action_group],
            auto_prepare=True,
        )
        bedrock_agent_alias = bedrock.CfnAgentAlias(
            self,
            "BedrockAgentAlias",
            agent_id=bedrock_agent.attr_agent_id,
            agent_alias_name="prod",
            description="Production alias for CentralIntegrationAgent",
        )
        bedrock_agent_alias.node.add_dependency(bedrock_agent)

        CfnOutput(
            self,
            "BedrockAgentIdOutput",
            value=bedrock_agent.attr_agent_id,
            description="Bedrock Agent ID",
            export_name="BedrockAgentId",
        )
        CfnOutput(
            self,
            "BedrockAgentAliasIdOutput",
            value=bedrock_agent_alias.attr_agent_alias_id,
            description="Agent Alias ID for invoke_agent",
            export_name="BedrockAgentAliasId",
        )

        # --- AI Gateway Lambda (POST /v1/ai/execute: PROMPT + DATA) ---
        ai_gateway_role = iam.Role(
            self,
            "AiGatewayLambdaRole",
            role_name="data_plane_ai_gateway_lambda_role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        )
        ai_gateway_role.add_to_policy(
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
        ai_gateway_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["xray:PutTraceSegments", "xray:PutTelemetryRecords"],
                resources=["*"],
            )
        )
        ai_gateway_role.add_to_policy(
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
        secret.grant_read(ai_gateway_role)

        # Bedrock IAM: wired from CDK constructs (no manual context IDs)
        bedrock_region = self.region or "us-west-2"
        bedrock_account = self.account or "*"
        # bedrock:InvokeAgent requires agent-alias ARN, not agent ARN
        bedrock_agent_alias_arn = (
            f"arn:aws:bedrock:{bedrock_region}:{bedrock_account}:agent-alias/"
            f"{bedrock_agent.attr_agent_id}/{bedrock_agent_alias.attr_agent_alias_id}"
        )
        formatter_model_id = (
            self.node.try_get_context("aiFormatterModelId")
            or os.environ.get("AI_FORMATTER_MODEL_DEFAULT", "anthropic.claude-3-haiku-20240307-v1:0")
            or "anthropic.claude-3-haiku-20240307-v1:0"
        ).strip()
        formatter_model_arn = (
            f"arn:aws:bedrock:{bedrock_region}:{bedrock_account}:model/{formatter_model_id}"
            if formatter_model_id and formatter_model_id != "*"
            else f"arn:aws:bedrock:{bedrock_region}:{bedrock_account}:model/*"
        )

        ai_gateway_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["bedrock:InvokeAgent"],
                resources=[bedrock_agent_alias_arn],
                sid="BedrockInvokeAgentForAiGateway",
            )
        )
        ai_gateway_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["bedrock:InvokeModel"],
                resources=[formatter_model_arn],
                sid="BedrockInvokeModelForFormatter",
            )
        )

        ai_gateway_lambda = lambda_.Function(
            self,
            "AiGatewayLambda",
            function_name="integrationhub-ai-gateway",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="ai_gateway_lambda.handler",
            code=_python_bundling(backend_lambda_path, "backend-lambda"),
            layers=[common_layer],
            role=ai_gateway_role,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            security_groups=[lambda_sg],
            timeout=Duration.seconds(60),
            tracing=lambda_.Tracing.ACTIVE,
            environment={
                "DB_SECRET_ARN": secret.secret_arn,
                "DB_NAME": "integrationhub",
                "VENDOR_API_URL": vendor_api_url,
                "BEDROCK_AGENT_ID": bedrock_agent.attr_agent_id,
                "BEDROCK_AGENT_ALIAS_ID": bedrock_agent_alias.attr_agent_alias_id,
                "BEDROCK_REGION": bedrock_region,
                "AI_FORMATTER_MODEL_DEFAULT": formatter_model_id,
                "IDP_ISSUER": runtime_idp_issuer,
                "IDP_AUDIENCE": runtime_idp_audience,
                "RUNTIME_API_AUDIENCE": runtime_idp_audience,
            },
        )

        self.ai_gateway_lambda = ai_gateway_lambda
        # AI/execute lives on Runtime API only. Admin API has no execute.

        # --- Runtime API (POST /v1/execute, /v1/ai/execute) - single source for execute ---
        runtime_api = apigwv2.HttpApi(
            self,
            "IntegrationHubRuntimeApi",
            api_name="IntegrationHubRuntimeApi",
            description="Runtime API - execute and AI execute (JWT auth)",
            default_authorizer=runtime_jwt_authorizer,
            cors_preflight=apigwv2.CorsPreflightOptions(
                allow_origins=["*"],
                allow_methods=[apigwv2.CorsHttpMethod.POST, apigwv2.CorsHttpMethod.OPTIONS],
                allow_headers=["content-type", "authorization"],
                max_age=Duration.seconds(86400),
            ),
        )
        runtime_api_url = (
            f"https://{domain_map['runtimeApi']}"
            if domain_map.get("runtimeApi")
            else (runtime_api.api_endpoint or "")
        ).rstrip("/")
        ai_gateway_lambda.add_environment("RUNTIME_API_URL", runtime_api_url)
        default_source = self.node.try_get_context("aiGatewaySourceVendor") or "LH001"
        ai_gateway_lambda.add_environment("AI_GATEWAY_SOURCE_VENDOR", str(default_source))
        # Bedrock debugger enrichment (optional, off by default)
        ai_gateway_lambda.add_environment(
            "BEDROCK_DEBUGGER_ENABLED",
            str(self.node.try_get_context("bedrockDebuggerEnabled") or "false"),
        )
        ai_gateway_lambda.add_environment(
            "BEDROCK_DEBUGGER_MODEL_ID",
            str(self.node.try_get_context("bedrockDebuggerModelId") or formatter_model_id),
        )
        ai_gateway_lambda.add_environment("BEDROCK_DEBUGGER_TIMEOUT_MS", "8000")
        # Grant registry/vendor-registry permission to invoke AI Gateway for debugger enrichment
        ai_gateway_lambda.grant_invoke(registry_lambda)
        ai_gateway_lambda.grant_invoke(vendor_registry_lambda)
        registry_lambda.add_environment("AI_GATEWAY_FUNCTION_ARN", ai_gateway_lambda.function_arn)
        vendor_registry_lambda.add_environment("AI_GATEWAY_FUNCTION_ARN", ai_gateway_lambda.function_arn)
        runtime_routing_integration = apigwv2_integrations.HttpLambdaIntegration(
            "RuntimeExecuteIntegration",
            routing_lambda,
            payload_format_version=apigwv2.PayloadFormatVersion.VERSION_2_0,
        )
        runtime_ai_integration = apigwv2_integrations.HttpLambdaIntegration(
            "RuntimeAiExecuteIntegration",
            ai_gateway_lambda,
            payload_format_version=apigwv2.PayloadFormatVersion.VERSION_2_0,
        )
        runtime_api.add_routes(
            path="/v1/execute",
            methods=[apigwv2.HttpMethod.POST],
            integration=runtime_routing_integration,
        )
        runtime_api.add_routes(
            path="/v1/ai/execute",
            methods=[apigwv2.HttpMethod.POST],
            integration=runtime_ai_integration,
        )

        # --- Custom domains (admin-api, partners-api, api) when CustomDomainRoot set ---
        admin_custom_url = (
            f"https://{domain_map['adminApi']}" if domain_map.get("adminApi") else ""
        )
        vendor_custom_url = (
            f"https://{domain_map['partnersApi']}" if domain_map.get("partnersApi") else ""
        )
        runtime_custom_url = (
            f"https://{domain_map['runtimeApi']}" if domain_map.get("runtimeApi") else ""
        )
        if domain_root:
            from aws_cdk import aws_route53 as route53
            from aws_cdk import aws_route53_targets as r53_targets

            from infra.stacks.custom_domain_utils import (
                create_api_gateway_cert,
                get_or_lookup_hosted_zone,
            )

            hosted_zone_id = (
                self.node.try_get_context("CustomDomainHostedZoneId") or ""
            ).strip()
            hosted_zone = get_or_lookup_hosted_zone(
                self, domain_root, hosted_zone_id or None
            )
            api_cert = create_api_gateway_cert(
                self, domain_root, hosted_zone
            )
            zone_name = domain_root.rstrip(".")

            def _record_name(domain: str) -> str:
                if domain.endswith(f".{zone_name}"):
                    return domain[: -len(zone_name) - 1] or ""
                return ""

            # Admin API domain (admin-api.gosam.info or admin-api.dev.gosam.info)
            admin_api_domain = domain_map.get("adminApi")
            if admin_api_domain:
                admin_domain_name = apigwv2.CfnDomainName(
                    self,
                    "AdminApiCustomDomain",
                    domain_name=admin_api_domain,
                    domain_name_configurations=[
                        apigwv2.CfnDomainName.DomainNameConfigurationProperty(
                            certificate_arn=api_cert.certificate_arn,
                            endpoint_type="REGIONAL",
                            security_policy="TLS_1_2",
                        )
                    ],
                )
                admin_stage = admin_api.default_stage
                if admin_stage:
                    apigwv2.CfnApiMapping(
                        self,
                        "AdminApiMapping",
                        api_id=admin_api.api_id,
                        domain_name=admin_domain_name.ref,
                        stage=admin_stage.stage_name,
                    )
                route53.ARecord(
                    self,
                    "AdminApiAlias",
                    zone=hosted_zone,
                    record_name=_record_name(admin_api_domain) or None,
                    target=route53.RecordTarget.from_alias(
                        r53_targets.ApiGatewayv2DomainProperties(
                            admin_domain_name.attr_regional_domain_name,
                            admin_domain_name.attr_regional_hosted_zone_id,
                        )
                    ),
                )

            # Vendor API domain (partners-api) - REST API
            partners_api_domain = domain_map.get("partnersApi")
            if partners_api_domain:
                rest_domain_name = apigw.DomainName(
                    self,
                    "VendorApiCustomDomain",
                    domain_name=partners_api_domain,
                    certificate=api_cert,
                    security_policy=apigw.SecurityPolicy.TLS_1_2,
                )
                apigw.BasePathMapping(
                    self,
                    "VendorApiBasePathMapping",
                    domain_name=rest_domain_name,
                    rest_api=rest_api,
                    stage=rest_api.deployment_stage,
                )
                route53.ARecord(
                    self,
                    "VendorApiAlias",
                    zone=hosted_zone,
                    record_name=_record_name(partners_api_domain) or None,
                    target=route53.RecordTarget.from_alias(
                        r53_targets.ApiGatewayDomain(rest_domain_name)
                    ),
                )

            # Runtime API domain (api.gosam.info or api.dev.gosam.info)
            runtime_api_domain = domain_map.get("runtimeApi")
            if runtime_api_domain:
                runtime_domain_name = apigwv2.CfnDomainName(
                    self,
                    "RuntimeApiCustomDomain",
                    domain_name=runtime_api_domain,
                    domain_name_configurations=[
                        apigwv2.CfnDomainName.DomainNameConfigurationProperty(
                            certificate_arn=api_cert.certificate_arn,
                            endpoint_type="REGIONAL",
                            security_policy="TLS_1_2",
                        )
                    ],
                )
                runtime_stage = runtime_api.default_stage
                if runtime_stage:
                    apigwv2.CfnApiMapping(
                        self,
                        "RuntimeApiMapping",
                        api_id=runtime_api.api_id,
                        domain_name=runtime_domain_name.ref,
                        stage=runtime_stage.stage_name,
                    )
                route53.ARecord(
                    self,
                    "RuntimeApiAlias",
                    zone=hosted_zone,
                    record_name=_record_name(runtime_api_domain) or None,
                    target=route53.RecordTarget.from_alias(
                        r53_targets.ApiGatewayv2DomainProperties(
                            runtime_domain_name.attr_regional_domain_name,
                            runtime_domain_name.attr_regional_hosted_zone_id,
                        )
                    ),
                )

        # --- CloudWatch Dashboard & Alarms ---
        alarm_topic = sns.Topic(
            self,
            "IntegrationHubAlarmTopic",
            topic_name="integrationhub-alarms",
            display_name="Integration Hub POC Alarms",
        )
        # POC: email subscription - set ALARM_EMAIL env to enable
        alarm_email = os.environ.get("ALARM_EMAIL", "").strip()
        if alarm_email:
            alarm_topic.add_subscription(sns_subs.EmailSubscription(alarm_email))

        # Custom EMF metrics (IntegrationHub/Routing namespace)
        def _emf_metric(name: str) -> cloudwatch.Metric:
            return cloudwatch.Metric(
                namespace=_EMF_NAMESPACE,
                metric_name=name,
                period=Duration.minutes(1),
                statistic=cloudwatch.Stats.SUM,
            )

        execute_success = _emf_metric("ExecuteSuccess")
        execute_validation_failed = _emf_metric("ExecuteValidationFailed")
        execute_auth_failed = _emf_metric("ExecuteAuthFailed")
        execute_allowlist_denied = _emf_metric("ExecuteAllowlistDenied")
        downstream_timeout = _emf_metric("DownstreamTimeout")
        downstream_error = _emf_metric("DownstreamError")

        total_requests = cloudwatch.MathExpression(
            expression="success + validation + auth + allowlist + timeout + error",
            using_metrics={
                "success": execute_success,
                "validation": execute_validation_failed,
                "auth": execute_auth_failed,
                "allowlist": execute_allowlist_denied,
                "timeout": downstream_timeout,
                "error": downstream_error,
            },
            period=Duration.minutes(1),
            label="Total Execute Requests",
        )

        failed_count = cloudwatch.MathExpression(
            expression="validation + auth + allowlist + timeout + error",
            using_metrics={
                "validation": execute_validation_failed,
                "auth": execute_auth_failed,
                "allowlist": execute_allowlist_denied,
                "timeout": downstream_timeout,
                "error": downstream_error,
            },
            period=Duration.minutes(1),
            label="Failed Requests",
        )

        success_rate = cloudwatch.MathExpression(
            expression="IF(total>0, success/total*100, 0)",
            using_metrics={
                "success": execute_success,
                "total": total_requests,
            },
            period=Duration.minutes(1),
            label="Success Rate (%)",
        )

        cloudwatch.MathExpression(
            expression="IF(total>0, failed/total*100, 0)",
            using_metrics={
                "failed": failed_count,
                "total": total_requests,
            },
            period=Duration.minutes(1),
            label="Error Rate (%)",
        )

        dashboard = cloudwatch.Dashboard(
            self,
            "IntegrationHubDashboard",
            dashboard_name="IntegrationHubDashboard",
        )
        dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Total Requests",
                left=[total_requests],
                width=6,
                height=4,
            ),
            cloudwatch.GraphWidget(
                title="Success Rate (%)",
                left=[success_rate],
                width=6,
                height=4,
            ),
            cloudwatch.GraphWidget(
                title="Validation Failures",
                left=[execute_validation_failed],
                width=6,
                height=4,
            ),
            cloudwatch.GraphWidget(
                title="Downstream Timeouts",
                left=[downstream_timeout],
                width=6,
                height=4,
            ),
            cloudwatch.GraphWidget(
                title="Routing Lambda p50 Latency (ms)",
                left=[routing_lambda.metric_duration(statistic=cloudwatch.Stats.p(50))],
                width=6,
                height=4,
            ),
            cloudwatch.GraphWidget(
                title="Routing Lambda p95 Latency (ms)",
                left=[routing_lambda.metric_duration(statistic=cloudwatch.Stats.p(95))],
                width=6,
                height=4,
            ),
        )

        alarm_action = cloudwatch_actions.SnsAction(alarm_topic)

        # DownstreamTimeout >= 5 in 5 minutes
        timeout_alarm = cloudwatch.Alarm(
            self,
            "DownstreamTimeoutAlarm",
            alarm_name="integrationhub-downstream-timeout",
            metric=cloudwatch.Metric(
                namespace=_EMF_NAMESPACE,
                metric_name="DownstreamTimeout",
                period=Duration.minutes(5),
                statistic=cloudwatch.Stats.SUM,
            ),
            threshold=5,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            alarm_description="Downstream timeout count >= 5 in 5 minutes",
        )
        timeout_alarm.add_alarm_action(alarm_action)

        def _emf_5m(name: str) -> cloudwatch.Metric:
            return cloudwatch.Metric(
                namespace=_EMF_NAMESPACE,
                metric_name=name,
                period=Duration.minutes(5),
                statistic=cloudwatch.Stats.SUM,
            )

        # Error rate > 5% in 5 minutes (Execute*Failed metrics / total)
        error_rate_expr = cloudwatch.MathExpression(
            expression="IF(total>0, failed/total*100, 0)",
            using_metrics={
                "failed": cloudwatch.MathExpression(
                    expression="vf + af + ad + dt + de",
                    using_metrics={
                        "vf": _emf_5m("ExecuteValidationFailed"),
                        "af": _emf_5m("ExecuteAuthFailed"),
                        "ad": _emf_5m("ExecuteAllowlistDenied"),
                        "dt": _emf_5m("DownstreamTimeout"),
                        "de": _emf_5m("DownstreamError"),
                    },
                    period=Duration.minutes(5),
                ),
                "total": cloudwatch.MathExpression(
                    expression="success + vf + af + ad + dt + de",
                    using_metrics={
                        "success": _emf_5m("ExecuteSuccess"),
                        "vf": _emf_5m("ExecuteValidationFailed"),
                        "af": _emf_5m("ExecuteAuthFailed"),
                        "ad": _emf_5m("ExecuteAllowlistDenied"),
                        "dt": _emf_5m("DownstreamTimeout"),
                        "de": _emf_5m("DownstreamError"),
                    },
                    period=Duration.minutes(5),
                ),
            },
            period=Duration.minutes(5),
        )
        error_rate_alarm = cloudwatch.Alarm(
            self,
            "ErrorRateAlarm",
            alarm_name="integrationhub-error-rate",
            metric=error_rate_expr,
            threshold=5,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description="Execute error rate > 5% in 5 minutes",
        )
        error_rate_alarm.add_alarm_action(alarm_action)

        # p95 routing lambda duration > 8s for 5 minutes
        duration_alarm = cloudwatch.Alarm(
            self,
            "RoutingLambdaDurationAlarm",
            alarm_name="integrationhub-routing-p95-duration",
            metric=routing_lambda.metric_duration(
                statistic=cloudwatch.Stats.p(95),
                period=Duration.minutes(5),
            ),
            threshold=8000,  # ms
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description="Routing Lambda p95 duration > 8s for 5 minutes",
        )
        duration_alarm.add_alarm_action(alarm_action)
        CfnOutput(
            self,
            "RestApiId",
            value=rest_api.rest_api_id,
            description="Vendor REST API ID",
            export_name="IntegrationHubRestApiId",
        )
        CfnOutput(
            self,
            "VendorApiInvokeUrl",
            value=vendor_api_url,
            description="Vendor API invoke URL (execute, onboarding)",
            export_name="VendorApiInvokeUrl",
        )
        CfnOutput(
            self,
            "AdminApiInvokeUrl",
            value=admin_custom_url or (admin_api.api_endpoint or ""),
            description="Admin API invoke URL (audit, registry, redrive)",
            export_name="AdminApiInvokeUrl",
        )
        CfnOutput(
            self,
            "RuntimeApiInvokeUrl",
            value=runtime_api_url,
            description="Runtime API invoke URL (execute, AI execute)",
            export_name="RuntimeApiInvokeUrl",
        )
        if admin_custom_url:
            CfnOutput(
                self,
                "AdminApiCustomDomainUrl",
                value=admin_custom_url,
                description="Admin API custom domain (admin-api.{root})",
                export_name="AdminApiCustomDomainUrl",
            )
        if vendor_custom_url:
            CfnOutput(
                self,
                "VendorApiCustomDomainUrl",
                value=vendor_custom_url,
                description="Vendor API custom domain (partners-api.{root})",
                export_name="VendorApiCustomDomainUrl",
            )
        if runtime_custom_url:
            CfnOutput(
                self,
                "RuntimeApiCustomDomainUrl",
                value=runtime_custom_url,
                description="Runtime API custom domain (api.{root})",
                export_name="RuntimeApiCustomDomainUrl",
            )
        CfnOutput(
            self,
            "UsagePlanId",
            value=usage_plan.usage_plan_id,
            description="Usage Plan ID (IntegrationHubVendorPlan)",
            export_name="IntegrationHubUsagePlanId",
        )
        CfnOutput(
            self,
            "DashboardUrl",
            value=f"https://console.aws.amazon.com/cloudwatch/home?region={self.region}#dashboards:name=IntegrationHubDashboard",
            description="CloudWatch Dashboard (IntegrationHubDashboard)",
            export_name="IntegrationHubDashboardUrl",
        )
        CfnOutput(
            self,
            "AlarmTopicArn",
            value=alarm_topic.topic_arn,
            description="SNS topic for Integration Hub alarms",
            export_name="IntegrationHubAlarmTopicArn",
        )
