"""Shared HTTP body + headers builder for endpoint verification and routing.

Used by vendor_registry_lambda (verify) and routing_lambda (real traffic).
Payload formats: json, xml, binary, form, raw.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from html import escape
from typing import Any
from urllib.parse import urlencode

DEFAULT_MAX_BINARY_BYTES = int(os.getenv("VENDOR_MAX_BINARY_BYTES", "5242880"))  # 5 MB default


def try_decode_base64(s: str) -> bytes | None:
    """
    Returns decoded bytes if s looks like valid base64, else None.
    Must not raise on invalid input.
    """
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    if not s:
        return None
    # base64 allows A-Za-z0-9+/= ; strip whitespace/newlines
    clean = re.sub(r"\s+", "", s)
    if not clean:
        return None
    # Padding for valid base64
    pad = len(clean) % 4
    if pad:
        clean += "=" * (4 - pad)
    try:
        return base64.b64decode(clean, validate=True)
    except Exception:
        return None


def _xml_escape(s: str) -> str:
    return escape(s, quote=False)


def _to_xml_value(val: Any, tag: str) -> str:
    if val is None:
        return f"<{tag}></{tag}>"
    if isinstance(val, bool):
        return f"<{tag}>{str(val).lower()}</{tag}>"
    if isinstance(val, (int, float)):
        return f"<{tag}>{val}</{tag}>"
    if isinstance(val, str):
        return f"<{tag}>{_xml_escape(val)}</{tag}>"
    if isinstance(val, dict):
        inner = "".join(_to_xml_value(v, k) for k, v in val.items())
        return f"<{tag}>{inner}</{tag}>"
    if isinstance(val, list):
        inner = "".join(_to_xml_value(v, "item") for v in val)
        return f"<{tag}>{inner}</{tag}>"
    return f"<{tag}>{_xml_escape(str(val))}</{tag}>"


def json_like_to_xml_root(body: Any, root_name: str = "root") -> str:
    """
    Best effort: convert simple dict/list/primitive into a basic XML document.
    Not a full schema mapper; only for simple cases.
    """
    if isinstance(body, dict):
        inner = "".join(_to_xml_value(v, k) for k, v in body.items())
    elif isinstance(body, list):
        inner = "".join(_to_xml_value(v, "item") for v in body)
    else:
        inner = _xml_escape(str(body)) if body is not None else ""
    return f"<?xml version=\"1.0\" encoding=\"UTF-8\"?><{root_name}>{inner}</{root_name}>"


class PayloadFormatError(ValueError):
    """Raised when payload format handling fails (e.g. binary expects base64, not dict)."""

    pass


def build_binary_metadata(
    body_bytes: bytes,
    content_type: str = "application/octet-stream",
) -> dict[str, Any]:
    """
    Return a small JSON-serializable metadata object for binary payloads.
    This is what we persist to the DB instead of the full bytes.
    """
    sha256 = hashlib.sha256(body_bytes).hexdigest()
    return {
        "binaryMeta": {
            "sizeBytes": len(body_bytes),
            "sha256": sha256,
            "contentType": content_type,
        }
    }


def build_http_request_body_and_headers(
    method: str,
    payload_format: str,
    body: Any,
    base_headers: dict[str, str] | None = None,
    content_type_override: str | None = None,
    max_binary_bytes: int = DEFAULT_MAX_BINARY_BYTES,
) -> tuple[bytes | None, dict[str, str], dict[str, Any] | None]:
    """
    Build (body_bytes, headers, binary_meta) for HTTP request.
    GET: never sends body regardless of format.
    For non-binary formats, binary_meta is None.
    For binary, binary_meta contains {binaryMeta: {sizeBytes, sha256, contentType}}.
    """
    headers = dict(base_headers) if base_headers else {}
    method_upper = (method or "POST").upper()

    if method_upper == "GET":
        return None, headers, None

    fmt = (payload_format or "json").strip().lower()
    if fmt in ("form", "x-www-form-urlencoded", "application/x-www-form-urlencoded"):
        fmt = "form"
    if not fmt:
        fmt = "json"

    if fmt == "json":
        headers.setdefault("Content-Type", content_type_override or "application/json")
        if body is None:
            return None, headers, None
        return json.dumps(body, default=str).encode("utf-8"), headers, None

    if fmt == "xml":
        headers.setdefault(
            "Content-Type", content_type_override or "application/xml; charset=utf-8"
        )
        if body is None:
            return None, headers, None
        if isinstance(body, str):
            return body.encode("utf-8"), headers, None
        if isinstance(body, (dict, list)):
            try:
                xml_str = json_like_to_xml_root(body)
                return xml_str.encode("utf-8"), headers, None
            except Exception as e:
                raise PayloadFormatError(
                    f"XML payloadFormat requires string or simple object: {e}"
                ) from e
        return str(body).encode("utf-8"), headers, None

    if fmt == "form":
        headers.setdefault(
            "Content-Type",
            content_type_override or "application/x-www-form-urlencoded",
        )
        if body is None:
            return None, headers, None
        if not isinstance(body, dict):
            raise PayloadFormatError("Form payload must be an object/dict")
        return urlencode(body, doseq=True).encode("utf-8"), headers, None

    if fmt in ("raw", "text"):
        headers.setdefault(
            "Content-Type", content_type_override or "text/plain; charset=utf-8"
        )
        if body is None:
            return None, headers, None
        if isinstance(body, (dict, list)):
            text = json.dumps(body, default=str)
        else:
            text = str(body)
        return text.encode("utf-8"), headers, None

    if fmt == "binary":
        headers.setdefault(
            "Content-Type", content_type_override or "application/octet-stream"
        )
        if body is None:
            return None, headers, None
        if isinstance(body, (dict, list)):
            raise PayloadFormatError(
                "Binary payload must be a base64 string or bytes, not an object/array"
            )
        if isinstance(body, bytes):
            raw = bytes(body)
        elif isinstance(body, bytearray):
            raw = bytes(body)
        else:
            s = str(body)
            decoded = try_decode_base64(s)
            if decoded is None:
                raise PayloadFormatError("Binary payload must be valid base64 string")
            raw = decoded

        if len(raw) > max_binary_bytes:
            raise PayloadFormatError(
                f"Binary payload exceeds size limit of {max_binary_bytes} bytes"
            )

        binary_meta = build_binary_metadata(raw, headers["Content-Type"])
        return raw, headers, binary_meta

    raise PayloadFormatError(f"Unsupported payload_format: {payload_format!r}")
