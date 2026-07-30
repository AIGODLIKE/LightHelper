from dataclasses import dataclass
from enum import Enum, unique
from uuid import uuid4

import bpy

from .. import __package__ as base_package

LIGHT_HELPER_MANAGED_KEY = "light_helper_managed"
LIGHT_HELPER_MANAGED_OWNER_KEY = "light_helper_managed_owner"
LIGHT_HELPER_SAFE_KEY = "light_helper_safe"
LIGHT_HELPER_SAFE_OWNER_KEY = "light_helper_safe_owner"
LIGHT_HELPER_OWNER_UUID_KEY = "light_helper_owner_uuid"
ILLUMINATED_OBJECT_TYPE_LIST = [
    "LIGHT", "MESH", "CURVE", "SURFACE", "META", "FONT", "GPENCIL", "GREASEPENCIL", "EMPTY",
]


@unique
class ChannelState(str, Enum):
    """State of one native light- or shadow-linking collection entry."""

    OFF = 'OFF'
    EXCLUDE = 'EXCLUDE'
    INCLUDE = 'INCLUDE'


@unique
class StateValue(Enum):
    """Legacy two-state alias kept for public API compatibility."""

    EXCLUDE = ChannelState.EXCLUDE.value
    INCLUDE = ChannelState.INCLUDE.value


@unique
class CollectionType(Enum):
    """the type of the collection, using in dict"""
    RECEIVER = 'receiver'
    BLOCKER = 'blocker'


@dataclass(frozen=True)
class EffectiveChannelState:
    """Resolved state for a target, including collection inheritance."""

    state: ChannelState
    direct: bool = False
    inherited_from: tuple = ()
    mixed: bool = False


def mark_managed_linking_collection(
        coll: bpy.types.Collection,
        light: bpy.types.Object | None = None) -> None:
    try:
        coll[LIGHT_HELPER_MANAGED_KEY] = True
    except (ReferenceError, RuntimeError, TypeError):
        return
    if light is not None:
        owner_uuid = _light_owner_uuid(light, create=True)
        if owner_uuid is not None:
            try:
                coll[LIGHT_HELPER_MANAGED_OWNER_KEY] = owner_uuid
            except (ReferenceError, RuntimeError, TypeError):
                pass


def is_managed_linking_collection(coll: bpy.types.Collection) -> bool:
    return bool(coll.get(LIGHT_HELPER_MANAGED_KEY))


def is_safe_helper_object(obj: bpy.types.Object | None) -> bool:
    # Legacy helpers are recognized only by the reserved custom property, never by name.
    # Deletion still requires the new owner UUID in ``remove_safe_helper_for_light``.
    return bool(obj is not None and obj.get(LIGHT_HELPER_SAFE_KEY))


def _light_owner_uuid(light: bpy.types.Object, create: bool = False) -> str | None:
    try:
        owner_uuid = light.get(LIGHT_HELPER_OWNER_UUID_KEY)
    except (ReferenceError, RuntimeError, TypeError):
        return None
    if isinstance(owner_uuid, str) and owner_uuid:
        return owner_uuid
    if not create:
        return None
    owner_uuid = uuid4().hex
    try:
        light[LIGHT_HELPER_OWNER_UUID_KEY] = owner_uuid
    except (ReferenceError, RuntimeError, TypeError):
        return None
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


def _remove_orphaned_safe_object(safe: bpy.types.Object | None) -> None:
    if safe is None or not is_safe_helper_object(safe):
        return
    if not safe.is_editable:
        return
    if safe.users_collection or safe.users > 0:
        return
    mesh = safe.data if safe.type == 'MESH' else None
    bpy.data.objects.remove(safe, do_unlink=True)
    if mesh is not None and mesh.users == 0:
        bpy.data.meshes.remove(mesh)


def _linking_collection_used_by_other_light(
        coll: bpy.types.Collection,
        light: bpy.types.Object) -> bool:
    for other in bpy.data.objects:
        if other == light or not hasattr(other, "light_linking"):
            continue
        linking = other.light_linking
        if linking.receiver_collection == coll or linking.blocker_collection == coll:
            return True
    return False


