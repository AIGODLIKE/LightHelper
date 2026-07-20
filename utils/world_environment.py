from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import bmesh
import bpy


WORLD_DOME_SCENE_UUID_KEY = "light_helper_world_dome_uuid"
WORLD_DOME_OWNER_KEY = "light_helper_world_dome_owner"
WORLD_DOME_ROLE_KEY = "light_helper_world_dome_role"
WORLD_DOME_NODE_ROLE_KEY = "light_helper_world_dome_node_role"
WORLD_DOME_SOURCE_WORLD_KEY = "light_helper_world_dome_source_world"
WORLD_DOME_SOURCE_WORLD_POINTER_KEY = "light_helper_world_dome_source_world_pointer"
WORLD_DOME_SOURCE_IMAGE_KEY = "light_helper_world_dome_source_image"
WORLD_DOME_SOURCE_TYPE_KEY = "light_helper_world_dome_source_type"
WORLD_DOME_OWNER_SCENE_POINTER_KEY = "light_helper_world_dome_owner_scene_pointer"

WORLD_SOURCE_NONE = "NONE"
WORLD_SOURCE_HDRI = "HDRI"
WORLD_SOURCE_COLOR = "COLOR"

ROLE_DOME_OBJECT = "DOME_OBJECT"
ROLE_DOME_MESH = "DOME_MESH"
ROLE_DOME_MATERIAL = "DOME_MATERIAL"
ROLE_DOME_COLLECTION = "DOME_COLLECTION"
ROLE_FALLBACK_WORLD = "FALLBACK_WORLD"
ROLE_SUN_RECEIVER = "SUN_RECEIVER"
ROLE_SUN_RECEIVER_COPY = "SUN_RECEIVER_COPY"
ROLE_SUN_PROXY = "SUN_PROXY"

NODE_ROLE_MAPPING = "MAPPING"
NODE_ROLE_ENVIRONMENT = "ENVIRONMENT"
NODE_ROLE_SOURCE_COLOR = "SOURCE_COLOR"
NODE_ROLE_GAMMA = "GAMMA"
NODE_ROLE_SATURATION = "SATURATION"
NODE_ROLE_TINT = "TINT"
NODE_ROLE_EMISSION = "EMISSION"
NODE_ROLE_LIGHT_PATH = "LIGHT_PATH"
NODE_ROLE_MAX_TOTAL = "MAX_TOTAL"
NODE_ROLE_MAX_DIFFUSE = "MAX_DIFFUSE"
NODE_ROLE_MAX_GLOSSY = "MAX_GLOSSY"
NODE_ROLE_MAX_TRANSMISSION = "MAX_TRANSMISSION"
NODE_ROLE_BOUNCE_GATE = "BOUNCE_GATE"

DEFAULT_RADIUS = 50.0
DEFAULT_STRENGTH = 1.0
DEFAULT_MAX_TOTAL = 2
DEFAULT_MAX_DIFFUSE = 1
DEFAULT_MAX_GLOSSY = 1
DEFAULT_MAX_TRANSMISSION = 2
DEFAULT_SEARCH_DEPTH = 64


@dataclass(frozen=True)
class _GroupFrame:
    parent_tree: bpy.types.NodeTree
    group_node: bpy.types.Node


@dataclass
class WorldEnvironmentInfo:
    source_type: str = WORLD_SOURCE_NONE
    image: bpy.types.Image | None = None
    environment_node: bpy.types.Node | None = None
    group_stack: tuple[_GroupFrame, ...] = ()
    mapping_node: bpy.types.Node | None = None
    mapping_stack: tuple[_GroupFrame, ...] = ()
    background_node: bpy.types.Node | None = None
    background_stack: tuple[_GroupFrame, ...] = ()
    connected_environment_count: int = 0
    connected_image_count: int = 0
    projection: str = "EQUIRECTANGULAR"
    interpolation: str = "Linear"
    color: tuple[float, float, float] = (0.050876, 0.050876, 0.050876)
    strength: float = DEFAULT_STRENGTH
    gamma: float = 1.0
    saturation: float = 1.0
    tint: tuple[float, float, float] = (1.0, 1.0, 1.0)
    tint_factor: float = 0.0
    location: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0)

    @property
    def has_source(self) -> bool:
        return self.source_type in {WORLD_SOURCE_HDRI, WORLD_SOURCE_COLOR}


def _mark_managed(id_block, owner_uuid: str, role: str) -> None:
    id_block[WORLD_DOME_OWNER_KEY] = owner_uuid
    id_block[WORLD_DOME_ROLE_KEY] = role


def _is_managed(id_block, owner_uuid: str | None = None, role: str | None = None) -> bool:
    if id_block is None:
        return False
    if owner_uuid is not None and id_block.get(WORLD_DOME_OWNER_KEY) != owner_uuid:
        return False
    if role is not None and id_block.get(WORLD_DOME_ROLE_KEY) != role:
        return False
    return bool(id_block.get(WORLD_DOME_OWNER_KEY) and id_block.get(WORLD_DOME_ROLE_KEY))


def _scene_owner_uuid(scene: bpy.types.Scene, create: bool = False) -> str | None:
    owner_uuid = scene.get(WORLD_DOME_SCENE_UUID_KEY)
    if isinstance(owner_uuid, str) and owner_uuid:
        if not create or not any(
                other != scene and other.get(WORLD_DOME_SCENE_UUID_KEY) == owner_uuid
                for other in bpy.data.scenes):
            return owner_uuid
        # Scene.copy() duplicates custom properties. A scene that is about to
        # create new managed data must never reuse another scene's owner UUID.
        owner_uuid = uuid4().hex
        scene[WORLD_DOME_SCENE_UUID_KEY] = owner_uuid
        return owner_uuid
    if not create:
        return None
    owner_uuid = uuid4().hex
    scene[WORLD_DOME_SCENE_UUID_KEY] = owner_uuid
    return owner_uuid


def _node_socket_index(sockets, target) -> int | None:
    for index, socket in enumerate(sockets):
        if socket == target:
            return index
    return None


def _matching_socket(sockets, source_socket):
    identifier = getattr(source_socket, "identifier", "")
    if identifier:
        for socket in sockets:
            if getattr(socket, "identifier", "") == identifier:
                return socket
    name = getattr(source_socket, "name", "")
    if name:
        matches = [socket for socket in sockets if socket.name == name]
        if len(matches) == 1:
            return matches[0]
    return None


def _active_output(nodes, output_type: str):
    candidates = [node for node in nodes if node.type == output_type]
    for node in candidates:
        if getattr(node, "is_active_output", False):
            return node
    return candidates[0] if candidates else None


def _group_output_input(group_node: bpy.types.Node, output_socket):
    node_tree = group_node.node_tree
    if node_tree is None:
        return None
    output = _active_output(node_tree.nodes, "GROUP_OUTPUT")
    if output is None:
        return None
    match = _matching_socket(output.inputs, output_socket)
    if match is not None:
        return match
    index = _node_socket_index(group_node.outputs, output_socket)
    if index is not None and index < len(output.inputs):
        return output.inputs[index]
    return None


def _parent_group_input(group_input_socket, stack: tuple[_GroupFrame, ...]):
    if not stack:
        return None, None, ()
    frame = stack[-1]
    parent_input = _matching_socket(frame.group_node.inputs, group_input_socket)
    if parent_input is None:
        index = _node_socket_index(group_input_socket.node.outputs, group_input_socket)
        if index is not None and index < len(frame.group_node.inputs):
            parent_input = frame.group_node.inputs[index]
    return parent_input, frame.parent_tree, stack[:-1]


def _walk_connected_nodes(
        input_socket,
        node_tree: bpy.types.NodeTree,
        stack: tuple[_GroupFrame, ...],
        depth: int,
        max_depth: int,
        background_ref,
        ancestry: frozenset,
        candidates: list,
        connected_env: list,
        connected_backgrounds: list,
) -> None:
    if input_socket is None or depth > max_depth:
        return
    for link in input_socket.links:
        node = link.from_node
        output_socket = link.from_socket
        stack_key = tuple(frame.group_node.as_pointer() for frame in stack)
        key = (node_tree.as_pointer(), node.as_pointer(), output_socket.identifier, stack_key)
        if key in ancestry:
            continue
        next_ancestry = ancestry | {key}

        if node.type == "TEX_ENVIRONMENT":
            connected_env.append((node, stack))
            if node.image is not None:
                candidates.append((depth, node, stack, background_ref))
            continue

        if node.type == "GROUP" and node.node_tree is not None:
            inner_input = _group_output_input(node, output_socket)
            if inner_input is not None:
                _walk_connected_nodes(
                    inner_input,
                    node.node_tree,
                    stack + (_GroupFrame(node_tree, node),),
                    depth + 1,
                    max_depth,
                    background_ref,
                    next_ancestry,
                    candidates,
                    connected_env,
                    connected_backgrounds,
                )
            continue

        if node.type == "GROUP_INPUT":
            parent_input, parent_tree, parent_stack = _parent_group_input(output_socket, stack)
            if parent_input is not None:
                _walk_connected_nodes(
                    parent_input,
                    parent_tree,
                    parent_stack,
                    depth + 1,
                    max_depth,
                    background_ref,
                    next_ancestry,
                    candidates,
                    connected_env,
                    connected_backgrounds,
                )
            continue

        next_background = background_ref
        if node.type == "BACKGROUND":
            next_background = (node, stack)
            connected_backgrounds.append((depth, node, stack))
        for node_input in node.inputs:
            if node_input.is_linked:
                _walk_connected_nodes(
                    node_input,
                    node_tree,
                    stack,
                    depth + 1,
                    max_depth,
                    next_background,
                    next_ancestry,
                    candidates,
                    connected_env,
                    connected_backgrounds,
                )


