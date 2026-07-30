"""Blender runtime adapter for versioned LightHelper Lighting Profiles."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping
from uuid import uuid4

import bpy

from ..core.profiles import build_id_reference, resolve_id_reference

KELVIN_ENABLED_KEY = "light_helper_kelvin_mode"
KELVIN_VALUE_KEY = "light_helper_kelvin_temperature"

_OBJECT_FIELDS = (
    "hide_viewport",
    "hide_render",
    "visible_camera",
    "visible_diffuse",
    "visible_glossy",
    "visible_transmission",
    "visible_volume_scatter",
    "visible_shadow",
)
_LIGHT_FIELDS = (
    "energy",
    "color",
    "diffuse_factor",
    "specular_factor",
    "transmission_factor",
    "volume_factor",
    "use_shadow",
    "normalize",
    "use_custom_distance",
    "cutoff_distance",
    "shape",
    "size",
    "size_y",
    "spot_size",
    "spot_blend",
    "show_cone",
    "angle",
)
_WORLD_FIELDS = (
    "world_dome_color",
    "world_dome_strength",
    "world_dome_tint",
    "world_dome_tint_factor",
    "world_dome_gamma",
    "world_dome_saturation",
    "world_dome_rotation",
    "world_dome_mapping_location",
    "world_dome_mapping_scale",
    "world_dome_radius",
    "world_dome_max_bounces",
    "world_dome_max_diffuse_bounces",
    "world_dome_max_glossy_bounces",
    "world_dome_max_transmission_bounces",
    "world_dome_visible_camera",
    "world_dome_visible_diffuse",
    "world_dome_visible_glossy",
    "world_dome_visible_transmission",
    "world_dome_visible_volume_scatter",
    "world_dome_show_viewport",
    "world_dome_lock_selection",
)


def _kelvin_metadata(light: Any) -> tuple[bool, float]:
    try:
        from ..ops.light_mixer import get_kelvin_state
        return get_kelvin_state(light)
    except (ImportError, AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
        pass
    props = getattr(light, "light_helper_property", None)
    if props is not None and hasattr(props, "kelvin_mode"):
        return bool(props.kelvin_mode), float(props.kelvin_temperature)
    return (
        bool(light.get(KELVIN_ENABLED_KEY, False)),
        float(light.get(KELVIN_VALUE_KEY, 5600.0)),
    )


def _apply_kelvin_metadata(light: Any, enabled: bool, temperature: float) -> None:
    temperature = min(40000.0, max(1000.0, float(temperature)))
    if enabled:
        from ..ops.light_mixer import set_light_kelvin
        set_light_kelvin(light, temperature)
        return
    props = getattr(light, "light_helper_property", None)
    if props is not None and hasattr(props, "kelvin_mode"):
        props.kelvin_mode = False
        props.kelvin_temperature = temperature
    else:
        light[KELVIN_ENABLED_KEY] = False
        light[KELVIN_VALUE_KEY] = temperature


def _plain_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    try:
        return [_plain_value(item) for item in value]
    except TypeError:
        return str(value)


def _id_key(id_block: Any) -> tuple[str, int]:
    try:
        return type(id_block).__name__, int(id_block.as_pointer())
    except (AttributeError, ReferenceError, TypeError):
        return type(id_block).__name__, id(id_block)


class ReferenceRegistry:
    """Caches references so repeated references never look like UUID collisions."""

    def __init__(self) -> None:
        self.used_uuids: set[str] = set()
        self._cache: dict[tuple[str, int], dict[str, Any]] = {}

    def reference(self, id_block: Any) -> dict[str, Any]:
        key = _id_key(id_block)
        reference = self._cache.get(key)
        if reference is None:
            reference = build_id_reference(id_block, used_uuids=self.used_uuids)
            self._cache[key] = reference
        return dict(reference)


@dataclass
class ProfileHooks:
    capture_links: Callable[[Any, ReferenceRegistry], Mapping[str, Any]] | None = None
    apply_links: Callable[[Any, Mapping[str, Any], Any], list[str] | None] | None = None
    capture_world: Callable[[Any, ReferenceRegistry], Mapping[str, Any]] | None = None
    apply_world: Callable[[Any, Mapping[str, Any], bool], list[str] | None] | None = None
    capture_studio: Callable[[Any, ReferenceRegistry], Mapping[str, Any]] | None = None
    apply_studio: Callable[[Any, Mapping[str, Any], bool], list[str] | None] | None = None
    capture_light_groups: Callable[[Any], Mapping[str, Any]] | None = None
    apply_light_groups: Callable[[Any, Mapping[str, Any], Any], list[str] | None] | None = None


@dataclass
class ApplyReport:
    matched: int = 0
    created: int = 0
    missing: list[str] = field(default_factory=list)
    skipped_read_only: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def changed(self) -> int:
        return self.matched + self.created


def _capture_attributes(owner: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    result = {}
    for field_name in fields:
        if hasattr(owner, field_name):
            try:
                result[field_name] = _plain_value(getattr(owner, field_name))
            except (AttributeError, ReferenceError, RuntimeError, TypeError):
                continue
    return result


def _capture_link_channel(light: Any, coll_type: Any, registry: ReferenceRegistry) -> list[dict]:
    from . import (
        get_item_channel_state,
        get_linking_coll,
        is_internal_world_dome_link,
        is_safe_helper_object,
    )

    collection = get_linking_coll(light, coll_type)
    if collection is None:
        return []
    result = []
    for item in tuple(collection.objects) + tuple(collection.children):
        if (is_safe_helper_object(item)
                or is_internal_world_dome_link(light, item, coll_type)):
            continue
        state = get_item_channel_state(light, item, coll_type)
        state_value = getattr(state, "value", str(state))
        if state_value == "OFF":
            continue
        result.append({"ref": registry.reference(item), "state": state_value})
    return result


def capture_link_payload(light: Any, registry: ReferenceRegistry) -> dict[str, Any]:
    from . import CollectionType, get_linking_edit_mode, get_linking_mode

    return {
        "edit_mode": get_linking_edit_mode(light),
        "simple_mode": get_linking_mode(light),
        "receiver": _capture_link_channel(light, CollectionType.RECEIVER, registry),
        "blocker": _capture_link_channel(light, CollectionType.BLOCKER, registry),
    }


def _all_reference_candidates(scene: Any) -> list[Any]:
    return list(scene.objects) + list(bpy.data.collections)


def apply_link_payload(light: Any, payload: Mapping[str, Any], context: Any) -> list[str]:
    """Replace only user-authored direct entries; managed dome entries survive."""
    from . import (
        ChannelState,
        CollectionType,
        get_linking_coll,
        is_internal_world_dome_link,
        set_item_channel_state,
        sync_safe_helpers_for_light,
    )

    warnings: list[str] = []
    candidates = _all_reference_candidates(context.scene)
    for field_name, coll_type in (
        ("receiver", CollectionType.RECEIVER),
        ("blocker", CollectionType.BLOCKER),
    ):
        desired_items = payload.get(field_name, [])
        if not isinstance(desired_items, list):
            warnings.append(f"Invalid {field_name} linking payload")
            continue
        collection = get_linking_coll(light, coll_type)
        if collection is not None:
            existing = tuple(collection.objects) + tuple(collection.children)
            for item in existing:
                if is_internal_world_dome_link(light, item, coll_type):
                    continue
                set_item_channel_state(
                    light,
                    item,
                    coll_type,
                    ChannelState.OFF,
                    context,
                    notify=False,
                    sync_helpers=False,
                )
        for index, entry in enumerate(desired_items):
            if not isinstance(entry, Mapping) or not isinstance(entry.get("ref"), Mapping):
                warnings.append(f"Invalid {field_name}[{index}] entry")
                continue
            item = resolve_id_reference(entry["ref"], candidates)
            if item is None:
                warnings.append(
                    f"Missing linked item: {entry['ref'].get('name_full', '<unknown>')}"
                )
                continue
            state_name = entry.get("state")
            try:
                state = ChannelState(state_name)
            except ValueError:
                warnings.append(f"Invalid linking state: {state_name!r}")
                continue
            if not set_item_channel_state(
                light,
                item,
                coll_type,
                state,
                context,
                notify=False,
                sync_helpers=False,
            ):
                # An already-correct direct state is not a failure.
                from . import get_item_channel_state

                if get_item_channel_state(light, item, coll_type) != state:
                    warnings.append(f"Could not apply link for {item.name_full}")
    try:
        sync_safe_helpers_for_light(light)
    except (AttributeError, ReferenceError, RuntimeError, TypeError):
        warnings.append(f"Could not synchronize linking helpers for {light.name_full}")
    try:
        from .overlay import notify_linking_changed

        notify_linking_changed(context)
    except (AttributeError, ReferenceError, RuntimeError, TypeError):
        pass
    props = getattr(light, "light_helper_property", None)
    if props is not None:
        edit_mode = payload.get("edit_mode")
        if edit_mode in {"SIMPLE", "ADVANCED"} and hasattr(props, "linking_edit_mode"):
            props.linking_edit_mode = edit_mode
        simple_mode = payload.get("simple_mode")
        if simple_mode in {"INCLUDE", "EXCLUDE"} and hasattr(props, "linking_mode"):
            # A profile is a native-state snapshot. Restore the Simple default
            # metadata without flattening a mixed state authored outside
            # LightHelper; the UI will truthfully show Mixed and offer Advanced.
            from ..property import set_linking_mode_silent
            set_linking_mode_silent(props, simple_mode)
    return warnings


def capture_world_payload(scene: Any, _registry: ReferenceRegistry) -> dict[str, Any]:
    from .world_environment import get_world_dome

    props = scene.light_helper_property
    return {
        "converted": get_world_dome(scene) is not None,
        "world_lightgroup": getattr(scene.world, "lightgroup", "") if scene.world else "",
        "settings": _capture_attributes(props, _WORLD_FIELDS),
    }


def apply_world_payload(
    scene: Any, payload: Mapping[str, Any], create_missing: bool = False
) -> list[str]:
    from .world_environment import (
        convert_world_environment,
        get_world_dome,
        restore_world_environment,
        update_world_dome_from_properties,
    )

    warnings: list[str] = []
    converted = bool(payload.get("converted", False))
    try:
        dome = get_world_dome(scene)
        if converted and dome is None:
            if not create_missing:
                warnings.append("Missing managed World dome (Create Missing is disabled)")
            elif scene.render.engine != "CYCLES":
                warnings.append("World dome requires Cycles")
            else:
                created, _status = convert_world_environment(scene)
                if created is None:
                    warnings.append("World environment could not be converted")
        elif not converted and dome is not None:
            restored, _status = restore_world_environment(scene)
            if not restored:
                warnings.append("Managed World environment could not be restored")
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError) as exc:
        warnings.append(f"World conversion state failed: {exc}")
    settings = payload.get("settings", {})
    world_lightgroup = payload.get("world_lightgroup")
    if (
        isinstance(world_lightgroup, str)
        and scene.world is not None
        and hasattr(scene.world, "lightgroup")
        and getattr(scene.world, "is_editable", True)
    ):
        try:
            scene.world.lightgroup = world_lightgroup
        except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
            warnings.append("World Light Group could not be applied")
    if isinstance(settings, Mapping):
        props = scene.light_helper_property
        for field_name, value in settings.items():
            if field_name in _WORLD_FIELDS and hasattr(props, field_name):
                try:
                    setattr(props, field_name, value)
                except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
                    warnings.append(f"World setting could not be applied: {field_name}")
        try:
            update_world_dome_from_properties(scene)
        except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
            pass
    return warnings


def _studio_material(obj: Any):
    if obj.data is None or not getattr(obj.data, "materials", None):
        return None
    return obj.data.materials[0]


def capture_studio_payload(scene: Any, registry: ReferenceRegistry) -> dict[str, Any]:
    from .studio import is_studio_object, studio_kind

    items = []
    for obj in sorted(
        (candidate for candidate in scene.objects if is_studio_object(candidate)),
        key=lambda candidate: candidate.name_full,
    ):
        kind = studio_kind(obj)
        material = _studio_material(obj)
        diffuse = tuple(getattr(material, "diffuse_color", (1.0, 1.0, 1.0)))[:3]
        parameters: dict[str, Any] = {
            "shape": obj.get("light_helper_studio_shape", "RECTANGLE"),
            "width": float(obj.get("light_helper_studio_width", obj.scale.x)),
            "height": float(obj.get("light_helper_studio_height", obj.scale.y)),
            "thickness": float(obj.get("light_helper_studio_thickness", 0.0)),
            "color": [float(value) for value in diffuse],
            "visible_camera": bool(getattr(obj, "visible_camera", True)),
        }
        if kind == "SCRIM":
            parameters.update(
                feather=float(obj.get("light_helper_scrim_feather", 0.2)),
                gradient_direction=str(obj.get("light_helper_scrim_gradient", "NONE")),
                gradient_amount=float(
                    obj.get("light_helper_scrim_gradient_amount", 0.5)
                ),
                color=_plain_value(obj.get("light_helper_scrim_color", diffuse)),
                strength=float(obj.get("light_helper_scrim_strength", 10.0)),
                exposure=float(obj.get("light_helper_scrim_exposure", 0.0)),
            )
        elif kind == "REFLECTOR":
            parameters.update(
                color=_plain_value(obj.get("light_helper_reflector_color", diffuse)),
                reflectance=float(
                    obj.get("light_helper_reflector_reflectance", 0.8)
                ),
                roughness=float(obj.get("light_helper_reflector_roughness", 0.5)),
            )
        studio_item = {
                "ref": registry.reference(obj),
                "kind": kind,
                "object": {
                    "matrix_world": [
                        [float(value) for value in row] for row in obj.matrix_world
                    ],
                    "hide_viewport": bool(obj.hide_viewport),
                    "hide_render": bool(obj.hide_render),
                },
                "parameters": parameters,
            }
        if hasattr(obj, "light_linking"):
            studio_item["linking"] = capture_link_payload(obj, registry)
        items.append(studio_item)
    return {"items": items}


def _create_studio_from_payload(scene: Any, item: Mapping[str, Any]):
    from .studio import create_flag, create_reflector, create_scrim

    parameters = dict(item.get("parameters", {}))
    kind = item.get("kind")
    if kind == "SCRIM":
        allowed = {
            "shape",
            "width",
            "height",
            "feather",
            "gradient_direction",
            "gradient_amount",
            "color",
            "strength",
            "exposure",
            "visible_camera",
        }
        return create_scrim(scene, **{key: value for key, value in parameters.items() if key in allowed})
    if kind == "FLAG":
        allowed = {
            "shape",
            "width",
            "height",
            "thickness",
            "color",
            "visible_camera",
        }
        return create_flag(scene, **{key: value for key, value in parameters.items() if key in allowed})
    if kind == "REFLECTOR":
        allowed = {
            "shape",
            "width",
            "height",
            "color",
            "reflectance",
            "roughness",
        }
        return create_reflector(
            scene, **{key: value for key, value in parameters.items() if key in allowed}
        )
    raise ValueError(f"Unsupported studio item kind: {kind!r}")


def _update_studio_material(obj: Any, kind: str, parameters: Mapping[str, Any]) -> None:
    material = _studio_material(obj)
    if material is None or not material.use_nodes:
        return
    color = tuple(float(value) for value in parameters.get("color", (1.0, 1.0, 1.0)))[:3]
    if kind == "SCRIM":
        material.diffuse_color = (*color, 1.0)
        emission = material.node_tree.nodes.get("Scrim Emission")
        if emission is not None:
            emission.inputs["Color"].default_value = (*color, 1.0)
        strength = material.node_tree.nodes.get("Scrim Strength")
        if strength is not None:
            base = max(0.0, float(parameters.get("strength", 10.0)))
            exposure = float(parameters.get("exposure", 0.0))
            strength.inputs[1].default_value = base * (2.0**exposure)
        feather = material.node_tree.nodes.get("Scrim Feather")
        if feather is not None:
            value = max(0.0, min(1.0, float(parameters.get("feather", 0.2))))
            feather.inputs["From Min"].default_value = 1.0 - value
        gradient_amount = material.node_tree.nodes.get("Gradient Amount")
        if gradient_amount is not None:
            value = max(
                0.0, min(1.0, float(parameters.get("gradient_amount", 0.5)))
            )
            gradient_amount.inputs[1].default_value = -value
    else:
        diffuse = material.node_tree.nodes.get("Studio Diffuse")
        reflectance = (
            max(0.0, min(1.0, float(parameters.get("reflectance", 1.0))))
            if kind == "REFLECTOR"
            else 1.0
        )
        shaded = tuple(max(0.0, min(1.0, value * reflectance)) for value in color)
        material.diffuse_color = (*shaded, 1.0)
        if diffuse is not None:
            diffuse.inputs["Color"].default_value = (*shaded, 1.0)
            if kind == "REFLECTOR":
                diffuse.inputs["Roughness"].default_value = max(
                    0.0, min(1.0, float(parameters.get("roughness", 0.5)))
                )


def apply_studio_payload(
    scene: Any, payload: Mapping[str, Any], create_missing: bool
) -> list[str]:
    from .studio import is_studio_object, studio_kind

    warnings: list[str] = []
    candidates = [obj for obj in scene.objects if is_studio_object(obj)]
    items = payload.get("items", [])
    if not isinstance(items, list):
        return ["Invalid studio profile payload"]
    for item in items:
        if not isinstance(item, Mapping) or not isinstance(item.get("ref"), Mapping):
            warnings.append("Invalid studio item")
            continue
        obj = resolve_id_reference(item["ref"], candidates)
        if obj is None and create_missing and item["ref"].get("kind") != "LIBRARY":
            try:
                obj = _create_studio_from_payload(scene, item)
                profile_uuid = item["ref"].get("uuid")
                if isinstance(profile_uuid, str):
                    obj["light_helper_uuid"] = profile_uuid
                candidates.append(obj)
            except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
                warnings.append(f"Studio item could not be created: {exc}")
        if obj is None:
            warnings.append(
                f"Missing studio item: {item['ref'].get('name_full', '<unknown>')}"
            )
            continue
        if not getattr(obj, "is_editable", True):
            warnings.append(f"Read-only studio item skipped: {obj.name_full}")
            continue
        kind = studio_kind(obj)
        if kind != item.get("kind"):
            warnings.append(f"Studio kind mismatch: {obj.name_full}")
            continue
        object_payload = item.get("object", {})
        parameters = item.get("parameters", {})
        try:
            old_shape = obj.get("light_helper_studio_shape", "RECTANGLE")
            old_gradient = obj.get("light_helper_scrim_gradient", "NONE")
            old_thickness = float(obj.get("light_helper_studio_thickness", 0.0))
            shape_changed = parameters.get("shape", old_shape) != old_shape
            gradient_changed = (
                kind == "SCRIM"
                and parameters.get("gradient_direction", old_gradient) != old_gradient
            )
            thickness_changed = (
                kind == "FLAG"
                and abs(float(parameters.get("thickness", old_thickness)) - old_thickness)
                > 1e-8
            )
            if "matrix_world" in object_payload:
                obj.matrix_world = object_payload["matrix_world"]
            obj.hide_viewport = bool(object_payload.get("hide_viewport", obj.hide_viewport))
            obj.hide_render = bool(object_payload.get("hide_render", obj.hide_render))
            if hasattr(obj, "visible_camera") and "visible_camera" in parameters:
                obj.visible_camera = bool(parameters["visible_camera"])
            width = max(0.001, float(parameters.get("width", obj.scale.x)))
            height = max(0.001, float(parameters.get("height", obj.scale.y)))
            obj.scale.x = width
            obj.scale.y = height
            for key, value in parameters.items():
                if (key == "shape" and shape_changed) or (
                    key == "gradient_direction" and gradient_changed
                ) or (key == "thickness" and thickness_changed):
                    continue
                custom_key = {
                    "shape": "light_helper_studio_shape",
                    "width": "light_helper_studio_width",
                    "height": "light_helper_studio_height",
                    "thickness": "light_helper_studio_thickness",
                    "feather": "light_helper_scrim_feather",
                    "gradient_direction": "light_helper_scrim_gradient",
                    "gradient_amount": "light_helper_scrim_gradient_amount",
                    "strength": "light_helper_scrim_strength",
                    "exposure": "light_helper_scrim_exposure",
                    "reflectance": "light_helper_reflector_reflectance",
                    "roughness": "light_helper_reflector_roughness",
                }.get(key)
                if custom_key is not None:
                    obj[custom_key] = value
            if kind == "SCRIM":
                obj["light_helper_scrim_color"] = parameters.get("color", (1, 1, 1))
            elif kind == "REFLECTOR":
                obj["light_helper_reflector_color"] = parameters.get(
                    "color", (1, 1, 1)
                )
            _update_studio_material(obj, kind, parameters)
            linking = item.get("linking")
            if isinstance(linking, Mapping):
                warnings.extend(apply_link_payload(obj, linking, bpy.context) or [])
            if shape_changed:
                warnings.append(f"Studio shape requires recreation: {obj.name_full}")
            if gradient_changed:
                warnings.append(f"Scrim gradient direction requires recreation: {obj.name_full}")
            if thickness_changed:
                warnings.append(f"Flag thickness requires recreation: {obj.name_full}")
        except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError) as exc:
            warnings.append(f"Studio item could not be applied: {obj.name_full}: {exc}")
    return warnings


def capture_light_group_payload(scene: Any) -> dict[str, Any]:
    settings = getattr(scene, "light_helper_light_group_settings", ())
    return {
        "settings": [
            {
                "name": item.name,
                "ev": float(item.ev),
                "tint": [float(value) for value in item.tint],
            }
            for item in settings
            if item.name
        ]
    }


def apply_light_group_payload(
    scene: Any, payload: Mapping[str, Any], context: Any
) -> list[str]:
    from .light_groups import ensure_light_group, ensure_used_light_groups

    warnings: list[str] = []
    collection = getattr(scene, "light_helper_light_group_settings", None)
    settings = payload.get("settings", [])
    if collection is None:
        return ["Light Group settings are not registered"]
    if not isinstance(settings, list):
        return ["Invalid Light Group profile payload"]
    existing = {item.name: item for item in collection}
    for entry in settings:
        if not isinstance(entry, Mapping) or not isinstance(entry.get("name"), str):
            warnings.append("Invalid Light Group setting")
            continue
        name = entry["name"].strip()
        if not name:
            warnings.append("Empty Light Group setting skipped")
            continue
        ensure_light_group(context.view_layer, name)
        item = existing.get(name)
        if item is None:
            item = collection.add()
            item.name = name
            existing[name] = item
        try:
            item.ev = float(entry.get("ev", 0.0))
            tint = entry.get("tint", (1.0, 1.0, 1.0))
            if not isinstance(tint, (list, tuple)) or len(tint) != 3:
                raise ValueError("Tint must have three components")
            item.tint = tuple(float(value) for value in tint)
        except (TypeError, ValueError):
            warnings.append(f"Invalid Light Group adjustment: {name}")
    ensure_used_light_groups(scene, context.view_layer)
    return warnings


def default_profile_hooks() -> ProfileHooks:
    return ProfileHooks(
        capture_links=capture_link_payload,
        apply_links=apply_link_payload,
        capture_world=capture_world_payload,
        apply_world=apply_world_payload,
        capture_studio=capture_studio_payload,
        apply_studio=apply_studio_payload,
        capture_light_groups=capture_light_group_payload,
        apply_light_groups=apply_light_group_payload,
    )


def capture_profile(
    scene: Any, name: str, *, hooks: ProfileHooks | None = None
) -> dict[str, Any]:
    hooks = hooks or default_profile_hooks()
    registry = ReferenceRegistry()
    lights = []
    for light in sorted(
        (obj for obj in scene.objects if obj.type == "LIGHT"), key=lambda item: item.name_full
    ):
        data = light.data
        kelvin_enabled, kelvin_value = _kelvin_metadata(light)
        item: dict[str, Any] = {
            "ref": registry.reference(light),
            "light_type": data.type,
            "object": {
                "matrix_world": [[float(value) for value in row] for row in light.matrix_world],
                **_capture_attributes(light, _OBJECT_FIELDS),
                "lightgroup": getattr(light, "lightgroup", ""),
            },
            "data": _capture_attributes(data, _LIGHT_FIELDS),
            "kelvin": {
                "enabled": kelvin_enabled,
                "value": kelvin_value,
            },
            "mixer": {
                "muted": bool(light.get("light_helper_mute", False)),
            },
        }
        if hooks.capture_links is not None:
            item["linking"] = dict(hooks.capture_links(light, registry))
        try:
            from .studio import _track_constraint_owner
            constraint = next(
                (
                    constraint for constraint in light.constraints
                    if _track_constraint_owner(constraint) is not None
                    and constraint.target is not None
                ),
                None,
            )
            if constraint is not None:
                item["track_target"] = {
                    "ref": registry.reference(constraint.target),
                }
        except (ImportError, AttributeError, ReferenceError, RuntimeError, TypeError):
            pass
        lights.append(item)
    profile: dict[str, Any] = {
        "id": str(uuid4()),
        "name": name.strip() or "Lighting Look",
        "lights": lights,
    }
    try:
        from . import is_emissive_light_source
        from .studio import is_studio_object

        emissive_sources = []
        for source in sorted(
            (
                obj for obj in scene.objects
                if obj.type != 'LIGHT'
                and not is_studio_object(obj)
                and is_emissive_light_source(obj, scene)
            ),
            key=lambda item: item.name_full,
        ):
            emissive_sources.append({
                "ref": registry.reference(source),
                "object": _capture_attributes(source, _OBJECT_FIELDS),
                "linking": capture_link_payload(source, registry),
            })
        profile["emissive_sources"] = emissive_sources
    except (ImportError, AttributeError, ReferenceError, RuntimeError, TypeError):
        profile["emissive_sources"] = []
    if hooks.capture_world is not None:
        profile["world"] = dict(hooks.capture_world(scene, registry))
    if hooks.capture_studio is not None:
        profile["studio"] = dict(hooks.capture_studio(scene, registry))
    if hooks.capture_light_groups is not None:
        profile["light_groups"] = dict(hooks.capture_light_groups(scene))
    return profile


def _is_editable_light(light: Any) -> bool:
    return bool(
        getattr(light, "is_editable", True)
        and getattr(light, "library", None) is None
        and light.data is not None
        and getattr(light.data, "is_editable", True)
        and getattr(light.data, "library", None) is None
    )


def _apply_attributes(owner: Any, payload: Mapping[str, Any], allowed: tuple[str, ...]) -> list[str]:
    warnings = []
    for field_name, value in payload.items():
        if field_name not in allowed or not hasattr(owner, field_name):
            continue
        try:
            setattr(owner, field_name, value)
        except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
            warnings.append(field_name)
    return warnings


def _create_native_light(scene: Any, item: Mapping[str, Any]) -> Any:
    reference = item["ref"]
    name = str(reference.get("name_full") or "Light")
    data = bpy.data.lights.new(name=name, type=item["light_type"])
    light = bpy.data.objects.new(name=name, object_data=data)
    try:
        scene.collection.objects.link(light)
    except Exception:
        bpy.data.objects.remove(light)
        if data.users == 0:
            bpy.data.lights.remove(data)
        raise
    profile_uuid = reference.get("uuid")
    if isinstance(profile_uuid, str):
        light["light_helper_uuid"] = profile_uuid
    return light


def apply_profile(
    scene: Any,
    profile: Mapping[str, Any],
    *,
    context: Any,
    create_missing: bool = False,
    hooks: ProfileHooks | None = None,
) -> ApplyReport:
    """Apply matching lights and optional managed data without deleting extras."""
    hooks = hooks or default_profile_hooks()
    report = ApplyReport()
    candidates = [obj for obj in scene.objects if obj.type == "LIGHT"]
    for item in profile.get("lights", []):
        reference = item["ref"]
        light = resolve_id_reference(reference, candidates)
        was_created = False
        if light is None and create_missing and reference.get("kind") != "LIBRARY":
            try:
                light = _create_native_light(scene, item)
                candidates.append(light)
                was_created = True
            except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
                report.warnings.append(
                    f"Could not create {reference.get('name_full', '<unknown>')}: {exc}"
                )
        if light is None:
            report.missing.append(str(reference.get("name_full", "<unknown>")))
            continue
        if not _is_editable_light(light):
            report.skipped_read_only.append(light.name_full)
            continue
        object_payload = item.get("object", {})
        try:
            matrix = object_payload.get("matrix_world")
            if matrix is not None:
                light.matrix_world = matrix
        except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
            report.warnings.append(f"Transform could not be applied: {light.name_full}")
        failed_object = _apply_attributes(light, object_payload, _OBJECT_FIELDS)
        failed_data = _apply_attributes(light.data, item.get("data", {}), _LIGHT_FIELDS)
        if failed_object or failed_data:
            report.warnings.append(
                f"Some properties could not be applied to {light.name_full}: "
                + ", ".join(failed_object + failed_data)
            )
        lightgroup = object_payload.get("lightgroup")
        if isinstance(lightgroup, str) and hasattr(light, "lightgroup"):
            try:
                light.lightgroup = lightgroup
            except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
                report.warnings.append(f"Light Group could not be set: {light.name_full}")
        kelvin = item.get("kelvin")
        if isinstance(kelvin, Mapping):
            _apply_kelvin_metadata(
                light,
                bool(kelvin.get("enabled", False)),
                float(kelvin.get("value", 5600.0)),
            )
        mixer = item.get("mixer")
        if isinstance(mixer, Mapping) and "muted" in mixer:
            from ..ops.light_mixer import _set_muted
            muted = bool(mixer.get("muted"))
            _set_muted(light, muted)
            if not muted:
                _apply_attributes(light, object_payload, _OBJECT_FIELDS)
        linking = item.get("linking")
        if isinstance(linking, Mapping) and hooks.apply_links is not None:
            report.warnings.extend(hooks.apply_links(light, linking, context) or [])
        track_target = item.get("track_target")
        if isinstance(track_target, Mapping) and isinstance(track_target.get("ref"), Mapping):
            target = resolve_id_reference(
                track_target["ref"], list(scene.objects),
            )
            if target is None:
                report.warnings.append(f"Missing managed track target for {light.name_full}")
            else:
                try:
                    from .studio import ensure_track_to
                    ensure_track_to(scene, light, target)
                except (ImportError, AttributeError, ReferenceError, RuntimeError, TypeError):
                    report.warnings.append(f"Track target could not be applied: {light.name_full}")
        if was_created:
            report.created += 1
        else:
            report.matched += 1
    emissive_candidates = [obj for obj in scene.objects if obj.type != 'LIGHT']
    for item in profile.get("emissive_sources", []):
        if not isinstance(item, Mapping) or not isinstance(item.get("ref"), Mapping):
            report.warnings.append("Invalid emissive source profile item")
            continue
        source = resolve_id_reference(item["ref"], emissive_candidates)
        if source is None:
            report.missing.append(str(item["ref"].get("name_full", "<unknown>")))
            continue
        if not getattr(source, "is_editable", True):
            report.skipped_read_only.append(source.name_full)
            continue
        failed = _apply_attributes(source, item.get("object", {}), _OBJECT_FIELDS)
        if failed:
            report.warnings.append(
                f"Some emissive visibility properties could not be applied to {source.name_full}: "
                + ", ".join(failed)
            )
        linking = item.get("linking")
        if isinstance(linking, Mapping) and hooks.apply_links is not None:
            report.warnings.extend(hooks.apply_links(source, linking, context) or [])
    world = profile.get("world")
    if isinstance(world, Mapping) and hooks.apply_world is not None:
        report.warnings.extend(hooks.apply_world(scene, world, create_missing) or [])
    light_groups = profile.get("light_groups")
    if isinstance(light_groups, Mapping) and hooks.apply_light_groups is not None:
        report.warnings.extend(
            hooks.apply_light_groups(scene, light_groups, context) or []
        )
    studio = profile.get("studio")
    if isinstance(studio, Mapping) and hooks.apply_studio is not None:
        report.warnings.extend(hooks.apply_studio(scene, studio, create_missing) or [])
    return report


__all__ = [
    "ApplyReport",
    "ProfileHooks",
    "ReferenceRegistry",
    "apply_link_payload",
    "apply_profile",
    "apply_world_payload",
    "capture_link_payload",
    "capture_light_group_payload",
    "capture_profile",
    "capture_studio_payload",
    "capture_world_payload",
    "default_profile_hooks",
    "apply_light_group_payload",
    "apply_studio_payload",
]