def _rebind_managed_collection_owner(
        light: bpy.types.Object,
        previous_owner_uuid: str,
        owner_uuid: str) -> None:
    if not is_light_linking_source_editable(light):
        return
    linking = light.light_linking
    collections = []
    for coll in (linking.receiver_collection, linking.blocker_collection):
        if coll is None or coll in collections:
            continue
        collections.append(coll)
    for coll in collections:
        if (_linking_collection_used_by_other_light(coll, light)
                or coll.get(LIGHT_HELPER_MANAGED_OWNER_KEY) != previous_owner_uuid):
            continue
        try:
            coll[LIGHT_HELPER_MANAGED_OWNER_KEY] = owner_uuid
        except (TypeError, RuntimeError):
            pass


def _ensure_unique_light_owner_uuid(light: bpy.types.Object) -> str | None:
    if not is_light_linking_source_editable(light):
        return None
    owner_uuid = _light_owner_uuid(light, create=True)
    if owner_uuid is None:
        return None
    duplicate_owner = any(
        other != light and other.get(LIGHT_HELPER_OWNER_UUID_KEY) == owner_uuid
        for other in bpy.data.objects
    )
    if not duplicate_owner:
        return owner_uuid

    # A still-shared linking collection intentionally has one helper state.
    # make_light_linking_single_user() assigns the new owner after copying it.
    if hasattr(light, "light_linking"):
        linking = light.light_linking
        if any(
                coll is not None and _linking_collection_used_by_other_light(coll, light)
                for coll in (linking.receiver_collection, linking.blocker_collection)):
            return owner_uuid

    new_owner_uuid = uuid4().hex
    try:
        light[LIGHT_HELPER_OWNER_UUID_KEY] = new_owner_uuid
    except (TypeError, RuntimeError):
        return owner_uuid
    _rebind_managed_collection_owner(light, owner_uuid, new_owner_uuid)
    return new_owner_uuid


def remove_safe_helper_for_light(light: bpy.types.Object) -> None:
    if not is_light_linking_source_editable(light):
        return
    owner_uuid = _light_owner_uuid(light)
    if owner_uuid is None or not hasattr(light, "light_linking"):
        return

    candidates = []
    safe = get_safe_obj(light)
    if safe is not None:
        candidates.append(safe)

    linking = light.light_linking
    collections = []
    for coll in (linking.receiver_collection, linking.blocker_collection):
        if coll is None or coll in collections:
            continue
        collections.append(coll)

    for coll in collections:
        if not coll.is_editable:
            continue
        owned_safes = [
            obj for obj in list(coll.objects)
            if (is_safe_helper_object(obj)
                and obj.get(LIGHT_HELPER_SAFE_OWNER_KEY) == owner_uuid)
        ]
        for owned_safe in owned_safes:
            if owned_safe not in candidates:
                candidates.append(owned_safe)
        # Clearing one duplicate must not mutate a collection still used by
        # another light. Its helper remains valid for that other owner.
        if _linking_collection_used_by_other_light(coll, light):
            continue
        for owned_safe in owned_safes:
            try:
                coll.objects.unlink(owned_safe)
            except RuntimeError:
                pass

    for candidate in candidates:
        _remove_orphaned_safe_object(candidate)


def sync_safe_helpers_for_light(light: bpy.types.Object) -> bool:
    """Keep LLP_SAFE_* only when a linking collection has no other items (Blender empty-coll quirk)."""
    if not are_light_linking_collections_editable(light):
        return False
    previous_helpers = []
    linking = light.light_linking
    for coll in (linking.receiver_collection, linking.blocker_collection):
        if coll is None:
            continue
        for obj in coll.objects:
            if is_safe_helper_object(obj) and obj not in previous_helpers:
                previous_helpers.append(obj)
    if _ensure_unique_light_owner_uuid(light) is None:
        return False
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
    for previous_helper in previous_helpers:
        _remove_orphaned_safe_object(previous_helper)
    if not used:
        remove_safe_helper_for_light(light)
    return True


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


def is_light_linking_source_editable(light: bpy.types.Object | None) -> bool:
    """Match Blender's writable light-linking source rules."""
    light = resolve_original_id(light)
    try:
        if (not isinstance(light, bpy.types.Object)
                or not is_original_id(light)
                or not hasattr(light, "light_linking")
                or not light.is_editable):
            return False
        override = light.override_library
        return override is None or not override.is_system_override
    except (AttributeError, ReferenceError, RuntimeError, TypeError):
        return False


def are_light_linking_collections_editable(light: bpy.types.Object | None) -> bool:
    """Check the source and both currently assigned channel collections."""
    light = resolve_original_id(light)
    if not is_light_linking_source_editable(light):
        return False
    try:
        linking = light.light_linking
        return all(
            coll is None or coll.is_editable
            for coll in (linking.receiver_collection, linking.blocker_collection)
        )
    except (AttributeError, ReferenceError, RuntimeError, TypeError):
        return False