def _find_upstream_node(
        input_socket,
        node_tree: bpy.types.NodeTree,
        stack: tuple[_GroupFrame, ...],
        node_type: str,
        depth: int = 0,
        max_depth: int = DEFAULT_SEARCH_DEPTH,
        visited: set | None = None,
):
    if input_socket is None or depth > max_depth:
        return None, ()
    if visited is None:
        visited = set()
    for link in input_socket.links:
        node = link.from_node
        output_socket = link.from_socket
        key = (
            node_tree.as_pointer(),
            node.as_pointer(),
            output_socket.identifier,
            tuple(frame.group_node.as_pointer() for frame in stack),
        )
        if key in visited:
            continue
        visited.add(key)
        if node.type == node_type:
            return node, stack
        if node.type == "GROUP" and node.node_tree is not None:
            inner_input = _group_output_input(node, output_socket)
            found = _find_upstream_node(
                inner_input,
                node.node_tree,
                stack + (_GroupFrame(node_tree, node),),
                node_type,
                depth + 1,
                max_depth,
                visited,
            )
            if found[0] is not None:
                return found
            continue
        if node.type == "GROUP_INPUT":
            parent_input, parent_tree, parent_stack = _parent_group_input(output_socket, stack)
            found = _find_upstream_node(
                parent_input,
                parent_tree,
                parent_stack,
                node_type,
                depth + 1,
                max_depth,
                visited,
            )
            if found[0] is not None:
                return found
            continue
        for node_input in node.inputs:
            if not node_input.is_linked:
                continue
            found = _find_upstream_node(
                node_input,
                node_tree,
                stack,
                node_type,
                depth + 1,
                max_depth,
                visited,
            )
            if found[0] is not None:
                return found
    return None, ()


def _socket_default(socket):
    if socket is None or not hasattr(socket, "default_value"):
        return None
    value = socket.default_value
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return tuple(float(component) for component in value)
    except (TypeError, ValueError):
        return None


def _resolve_socket_value(
        input_socket,
        node_tree: bpy.types.NodeTree,
        stack: tuple[_GroupFrame, ...],
        depth: int = 0,
        visited: set | None = None,
):
    if input_socket is None or depth > DEFAULT_SEARCH_DEPTH:
        return None
    if visited is None:
        visited = set()
    if not input_socket.is_linked:
        return _socket_default(input_socket)

    link = input_socket.links[0]
    node = link.from_node
    output_socket = link.from_socket
    key = (
        node_tree.as_pointer(),
        node.as_pointer(),
        output_socket.identifier,
        tuple(frame.group_node.as_pointer() for frame in stack),
    )
    if key in visited:
        return None
    visited.add(key)

    if node.type == "GROUP_INPUT":
        parent_input, parent_tree, parent_stack = _parent_group_input(output_socket, stack)
        return _resolve_socket_value(parent_input, parent_tree, parent_stack, depth + 1, visited)
    if node.type == "VALUE":
        return _socket_default(output_socket)
    if node.type == "RGB":
        return _socket_default(output_socket)
    if node.type == "COMBXYZ":
        values = [
            _resolve_socket_value(node.inputs[index], node_tree, stack, depth + 1, visited.copy())
            for index in range(min(3, len(node.inputs)))
        ]
        if len(values) == 3 and all(isinstance(value, (int, float)) for value in values):
            return tuple(float(value) for value in values)
    if node.type == "GROUP" and node.node_tree is not None:
        inner_input = _group_output_input(node, output_socket)
        return _resolve_socket_value(
            inner_input,
            node.node_tree,
            stack + (_GroupFrame(node_tree, node),),
            depth + 1,
            visited,
        )
    return None


def _vector3(value, default):
    if value is None:
        return default
    try:
        values = tuple(float(component) for component in value)
    except (TypeError, ValueError):
        return default
    return values[:3] if len(values) >= 3 else default


def _group_control_value(
        stack: tuple[_GroupFrame, ...],
        names: tuple[str, ...],
):
    for index, frame in enumerate(stack):
        for name in names:
            socket = frame.group_node.inputs.get(name)
            if socket is None:
                continue
            value = _resolve_socket_value(
                socket,
                frame.parent_tree,
                stack[:index],
            )
            if value is not None:
                return value
    return None


def find_world_environment(scene: bpy.types.Scene, max_depth: int = DEFAULT_SEARCH_DEPTH) -> WorldEnvironmentInfo:
    info = WorldEnvironmentInfo()
    world = scene.world if scene is not None else None
    if world is None:
        return info
    if not world.use_nodes or world.node_tree is None:
        info.source_type = WORLD_SOURCE_COLOR
        info.color = _vector3(getattr(world, "color", None), info.color)
        return info
    output = None
    get_output_node = getattr(world.node_tree, "get_output_node", None)
    if get_output_node is not None:
        if scene.render.engine == "CYCLES":
            targets = ("CYCLES", "ALL")
        elif is_eevee_engine(scene.render.engine):
            targets = ("EEVEE", "ALL")
        else:
            targets = ("ALL",)
        for target in targets:
            try:
                output = get_output_node(target)
            except (TypeError, ValueError):
                output = None
            if output is not None:
                break
    if output is None:
        output = _active_output(world.node_tree.nodes, "OUTPUT_WORLD")
    if output is None:
        return info
    surface = output.inputs.get("Surface")
    if surface is None or not surface.is_linked:
        return info

    candidates = []
    connected_env = []
    connected_backgrounds = []
    _walk_connected_nodes(
        surface,
        world.node_tree,
        (),
        0,
        max_depth,
        None,
        frozenset(),
        candidates,
        connected_env,
        connected_backgrounds,
    )
    environment_instances = {
        (
            node.as_pointer(),
            tuple(frame.group_node.as_pointer() for frame in stack),
        )
        for node, stack in connected_env
    }
    connected_images = {
        node.image.as_pointer()
        for _, node, _, _ in candidates
        if node.image is not None
    }
    info.connected_environment_count = len(environment_instances)
    info.connected_image_count = len(connected_images)
    def _background_key(item):
        depth, node, stack = item
        stack_names = tuple(frame.group_node.name for frame in stack)
        return depth, stack_names, node.name

    if not candidates:
        if not connected_backgrounds:
            return info
        _, background, background_stack = min(connected_backgrounds, key=_background_key)
        color_socket = background.inputs.get("Color")
        resolved_color = _resolve_socket_value(
            color_socket,
            background.id_data,
            background_stack,
        )
        # An empty connected Environment Texture has no usable color output.
        # In that specific case, use the Background socket's fallback color.
        # Other unresolved procedural color graphs stay unsupported rather than
        # being silently flattened to an unrelated default.
        if resolved_color is None and info.connected_environment_count:
            resolved_color = _socket_default(color_socket)
        color = _vector3(resolved_color, None)
        if color is None:
            return info
        info.source_type = WORLD_SOURCE_COLOR
        info.color = color
        info.background_node = background
        info.background_stack = background_stack
        strength = _resolve_socket_value(
            background.inputs.get("Strength"),
            background.id_data,
            background_stack,
        )
        if isinstance(strength, (int, float)):
            info.strength = max(0.0, float(strength))
        return info

    def _candidate_key(item):
        depth, node, stack, background_ref = item
        background_name = background_ref[0].name if background_ref is not None else ""
        stack_names = tuple(frame.group_node.name for frame in stack)
        return depth, stack_names, background_name, node.name

    _, env_node, env_stack, background_ref = min(candidates, key=_candidate_key)
    info.image = env_node.image
    info.environment_node = env_node
    info.source_type = WORLD_SOURCE_HDRI
    info.group_stack = env_stack
    info.projection = getattr(env_node, "projection", "EQUIRECTANGULAR")
    info.interpolation = getattr(env_node, "interpolation", "Linear")
    group_strength = _group_control_value(env_stack, ("天空强度", "Sky Strength", "Strength"))
    if isinstance(group_strength, (int, float)):
        info.strength = max(0.0, float(group_strength))
    group_gamma = _group_control_value(env_stack, ("Gamma",))
    if isinstance(group_gamma, (int, float)):
        info.gamma = max(0.001, float(group_gamma))
    group_saturation = _group_control_value(env_stack, ("Saturation", "饱和度"))
    if isinstance(group_saturation, (int, float)):
        info.saturation = max(0.0, float(group_saturation))
    group_tint = _group_control_value(env_stack, ("着色", "Tint"))
    info.tint = _vector3(group_tint, info.tint)
    group_tint_factor = _group_control_value(env_stack, ("着色系数", "Tint Factor"))
    if isinstance(group_tint_factor, (int, float)):
        info.tint_factor = max(0.0, min(1.0, float(group_tint_factor)))
    if background_ref is not None:
        info.background_node, info.background_stack = background_ref
        strength_socket = info.background_node.inputs.get("Strength")
        resolved = _resolve_socket_value(
            strength_socket,
            info.background_node.id_data,
            info.background_stack,
        )
        if isinstance(resolved, (int, float)):
            info.strength = max(0.0, float(resolved))

    vector_input = env_node.inputs.get("Vector")
    mapping, mapping_stack = _find_upstream_node(
        vector_input,
        env_node.id_data,
        env_stack,
        "MAPPING",
        max_depth=max_depth,
    )
    if mapping is not None:
        info.mapping_node = mapping
        info.mapping_stack = mapping_stack
        info.location = _vector3(
            _resolve_socket_value(mapping.inputs.get("Location"), mapping.id_data, mapping_stack),
            info.location,
        )
        info.rotation = _vector3(
            _resolve_socket_value(mapping.inputs.get("Rotation"), mapping.id_data, mapping_stack),
            info.rotation,
        )
        info.scale = _vector3(
            _resolve_socket_value(mapping.inputs.get("Scale"), mapping.id_data, mapping_stack),
            info.scale,
        )
    return info


