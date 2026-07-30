"""Managed LightHelper studio-shaping objects.

Every created datablock carries explicit provenance.  Cleanup is deliberately
conservative: only local, owner-matching datablocks are removed, and shared
mesh/material data survives until it is orphaned.
"""

from math import cos, pi, sin
from uuid import uuid4

import bpy


STUDIO_SCENE_UUID_KEY = "light_helper_studio_scene_uuid"
STUDIO_MANAGED_KEY = "light_helper_studio_managed"
STUDIO_OWNER_KEY = "light_helper_studio_owner"
STUDIO_ROLE_KEY = "light_helper_studio_role"
STUDIO_COLLECTION_NAME = "LightHelper Studio"

ROLE_COLLECTION = "STUDIO_COLLECTION"
ROLE_SCRIM_OBJECT = "SCRIM_OBJECT"
ROLE_SCRIM_MESH = "SCRIM_MESH"
ROLE_SCRIM_MATERIAL = "SCRIM_MATERIAL"
ROLE_FLAG_OBJECT = "FLAG_OBJECT"
ROLE_FLAG_MESH = "FLAG_MESH"
ROLE_FLAG_MATERIAL = "FLAG_MATERIAL"
ROLE_REFLECTOR_OBJECT = "REFLECTOR_OBJECT"
ROLE_REFLECTOR_MESH = "REFLECTOR_MESH"
ROLE_REFLECTOR_MATERIAL = "REFLECTOR_MATERIAL"
ROLE_TRACK_TARGET = "TRACK_TARGET"
ROLE_TRACK_CONSTRAINT = "TRACK_CONSTRAINT"
TRACK_CONSTRAINT_PREFIX = "LightHelper Track Target ["

STUDIO_OBJECT_ROLES = {
    ROLE_SCRIM_OBJECT,
    ROLE_FLAG_OBJECT,
    ROLE_REFLECTOR_OBJECT,
}


class StudioEngineError(RuntimeError):
    pass


def _mark_managed(id_block, owner_uuid: str, role: str) -> None:
    id_block[STUDIO_MANAGED_KEY] = True
    id_block[STUDIO_OWNER_KEY] = owner_uuid
    id_block[STUDIO_ROLE_KEY] = role


def _mark_track_constraint(constraint, owner_uuid: str) -> None:
    # Blender constraints do not support IDProperties in 4.2.  A complete UUID
    # in the reserved name is the ownership token; deletion also verifies the
    # constraint type before trusting it.
    constraint.name = f"{TRACK_CONSTRAINT_PREFIX}{owner_uuid}]"


def _track_constraint_owner(constraint) -> str | None:
    name = getattr(constraint, "name", "")
    if getattr(constraint, "type", None) != 'TRACK_TO' or not name.startswith(TRACK_CONSTRAINT_PREFIX):
        return None
    if not name.endswith(']'):
        return None
    owner_uuid = name[len(TRACK_CONSTRAINT_PREFIX):-1]
    if len(owner_uuid) != 32 or any(character not in "0123456789abcdef" for character in owner_uuid):
        return None
    return owner_uuid


def is_managed(id_block, owner_uuid: str | None = None, role: str | None = None) -> bool:
    if id_block is None:
        return False
    try:
        if not bool(id_block.get(STUDIO_MANAGED_KEY)):
            return False
        if owner_uuid is not None and id_block.get(STUDIO_OWNER_KEY) != owner_uuid:
            return False
        return role is None or id_block.get(STUDIO_ROLE_KEY) == role
    except (ReferenceError, RuntimeError, TypeError):
        return False


def is_studio_object(obj) -> bool:
    return bool(obj is not None and is_managed(obj) and obj.get(STUDIO_ROLE_KEY) in STUDIO_OBJECT_ROLES)


def studio_kind(obj) -> str | None:
    if not is_studio_object(obj):
        return None
    role = obj.get(STUDIO_ROLE_KEY)
    return {
        ROLE_SCRIM_OBJECT: "SCRIM",
        ROLE_FLAG_OBJECT: "FLAG",
        ROLE_REFLECTOR_OBJECT: "REFLECTOR",
    }.get(role)


