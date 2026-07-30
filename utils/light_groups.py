"""Cycles Light Group and 4.2/5.x compositor compatibility adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping
from uuid import uuid4

import bpy

from ..core.light_group_plan import (
    CompositeConnectionDecision,
    GroupAdjustment,
    build_light_group_plan,
    decide_composite_connection,
    group_key,
)
from ..core.profiles import UUID_KEY, ensure_stable_uuid

MANAGED_OWNER_KEY = "light_helper_aov_owner"
MANAGED_ROLE_KEY = "light_helper_aov_role"
MANAGED_BUILD_KEY = "light_helper_aov_build"
MANAGED_GROUP_KEY = "light_helper_aov_group"
MANAGED_EV_KEY = "light_helper_aov_ev"
MANAGED_TINT_KEY = "light_helper_aov_tint"
MANAGED_VERSION_KEY = "light_helper_aov_version"
MANAGED_VERSION = 1


@dataclass
class CompositorBuildResult:
    group_count: int
    connection: CompositeConnectionDecision
    output_node: str
    target_node: str
    warnings: list[str] = field(default_factory=list)


def _scene_owner_uuid(scene: Any) -> str:
    used = {
        value
        for other in bpy.data.scenes
        if other != scene
        for value in (other.get(UUID_KEY),)
        if isinstance(value, str)
    }
    return ensure_stable_uuid(scene, used_uuids=used)


def light_group_names(view_layer: Any) -> list[str]:
    return [item.name for item in view_layer.lightgroups if item.name]


def used_light_group_names(scene: Any) -> list[str]:
    names = {
        str(getattr(obj, "lightgroup", "")).strip()
        for obj in scene.objects
        if str(getattr(obj, "lightgroup", "")).strip()
    }
    world_name = str(getattr(scene.world, "lightgroup", "")).strip() if scene.world else ""
    if world_name:
        names.add(world_name)
    return sorted(names, key=str.casefold)


def ensure_light_group(view_layer: Any, name: str):
    if not name:
        raise ValueError("Light Group name cannot be empty")
    existing = view_layer.lightgroups.get(name)
    if existing is not None:
        return existing
    item = view_layer.lightgroups.add()
    item.name = name
    return item


def ensure_used_light_groups(scene: Any, view_layer: Any) -> list[str]:
    names = used_light_group_names(scene)
    for name in names:
        ensure_light_group(view_layer, name)
    return names


def remove_light_group(scene: Any, view_layer: Any, name: str, *, context: Any = None) -> bool:
    item = view_layer.lightgroups.get(name)
    if item is None:
        return False
    remove = getattr(view_layer.lightgroups, "remove", None)
    if callable(remove):
        remove(item)
        return True
    index = view_layer.lightgroups.find(name)
    if index < 0:
        return False
    view_layer.active_lightgroup_index = index
    active_context = context or bpy.context
    try:
        with active_context.temp_override(scene=scene, view_layer=view_layer):
            return bpy.ops.scene.view_layer_remove_lightgroup() == {"FINISHED"}
    except (AttributeError, RuntimeError, TypeError):
        return False


def _compositor_tree(scene: Any, *, create: bool) -> Any | None:
    if hasattr(scene, "node_tree"):
        if create and not scene.use_nodes:
            scene.use_nodes = True
        return scene.node_tree if scene.use_nodes else None
    tree = getattr(scene, "compositing_node_group", None)
    if tree is None and create:
        tree = bpy.data.node_groups.new(f"{scene.name} LightHelper Compositor", "CompositorNodeTree")
        scene.compositing_node_group = tree
        tree[MANAGED_ROLE_KEY] = "ROOT_TREE"
    return tree


def _mark_node(node: Any, owner_uuid: str, role: str, build_id: str) -> Any:
    node[MANAGED_OWNER_KEY] = owner_uuid
    node[MANAGED_ROLE_KEY] = role
    node[MANAGED_BUILD_KEY] = build_id
    node[MANAGED_VERSION_KEY] = MANAGED_VERSION
    return node


def _managed_nodes(tree: Any, owner_uuid: str) -> list[Any]:
    return [node for node in tree.nodes if node.get(MANAGED_OWNER_KEY) == owner_uuid]


def _find_render_layers(tree: Any, view_layer: Any, owner_uuid: str) -> Any | None:
    candidates = [
        node
        for node in tree.nodes
        if node.bl_idname == "CompositorNodeRLayers"
        and node.get(MANAGED_OWNER_KEY) != owner_uuid
    ]
    for node in candidates:
        if getattr(node, "layer", "") == view_layer.name:
            return node
    return None


def _ensure_render_layers(
    tree: Any, view_layer: Any, owner_uuid: str, build_id: str, created: list[Any]
) -> Any:
    node = _find_render_layers(tree, view_layer, owner_uuid)
    if node is not None:
        return node
    node = _mark_node(
        tree.nodes.new("CompositorNodeRLayers"), owner_uuid, "RENDER_LAYERS", build_id
    )
    node.name = "LightHelper Render Layers"
    node.label = f"LightHelper · {view_layer.name}"
    node.layer = view_layer.name
    created.append(node)
    return node


def _active_node(nodes: Iterable[Any]) -> Any | None:
    candidates = list(nodes)
    return next((node for node in candidates if getattr(node, "is_active_output", False)), None) or (
        candidates[0] if candidates else None
    )


def _ensure_output_target(
    tree: Any, scene: Any, owner_uuid: str, build_id: str, created: list[Any]
) -> tuple[Any, Any]:
    if hasattr(scene, "node_tree"):
        node = _active_node(
            node for node in tree.nodes if node.bl_idname == "CompositorNodeComposite"
        )
        if node is None:
            node = _mark_node(
                tree.nodes.new("CompositorNodeComposite"),
                owner_uuid,
                "COMPOSITE_OUTPUT",
                build_id,
            )
            node.name = "LightHelper Composite"
            created.append(node)
        return node, node.inputs.get("Image") or node.inputs[0]

    output_items = [
        item
        for item in tree.interface.items_tree
        if item.item_type == "SOCKET"
        and item.in_out == "OUTPUT"
        and item.socket_type == "NodeSocketColor"
    ]
    if output_items:
        interface_socket = output_items[0]
    else:
        interface_socket = tree.interface.new_socket(
            name="Image", in_out="OUTPUT", socket_type="NodeSocketColor"
        )
    node = _active_node(node for node in tree.nodes if node.bl_idname == "NodeGroupOutput")
    if node is None:
        node = _mark_node(
            tree.nodes.new("NodeGroupOutput"), owner_uuid, "COMPOSITE_OUTPUT", build_id
        )
        node.name = "LightHelper Group Output"
        created.append(node)
    socket = next(
        (item for item in node.inputs if item.identifier == interface_socket.identifier), None
    )
    if socket is None:
        socket = node.inputs.get(interface_socket.name)
    if socket is None:
        raise RuntimeError("The compositor root output socket is unavailable")
    return node, socket


def _socket(node: Any, *, identifier: str | None = None, name: str | None = None):
    if identifier is not None:
        found = next((item for item in node.outputs if item.identifier == identifier), None)
        if found is not None:
            return found
    if name is not None:
        found = node.outputs.get(name)
        if found is not None:
            return found
    raise RuntimeError(f"Required output is unavailable: {identifier or name}")


def _new_mix_node(
    tree: Any,
    operation: str,
    left: Any,
    right: Any | None,
    *,
    owner_uuid: str,
    role: str,
    build_id: str,
    created: list[Any],
    tint: tuple[float, float, float] | None = None,
) -> tuple[Any, Any]:
    if hasattr(bpy.types, "CompositorNodeMixRGB"):
        node = tree.nodes.new("CompositorNodeMixRGB")
        node.blend_type = operation
        node.inputs[0].default_value = 1.0
        left_input, right_input, output = node.inputs[1], node.inputs[2], node.outputs[0]
    else:
        node = tree.nodes.new("ShaderNodeMix")
        node.data_type = "RGBA"
        node.blend_type = operation
        node.clamp_factor = False
        node.clamp_result = False
        node.inputs.get("Factor").default_value = 1.0
        left_input = next(item for item in node.inputs if item.identifier == "A_Color")
        right_input = next(item for item in node.inputs if item.identifier == "B_Color")
        output = next(item for item in node.outputs if item.identifier == "Result_Color")
    _mark_node(node, owner_uuid, role, build_id)
    created.append(node)
    tree.links.new(left, left_input)
    if right is not None:
        tree.links.new(right, right_input)
    elif tint is not None:
        right_input.default_value = (*tint, 1.0)
    return node, output


def read_managed_adjustments(tree: Any, owner_uuid: str) -> dict[str, GroupAdjustment]:
    result: dict[str, GroupAdjustment] = {}
    for node in _managed_nodes(tree, owner_uuid):
        if node.get(MANAGED_ROLE_KEY) != "GROUP_EXPOSURE":
            continue
        name = node.get(MANAGED_GROUP_KEY)
        if not isinstance(name, str) or not name:
            continue
        ev = float(node.get(MANAGED_EV_KEY, 0.0))
        tint_value = node.get(MANAGED_TINT_KEY, (1.0, 1.0, 1.0))
        try:
            tint = tuple(float(value) for value in tint_value[:3])
            result[name] = GroupAdjustment(name=name, ev=ev, tint=tint)
        except (TypeError, ValueError):
            continue
    return result


def build_light_group_compositor(
    scene: Any,
    view_layer: Any,
    adjustments: Mapping[str, GroupAdjustment] | None = None,
) -> CompositorBuildResult:
    if scene.render.engine != "CYCLES":
        raise RuntimeError("Cycles Light Groups require the Cycles render engine")
    names = light_group_names(view_layer)
    if not names:
        names = ensure_used_light_groups(scene, view_layer)
    if not names:
        raise RuntimeError("No Light Groups are configured on this View Layer")

    owner_uuid = _scene_owner_uuid(scene)
    tree = _compositor_tree(scene, create=True)
    if tree is None:
        raise RuntimeError("The scene compositor is unavailable")
    previous = read_managed_adjustments(tree, owner_uuid)
    effective = dict(previous)
    if adjustments is not None:
        effective.update(adjustments)
    plan = build_light_group_plan(names, effective)
    build_id = uuid4().hex
    old_nodes = _managed_nodes(tree, owner_uuid)
    created: list[Any] = []
    try:
        output_node, output_input = _ensure_output_target(
            tree, scene, owner_uuid, build_id, created
        )
        if output_node.get(MANAGED_OWNER_KEY) == owner_uuid:
            output_node[MANAGED_BUILD_KEY] = build_id
        existing_link = output_input.links[0] if output_input.is_linked else None
        source_is_managed = bool(
            existing_link
            and existing_link.from_node.get(MANAGED_OWNER_KEY) == owner_uuid
        )
        connection = decide_composite_connection(
            input_is_linked=existing_link is not None,
            source_is_managed=source_is_managed,
        )

        render_layers = _ensure_render_layers(
            tree, view_layer, owner_uuid, build_id, created
        )
        combined = _socket(render_layers, identifier="Image", name="Image")
        raw_outputs = {
            group_key(name): _socket(
                render_layers,
                identifier=f"Combined_{name}",
                name=f"Combined_{name}",
            )
            for name in names
        }
        outputs: dict[str, Any] = {"combined": combined}
        outputs.update({f"raw:{key}": value for key, value in raw_outputs.items()})
        x = 0.0
        for step in plan["steps"]:
            operation = step["operation"]
            role = step["role"]
            if operation == "EXPOSURE":
                node = tree.nodes.new("CompositorNodeExposure")
                _mark_node(node, owner_uuid, "GROUP_EXPOSURE", build_id)
                created.append(node)
                tree.links.new(outputs[step["inputs"][0]], node.inputs.get("Image") or node.inputs[0])
                (node.inputs.get("Exposure") or node.inputs[1]).default_value = step["ev"]
                output = node.outputs.get("Image") or node.outputs[0]
                group = next(item for item in plan["groups"] if f"exposure:{item['key']}" == role)
                node[MANAGED_GROUP_KEY] = group["name"]
                node[MANAGED_EV_KEY] = group["ev"]
                node[MANAGED_TINT_KEY] = group["tint"]
                node.label = f"{group['name']} · {group['ev']:+.2f} EV"
            else:
                left = outputs[step["inputs"][0]]
                right = outputs[step["inputs"][1]] if len(step["inputs"]) > 1 else None
                node, output = _new_mix_node(
                    tree,
                    operation,
                    left,
                    right,
                    owner_uuid=owner_uuid,
                    role=role.split(":", 1)[0].upper(),
                    build_id=build_id,
                    created=created,
                    tint=tuple(step["tint"]) if "tint" in step else None,
                )
            node.location = (x, -120.0 * len(created))
            x += 40.0
            outputs[role] = output

        final_output = outputs[plan["output"]]
        managed_output = final_output.node
        managed_output.name = "LightHelper Mixer Output"
        managed_output.label = "LightHelper Mixer Output"
        managed_output[MANAGED_ROLE_KEY] = "MIXER_OUTPUT"
        warnings = []
        if connection in {
            CompositeConnectionDecision.CONNECT,
            CompositeConnectionDecision.REPLACE_MANAGED,
        }:
            if existing_link is not None:
                tree.links.remove(existing_link)
            tree.links.new(final_output, output_input)
        else:
            warnings.append(
                "A user-authored compositor output link was preserved; use the LightHelper output manually"
            )
        for node in old_nodes:
            if node not in created and node != output_node:
                tree.nodes.remove(node)
        managed_output.name = "LightHelper Mixer Output"
    except Exception:
        for node in reversed(created):
            try:
                tree.nodes.remove(node)
            except (ReferenceError, RuntimeError, TypeError):
                pass
        raise
    return CompositorBuildResult(
        group_count=len(names),
        connection=connection,
        output_node=managed_output.name,
        target_node=output_node.name,
        warnings=warnings,
    )


def remove_managed_light_group_compositor(scene: Any) -> int:
    tree = _compositor_tree(scene, create=False)
    if tree is None:
        return 0
    owner_uuid = scene.get(UUID_KEY)
    if not isinstance(owner_uuid, str):
        return 0
    nodes = _managed_nodes(tree, owner_uuid)
    removed = 0
    for node in nodes:
        if node.get(MANAGED_ROLE_KEY) == "COMPOSITE_OUTPUT":
            # In 5.x this is structural root output state. Keep it, and make
            # any user-authored replacement link ordinary user data.
            for key in (
                MANAGED_OWNER_KEY,
                MANAGED_ROLE_KEY,
                MANAGED_BUILD_KEY,
                MANAGED_VERSION_KEY,
            ):
                if key in node:
                    del node[key]
            continue
        tree.nodes.remove(node)
        removed += 1
    return removed


__all__ = [
    "CompositorBuildResult",
    "build_light_group_compositor",
    "ensure_light_group",
    "ensure_used_light_groups",
    "light_group_names",
    "read_managed_adjustments",
    "remove_light_group",
    "remove_managed_light_group_compositor",
    "used_light_group_names",
]