def is_linking_initialized(light: bpy.types.Object) -> bool:
    if not hasattr(light, "light_linking"):
        return False
    linking = light.light_linking
    return linking.receiver_collection is not None and linking.blocker_collection is not None


def get_linking_mode(light: bpy.types.Object) -> str:
    if hasattr(light, "light_helper_property"):
        return light.light_helper_property.linking_mode
    return StateValue.INCLUDE.value


def get_linking_edit_mode(light: bpy.types.Object) -> str:
    """Return SIMPLE for legacy files which predate the edit-mode property."""
    if hasattr(light, "light_helper_property"):
        return getattr(light.light_helper_property, "linking_edit_mode", "SIMPLE")
    return "SIMPLE"


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


def _coerce_channel_state(state) -> ChannelState:
    if isinstance(state, ChannelState):
        return state
    try:
        return ChannelState(str(state))
    except ValueError as exc:
        raise ValueError(f"Unsupported light linking channel state: {state!r}") from exc


def _entry_for_item(coll: bpy.types.Collection | None, item):
    if coll is None or item is None:
        return None
    if isinstance(item, bpy.types.Object):
        return enum_coll_objs_from_coll(coll).get(item)
    if isinstance(item, bpy.types.Collection):
        return enum_coll_children_from_coll(coll).get(item)
    return None


def get_item_channel_state(
        light: bpy.types.Object,
        item,
        coll_type: CollectionType) -> ChannelState:
    """Return the target's direct native state, or OFF when no direct entry exists."""
    light = resolve_original_id(light)
    item = resolve_original_id(item)
    try:
        coll = get_linking_coll(light, coll_type)
        entry = _entry_for_item(coll, item)
        if entry is None:
            return ChannelState.OFF
        return _coerce_channel_state(entry.light_linking.link_state)
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
        return ChannelState.OFF


def _collection_contains_object(
        coll: bpy.types.Collection,
        obj: bpy.types.Object,
        visited: set[int] | None = None) -> bool:
    if visited is None:
        visited = set()
    pointer = coll.as_pointer()
    if pointer in visited:
        return False
    visited.add(pointer)
    if collection_has_object(coll, obj):
        return True
    return any(_collection_contains_object(child, obj, visited) for child in coll.children)


def get_effective_item_channel_state(
        light: bpy.types.Object,
        item,
        coll_type: CollectionType) -> EffectiveChannelState:
    """Resolve a direct state first, then states inherited from linked collections.

    A direct object entry overrides collection inheritance without removing any
    parent collection link. Conflicting inherited collection entries are
    reported as ``mixed`` and are never normalized as a side effect of reading.
    """
    direct_state = get_item_channel_state(light, item, coll_type)
    if direct_state != ChannelState.OFF:
        return EffectiveChannelState(direct_state, direct=True)
    if not isinstance(item, bpy.types.Object):
        return EffectiveChannelState(ChannelState.OFF)
    try:
        coll = get_linking_coll(light, coll_type)
    except (AttributeError, ReferenceError, RuntimeError, TypeError):
        coll = None
    if coll is None:
        return EffectiveChannelState(ChannelState.OFF)

    inherited = []
    states = set()
    for child in coll.children:
        try:
            if not _collection_contains_object(child, item):
                continue
            state = get_item_channel_state(light, child, coll_type)
            if state == ChannelState.OFF:
                continue
            inherited.append(child)
            states.add(state)
        except (AttributeError, ReferenceError, RuntimeError, TypeError):
            continue
    if not states:
        return EffectiveChannelState(ChannelState.OFF)
    if len(states) > 1:
        return EffectiveChannelState(
            ChannelState.OFF,
            inherited_from=tuple(inherited),
            mixed=True,
        )
    return EffectiveChannelState(
        next(iter(states)),
        inherited_from=tuple(inherited),
    )


def get_effective_linking_mode(light: bpy.types.Object) -> str:
    """Return INCLUDE, EXCLUDE, or MIXED from the native user-authored entries."""
    light = resolve_original_id(light)
    states = set()
    try:
        for coll_type in (CollectionType.RECEIVER, CollectionType.BLOCKER):
            coll = get_linking_coll(light, coll_type)
            if coll is None:
                continue
            for item in tuple(coll.objects) + tuple(coll.children):
                if (is_safe_helper_object(item)
                        or is_internal_world_dome_link(light, item, coll_type)):
                    continue
                state = get_item_channel_state(light, item, coll_type)
                if state != ChannelState.OFF:
                    states.add(state.value)
    except (AttributeError, ReferenceError, RuntimeError, TypeError):
        return get_linking_mode(light)
    if not states:
        return get_linking_mode(light)
    if len(states) == 1:
        return next(iter(states))
    return "MIXED"


