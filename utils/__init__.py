from enum import Enum, unique

import bpy

LIGHT_HELPER_MANAGED_KEY = "light_helper_managed"
ILLUMINATED_OBJECT_TYPE_LIST = [
    "LIGHT", "MESH", "CURVE", "SURFACE", "META", "FONT", "GPENCIL", "GREASEPENCIL", "EMPTY",
]
from .. import __package__ as base_package


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


def mark_managed_linking_collection(coll: bpy.types.Collection) -> None:
    coll[LIGHT_HELPER_MANAGED_KEY] = True


def is_managed_linking_collection(coll: bpy.types.Collection) -> bool:
    if coll.get(LIGHT_HELPER_MANAGED_KEY):
        return True
    name = coll.name
    return name.startswith("Light Linking for ") or name.startswith("Shadow Linking for ")


def get_pref(context=None):
    ctx = context if context is not None else bpy.context
    return ctx.preferences.addons[base_package].preferences


def resolve_original_id(id_block):
    if id_block is None:
        return None
    if isinstance(id_block, bpy.types.Object) and id_block.is_evaluated:
        return id_block.original
    original = getattr(id_block, "original", None)
    if original is not None:
        return original
    return id_block


def is_original_id(id_block) -> bool:
    if id_block is None:
        return False
    if isinstance(id_block, bpy.types.Object):
        return not id_block.is_evaluated
    if isinstance(id_block, bpy.types.ID):
        return not getattr(id_block, "is_evaluated", False)
    return True


def is_linking_initialized(light: bpy.types.Object) -> bool:
    if not hasattr(light, "light_linking"):
        return False
    linking = light.light_linking
    return linking.receiver_collection is not None and linking.blocker_collection is not None


def get_linking_mode(light: bpy.types.Object) -> str:
    if hasattr(light, "light_helper_property"):
        return light.light_helper_property.linking_mode
    return StateValue.EXCLUDE.value


def get_linking_coll(obj: bpy.types.Object, type: CollectionType) -> bpy.types.Collection:
    if type == CollectionType.RECEIVER:
        return obj.light_linking.receiver_collection
    elif type == CollectionType.BLOCKER:
        return obj.light_linking.blocker_collection
    raise ValueError(f"CollectionType {type} is not supported")


def enum_coll_objs_from_coll(coll: bpy.types.Collection) -> dict:
    return {obj: coll.collection_objects[i] for i, obj in enumerate(coll.objects)}


def enum_coll_children_from_coll(coll: bpy.types.Collection) -> dict:
    return {child: coll.collection_children[i] for i, child in enumerate(coll.children)}


def _set_item_link_state(coll: bpy.types.Collection, item, mode: str) -> None:
    if isinstance(item, bpy.types.Object):
        coll_objs = enum_coll_objs_from_coll(coll)
        coll_obj = coll_objs.get(item)
        if coll_obj:
            coll_obj.light_linking.link_state = mode
    elif isinstance(item, bpy.types.Collection):
        coll_children = enum_coll_children_from_coll(coll)
        coll_child = coll_children.get(item)
        if coll_child:
            coll_child.light_linking.link_state = mode


def apply_linking_mode_to_light(light: bpy.types.Object, mode: str | None = None) -> None:
    if mode is None:
        mode = get_linking_mode(light)
    for coll_type in (CollectionType.RECEIVER, CollectionType.BLOCKER):
        coll = get_linking_coll(light, coll_type)
        if coll is None:
            continue
        for coll_obj in coll.collection_objects:
            coll_obj.light_linking.link_state = mode
        for coll_child in coll.collection_children:
            coll_child.light_linking.link_state = mode


def init_light_linking(light: bpy.types.Object, context: bpy.types.Context | None = None) -> None:
    ctx = context if context is not None else bpy.context
    with ctx.temp_override(object=light, active_object=light, selected_objects=[light]):
        if light.light_linking.receiver_collection is None:
            bpy.ops.object.light_linking_receiver_collection_new()
        if light.light_linking.blocker_collection is None:
            bpy.ops.object.light_linking_blocker_collection_new()
    for coll_type in (CollectionType.RECEIVER, CollectionType.BLOCKER):
        coll = get_linking_coll(light, coll_type)
        if coll is not None:
            mark_managed_linking_collection(coll)


def ensure_linking_coll(coll_type: CollectionType, light: bpy.types.Object,
                        context: bpy.types.Context | None = None) -> bpy.types.Collection:
    if not is_linking_initialized(light):
        init_light_linking(light, context)
    return get_linking_coll(light, coll_type)


