"""Add DownstreamTimeout to _execute_routing_for_redrive."""
path = "apps/api/src/lambda/routing_lambda.py"
with open(path, encoding="utf-8") as f:
    content = f.read()

old = """    with _xray_subsegment("downstream_http"):
        status_code, downstream_body = call_downstream(
            endpoint["url"],
            endpoint.get("timeout_ms") or 8000,
            transformed,
            endpoint.get("http_method"),
        )

    with _get_connection() as conn:
        if 200 <= status_code < 300:
            response_body = {
                "transactionId": transaction_id,"""

new = """    with _xray_subsegment("downstream_http"):
        try:
            status_code, downstream_body = call_downstream(
                endpoint["url"],
                endpoint.get("timeout_ms") or 8000,
                transformed,
                endpoint.get("http_method"),
            )
        except requests.exceptions.Timeout:
            emit_metric("DownstreamTimeout", operation=operation or "-", source_vendor=source, target_vendor=target)
            response_body_err = {
                "error": {
                    "code": "DOWNSTREAM_TIMEOUT",
                    "message": "Downstream request timed out",
                    "response": None,
                }
            }
            with _get_connection() as conn:
                update_transaction_failure(
                    conn, transaction_id, "downstream_error", response_body=response_body_err
                )
                write_audit_event(
                    conn,
                    transaction_id,
                    source,
                    "REDRIVE_FAIL",
                    {"original_transaction_id": original_tx_id, "statusCode": 504, "body": "Request timed out"},
                )
            return False, 504, response_body_err, {"code": "DOWNSTREAM_TIMEOUT", "message": "Downstream request timed out"}

    with _get_connection() as conn:
        if 200 <= status_code < 300:
            response_body = {
                "transactionId": transaction_id,"""

if old in content:
    content = content.replace(old, new, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Redrive DownstreamTimeout added")
else:
    print("Pattern not found")