def _set_item_link_state(coll: bpy.types.Collection, item, mode: str) -> bool:
    entry = _entry_for_item(coll, item)
    if entry is None:
        return False
    try:
        if entry.light_linking.link_state == mode:
            return False
        entry.light_linking.link_state = mode
        return True
    except (AttributeError, ReferenceError, RuntimeError, TypeError):
        return False


def set_item_channel_state(
        light: bpy.types.Object,
        item,
        coll_type: CollectionType,
        state: ChannelState | str,
        context: bpy.types.Context | None = None,
        *,
        notify: bool = True,
        sync_helpers: bool = True,
) -> bool:
    """Set one direct channel entry without disturbing inherited collection links."""
    light = resolve_original_id(light)
    item = resolve_original_id(item)
    try:
        state = _coerce_channel_state(state)
    except ValueError:
        return False
    if (not are_light_linking_collections_editable(light)
            or not is_original_id(item)):
        return False

    try:
        coll = get_linking_coll(light, coll_type)
    except (AttributeError, ReferenceError, RuntimeError, TypeError):
        coll = None
    if coll is not None and is_internal_world_dome_link(light, item, coll_type):
        return False
    if coll is None:
        if state == ChannelState.OFF:
            return False
        try:
            coll = ensure_linking_coll(coll_type, light, context)
        except (AttributeError, ReferenceError, RuntimeError, TypeError):
            return False
    if coll is None or not coll.is_editable:
        return False

    changed = False
    try:
        if isinstance(item, bpy.types.Object):
            linked = collection_has_object(coll, item)
            if state == ChannelState.OFF:
                if linked:
                    coll.objects.unlink(item)
                    changed = True
            else:
                if not linked:
                    coll.objects.link(item)
                    changed = True
                changed = _set_item_link_state(coll, item, state.value) or changed
        elif isinstance(item, bpy.types.Collection):
            linked = collection_has_child(coll, item)
            if state == ChannelState.OFF:
                if linked:
                    coll.children.unlink(item)
                    changed = True
            else:
                if not linked:
                    coll.children.link(item)
                    changed = True
                changed = _set_item_link_state(coll, item, state.value) or changed
        else:
            return False
    except (AttributeError, ReferenceError, RuntimeError, TypeError):
        return False
    if not changed:
        return False
    if sync_helpers and not sync_safe_helpers_for_light(light):
        return False
    if notify:
        from .overlay import notify_linking_changed
        notify_linking_changed(context)
    return True


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


def apply_linking_mode_to_light(light: bpy.types.Object, mode: str | None = None) -> bool:
    light = resolve_original_id(light)
    if not are_light_linking_collections_editable(light):
        return False
    if mode is None:
        mode = get_linking_mode(light)
    changed = False
    for coll_type in (CollectionType.RECEIVER, CollectionType.BLOCKER):
        coll = get_linking_coll(light, coll_type)
        if coll is None:
            continue
        for index, _coll_obj in enumerate(coll.collection_objects):
            item = coll.objects[index]
            if is_internal_world_dome_link(light, item, coll_type):
                changed = _set_item_link_state(
                    coll, item, StateValue.EXCLUDE.value,
                ) or changed
                continue
            changed = _set_item_link_state(coll, item, mode) or changed
        for index, _coll_child in enumerate(coll.collection_children):
            item = coll.children[index]
            if is_internal_world_dome_link(light, item, coll_type):
                changed = _set_item_link_state(
                    coll, item, StateValue.EXCLUDE.value,
                ) or changed
                continue
            changed = _set_item_link_state(coll, item, mode) or changed
    return changed


