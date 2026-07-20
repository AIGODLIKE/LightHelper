from enum import Enum, unique
from uuid import uuid4

import bpy

from .. import __package__ as base_package

LIGHT_HELPER_MANAGED_KEY = "light_helper_managed"
LIGHT_HELPER_SAFE_KEY = "light_helper_safe"
LIGHT_HELPER_SAFE_OWNER_KEY = "light_helper_safe_owner"
LIGHT_HELPER_OWNER_UUID_KEY = "light_helper_owner_uuid"
ILLUMINATED_OBJECT_TYPE_LIST = [
    "LIGHT", "MESH", "CURVE", "SURFACE", "META", "FONT", "GPENCIL", "GREASEPENCIL", "EMPTY",
]


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
    return bool(coll.get(LIGHT_HELPER_MANAGED_KEY))


def is_safe_helper_object(obj: bpy.types.Object | None) -> bool:
    # Legacy helpers are recognized only by the reserved custom property, never by name.
    # Deletion still requires the new owner UUID in ``remove_safe_helper_for_light``.
    return bool(obj is not None and obj.get(LIGHT_HELPER_SAFE_KEY))


def _light_owner_uuid(light: bpy.types.Object, create: bool = False) -> str | None:
    owner_uuid = light.get(LIGHT_HELPER_OWNER_UUID_KEY)
    if isinstance(owner_uuid, str) and owner_uuid:
        return owner_uuid
    if not create:
        return None
    owner_uuid = uuid4().hex
    light[LIGHT_HELPER_OWNER_UUID_KEY] = owner_uuid
    return owner_uuid


def get_safe_obj(light: bpy.types.Object) -> bpy.types.Object | None:
    owner_uuid = _light_owner_uuid(light)
    if owner_uuid is None:
        return None
    for obj in bpy.data.objects:
        if (is_safe_helper_object(obj)
                and obj.get(LIGHT_HELPER_SAFE_OWNER_KEY) == owner_uuid):
            return obj
    return None


def remove_safe_helper_for_light(light: bpy.types.Object) -> None:
    safe = get_safe_obj(light)
    owner_uuid = _light_owner_uuid(light)
    if (safe is None or owner_uuid is None
            or safe.get(LIGHT_HELPER_SAFE_OWNER_KEY) != owner_uuid):
        return
    mesh = safe.data if safe.type == 'MESH' else None
    bpy.data.objects.remove(safe, do_unlink=True)
    if mesh is not None and mesh.users == 0:
        bpy.data.meshes.remove(mesh)


def sync_safe_helpers_for_light(light: bpy.types.Object) -> None:
    """Keep LLP_SAFE_* only when a linking collection has no other items (Blender empty-coll quirk)."""
    if not hasattr(light, "light_linking"):
        return
    linking = light.light_linking
    mode = get_linking_mode(light)
    used = False
    for coll in (linking.receiver_collection, linking.blocker_collection):
        if coll is None:
            continue
        safes = [o for o in list(coll.objects) if is_safe_helper_object(o)]
        has_real = any(not is_safe_helper_object(o) for o in coll.objects) or bool(coll.children)
        if has_real:
            for o in safes:
                coll.objects.unlink(o)
            continue
        safe = get_safe_obj(light)
        if safe is None:
            owner_uuid = _light_owner_uuid(light, create=True)
            name = f"LLP_SAFE_{light.name}_{owner_uuid[:8]}"
            mesh = bpy.data.meshes.new(name)
            safe = bpy.data.objects.new(name, mesh)
            safe.hide_viewport = True
            safe.hide_render = True
            safe.hide_select = True
            safe[LIGHT_HELPER_SAFE_KEY] = True
            safe[LIGHT_HELPER_SAFE_OWNER_KEY] = owner_uuid
        for o in safes:
            if o != safe:
                coll.objects.unlink(o)
        if safe.name not in coll.objects:
            coll.objects.link(safe)
        _set_item_link_state(coll, safe, mode)
        used = True
    if not used:
        remove_safe_helper_for_light(light)


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
    return StateValue.INCLUDE.value


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


