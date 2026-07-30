"""Versioned Lighting Profile documents and stable ID references.

This module deliberately has no ``bpy`` dependency.  Blender data-blocks are
accepted through a small duck-typed surface so reference and file contracts can
be tested with ordinary Python.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

SCHEMA_VERSION = 1
PROFILE_EXTENSION = ".lhprofile"
UUID_KEY = "light_helper_uuid"


class ProfileFormatError(ValueError):
    """Raised when a Lighting Profile document does not match the schema."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProfileFormatError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _nonempty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProfileFormatError(f"{path} must be a non-empty string")
    return value


def _validate_reference(reference: Any, path: str) -> None:
    if not isinstance(reference, Mapping):
        raise ProfileFormatError(f"{path} must be an object")
    kind = reference.get("kind")
    if kind not in {"LOCAL", "LIBRARY", "NAMED"}:
        raise ProfileFormatError(f"{path}.kind is invalid")
    _nonempty_string(reference.get("name_full"), f"{path}.name_full")
    _nonempty_string(reference.get("id_type"), f"{path}.id_type")
    if kind == "LOCAL":
        _nonempty_string(reference.get("uuid"), f"{path}.uuid")
    elif kind == "LIBRARY":
        _nonempty_string(reference.get("library_path"), f"{path}.library_path")


def _validate_profile(profile: Any, index: int) -> None:
    path = f"profiles[{index}]"
    if not isinstance(profile, Mapping):
        raise ProfileFormatError(f"{path} must be an object")
    _nonempty_string(profile.get("id"), f"{path}.id")
    _nonempty_string(profile.get("name"), f"{path}.name")
    lights = profile.get("lights")
    if not isinstance(lights, list):
        raise ProfileFormatError(f"{path}.lights must be an array")
    for light_index, light in enumerate(lights):
        light_path = f"{path}.lights[{light_index}]"
        if not isinstance(light, Mapping):
            raise ProfileFormatError(f"{light_path} must be an object")
        _validate_reference(light.get("ref"), f"{light_path}.ref")
        _nonempty_string(light.get("light_type"), f"{light_path}.light_type")
        for field in ("object", "data"):
            if not isinstance(light.get(field), Mapping):
                raise ProfileFormatError(f"{light_path}.{field} must be an object")
        for optional_mapping in ("linking", "kelvin", "mixer", "track_target"):
            value = light.get(optional_mapping)
            if value is not None and not isinstance(value, Mapping):
                raise ProfileFormatError(
                    f"{light_path}.{optional_mapping} must be an object or null"
                )
        track_target = light.get("track_target")
        if isinstance(track_target, Mapping):
            _validate_reference(track_target.get("ref"), f"{light_path}.track_target.ref")
    for optional_mapping in ("world", "studio", "light_groups"):
        value = profile.get(optional_mapping)
        if value is not None and not isinstance(value, Mapping):
            raise ProfileFormatError(f"{path}.{optional_mapping} must be an object or null")
    emissive_sources = profile.get("emissive_sources", [])
    if not isinstance(emissive_sources, list):
        raise ProfileFormatError(f"{path}.emissive_sources must be an array")
    for source_index, source in enumerate(emissive_sources):
        source_path = f"{path}.emissive_sources[{source_index}]"
        if not isinstance(source, Mapping):
            raise ProfileFormatError(f"{source_path} must be an object")
        _validate_reference(source.get("ref"), f"{source_path}.ref")
        if not isinstance(source.get("object"), Mapping):
            raise ProfileFormatError(f"{source_path}.object must be an object")
        linking = source.get("linking")
        if linking is not None and not isinstance(linking, Mapping):
            raise ProfileFormatError(f"{source_path}.linking must be an object or null")


def validate_document(document: Any) -> dict[str, Any]:
    """Validate and return *document* without mutating it."""
    if not isinstance(document, dict):
        raise ProfileFormatError("Profile document must be an object")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ProfileFormatError(
            f"Unsupported schema_version: {document.get('schema_version')!r}"
        )
    profiles = document.get("profiles")
    if not isinstance(profiles, list):
        raise ProfileFormatError("profiles must be an array")
    seen_ids: set[str] = set()
    for index, profile in enumerate(profiles):
        _validate_profile(profile, index)
        profile_id = profile["id"]
        if profile_id in seen_ids:
            raise ProfileFormatError(f"Duplicate profile id: {profile_id}")
        seen_ids.add(profile_id)
    return document


