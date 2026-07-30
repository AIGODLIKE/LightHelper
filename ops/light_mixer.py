"""Undoable Lighting Desk mixer operations and temporary diagnostics."""

import json

import bpy
from bpy.app.handlers import persistent
from bpy.app.translations import pgettext_iface as p_

from .common import LightHelperOperator
from ..utils.desk_layout import (
    MIXER_COLUMN_SETS,
    MixerRowSnapshot,
    apply_ev,
    apply_linear_tint,
    colors_close,
    kelvin_to_linear_rgb,
)


KELVIN_PRESETS = (
    ("CANDLE", "Candle", 1850.0),
    ("TUNGSTEN", "Tungsten", 3200.0),
    ("WARM", "Warm LED", 4000.0),
    ("DAYLIGHT", "Daylight", 5600.0),
    ("OVERCAST", "Overcast", 6500.0),
    ("SKY", "Blue Sky", 10000.0),
)
COMMON_LIGHT_PROPERTIES = (
    "energy",
    "color",
    "use_shadow",
    "diffuse_factor",
    "specular_factor",
    "transmission_factor",
    "volume_factor",
    "normalize",
)
TYPE_LIGHT_PROPERTIES = {
    "POINT": ("shadow_soft_size",),
    "SUN": ("angle",),
    "SPOT": ("shadow_soft_size", "spot_size", "spot_blend", "show_cone"),
    "AREA": ("shape", "size", "size_y", "spread"),
}
SCALAR_EDIT_PROPERTIES = frozenset(
    property_name
    for property_name in COMMON_LIGHT_PROPERTIES + tuple(
        item for values in TYPE_LIGHT_PROPERTIES.values() for item in values
    )
    if property_name not in {"color", "use_shadow", "normalize", "shape", "show_cone"}
)

_MIXER_CLIPBOARD = None
_FALSE_COLOR_STATES = {}


def _pointer(value) -> int:
    try:
        return int(value.as_pointer())
    except (AttributeError, ReferenceError, TypeError):
        return 0


def _light_objects(context, names_json: str = "") -> list:
    names = None
    if names_json:
        try:
            decoded = json.loads(names_json)
        except (TypeError, ValueError, json.JSONDecodeError):
            decoded = []
        if isinstance(decoded, list) and decoded:
            names = {str(name) for name in decoded}
        elif isinstance(decoded, list):
            names = {
                obj.name for obj in context.selected_objects
                if obj.type == 'LIGHT' and obj.data is not None
            }
    result = []
    for obj in context.scene.objects:
        if obj.type != 'LIGHT' or obj.data is None:
            continue
        if names is not None and obj.name not in names:
            continue
        result.append(obj)
    return result


def _read_property(data, property_name):
    if not hasattr(data, property_name):
        return None
    value = getattr(data, property_name)
    if property_name == "color":
        return tuple(float(item) for item in value[:3])
    if isinstance(value, (bool, int, float, str)):
        return value
    return None


def _is_muted(light) -> bool:
    try:
        return bool(light.get("light_helper_mute", False))
    except (AttributeError, ReferenceError, TypeError):
        return False


def _set_muted(light, muted: bool) -> None:
    muted = bool(muted)
    if muted == _is_muted(light):
        return
    if muted:
        light["light_helper_mute_prev_viewport"] = bool(light.hide_viewport)
        light["light_helper_mute_prev_render"] = bool(light.hide_render)
        light["light_helper_mute"] = True
        light.hide_viewport = True
        light.hide_render = True
    else:
        light.hide_viewport = bool(light.get("light_helper_mute_prev_viewport", False))
        light.hide_render = bool(light.get("light_helper_mute_prev_render", False))
        for key in (
            "light_helper_mute",
            "light_helper_mute_prev_viewport",
            "light_helper_mute_prev_render",
        ):
            try:
                del light[key]
            except KeyError:
                pass


def _set_kelvin_metadata(light, enabled: bool, temperature: float) -> None:
    props = getattr(light, "light_helper_property", None)
    if props is not None and hasattr(props, "kelvin_mode"):
        props.kelvin_mode = bool(enabled)
        if hasattr(props, "kelvin_temperature"):
            props.kelvin_temperature = float(temperature)
        return
    light["light_helper_kelvin_mode"] = bool(enabled)
    light["light_helper_kelvin_temperature"] = float(temperature)