def _scene_owner_uuid(scene, create: bool = False) -> str | None:
    owner_uuid = scene.get(STUDIO_SCENE_UUID_KEY)
    if isinstance(owner_uuid, str) and owner_uuid:
        duplicate = any(
            other != scene and other.get(STUDIO_SCENE_UUID_KEY) == owner_uuid
            for other in bpy.data.scenes
        )
        if not duplicate:
            return owner_uuid
    if not create or not getattr(scene, "is_editable", True):
        return None
    owner_uuid = uuid4().hex
    scene[STUDIO_SCENE_UUID_KEY] = owner_uuid
    return owner_uuid


def ensure_studio_collection(scene):
    scene_owner = _scene_owner_uuid(scene, create=True)
    if scene_owner is None:
        raise RuntimeError("The scene is read-only")
    for collection in bpy.data.collections:
        if is_managed(collection, scene_owner, ROLE_COLLECTION):
            if collection.name not in scene.collection.children:
                scene.collection.children.link(collection)
            return collection
    collection = bpy.data.collections.new(STUDIO_COLLECTION_NAME)
    _mark_managed(collection, scene_owner, ROLE_COLLECTION)
    scene.collection.children.link(collection)
    return collection


def _unit_panel_mesh(name: str, shape: str, thickness: float = 0.0):
    shape = shape.upper()
    thickness = max(0.0, float(thickness))
    mesh = bpy.data.meshes.new(name)
    if shape == 'RECTANGLE':
        if thickness > 0.0:
            z = thickness * 0.5
            vertices = [
                (-0.5, -0.5, -z), (0.5, -0.5, -z),
                (0.5, 0.5, -z), (-0.5, 0.5, -z),
                (-0.5, -0.5, z), (0.5, -0.5, z),
                (0.5, 0.5, z), (-0.5, 0.5, z),
            ]
            faces = [
                (0, 3, 2, 1), (4, 5, 6, 7),
                (0, 1, 5, 4), (1, 2, 6, 5),
                (2, 3, 7, 6), (3, 0, 4, 7),
            ]
        else:
            vertices = [(-0.5, -0.5, 0.0), (0.5, -0.5, 0.0), (0.5, 0.5, 0.0), (-0.5, 0.5, 0.0)]
            faces = [(0, 1, 2, 3)]
    elif shape == 'ELLIPSE':
        segments = 64
        if thickness > 0.0:
            z = thickness * 0.5
            bottom = [(0.5 * cos(index * 2.0 * pi / segments), 0.5 * sin(index * 2.0 * pi / segments), -z)
                      for index in range(segments)]
            top = [(x, y, z) for x, y, _z in bottom]
            vertices = bottom + top
            faces = [tuple(reversed(range(segments))), tuple(range(segments, segments * 2))]
            faces.extend(
                (index, (index + 1) % segments, (index + 1) % segments + segments, index + segments)
                for index in range(segments)
            )
        else:
            vertices = [(0.5 * cos(index * 2.0 * pi / segments),
                         0.5 * sin(index * 2.0 * pi / segments), 0.0)
                        for index in range(segments)]
            faces = [tuple(range(segments))]
    else:
        bpy.data.meshes.remove(mesh)
        raise ValueError(f"Unsupported studio shape: {shape}")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    return mesh


def _new_node(nodes, node_type: str, name: str, owner_uuid: str, role: str):
    node = nodes.new(node_type)
    node.name = name
    _mark_managed(node, owner_uuid, role)
    return node


def _math_node(nodes, operation: str, name: str, owner_uuid: str):
    node = _new_node(nodes, "ShaderNodeMath", name, owner_uuid, f"SCRIM_NODE_{name.upper().replace(' ', '_')}")
    node.operation = operation
    return node