def is_internal_world_dome_link(
        light: bpy.types.Object,
        item,
        coll_type: CollectionType,
) -> bool:
    """World dome exclusions are infrastructure, not user-authored light links."""
    if coll_type != CollectionType.RECEIVER:
        return False
    if light.type != 'LIGHT' or light.data is None or light.data.type != 'SUN':
        return False
    try:
        from .world_environment import (
            ROLE_DOME_OBJECT,
            ROLE_SUN_PROXY,
            WORLD_DOME_ROLE_KEY,
        )
        role = item.get(WORLD_DOME_ROLE_KEY)
        if isinstance(item, bpy.types.Object):
            return role == ROLE_DOME_OBJECT
        if isinstance(item, bpy.types.Collection):
            return role == ROLE_SUN_PROXY
        return False
    except (ImportError, AttributeError, ReferenceError):
        return False


def apply_linking_mode_to_light(light: bpy.types.Object, mode: str | None = None) -> None:
    if mode is None:
        mode = get_linking_mode(light)
    for coll_type in (CollectionType.RECEIVER, CollectionType.BLOCKER):
        coll = get_linking_coll(light, coll_type)
        if coll is None:
            continue
        for index, coll_obj in enumerate(coll.collection_objects):
            item = coll.objects[index]
            if is_internal_world_dome_link(light, item, coll_type):
                coll_obj.light_linking.link_state = StateValue.EXCLUDE.value
                continue
            coll_obj.light_linking.link_state = mode
        for index, coll_child in enumerate(coll.collection_children):
            item = coll.children[index]
            if is_internal_world_dome_link(light, item, coll_type):
                coll_child.light_linking.link_state = StateValue.EXCLUDE.value
                continue
            coll_child.light_linking.link_state = mode


def init_light_linking(light: bpy.types.Object, context: bpy.types.Context | None = None) -> None:
    # Prefer RNA over ops: light_linking_*_collection_new.poll rejects hidden objects.
    linking = light.light_linking
    for coll_type in (CollectionType.RECEIVER, CollectionType.BLOCKER):
        coll = get_linking_coll(light, coll_type)
        if coll is None:
            coll = bpy.data.collections.new(_managed_linking_coll_name(light, coll_type))
            if coll_type == CollectionType.RECEIVER:
                linking.receiver_collection = coll
            else:
                linking.blocker_collection = coll
        mark_managed_linking_collection(coll)
    sync_safe_helpers_for_light(light)


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


def has_real_linking_items(light: bpy.types.Object) -> bool:
    """Return whether either linking channel contains a non-helper item."""
    if not hasattr(light, "light_linking"):
        return False
    linking = light.light_linking
    for coll_type, coll in (
        (CollectionType.RECEIVER, linking.receiver_collection),
        (CollectionType.BLOCKER, linking.blocker_collection),
    ):
        if coll is None:
            continue
        if any(
                not is_safe_helper_object(obj)
                and not is_internal_world_dome_link(light, obj, coll_type)
                for obj in coll.objects):
            return True
        if any(
                not is_internal_world_dome_link(light, child, coll_type)
                for child in coll.children):
            return True
    return False


def link_item_to_channel(light: bpy.types.Object, item,
                         coll_type: CollectionType, enabled: bool,
                         context: bpy.types.Context | None = None, *,
                         restore_default_when_empty: bool = False) -> None:
    light = resolve_original_id(light)
    item = resolve_original_id(item)
    if not is_original_id(light) or not is_original_id(item):
        return
    coll = get_linking_coll(light, coll_type)
    if coll is None:
        if not enabled:
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

    if restore_default_when_empty and not enabled and not has_real_linking_items(light):
        restore_light_linking(light, context)
        return

    sync_safe_helpers_for_light(light)
    from .overlay import notify_linking_changed
    notify_linking_changed(context)


def link_item_both_channels(light: bpy.types.Object, item,
                            context: bpy.types.Context | None = None) -> None:
    link_item_to_channel(light, item, CollectionType.RECEIVER, True, context)
    link_item_to_channel(light, item, CollectionType.BLOCKER, True, context)


def toggle_item_both_channels(light: bpy.types.Object, item,
                              context: bpy.types.Context | None = None, *,
                              restore_default_when_empty: bool = False) -> bool:
    """Toggle receiver and blocker channels together. Returns True if channels are enabled."""
    if not is_linking_initialized(light):
        init_light_linking(light, context)
    receiver = is_item_in_channel(light, item, CollectionType.RECEIVER)
    blocker = is_item_in_channel(light, item, CollectionType.BLOCKER)
    enable = not (receiver and blocker)
    link_item_to_channel(
        light, item, CollectionType.RECEIVER, enable, context,
        restore_default_when_empty=restore_default_when_empty,
    )
    link_item_to_channel(
        light, item, CollectionType.BLOCKER, enable, context,
        restore_default_when_empty=restore_default_when_empty,
    )
    return enable


