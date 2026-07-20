EMPTY = 0
_filter_list_cache = {}
_filtered_objects_cache = {}
_filter_visibility_state_cache = {}
_filter_cache_generation = 0


def invalidate_filter_cache():
    global _filter_cache_generation
    _filter_list_cache.clear()
    _filtered_objects_cache.clear()
    _filter_visibility_state_cache.clear()
    _filter_cache_generation += 1


def get_filter_cache_generation() -> int:
    return _filter_cache_generation


def _filter_cache_key(context, bitflag, pref):
    scene = context.scene
    return (
        id(scene),
        len(scene.objects),
        pref.light_list_filter_type,
        pref.light_link_filter_type,
        pref.node_search_depth,
        scene.render.engine,
        bitflag,
    )


def filter_list(context, bitflag=None):
    from .handlers import ensure_filter_cache_invalidation_handler
    from .utils import check_link, get_pref, is_emissive_light_source

    ensure_filter_cache_invalidation_handler()
    pref = get_pref(context)
    cache_key = _filter_cache_key(context, bitflag, pref)
    cached = _filter_list_cache.get(cache_key)
    if cached is not None:
        return cached

    filter_type = pref.light_list_filter_type
    if context.scene.render.engine != "CYCLES":
        # EEVEE does not expose emissive meshes as Light Linking sources.
        # Keep the stored Cycles preference intact, but present a useful
        # native-light list while the unsupported filter UI is hidden.
        filter_type = "LIGHT"
    link_type = pref.light_link_filter_type
    search_deep = pref.node_search_depth

    objects = context.scene.objects[:]
    flt_flags = [bitflag] * len(objects)
    emission_cache = {}

    for idx, obj in enumerate(objects):
        if filter_type == "ALL":
            is_show = obj.type == "LIGHT" or is_emissive_light_source(
                obj, context, search_depth=search_deep, cache=emission_cache)
            flag = bitflag if is_show else EMPTY
        elif filter_type == "LIGHT":
            flag = bitflag if obj.type == 'LIGHT' else EMPTY
        elif filter_type == "EMISSION":
            flag = bitflag if is_emissive_light_source(
                obj, context, search_depth=search_deep, cache=emission_cache) else EMPTY
        else:
            flag = EMPTY

        if flag == bitflag and link_type != "ALL":
            is_link = check_link(obj)
            is_ok = (link_type == "LINK" and is_link) or (link_type == "NOT_LINK" and not is_link)
            flag = bitflag if is_ok else EMPTY
        flt_flags[idx] = flag

    if len(_filter_list_cache) > 16:
        _filter_list_cache.clear()
    _filter_list_cache[cache_key] = flt_flags
    return flt_flags


def filter_objects(context):
    from .utils import get_pref

    key = (_filter_cache_key(context, True, get_pref(context)), _filter_cache_generation)
    cached = _filtered_objects_cache.get(key)
    if cached is not None:
        return cached
    objects = tuple(
        context.scene.objects[i]
        for i, flag in enumerate(filter_list(context, bitflag=True))
        if flag
    )
    if len(_filtered_objects_cache) > 16:
        _filtered_objects_cache.clear()
    _filtered_objects_cache[key] = objects
    return objects


def get_filter_visibility_state(context):
    from .utils import get_pref

    key = (_filter_cache_key(context, True, get_pref(context)), _filter_cache_generation)
    cached = _filter_visibility_state_cache.get(key)
    if cached is not None:
        return cached
    last_show = None
    for obj in filter_objects(context):
        show = obj.light_helper_property.show_in_view
        if last_show is None:
            last_show = show
        elif show != last_show:
            result = ('REMOVE', show)
            break
    else:
        result = ('HIDE_OFF', True) if last_show is True else ('HIDE_ON', False)
    if len(_filter_visibility_state_cache) > 16:
        _filter_visibility_state_cache.clear()
    _filter_visibility_state_cache[key] = result
    return result
