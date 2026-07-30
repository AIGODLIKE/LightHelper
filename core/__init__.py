"""Blender-independent models used by LightHelper runtime adapters."""

from .light_group_plan import (
    CompositeConnectionDecision,
    GroupAdjustment,
    build_light_group_plan,
    decide_composite_connection,
)
from .profiles import (
    PROFILE_EXTENSION,
    SCHEMA_VERSION,
    UUID_KEY,
    ProfileFormatError,
    atomic_write_document,
    build_id_reference,
    ensure_stable_uuid,
    make_document,
    read_document,
    resolve_id_reference,
    validate_document,
)

__all__ = [
    "CompositeConnectionDecision",
    "GroupAdjustment",
    "PROFILE_EXTENSION",
    "ProfileFormatError",
    "SCHEMA_VERSION",
    "UUID_KEY",
    "atomic_write_document",
    "build_id_reference",
    "build_light_group_plan",
    "decide_composite_connection",
    "ensure_stable_uuid",
    "make_document",
    "read_document",
    "resolve_id_reference",
    "validate_document",
]