def set_linking_edit_mode(
        light: bpy.types.Object,
        edit_mode: str,
        simple_mode: str | None = None,
        context: bpy.types.Context | None = None,
) -> bool:
    """Switch editing models without silently flattening advanced native state.

    Entering ADVANCED only changes the stored UI mode. Returning to SIMPLE
    requires an explicit INCLUDE or EXCLUDE choice and rewrites user entries
    while preserving World Dome infrastructure exclusions.
    """
    light = resolve_original_id(light)
    if not is_light_linking_source_editable(light) or not hasattr(light, "light_helper_property"):
        return False
    if edit_mode not in {"SIMPLE", "ADVANCED"}:
        return False
    props = light.light_helper_property
    if edit_mode == "ADVANCED":
        changed = getattr(props, "linking_edit_mode", "SIMPLE") != "ADVANCED"
        props.linking_edit_mode = "ADVANCED"
    else:
        if simple_mode not in {ChannelState.INCLUDE.value, ChannelState.EXCLUDE.value}:
            return False
        if not are_light_linking_collections_editable(light):
            return False
        changed = (
            getattr(props, "linking_edit_mode", "SIMPLE") != "SIMPLE"
            or props.linking_mode != simple_mode
            or get_effective_linking_mode(light) != simple_mode
        )
        # While still ADVANCED the linking_mode update callback only updates
        # the default, so the explicit flattening remains one controlled step.
        props.linking_mode = simple_mode
        changed = apply_linking_mode_to_light(light, simple_mode) or changed
        props.linking_edit_mode = "SIMPLE"
    if changed:
        from .overlay import notify_linking_changed
        notify_linking_changed(context)
    return changed


def init_light_linking(light: bpy.types.Object, context: bpy.types.Context | None = None) -> bool:
    # Prefer RNA over ops: light_linking_*_collection_new.poll rejects hidden objects.
    light = resolve_original_id(light)
    if not are_light_linking_collections_editable(light):
        return False
    if _ensure_unique_light_owner_uuid(light) is None:
        return False

    linking = light.light_linking
    created = []
    try:
        for coll_type in (CollectionType.RECEIVER, CollectionType.BLOCKER):
            coll = get_linking_coll(light, coll_type)
            if coll is not None:
                continue
            coll = bpy.data.collections.new(_managed_linking_coll_name(light, coll_type))
            created.append((coll_type, coll))
            mark_managed_linking_collection(coll, light)
            if coll_type == CollectionType.RECEIVER:
                linking.receiver_collection = coll
            else:
                linking.blocker_collection = coll
        if not sync_safe_helpers_for_light(light):
            raise RuntimeError("Light linking collections are not editable")
    except (AttributeError, ReferenceError, RuntimeError, TypeError):
        remove_safe_helper_for_light(light)
        for coll_type, coll in reversed(created):
            try:
                if get_linking_coll(light, coll_type) == coll:
                    if coll_type == CollectionType.RECEIVER:
                        linking.receiver_collection = None
                    else:
                        linking.blocker_collection = None
                if coll.is_editable and coll.users == 0:
                    bpy.data.collections.remove(coll)
            except (ReferenceError, RuntimeError, TypeError):
                pass
        return False
    return is_linking_initialized(light)


def ensure_linking_coll(coll_type: CollectionType, light: bpy.types.Object,
                        context: bpy.types.Context | None = None) -> bpy.types.Collection | None:
    if not is_linking_initialized(light):
        if not init_light_linking(light, context):
            return None
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
                         restore_default_when_empty: bool = False) -> bool:
    light = resolve_original_id(light)
    item = resolve_original_id(item)
    if (not are_light_linking_collections_editable(light)
            or not is_original_id(item)):
        return False
    state = get_linking_mode(light) if enabled else ChannelState.OFF
    changed = set_item_channel_state(
        light, item, coll_type, state, context,
        notify=False,
        sync_helpers=False,
    )
    if not changed:
        return False

    if restore_default_when_empty and not enabled and not has_real_linking_items(light):
        if restore_light_linking(light, context):
            return True

    if not sync_safe_helpers_for_light(light):
        return False
    from .overlay import notify_linking_changed
    notify_linking_changed(context)
    return True


def link_item_both_channels(light: bpy.types.Object, item,
                            context: bpy.types.Context | None = None) -> bool:
    if not are_light_linking_collections_editable(light):
        return False
    receiver_changed = link_item_to_channel(
        light, item, CollectionType.RECEIVER, True, context,
    )
    blocker_changed = link_item_to_channel(
        light, item, CollectionType.BLOCKER, True, context,
    )
    return bool(
        (receiver_changed or blocker_changed)
        and is_item_in_channel(light, item, CollectionType.RECEIVER)
        and is_item_in_channel(light, item, CollectionType.BLOCKER)
    )