def supports_emissive_light_sources(context: bpy.types.Context | None = None) -> bool:
    """Whether material-emission objects can act as Light Linking sources.

    Blender supports Light Linking for emissive mesh objects only in Cycles.
    A missing context intentionally keeps this a data-level check for RNA pointer
    polls and migration code; all interactive entry points pass a context.
    """
    if context is None:
        return True
    scene = getattr(context, "scene", None)
    if scene is None and isinstance(context, bpy.types.Scene):
        scene = context
    if scene is None:
        return True
    return scene.render.engine == 'CYCLES'


def is_emissive_light_source(
        obj: bpy.types.Object,
        context: bpy.types.Context | None = None,
        *,
        search_depth: int | None = None,
        cache: dict | None = None,
) -> bool:
    obj = resolve_original_id(obj)
    if obj is None or obj.type == 'LIGHT':
        return False
    if not hasattr(obj, "light_linking"):
        return False
    if not supports_emissive_light_sources(context):
        return False
    if search_depth is None:
        search_depth = get_pref(context).node_search_depth
    return check_material_including_emission(obj, search_depth, cache=cache)


def is_tool_light_source(obj: bpy.types.Object, context: bpy.types.Context | None = None) -> bool:
    obj = resolve_original_id(obj)
    if obj is None:
        return False
    if obj.type == 'LIGHT':
        return True
    return is_emissive_light_source(obj, context)


def get_active_light_source(context: bpy.types.Context) -> bpy.types.Object | None:
    """Resolve the pinned or selected source using the current render engine."""
    if context is None or context.scene is None:
        return None
    scene_props = context.scene.light_helper_property
    if scene_props.light_linking_pin:
        light_obj = resolve_original_id(scene_props.light_linking_pin_object)
        if is_tool_light_source(light_obj, context):
            return light_obj
    light_obj = resolve_original_id(context.object)
    if is_tool_light_source(light_obj, context):
        return light_obj
    return None


def is_linkable_object(obj: bpy.types.Object) -> bool:
    return obj.type in ILLUMINATED_OBJECT_TYPE_LIST and obj.type != "LIGHT"


def is_in_view_layer(context: bpy.types.Context, obj: bpy.types.Object) -> bool:
    """True when ``obj`` is present in the current view layer (not collection-excluded)."""
    obj = resolve_original_id(obj)
    if obj is None or context is None or context.view_layer is None:
        return False
    return obj.name in context.view_layer.objects


def is_shown_in_view_layer(context: bpy.types.Context, obj: bpy.types.Object) -> bool:
    """True when the object is in the view layer and visible in the viewport."""
    obj = resolve_original_id(obj)
    if obj is None or not is_in_view_layer(context, obj):
        return False
    try:
        return bool(obj.visible_get())
    except ReferenceError:
        return False


def get_filtered_tool_lights(context: bpy.types.Context) -> list[bpy.types.Object]:
    from ..filter import filter_objects
    return [
        obj for obj in filter_objects(context)
        if is_tool_light_source(obj, context) and is_shown_in_view_layer(context, obj)
    ]


def cycle_tool_light(context: bpy.types.Context, light: bpy.types.Object | None,
                     direction: int) -> bpy.types.Object | None:
    lights = get_filtered_tool_lights(context)
    if not lights:
        return None
    light = resolve_original_id(light)
    resolved = [resolve_original_id(item) for item in lights]
    if light is None or light not in resolved:
        return lights[0]
    index = resolved.index(light)
    return lights[(index + direction) % len(lights)]


