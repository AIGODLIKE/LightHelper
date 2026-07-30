"""Foreground-only regression for the Lighting Desk modal owner lifetime."""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

import LightHelper  # noqa: E402
from LightHelper.ops.desk import LLP_OT_lighting_desk  # noqa: E402


OUTPUT = ROOT / ".tmp" / "desk-foreground-lifecycle.json"
STATE = {
    "events": [],
    "active_after_delay": False,
    "docked_scene_visible": False,
    "error": "",
}
_ORIGINAL_MODAL = LLP_OT_lighting_desk.modal


def _pointer(value) -> int:
    try:
        return int(value.as_pointer())
    except (AttributeError, ReferenceError, TypeError):
        return 0


def _recording_modal(self, context, event):
    session = getattr(self, "_session", None)
    entry = {
        "event": event.type,
        "value": event.value,
        "has_session": session is not None,
    }
    if session is not None:
        try:
            entry.update({
                "alive_before": session.is_owner_alive(),
                "screen_identity": session.window.screen is session.screen,
                "screen_pointer_equal": (
                    _pointer(session.window.screen) == _pointer(session.screen)
                ),
                "area_pointer_present": any(
                    _pointer(area) == session.area_key
                    for area in session.window.screen.areas
                ),
                "context_area_pointer": _pointer(context.area),
                "owner_area_pointer": session.area_key,
                "context_region_pointer": _pointer(context.region),
                "owner_region_pointer": session.region_key,
                "area_region_pointers": [
                    (region.type, _pointer(region))
                    for region in session.area.regions
                ],
            })
        except Exception:
            entry["diagnostic_error"] = traceback.format_exc()
    STATE["events"].append(entry)
    return _ORIGINAL_MODAL(self, context, event)


def _view3d_override():
    window = bpy.context.window_manager.windows[0]
    area = next(area for area in window.screen.areas if area.type == "VIEW_3D")
    region = next(region for region in area.regions if region.type == "WINDOW")
    return window, area, region


def _finish():
    try:
        from LightHelper.ui.desk import (
            active_desk_count,
            cleanup_all_desks,
            get_desk_session,
        )

        STATE["active_after_delay"] = active_desk_count() == 1
        window, area, region = _view3d_override()
        session = get_desk_session(window, area)
        if session is not None:
            bounds = session.desk_bounds(region)
            STATE["docked_scene_visible"] = (
                not session.expanded
                and bounds.top < region.height
                and region.height - bounds.top >= 100
            )
        if not STATE["active_after_delay"] and not STATE["error"]:
            STATE["error"] = "Lighting Desk did not survive the initial foreground events"
        if not STATE["docked_scene_visible"] and not STATE["error"]:
            STATE["error"] = "Docked Lighting Desk did not preserve visible scene space"
        cleanup_all_desks()
        LightHelper.unregister()
    except Exception:
        STATE["error"] = traceback.format_exc()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(STATE, indent=2), encoding="utf-8")
    bpy.ops.wm.quit_blender()
    return None


def _start():
    try:
        LLP_OT_lighting_desk.modal = _recording_modal
        LightHelper.register()
        window, area, region = _view3d_override()
        with bpy.context.temp_override(window=window, area=area, region=region):
            result = bpy.ops.view3d.light_helper_lighting_desk("INVOKE_DEFAULT")
        if result != {"RUNNING_MODAL"}:
            raise AssertionError(f"Unexpected Desk invoke result: {result}")
    except Exception:
        STATE["error"] = traceback.format_exc()
    bpy.app.timers.register(_finish, first_interval=1.0)
    return None


bpy.app.timers.register(_start, first_interval=0.25)