def get_kelvin_state(light) -> tuple[bool, float]:
    props = getattr(light, "light_helper_property", None)
    if props is not None and hasattr(props, "kelvin_mode"):
        enabled = bool(props.kelvin_mode)
        temperature = float(getattr(props, "kelvin_temperature", 5600.0))
    else:
        enabled = bool(light.get("light_helper_kelvin_mode", False))
        temperature = float(light.get("light_helper_kelvin_temperature", 5600.0))
    if enabled and not colors_close(light.data.color, kelvin_to_linear_rgb(temperature), 2e-4):
        # A native RGB edit logically exits Kelvin mode without writing from a
        # read/snapshot path.  The next Desk color operation updates metadata.
        enabled = False
    return enabled, temperature


def set_light_kelvin(light, temperature: float) -> None:
    temperature = min(40000.0, max(1000.0, float(temperature)))
    color = kelvin_to_linear_rgb(temperature)
    if not colors_close(light.data.color, color):
        light.data.color = color
    _set_kelvin_metadata(light, True, temperature)


def set_light_rgb(light, color) -> None:
    color = tuple(min(1.0, max(0.0, float(value))) for value in color[:3])
    if not colors_close(light.data.color, color):
        light.data.color = color
    _, previous_temperature = get_kelvin_state(light)
    _set_kelvin_metadata(light, False, previous_temperature)


def capture_light_settings(light, full: bool = False) -> dict:
    data = light.data
    payload = {"source_type": str(data.type), "values": {}}
    property_names = list(COMMON_LIGHT_PROPERTIES)
    if full:
        property_names.extend(TYPE_LIGHT_PROPERTIES.get(data.type, ()))
    for property_name in property_names:
        value = _read_property(data, property_name)
        if value is not None:
            payload["values"][property_name] = value
    kelvin_mode, temperature = get_kelvin_state(light)
    payload["kelvin_mode"] = kelvin_mode
    payload["kelvin_temperature"] = temperature
    return payload


def apply_light_settings(light, payload: dict, full: bool = False) -> int:
    data = light.data
    allowed = set(COMMON_LIGHT_PROPERTIES)
    if full and payload.get("source_type") == data.type:
        allowed.update(TYPE_LIGHT_PROPERTIES.get(data.type, ()))
    changed = 0
    values = payload.get("values", {})
    if not isinstance(values, dict):
        return 0
    for property_name, value in values.items():
        if property_name not in allowed or not hasattr(data, property_name):
            continue
        try:
            current = getattr(data, property_name)
            if property_name == "color":
                candidate = tuple(float(item) for item in value[:3])
                if colors_close(current, candidate):
                    continue
            elif current == value:
                continue
            setattr(data, property_name, value)
            changed += 1
        except (AttributeError, TypeError, ValueError):
            continue
    if payload.get("kelvin_mode"):
        set_light_kelvin(light, float(payload.get("kelvin_temperature", 5600.0)))
    elif "color" in values:
        _set_kelvin_metadata(light, False, float(payload.get("kelvin_temperature", 5600.0)))
    return changed


def mixer_row_snapshot(light, link_count: int = 0) -> MixerRowSnapshot:
    data = light.data
    size = getattr(data, "size", getattr(data, "shadow_soft_size", getattr(data, "angle", 0.0)))
    spot = (getattr(data, "spot_size", None), getattr(data, "spot_blend", None))
    kelvin_mode, kelvin_temperature = get_kelvin_state(light)
    try:
        solo = bpy.context.window_manager.light_helper_property.solo_light == light
    except (AttributeError, ReferenceError, RuntimeError, TypeError):
        solo = False
    values = {
        "mute": _is_muted(light),
        "solo": solo,
        "render": not bool(light.hide_render),
        "energy": float(getattr(data, "energy", 0.0)),
        "color": tuple(float(value) for value in data.color[:3]),
        "size": float(size),
        "spot": spot,
        "link_count": int(link_count),
        "light_group": str(getattr(light, "lightgroup", "")),
        "visibility": (
            bool(getattr(light, "visible_camera", True)),
            bool(getattr(light, "visible_diffuse", True)),
            bool(getattr(light, "visible_glossy", True)),
            bool(getattr(light, "visible_transmission", True)),
            bool(getattr(light, "visible_volume_scatter", True)),
        ),
        "diffuse": float(getattr(data, "diffuse_factor", 1.0)),
        "specular": float(getattr(data, "specular_factor", 1.0)),
        "transmission": float(getattr(data, "transmission_factor", 1.0)),
        "volume": float(getattr(data, "volume_factor", 1.0)),
        "shadow": bool(getattr(data, "use_shadow", True)),
        "normalize": getattr(data, "normalize", None),
        "kelvin_mode": kelvin_mode,
        "kelvin_temperature": kelvin_temperature,
    }
    return MixerRowSnapshot(light.name, data.type, tuple(values.items()))


