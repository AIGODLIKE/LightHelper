EMPTY = 0
_filter_list_cache = {}


def invalidate_filter_cache():
    _filter_list_cache.clear()


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
    return [
        context.scene.objects[i]
        for i, flag in enumerate(filter_list(context, bitflag=True))
        if flag
    ]
