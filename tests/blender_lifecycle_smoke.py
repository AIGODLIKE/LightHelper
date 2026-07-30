"""Undo/Redo and File New lifecycle coverage in a registered extension."""

from __future__ import annotations

import sys
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

import LightHelper  # noqa: E402
from LightHelper.ops.light_mixer import (  # noqa: E402
    enable_false_color,
    is_false_color_enabled,
)
from LightHelper.ui.desk import active_desk_count  # noqa: E402
from LightHelper.utils import (  # noqa: E402
    ChannelState,
    CollectionType,
    get_item_channel_state,
)


LightHelper.register()
try:
    scene = bpy.context.scene
    light_data = bpy.data.lights.new("Lifecycle Light", 'AREA')
    light = bpy.data.objects.new("Lifecycle Light", light_data)
    target = bpy.data.objects.new("Lifecycle Target", None)
    scene.collection.objects.link(light)
    scene.collection.objects.link(target)
    bpy.context.view_layer.update()

    can_undo = bpy.ops.ed.undo.poll()
    if can_undo:
        bpy.ops.ed.undo_push(message="Before LightHelper Link")
    assert bpy.ops.object.light_helper_desk_set_channel(
        source_name=light.name,
        item_name=target.name,
        item_kind='OBJECT',
        channel='RECEIVER',
        state='INCLUDE',
    ) == {'FINISHED'}
    assert get_item_channel_state(
        light, target, CollectionType.RECEIVER,
    ) == ChannelState.INCLUDE
    if can_undo:
        assert bpy.ops.ed.undo() == {'FINISHED'}
        light = bpy.data.objects.get("Lifecycle Light")
        target = bpy.data.objects.get("Lifecycle Target")
        assert light is not None and target is not None
        assert get_item_channel_state(
            light, target, CollectionType.RECEIVER,
        ) == ChannelState.OFF
        assert bpy.ops.ed.redo() == {'FINISHED'}
        light = bpy.data.objects.get("Lifecycle Light")
        target = bpy.data.objects.get("Lifecycle Target")
        assert get_item_channel_state(
            light, target, CollectionType.RECEIVER,
        ) == ChannelState.INCLUDE
    else:
        print("LIGHTHELPER_UNDO_SKIPPED_NO_WINDOW")

    assert enable_false_color(scene)
    assert is_false_color_enabled(scene)
    assert bpy.ops.wm.read_homefile(use_empty=True) == {'FINISHED'}
    assert active_desk_count() == 0
    assert hasattr(bpy.types.Scene, "light_helper_profiles")
    assert not is_false_color_enabled(bpy.context.scene)
    print("LIGHTHELPER_LIFECYCLE_OK", bpy.app.version_string)
finally:
    LightHelper.unregister()