def get_mixer_columns(mode: str) -> tuple[str, ...]:
    return MIXER_COLUMN_SETS.get(str(mode).upper(), MIXER_COLUMN_SETS["NORMAL"])


def is_false_color_enabled(scene) -> bool:
    return _pointer(scene) in _FALSE_COLOR_STATES and scene.view_settings.view_transform == "False Color"


def enable_false_color(scene) -> bool:
    key = _pointer(scene)
    if not key:
        return False
    if key not in _FALSE_COLOR_STATES:
        _FALSE_COLOR_STATES[key] = (scene.name_full, str(scene.view_settings.view_transform))
    if scene.view_settings.view_transform != "False Color":
        scene.view_settings.view_transform = "False Color"
    return True


def restore_false_color(scene) -> bool:
    state = _FALSE_COLOR_STATES.pop(_pointer(scene), None)
    if state is None:
        return False
    previous = state[1]
    try:
        scene.view_settings.view_transform = previous
    except (TypeError, ValueError):
        return False
    return True


def restore_all_false_color() -> None:
    by_pointer = {_pointer(scene): scene for scene in tuple(bpy.data.scenes)}
    for key, (_name, previous) in tuple(_FALSE_COLOR_STATES.items()):
        scene = by_pointer.get(key)
        if scene is not None:
            try:
                scene.view_settings.view_transform = previous
            except (AttributeError, ReferenceError, TypeError, ValueError):
                pass
        _FALSE_COLOR_STATES.pop(key, None)


@persistent
def false_color_load_pre(_dummy):
    restore_all_false_color()


def cleanup_light_mixer_runtime() -> None:
    global _MIXER_CLIPBOARD
    restore_all_false_color()
    _MIXER_CLIPBOARD = None


def register_light_mixer_handlers() -> None:
    if false_color_load_pre not in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.append(false_color_load_pre)


def unregister_light_mixer_handlers() -> None:
    if false_color_load_pre in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(false_color_load_pre)
    cleanup_light_mixer_runtime()


