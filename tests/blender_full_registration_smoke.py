"""Full integrated registration/lifecycle smoke for Blender-hosted runs."""

from __future__ import annotations

import sys
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

import LightHelper  # noqa: E402
from LightHelper.ops.light_mixer import enable_false_color  # noqa: E402


def light_helper_handlers():
    collections = (
        bpy.app.handlers.load_pre,
        bpy.app.handlers.load_post,
        bpy.app.handlers.undo_pre,
        bpy.app.handlers.undo_post,
        bpy.app.handlers.redo_pre,
        bpy.app.handlers.redo_post,
        bpy.app.handlers.depsgraph_update_post,
    )
    return [
        handler
        for collection in collections
        for handler in collection
        if getattr(handler, "__module__", "").startswith("LightHelper")
    ]


def cycle() -> None:
    scene = bpy.context.scene
    previous_transform = scene.view_settings.view_transform
    LightHelper.register()
    assert hasattr(bpy.types.Object, "light_helper_property")
    assert hasattr(bpy.types.Scene, "light_helper_profiles")
    assert hasattr(bpy.types.Scene, "light_helper_light_group_settings")
    assert hasattr(bpy.types.WindowManager, "light_helper_property")
    assert bpy.ops.view3d.light_helper_lighting_desk.get_rna_type() is not None
    assert bpy.ops.view3d.light_helper_place.get_rna_type() is not None
    assert bpy.ops.scene.light_helper_profile_capture.get_rna_type() is not None
    assert bpy.ops.scene.light_helper_light_group_build_compositor.get_rna_type() is not None
    assert enable_false_color(scene)
    LightHelper.unregister()
    assert scene.view_settings.view_transform == previous_transform
    assert not hasattr(bpy.types.Object, "light_helper_property")
    assert not hasattr(bpy.types.Scene, "light_helper_profiles")
    assert not hasattr(bpy.types.Scene, "light_helper_light_group_settings")
    assert not light_helper_handlers(), light_helper_handlers()


cycle()
cycle()
print("LIGHTHELPER_FULL_REGISTRATION_OK", bpy.app.version_string)
