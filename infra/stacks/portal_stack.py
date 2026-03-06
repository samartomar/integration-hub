"""Portal stack: Admin and Vendor portals (S3 + CloudFront).

When CustomDomainRoot is set:
  - cip.gosam.info (prod) / cip.dev.gosam.info (dev) → Admin Portal (CloudFront)
  - partners.gosam.info (prod) / partners.dev.gosam.info (dev) → Vendor Portal (CloudFront)

Deploys to us-east-1 for CloudFront (ACM cert must be us-east-1).
Without CustomDomainRoot, uses default CloudFront URLs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_s3 as s3
from constructs import Construct

if TYPE_CHECKING:
    pass


def _record_name_from_domain(domain: str, zone_name: str) -> str:
    """Extract record name for hosted zone. e.g. cip.gosam.info in zone gosam.info -> cip."""
    zone = zone_name.rstrip(".")
    if domain.endswith(f".{zone}") or domain == zone:
        prefix = domain[: -len(zone) - 1] if domain != zone else ""
        return prefix if prefix else ""
    return ""


def _create_portal_distribution(
    scope: Construct,
    id_prefix: str,
    bucket: s3.IBucket,
    domain_names: list[str],
    certificate: Any | None,
) -> cloudfront.Distribution:
    """Create CloudFront distribution for a portal."""
    dist_config: dict[str, Any] = {
        "default_behavior": cloudfront.BehaviorOptions(
            origin=origins.S3BucketOrigin.with_origin_access_control(bucket),
            viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        ),
        "default_root_object": "index.html",
        "error_responses": [
            cloudfront.ErrorResponse(
                http_status=404,
                response_http_status=200,
                response_page_path="/index.html",
                ttl=Duration.seconds(0),
            ),
            cloudfront.ErrorResponse(
                http_status=403,
                response_http_status=200,
                response_page_path="/index.html",
                ttl=Duration.seconds(0),
            ),
        ],
    }
    if domain_names and certificate:
        dist_config["domain_names"] = domain_names
        dist_config["certificate"] = certificate
    return cloudfront.Distribution(
        scope,
        f"{id_prefix}Distribution",
        **dist_config,
    )


class PortalStack(Stack):
    """Admin and Vendor portal hosting (S3 + CloudFront)."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        custom_domain_root: str | None = None,
        hosted_zone_id: str | None = None,
        environment: str = "dev",
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        domain_root = (custom_domain_root or "").strip()
        use_custom_domain = bool(domain_root)
        env = (environment or "dev").strip().lower()
        if env not in ("prod", "dev"):
            env = "dev"

        hosted_zone = None
        cloudfront_cert = None
        domain_map: dict[str, str] = {}
        if use_custom_domain:
            from aws_cdk import aws_route53 as route53

            from infra.stacks.custom_domain_utils import (
                create_cloudfront_cert,
                get_or_lookup_hosted_zone,
                resolve_domain_names,
            )

            hosted_zone = get_or_lookup_hosted_zone(
                self, domain_root, hosted_zone_id
            )
            cloudfront_cert = create_cloudfront_cert(
                self, domain_root, hosted_zone
            )
            domain_map = resolve_domain_names(domain_root, env)

        # Admin Portal bucket (no auto_delete_objects - conflicts with CloudFront OAC bucket policy)
        admin_bucket = s3.Bucket(
            self,
            "AdminPortalBucket",
            bucket_name=None,
            removal_policy=RemovalPolicy.DESTROY,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        )
        admin_domain = domain_map.get("adminPortal") if use_custom_domain else None
        admin_domain_names = [admin_domain] if admin_domain else []
        admin_dist = _create_portal_distribution(
            self,
            "AdminPortal",
            admin_bucket,
            admin_domain_names,
            cloudfront_cert,
        )

        # CI/buildspec syncs: apps/web-cip/dist -> Admin bucket (cip.dev / cip)
        #                      apps/web-partners/dist -> Vendor bucket (partners.dev / partners)

        # Vendor Portal bucket (no auto_delete_objects - conflicts with CloudFront OAC bucket policy)
        vendor_bucket = s3.Bucket(
            self,
            "VendorPortalBucket",
            bucket_name=None,
            removal_policy=RemovalPolicy.DESTROY,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        )
        vendor_domain = domain_map.get("vendorPortal") if use_custom_domain else None
        vendor_domain_names = [vendor_domain] if vendor_domain else []
        vendor_dist = _create_portal_distribution(
            self,
            "VendorPortal",
            vendor_bucket,
            vendor_domain_names,
            cloudfront_cert,
        )

        # Route53 records when custom domain
        zone_name = domain_root.rstrip(".")
        if use_custom_domain and hosted_zone:
            from aws_cdk import aws_route53 as route53
            from aws_cdk import aws_route53_targets as targets

            # adminPortal (cip or cip.dev) -> Admin CloudFront
            if admin_domain:
                admin_record_name = _record_name_from_domain(admin_domain, zone_name)
                route53.ARecord(
                    self,
                    "AdminPortalAlias",
                    zone=hosted_zone,
                    record_name=admin_record_name or None,
                    target=route53.RecordTarget.from_alias(
                        targets.CloudFrontTarget(admin_dist)
                    ),
                )
            # vendorPortal (partners or partners.dev) -> Vendor CloudFront
            if vendor_domain:
                vendor_record_name = _record_name_from_domain(vendor_domain, zone_name)
                route53.ARecord(
                    self,
                    "VendorPortalAlias",
                    zone=hosted_zone,
                    record_name=vendor_record_name or None,
                    target=route53.RecordTarget.from_alias(
                        targets.CloudFrontTarget(vendor_dist)
                    ),
                )

        admin_url = (
            f"https://{admin_domain}"
            if admin_domain
            else f"https://{admin_dist.distribution_domain_name}"
        )
        vendor_url = (
            f"https://{vendor_domain}"
            if vendor_domain
            else f"https://{vendor_dist.distribution_domain_name}"
        )

        CfnOutput(
            self,
            "AdminPortalUrl",
            value=admin_url,
            description="Admin Portal URL",
            export_name="AdminPortalUrl",
        )
        CfnOutput(
            self,
            "VendorPortalUrl",
            value=vendor_url,
            description="Vendor Portal URL",
            export_name="VendorPortalUrl",
        )
        CfnOutput(
            self,
            "AdminPortalBucketName",
            value=admin_bucket.bucket_name,
            description="Admin Portal S3 bucket",
            export_name="AdminPortalBucketName",
        )
        CfnOutput(
            self,
            "VendorPortalBucketName",
            value=vendor_bucket.bucket_name,
            description="Vendor Portal S3 bucket",
            export_name="VendorPortalBucketName",
        )
        CfnOutput(
            self,
            "AdminPortalDistributionId",
            value=admin_dist.distribution_id,
            description="Admin Portal CloudFront distribution ID",
            export_name="AdminPortalDistributionId",
        )
        CfnOutput(
            self,
            "VendorPortalDistributionId",
            value=vendor_dist.distribution_id,
            description="Vendor Portal CloudFront distribution ID",
            export_name="VendorPortalDistributionId",
        )

        self.admin_bucket = admin_bucket
        self.vendor_bucket = vendor_bucket
        self.admin_distribution = admin_dist
        self.vendor_distribution = vendor_dist