class LLP_OT_light_mixer_batch(LightHelperOperator, bpy.types.Operator):
    bl_idname = "object.light_helper_mixer_batch"
    bl_label = "Edit Light Mixer Selection"
    bl_description = "Apply a Lighting Desk value to the selected lights"
    bl_options = {'REGISTER', 'UNDO'}

    target_names_json: bpy.props.StringProperty(default="[]", options={'HIDDEN', 'SKIP_SAVE'})
    action: bpy.props.EnumProperty(
        items=(
            ("ADJUST_EV", "Adjust EV", "Multiply energy by 2^EV"),
            ("SET_ENERGY", "Set Energy", "Set light energy"),
            ("SET_RGB", "Set RGB", "Set light color and exit Kelvin mode"),
            ("SET_KELVIN", "Set Kelvin", "Set blackbody color temperature"),
            ("TOGGLE_MUTE", "Toggle Mute", "Toggle selected light visibility"),
            ("SET_RENDER", "Set Render", "Set render visibility"),
            ("SET_SCALAR", "Set Property", "Set a supported scalar light property"),
            ("SET_BOOL", "Set Boolean", "Set a supported boolean light property"),
        ),
        options={'HIDDEN', 'SKIP_SAVE'},
    )
    value: bpy.props.FloatProperty(default=0.0, options={'SKIP_SAVE'})
    enabled: bpy.props.BoolProperty(default=True, options={'SKIP_SAVE'})
    color: bpy.props.FloatVectorProperty(
        size=3,
        subtype='COLOR',
        default=(1.0, 1.0, 1.0),
        min=0.0,
        max=1.0,
        options={'SKIP_SAVE'},
    )
    property_name: bpy.props.StringProperty(default="", options={'HIDDEN', 'SKIP_SAVE'})

    def invoke(self, context, _event):
        if self.action == "SET_KELVIN" and self.value < 1000.0:
            self.value = 5600.0
        if self.action in {"SET_ENERGY", "SET_RGB", "SET_KELVIN", "SET_SCALAR"}:
            return context.window_manager.invoke_props_dialog(self)
        return self.execute(context)

    def draw(self, _context):
        if self.action == "SET_RGB":
            self.layout.prop(self, "color")
        elif self.action == "SET_KELVIN":
            self.layout.prop(self, "value", text=p_("Temperature"))
        elif self.action == "SET_ENERGY":
            self.layout.prop(self, "value", text=p_("Energy"))
        elif self.action == "SET_SCALAR":
            self.layout.prop(self, "value", text=p_("Value"))

    def execute(self, context):
        lights = _light_objects(context, self.target_names_json)
        if not lights:
            self.report({'WARNING'}, p_("No light selected"))
            return {'CANCELLED'}
        changed = 0
        for light in lights:
            data = light.data
            if self.action == "ADJUST_EV":
                candidate = apply_ev(data.energy, self.value)
                if candidate != data.energy:
                    data.energy = candidate
                    changed += 1
            elif self.action == "SET_ENERGY":
                candidate = max(0.0, self.value)
                if candidate != data.energy:
                    data.energy = candidate
                    changed += 1
            elif self.action == "SET_RGB":
                before = tuple(data.color[:3])
                set_light_rgb(light, self.color)
                changed += before != tuple(data.color[:3])
            elif self.action == "SET_KELVIN":
                before = tuple(data.color[:3])
                set_light_kelvin(light, self.value)
                changed += before != tuple(data.color[:3])
            elif self.action == "TOGGLE_MUTE":
                _set_muted(light, not _is_muted(light))
                changed += 1
            elif self.action == "SET_RENDER":
                candidate = not bool(self.enabled)
                if light.hide_render != candidate:
                    light.hide_render = candidate
                    changed += 1
            elif self.action == "SET_SCALAR" and self.property_name in SCALAR_EDIT_PROPERTIES:
                if hasattr(data, self.property_name):
                    try:
                        current = getattr(data, self.property_name)
                        candidate = type(current)(self.value)
                        if candidate != current:
                            setattr(data, self.property_name, candidate)
                            changed += 1
                    except (TypeError, ValueError):
                        pass
            elif self.action == "SET_BOOL" and self.property_name in {"use_shadow", "normalize"}:
                if hasattr(data, self.property_name):
                    candidate = bool(self.enabled)
                    if getattr(data, self.property_name) != candidate:
                        setattr(data, self.property_name, candidate)
                        changed += 1
            elif self.action == "SET_BOOL" and self.property_name in {
                "visible_camera",
                "visible_diffuse",
                "visible_glossy",
                "visible_transmission",
                "visible_volume_scatter",
            }:
                if hasattr(light, self.property_name):
                    candidate = bool(self.enabled)
                    if getattr(light, self.property_name) != candidate:
                        setattr(light, self.property_name, candidate)
                        changed += 1
        if not changed:
            self.report({'INFO'}, p_("Light settings unchanged"))
        return {'FINISHED'}


class LLP_OT_light_mixer_copy(LightHelperOperator, bpy.types.Operator):
    bl_idname = "object.light_helper_mixer_copy"
    bl_label = "Copy Light Settings"
    bl_description = "Copy common light parameters without copying datablocks or links"
    bl_options = {'REGISTER'}

    source_name: bpy.props.StringProperty(default="", options={'HIDDEN', 'SKIP_SAVE'})
    full: bpy.props.BoolProperty(default=False, options={'HIDDEN', 'SKIP_SAVE'})

    def execute(self, context):
        global _MIXER_CLIPBOARD
        light = context.scene.objects.get(self.source_name)
        if light is None or light.type != 'LIGHT' or light.data is None:
            self.report({'WARNING'}, p_("No light selected"))
            return {'CANCELLED'}
        # The clipboard always captures the complete safe property payload.
        # Normal paste deliberately applies only common values; Paste Full may
        # then opt into same-type values without needing a second copy action.
        _MIXER_CLIPBOARD = capture_light_settings(light, True)
        self.report({'INFO'}, p_("Light settings copied"))
        return {'FINISHED'}