def _object_is_in_scene(scene: bpy.types.Scene, obj: bpy.types.Object | None) -> bool:
    return bool(
        scene is not None
        and obj is not None
        and scene.objects.get(obj.name) == obj
    )


def _raw_world_dome(
        scene: bpy.types.Scene,
        *,
        repair_pointer: bool = False,
) -> bpy.types.Object | None:
    if scene is None:
        return None
    props = getattr(scene, "light_helper_property", None)
    dome = getattr(props, "world_environment_dome", None) if props is not None else None
    owner_uuid = _scene_owner_uuid(scene)
    if dome is not None and _is_managed(dome, owner_uuid, ROLE_DOME_OBJECT):
        if _object_is_in_scene(scene, dome):
            return dome
    if owner_uuid is None:
        return None
    matches = [
        obj for obj in scene.objects
        if _is_managed(obj, owner_uuid, ROLE_DOME_OBJECT)
    ]
    if not matches:
        return None
    dome = sorted(matches, key=lambda obj: obj.name_full.casefold())[0]
    if repair_pointer and props is not None:
        props.world_environment_dome = dome
    return dome


def _dome_owner_scene(
        dome: bpy.types.Object,
        owner_uuid: str,
        *,
        repair_pointer: bool = False,
) -> bpy.types.Scene | None:
    owner_scene = dome.get(WORLD_DOME_OWNER_SCENE_POINTER_KEY)
    if isinstance(owner_scene, bpy.types.Scene) and _object_is_in_scene(owner_scene, dome):
        return owner_scene
    # Compatibility path for files created before the owner-scene pointer was
    # introduced. Blender keeps the source scene before its copies in this
    # collection, giving copied scenes a deterministic isolation target.
    for candidate in bpy.data.scenes:
        if (candidate.get(WORLD_DOME_SCENE_UUID_KEY) == owner_uuid
                and _object_is_in_scene(candidate, dome)):
            if repair_pointer:
                dome[WORLD_DOME_OWNER_SCENE_POINTER_KEY] = candidate
            return candidate
    return None


def _remove_isolation_copy(
        dome,
        mesh,
        material,
        collection,
        managed_world,
) -> None:
    if dome is not None and dome.name in bpy.data.objects:
        bpy.data.objects.remove(dome, do_unlink=True)
    if mesh is not None and mesh.users == 0 and mesh.name in bpy.data.meshes:
        bpy.data.meshes.remove(mesh)
    if material is not None and material.users == 0 and material.name in bpy.data.materials:
        bpy.data.materials.remove(material)
    if collection is not None:
        for parent_scene in bpy.data.scenes:
            if collection.name in parent_scene.collection.children:
                parent_scene.collection.children.unlink(collection)
        if collection.users == 0 and collection.name in bpy.data.collections:
            bpy.data.collections.remove(collection)
    if managed_world is not None and managed_world.users == 0 and managed_world.name in bpy.data.worlds:
        bpy.data.worlds.remove(managed_world)


def _isolate_copied_scene_environment(
        scene: bpy.types.Scene,
        source_dome: bpy.types.Object,
) -> bpy.types.Object:
    """Give a Scene.copy() its own dome data before any destructive action."""
    props = getattr(scene, "light_helper_property", None)
    old_owner = source_dome.get(WORLD_DOME_OWNER_KEY)
    if props is None or not isinstance(old_owner, str) or not old_owner:
        return source_dome

    direct_collections = [
        collection for collection in list(scene.collection.children)
        if _is_managed(collection, old_owner, ROLE_DOME_COLLECTION)
        and source_dome.name in collection.objects
    ]
    source_direct = scene.collection.objects.get(source_dome.name) == source_dome
    if not direct_collections and not source_direct:
        # A user moved the locked managed object into a shared collection. Do
        # not mutate that collection globally; restore has a second safety net
        # that refuses to delete an object used by another scene.
        return source_dome

    new_owner = uuid4().hex
    new_mesh = None
    new_material = None
    new_dome = None
    new_collection = None
    new_world = None
    detached_collections = []
    detached_direct = False
    try:
        if source_dome.type == "MESH" and source_dome.data is not None:
            new_mesh = source_dome.data.copy()
            new_mesh.name = f"LH World Environment Mesh [{new_owner[:8]}]"
            _mark_managed(new_mesh, new_owner, ROLE_DOME_MESH)
        source_material = source_dome.active_material
        if source_material is not None:
            new_material = source_material.copy()
            new_material.name = f"LH World Environment [{new_owner[:8]}]"
            _mark_managed(new_material, new_owner, ROLE_DOME_MATERIAL)
            if new_mesh is not None:
                for index, material in enumerate(new_mesh.materials):
                    if material == source_material:
                        new_mesh.materials[index] = new_material

        new_dome = source_dome.copy()
        if new_mesh is not None:
            new_dome.data = new_mesh
        new_dome.name = f"LH World Environment [{new_owner[:8]}]"
        _mark_managed(new_dome, new_owner, ROLE_DOME_OBJECT)
        new_dome[WORLD_DOME_OWNER_SCENE_POINTER_KEY] = scene

        if direct_collections:
            new_collection = direct_collections[0].copy()
            new_collection.name = f"LH World Environment [{new_owner[:8]}]"
            for obj in list(new_collection.objects):
                if obj == source_dome:
                    new_collection.objects.unlink(obj)
        else:
            new_collection = bpy.data.collections.new(
                f"LH World Environment [{new_owner[:8]}]"
            )
        _mark_managed(new_collection, new_owner, ROLE_DOME_COLLECTION)
        new_collection.objects.link(new_dome)
        scene.collection.children.link(new_collection)

        old_world = props.world_environment_managed_world
        if old_world is None and _is_managed(scene.world, old_owner, ROLE_FALLBACK_WORLD):
            old_world = scene.world
        if old_world is not None:
            new_world = old_world.copy()
            new_world.name = f"LH World Fallback [{new_owner[:8]}]"
            _mark_managed(new_world, new_owner, ROLE_FALLBACK_WORLD)

        for collection in direct_collections:
            scene.collection.children.unlink(collection)
            detached_collections.append(collection)
        if source_direct:
            scene.collection.objects.unlink(source_dome)
            detached_direct = True
        if _object_is_in_scene(scene, source_dome):
            raise RuntimeError("The copied scene uses the source dome through a shared user collection")

        scene[WORLD_DOME_SCENE_UUID_KEY] = new_owner
        props.world_environment_sun_records.clear()
        props.world_environment_dome = new_dome
        props.world_environment_managed_world = new_world
        if new_world is not None:
            scene.world = new_world
        return new_dome
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
        if new_collection is not None and new_collection.name in scene.collection.children:
            scene.collection.children.unlink(new_collection)
        for collection in detached_collections:
            if collection.name not in scene.collection.children:
                scene.collection.children.link(collection)
        if detached_direct and scene.collection.objects.get(source_dome.name) is None:
            scene.collection.objects.link(source_dome)
        _remove_isolation_copy(new_dome, new_mesh, new_material, new_collection, new_world)
        return source_dome