def toggle_item_both_channels(light: bpy.types.Object, item,
                              context: bpy.types.Context | None = None, *,
                              restore_default_when_empty: bool = False) -> bool | None:
    """Toggle both channels, returning their new state or None when the mutation failed."""
    if not are_light_linking_collections_editable(light):
        return None
    if not is_linking_initialized(light):
        if not init_light_linking(light, context):
            return None
    receiver = is_item_in_channel(light, item, CollectionType.RECEIVER)
    blocker = is_item_in_channel(light, item, CollectionType.BLOCKER)
    enable = not (receiver and blocker)
    receiver_changed = link_item_to_channel(
        light, item, CollectionType.RECEIVER, enable, context,
        restore_default_when_empty=restore_default_when_empty,
    )
    blocker_changed = link_item_to_channel(
        light, item, CollectionType.BLOCKER, enable, context,
        restore_default_when_empty=restore_default_when_empty,
    )
    receiver_now = is_item_in_channel(light, item, CollectionType.RECEIVER)
    blocker_now = is_item_in_channel(light, item, CollectionType.BLOCKER)
    if (receiver_now != enable or blocker_now != enable
            or not (receiver_changed or blocker_changed)):
        return None
    return enable


def is_eevee_engine(engine: str) -> bool:
    return engine in {"BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"}


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


def is_tool_light_source(obj: bpy.types.Object, context: bpy.types.Context | None = None, *,
                         cache: dict | None = None) -> bool:
    obj = resolve_original_id(obj)
    if obj is None:
        return False
    if obj.type == 'LIGHT':
        return True
    return is_emissive_light_source(obj, context, cache=cache)


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
        # Copy before mutating: deselecting while iterating the live
        # ``selected`` collection can skip items.
        for obj in list(view_layer.objects.selected):
            obj.select_set(False)
        view_layer.objects.active = light
        light.select_set(True)
    objects = context.scene.objects[:]
    if light in objects:
        context.scene.light_helper_property.active_object_index = objects.index(light)
    if is_in_view_layer(context, light):
        view_selected(context)


def remove_orphaned_managed_collection(
        coll: bpy.types.Collection | None,
        light: bpy.types.Object) -> None:
    owner_uuid = _light_owner_uuid(light)
    if (coll is None or not coll.is_editable
            or not is_managed_linking_collection(coll)
            or owner_uuid is None
            or coll.get(LIGHT_HELPER_MANAGED_OWNER_KEY) != owner_uuid):
        return
    # Keep a managed collection if the user has linked or instanced it elsewhere.
    if coll.users > 0:
        return
    for obj in bpy.data.objects:
        if not hasattr(obj, "light_linking"):
            continue
        linking = obj.light_linking
        if linking.receiver_collection == coll or linking.blocker_collection == coll:
            return
    bpy.data.collections.remove(coll)


def restore_light_linking(light: bpy.types.Object, context: bpy.types.Context | None = None) -> bool:
    light = resolve_original_id(light)
    if not is_light_linking_source_editable(light):
        return False
    linking = light.light_linking
    receiver = linking.receiver_collection
    blocker = linking.blocker_collection
    if receiver is None and blocker is None:
        return False

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
    remove_safe_helper_for_light(light)
    try:
        linking.receiver_collection = None
        linking.blocker_collection = None
    except (AttributeError, ReferenceError, RuntimeError, TypeError):
        return False
    same_collection = receiver is not None and receiver == blocker
    remove_orphaned_managed_collection(receiver, light)
    if not same_collection:
        remove_orphaned_managed_collection(blocker, light)
    # A converted world dome must remain excluded from Sun lights even when the
    # user restores all ordinary links for that Sun.
    if active_world_domes:
        from .world_environment import ensure_sun_exclusions
        for scene, dome in active_world_domes:
            ensure_sun_exclusions(scene, dome, [light])
    from .overlay import notify_linking_changed
    notify_linking_changed(context)
    return True


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


# Redraw-hot path: the light UIList reads this per row on every redraw.
# Invalidated together with the linking UI cache.
_light_link_count_cache: dict[int, int] = {}