def collection_has_object(coll: bpy.types.Collection, obj: bpy.types.Object) -> bool:
    return any(member == obj for member in coll.objects)


def collection_has_child(coll: bpy.types.Collection, child: bpy.types.Collection) -> bool:
    return any(member == child for member in coll.children)


def is_item_in_channel(light: bpy.types.Object, item,
                       coll_type: CollectionType) -> bool:
    coll = get_linking_coll(light, coll_type)
    if coll is None:
        return False
    if isinstance(item, bpy.types.Object):
        return collection_has_object(coll, item)
    if isinstance(item, bpy.types.Collection):
        return collection_has_child(coll, item)
    return False


def object_in_collection_tree(coll: bpy.types.Collection, obj: bpy.types.Object) -> bool:
    if collection_has_object(coll, obj):
        return True
    for child in coll.children:
        if object_in_collection_tree(child, obj):
            return True
    return False


def is_object_affected_in_channel(light: bpy.types.Object, obj: bpy.types.Object,
                                  coll_type: CollectionType) -> bool:
    if is_item_in_channel(light, obj, coll_type):
        return True
    coll = get_linking_coll(light, coll_type)
    if coll is None:
        return False
    for child in coll.children:
        if object_in_collection_tree(child, obj):
            return True
    return False


def link_item_to_channel(light: bpy.types.Object, item,
                         coll_type: CollectionType, enabled: bool,
                         context: bpy.types.Context | None = None) -> None:
    light = resolve_original_id(light)
    item = resolve_original_id(item)
    if not is_original_id(light) or not is_original_id(item):
        return
    try:
        coll = ensure_linking_coll(coll_type, light, context)
    except RuntimeError:
        return
    mode = get_linking_mode(light)
    try:
        if isinstance(item, bpy.types.Object):
            if enabled:
                if not collection_has_object(coll, item):
                    coll.objects.link(item)
                _set_item_link_state(coll, item, mode)
            elif collection_has_object(coll, item):
                coll.objects.unlink(item)
        elif isinstance(item, bpy.types.Collection):
            if enabled:
                if not collection_has_child(coll, item):
                    coll.children.link(item)
                _set_item_link_state(coll, item, mode)
            elif collection_has_child(coll, item):
                coll.children.unlink(item)
    except RuntimeError:
        return

    from .overlay import notify_linking_changed
    notify_linking_changed(context)


def link_item_both_channels(light: bpy.types.Object, item,
                            context: bpy.types.Context | None = None) -> None:
    link_item_to_channel(light, item, CollectionType.RECEIVER, True, context)
    link_item_to_channel(light, item, CollectionType.BLOCKER, True, context)


def toggle_item_both_channels(light: bpy.types.Object, item,
                              context: bpy.types.Context | None = None) -> bool:
    """Toggle receiver and blocker channels together. Returns True if channels are enabled."""
    if not is_linking_initialized(light):
        init_light_linking(light, context)
    receiver = is_item_in_channel(light, item, CollectionType.RECEIVER)
    blocker = is_item_in_channel(light, item, CollectionType.BLOCKER)
    enable = not (receiver and blocker)
    link_item_to_channel(light, item, CollectionType.RECEIVER, enable, context)
    link_item_to_channel(light, item, CollectionType.BLOCKER, enable, context)
    return enable


def is_emissive_light_source(obj: bpy.types.Object, context: bpy.types.Context | None = None) -> bool:
    obj = resolve_original_id(obj)
    if obj is None or obj.type == 'LIGHT':
        return False
    if not hasattr(obj, "light_linking"):
        return False
    pref = get_pref(context)
    return check_material_including_emission(obj, pref.node_search_depth)


def is_tool_light_source(obj: bpy.types.Object, context: bpy.types.Context | None = None) -> bool:
    obj = resolve_original_id(obj)
    if obj is None:
        return False
    if obj.type == 'LIGHT':
        return True
    return is_emissive_light_source(obj, context)


def is_linkable_object(obj: bpy.types.Object) -> bool:
    return obj.type in ILLUMINATED_OBJECT_TYPE_LIST and obj.type != "LIGHT"


def get_filtered_tool_lights(context: bpy.types.Context) -> list[bpy.types.Object]:
    from ..filter import filter_objects
    return [obj for obj in filter_objects(context) if is_tool_light_source(obj, context)]