def get_world_dome(scene: bpy.types.Scene) -> bpy.types.Object | None:
    """Return the managed dome without modifying or isolating scene data."""
    return _raw_world_dome(scene)


def is_world_dome_owned_by_scene(
        scene: bpy.types.Scene,
        dome: bpy.types.Object | None = None,
) -> bool:
    """Whether ``dome`` belongs to ``scene`` rather than a copied source scene."""
    dome = dome or _raw_world_dome(scene)
    if dome is None:
        return False
    owner_uuid = dome.get(WORLD_DOME_OWNER_KEY)
    if not isinstance(owner_uuid, str) or not owner_uuid:
        return False
    owner_scene = _dome_owner_scene(dome, owner_uuid)
    return owner_scene is None or owner_scene == scene


def ensure_world_dome_ownership(scene: bpy.types.Scene) -> bpy.types.Object | None:
    """Repair the scene pointer and isolate copied dome data for a mutating action."""
    dome = _raw_world_dome(scene, repair_pointer=True)
    if dome is None:
        return None
    owner_uuid = dome.get(WORLD_DOME_OWNER_KEY)
    owner_scene = _dome_owner_scene(dome, owner_uuid, repair_pointer=True)
    if owner_scene is not None and owner_scene != scene:
        return _isolate_copied_scene_environment(scene, dome)
    return dome


def is_world_environment_converted(scene: bpy.types.Scene) -> bool:
    return get_world_dome(scene) is not None


def _node_with_role(material: bpy.types.Material, role: str):
    if material is None or material.node_tree is None:
        return None
    for node in material.node_tree.nodes:
        if node.get(WORLD_DOME_NODE_ROLE_KEY) == role:
            return node
    return None


def _set_node_role(node, role: str) -> None:
    node[WORLD_DOME_NODE_ROLE_KEY] = role


def _copy_color_ramp(source, target) -> None:
    target.color_mode = source.color_mode
    target.hue_interpolation = source.hue_interpolation
    target.interpolation = source.interpolation
    while len(target.elements) > 2:
        target.elements.remove(target.elements[-1])
    while len(target.elements) < len(source.elements):
        target.elements.new(source.elements[len(target.elements)].position)
    for src, dst in zip(source.elements, target.elements):
        dst.position = src.position
        dst.color = src.color


def _copy_environment_settings(source: bpy.types.Node, target: bpy.types.Node) -> None:
    target.image = source.image
    target.interpolation = source.interpolation
    target.projection = source.projection
    if hasattr(source, "extension") and hasattr(target, "extension"):
        target.extension = source.extension
    source_mapping = getattr(source, "color_mapping", None)
    target_mapping = getattr(target, "color_mapping", None)
    if source_mapping is None or target_mapping is None:
        return
    for name in (
        "blend_color", "blend_factor", "blend_type", "brightness", "contrast",
        "saturation", "use_color_ramp",
    ):
        try:
            setattr(target_mapping, name, getattr(source_mapping, name))
        except (AttributeError, TypeError, ValueError):
            pass
    if source_mapping.use_color_ramp:
        _copy_color_ramp(source_mapping.color_ramp, target_mapping.color_ramp)


def _make_sphere_mesh(name: str, owner_uuid: str, segments: int = 128, rings: int = 64):
    mesh = bpy.data.meshes.new(name)
    _mark_managed(mesh, owner_uuid, ROLE_DOME_MESH)
    bm = bmesh.new()
    try:
        bmesh.ops.create_uvsphere(
            bm,
            u_segments=segments,
            v_segments=rings,
            radius=1.0,
        )
        bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
        for face in bm.faces:
            face.smooth = True
        bm.to_mesh(mesh)
        mesh.update()
        return mesh
    except Exception:
        if mesh.users == 0 and mesh.name in bpy.data.meshes:
            bpy.data.meshes.remove(mesh)
        raise
    finally:
        bm.free()


def _create_dome_material(
        owner_uuid: str,
        info: WorldEnvironmentInfo,
) -> bpy.types.Material:
    material = bpy.data.materials.new(f"LH World Environment [{owner_uuid[:8]}]")
    _mark_managed(material, owner_uuid, ROLE_DOME_MATERIAL)
    try:
        return _populate_dome_material(material, info)
    except Exception:
        if material.users == 0 and material.name in bpy.data.materials:
            bpy.data.materials.remove(material)
        raise


def _populate_dome_material(
        material: bpy.types.Material,
        info: WorldEnvironmentInfo,
) -> bpy.types.Material:
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    output.name = "World Environment Output"
    output.location = (900, 80)

    emission = nodes.new("ShaderNodeEmission")
    emission.name = "World Environment Emission"
    emission.location = (660, 80)
    _set_node_role(emission, NODE_ROLE_EMISSION)

    if info.source_type == WORLD_SOURCE_HDRI:
        texcoord = nodes.new("ShaderNodeTexCoord")
        texcoord.name = "World Environment Coordinates"
        texcoord.location = (-1080, 260)

        invert = nodes.new("ShaderNodeVectorMath")
        invert.name = "Inward Normal to World Direction"
        invert.operation = "SCALE"
        invert.inputs[3].default_value = -1.0
        invert.location = (-860, 260)

        mapping = nodes.new("ShaderNodeMapping")
        mapping.name = "World Environment Mapping"
        mapping.vector_type = "POINT"
        mapping.location = (-620, 260)
        mapping.inputs["Location"].default_value = info.location
        mapping.inputs["Rotation"].default_value = info.rotation
        mapping.inputs["Scale"].default_value = info.scale
        _set_node_role(mapping, NODE_ROLE_MAPPING)

        source = nodes.new("ShaderNodeTexEnvironment")
        source.name = "World Environment HDRI"
        source.location = (-360, 260)
        _copy_environment_settings(info.environment_node, source)
        _set_node_role(source, NODE_ROLE_ENVIRONMENT)

        links.new(texcoord.outputs["Normal"], invert.inputs[0])
        links.new(invert.outputs["Vector"], mapping.inputs["Vector"])
        links.new(mapping.outputs["Vector"], source.inputs["Vector"])
        source_output = source.outputs["Color"]
    elif info.source_type == WORLD_SOURCE_COLOR:
        source = nodes.new("ShaderNodeRGB")
        source.name = "World Environment Color"
        source.location = (-360, 260)
        source.outputs["Color"].default_value = (*info.color[:3], 1.0)
        _set_node_role(source, NODE_ROLE_SOURCE_COLOR)
        source_output = source.outputs["Color"]
    else:
        raise ValueError("World environment information has no usable source")

    gamma = nodes.new("ShaderNodeGamma")
    gamma.name = "World Environment Gamma"
    gamma.inputs["Gamma"].default_value = 1.0
    gamma.location = (-130, 320)
    _set_node_role(gamma, NODE_ROLE_GAMMA)

    saturation = nodes.new("ShaderNodeHueSaturation")
    saturation.name = "World Environment Saturation"
    saturation.inputs["Saturation"].default_value = 1.0
    saturation.location = (90, 320)
    _set_node_role(saturation, NODE_ROLE_SATURATION)

    tint = nodes.new("ShaderNodeMixRGB")
    tint.name = "World Environment Tint"
    tint.blend_type = "MULTIPLY"
    tint.inputs[0].default_value = 0.0
    tint.inputs[2].default_value = (1.0, 1.0, 1.0, 1.0)
    tint.location = (310, 320)
    _set_node_role(tint, NODE_ROLE_TINT)

    light_path = nodes.new("ShaderNodeLightPath")
    light_path.name = "World Environment Light Path"
    light_path.location = (-620, -300)
    _set_node_role(light_path, NODE_ROLE_LIGHT_PATH)

    limits = []
    limit_specs = (
        ("Ray Depth", "Max Total Bounces", NODE_ROLE_MAX_TOTAL, DEFAULT_MAX_TOTAL),
        ("Diffuse Depth", "Max Diffuse Bounces", NODE_ROLE_MAX_DIFFUSE, DEFAULT_MAX_DIFFUSE),
        ("Glossy Depth", "Max Glossy Bounces", NODE_ROLE_MAX_GLOSSY, DEFAULT_MAX_GLOSSY),
        ("Transmission Depth", "Max Transmission Bounces", NODE_ROLE_MAX_TRANSMISSION, DEFAULT_MAX_TRANSMISSION),
    )
    for index, (depth_name, label, role, default) in enumerate(limit_specs):
        value = nodes.new("ShaderNodeValue")
        value.name = label
        value.label = label
        value.outputs[0].default_value = float(default)
        value.location = (-620, -500 - index * 110)
        _set_node_role(value, role)

        compare = nodes.new("ShaderNodeMath")
        compare.name = f"Block Above {label}"
        compare.operation = "GREATER_THAN"
        compare.location = (-330, -330 - index * 120)
        links.new(light_path.outputs[depth_name], compare.inputs[0])
        links.new(value.outputs[0], compare.inputs[1])
        limits.append(compare)

    combine_a = nodes.new("ShaderNodeMath")
    combine_a.operation = "MAXIMUM"
    combine_a.location = (-80, -390)
    links.new(limits[0].outputs[0], combine_a.inputs[0])
    links.new(limits[1].outputs[0], combine_a.inputs[1])

    combine_b = nodes.new("ShaderNodeMath")
    combine_b.operation = "MAXIMUM"
    combine_b.location = (-80, -600)
    links.new(limits[2].outputs[0], combine_b.inputs[0])
    links.new(limits[3].outputs[0], combine_b.inputs[1])

    combine_all = nodes.new("ShaderNodeMath")
    combine_all.operation = "MAXIMUM"
    combine_all.location = (130, -480)
    links.new(combine_a.outputs[0], combine_all.inputs[0])
    links.new(combine_b.outputs[0], combine_all.inputs[1])

    allowed = nodes.new("ShaderNodeMath")
    allowed.name = "World Environment Bounce Allowed"
    allowed.operation = "SUBTRACT"
    allowed.inputs[0].default_value = 1.0
    allowed.location = (330, -370)
    links.new(combine_all.outputs[0], allowed.inputs[1])

    gate = nodes.new("ShaderNodeMixRGB")
    gate.name = "World Environment Bounce Gate"
    gate.blend_type = "MULTIPLY"
    gate.inputs[0].default_value = 1.0
    gate.location = (520, 170)
    _set_node_role(gate, NODE_ROLE_BOUNCE_GATE)

    links.new(source_output, gamma.inputs["Color"])
    links.new(gamma.outputs["Color"], saturation.inputs["Color"])
    links.new(saturation.outputs["Color"], tint.inputs[1])
    links.new(tint.outputs[0], gate.inputs[1])
    links.new(allowed.outputs[0], gate.inputs[2])
    links.new(gate.outputs[0], emission.inputs["Color"])
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def _create_fallback_world(
        owner_uuid: str,
        original_world: bpy.types.World,
) -> bpy.types.World:
    # Copy the complete World so Volume and renderer-specific settings survive;
    # only Surface emission is neutralized in the scene-local managed copy.
    world = original_world.copy()
    world.name = f"LH World Fallback [{owner_uuid[:8]}]"
    _mark_managed(world, owner_uuid, ROLE_FALLBACK_WORLD)
    try:
        return _populate_fallback_world(world)
    except Exception:
        if world.users == 0 and world.name in bpy.data.worlds:
            bpy.data.worlds.remove(world)
        raise