def get_light_link_item_count(light: bpy.types.Object) -> int:
    if light is None:
        return 0
    key = light.as_pointer()
    cached = _light_link_count_cache.get(key)
    if cached is None:
        cached = len(get_all_light_effect_items_state(light))
        _light_link_count_cache[key] = cached
    return cached


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
                for child in item.all_objects:
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
        for selected in list(view_layer.objects.selected):
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
    _light_link_count_cache.clear()
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
    cache_key = (obj.as_pointer(), check_depth)
    if cache is not None:
        if cache_key in cache:
            return cache[cache_key]

    def socket_value_is_positive(socket, *, color: bool = False) -> bool:
        if socket is None:
            return False

        def value_is_positive(value) -> bool:
            if color and not isinstance(value, (int, float)):
                return any(float(component) > 0.0 for component in value[:3])
            return float(value) > 0.0

        if socket.is_linked:
            for link in socket.links:
                from_node = link.from_node
                if from_node.type not in {"VALUE", "RGB"}:
                    # Dynamic inputs cannot be evaluated safely here, but they
                    # can produce a non-zero value at render time.
                    return True
                value = link.from_socket.default_value
                if value_is_positive(value):
                    return True
            return False

        return value_is_positive(socket.default_value)

    def input_by_identifier(node: bpy.types.Node, *identifiers: str):
        return next(
            (socket for socket in node.inputs if socket.identifier in identifiers),
            None,
        )

    def emission_node_is_active(node: bpy.types.Node) -> bool:
        if node.type == "EMISSION":
            color = input_by_identifier(node, "Color")
            strength = input_by_identifier(node, "Strength")
        else:
            color = input_by_identifier(node, "Emission Color", "Emission")
            strength = input_by_identifier(node, "Emission Strength")
        return (
            socket_value_is_positive(color, color=True)
            and socket_value_is_positive(strength)
        )

    def socket_has_emission(socket, depth: int, visiting: set[tuple[int, str]]) -> bool:
        return any(
            node_has_emission(link.from_node, link.from_socket, depth, visiting)
            for link in socket.links
        )

    def node_has_emission(
            node: bpy.types.Node,
            output_socket,
            depth: int,
            visiting: set[tuple[int, str]],
    ) -> bool:
        if depth > check_depth:
            return False

        output_identifier = getattr(output_socket, "identifier", "")
        visit_key = (node.as_pointer(), output_identifier)
        if visit_key in visiting:
            return False
        visiting.add(visit_key)
        try:
            if node.type in {"EMISSION", "BSDF_PRINCIPLED"}:
                return emission_node_is_active(node)

            if node.type == "GROUP":
                node_tree = node.node_tree
                if node_tree is None:
                    return False
                group_output = find_material_output_node(node_tree.nodes)
                if group_output is None:
                    return False
                group_socket = next(
                    (
                        socket for socket in group_output.inputs
                        if socket.identifier == output_identifier
                    ),
                    None,
                )
                return bool(
                    group_socket
                    and socket_has_emission(group_socket, depth + 1, visiting)
                )

            return any(
                socket_has_emission(input_socket, depth + 1, visiting)
                for input_socket in node.inputs
                if input_socket.is_linked
            )
        finally:
            visiting.remove(visit_key)

    result = False
    for material in obj.material_slots:
        mat = material.material
        if mat and mat.use_nodes:
            out_node = find_material_output_node(mat.node_tree.nodes)
            surface = input_by_identifier(out_node, "Surface") if out_node else None
            if surface and socket_has_emission(surface, 0, set()):
                result = True
                break
    if cache is not None:
        cache[cache_key] = result
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
    return any(
        coll is not None and _linking_collection_used_by_other_light(coll, light)
        for coll in (receiver, blocker)
    )


def split_shared_linking_collection(light: bpy.types.Object, coll_type: CollectionType) -> bool:
    light = resolve_original_id(light)
    if not is_light_linking_source_editable(light):
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
    return True


def make_light_linking_single_user(light: bpy.types.Object) -> bool:
    light = resolve_original_id(light)
    if not is_light_linking_source_editable(light):
        return False
    if not has_shared_linking_collections(light):
        return False

    old_helpers = []
    linking = light.light_linking
    for coll in (linking.receiver_collection, linking.blocker_collection):
        if coll is None:
            continue
        for obj in coll.objects:
            if is_safe_helper_object(obj) and obj not in old_helpers:
                old_helpers.append(obj)

    changed = False
    split_collections = []
    if split_shared_linking_collection(light, CollectionType.RECEIVER):
        changed = True
        split_collections.append(light.light_linking.receiver_collection)
    if split_shared_linking_collection(light, CollectionType.BLOCKER):
        changed = True
        split_collections.append(light.light_linking.blocker_collection)
    if changed:
        # Object.copy() duplicates IDProperties, so a copied light inherits the
        # source owner UUID. Give the separated light its own helper identity.
        previous_owner_uuid = _light_owner_uuid(light)
        light[LIGHT_HELPER_OWNER_UUID_KEY] = uuid4().hex
        owner_uuid = _light_owner_uuid(light)
        for coll in split_collections:
            if coll is not None:
                mark_managed_linking_collection(coll, light)
        if previous_owner_uuid is not None and owner_uuid is not None:
            _rebind_managed_collection_owner(light, previous_owner_uuid, owner_uuid)
        sync_safe_helpers_for_light(light)
        for old_helper in old_helpers:
            _remove_orphaned_safe_object(old_helper)
    return changed


