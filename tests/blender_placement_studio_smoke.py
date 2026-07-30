"""Background Blender smoke for Placement/Studio API contracts.

Run with Blender's ``--factory-startup --background --python-exit-code 1`` and
isolated BLENDER_USER_* roots.
"""

from pathlib import Path
import sys
from types import SimpleNamespace

import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from LightHelper.ops.placement import (  # noqa: E402
    LLP_OT_place_light,
    PLACEMENT_OPERATOR_CLASSES,
    _restore_target,
    _snapshot_target,
)
from LightHelper.ops.studio import STUDIO_OPERATOR_CLASSES  # noqa: E402
from LightHelper.ui.placement_tool import VIEW3D_WT_light_helper_placement  # noqa: E402
from LightHelper.utils.studio import (  # noqa: E402
    ROLE_SCRIM_MATERIAL,
    ROLE_TRACK_TARGET,
    StudioEngineError,
    create_flag,
    create_reflector,
    create_scrim,
    ensure_track_to,
    ensure_unique_studio_data,
    is_managed,
    remove_managed_track_to,
    remove_studio_object,
    set_scrim_exposure,
)


def main():
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'

    scrim = create_scrim(scene, shape='ELLIPSE', feather=0.35, gradient_direction='RADIAL')
    assert scrim.type == 'MESH'
    assert scrim.active_material is not None
    assert is_managed(scrim.active_material, role=ROLE_SCRIM_MATERIAL)
    assert scrim.active_material.node_tree.nodes.get("Scrim Emission") is not None
    assert set_scrim_exposure(scrim, 1.0)
    assert scrim.active_material.node_tree.nodes["Scrim Strength"].inputs[1].default_value == 20.0

    duplicate = scrim.copy()
    scene.collection.objects.link(duplicate)
    assert duplicate.data == scrim.data
    assert ensure_unique_studio_data(duplicate)
    assert duplicate.data != scrim.data
    assert duplicate.active_material != scrim.active_material

    engine_items = scene.render.bl_rna.properties["engine"].enum_items.keys()
    eevee_engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in engine_items else 'BLENDER_EEVEE'
    scene.render.engine = eevee_engine
    flag = create_flag(scene, shape='RECTANGLE', thickness=0.05)
    assert flag.type == 'MESH'
    try:
        create_reflector(scene)
    except StudioEngineError:
        pass
    else:
        raise AssertionError("Eevee reflector creation must be rejected")

    scene.render.engine = 'CYCLES'
    reflector = create_reflector(scene, shape='ELLIPSE')
    assert reflector.type == 'MESH'

    data_a = bpy.data.lights.new("LH Smoke A", 'AREA')
    light_a = bpy.data.objects.new("LH Smoke A", data_a)
    scene.collection.objects.link(light_a)
    data_b = bpy.data.lights.new("LH Smoke B", 'SPOT')
    light_b = bpy.data.objects.new("LH Smoke B", data_b)
    scene.collection.objects.link(light_b)
    constraint_a, target = ensure_track_to(scene, light_a, location=(1.0, 2.0, 3.0))
    constraint_b, target_b = ensure_track_to(scene, light_b, target)
    assert constraint_a.track_axis == 'TRACK_NEGATIVE_Z'
    assert constraint_b.up_axis == 'UP_Y'
    assert target_b == target and is_managed(target, role=ROLE_TRACK_TARGET)
    target_name = target.name
    assert remove_managed_track_to(light_a) == 1
    assert target_name in bpy.data.objects
    assert remove_managed_track_to(light_b) == 1
    assert target_name not in bpy.data.objects

    classes = (*PLACEMENT_OPERATOR_CLASSES, *STUDIO_OPERATOR_CLASSES)
    registered = []
    tool_registered = False
    try:
        for cls in classes:
            bpy.utils.register_class(cls)
            registered.append(cls)
        bpy.utils.register_tool(VIEW3D_WT_light_helper_placement, separator=True, group=False)
        tool_registered = True
        rna = bpy.ops.view3d.light_helper_place.get_rna_type().properties
        assert rna.get("mode") is not None
        assert rna.get("target_kind") is not None
        assert bpy.types.Operator.bl_rna_get_subclass_py("VIEW3D_OT_light_helper_place") is not None
        light_snapshot = _snapshot_target(light_a)
        light_a.location = (9.0, 8.0, 7.0)
        light_a.data.energy = 321.0
        _restore_target(light_a, light_snapshot)
        assert tuple(light_a.location) == (0.0, 0.0, 0.0)
        assert light_a.data.energy == light_snapshot["data.energy"]
        placement_state = SimpleNamespace(
            mode='DIRECT',
            distance=4.0,
            _target=light_a,
            _last_hit=(0.0, 0.0, 0.0),
            _last_normal=(0.0, 0.0, 1.0),
            _last_view=(0.0, 0.0, 1.0),
            _last_orbit=None,
            _roll=0.0,
        )
        assert LLP_OT_place_light._apply_last_solution(placement_state)
        assert tuple(round(value, 6) for value in light_a.matrix_world.translation) == (0.0, 0.0, 4.0)
    finally:
        if tool_registered:
            bpy.utils.unregister_tool(VIEW3D_WT_light_helper_placement)
        for cls in reversed(registered):
            bpy.utils.unregister_class(cls)

    for obj in (duplicate, scrim, flag, reflector):
        assert remove_studio_object(obj)
    for obj, data in ((light_a, data_a), (light_b, data_b)):
        bpy.data.objects.remove(obj, do_unlink=True)
        if data.users == 0:
            bpy.data.lights.remove(data)

    print(f"LIGHTHELPER_PLACEMENT_STUDIO_SMOKE_OK {bpy.app.version_string}")


main()
