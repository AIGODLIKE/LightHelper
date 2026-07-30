"""Lighting Profile capture, apply, and transactional file operators."""

from __future__ import annotations

import json

import bpy
from bpy.app.translations import pgettext_iface as p_
from bpy_extras.io_utils import ExportHelper, ImportHelper

from ..core.profiles import (
    PROFILE_EXTENSION,
    ProfileFormatError,
    atomic_write_document,
    make_document,
    read_document,
)
from ..utils.profile_runtime import apply_profile, capture_profile
from .common import LightHelperOperator


class LLP_PG_lighting_profile(bpy.types.PropertyGroup):
    profile_id: bpy.props.StringProperty(name="Profile ID")
    name: bpy.props.StringProperty(name="Name", default="Lighting Look")
    payload_json: bpy.props.StringProperty(name="Profile Data")


def _profile_collection(scene):
    collection = getattr(scene, "light_helper_profiles", None)
    if collection is None:
        raise RuntimeError("Lighting Profile scene properties are not registered")
    return collection


def _active_profile(scene):
    profiles = _profile_collection(scene)
    index = int(getattr(scene, "light_helper_profile_index", -1))
    return profiles[index] if 0 <= index < len(profiles) else None


def _decode_item(item) -> dict:
    try:
        profile = json.loads(item.payload_json)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ProfileFormatError(f"Stored profile is invalid JSON: {exc}") from exc
    make_document([profile])
    return profile


def _append_profile(scene, profile: dict):
    make_document([profile])
    item = _profile_collection(scene).add()
    item.profile_id = profile["id"]
    item.name = profile["name"]
    item.payload_json = json.dumps(profile, ensure_ascii=False, separators=(",", ":"))
    return item


class LLP_OT_capture_lighting_profile(LightHelperOperator, bpy.types.Operator):
    bl_idname = "scene.light_helper_profile_capture"
    bl_label = "Capture Lighting Profile"
    bl_description = "Capture native lights, linking, World, and managed studio state"
    bl_options = {"REGISTER", "UNDO"}

    name: bpy.props.StringProperty(name="Name", default="Lighting Look")

    def execute(self, context):
        try:
            profile = capture_profile(context.scene, self.name)
            _append_profile(context.scene, profile)
            context.scene.light_helper_profile_index = len(
                context.scene.light_helper_profiles
            ) - 1
        except (AttributeError, ProfileFormatError, RuntimeError, TypeError, ValueError) as exc:
            self.report({"ERROR"}, p_("Lighting Profile capture failed: %s") % str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, p_("Captured Lighting Profile: %s") % profile["name"])
        return {"FINISHED"}


class LLP_OT_select_lighting_profile(LightHelperOperator, bpy.types.Operator):
    bl_idname = "scene.light_helper_profile_select"
    bl_label = "Select Lighting Profile"
    bl_description = "Select the active stored Lighting Profile"
    bl_options = {'INTERNAL'}

    index: bpy.props.IntProperty(default=-1, options={'HIDDEN', 'SKIP_SAVE'})

    def execute(self, context):
        profiles = _profile_collection(context.scene)
        if not 0 <= self.index < len(profiles):
            return {'CANCELLED'}
        context.scene.light_helper_profile_index = self.index
        return {'FINISHED'}


