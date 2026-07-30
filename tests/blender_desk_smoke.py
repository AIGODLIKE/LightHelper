"""Isolated Blender smoke for Desk/Mixer leaf registration and RNA writes."""

from pathlib import Path
import sys

import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from LightHelper.ops.desk import DESK_CLASSES  # noqa: E402
from LightHelper.ops.light_mixer import (  # noqa: E402
    LIGHT_MIXER_CLASSES,
    enable_false_color,
    get_kelvin_state,
    restore_false_color,
)
from LightHelper.ui.desk import capture_desk_snapshot, cleanup_all_desks  # noqa: E402
from LightHelper.utils import ChannelState, CollectionType, get_item_channel_state  # noqa: E402
from LightHelper import property as light_helper_property  # noqa: E402


classes = LIGHT_MIXER_CLASSES + DESK_CLASSES
light_helper_property.register()
for cls in classes:
    bpy.utils.register_class(cls)

try:
    scene = bpy.context.scene
    light_data = bpy.data.lights.new("Desk Smoke Light", 'AREA')
    light = bpy.data.objects.new("Desk Smoke Light", light_data)
    receiver = bpy.data.objects.new("Desk Smoke Receiver", bpy.data.meshes.new("Desk Smoke Mesh"))
    scene.collection.objects.link(light)
    scene.collection.objects.link(receiver)

    props = bpy.ops.object.light_helper_desk_set_channel.get_rna_type().properties
    assert props.get("state") is not None
    result = bpy.ops.object.light_helper_desk_set_channel(
        source_name=light.name,
        item_name=receiver.name,
        item_kind='OBJECT',
        channel='RECEIVER',
        state='INCLUDE',
    )
    assert result == {'FINISHED'}, result
    assert get_item_channel_state(light, receiver, CollectionType.RECEIVER) == ChannelState.INCLUDE

    light_data.energy = 100.0
    result = bpy.ops.object.light_helper_mixer_batch(
        target_names_json='["Desk Smoke Light"]',
        action='ADJUST_EV',
        value=1.0,
    )
    assert result == {'FINISHED'}, result
    assert light_data.energy == 200.0

    area_copy_data = bpy.data.lights.new("Desk Smoke Area Copy", 'AREA')
    area_copy = bpy.data.objects.new("Desk Smoke Area Copy", area_copy_data)
    point_data = bpy.data.lights.new("Desk Smoke Point", 'POINT')
    point = bpy.data.objects.new("Desk Smoke Point", point_data)
    scene.collection.objects.link(area_copy)
    scene.collection.objects.link(point)
    light_data.size = 3.25
    area_copy_data.size = 0.75
    area_pointer = area_copy_data.as_pointer()
    point_pointer = point_data.as_pointer()
    assert bpy.ops.object.light_helper_mixer_copy(source_name=light.name, full=True) == {'FINISHED'}
    targets = '["Desk Smoke Area Copy", "Desk Smoke Point"]'
    assert bpy.ops.object.light_helper_mixer_paste(target_names_json=targets, full=False) == {'FINISHED'}
    assert area_copy_data.energy == light_data.energy
    assert area_copy_data.size == 0.75
    assert bpy.ops.object.light_helper_mixer_paste(target_names_json=targets, full=True) == {'FINISHED'}
    assert area_copy_data.size == light_data.size
    assert area_copy_data.as_pointer() == area_pointer
    assert point_data.as_pointer() == point_pointer

    assert bpy.ops.object.light_helper_mixer_batch(
        target_names_json='["Desk Smoke Light"]',
        action='SET_KELVIN',
        value=3200.0,
    ) == {'FINISHED'}
    assert get_kelvin_state(light) == (True, 3200.0)
    assert bpy.ops.object.light_helper_mixer_batch(
        target_names_json='["Desk Smoke Light"]',
        action='SET_RGB',
        color=(0.2, 0.3, 0.4),
    ) == {'FINISHED'}
    assert get_kelvin_state(light)[0] is False

    previous = scene.view_settings.view_transform
    assert enable_false_color(scene)
    assert scene.view_settings.view_transform == "False Color"
    assert restore_false_color(scene)
    assert scene.view_settings.view_transform == previous

    snapshot = capture_desk_snapshot(scene, 7)
    row = next(row for row in snapshot.rows if row.source_name == light.name)
    target_index = next(index for index, target in enumerate(snapshot.targets) if target.name == receiver.name)
    assert row.cells[target_index].illumination == "INCLUDE"
    assert snapshot.revision == 7
    print("LIGHTHELPER_DESK_SMOKE_OK", bpy.app.version_string)
finally:
    cleanup_all_desks()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    light_helper_property.unregister()