def cycle_tool_light(context: bpy.types.Context, light: bpy.types.Object | None,
                     direction: int) -> bpy.types.Object | None:
    lights = get_filtered_tool_lights(context)
    if not lights:
        return None
    light = resolve_original_id(light)
    names = [resolve_original_id(item).name for item in lights]
    if light is None or light.name not in names:
        return lights[0]
    index = names.index(light.name)
    return lights[(index + direction) % len(lights)]


def select_tool_light(context: bpy.types.Context, light: bpy.types.Object) -> None:
    view_layer = context.view_layer
    for obj in view_layer.objects.selected:
        obj.select_set(False)
    view_layer.objects.active = light
    light.select_set(True)
    objects = context.scene.objects[:]
    if light in objects:
        context.scene.light_helper_property.active_object_index = objects.index(light)
    view_selected(context)


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


def restore_light_linking(light: bpy.types.Object, context: bpy.types.Context | None = None) -> None:
    linking = light.light_linking
    receiver = linking.receiver_collection
    blocker = linking.blocker_collection
    linking.receiver_collection = None
    linking.blocker_collection = None
    remove_orphaned_managed_collection(receiver)
    remove_orphaned_managed_collection(blocker)
    from .overlay import notify_linking_changed
    notify_linking_changed(context)


def get_light_effect_obj_state(light: bpy.types.Object, obj: bpy.types.Object) -> dict:
    state = {
        CollectionType.RECEIVER: None,
        CollectionType.BLOCKER: None,
    }
    if is_item_in_channel(light, obj, CollectionType.RECEIVER):
        state[CollectionType.RECEIVER] = True
    if is_item_in_channel(light, obj, CollectionType.BLOCKER):
        state[CollectionType.BLOCKER] = True
    return state


def get_light_effect_coll_state(light: bpy.types.Object, coll: bpy.types.Collection) -> dict:
    state = {
        CollectionType.RECEIVER: None,
        CollectionType.BLOCKER: None,
    }
    if is_item_in_channel(light, coll, CollectionType.RECEIVER):
        state[CollectionType.RECEIVER] = True
    if is_item_in_channel(light, coll, CollectionType.BLOCKER):
        state[CollectionType.BLOCKER] = True
    return state


def get_all_light_effect_items_state(light: bpy.types.Object) -> dict:
    receiver_coll = get_linking_coll(light, CollectionType.RECEIVER)
    blocker_coll = get_linking_coll(light, CollectionType.BLOCKER)

    items_state = {}

    if receiver_coll:
        for child in enum_coll_children_from_coll(receiver_coll):
            items_state.setdefault(child, {CollectionType.RECEIVER: None, CollectionType.BLOCKER: None})
            items_state[child][CollectionType.RECEIVER] = True
        for obj in enum_coll_objs_from_coll(receiver_coll):
            items_state.setdefault(obj, {CollectionType.RECEIVER: None, CollectionType.BLOCKER: None})
            items_state[obj][CollectionType.RECEIVER] = True

    if blocker_coll:
        for child in enum_coll_children_from_coll(blocker_coll):
            items_state.setdefault(child, {CollectionType.RECEIVER: None, CollectionType.BLOCKER: None})
            items_state[child][CollectionType.BLOCKER] = True
        for obj in enum_coll_objs_from_coll(blocker_coll):
            items_state.setdefault(obj, {CollectionType.RECEIVER: None, CollectionType.BLOCKER: None})
            items_state[obj][CollectionType.BLOCKER] = True

    return items_state


def get_light_link_item_count(light: bpy.types.Object) -> int:
    if light is None:
        return 0
    return len(get_all_light_effect_items_state(light))


def get_lights_from_effect_obj(obj: bpy.types.Object, context: bpy.types.Context | None = None) -> dict:
    """Return lights that affect ``obj`` via light/shadow linking."""
    light_state = {}
    if obj is None:
        return light_state

    obj = resolve_original_id(obj)
    if _cached_linking_lights:
        lights = _cached_linking_lights
    elif context is not None:
        lights = context.scene.objects
    else:
        return light_state

    for light_obj in lights:
        if not is_tool_light_source(light_obj, context) or not hasattr(light_obj, 'light_linking'):
            continue
        linking = light_obj.light_linking
        if not linking.receiver_collection and not linking.blocker_collection:
            continue

        receiver_on = is_object_affected_in_channel(light_obj, obj, CollectionType.RECEIVER)
        blocker_on = is_object_affected_in_channel(light_obj, obj, CollectionType.BLOCKER)
        if not receiver_on and not blocker_on:
            continue

        light_state[light_obj] = {
            CollectionType.RECEIVER: True if receiver_on else None,
            CollectionType.BLOCKER: True if blocker_on else None,
        }

    return light_state