def _populate_fallback_world(world: bpy.types.World) -> bpy.types.World:
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    background = nodes.new("ShaderNodeBackground")
    background.name = "Light Helper Zero Surface"
    background.label = "Light Helper Zero Surface"
    background.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
    background.inputs["Strength"].default_value = 0.0
    outputs = [node for node in nodes if node.type == "OUTPUT_WORLD"]
    if not outputs:
        outputs = [nodes.new("ShaderNodeOutputWorld")]
    for output in outputs:
        surface = output.inputs.get("Surface")
        if surface is None:
            continue
        for link in list(surface.links):
            links.remove(link)
        links.new(background.outputs["Background"], surface)
    return world


def _find_or_create_dome_collection(scene: bpy.types.Scene, owner_uuid: str):
    for collection in bpy.data.collections:
        if _is_managed(collection, owner_uuid, ROLE_DOME_COLLECTION):
            if collection.name not in scene.collection.children:
                scene.collection.children.link(collection)
            return collection
    collection = bpy.data.collections.new(f"LH World Environment [{owner_uuid[:8]}]")
    _mark_managed(collection, owner_uuid, ROLE_DOME_COLLECTION)
    try:
        collection.color_tag = "COLOR_05"
    except (AttributeError, TypeError, ValueError):
        pass
    scene.collection.children.link(collection)
    return collection


def _set_scene_properties_from_info(scene: bpy.types.Scene, info: WorldEnvironmentInfo) -> None:
    props = scene.light_helper_property
    props.world_dome_color = info.color
    props.world_dome_strength = info.strength
    props.world_dome_rotation = info.rotation
    props.world_dome_mapping_location = info.location
    props.world_dome_mapping_scale = info.scale
    props.world_dome_radius = DEFAULT_RADIUS
    props.world_dome_tint = info.tint
    props.world_dome_tint_factor = info.tint_factor
    props.world_dome_gamma = info.gamma
    props.world_dome_saturation = info.saturation
    props.world_dome_max_bounces = DEFAULT_MAX_TOTAL
    props.world_dome_max_diffuse_bounces = DEFAULT_MAX_DIFFUSE
    props.world_dome_max_glossy_bounces = DEFAULT_MAX_GLOSSY
    props.world_dome_max_transmission_bounces = DEFAULT_MAX_TRANSMISSION
    props.world_dome_visible_camera = True
    props.world_dome_visible_diffuse = True
    props.world_dome_visible_glossy = True
    props.world_dome_visible_transmission = True
    props.world_dome_visible_volume_scatter = True
    props.world_dome_show_viewport = True
    props.world_dome_lock_selection = True


def update_world_dome_from_properties(scene: bpy.types.Scene) -> None:
    dome = ensure_world_dome_ownership(scene)
    props = getattr(scene, "light_helper_property", None)
    if dome is None or props is None:
        return
    radius = max(0.001, float(props.world_dome_radius))
    dome.scale = (radius, radius, radius)
    dome.hide_viewport = not bool(props.world_dome_show_viewport)
    dome.hide_select = bool(props.world_dome_lock_selection)
    for name in (
        "visible_camera", "visible_diffuse", "visible_glossy",
        "visible_transmission", "visible_volume_scatter",
    ):
        prop_name = f"world_dome_{name}"
        if hasattr(dome, name) and hasattr(props, prop_name):
            setattr(dome, name, bool(getattr(props, prop_name)))
    if hasattr(dome, "visible_shadow"):
        dome.visible_shadow = False

    material = dome.active_material
    if material is None:
        return
    source_color = _node_with_role(material, NODE_ROLE_SOURCE_COLOR)
    if source_color is not None:
        color = tuple(props.world_dome_color)
        source_color.outputs["Color"].default_value = (*color[:3], 1.0)
    mapping = _node_with_role(material, NODE_ROLE_MAPPING)
    if mapping is not None:
        mapping.inputs["Location"].default_value = props.world_dome_mapping_location
        mapping.inputs["Rotation"].default_value = props.world_dome_rotation
        mapping.inputs["Scale"].default_value = props.world_dome_mapping_scale
    tint = _node_with_role(material, NODE_ROLE_TINT)
    if tint is not None:
        color = tuple(props.world_dome_tint)
        tint.inputs[0].default_value = max(0.0, min(1.0, float(props.world_dome_tint_factor)))
        tint.inputs[2].default_value = (*color[:3], 1.0)
    gamma = _node_with_role(material, NODE_ROLE_GAMMA)
    if gamma is not None:
        gamma.inputs["Gamma"].default_value = max(0.001, float(props.world_dome_gamma))
    saturation = _node_with_role(material, NODE_ROLE_SATURATION)
    if saturation is not None:
        saturation.inputs["Saturation"].default_value = max(0.0, float(props.world_dome_saturation))
    emission = _node_with_role(material, NODE_ROLE_EMISSION)
    if emission is not None:
        emission.inputs["Strength"].default_value = max(0.0, float(props.world_dome_strength))
    limit_values = (
        (NODE_ROLE_MAX_TOTAL, props.world_dome_max_bounces),
        (NODE_ROLE_MAX_DIFFUSE, props.world_dome_max_diffuse_bounces),
        (NODE_ROLE_MAX_GLOSSY, props.world_dome_max_glossy_bounces),
        (NODE_ROLE_MAX_TRANSMISSION, props.world_dome_max_transmission_bounces),
    )
    for role, value in limit_values:
        node = _node_with_role(material, role)
        if node is not None:
            node.outputs[0].default_value = float(max(0, int(value)))


def _collection_has_real_items(collection: bpy.types.Collection) -> bool:
    from . import is_safe_helper_object
    if any(not is_safe_helper_object(obj) for obj in collection.objects):
        return True
    return bool(collection.children)