def select_tool_light(context: bpy.types.Context, light: bpy.types.Object) -> None:
    view_layer = context.view_layer
    if is_in_view_layer(context, light):
        for obj in view_layer.objects.selected:
            obj.select_set(False)
        view_layer.objects.active = light
        light.select_set(True)
    objects = context.scene.objects[:]
    if light in objects:
        context.scene.light_helper_property.active_object_index = objects.index(light)
    if is_in_view_layer(context, light):
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
    active_world_domes = []
    if light.type == 'LIGHT' and light.data is not None and light.data.type == 'SUN':
        from .world_environment import get_world_dome, remove_sun_exclusions
        for scene in bpy.data.scenes:
            if light.name not in scene.objects:
                continue
            dome = get_world_dome(scene)
            if dome is None:
                continue
            remove_sun_exclusions(scene, dome, [light])
            if scene.render.engine == 'CYCLES':
                active_world_domes.append((scene, dome))
    linking = light.light_linking
    receiver = linking.receiver_collection
    blocker = linking.blocker_collection
    linking.receiver_collection = None
    linking.blocker_collection = None
    remove_safe_helper_for_light(light)
    remove_orphaned_managed_collection(receiver)
    remove_orphaned_managed_collection(blocker)
    # A converted world dome must remain excluded from Sun lights even when the
    # user restores all ordinary links for that Sun.
    if active_world_domes:
        from .world_environment import ensure_sun_exclusions
        for scene, dome in active_world_domes:
            ensure_sun_exclusions(scene, dome, [light])
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
            if is_internal_world_dome_link(light, child, CollectionType.RECEIVER):
                continue
            items_state.setdefault(child, {CollectionType.RECEIVER: None, CollectionType.BLOCKER: None})
            items_state[child][CollectionType.RECEIVER] = True
        for obj in enum_coll_objs_from_coll(receiver_coll):
            if is_safe_helper_object(obj):
                continue
            if is_internal_world_dome_link(light, obj, CollectionType.RECEIVER):
                continue
            items_state.setdefault(obj, {CollectionType.RECEIVER: None, CollectionType.BLOCKER: None})
            items_state[obj][CollectionType.RECEIVER] = True

    if blocker_coll:
        for child in enum_coll_children_from_coll(blocker_coll):
            if is_internal_world_dome_link(light, child, CollectionType.BLOCKER):
                continue
            items_state.setdefault(child, {CollectionType.RECEIVER: None, CollectionType.BLOCKER: None})
            items_state[child][CollectionType.BLOCKER] = True
        for obj in enum_coll_objs_from_coll(blocker_coll):
            if is_safe_helper_object(obj):
                continue
            if is_internal_world_dome_link(light, obj, CollectionType.BLOCKER):
                continue
            items_state.setdefault(obj, {CollectionType.RECEIVER: None, CollectionType.BLOCKER: None})
            items_state[obj][CollectionType.BLOCKER] = True

    return items_state


def get_light_link_item_count(light: bpy.types.Object) -> int:
    if light is None:
        return 0
    return len(get_all_light_effect_items_state(light))


def get_lights_from_effect_obj(obj: bpy.types.Object, context: bpy.types.Context | None = None) -> dict:
    """Return lights that affect ``obj`` via light/shadow linking."""
    if obj is None:
        return {}

    obj = resolve_original_id(obj)
    if context is not None:
        _ensure_linking_ui_cache(context)
    cache_key = obj.as_pointer()
    cached = _cached_object_light_states.get(cache_key)
    if cached is not None:
        return cached

    light_state = {}
    if _linking_ui_cache_key is not None:
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

        receiver_on = (
            is_object_affected_in_channel(light_obj, obj, CollectionType.RECEIVER)
            and not is_internal_world_dome_link(light_obj, obj, CollectionType.RECEIVER)
        )
        blocker_on = (
            is_object_affected_in_channel(light_obj, obj, CollectionType.BLOCKER)
            and not is_internal_world_dome_link(light_obj, obj, CollectionType.BLOCKER)
        )
        if not receiver_on and not blocker_on:
            continue

        light_state[light_obj] = {
            CollectionType.RECEIVER: True if receiver_on else None,
            CollectionType.BLOCKER: True if blocker_on else None,
        }

    if _linking_ui_cache_key is not None:
        _cached_object_light_states[cache_key] = light_state
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


def iter_objects_linked_by_lights(context: bpy.types.Context) -> list[bpy.types.Object]:
    """Objects that appear in any light's receiver/blocker linking collections."""
    _ensure_linking_ui_cache(context)
    return list(_cached_linked_objects)


