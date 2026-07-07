from enum import Enum, unique

import bpy

LIGHT_HELPER_MANAGED_KEY = "light_helper_managed"
LIGHT_HELPER_SAFE_KEY = "light_helper_safe"
ILLUMINATED_OBJECT_TYPE_LIST = [
    "LIGHT", "MESH", "CURVE", "SURFACE", "META", "FONT", "GPENCIL", "GREASEPENCIL", "EMPTY",
]
from .. import __package__ as base_package


def get_safe_obj_name(light: bpy.types.Object) -> str:
    return f"LLP_SAFE_{light.name}"


def get_safe_obj(light: bpy.types.Object) -> bpy.types.Object | None:
    return bpy.data.objects.get(get_safe_obj_name(light))


def is_safe_helper_object(obj: bpy.types.Object) -> bool:
    return bool(obj.get(LIGHT_HELPER_SAFE_KEY))


def mark_managed_linking_collection(coll: bpy.types.Collection) -> None:
    coll[LIGHT_HELPER_MANAGED_KEY] = True


def is_managed_linking_collection(coll: bpy.types.Collection) -> bool:
    if coll.get(LIGHT_HELPER_MANAGED_KEY):
        return True
    name = coll.name
    return name.startswith("Light Linking for ") or name.startswith("Shadow Linking for ")


def linking_coll_has_safe_obj(light: bpy.types.Object, coll: bpy.types.Collection | None) -> bool:
    if coll is None:
        return False
    safe_obj = get_safe_obj(light)
    return safe_obj is not None and safe_obj.name in coll.objects


@unique
class StateValue(Enum):
    """the state of the light linking"""
    EXCLUDE = 'EXCLUDE'
    INCLUDE = 'INCLUDE'


@unique
class CollectionType(Enum):
    """the type of the collection, using in dict"""
    RECEIVER = 'receiver'
    BLOCKER = 'blocker'


def get_pref(context=None):
    ctx = context if context is not None else bpy.context
    return ctx.preferences.addons[base_package].preferences


def remove_safe_helper_for_light(light: bpy.types.Object) -> None:
    safe_obj = get_safe_obj(light)
    if safe_obj is None:
        return
    mesh = safe_obj.data
    bpy.data.objects.remove(safe_obj, do_unlink=True)
    if mesh and mesh.users == 0:
        bpy.data.meshes.remove(mesh)


def remove_orphaned_managed_collection(coll: bpy.types.Collection | None) -> None:
    if coll is None or not is_managed_linking_collection(coll):
        return
    for obj in bpy.data.objects:
        if not hasattr(obj, "light_linking"):
            continue
        linking = obj.light_linking
        if linking.receiver_collection == coll or linking.blocker_collection == coll:
            return
    bpy.data.collections.remove(coll)


def restore_light_linking(light: bpy.types.Object) -> None:
    linking = light.light_linking
    receiver = linking.receiver_collection
    blocker = linking.blocker_collection
    linking.receiver_collection = None
    linking.blocker_collection = None
    remove_safe_helper_for_light(light)
    remove_orphaned_managed_collection(receiver)
    remove_orphaned_managed_collection(blocker)


def ensure_linking_coll(coll_type: CollectionType, light: bpy.types.Object, make_safe_obj: bool = True):
    """ensure the collection exists
    """

    prefix = 'Light Linking for ' if coll_type == CollectionType.RECEIVER else 'Shadow Linking for '
    coll_name = prefix + light.name

    if coll_type == CollectionType.RECEIVER:
        if light.light_linking.receiver_collection is None:
            coll = bpy.data.collections.new(coll_name)
            mark_managed_linking_collection(coll)
            light.light_linking.receiver_collection = coll
        else:
            coll = light.light_linking.receiver_collection
    else:
        if light.light_linking.blocker_collection is None:
            coll = bpy.data.collections.new(coll_name)
            mark_managed_linking_collection(coll)
            light.light_linking.blocker_collection = coll
        else:
            coll = light.light_linking.blocker_collection
    # make an empty mesh obj in this collection to avoid the annoying logic inverse between the exclude and include
    if make_safe_obj:
        safe_name = get_safe_obj_name(light)
        empty_mesh = bpy.data.meshes.get(safe_name)
        if empty_mesh is None:
            empty_mesh = bpy.data.meshes.new(safe_name)
        obj = bpy.data.objects.get(safe_name)
        if obj is None:
            obj = bpy.data.objects.new(safe_name, empty_mesh)
            obj[LIGHT_HELPER_SAFE_KEY] = light.name
        if obj.name not in coll.objects:
            coll.objects.link(obj)

    return coll