def _collection_has_user_items(collection: bpy.types.Collection) -> bool:
    from . import is_safe_helper_object
    if any(not is_safe_helper_object(obj) for obj in collection.objects):
        return True
    return any(
        child.get(WORLD_DOME_ROLE_KEY) != ROLE_SUN_PROXY
        for child in collection.children
    )


def _sun_record(scene: bpy.types.Scene, light_obj: bpy.types.Object):
    props = getattr(scene, "light_helper_property", None)
    if props is None:
        return None
    for record in props.world_environment_sun_records:
        if record.light == light_obj:
            return record
    return None


def _collection_user_state(collection: bpy.types.Collection):
    from . import is_safe_helper_object
    objects = []
    for index, obj in enumerate(collection.objects):
        if is_safe_helper_object(obj):
            continue
        objects.append((obj, collection.collection_objects[index].light_linking.link_state))
    children = []
    for index, child in enumerate(collection.children):
        if child.get(WORLD_DOME_ROLE_KEY) == ROLE_SUN_PROXY:
            continue
        children.append((child, collection.collection_children[index].light_linking.link_state))
    return objects, children


def _collections_equivalent(left, right) -> bool:
    if left is None or right is None:
        return left is right
    return _collection_user_state(left) == _collection_user_state(right)


def _remove_proxy(
        receiver,
        proxy,
        owner_uuid: str,
        *,
        trusted_record: bool = False,
        dome: bpy.types.Object | None = None,
) -> None:
    if proxy is None:
        return
    managed_proxy = _is_managed(proxy, owner_uuid, ROLE_SUN_PROXY)
    if not managed_proxy and not trusted_record:
        return
    if dome is not None and proxy.objects.get(dome.name) == dome:
        try:
            proxy.objects.unlink(dome)
        except RuntimeError:
            pass
    proxy_owner = proxy.get(WORLD_DOME_OWNER_KEY)
    if trusted_record and proxy_owner not in {None, owner_uuid}:
        return
    # A record proves that this used to be our proxy. If its marker was
    # damaged but it now contains user data, detach only the managed dome and
    # preserve the collection as ordinary user data.
    removable = managed_proxy or (not proxy.objects and not proxy.children)
    if not removable:
        return
    if receiver is not None and proxy.name in receiver.children:
        try:
            receiver.children.unlink(proxy)
        except RuntimeError:
            return
    if proxy.users == 0:
        bpy.data.collections.remove(proxy)


def _clear_management_marker(collection) -> None:
    if collection is None:
        return
    for key in (WORLD_DOME_OWNER_KEY, WORLD_DOME_ROLE_KEY):
        try:
            del collection[key]
        except KeyError:
            pass


def _restore_sun_record(
        scene: bpy.types.Scene,
        record,
        dome: bpy.types.Object,
) -> None:
    light_obj = record.light
    owner_uuid = dome.get(WORLD_DOME_OWNER_KEY)
    managed = record.managed_receiver
    original = record.original_receiver
    proxy = record.proxy_collection
    _remove_proxy(
        managed,
        proxy,
        owner_uuid,
        trusted_record=True,
        dome=dome,
    )
    if light_obj is None or not hasattr(light_obj, "light_linking"):
        return

    current = light_obj.light_linking.receiver_collection
    if current != managed:
        if managed is not None and managed.users == 0 and _is_managed(
                managed, owner_uuid, ROLE_SUN_RECEIVER_COPY):
            bpy.data.collections.remove(managed)
        return

    if managed is not None and (record.receiver_created or managed != original):
        expected_role = ROLE_SUN_RECEIVER if record.receiver_created else ROLE_SUN_RECEIVER_COPY
        managed_owner = managed.get(WORLD_DOME_OWNER_KEY)
        managed_role = managed.get(WORLD_DOME_ROLE_KEY)
        if (managed_owner not in {None, owner_uuid}
                or managed_role not in {None, expected_role}):
            # The collection has been explicitly claimed for other data. The
            # owner-proven proxy is removed, but the current receiver survives.
            return
        _mark_managed(managed, owner_uuid, expected_role)

    if record.receiver_created:
        if managed is not None and not _collection_has_real_items(managed):
            light_obj.light_linking.receiver_collection = None
            if managed.users == 0 and _is_managed(managed, owner_uuid, ROLE_SUN_RECEIVER):
                bpy.data.collections.remove(managed)
        elif managed is not None and _collection_has_user_items(managed):
            _clear_management_marker(managed)
        return

    if managed is not None and managed != original and _collections_equivalent(managed, original):
        light_obj.light_linking.receiver_collection = original
        if managed.users == 0 and _is_managed(managed, owner_uuid, ROLE_SUN_RECEIVER_COPY):
            bpy.data.collections.remove(managed)
    elif managed is not None and managed != original:
        # Preserve edits made while converted. It is now ordinary user data.
        _clear_management_marker(managed)
    elif (managed is not None
            and managed == original
            and managed.get(WORLD_DOME_ROLE_KEY) == ROLE_SUN_RECEIVER
            and not _collection_has_real_items(managed)):
        light_obj.light_linking.receiver_collection = None


def remove_sun_exclusions(
        scene: bpy.types.Scene,
        dome: bpy.types.Object | None = None,
        sun_objects=None,
) -> None:
    scene_dome = ensure_world_dome_ownership(scene)
    if scene_dome is not None and (
            dome is None or not _object_is_in_scene(scene, dome)
            or dome.get(WORLD_DOME_OWNER_KEY) != scene_dome.get(WORLD_DOME_OWNER_KEY)):
        dome = scene_dome
    if dome is None:
        return
    owner_uuid = dome.get(WORLD_DOME_OWNER_KEY)
    allowed = None if sun_objects is None else set(sun_objects)
    records = scene.light_helper_property.world_environment_sun_records
    for index in reversed(range(len(records))):
        record = records[index]
        light_obj = record.light
        if allowed is not None and light_obj not in allowed:
            continue
        managed = record.managed_receiver
        proxy = record.proxy_collection
        _restore_sun_record(scene, record, dome)
        records.remove(index)
        if proxy is not None and proxy.users == 0 and _is_managed(proxy, owner_uuid, ROLE_SUN_PROXY):
            bpy.data.collections.remove(proxy)
        if (managed is not None and managed.users == 0
                and managed.get(WORLD_DOME_ROLE_KEY) in {ROLE_SUN_RECEIVER, ROLE_SUN_RECEIVER_COPY}):
            bpy.data.collections.remove(managed)

    for light_obj in list(scene.objects):
        if light_obj.type != "LIGHT" or light_obj.data is None or light_obj.data.type != "SUN":
            continue
        if allowed is not None and light_obj not in allowed:
            continue
        if not hasattr(light_obj, "light_linking"):
            continue
        # Recovery path for files saved while the extension was disabled.
        receiver = light_obj.light_linking.receiver_collection
        if receiver is None:
            continue
        proxies = [
            child for child in receiver.children
            if _is_managed(child, owner_uuid, ROLE_SUN_PROXY)
        ]
        for proxy in proxies:
            _remove_proxy(receiver, proxy, owner_uuid)
        if (not _collection_has_real_items(receiver)
                and receiver.get(WORLD_DOME_ROLE_KEY) == ROLE_SUN_RECEIVER):
            light_obj.light_linking.receiver_collection = None
            if receiver.users == 0:
                bpy.data.collections.remove(receiver)


