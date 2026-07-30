"""Operators and persistent controls for Cycles Light Group mixing."""

from __future__ import annotations

import bpy
from bpy.app.translations import pgettext_iface as p_

from ..core.light_group_plan import GroupAdjustment
from ..utils.light_groups import (
    build_light_group_compositor,
    ensure_light_group,
    ensure_used_light_groups,
    light_group_names,
    remove_light_group,
    remove_managed_light_group_compositor,
)
from .common import LightHelperOperator


class LLP_PG_light_group_setting(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Light Group")
    ev: bpy.props.FloatProperty(
        name="Exposure",
        description="Exposure adjustment applied by the managed compositor chain",
        default=0.0,
        soft_min=-10.0,
        soft_max=10.0,
        subtype="FACTOR",
    )
    tint: bpy.props.FloatVectorProperty(
        name="Tint",
        subtype="COLOR",
        size=3,
        default=(1.0, 1.0, 1.0),
        min=0.0,
        soft_max=2.0,
    )


def _settings(scene):
    result = getattr(scene, "light_helper_light_group_settings", None)
    if result is None:
        raise RuntimeError("Light Group scene properties are not registered")
    return result


def _sync_settings(scene, view_layer) -> int:
    ensure_used_light_groups(scene, view_layer)
    settings = _settings(scene)
    existing = {item.name for item in settings}
    added = 0
    for name in light_group_names(view_layer):
        if name in existing:
            continue
        item = settings.add()
        item.name = name
        added += 1
    return added


class LLP_OT_sync_light_groups(LightHelperOperator, bpy.types.Operator):
    bl_idname = "scene.light_helper_light_groups_sync"
    bl_label = "Sync Light Groups"
    bl_description = "Add Light Groups used by scene objects or World to this View Layer"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            added = _sync_settings(context.scene, context.view_layer)
        except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
            self.report({"ERROR"}, p_("Light Group synchronization failed: %s") % str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, p_("Added %d Light Group(s)") % added)
        return {"FINISHED"}


class LLP_OT_assign_light_group(LightHelperOperator, bpy.types.Operator):
    bl_idname = "object.light_helper_assign_light_group"
    bl_label = "Assign Light Group"
    bl_description = "Assign the selected compatible objects to one Cycles Light Group"
    bl_options = {"REGISTER", "UNDO"}

    group_name: bpy.props.StringProperty(name="Light Group")

    @classmethod
    def poll(cls, context):
        if any(hasattr(obj, "lightgroup") for obj in context.selected_objects):
            return True
        cls.poll_message_set(p_("No selected object supports Light Groups"))
        return False

    def execute(self, context):
        name = self.group_name.strip()
        if not name:
            self.report({"ERROR"}, p_("Light Group name cannot be empty"))
            return {"CANCELLED"}
        ensure_light_group(context.view_layer, name)
        changed = 0
        skipped = 0
        for obj in context.selected_objects:
            if not hasattr(obj, "lightgroup") or not getattr(obj, "is_editable", True):
                skipped += 1
                continue
            try:
                if obj.lightgroup != name:
                    obj.lightgroup = name
                    changed += 1
            except (AttributeError, ReferenceError, RuntimeError, TypeError):
                skipped += 1
        _sync_settings(context.scene, context.view_layer)
        self.report(
            {"INFO"}, p_("Assigned %d object(s); skipped %d") % (changed, skipped)
        )
        return {"FINISHED"}


class LLP_OT_assign_world_light_group(LightHelperOperator, bpy.types.Operator):
    bl_idname = "world.light_helper_assign_light_group"
    bl_label = "Assign World Light Group"
    bl_description = "Assign the active World contribution to one Cycles Light Group"
    bl_options = {"REGISTER", "UNDO"}

    group_name: bpy.props.StringProperty(name="Light Group")

    @classmethod
    def poll(cls, context):
        world = context.scene.world
        if world is not None and hasattr(world, "lightgroup") and world.is_editable:
            return True
        cls.poll_message_set(p_("The active World does not support editable Light Groups"))
        return False

    def execute(self, context):
        name = self.group_name.strip()
        if not name:
            self.report({"ERROR"}, p_("Light Group name cannot be empty"))
            return {"CANCELLED"}
        ensure_light_group(context.view_layer, name)
        context.scene.world.lightgroup = name
        _sync_settings(context.scene, context.view_layer)
        return {"FINISHED"}


class LLP_OT_adjust_light_group(LightHelperOperator, bpy.types.Operator):
    bl_idname = "scene.light_helper_light_group_adjust"
    bl_label = "Adjust Light Group"
    bl_description = "Adjust one managed Light Group exposure or tint preset"
    bl_options = {'REGISTER', 'UNDO'}

    group_name: bpy.props.StringProperty(options={'HIDDEN', 'SKIP_SAVE'})
    ev_delta: bpy.props.FloatProperty(default=0.0, options={'SKIP_SAVE'})
    tint: bpy.props.FloatVectorProperty(
        size=3,
        subtype='COLOR',
        default=(1.0, 1.0, 1.0),
        min=0.0,
        soft_max=2.0,
        options={'SKIP_SAVE'},
    )
    set_tint: bpy.props.BoolProperty(default=False, options={'HIDDEN', 'SKIP_SAVE'})

    def execute(self, context):
        setting = next(
            (
                item for item in _settings(context.scene)
                if item.name == self.group_name
            ),
            None,
        )
        if setting is None:
            return {'CANCELLED'}
        setting.ev += self.ev_delta
        if self.set_tint:
            setting.tint = self.tint
        return {'FINISHED'}


class LLP_OT_remove_light_group(LightHelperOperator, bpy.types.Operator):
    bl_idname = "scene.light_helper_light_group_remove"
    bl_label = "Remove Light Group Pass"
    bl_description = "Remove the View Layer pass without changing object assignments"
    bl_options = {"REGISTER", "UNDO"}

    group_name: bpy.props.StringProperty(name="Light Group")

    def execute(self, context):
        if not remove_light_group(
            context.scene, context.view_layer, self.group_name, context=context
        ):
            self.report({"WARNING"}, p_("Light Group was not found or could not be removed"))
            return {"CANCELLED"}
        return {"FINISHED"}


class LLP_OT_build_light_group_compositor(LightHelperOperator, bpy.types.Operator):
    bl_idname = "scene.light_helper_light_group_build_compositor"
    bl_label = "Build Light Group Mixer"
    bl_description = "Build an idempotent residual plus adjusted Light Group compositor chain"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if context.scene.render.engine == "CYCLES":
            return True
        cls.poll_message_set(p_("Light Group Mixer requires Cycles"))
        return False

    def execute(self, context):
        try:
            _sync_settings(context.scene, context.view_layer)
            names = set(light_group_names(context.view_layer))
            adjustments = {
                item.name: GroupAdjustment(
                    name=item.name,
                    ev=float(item.ev),
                    tint=tuple(float(value) for value in item.tint),
                )
                for item in _settings(context.scene)
                if item.name in names
            }
            result = build_light_group_compositor(
                context.scene, context.view_layer, adjustments
            )
        except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
            self.report({"ERROR"}, p_("Light Group Mixer build failed: %s") % str(exc))
            return {"CANCELLED"}
        if result.warnings:
            self.report({"WARNING"}, p_(result.warnings[0]))
        else:
            self.report(
                {"INFO"}, p_("Built Light Group Mixer for %d group(s)") % result.group_count
            )
        return {"FINISHED"}


class LLP_OT_remove_light_group_compositor(LightHelperOperator, bpy.types.Operator):
    bl_idname = "scene.light_helper_light_group_remove_compositor"
    bl_label = "Remove Light Group Mixer"
    bl_description = "Remove only compositor nodes owned by LightHelper"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        removed = remove_managed_light_group_compositor(context.scene)
        self.report({"INFO"}, p_("Removed %d managed compositor node(s)") % removed)
        return {"FINISHED"}


classes = (
    LLP_PG_light_group_setting,
    LLP_OT_sync_light_groups,
    LLP_OT_assign_light_group,
    LLP_OT_assign_world_light_group,
    LLP_OT_adjust_light_group,
    LLP_OT_remove_light_group,
    LLP_OT_build_light_group_compositor,
    LLP_OT_remove_light_group_compositor,
)


def register_scene_properties() -> None:
    bpy.types.Scene.light_helper_light_group_settings = bpy.props.CollectionProperty(
        type=LLP_PG_light_group_setting
    )
    bpy.types.Scene.light_helper_light_group_index = bpy.props.IntProperty(default=-1)


def unregister_scene_properties() -> None:
    for name in ("light_helper_light_group_index", "light_helper_light_group_settings"):
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