def make_document(profiles: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    document = {"schema_version": SCHEMA_VERSION, "profiles": list(profiles)}
    return validate_document(document)


def _loads_document(text: str) -> dict[str, Any]:
    try:
        document = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ProfileFormatError(f"Invalid JSON: {exc}") from exc
    return validate_document(document)


def read_document(path: str | os.PathLike[str]) -> dict[str, Any]:
    return _loads_document(Path(path).read_text(encoding="utf-8"))


def atomic_write_document(
    path: str | os.PathLike[str], document: Mapping[str, Any]
) -> Path:
    """Validate, fsync, re-read, then atomically replace a profile file."""
    validated = validate_document(dict(document))
    destination = Path(path)
    if destination.suffix.lower() != PROFILE_EXTENSION:
        destination = destination.with_suffix(PROFILE_EXTENSION)
    parent = destination.parent
    if not parent.is_dir():
        raise FileNotFoundError(f"Profile directory does not exist: {parent}")
    temporary = parent / f".{destination.name}.{uuid4().hex}.tmp"
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(validated, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        # Verification uses the strict duplicate-key parser and full schema.
        read_document(temporary)
        os.replace(temporary, destination)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return destination


def _custom_get(id_block: Any, key: str) -> Any:
    getter = getattr(id_block, "get", None)
    return getter(key) if callable(getter) else None


def _id_type(id_block: Any) -> str:
    bl_rna = getattr(id_block, "bl_rna", None)
    identifier = getattr(bl_rna, "identifier", None)
    return str(identifier or type(id_block).__name__)


def _valid_uuid(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return str(UUID(value))
    except (ValueError, AttributeError):
        return None


def ensure_stable_uuid(
    id_block: Any,
    *,
    used_uuids: set[str] | None = None,
    uuid_factory: Callable[[], Any] = uuid4,
) -> str:
    """Return a valid, collision-free UUID stored on an editable ID."""
    if getattr(id_block, "library", None) is not None or not bool(
        getattr(id_block, "is_editable", True)
    ):
        raise ValueError("Cannot assign a UUID to a read-only ID")
    current = _valid_uuid(_custom_get(id_block, UUID_KEY))
    if current is not None and (used_uuids is None or current not in used_uuids):
        result = current
    else:
        while True:
            result = str(UUID(str(uuid_factory())))
            if used_uuids is None or result not in used_uuids:
                break
        id_block[UUID_KEY] = result
    if used_uuids is not None:
        used_uuids.add(result)
    return result


def build_id_reference(
    id_block: Any, *, used_uuids: set[str] | None = None
) -> dict[str, Any]:
    """Create the portable reference stored in a profile payload."""
    name = _nonempty_string(getattr(id_block, "name_full", None), "ID name_full")
    reference: dict[str, Any] = {
        "name_full": name,
        "id_type": _id_type(id_block),
    }
    object_type = getattr(id_block, "type", None)
    if isinstance(object_type, str):
        reference["object_type"] = object_type
    library = getattr(id_block, "library", None)
    if library is not None:
        reference.update(
            kind="LIBRARY",
            library_path=_nonempty_string(
                getattr(library, "filepath", None), "Library filepath"
            ),
        )
    elif bool(getattr(id_block, "is_editable", True)):
        reference.update(
            kind="LOCAL",
            uuid=ensure_stable_uuid(id_block, used_uuids=used_uuids),
        )
    else:
        reference["kind"] = "NAMED"
    return reference


def _reference_matches_type(reference: Mapping[str, Any], candidate: Any) -> bool:
    if _id_type(candidate) != reference.get("id_type"):
        return False
    expected_object_type = reference.get("object_type")
    return expected_object_type is None or getattr(candidate, "type", None) == expected_object_type


def resolve_id_reference(reference: Mapping[str, Any], candidates: Iterable[Any]) -> Any | None:
    """Resolve UUID, then library identity, then a unique explicit name/type."""
    _validate_reference(reference, "reference")
    pool = [candidate for candidate in candidates if _reference_matches_type(reference, candidate)]
    reference_uuid = reference.get("uuid")
    if isinstance(reference_uuid, str):
        matches = [item for item in pool if _custom_get(item, UUID_KEY) == reference_uuid]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            return None
    library_path = reference.get("library_path")
    if isinstance(library_path, str):
        matches = [
            item
            for item in pool
            if getattr(getattr(item, "library", None), "filepath", None) == library_path
            and getattr(item, "name_full", None) == reference.get("name_full")
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            return None
    matches = [
        item for item in pool if getattr(item, "name_full", None) == reference.get("name_full")
    ]
    return matches[0] if len(matches) == 1 else None
