from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from core.profiles import (
    ProfileFormatError,
    atomic_write_document,
    build_id_reference,
    make_document,
    read_document,
    resolve_id_reference,
    validate_document,
)


class FakeID(dict):
    def __init__(
        self,
        name: str,
        *,
        id_type: str = "Object",
        object_type: str = "LIGHT",
        editable: bool = True,
        library_path: str | None = None,
    ) -> None:
        super().__init__()
        self.name_full = name
        self.bl_rna = SimpleNamespace(identifier=id_type)
        self.type = object_type
        self.is_editable = editable
        self.library = (
            SimpleNamespace(filepath=library_path) if library_path is not None else None
        )


def sample_profile() -> dict:
    light = FakeID("Key")
    reference = build_id_reference(light)
    return {
        "id": "profile-1",
        "name": "Day",
        "lights": [
            {
                "ref": reference,
                "light_type": "AREA",
                "object": {"matrix_world": [[1.0, 0.0], [0.0, 1.0]]},
                "data": {"energy": 1000.0},
                "linking": {"receiver": [], "blocker": []},
                "kelvin": {"enabled": True, "value": 5600.0},
            }
        ],
        "world": {"converted": False, "settings": {}},
        "studio": {"items": []},
    }


class ProfileSchemaTests(unittest.TestCase):
    def test_round_trip_atomic_file(self) -> None:
        document = make_document([sample_profile()])
        with tempfile.TemporaryDirectory() as temporary:
            destination = atomic_write_document(Path(temporary) / "looks", document)
            self.assertEqual(destination.suffix, ".lhprofile")
            self.assertEqual(read_document(destination), document)
            self.assertEqual(list(Path(temporary).glob("*.tmp")), [])

    def test_rejects_unknown_schema_and_duplicate_profile_ids(self) -> None:
        with self.assertRaises(ProfileFormatError):
            validate_document({"schema_version": 2, "profiles": []})
        duplicate = sample_profile()
        with self.assertRaises(ProfileFormatError):
            make_document([duplicate, dict(duplicate)])

    def test_strict_reader_rejects_duplicate_json_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.lhprofile"
            path.write_text(
                '{"schema_version":1,"schema_version":1,"profiles":[]}',
                encoding="utf-8",
            )
            with self.assertRaises(ProfileFormatError):
                read_document(path)

    def test_local_reference_uses_stable_uuid(self) -> None:
        light = FakeID("Key")
        first = build_id_reference(light)
        second = build_id_reference(light)
        self.assertEqual(first, second)
        self.assertEqual(str(UUID(first["uuid"])), first["uuid"])

    def test_library_reference_and_resolution_precedence(self) -> None:
        library_light = FakeID("Key", editable=False, library_path="//rig.blend")
        local_light = FakeID("Key")
        reference = build_id_reference(library_light)
        self.assertEqual(reference["kind"], "LIBRARY")
        self.assertIs(
            resolve_id_reference(reference, [local_light, library_light]), library_light
        )

        local_reference = build_id_reference(local_light)
        renamed = FakeID("Renamed")
        renamed["light_helper_uuid"] = local_reference["uuid"]
        self.assertIs(resolve_id_reference(local_reference, [renamed]), renamed)

    def test_ambiguous_name_fallback_is_not_guessed(self) -> None:
        reference = {
            "kind": "NAMED",
            "name_full": "Fill",
            "id_type": "Object",
            "object_type": "LIGHT",
        }
        self.assertIsNone(
            resolve_id_reference(reference, [FakeID("Fill"), FakeID("Fill")])
        )


if __name__ == "__main__":
    unittest.main()
