EMPTY = 0


def filter_list(context, bitflag=None):
    from .utils import check_material_including_emission, get_pref, check_link

    pref = get_pref()
    filter_type = pref.light_list_filter_type
    link_type = pref.light_link_filter_type
    search_deep = pref.node_search_depth

    objects = context.scene.objects[:]

    flt_flags = []
    if not flt_flags:
        flt_flags = [bitflag] * len(objects)

    for idx, obj in enumerate(objects):
        if filter_type == "ALL":
            is_show = obj.type == "LIGHT" or check_material_including_emission(obj, search_deep)
            flag = bitflag if is_show else EMPTY
        elif filter_type == "LIGHT":
            flag = bitflag if obj.type == 'LIGHT' else EMPTY
        elif filter_type == "EMISSION":
            flag = bitflag if check_material_including_emission(obj, search_deep) else EMPTY
        else:
            flag = EMPTY

        if flag == bitflag and link_type != "ALL":
            is_link = check_link(obj)

            is_ok = link_type == "LINK" and is_link or link_type == "NOT_LINK" and not is_link
            flag = bitflag if is_ok else EMPTY
        flt_flags[idx] = flag
    return flt_flags


def filter_objects(context):
    l = []
    for i, v in enumerate(filter_list(context, bitflag=True)):
        if v is True:
            l.append(context.scene.objects[i])
    return l