class LLP_OT_apply_lighting_profile(LightHelperOperator, bpy.types.Operator):
    bl_idname = "scene.light_helper_profile_apply"
    bl_label = "Apply Lighting Profile"
    bl_description = "Apply matching items without deleting anything outside the profile"
    bl_options = {"REGISTER", "UNDO"}

    create_missing: bpy.props.BoolProperty(
        name="Create Missing",
        description="Create missing native lights and supported LightHelper studio objects",
        default=False,
    )

    @classmethod
    def poll(cls, context):
        try:
            if _active_profile(context.scene) is not None:
                return True
        except (AttributeError, RuntimeError):
            pass
        cls.poll_message_set(p_("No Lighting Profile is selected"))
        return False

    def invoke(self, context, _event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        item = _active_profile(context.scene)
        if item is None:
            return {"CANCELLED"}
        try:
            profile = _decode_item(item)
            report = apply_profile(
                context.scene,
                profile,
                context=context,
                create_missing=self.create_missing,
            )
        except (AttributeError, ProfileFormatError, RuntimeError, TypeError, ValueError) as exc:
            self.report({"ERROR"}, p_("Lighting Profile apply failed: %s") % str(exc))
            return {"CANCELLED"}
        if report.warnings:
            self.report(
                {"WARNING"},
                p_("Applied with %d warning(s): %s")
                % (len(report.warnings), "; ".join(report.warnings[:3])),
            )
        else:
            self.report(
                {"INFO"},
                p_("Applied %d light(s); created %d; missing %d; read-only %d")
                % (
                    report.matched,
                    report.created,
                    len(report.missing),
                    len(report.skipped_read_only),
                ),
            )
        return {"FINISHED"}


class LLP_OT_remove_lighting_profile(LightHelperOperator, bpy.types.Operator):
    bl_idname = "scene.light_helper_profile_remove"
    bl_label = "Remove Lighting Profile"
    bl_description = "Remove the selected stored profile without changing scene lighting"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        try:
            return _active_profile(context.scene) is not None
        except (AttributeError, RuntimeError):
            return False

    def execute(self, context):
        profiles = _profile_collection(context.scene)
        index = context.scene.light_helper_profile_index
        if not 0 <= index < len(profiles):
            return {"CANCELLED"}
        profiles.remove(index)
        context.scene.light_helper_profile_index = min(index, len(profiles) - 1)
        return {"FINISHED"}


class LLP_OT_import_lighting_profiles(
    LightHelperOperator, ImportHelper, bpy.types.Operator
):
    bl_idname = "scene.light_helper_profile_import"
    bl_label = "Import Lighting Profiles"
    bl_description = "Validate the complete file before appending any profiles"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = PROFILE_EXTENSION
    filter_glob: bpy.props.StringProperty(default="*.lhprofile", options={"HIDDEN"})

    def execute(self, context):
        try:
            # Parse and validate the whole batch before touching RNA.
            document = read_document(self.filepath)
            serialized = [
                json.dumps(profile, ensure_ascii=False, separators=(",", ":"))
                for profile in document["profiles"]
            ]
        except (OSError, ProfileFormatError, TypeError, ValueError) as exc:
            self.report({"ERROR"}, p_("Lighting Profile import failed: %s") % str(exc))
            return {"CANCELLED"}

        profiles = _profile_collection(context.scene)
        start_length = len(profiles)
        old_index = context.scene.light_helper_profile_index
        try:
            for profile, payload in zip(document["profiles"], serialized, strict=True):
                item = profiles.add()
                item.profile_id = profile["id"]
                item.name = profile["name"]
                item.payload_json = payload
            # Validate actual RNA round-trip before accepting the transaction.
            make_document([_decode_item(profiles[index]) for index in range(start_length, len(profiles))])
            if len(profiles) > start_length:
                context.scene.light_helper_profile_index = start_length
        except Exception as exc:
            rollback_errors = []
            while len(profiles) > start_length:
                try:
                    profiles.remove(len(profiles) - 1)
                except Exception as rollback_exc:
                    rollback_errors.append(str(rollback_exc))
                    break
            context.scene.light_helper_profile_index = old_index
            suffix = f"; rollback failed: {'; '.join(rollback_errors)}" if rollback_errors else ""
            self.report({"ERROR"}, p_("Lighting Profile import failed: %s%s") % (exc, suffix))
            return {"CANCELLED"}
        self.report(
            {"INFO"}, p_("Imported %d Lighting Profile(s)") % len(document["profiles"])
        )
        return {"FINISHED"}


class LLP_OT_export_lighting_profiles(
    LightHelperOperator, ExportHelper, bpy.types.Operator
):
    bl_idname = "scene.light_helper_profile_export"
    bl_label = "Export Lighting Profiles"
    bl_description = "Atomically export selected or all stored Lighting Profiles"

    filename_ext = PROFILE_EXTENSION
    filter_glob: bpy.props.StringProperty(default="*.lhprofile", options={"HIDDEN"})
    selected_only: bpy.props.BoolProperty(name="Selected Only", default=False)

    @classmethod
    def poll(cls, context):
        try:
            return len(_profile_collection(context.scene)) > 0
        except (AttributeError, RuntimeError):
            return False

    def execute(self, context):
        try:
            if self.selected_only:
                item = _active_profile(context.scene)
                if item is None:
                    raise ProfileFormatError("No Lighting Profile is selected")
                profiles = [_decode_item(item)]
            else:
                profiles = [_decode_item(item) for item in _profile_collection(context.scene)]
            destination = atomic_write_document(self.filepath, make_document(profiles))
        except (OSError, ProfileFormatError, RuntimeError, TypeError, ValueError) as exc:
            self.report({"ERROR"}, p_("Lighting Profile export failed: %s") % str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, p_("Exported Lighting Profiles: %s") % str(destination))
        return {"FINISHED"}


classes = (
    LLP_PG_lighting_profile,
    LLP_OT_capture_lighting_profile,
    LLP_OT_select_lighting_profile,
    LLP_OT_apply_lighting_profile,
    LLP_OT_remove_lighting_profile,
    LLP_OT_import_lighting_profiles,
    LLP_OT_export_lighting_profiles,
)


def register_scene_properties() -> None:
    bpy.types.Scene.light_helper_profiles = bpy.props.CollectionProperty(
        type=LLP_PG_lighting_profile
    )
    bpy.types.Scene.light_helper_profile_index = bpy.props.IntProperty(default=-1)


def unregister_scene_properties() -> None:
    for name in ("light_helper_profile_index", "light_helper_profiles"):
        if hasattr(bpy.types.Scene, name):
            delattr(bpy.types.Scene, name)


def register() -> None:
    for cls in classes:
        bpy.utils.register_class(cls)
    register_scene_properties()


def unregister() -> None:
    unregister_scene_properties()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


__all__ = [cls.__name__ for cls in classes] + [
    "classes",
    "register",
    "register_scene_properties",
    "unregister",
    "unregister_scene_properties",
]