def _build_scrim_material(
        owner_uuid: str,
        shape: str,
        color,
        strength: float,
        exposure: float,
        feather: float,
        gradient_direction: str,
        gradient_amount: float):
    material = bpy.data.materials.new(f"LH Scrim Material [{owner_uuid[:8]}]")
    _mark_managed(material, owner_uuid, ROLE_SCRIM_MATERIAL)
    material.use_nodes = True
    material.diffuse_color = (*tuple(color)[:3], 1.0)
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    output = _new_node(nodes, "ShaderNodeOutputMaterial", "Scrim Output", owner_uuid, "SCRIM_NODE_OUTPUT")
    emission = _new_node(nodes, "ShaderNodeEmission", "Scrim Emission", owner_uuid, "SCRIM_NODE_EMISSION")
    emission.inputs["Color"].default_value = (*tuple(color)[:3], 1.0)
    texcoord = _new_node(nodes, "ShaderNodeTexCoord", "Scrim Coordinates", owner_uuid, "SCRIM_NODE_COORDINATES")
    separate = _new_node(nodes, "ShaderNodeSeparateXYZ", "Scrim Separate", owner_uuid, "SCRIM_NODE_SEPARATE")
    links.new(texcoord.outputs["Generated"], separate.inputs["Vector"])

    centered = []
    for axis in ("X", "Y"):
        subtract = _math_node(nodes, 'SUBTRACT', f"{axis} Center", owner_uuid)
        subtract.inputs[1].default_value = 0.5
        absolute = _math_node(nodes, 'ABSOLUTE', f"{axis} Absolute", owner_uuid)
        doubled = _math_node(nodes, 'MULTIPLY', f"{axis} Radius", owner_uuid)
        doubled.inputs[1].default_value = 2.0
        links.new(separate.outputs[axis], subtract.inputs[0])
        links.new(subtract.outputs[0], absolute.inputs[0])
        links.new(absolute.outputs[0], doubled.inputs[0])
        centered.append(doubled.outputs[0])

    if shape.upper() == 'ELLIPSE':
        squares = []
        for index, socket in enumerate(centered):
            square = _math_node(nodes, 'MULTIPLY', f"Radius Square {index}", owner_uuid)
            links.new(socket, square.inputs[0])
            links.new(socket, square.inputs[1])
            squares.append(square.outputs[0])
        add_radius = _math_node(nodes, 'ADD', "Radius Sum", owner_uuid)
        radius = _math_node(nodes, 'SQRT', "Radial Distance", owner_uuid)
        links.new(squares[0], add_radius.inputs[0])
        links.new(squares[1], add_radius.inputs[1])
        links.new(add_radius.outputs[0], radius.inputs[0])
        edge_source = radius.outputs[0]
        radial_source = radius.outputs[0]
    else:
        maximum = _math_node(nodes, 'MAXIMUM', "Rectangle Radius", owner_uuid)
        links.new(centered[0], maximum.inputs[0])
        links.new(centered[1], maximum.inputs[1])
        edge_source = maximum.outputs[0]
        radial_source = maximum.outputs[0]

    edge = _new_node(nodes, "ShaderNodeMapRange", "Scrim Feather", owner_uuid, "SCRIM_NODE_FEATHER")
    edge.clamp = True
    feather = max(1.0e-6, min(1.0, float(feather)))
    edge.inputs["From Min"].default_value = 1.0 - feather
    edge.inputs["From Max"].default_value = 1.0
    edge.inputs["To Min"].default_value = 1.0
    edge.inputs["To Max"].default_value = 0.0
    links.new(edge_source, edge.inputs["Value"])

    gradient_direction = gradient_direction.upper()
    if gradient_direction == 'X':
        gradient_source = separate.outputs["X"]
    elif gradient_direction == 'Y':
        gradient_source = separate.outputs["Y"]
    elif gradient_direction == 'RADIAL':
        gradient_source = radial_source
    else:
        gradient_source = None
    if gradient_source is not None and gradient_amount > 0.0:
        gradient_multiply = _math_node(nodes, 'MULTIPLY', "Gradient Amount", owner_uuid)
        gradient_multiply.inputs[1].default_value = -max(0.0, min(1.0, gradient_amount))
        gradient = _math_node(nodes, 'ADD', "Gradient", owner_uuid)
        gradient.inputs[1].default_value = 1.0
        links.new(gradient_source, gradient_multiply.inputs[0])
        links.new(gradient_multiply.outputs[0], gradient.inputs[0])
        mask = _math_node(nodes, 'MULTIPLY', "Scrim Mask", owner_uuid)
        links.new(edge.outputs["Result"], mask.inputs[0])
        links.new(gradient.outputs[0], mask.inputs[1])
        mask_socket = mask.outputs[0]
    else:
        mask_socket = edge.outputs["Result"]

    strength_node = _math_node(nodes, 'MULTIPLY', "Scrim Strength", owner_uuid)
    strength_node.inputs[1].default_value = max(0.0, float(strength)) * (2.0 ** float(exposure))
    links.new(mask_socket, strength_node.inputs[0])
    links.new(strength_node.outputs[0], emission.inputs["Strength"])
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def _build_diffuse_material(owner_uuid: str, role: str, name: str, color, roughness: float, reflectance: float = 1.0):
    material = bpy.data.materials.new(name)
    _mark_managed(material, owner_uuid, role)
    material.use_nodes = True
    rgb = tuple(max(0.0, min(1.0, float(component) * float(reflectance))) for component in tuple(color)[:3])
    material.diffuse_color = (*rgb, 1.0)
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = _new_node(nodes, "ShaderNodeOutputMaterial", "Studio Output", owner_uuid, "STUDIO_NODE_OUTPUT")
    diffuse = _new_node(nodes, "ShaderNodeBsdfDiffuse", "Studio Diffuse", owner_uuid, "STUDIO_NODE_DIFFUSE")
    diffuse.inputs["Color"].default_value = (*rgb, 1.0)
    diffuse.inputs["Roughness"].default_value = max(0.0, min(1.0, float(roughness)))
    links.new(diffuse.outputs["BSDF"], output.inputs["Surface"])
    return material


