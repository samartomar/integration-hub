"""Custom domain utilities: Hosted Zone lookup and ACM certificates.

Used when CustomDomainRoot is configured. All custom domain logic is optional;
if CustomDomainRoot is not set, these helpers are not used.

The ONLY place subdomain strings are assembled is resolve_domain_names().
Other stacks import and use these names; they never hard-code *.gosam.info.
"""

from __future__ import annotations

from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_route53 as route53
from constructs import Construct


def resolve_domain_names(domain_root: str, environment: str) -> dict[str, str]:
    """Resolve all domain names from domain_root and environment.

    Args:
        domain_root: Root domain (e.g. gosam.info). Must not include apex.
        environment: One of "prod" | "dev".
            - prod: partners.gosam.info, admin-api.gosam.info, api.gosam.info, etc.
            - dev: partners.dev.gosam.info, admin-api.dev.gosam.info, api.dev.gosam.info, etc.

    Returns:
        Dict with keys: adminPortal, vendorPortal, adminApi, partnersApi, runtimeApi
    """
    root = domain_root.rstrip(".")
    if not root:
        raise ValueError("domain_root must not be empty")
    env = (environment or "dev").strip().lower()
    if env not in ("prod", "dev"):
        env = "dev"

    if env == "prod":
        return {
            "adminPortal": f"cip.{root}",
            "vendorPortal": f"partners.{root}",
            "adminApi": f"admin-api.{root}",
            "partnersApi": f"partners-api.{root}",
            "runtimeApi": f"api.{root}",
        }
    # dev
    return {
        "adminPortal": f"cip.dev.{root}",
        "vendorPortal": f"partners.dev.{root}",
        "adminApi": f"admin-api.dev.{root}",
        "partnersApi": f"partners-api.dev.{root}",
        "runtimeApi": f"api.dev.{root}",
    }


def get_all_portal_domains(domain_root: str) -> list[str]:
    """All portal domains for CloudFront cert SANs (prod + dev)."""
    root = domain_root.rstrip(".")
    return [
        f"partners.{root}",
        f"partners.dev.{root}",
        f"cip.{root}",
        f"cip.dev.{root}",
    ]


def get_all_api_domains(domain_root: str) -> list[str]:
    """All API domains for API Gateway cert SANs (prod + dev)."""
    root = domain_root.rstrip(".")
    return [
        f"partners-api.{root}",
        f"partners-api.dev.{root}",
        f"admin-api.{root}",
        f"admin-api.dev.{root}",
        f"api.{root}",
        f"api.dev.{root}",
    ]


def get_or_lookup_hosted_zone(
    scope: Construct,
    domain_root: str,
    hosted_zone_id_from_context: str | None = None,
) -> route53.IHostedZone:
    """Get Hosted Zone by lookup or by ID.

    When CustomDomainRoot is set:
    - If CustomDomainHostedZoneId is provided: use from_hosted_zone_attributes.
    - Else: use from_lookup(domain_name). Lookup requires AWS credentials at synth.
    If lookup fails, fail with a clear error.
    """
    zone_id = (hosted_zone_id_from_context or "").strip()
    root = domain_root.rstrip(".")

    if zone_id:
        return route53.HostedZone.from_hosted_zone_attributes(
            scope,
            "CustomDomainHostedZone",
            hosted_zone_id=zone_id,
            zone_name=root,
        )

    # Look up by domain name (requires env/credentials at synth)
    try:
        return route53.HostedZone.from_lookup(
            scope,
            "CustomDomainHostedZone",
            domain_name=root,
        )
    except Exception as e:
        raise ValueError(
            f"Failed to lookup Route53 hosted zone for {root}. "
            "Either ensure the zone exists and synth has AWS credentials, or provide: "
            f"cdk deploy -c CustomDomainRoot={root} -c CustomDomainHostedZoneId=Z1234567890ABC"
        ) from e


def create_cloudfront_cert(
    scope: Construct,
    domain_root: str,
    hosted_zone: route53.IHostedZone,
) -> acm.ICertificate:
    """Create ACM certificate for CloudFront (must be in us-east-1).

    Includes SANs for ALL portal domains:
    partners.gosam.info, partners.dev.gosam.info,
    cip.gosam.info, cip.dev.gosam.info.
    Uses DNS validation in the provided hosted zone.
    """
    domains = get_all_portal_domains(domain_root)
    return acm.Certificate(
        scope,
        "CloudFrontCert",
        domain_name=domains[0],
        subject_alternative_names=domains[1:],
        validation=acm.CertificateValidation.from_dns(hosted_zone),
    )


def create_api_gateway_cert(
    scope: Construct,
    domain_root: str,
    hosted_zone: route53.IHostedZone,
) -> acm.ICertificate:
    """Create ACM certificate for API Gateway (in stack region).

    Includes SANs for ALL API domains:
    partners-api, partners-api.dev, admin-api, admin-api.dev,
    api, api.dev (all with domain_root).
    Uses DNS validation in the provided hosted zone.
    """
    domains = get_all_api_domains(domain_root)
    return acm.Certificate(
        scope,
        "ApiGatewayCert",
        domain_name=domains[0],
        subject_alternative_names=domains[1:],
        validation=acm.CertificateValidation.from_dns(hosted_zone),
    )