def ensure_sun_exclusions(
        scene: bpy.types.Scene,
        dome: bpy.types.Object | None = None,
        sun_objects=None,
) -> int:
    scene_dome = ensure_world_dome_ownership(scene)
    if scene_dome is not None and (
            dome is None or not _object_is_in_scene(scene, dome)
            or dome.get(WORLD_DOME_OWNER_KEY) != scene_dome.get(WORLD_DOME_OWNER_KEY)):
        dome = scene_dome
    if dome is None:
        return 0
    remove_duplicate_managed_domes(scene)
    owner_uuid = dome.get(WORLD_DOME_OWNER_KEY)
    if sun_objects is None:
        sun_objects = [
            obj for obj in scene.objects
            if obj.type == "LIGHT" and obj.data is not None and obj.data.type == "SUN"
        ]
    count = 0
    for light_obj in sun_objects:
        if light_obj is None or light_obj.name not in scene.objects:
            continue
        if light_obj.type != "LIGHT" or light_obj.data is None or light_obj.data.type != "SUN":
            continue
        if not hasattr(light_obj, "light_linking"):
            continue
        records = scene.light_helper_property.world_environment_sun_records
        record_indices = [
            index for index, item in enumerate(records)
            if item.light == light_obj
        ]
        collection = light_obj.light_linking.receiver_collection

        # Fast, idempotent repair path for the canonical record. Missing links,
        # objects, markers, and even the proxy itself are repaired in place.
        if len(record_indices) == 1:
            record = records[record_indices[0]]
            collection_owner = collection.get(WORLD_DOME_OWNER_KEY) if collection is not None else None
            collection_role = collection.get(WORLD_DOME_ROLE_KEY) if collection is not None else None
            receiver_can_repair = True
            if record.receiver_created:
                receiver_can_repair = (
                    collection_owner in {None, owner_uuid}
                    and collection_role in {None, ROLE_SUN_RECEIVER}
                )
            elif collection is not None and collection != record.original_receiver:
                receiver_can_repair = (
                    collection_owner in {None, owner_uuid}
                    and collection_role in {None, ROLE_SUN_RECEIVER_COPY}
                )
            if (collection is not None
                    and record.managed_receiver == collection
                    and receiver_can_repair):
                if record.receiver_created:
                    _mark_managed(collection, owner_uuid, ROLE_SUN_RECEIVER)
                elif collection != record.original_receiver:
                    _mark_managed(collection, owner_uuid, ROLE_SUN_RECEIVER_COPY)

                proxy = record.proxy_collection
                if not _is_managed(proxy, owner_uuid, ROLE_SUN_PROXY):
                    _remove_proxy(
                        collection,
                        proxy,
                        owner_uuid,
                        trusted_record=True,
                        dome=dome,
                    )
                    proxy = bpy.data.collections.new(
                        f"World Dome Proxy [{owner_uuid[:8]}] for {light_obj.name}"
                    )
                    _mark_managed(proxy, owner_uuid, ROLE_SUN_PROXY)
                    record.proxy_collection = proxy
                if proxy.name not in collection.children:
                    collection.children.link(proxy)
                if proxy.objects.get(dome.name) != dome:
                    proxy.objects.link(dome)
                for extra in list(collection.children):
                    if extra != proxy and _is_managed(extra, owner_uuid, ROLE_SUN_PROXY):
                        _remove_proxy(collection, extra, owner_uuid, dome=dome)
                from . import _set_item_link_state
                _set_item_link_state(collection, proxy, "EXCLUDE")
                count += 1
                continue

        # Receiver replacement, deleted managed data, and historical duplicate
        # records all converge here. Retire the old owner-proven artifacts, then
        # rebuild exactly one record against the receiver the user currently
        # selected. If a deleted receiver copy left only its original pointer,
        # that original becomes the safe reconstruction base.
        fallback_original = None
        for index in record_indices:
            original = records[index].original_receiver
            if fallback_original is None and original is not None:
                fallback_original = original
        for index in reversed(record_indices):
            record = records[index]
            managed = record.managed_receiver
            proxy = record.proxy_collection
            _restore_sun_record(scene, record, dome)
            records.remove(index)
            if proxy is not None and proxy.users == 0 and _is_managed(
                    proxy, owner_uuid, ROLE_SUN_PROXY):
                bpy.data.collections.remove(proxy)
            if (managed is not None and managed.users == 0
                    and _is_managed(managed, owner_uuid)
                    and managed.get(WORLD_DOME_ROLE_KEY) in {
                        ROLE_SUN_RECEIVER, ROLE_SUN_RECEIVER_COPY,
                    }):
                bpy.data.collections.remove(managed)

        collection = light_obj.light_linking.receiver_collection
        if collection is None and fallback_original is not None:
            try:
                light_obj.light_linking.receiver_collection = fallback_original
                collection = fallback_original
            except (ReferenceError, RuntimeError, TypeError, ValueError):
                collection = None

        original = collection
        managed = collection
        created = False
        proxy = None
        record_index = None
        try:
            if managed is None:
                managed = bpy.data.collections.new(f"World Dome Exclusion for {light_obj.name}")
                _mark_managed(managed, owner_uuid, ROLE_SUN_RECEIVER)
                light_obj.light_linking.receiver_collection = managed
                created = True
            elif managed.users > 1 or managed.library is not None or not managed.is_editable:
                managed = managed.copy()
                managed.name = f"{original.name} for {light_obj.name}"
                _mark_managed(managed, owner_uuid, ROLE_SUN_RECEIVER_COPY)
                light_obj.light_linking.receiver_collection = managed

            proxy = bpy.data.collections.new(f"World Dome Proxy [{owner_uuid[:8]}] for {light_obj.name}")
            _mark_managed(proxy, owner_uuid, ROLE_SUN_PROXY)
            proxy.objects.link(dome)
            managed.children.link(proxy)
            from . import _set_item_link_state
            _set_item_link_state(managed, proxy, "EXCLUDE")

            record = scene.light_helper_property.world_environment_sun_records.add()
            record_index = len(scene.light_helper_property.world_environment_sun_records) - 1
            record.light = light_obj
            record.original_receiver = original
            record.managed_receiver = managed
            record.proxy_collection = proxy
            record.receiver_created = created
            count += 1
        except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
            if record_index is not None:
                scene.light_helper_property.world_environment_sun_records.remove(record_index)
            if proxy is not None:
                if managed is not None and proxy.name in managed.children:
                    try:
                        managed.children.unlink(proxy)
                    except RuntimeError:
                        pass
                if proxy.users == 0 and _is_managed(proxy, owner_uuid, ROLE_SUN_PROXY):
                    bpy.data.collections.remove(proxy)
            if managed is not None and managed != original and light_obj.light_linking.receiver_collection == managed:
                light_obj.light_linking.receiver_collection = original
            if managed is not None and managed != original and managed.users == 0 and _is_managed(
                    managed, owner_uuid):
                bpy.data.collections.remove(managed)
            continue
    return count


def count_synced_suns(scene: bpy.types.Scene, dome: bpy.types.Object | None = None) -> tuple[int, int]:
    dome = dome or get_world_dome(scene)
    total = 0
    synced = 0
    if dome is None:
        return synced, total
    for obj in scene.objects:
        if obj.type != "LIGHT" or obj.data is None or obj.data.type != "SUN":
            continue
        total += 1
        collection = obj.light_linking.receiver_collection if hasattr(obj, "light_linking") else None
        if collection is None:
            continue
        for index, child in enumerate(collection.children):
            if not _is_managed(child, dome.get(WORLD_DOME_OWNER_KEY), ROLE_SUN_PROXY):
                continue
            if dome.name not in child.objects:
                continue
            if collection.collection_children[index].light_linking.link_state == "EXCLUDE":
                synced += 1
                break
    return synced, total


def convert_world_environment(scene: bpy.types.Scene) -> tuple[bpy.types.Object | None, str]:
    if scene is None or scene.render.engine != 'CYCLES':
        return None, "UNSUPPORTED_ENGINE"
    existing = ensure_world_dome_ownership(scene)
    if existing is not None:
        remove_duplicate_managed_domes(scene)
        ensure_sun_exclusions(scene, existing)
        update_world_dome_from_properties(scene)
        from ..handlers import sync_world_environment_sun_handler
        sync_world_environment_sun_handler(True)
        return existing, "EXISTS"
    info = find_world_environment(scene)
    if not info.has_source:
        return None, "NO_SOURCE"

    owner_uuid = _scene_owner_uuid(scene, create=True)
    props = scene.light_helper_property
    original_world = scene.world
    material = None
    mesh = None
    dome = None
    dome_collection = None
    fallback_world = None
    try:
        material = _create_dome_material(owner_uuid, info)
        mesh = _make_sphere_mesh(f"LH World Environment Mesh [{owner_uuid[:8]}]", owner_uuid)
        dome = bpy.data.objects.new(f"LH World Environment [{owner_uuid[:8]}]", mesh)
        _mark_managed(dome, owner_uuid, ROLE_DOME_OBJECT)
        dome[WORLD_DOME_OWNER_SCENE_POINTER_KEY] = scene
        dome[WORLD_DOME_SOURCE_WORLD_KEY] = original_world.name_full
        dome[WORLD_DOME_SOURCE_WORLD_POINTER_KEY] = original_world
        dome[WORLD_DOME_SOURCE_TYPE_KEY] = info.source_type
        dome[WORLD_DOME_SOURCE_IMAGE_KEY] = info.image.name_full if info.image is not None else ""
        dome.data.materials.append(material)
        dome.display_type = "WIRE"
        dome.show_name = True
        dome_collection = _find_or_create_dome_collection(scene, owner_uuid)
        dome_collection.objects.link(dome)

        total, inward = dome_face_stats(dome)
        if total == 0 or total != inward:
            raise RuntimeError("The generated environment sphere failed its inward-normal validation")

        _set_scene_properties_from_info(scene, info)
        world_visibility = getattr(original_world, "cycles_visibility", None)
        if world_visibility is not None:
            props.world_dome_visible_camera = bool(
                getattr(world_visibility, "camera", True)
                and not scene.render.film_transparent
            )
            props.world_dome_visible_diffuse = bool(getattr(world_visibility, "diffuse", True))
            props.world_dome_visible_glossy = bool(getattr(world_visibility, "glossy", True))
            props.world_dome_visible_transmission = bool(getattr(world_visibility, "transmission", True))
            props.world_dome_visible_volume_scatter = bool(getattr(world_visibility, "scatter", True))
        elif scene.render.film_transparent:
            props.world_dome_visible_camera = False

        fallback_world = _create_fallback_world(owner_uuid, original_world)
        props.world_environment_original_world = original_world
        props.world_environment_managed_world = fallback_world
        props.world_environment_dome = dome
        scene.world = fallback_world
        update_world_dome_from_properties(scene)
        ensure_sun_exclusions(scene, dome)
        from ..handlers import sync_world_environment_sun_handler
        sync_world_environment_sun_handler(True)
        return dome, "CONVERTED"
    except Exception:
        if dome is not None:
            try:
                remove_sun_exclusions(scene, dome)
            except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
                pass
        if original_world is not None:
            scene.world = original_world
        props.world_environment_sun_records.clear()
        props.world_environment_dome = None
        props.world_environment_original_world = None
        props.world_environment_managed_world = None
        if dome is not None:
            bpy.data.objects.remove(dome, do_unlink=True)
        if mesh is not None and mesh.users == 0:
            bpy.data.meshes.remove(mesh)
        if material is not None and material.users == 0:
            bpy.data.materials.remove(material)
        if fallback_world is not None and fallback_world.users == 0:
            bpy.data.worlds.remove(fallback_world)
        if (dome_collection is not None
                and not dome_collection.objects
                and not dome_collection.children
                and _is_managed(dome_collection, owner_uuid, ROLE_DOME_COLLECTION)):
            if dome_collection.name in scene.collection.children:
                scene.collection.children.unlink(dome_collection)
            if dome_collection.users == 0:
                bpy.data.collections.remove(dome_collection)
        raise