class LLP_OT_light_mixer_paste(LightHelperOperator, bpy.types.Operator):
    bl_idname = "object.light_helper_mixer_paste"
    bl_label = "Paste Light Settings"
    bl_description = "Paste settings without replacing objects, datablocks, or link collections"
    bl_options = {'REGISTER', 'UNDO'}

    target_names_json: bpy.props.StringProperty(default="[]", options={'HIDDEN', 'SKIP_SAVE'})
    full: bpy.props.BoolProperty(default=False, options={'HIDDEN', 'SKIP_SAVE'})

    def execute(self, context):
        if _MIXER_CLIPBOARD is None:
            self.report({'WARNING'}, p_("No copied light settings"))
            return {'CANCELLED'}
        lights = _light_objects(context, self.target_names_json)
        if not lights:
            self.report({'WARNING'}, p_("No light selected"))
            return {'CANCELLED'}
        for light in lights:
            apply_light_settings(light, _MIXER_CLIPBOARD, self.full)
        return {'FINISHED'}


class LLP_OT_light_mixer_collection_transform(LightHelperOperator, bpy.types.Operator):
    bl_idname = "object.light_helper_mixer_collection_transform"
    bl_label = "Apply Collection EV and Tint"
    bl_description = "Apply a one-shot EV and tint operation to lights in a collection"
    bl_options = {'REGISTER', 'UNDO'}

    collection_name: bpy.props.StringProperty(default="", options={'HIDDEN', 'SKIP_SAVE'})
    ev: bpy.props.FloatProperty(name="EV", default=0.0, options={'SKIP_SAVE'})
    tint: bpy.props.FloatVectorProperty(
        name="Tint",
        size=3,
        subtype='COLOR',
        default=(1.0, 1.0, 1.0),
        min=0.0,
        max=1.0,
        options={'SKIP_SAVE'},
    )

    def invoke(self, context, _event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        collection = bpy.data.collections.get(self.collection_name)
        if collection is None:
            self.report({'WARNING'}, p_("Collection not found"))
            return {'CANCELLED'}
        lights = [obj for obj in collection.all_objects if obj.type == 'LIGHT' and obj.data is not None]
        for light in lights:
            light.data.energy = apply_ev(light.data.energy, self.ev)
            set_light_rgb(light, apply_linear_tint(light.data.color, self.tint))
        if not lights:
            self.report({'WARNING'}, p_("Collection contains no lights"))
            return {'CANCELLED'}
        return {'FINISHED'}


class LLP_OT_toggle_false_color(LightHelperOperator, bpy.types.Operator):
    bl_idname = "scene.light_helper_toggle_false_color"
    bl_label = "Toggle False Color"
    bl_description = "Temporarily switch the active scene to False Color and restore it exactly"
    bl_options = {'REGISTER'}

    enabled: bpy.props.BoolProperty(default=True, options={'HIDDEN', 'SKIP_SAVE'})

    def execute(self, context):
        success = enable_false_color(context.scene) if self.enabled else restore_false_color(context.scene)
        if not success and not self.enabled:
            self.report({'INFO'}, p_("False Color was not enabled by LightHelper"))
        return {'FINISHED'}


LIGHT_MIXER_CLASSES = (
    LLP_OT_light_mixer_batch,
    LLP_OT_light_mixer_copy,
    LLP_OT_light_mixer_paste,
    LLP_OT_light_mixer_collection_transform,
    LLP_OT_toggle_false_color,
)


__all__ = [
    "KELVIN_PRESETS",
    "LIGHT_MIXER_CLASSES",
    "LLP_OT_light_mixer_batch",
    "LLP_OT_light_mixer_collection_transform",
    "LLP_OT_light_mixer_copy",
    "LLP_OT_light_mixer_paste",
    "LLP_OT_toggle_false_color",
    "apply_light_settings",
    "capture_light_settings",
    "cleanup_light_mixer_runtime",
    "enable_false_color",
    "false_color_load_pre",
    "get_kelvin_state",
    "get_mixer_columns",
    "is_false_color_enabled",
    "mixer_row_snapshot",
    "restore_all_false_color",
    "restore_false_color",
    "register_light_mixer_handlers",
    "set_light_kelvin",
    "set_light_rgb",
    "unregister_light_mixer_handlers",
]
