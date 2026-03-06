"""CDK assertion tests for DataPlaneStack Bedrock IAM (AI Gateway bedrock:InvokeAgent)."""

from __future__ import annotations

import shutil
import subprocess
import os
import sys
from pathlib import Path

# Ensure project root and infra are importable
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import pytest

# aws_cdk.assertions requires aws-cdk-lib (bundled with app)
pytest.importorskip("aws_cdk")


def _docker_is_available() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return False
    return result.returncode == 0


def test_ai_gateway_role_has_bedrock_invoke_agent_on_agent_alias() -> None:
    """AI Gateway Lambda role has bedrock:InvokeAgent on agent-alias ARN."""
    if not _docker_is_available():
        pytest.skip("Docker daemon unavailable; CDK asset bundling cannot run")
    from aws_cdk import App
    from aws_cdk.assertions import Template

    from infra.stacks.data_plane_stack import DataPlaneStack
    from infra.stacks.database_stack import DatabaseStack
    from infra.stacks.foundation_stack import FoundationStack

    app = App()
    foundation = FoundationStack(app, "FoundationStack")
    database = DatabaseStack(app, "DatabaseStack", foundation=foundation)
    data_plane = DataPlaneStack(
        app,
        "DataPlaneStack",
        foundation=foundation,
        database=database,
    )

    template = Template.from_stack(data_plane)

    # AI Gateway role's default policy must include bedrock:InvokeAgent on agent-alias
    # The policy is attached to AiGatewayLambdaRole
    policies = template.find_resources("AWS::IAM::Policy")
    ai_gateway_policy = None
    for logical_id, resource in policies.items():
        roles = resource.get("Properties", {}).get("Roles", [])
        policy_doc = resource.get("Properties", {}).get("PolicyDocument", {})
        statements = policy_doc.get("Statement", [])
        # Find policy for AiGatewayLambdaRole
        if any("AiGatewayLambda" in str(r) for r in roles):
            for stmt in statements:
                if stmt.get("Sid") == "BedrockInvokeAgentForAiGateway":
                    ai_gateway_policy = stmt
                    break
        if ai_gateway_policy:
            break

    assert ai_gateway_policy is not None, (
        "AiGatewayLambdaRole should have BedrockInvokeAgentForAiGateway policy statement"
    )
    assert "bedrock:InvokeAgent" in (
        ai_gateway_policy.get("Action")
        if isinstance(ai_gateway_policy.get("Action"), str)
        else ai_gateway_policy.get("Action", [])
    ), "bedrock:InvokeAgent must be in Action"
    resources = ai_gateway_policy.get("Resource", [])
    if isinstance(resources, (str, dict)):
        resources = [resources]
    assert any("agent-alias" in str(r) for r in resources), (
        "Resource must be agent-alias ARN (bedrock:InvokeAgent requires agent-alias, not agent)"
    )
