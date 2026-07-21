import bpy

_UI_ICON_NAMES: frozenset | None = None


def ui_icon(name: str, fallback: str = "ERROR") -> str:
    """Return ``name`` when the running Blender ships that UILayout icon.

    Icon identifiers differ between Blender versions; an unknown name raises
    TypeError inside ``draw`` and aborts the whole panel. Unknown names fall
    back to ``fallback``. When the icon enum cannot be inspected the name is
    passed through unchanged.
    """
    global _UI_ICON_NAMES
    if _UI_ICON_NAMES is None:
        try:
            items = bpy.types.UILayout.bl_rna.functions["prop"].parameters["icon"].enum_items
            _UI_ICON_NAMES = frozenset(items.keys())
        except (AttributeError, KeyError, TypeError):
            _UI_ICON_NAMES = frozenset()
    if not _UI_ICON_NAMES or name in _UI_ICON_NAMES:
        return name
    if fallback in _UI_ICON_NAMES:
        return fallback
    return "NONE"


def get_light_icon(light):
    data = light.data
    type_icon = {
        'AREA': 'LIGHT_AREA',
        'POINT': 'LIGHT_POINT',
        'SPOT': 'LIGHT_SPOT',
        'SUN': 'LIGHT_SUN',
    }
    if hasattr(data, 'type'):
        return ui_icon(type_icon.get(data.type, 'OBJECT_DATA'), 'OBJECT_DATA')

    return ui_icon('OBJECT_DATA')


def get_item_icon(item: bpy.types.Object | bpy.types.Collection):
    from bpy.types import UILayout

    if isinstance(item, bpy.types.Collection):
        return {'icon': ui_icon("OUTLINER_COLLECTION")}
    elif isinstance(item, bpy.types.Object):
        if item.type == "LIGHT":
            # RNA-provided icons are valid for the running version by construction.
            for i in item.data.bl_rna.properties['type'].enum_items:
                if item.data.type == i.identifier:
                    return {"icon": i.icon}
            return {"icon": ui_icon("OUTLINER_DATA_LIGHT")}
        elif hasattr(item, 'data') and item.data is not None:
            try:
                icon_value = UILayout.icon(item.data)
            except (TypeError, AttributeError):
                pass
            else:
                # 157 is Blender's blank/placeholder icon id.
                if icon_value != 157:
                    return {"icon_value": icon_value}
        if item.type == "EMPTY":
            return {"icon": ui_icon("EMPTY_DATA")}
        else:
            return {"icon": ui_icon("OBJECT_DATA")}
    return {"icon": ui_icon("QUESTION")}
