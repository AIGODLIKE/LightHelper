import bpy


def get_light_icon(light):
    data = light.data
    type_icon = {
        'AREA': 'LIGHT_AREA',
        'POINT': 'LIGHT_POINT',
        'SPOT': 'LIGHT_SPOT',
        'SUN': 'LIGHT_SUN',
    }
    if hasattr(data, 'type'):
        return type_icon.get(data.type, 'OBJECT_DATA')

    return 'OBJECT_DATA'


def get_item_icon(item: bpy.types.Object | bpy.types.Collection):
    from bpy.types import UILayout

    if isinstance(item, bpy.types.Collection):
        return {'icon': "OUTLINER_COLLECTION"}
    elif isinstance(item, bpy.types.Object):
        if item.type == "LIGHT":
            from .utils import check_link
            for i in item.data.bl_rna.properties['type'].enum_items:
                if item.data.type == i.identifier:
                    return {"icon": i.icon}
            return {"icon": "OUTLINER_OB_LIGHT" if check_link(item) else "OUTLINER_DATA_LIGHT"}
        elif hasattr(item, 'data'):
            try:
                icon_value = UILayout.icon(item.data)
                if icon_value != 157:
                    return {"icon_value": icon_value}
            except Exception:
                ...
        if item.type == "EMPTY":
            return {"icon": "EMPTY_DATA"}
        else:
            return {"icon": "OBJECT_DATA"}
    return {"icon": "QUESTION"}
