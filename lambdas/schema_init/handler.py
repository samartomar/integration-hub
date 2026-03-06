"""Lambda handler to create PostgreSQL schemas via RDS Data API."""

from __future__ import annotations

from typing import Any

import boto3

# Pre-defined SQL only - no string concatenation into SQL
_SCHEMA_SQL: dict[str, str] = {
    "control_plane": "CREATE SCHEMA IF NOT EXISTS control_plane",
    "data_plane": "CREATE SCHEMA IF NOT EXISTS data_plane",
}


def on_event(event: dict[str, Any], context: object) -> dict[str, Any]:
    """Handle CloudFormation custom resource lifecycle events."""
    request_type: str = event["RequestType"]
    props: dict[str, Any] = event["ResourceProperties"]

    if request_type == "Create":
        return on_create(props)
    if request_type == "Update":
        return on_update(event)
    if request_type == "Delete":
        return on_delete(event)
    raise ValueError(f"Invalid request type: {request_type}")


def on_create(props: dict[str, Any]) -> dict[str, Any]:
    """Create schemas in the database."""
    cluster_arn: str = props["ClusterArn"]
    secret_arn: str = props["SecretArn"]
    database: str = props["Database"]
    schemas: list[str] = props["Schemas"]

    if not isinstance(schemas, list):
        raise ValueError("Schemas must be a list")
    for schema_name in schemas:
        if not isinstance(schema_name, str) or schema_name not in _SCHEMA_SQL:
            raise ValueError(f"Schema must be one of {sorted(_SCHEMA_SQL)}")

    client = boto3.client("rds-data")
    for schema_name in schemas:
        sql = _SCHEMA_SQL[schema_name]
        client.execute_statement(
            resourceArn=cluster_arn,
            secretArn=secret_arn,
            database=database,
            sql=sql,
        )

    return {"PhysicalResourceId": f"schemas-{database}"}


def on_update(event: dict[str, Any]) -> dict[str, Any]:
    """No-op for updates; schemas already exist."""
    return {"PhysicalResourceId": event["PhysicalResourceId"]}


def on_delete(event: dict[str, Any]) -> dict[str, Any]:
    """No-op for deletes; schemas are dropped with the cluster."""
    return {"PhysicalResourceId": event["PhysicalResourceId"]}