# Keep the overlay-facing name as an alias of the shared query.
get_object_overlay_lights_state = get_lights_from_effect_obj


def get_object_link_light_count(obj: bpy.types.Object, context: bpy.types.Context | None = None) -> int:
    if obj is None:
        return 0
    return len(get_lights_from_effect_obj(obj, context))


def get_filtered_tool_objects(context: bpy.types.Context) -> list[bpy.types.Object]:
    from ..filter import filter_objects
    return [obj for obj in filter_objects(context) if is_linkable_object(obj)]


def cycle_tool_object(context: bpy.types.Context, obj: bpy.types.Object | None,
                      direction: int) -> bpy.types.Object | None:
    objects = get_filtered_tool_objects(context)
    if not objects:
        return None
    obj = resolve_original_id(obj)
    names = [resolve_original_id(item).name for item in objects]
    if obj is None or obj.name not in names:
        return objects[0]
    index = names.index(obj.name)
    return objects[(index + direction) % len(objects)]


def select_tool_object(context: bpy.types.Context, obj: bpy.types.Object) -> None:
    view_layer = context.view_layer
    for selected in view_layer.objects.selected:
        selected.select_set(False)
    view_layer.objects.active = obj
    obj.select_set(True)
    objects = context.scene.objects[:]
    if obj in objects:
        context.scene.light_helper_property.active_object_index = objects.index(obj)
    view_selected(context)


def linking_item_sort_key(item: bpy.types.Object | bpy.types.Collection) -> tuple:
    type_order = 0 if isinstance(item, bpy.types.Collection) else 1
    return type_order, item.name.casefold()


def iter_sorted_linking_items(items_state: dict):
    yield from sorted(items_state.items(), key=lambda pair: linking_item_sort_key(pair[0]))


def iter_sorted_linking_lights(light_state: dict):
    yield from sorted(light_state.items(), key=lambda pair: pair[0].name.casefold())


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


def check_material_including_emission(
        obj: bpy.types.Object,
        check_depth=5,
        cache: dict | None = None,
) -> bool:
    if cache is not None:
        cache_key = (obj.name_full, check_depth)
        if cache_key in cache:
            return cache[cache_key]

    def node_tree_search(node: bpy.types.Node, depth=0):
        if depth > check_depth:
            return None
        for input_point in node.inputs:
            for link in input_point.links:
                from_node = link.from_node
                if from_node.type in {"ADD_SHADER", "MIX_SHADER"}:
                    find = node_tree_search(from_node, depth + 1)
                    if find:
                        return find
                elif from_node.type == "EMISSION":
                    return True
                elif from_node.type == "BSDF_PRINCIPLED":
                    for i in from_node.inputs:
                        if i.identifier == "Emission Strength" and i.default_value > 0:
                            return True
                elif from_node.type == "GROUP":
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


def find_material_output_node(nodes):
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
    return bool(obj.light_linking.receiver_collection or obj.light_linking.blocker_collection)


def get_item_visibility_restrictions(
        item: bpy.types.Object | bpy.types.Collection) -> tuple[bool, bool, bool]:
    if isinstance(item, bpy.types.Object):
        viewport_hidden = item.hide_viewport or item.hide_get()
        render_hidden = item.hide_render
    elif isinstance(item, bpy.types.Collection):
        viewport_hidden = item.hide_viewport
        render_hidden = item.hide_render
    else:
        return False, False, False
    return viewport_hidden, render_hidden, viewport_hidden or render_hidden


LIGHT_HELPER_DUP_HANDLED_KEY = "light_helper_dup_handled"


def _managed_linking_coll_name(light: bpy.types.Object, coll_type: CollectionType) -> str:
    prefix = 'Light Linking for ' if coll_type == CollectionType.RECEIVER else 'Shadow Linking for '
    return prefix + light.name


def has_shared_linking_collections(light: bpy.types.Object) -> bool:
    if not hasattr(light, "light_linking"):
        return False
    linking = light.light_linking
    receiver = linking.receiver_collection
    blocker = linking.blocker_collection
    return (receiver is not None and receiver.users > 1) or (blocker is not None and blocker.users > 1)