def _create_studio_object(scene, name: str, shape: str, width: float, height: float, thickness: float,
                          object_role: str, mesh_role: str):
    owner_uuid = uuid4().hex
    mesh = None
    obj = None
    try:
        mesh = _unit_panel_mesh(f"{name} Mesh [{owner_uuid[:8]}]", shape, thickness)
        _mark_managed(mesh, owner_uuid, mesh_role)
        obj = bpy.data.objects.new(f"{name} [{owner_uuid[:8]}]", mesh)
        _mark_managed(obj, owner_uuid, object_role)
        obj.scale = (max(0.001, float(width)), max(0.001, float(height)), 1.0)
        obj["light_helper_studio_shape"] = shape.upper()
        obj["light_helper_studio_width"] = max(0.001, float(width))
        obj["light_helper_studio_height"] = max(0.001, float(height))
        obj["light_helper_studio_thickness"] = max(0.0, float(thickness))
        ensure_studio_collection(scene).objects.link(obj)
        return obj, owner_uuid
    except BaseException:
        if obj is not None and obj.users == 0:
            bpy.data.objects.remove(obj)
        if mesh is not None and mesh.users == 0 and is_managed(mesh, owner_uuid, mesh_role):
            bpy.data.meshes.remove(mesh)
        raise


def _remove_owned_orphans(owner_uuid: str) -> None:
    for material in list(bpy.data.materials):
        if material.users == 0 and is_managed(material, owner_uuid):
            bpy.data.materials.remove(material)
    for mesh in list(bpy.data.meshes):
        if mesh.users == 0 and is_managed(mesh, owner_uuid):
            bpy.data.meshes.remove(mesh)


def create_scrim(
        scene,
        *,
        shape: str = 'RECTANGLE',
        width: float = 2.0,
        height: float = 2.0,
        feather: float = 0.2,
        gradient_direction: str = 'NONE',
        gradient_amount: float = 0.5,
        color=(1.0, 1.0, 1.0),
        strength: float = 10.0,
        exposure: float = 0.0,
        visible_camera: bool = False):
    if scene.render.engine != 'CYCLES':
        raise StudioEngineError("Scrims require Cycles")
    obj, owner_uuid = _create_studio_object(
        scene, "LH Scrim", shape, width, height, 0.0, ROLE_SCRIM_OBJECT, ROLE_SCRIM_MESH,
    )
    try:
        material = _build_scrim_material(
            owner_uuid, shape, color, strength, exposure, feather, gradient_direction, gradient_amount,
        )
        obj.data.materials.append(material)
        obj["light_helper_scrim_feather"] = max(0.0, min(1.0, float(feather)))
        obj["light_helper_scrim_gradient"] = gradient_direction.upper()
        obj["light_helper_scrim_gradient_amount"] = max(0.0, min(1.0, float(gradient_amount)))
        obj["light_helper_scrim_color"] = tuple(color)[:3]
        obj["light_helper_scrim_strength"] = max(0.0, float(strength))
        obj["light_helper_scrim_exposure"] = float(exposure)
        if hasattr(obj, "visible_camera"):
            obj.visible_camera = bool(visible_camera)
        return obj
    except BaseException:
        remove_studio_object(obj)
        _remove_owned_orphans(owner_uuid)
        raise