def get_linking_coll(obj: bpy.types.Object, type: CollectionType) -> bpy.types.Collection:
    """get the linking collection from the object"""

    if type == CollectionType.RECEIVER:
        return obj.light_linking.receiver_collection
    elif type == CollectionType.BLOCKER:
        return obj.light_linking.blocker_collection
    else:
        raise ValueError(f"CollectionType {type} is not supported")


def get_coll_item_linking_state(coll_obj: bpy.types.CollectionObject | bpy.types.CollectionChildren) -> StateValue:
    """returns the linking state of the collection object
    :returns str value in StateValue: 'EXCLUDE' or 'INCLUDE'
    """
    if coll_obj.light_linking.link_state == 'EXCLUDE':
        return StateValue.EXCLUDE
    else:
        return StateValue.INCLUDE


def enum_coll_objs_from_coll(coll: bpy.types.Collection) -> dict[bpy.types.Object:bpy.types.CollectionObject]:
    """Since that the CollectionObject can not be accessed directly by name from the Collection, this function is used to
    :returns dict[bpy.types.Object:bpy.types.CollectionObject]: {obj:coll_obj}
    """
    return {obj: coll.collection_objects[i] for i, obj in enumerate(coll.objects)}


def enum_coll_children_from_coll(coll: bpy.types.Collection) -> dict[bpy.types.Collection:bpy.types.CollectionChildren]:
    """Since that the CollectionObject can not be accessed directly by name from the Collection, this function is used to
    :returns dict[bpy.types.Object:bpy.types.CollectionObject]: {obj:coll_obj}
    """
    return {child: coll.collection_children[i] for i, child in enumerate(coll.children)}


def get_light_effect_obj_state(light: bpy.types.Object, obj: bpy.types.Object) -> dict[str:str]:
    """get the light effect state of the object from the light,both the receiver and the block collection, return a dict that contains the light linking state of the object

    :return dict[str:str]: {CollectionType.RECEIVER.value:str|None, CollectionType.BLOCKER.value:str|None
    """

    # first get the receiver collection and the block collection
    receiver_coll = get_linking_coll(light, CollectionType.RECEIVER)
    blocker_coll = get_linking_coll(light, CollectionType.BLOCKER)

    state = {
        CollectionType.RECEIVER: None,
        CollectionType.BLOCKER: None
    }

    def get_obj_state_from_coll(coll: bpy.types.Collection) -> StateValue | None:
        """get the state of the object from the collection"""
        coll_objs = enum_coll_objs_from_coll(coll)
        coll_obj = coll_objs.get(obj)
        if coll_obj:
            return get_coll_item_linking_state(coll_obj)
        return None

    # if the receiver collection exists, get the state of the object from the receiver collection

    if receiver_coll:
        state[CollectionType.RECEIVER] = get_obj_state_from_coll(receiver_coll)
    if blocker_coll:
        state[CollectionType.BLOCKER] = get_obj_state_from_coll(blocker_coll)

    return state


def get_light_effect_coll_state(light: bpy.types.Object, coll: bpy.types.Collection) -> dict[str:str]:
    """get the light effect state of the object from the light,both the receiver and the block collection, return a dict that contains the light linking state of the object

    :return dict[str:str]: {CollectionType.RECEIVER.value:str|None, CollectionType.BLOCKER.value:str|None
    """

    # first get the receiver collection and the block collection
    receiver_coll = get_linking_coll(light, CollectionType.RECEIVER)
    blocker_coll = get_linking_coll(light, CollectionType.BLOCKER)

    state = {
        CollectionType.RECEIVER: None,
        CollectionType.BLOCKER: None
    }

    def get_obj_state_from_coll(_coll: bpy.types.Collection) -> StateValue | None:
        """get the state of the object from the collection"""
        coll_objs = enum_coll_children_from_coll(_coll)
        coll_obj = coll_objs.get(coll)
        if coll_obj:
            return get_coll_item_linking_state(coll_obj)
        return None

    # if the receiver collection exists, get the state of the object from the receiver collection

    if receiver_coll:
        state[CollectionType.RECEIVER] = get_obj_state_from_coll(receiver_coll)
    if blocker_coll:
        state[CollectionType.BLOCKER] = get_obj_state_from_coll(blocker_coll)

    return state