def _collect_objects_linked_by_lights(
        context: bpy.types.Context,
        lights,
) -> tuple[bpy.types.Object, ...]:
    linked: set[bpy.types.Object] = set()
    for light_obj in lights:
        for item in get_all_light_effect_items_state(light_obj):
            if isinstance(item, bpy.types.Object):
                if is_linkable_object(item):
                    linked.add(resolve_original_id(item) or item)
            elif isinstance(item, bpy.types.Collection):
                for child in item.objects:
                    if is_linkable_object(child):
                        linked.add(resolve_original_id(child) or child)
    return tuple(sorted(linked, key=lambda o: o.name.casefold()))


def is_object_linked_by_any_light(obj: bpy.types.Object, context: bpy.types.Context) -> bool:
    obj = resolve_original_id(obj)
    if obj is None or not is_linkable_object(obj):
        return False
    return obj in set(iter_objects_linked_by_lights(context))


def cycle_tool_object(context: bpy.types.Context, obj: bpy.types.Object | None,
                      direction: int) -> bpy.types.Object | None:
    # Match the Object Linking UIList: only objects already linked by lights,
    # and skip ones hidden or excluded from the current view layer.
    objects = [
        item for item in iter_objects_linked_by_lights(context)
        if is_shown_in_view_layer(context, item)
    ]
    if not objects:
        return None
    obj = resolve_original_id(obj)
    resolved = [resolve_original_id(item) for item in objects]
    if obj is None or obj not in resolved:
        return objects[0]
    index = resolved.index(obj)
    return objects[(index + direction) % len(objects)]


def select_tool_object(context: bpy.types.Context, obj: bpy.types.Object) -> None:
    view_layer = context.view_layer
    if is_in_view_layer(context, obj):
        for selected in view_layer.objects.selected:
            selected.select_set(False)
        view_layer.objects.active = obj
        obj.select_set(True)
    objects = context.scene.objects[:]
    scene_props = context.scene.light_helper_property
    if obj in objects:
        scene_props.active_object_index = objects.index(obj)
        scene_props.active_linked_object_index = objects.index(obj)
    if is_in_view_layer(context, obj):
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
_cached_linked_objects = ()
_cached_object_light_states = {}
_linking_ui_cache_key = None
_linking_ui_cache_generation = 0


def get_all_view_layout_collection(context: bpy.types.Context) -> list[bpy.types.Collection]:
    layer_collection = context.view_layer.layer_collection
    res = []

    def get_lc(lc: bpy.types.LayerCollection):
        res.append(lc.collection)
        for child in lc.children:
            get_lc(child)

    get_lc(layer_collection)
    return res


def invalidate_linking_ui_cache() -> None:
    """Invalidate panel/linking lookups after relevant data changes."""
    global _view_layer_collections_cache
    global _cached_linking_lights
    global _cached_linked_objects
    global _cached_object_light_states
    global _linking_ui_cache_key
    global _linking_ui_cache_generation
    _view_layer_collections_cache = frozenset()
    _cached_linking_lights = ()
    _cached_linked_objects = ()
    _cached_object_light_states = {}
    _linking_ui_cache_key = None
    _linking_ui_cache_generation += 1


def _linking_context_cache_key(context: bpy.types.Context) -> tuple:
    return (
        context.scene.as_pointer(),
        context.view_layer.as_pointer(),
        context.scene.render.engine,
        len(context.scene.objects),
        _linking_ui_cache_generation,
    )


def _ensure_linking_ui_cache(context: bpy.types.Context) -> None:
    global _view_layer_collections_cache
    global _cached_linking_lights
    global _cached_linked_objects
    global _cached_object_light_states
    global _linking_ui_cache_key
    if context is None or context.scene is None or context.view_layer is None:
        return
    cache_key = _linking_context_cache_key(context)
    if cache_key == _linking_ui_cache_key:
        return

    linking_lights = []
    emission_cache = {}
    for light_obj in context.scene.objects:
        if not hasattr(light_obj, "light_linking"):
            continue
        linking = light_obj.light_linking
        if not linking.receiver_collection and not linking.blocker_collection:
            continue
        if light_obj.type != 'LIGHT' and not is_emissive_light_source(
                light_obj,
                context,
                cache=emission_cache,
        ):
            continue
        linking_lights.append(light_obj)

    _view_layer_collections_cache = frozenset(get_all_view_layout_collection(context))
    _cached_linking_lights = tuple(linking_lights)
    _cached_linked_objects = _collect_objects_linked_by_lights(
        context,
        _cached_linking_lights,
    )
    _cached_object_light_states = {}
    _linking_ui_cache_key = cache_key


