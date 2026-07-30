"""Populate an isolated foreground Blender session for manual visual QA."""

from __future__ import annotations

import math
import sys
import traceback
import json
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

import LightHelper  # noqa: E402
from LightHelper.utils import ChannelState, CollectionType, set_item_channel_state  # noqa: E402


VERSION_TAG = f"{bpy.app.version[0]}.{bpy.app.version[1]}"
QA_DIRECTORY = ROOT / ".tmp" / f"foreground-{VERSION_TAG}"
QA_DIRECTORY.mkdir(parents=True, exist_ok=True)
QA_STATE = {"step": 0, "checks": [], "error": ""}


def view3d_override(window=None):
    window = window or bpy.context.window_manager.windows[0]
    area = next(area for area in window.screen.areas if area.type == 'VIEW_3D')
    region = next(region for region in area.regions if region.type == 'WINDOW')
    return window, area, region


def record(check, value=True):
    if not value:
        raise AssertionError(check)
    QA_STATE["checks"].append(check)


def write_result():
    (QA_DIRECTORY / "result.json").write_text(
        json.dumps(QA_STATE, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def setup_scene():
    LightHelper.register()
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    for obj in tuple(scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    mesh = bpy.data.meshes.new("QA Surface Mesh")
    mesh.from_pydata(
        [(-6, -6, 0), (6, -6, 0), (6, 6, 0), (-6, 6, 0)],
        [],
        [(0, 1, 2, 3)],
    )
    surface = bpy.data.objects.new("QA Placement Surface", mesh)
    scene.collection.objects.link(surface)

    targets = [surface]
    for index in range(299):
        target = bpy.data.objects.new(f"Target {index + 1:03d}", None)
        target.empty_display_type = 'CUBE'
        target.empty_display_size = 0.15
        target.location = (
            (index % 20) * 0.5 - 5.0,
            ((index // 20) % 15) * 0.5 - 3.5,
            0.2,
        )
        scene.collection.objects.link(target)
        targets.append(target)

    lights = []
    for index in range(100):
        data = bpy.data.lights.new(f"Light {index + 1:03d}", 'AREA')
        data.energy = 200.0 * (2.0 ** ((index % 7 - 3) * 0.25))
        data.shape = 'DISK' if index % 2 else 'RECTANGLE'
        data.size = 1.0 + (index % 5) * 0.25
        light = bpy.data.objects.new(data.name, data)
        angle = index * (math.tau / 100.0)
        light.location = (math.cos(angle) * 8.0, math.sin(angle) * 8.0, 4.0)
        light.rotation_euler = (0.0, 0.0, angle)
        scene.collection.objects.link(light)
        lights.append(light)

    for index, light in enumerate(lights[:12]):
        light.light_helper_property.linking_edit_mode = 'ADVANCED'
        set_item_channel_state(
            light,
            targets[index],
            CollectionType.RECEIVER,
            ChannelState.INCLUDE if index % 2 == 0 else ChannelState.EXCLUDE,
        )
        set_item_channel_state(
            light,
            targets[index + 12],
            CollectionType.BLOCKER,
            ChannelState.EXCLUDE if index % 2 == 0 else ChannelState.INCLUDE,
        )

    view_layer = bpy.context.view_layer
    for name in ("Key", "Fill", "Rim"):
        item = view_layer.lightgroups.add()
        item.name = name
        setting = scene.light_helper_light_group_settings.add()
        setting.name = name
    lights[0].lightgroup = "Key"
    lights[1].lightgroup = "Fill"
    lights[2].lightgroup = "Rim"

    bpy.context.view_layer.objects.active = lights[0]
    lights[0].select_set(True)
    bpy.ops.scene.light_helper_profile_capture(name="QA Look")

    try:
        preferences = bpy.context.preferences
        preferences.view.use_translate_interface = bpy.app.version >= (5, 0, 0)
        if bpy.app.version >= (5, 0, 0):
            preferences.view.language = 'zh_HANS'
            if hasattr(preferences.system, "ui_scale"):
                preferences.system.ui_scale = 1.5
    except (AttributeError, TypeError, ValueError):
        pass

    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != 'VIEW_3D':
                continue
            region = next((region for region in area.regions if region.type == 'WINDOW'), None)
            if region is None:
                continue
            with bpy.context.temp_override(window=window, area=area, region=region):
                bpy.ops.view3d.light_helper_lighting_desk('INVOKE_DEFAULT')
            bpy.app.timers.register(run_foreground_qa, first_interval=1.0)
            return None
    return 0.25


def capture_tab(tab):
    from LightHelper.ui.desk import get_desk_session

    window, area, region = view3d_override()
    session = get_desk_session(window, area)
    record(f"desk_session_{tab.lower()}", session is not None)
    session.tab = tab
    session.refresh_snapshot()
    with bpy.context.temp_override(window=window, area=area, region=region):
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=3)
        result = bpy.ops.screen.screenshot(
            filepath=str(QA_DIRECTORY / f"desk_{tab.lower()}.png"),
            check_existing=False,
        )
    record(f"screenshot_{tab.lower()}", result == {'FINISHED'})


def interaction_checks():
    from LightHelper.ops.light_mixer import enable_false_color, restore_false_color
    from LightHelper.ops.placement import _ACTIVE_PLACEMENTS, cancel_all_placements
    from LightHelper.ui.desk import active_desk_count, cleanup_all_desks
    from LightHelper.utils import get_item_channel_state

    window, area, region = view3d_override()
    scene = bpy.context.scene
    light = scene.objects["Light 001"]
    target = scene.objects["Target 050"]
    with bpy.context.temp_override(window=window, area=area, region=region):
        if bpy.ops.ed.undo.poll():
            bpy.ops.ed.undo_push(message="LightHelper Foreground QA")
            record(
                "desk_link_operator",
                bpy.ops.object.light_helper_desk_set_channel(
                    source_name=light.name,
                    item_name=target.name,
                    item_kind='OBJECT',
                    channel='RECEIVER',
                    state='INCLUDE',
                ) == {'FINISHED'},
            )
            record(
                "desk_link_include",
                get_item_channel_state(light, target, CollectionType.RECEIVER)
                == ChannelState.INCLUDE,
            )
            record("foreground_undo", bpy.ops.ed.undo() == {'FINISHED'})
            light = scene.objects["Light 001"]
            target = scene.objects["Target 050"]
            record(
                "foreground_undo_state",
                get_item_channel_state(light, target, CollectionType.RECEIVER)
                == ChannelState.OFF,
            )
            record("foreground_redo", bpy.ops.ed.redo() == {'FINISHED'})
        else:
            QA_STATE["checks"].append("foreground_undo_poll_unavailable")

        previous = scene.view_settings.view_transform
        record("false_color_enable", enable_false_color(scene))
        record("false_color_restore", restore_false_color(scene))
        record("false_color_exact", scene.view_settings.view_transform == previous)

        before_lights = sum(obj.type == 'LIGHT' for obj in scene.objects)
        placement_result = bpy.ops.view3d.light_helper_place(
            'INVOKE_DEFAULT',
            adjust_selected=False,
            target_kind='LIGHT',
            light_type='AREA',
            mode='DIRECT',
        )
        if placement_result == {'RUNNING_MODAL'}:
            record("placement_owner", bool(_ACTIVE_PLACEMENTS))
            cancel_all_placements()
            record("placement_cancel_owner", not _ACTIVE_PLACEMENTS)
            record(
                "placement_cancel_count",
                sum(obj.type == 'LIGHT' for obj in scene.objects) == before_lights,
            )
        else:
            QA_STATE["checks"].append(f"placement_invoke_{placement_result}")

        initial_windows = len(bpy.context.window_manager.windows)
        if bpy.ops.wm.window_new() == {'FINISHED'}:
            record(
                "second_window_created",
                len(bpy.context.window_manager.windows) == initial_windows + 1,
            )
            second = bpy.context.window_manager.windows[-1]
            second_window, second_area, second_region = view3d_override(second)
            with bpy.context.temp_override(
                window=second_window, area=second_area, region=second_region,
            ):
                bpy.ops.view3d.light_helper_lighting_desk('INVOKE_DEFAULT')
            record("dual_window_desk_owners", active_desk_count() == 2)
            cleanup_all_desks()
            with bpy.context.temp_override(window=second_window):
                bpy.ops.wm.window_close()


def finish_foreground_qa():
    try:
        from LightHelper.ui.desk import cleanup_all_desks
        from LightHelper.ops.placement import cancel_all_placements
        cleanup_all_desks()
        cancel_all_placements()
        LightHelper.unregister()
    except Exception:
        if not QA_STATE["error"]:
            QA_STATE["error"] = traceback.format_exc()
    write_result()
    bpy.ops.wm.quit_blender()
    return None


def run_foreground_qa():
    try:
        steps = ('LINK', 'MIX', 'LOOKS', 'STUDIO')
        if QA_STATE["step"] < len(steps):
            capture_tab(steps[QA_STATE["step"]])
            QA_STATE["step"] += 1
            return 0.75
        interaction_checks()
    except Exception:
        QA_STATE["error"] = traceback.format_exc()
    bpy.app.timers.register(finish_foreground_qa, first_interval=0.5)
    return None


bpy.app.timers.register(setup_scene, first_interval=0.5)