def split_shared_linking_collection(light: bpy.types.Object, coll_type: CollectionType) -> bool:
    if not hasattr(light, "light_linking"):
        return False
    linking = light.light_linking
    coll = get_linking_coll(light, coll_type)
    if coll is None or coll.users <= 1:
        return False
    new_coll = coll.copy()
    mark_managed_linking_collection(new_coll)
    new_coll.name = _managed_linking_coll_name(light, coll_type)
    if coll_type == CollectionType.RECEIVER:
        linking.receiver_collection = new_coll
    else:
        linking.blocker_collection = new_coll
    apply_linking_mode_to_light(light)
    return True


def make_light_linking_single_user(light: bpy.types.Object) -> bool:
    if not hasattr(light, "light_linking"):
        return False
    changed = False
    if split_shared_linking_collection(light, CollectionType.RECEIVER):
        changed = True
    if split_shared_linking_collection(light, CollectionType.BLOCKER):
        changed = True
    return changed


def find_duplicate_source_object(obj: bpy.types.Object) -> bpy.types.Object | None:
    name = obj.name
    if '.' not in name:
        return None
    base, suffix = name.rsplit('.', 1)
    if not suffix.isdigit():
        return None
    num = int(suffix)
    if num <= 0:
        return None
    if num == 1:
        source_name = base
    else:
        source_name = f"{base}.{num - 1:03d}"
    source = bpy.data.objects.get(source_name)
    if source is None or source == obj:
        return None
    return source


def inherit_light_linking_from_object(
        target: bpy.types.Object,
        source: bpy.types.Object,
        context: bpy.types.Context | None = None) -> bool:
    target = resolve_original_id(target)
    source = resolve_original_id(source)
    if target is None or source is None or target == source:
        return False
    if not is_original_id(target) or not is_original_id(source):
        return False
    changed = False
    ctx = context if context is not None else bpy.context
    scene = ctx.scene
    if scene is None:
        return False

    if (target.type == 'LIGHT' and source.type == 'LIGHT'
            and hasattr(target, "light_helper_property")
            and hasattr(source, "light_helper_property")):
        target.light_helper_property.linking_mode = source.light_helper_property.linking_mode

    for light_obj in scene.objects:
        if not hasattr(light_obj, "light_linking"):
            continue
        linking = light_obj.light_linking
        if not linking.receiver_collection and not linking.blocker_collection:
            continue
        for coll_type in (CollectionType.RECEIVER, CollectionType.BLOCKER):
            if is_item_in_channel(light_obj, source, coll_type):
                link_item_to_channel(light_obj, target, coll_type, True, context)
                changed = True
    return changed


def is_duplicate_handled(obj: bpy.types.Object) -> bool:
    return bool(obj.get(LIGHT_HELPER_DUP_HANDLED_KEY))


def mark_duplicate_handled(obj: bpy.types.Object) -> None:
    obj[LIGHT_HELPER_DUP_HANDLED_KEY] = True


def process_duplicated_object(obj: bpy.types.Object, context: bpy.types.Context | None = None) -> bool:
    obj = resolve_original_id(obj)
    if obj is None or not is_original_id(obj):
        return False
    if is_duplicate_handled(obj):
        return False
    changed = False
    source = find_duplicate_source_object(obj)

    if obj.type == 'LIGHT':
        if has_shared_linking_collections(obj):
            changed = make_light_linking_single_user(obj) or changed
        if (source is not None and source.type == 'LIGHT'
                and hasattr(obj, "light_helper_property")
                and hasattr(source, "light_helper_property")):
            obj.light_helper_property.linking_mode = source.light_helper_property.linking_mode
            changed = True
    elif source is not None:
        changed = inherit_light_linking_from_object(obj, source, context) or changed

    if changed:
        mark_duplicate_handled(obj)
    return changed


def fix_all_shared_light_linking(scene: bpy.types.Scene) -> list[bpy.types.Object]:
    fixed = []
    for obj in scene.objects:
        if obj.type != 'LIGHT':
            continue
        if make_light_linking_single_user(obj):
            fixed.append(obj)
    return fixed


def scene_has_uninitialized_lights(scene: bpy.types.Scene) -> bool:
    for obj in scene.objects:
        if obj.type != 'LIGHT':
            continue
        if hasattr(obj, "light_linking") and not is_linking_initialized(obj):
            return True
    return False


def init_all_light_linking(scene: bpy.types.Scene,
                           context: bpy.types.Context | None = None) -> list[bpy.types.Object]:
    initialized = []
    for obj in scene.objects:
        if obj.type != 'LIGHT':
            continue
        if not hasattr(obj, "light_linking"):
            continue
        if is_linking_initialized(obj):
            continue
        init_light_linking(obj, context)
        initialized.append(obj)
    return initialized