def get_all_light_effect_items_state(light: bpy.types.Object) -> dict[
                                                                 bpy.types.Object | bpy.types.Collection:dict[str:str]]:
    """get all the objects that are affected by the light and their receiver and blocker state
    version for all object because the function above runs multiple times function:enum_coll_objs_from_coll is not efficient
    :return dict{bpy.types.Object:dict: {'receiver':str|None, 'blocker':str|None}}
    """
    receiver_coll = get_linking_coll(light, CollectionType.RECEIVER)
    blocker_coll = get_linking_coll(light, CollectionType.BLOCKER)

    items_state = {}  # {bpy.types.Object:dict: {'receiver':str|None, 'blocker':str|None}} Note: the str is the link state, None means the object is not in the collection

    #
    if receiver_coll:
        coll_children = enum_coll_children_from_coll(receiver_coll)
        for child in coll_children:
            items_state[child] = {
                CollectionType.RECEIVER: get_coll_item_linking_state(coll_children[child]),
                CollectionType.BLOCKER: None
            }
        coll_objs = enum_coll_objs_from_coll(receiver_coll)
        for obj in coll_objs:
            items_state[obj] = {
                CollectionType.RECEIVER: get_coll_item_linking_state(coll_objs[obj]),
                CollectionType.BLOCKER: None
            }

    if blocker_coll:
        coll_children = enum_coll_children_from_coll(blocker_coll)
        for child in coll_children:
            if items_state.get(child):
                items_state[child][CollectionType.BLOCKER] = get_coll_item_linking_state(coll_children[child])
            else:
                items_state[child] = {
                    CollectionType.RECEIVER: None,
                    CollectionType.BLOCKER: get_coll_item_linking_state(coll_children[child])
                }

        coll_objs = enum_coll_objs_from_coll(blocker_coll)
        for obj in coll_objs:
            if items_state.get(obj):
                items_state[obj][CollectionType.BLOCKER] = get_coll_item_linking_state(coll_objs[obj])
            else:
                items_state[obj] = {
                    CollectionType.RECEIVER: None,
                    CollectionType.BLOCKER: get_coll_item_linking_state(coll_objs[obj])
                }

    return items_state


_view_layer_collections_cache = frozenset()
_cached_linking_lights = ()


def get_all_view_layout_collection(context: bpy.types.Context) -> list[bpy.types.Collection]:
    layer_collection = context.view_layer.layer_collection
    res = []

    def get_lc(lc: bpy.types.LayerCollection):
        res.append(lc.collection)
        for child in lc.children:
            get_lc(child)

    get_lc(layer_collection)
    return res


def refresh_drop_poll_context(context: bpy.types.Context) -> None:
    global _view_layer_collections_cache, _cached_linking_lights
    wm_props = context.window_manager.light_helper_property
    scene_props = context.scene.light_helper_property
    if scene_props.light_linking_pin:
        wm_props.drop_light_obj = scene_props.light_linking_pin_object
    else:
        wm_props.drop_light_obj = context.object
    if scene_props.object_linking_pin:
        wm_props.drop_object_obj = scene_props.object_linking_pin_object
    else:
        wm_props.drop_object_obj = context.object
    _view_layer_collections_cache = frozenset(get_all_view_layout_collection(context))
    _cached_linking_lights = tuple(
        light_obj for light_obj in context.scene.objects
        if hasattr(light_obj, "light_linking")
        and (light_obj.light_linking.receiver_collection or light_obj.light_linking.blocker_collection)
    )


def get_view_layer_collections_cache():
    return _view_layer_collections_cache


def get_lights_from_effect_obj(obj: bpy.types.Object, context: bpy.types.Context | None = None) -> dict:
    """get all the lights that affect the object and their receiver and blocker state"""
    colls = obj.users_collection
    light_state = {}
    if _cached_linking_lights:
        lights = _cached_linking_lights
    elif context is not None:
        lights = context.scene.objects
    else:
        return light_state

    for light_obj in lights:
        if not hasattr(light_obj, 'light_linking'): continue
        if not light_obj.light_linking.receiver_collection and not light_obj.light_linking.blocker_collection: continue

        receiver_coll = light_obj.light_linking.receiver_collection
        blocker_coll = light_obj.light_linking.blocker_collection

        if receiver_coll in colls or blocker_coll in colls:
            light_state[light_obj] = {
                CollectionType.RECEIVER: None,
                CollectionType.BLOCKER: None
            }
            if receiver_coll:
                for i, o in enumerate(receiver_coll.objects):
                    if o is obj:
                        light_state[light_obj][CollectionType.RECEIVER] = get_coll_item_linking_state(
                            receiver_coll.collection_objects[i])
                        break
            if blocker_coll:
                for i, o in enumerate(blocker_coll.objects):
                    if o is obj:
                        light_state[light_obj][CollectionType.BLOCKER] = get_coll_item_linking_state(
                            blocker_coll.collection_objects[i])
                        break

    return light_state