def create_flag(
        scene,
        *,
        shape: str = 'RECTANGLE',
        width: float = 2.0,
        height: float = 2.0,
        thickness: float = 0.02,
        color=(0.005, 0.005, 0.005),
        visible_camera: bool = False):
    obj, owner_uuid = _create_studio_object(
        scene, "LH Flag", shape, width, height, thickness, ROLE_FLAG_OBJECT, ROLE_FLAG_MESH,
    )
    try:
        material = _build_diffuse_material(
            owner_uuid, ROLE_FLAG_MATERIAL, f"LH Flag Material [{owner_uuid[:8]}]", color, 1.0,
        )
        obj.data.materials.append(material)
        if scene.render.engine == 'CYCLES' and hasattr(obj, "visible_camera"):
            obj.visible_camera = bool(visible_camera)
        return obj
    except BaseException:
        remove_studio_object(obj)
        _remove_owned_orphans(owner_uuid)
        raise


def create_reflector(
        scene,
        *,
        shape: str = 'RECTANGLE',
        width: float = 2.0,
        height: float = 2.0,
        color=(1.0, 1.0, 1.0),
        reflectance: float = 0.8,
        roughness: float = 0.5):
    if scene.render.engine != 'CYCLES':
        raise StudioEngineError("Reflectors require Cycles")
    obj, owner_uuid = _create_studio_object(
        scene, "LH Reflector", shape, width, height, 0.0, ROLE_REFLECTOR_OBJECT, ROLE_REFLECTOR_MESH,
    )
    try:
        material = _build_diffuse_material(
            owner_uuid,
            ROLE_REFLECTOR_MATERIAL,
            f"LH Reflector Material [{owner_uuid[:8]}]",
            color,
            roughness,
            reflectance,
        )
        obj.data.materials.append(material)
        obj["light_helper_reflector_color"] = tuple(color)[:3]
        obj["light_helper_reflector_reflectance"] = max(0.0, min(1.0, float(reflectance)))
        obj["light_helper_reflector_roughness"] = max(0.0, min(1.0, float(roughness)))
        return obj
    except BaseException:
        remove_studio_object(obj)
        _remove_owned_orphans(owner_uuid)
        raise


def ensure_unique_studio_data(obj) -> bool:
    """Give a duplicated managed object private provenance and mutable data."""

    if not is_studio_object(obj) or not getattr(obj, "is_editable", True):
        return False
    owner_uuid = obj.get(STUDIO_OWNER_KEY)
    duplicate_owner = any(
        other != obj and is_managed(other, owner_uuid) and other.get(STUDIO_ROLE_KEY) == obj.get(STUDIO_ROLE_KEY)
        for other in bpy.data.objects
    )
    if not duplicate_owner and (obj.data is None or obj.data.users <= 1):
        return False
    new_owner = uuid4().hex
    _mark_managed(obj, new_owner, obj.get(STUDIO_ROLE_KEY))
    if obj.data is not None:
        old_data = obj.data
        new_data = old_data.copy()
        _mark_managed(new_data, new_owner, old_data.get(STUDIO_ROLE_KEY))
        obj.data = new_data
        for index, material in enumerate(list(new_data.materials)):
            if material is None:
                continue
            new_material = material.copy()
            _mark_managed(new_material, new_owner, material.get(STUDIO_ROLE_KEY))
            new_data.materials[index] = new_material
    return True


def scrim_exposure(obj) -> float:
    if not is_managed(obj, role=ROLE_SCRIM_OBJECT):
        raise ValueError("Object is not a managed scrim")
    return float(obj.get("light_helper_scrim_exposure", 0.0))