def refresh_drop_poll_context(context: bpy.types.Context) -> None:
    wm_props = context.window_manager.light_helper_property
    scene_props = context.scene.light_helper_property
    drop_light = get_active_light_source(context)
    if wm_props.drop_light_obj != drop_light:
        wm_props.drop_light_obj = drop_light
    if scene_props.object_linking_pin:
        drop_object = scene_props.object_linking_pin_object
    else:
        drop_object = context.object
    if wm_props.drop_object_obj != drop_object:
        wm_props.drop_object_obj = drop_object
    _ensure_linking_ui_cache(context)


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
    if not hasattr(obj, "light_linking"):
        return False
    linking = obj.light_linking
    return bool(linking.receiver_collection or linking.blocker_collection)


def get_item_visibility_restrictions(
        item: bpy.types.Object | bpy.types.Collection,
        context: bpy.types.Context | None = None,
) -> tuple[bool, bool, bool]:
    if isinstance(item, bpy.types.Object):
        viewport_hidden = item.hide_viewport or item.hide_get()
        if context is not None and not is_shown_in_view_layer(context, item):
            viewport_hidden = True
        render_hidden = item.hide_render
    elif isinstance(item, bpy.types.Collection):
        viewport_hidden = item.hide_viewport
        render_hidden = item.hide_render
    else:
        return False, False, False
    return viewport_hidden, render_hidden, viewport_hidden or render_hidden


LIGHT_HELPER_DUP_HANDLED_KEY = "light_helper_dup_handled"
LIGHT_HELPER_DUP_SOURCE_KEY = "light_helper_dup_source"


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
    """Resolve a duplicate source only from explicit tracking or shared light-linking data."""
    source = obj.get(LIGHT_HELPER_DUP_SOURCE_KEY)
    if isinstance(source, bpy.types.Object) and source != obj:
        return source

    if obj.type == 'LIGHT' and hasattr(obj, "light_linking"):
        linking = obj.light_linking
        for coll in (linking.receiver_collection, linking.blocker_collection):
            if coll is None or coll.users <= 1:
                continue
            for other in bpy.data.objects:
                if other == obj or other.type != 'LIGHT' or not hasattr(other, "light_linking"):
                    continue
                other_linking = other.light_linking
                if (other_linking.receiver_collection == coll
                        or other_linking.blocker_collection == coll):
                    return other

    return None


def track_duplicate_source(source: bpy.types.Object, duplicate: bpy.types.Object) -> None:
    if source is None or duplicate is None or source == duplicate:
        return
    duplicate[LIGHT_HELPER_DUP_SOURCE_KEY] = source


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


def prime_existing_duplicate_objects(scene: bpy.types.Scene,
                                   context: bpy.types.Context | None = None) -> None:
    """Mark scene duplicates as handled so later source links do not cascade."""
    ctx = context if context is not None else bpy.context
    for obj in scene.objects:
        if is_duplicate_handled(obj) or obj.type == 'LIGHT':
            continue
        source = find_duplicate_source_object(obj)
        if source is None:
            continue
        if (is_object_linked_by_any_light(source, ctx)
                and not is_object_linked_by_any_light(obj, ctx)):
            inherit_light_linking_from_object(obj, source, ctx)
        mark_duplicate_handled(obj)


def process_duplicated_object(obj: bpy.types.Object, context: bpy.types.Context | None = None) -> bool:
    obj = resolve_original_id(obj)
    if obj is None or not is_original_id(obj):
        return False
    if is_duplicate_handled(obj):
        return False
    changed = False
    source = find_duplicate_source_object(obj)
    if source is not None:
        track_duplicate_source(source, obj)

    if obj.type == 'LIGHT':
        if has_shared_linking_collections(obj):
            changed = make_light_linking_single_user(obj) or changed
        if (source is not None and source.type == 'LIGHT'
                and hasattr(obj, "light_helper_property")
                and hasattr(source, "light_helper_property")):
            obj.light_helper_property.linking_mode = source.light_helper_property.linking_mode
            changed = True
    elif source is not None:
        source_has_links = is_object_linked_by_any_light(source, context)
        if source_has_links:
            changed = inherit_light_linking_from_object(obj, source, context) or changed
        # Mark explicitly tracked duplicates after their first processing pass.
        mark_duplicate_handled(obj)
        return changed

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