def set_light_effect_obj_state(light: bpy.types.Object, obj: bpy.types.Object,
                               state: tuple[CollectionType, StateValue]) -> None:
    """set the light effect state of the object from the light,in the receiver or the block collection

    :param light: the light object
    :param obj: the object that is affected by the light
    :param state: the state to set for the object, dict[CollectionType.value:StateValue.value]
    """

    def set_obj_state_from_coll(coll: bpy.types.Collection, state_value: StateValue):
        """set the state of the object from the collection"""
        coll_objs = enum_coll_objs_from_coll(coll)
        coll_obj = coll_objs.get(obj)
        if coll_obj:
            coll_obj.light_linking.link_state = state_value.value

    if state[0] == CollectionType.RECEIVER:
        set_obj_state_from_coll(get_linking_coll(light, CollectionType.RECEIVER), state[1])
    elif state[0] == CollectionType.BLOCKER:
        set_obj_state_from_coll(get_linking_coll(light, CollectionType.BLOCKER), state[1])

    return


def set_light_effect_coll_state(light: bpy.types.Object, coll: bpy.types.Collection,
                                state: tuple[CollectionType, StateValue]) -> None:
    """set the light effect state of the object from the light,in the receiver or the block collection

    :param light: the light object
    :param obj: the object that is affected by the light
    :param state: the state to set for the object, dict[CollectionType.value:StateValue.value]
    """

    def set_obj_state_from_coll(_coll: bpy.types.Collection, state_value: StateValue):
        """set the state of the object from the collection"""
        coll_objs = enum_coll_children_from_coll(_coll)
        coll_obj = coll_objs.get(coll)
        if coll_obj:
            coll_obj.light_linking.link_state = state_value.value

    if state[0] == CollectionType.RECEIVER:
        set_obj_state_from_coll(get_linking_coll(light, CollectionType.RECEIVER), state[1])
    elif state[0] == CollectionType.BLOCKER:
        set_obj_state_from_coll(get_linking_coll(light, CollectionType.BLOCKER), state[1])

    return


def check_material_including_emission(
        obj: bpy.types.Object,
        check_depth=5,
        cache: dict | None = None,
) -> bool:
    if cache is not None:
        cache_key = (obj.name_full, check_depth)
        if cache_key in cache:
            return cache[cache_key]

    def node_tree_search(node: bpy.types.Node, depth=0) -> [bpy.types.Node | None]:
        if depth > check_depth:
            return None
        for input_point in node.inputs:  # 当前节点的输入节点
            for link in input_point.links:  # 输入链接的节点
                from_node = link.from_node  # 链接 从
                if from_node.type in {"ADD_SHADER", "MIX_SHADER"}:
                    find = node_tree_search(from_node, depth + 1)
                    if find:
                        return find
                elif from_node.type == "EMISSION":  # 就是一个自发光节点
                    return True
                elif from_node.type == "BSDF_PRINCIPLED":  # 原理化节点
                    for i in from_node.inputs:
                        if i.identifier == "Emission Strength" and i.default_value > 0:
                            return True
                elif from_node.type == "GROUP":  # 处理节点组
                    group_out_node = find_material_output_node(from_node.node_tree.nodes)
                    if group_out_node:
                        find = node_tree_search(group_out_node) is not None
                        if find:
                            return find
                else:
                    find = node_tree_search(link.from_node, depth + 1)
                    if find:
                        return find

    result = False
    for material in obj.material_slots:
        mat = material.material
        if mat and mat.use_nodes:
            out_node = find_material_output_node(mat.node_tree.nodes)
            if out_node and node_tree_search(out_node):
                result = True
                break
    if cache is not None:
        cache[(obj.name_full, check_depth)] = result
    return result


def find_material_output_node(nodes: [bpy.types.Node]) -> [bpy.types.Material | None]:
    for node in nodes:
        if node.type in ("OUTPUT_MATERIAL", "GROUP_OUTPUT") and node.is_active_output:
            return node


def view_selected(context: bpy.types.Context):
    mt = get_pref(context).moving_view_type
    if mt == "NONE":
        return
    for area in context.screen.areas:
        if area.type == "VIEW_3D" and area == context.area:
            for region in area.regions:
                if region.type == "WINDOW":
                    with context.temp_override(area=area, region=region):
                        if mt == "MAINTAINING_ZOOM":
                            view_distance = context.space_data.region_3d.view_distance
                            bpy.ops.view3d.view_selected("EXEC_DEFAULT", use_all_regions=True)
                            context.space_data.region_3d.view_distance = view_distance
                        elif mt == "ANIMATION":
                            bpy.ops.view3d.view_selected("INVOKE_DEFAULT", use_all_regions=True)


def check_link(obj: bpy.types.Object) -> bool:
    return obj.light_linking.receiver_collection or obj.light_linking.blocker_collection