def set_scrim_exposure(obj, exposure: float) -> bool:
    """Set scrim EV metadata and its managed emission strength input."""

    if not is_managed(obj, role=ROLE_SCRIM_OBJECT) or not getattr(obj, "is_editable", True):
        return False
    if obj.data is None or obj.data.users > 1:
        return False
    material = obj.active_material
    owner_uuid = obj.get(STUDIO_OWNER_KEY)
    if not is_managed(material, owner_uuid, ROLE_SCRIM_MATERIAL) or material.node_tree is None:
        return False
    if material.users > 1:
        return False
    strength_node = material.node_tree.nodes.get("Scrim Strength")
    if strength_node is None or strength_node.type != 'MATH':
        return False
    exposure = float(exposure)
    base_strength = max(0.0, float(obj.get("light_helper_scrim_strength", 0.0)))
    effective_strength = base_strength * (2.0 ** exposure)
    changed = float(obj.get("light_helper_scrim_exposure", 0.0)) != exposure
    changed = changed or strength_node.inputs[1].default_value != effective_strength
    if not changed:
        return False
    obj["light_helper_scrim_exposure"] = exposure
    strength_node.inputs[1].default_value = effective_strength
    return True


def remove_studio_object(obj) -> bool:
    if not is_studio_object(obj) or not getattr(obj, "is_editable", True):
        return False
    owner_uuid = obj.get(STUDIO_OWNER_KEY)
    mesh = obj.data if obj.type == 'MESH' else None
    materials = list(mesh.materials) if mesh is not None else []
    bpy.data.objects.remove(obj, do_unlink=True)
    if mesh is not None and mesh.users == 0 and is_managed(mesh, owner_uuid):
        bpy.data.meshes.remove(mesh)
    for material in materials:
        if material is not None and material.users == 0 and is_managed(material, owner_uuid):
            bpy.data.materials.remove(material)
    return True


def ensure_track_to(scene, source, target=None, *, location=None):
    """Create or reuse an owned ``TRACK_TO(-Z, Y)`` target for ``source``."""

    for constraint in source.constraints:
        if _track_constraint_owner(constraint) is not None:
            if target is not None:
                constraint.target = target
            elif constraint.target is not None and is_managed(constraint.target, role=ROLE_TRACK_TARGET):
                target = constraint.target
            if target is not None and location is not None and is_managed(target, role=ROLE_TRACK_TARGET):
                target.location = location
            return constraint, target

    if target is not None and is_managed(target, role=ROLE_TRACK_TARGET):
        owner_uuid = target.get(STUDIO_OWNER_KEY)
    else:
        owner_uuid = uuid4().hex
    if target is None:
        target = bpy.data.objects.new(f"LH Track Target [{owner_uuid[:8]}]", None)
        _mark_managed(target, owner_uuid, ROLE_TRACK_TARGET)
        target.empty_display_type = 'SPHERE'
        target.empty_display_size = 0.15
        if location is not None:
            target.location = location
        ensure_studio_collection(scene).objects.link(target)
    constraint = source.constraints.new('TRACK_TO')
    _mark_track_constraint(constraint, owner_uuid)
    constraint.target = target
    constraint.track_axis = 'TRACK_NEGATIVE_Z'
    constraint.up_axis = 'UP_Y'
    return constraint, target


def remove_managed_track_to(source) -> int:
    removed = 0
    targets = []
    for constraint in list(source.constraints):
        owner_uuid = _track_constraint_owner(constraint)
        if owner_uuid is None:
            continue
        target = constraint.target
        source.constraints.remove(constraint)
        removed += 1
        if is_managed(target, owner_uuid, ROLE_TRACK_TARGET):
            targets.append(target)
    for target in targets:
        referenced = any(
            constraint.target == target
            for obj in bpy.data.objects
            for constraint in obj.constraints
            if hasattr(constraint, "target")
        )
        parented = any(obj.parent == target for obj in bpy.data.objects)
        collection_users = len(target.users_collection)
        has_other_id_users = target.users > collection_users
        if (not referenced and not parented and not has_other_id_users
                and getattr(target, "is_editable", True)):
            bpy.data.objects.remove(target, do_unlink=True)
    return removed