def _recover_original_world(scene: bpy.types.Scene, dome: bpy.types.Object | None):
    props = getattr(scene, "light_helper_property", None)
    world = getattr(props, "world_environment_original_world", None) if props is not None else None
    if world is not None:
        return world
    if dome is not None:
        world_pointer = dome.get(WORLD_DOME_SOURCE_WORLD_POINTER_KEY)
        if isinstance(world_pointer, bpy.types.World):
            return world_pointer
        name = dome.get(WORLD_DOME_SOURCE_WORLD_KEY)
        if isinstance(name, str) and name:
            return bpy.data.worlds.get(name)
    return None


def _other_environment_consumers(
        scene: bpy.types.Scene,
        dome: bpy.types.Object,
) -> list[bpy.types.Scene]:
    # Object removal is global in Blender. Any other Scene membership must
    # block restoration, even if that Scene is not a LightHelper-managed copy.
    return [
        other for other in bpy.data.scenes
        if other != scene and _object_is_in_scene(other, dome)
    ]


def restore_world_environment(scene: bpy.types.Scene) -> tuple[bool, str]:
    dome = ensure_world_dome_ownership(scene)
    if dome is None:
        return False, "NOT_CONVERTED"
    if _other_environment_consumers(scene, dome):
        # Copy-on-write normally isolates Scene.copy() before this point. If a
        # user moved the locked dome into a shared collection and isolation is
        # impossible, fail closed instead of deleting another scene's data.
        return False, "SHARED_SCENE_DATA"
    remove_duplicate_managed_domes(scene)
    dome = ensure_world_dome_ownership(scene)
    if dome is None:
        return False, "NOT_CONVERTED"
    owner_uuid = dome.get(WORLD_DOME_OWNER_KEY)
    props = scene.light_helper_property
    original_world = _recover_original_world(scene, dome)
    managed_world = props.world_environment_managed_world
    if managed_world is None and _is_managed(scene.world, owner_uuid, ROLE_FALLBACK_WORLD):
        managed_world = scene.world

    remove_sun_exclusions(scene, dome)
    try:
        from . import restore_light_linking
        if hasattr(dome, "light_linking") and (
                dome.light_linking.receiver_collection is not None
                or dome.light_linking.blocker_collection is not None):
            restore_light_linking(dome)
    except (AttributeError, ReferenceError, RuntimeError):
        pass

    material = dome.active_material
    mesh = dome.data if dome.type == "MESH" else None
    collection_candidates = [
        collection for collection in dome.users_collection
        if _is_managed(collection, owner_uuid, ROLE_DOME_COLLECTION)
    ]
    bpy.data.objects.remove(dome, do_unlink=True)
    if mesh is not None and mesh.users == 0 and _is_managed(mesh, owner_uuid, ROLE_DOME_MESH):
        bpy.data.meshes.remove(mesh)
    if material is not None and material.users == 0 and _is_managed(material, owner_uuid, ROLE_DOME_MATERIAL):
        bpy.data.materials.remove(material)
    for collection in collection_candidates:
        if not collection.objects and not collection.children:
            if collection.name in scene.collection.children:
                scene.collection.children.unlink(collection)
            if collection.users == 0:
                bpy.data.collections.remove(collection)

    scene.world = original_world
    props.world_environment_dome = None
    props.world_environment_original_world = None
    props.world_environment_managed_world = None
    if managed_world is not None and managed_world.users == 0 and _is_managed(
            managed_world, owner_uuid, ROLE_FALLBACK_WORLD):
        bpy.data.worlds.remove(managed_world)
    try:
        del scene[WORLD_DOME_SCENE_UUID_KEY]
    except KeyError:
        pass
    from ..handlers import sync_world_environment_sun_handler
    sync_world_environment_sun_handler()
    return True, "RESTORED" if original_world is not None else "RESTORED_NO_WORLD"


def remove_duplicate_managed_domes(scene: bpy.types.Scene) -> int:
    owner_uuid = _scene_owner_uuid(scene)
    primary = get_world_dome(scene)
    if owner_uuid is None or primary is None:
        return 0
    removed = 0
    for obj in list(scene.objects):
        if obj == primary or not _is_managed(obj, owner_uuid, ROLE_DOME_OBJECT):
            continue
        if any(
                other != scene and _object_is_in_scene(other, obj)
                for other in bpy.data.scenes):
            # Scene.copy() can briefly expose the same managed object in two
            # scenes. Never turn duplicate repair into a global deletion.
            continue
        mesh = obj.data if obj.type == "MESH" else None
        material = obj.active_material
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh is not None and mesh.users == 0 and _is_managed(mesh, owner_uuid, ROLE_DOME_MESH):
            bpy.data.meshes.remove(mesh)
        if material is not None and material.users == 0 and _is_managed(material, owner_uuid, ROLE_DOME_MATERIAL):
            bpy.data.materials.remove(material)
        removed += 1
    return removed


def is_eevee_engine(engine: str) -> bool:
    return engine in {"BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"}


_syncing_suns = False
_sun_sync_engine_by_scene = {}


def sync_world_environment_suns_from_depsgraph(scene, depsgraph) -> None:
    global _syncing_suns
    if _syncing_suns or scene is None:
        return
    scene_key = scene.as_pointer()
    engine = scene.render.engine
    previous_engine = _sun_sync_engine_by_scene.get(scene_key)
    _sun_sync_engine_by_scene[scene_key] = engine
    if engine != 'CYCLES':
        return
    dome = get_world_dome(scene)
    if dome is None or not is_world_dome_owned_by_scene(scene, dome):
        return
    if previous_engine != 'CYCLES':
        _syncing_suns = True
        try:
            ensure_sun_exclusions(scene, dome)
        finally:
            _syncing_suns = False
        return
    candidates = []
    for update in depsgraph.updates:
        id_ref = update.id
        if isinstance(id_ref, bpy.types.Object):
            obj = id_ref.original if id_ref.is_evaluated else id_ref
            if obj and obj.type == "LIGHT" and obj.data is not None and obj.data.type == "SUN":
                candidates.append(obj)
        elif isinstance(id_ref, bpy.types.Light) and id_ref.type == "SUN":
            candidates.extend(
                obj for obj in scene.objects
                if obj.type == "LIGHT" and obj.data == id_ref
            )
    if not candidates:
        return
    unique = list(dict.fromkeys(candidates))
    _syncing_suns = True
    try:
        ensure_sun_exclusions(scene, dome, unique)
    finally:
        _syncing_suns = False


def clear_world_environment_sync_state() -> None:
    _sun_sync_engine_by_scene.clear()


def dome_face_stats(dome: bpy.types.Object) -> tuple[int, int]:
    if dome is None or dome.type != "MESH":
        return 0, 0
    total = len(dome.data.polygons)
    inward = sum(
        1 for polygon in dome.data.polygons
        if polygon.center.dot(polygon.normal) < 0.0
    )
    return total, inward
