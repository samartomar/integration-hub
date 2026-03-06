"""SQLAlchemy models for control_plane schema.

Current active endpoint auth source of truth: control_plane.vendor_auth_profiles.
Legacy control_plane.auth_profiles remains for future/legacy paths only.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all control_plane models."""

    pass


class AuthProfile(Base):
    """Legacy model for control_plane.auth_profiles (not used in active endpoint auth flow)."""

    __tablename__ = "auth_profiles"
    __table_args__ = (
        UniqueConstraint("vendor_code", "name", name="uq_auth_profiles_vendor_name"),
        {"schema": "control_plane"},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default="gen_random_uuid()",
    )
    vendor_code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    auth_type: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )

    # Relationship: endpoints that use this auth profile
    vendor_endpoints: Mapped[list[VendorEndpoint]] = relationship(
        "VendorEndpoint",
        back_populates="legacy_auth_profile",
        foreign_keys="VendorEndpoint.auth_profile_id",
    )


class VendorAuthProfile(Base):
    """Active model for control_plane.vendor_auth_profiles (endpoint outbound auth source of truth)."""

    __tablename__ = "vendor_auth_profiles"
    __table_args__ = (
        UniqueConstraint(
            "vendor_code",
            "profile_name",
            name="uq_vendor_auth_profiles_vendor_profile_name",
        ),
        {"schema": "control_plane"},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default="gen_random_uuid()",
    )
    vendor_code: Mapped[str] = mapped_column(Text, nullable=False)
    profile_name: Mapped[str] = mapped_column(Text, nullable=False)
    auth_type: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )

    vendor_endpoints: Mapped[list[VendorEndpoint]] = relationship(
        "VendorEndpoint",
        back_populates="vendor_auth_profile",
        foreign_keys="VendorEndpoint.vendor_auth_profile_id",
    )


class VendorEndpoint(Base):
    """Maps to control_plane.vendor_endpoints.

    Active relation uses vendor_auth_profile_id; legacy auth_profile_id is retained.
    """

    __tablename__ = "vendor_endpoints"
    __table_args__ = {"schema": "control_plane"}

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default="gen_random_uuid()",
    )
    vendor_code: Mapped[str] = mapped_column(Text, nullable=False)
    operation_code: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    http_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_format: Mapped[str | None] = mapped_column(Text, nullable=True)
    timeout_ms: Mapped[int | None] = mapped_column(nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=True)
    vendor_auth_profile_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("control_plane.vendor_auth_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Legacy nullable column retained for backward compatibility only.
    auth_profile_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("control_plane.auth_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Active relationship
    vendor_auth_profile: Mapped[VendorAuthProfile | None] = relationship(
        "VendorAuthProfile",
        back_populates="vendor_endpoints",
        foreign_keys=[vendor_auth_profile_id],
    )

    # Legacy relationship
    legacy_auth_profile: Mapped[AuthProfile | None] = relationship(
        "AuthProfile",
        back_populates="vendor_endpoints",
        foreign_keys=[auth_profile_id],
    )