def find_duplicate_source_object(obj: bpy.types.Object) -> bpy.types.Object | None:
    """Resolve a duplicate source only from explicit tracking or shared light-linking data."""
    try:
        source = obj.get(LIGHT_HELPER_DUP_SOURCE_KEY)
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
        source = None
    if isinstance(source, bpy.types.Object) and source != obj:
        return source

    if hasattr(obj, "light_linking"):
        linking = obj.light_linking
        for coll in (linking.receiver_collection, linking.blocker_collection):
            if coll is None:
                continue
            for other in bpy.data.objects:
                if other == obj or not hasattr(other, "light_linking"):
                    continue
                other_linking = other.light_linking
                if (other_linking.receiver_collection == coll
                        or other_linking.blocker_collection == coll):
                    return other

    return None


def _can_write_object_idproperties(obj: bpy.types.Object | None) -> bool:
    obj = resolve_original_id(obj)
    try:
        if (not isinstance(obj, bpy.types.Object)
                or not is_original_id(obj)
                or not obj.is_editable):
            return False
        override = getattr(obj, "override_library", None)
        return override is None or not bool(
            getattr(override, "is_system_override", False)
        )
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
        return False


def track_duplicate_source(source: bpy.types.Object, duplicate: bpy.types.Object) -> bool:
    if (source is None or duplicate is None or source == duplicate
            or not _can_write_object_idproperties(duplicate)):
        return False
    try:
        duplicate[LIGHT_HELPER_DUP_SOURCE_KEY] = source
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
        return False
    return True


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
    if not _can_write_object_idproperties(target):
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
                changed = link_item_to_channel(
                    light_obj, target, coll_type, True, context,
                ) or changed
    return changed


def is_duplicate_handled(obj: bpy.types.Object) -> bool:
    try:
        return bool(obj is not None and obj.get(LIGHT_HELPER_DUP_HANDLED_KEY))
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
        return False


def mark_duplicate_handled(obj: bpy.types.Object) -> bool:
    if not _can_write_object_idproperties(obj):
        return False
    try:
        obj[LIGHT_HELPER_DUP_HANDLED_KEY] = True
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
        return False
    return True


def process_duplicated_object(obj: bpy.types.Object, context: bpy.types.Context | None = None) -> bool:
    obj = resolve_original_id(obj)
    if not _can_write_object_idproperties(obj):
        return False
    shared_linking = has_shared_linking_collections(obj)
    if is_duplicate_handled(obj) and not shared_linking:
        return False
    changed = False
    source = find_duplicate_source_object(obj)
    if source is not None and not shared_linking:
        track_duplicate_source(source, obj)

    if shared_linking:
        changed = make_light_linking_single_user(obj) or changed
        if (source is not None and hasattr(obj, "light_helper_property")
                and hasattr(source, "light_helper_property")):
            source_mode = source.light_helper_property.linking_mode
            if obj.light_helper_property.linking_mode != source_mode:
                obj.light_helper_property.linking_mode = source_mode
                changed = True

    if source is not None and obj.type != 'LIGHT':
        source_has_links = is_object_linked_by_any_light(source, context)
        if source_has_links:
            inherited = inherit_light_linking_from_object(obj, source, context)
            changed = inherited or changed
            # Keep the marker clear when inheritance failed, so a later update
            # can retry after a read-only collection becomes editable.
            if not inherited:
                return changed
        # Mark explicitly tracked duplicates after their first processing pass.
        mark_duplicate_handled(obj)
        return changed

    if changed:
        mark_duplicate_handled(obj)
    return changed


def fix_all_shared_light_linking(scene: bpy.types.Scene) -> list[bpy.types.Object]:
    fixed = []
    for obj in scene.objects:
        if not hasattr(obj, "light_linking"):
            continue
        if make_light_linking_single_user(obj):
            fixed.append(obj)
    return fixed


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
        if init_light_linking(obj, context):
            initialized.append(obj)
    return initialized
