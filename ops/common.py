import bpy
from bpy.app.translations import pgettext_iface as p_

from ..utils import CollectionType

TCTX = "light_helper_zh_CN"


class LightHelperOperator:
    bl_translation_context = TCTX


def enum_coll_type(self, context):
    items = []
    for i in CollectionType:
        items.append((i.value, p_(i.value.title()), ''))
    return items


def get_light_obj(context):
    if context.scene.light_helper_property.light_linking_pin:
        light_obj = context.scene.light_helper_property.light_linking_pin_object
    else:
        light_obj = context.object
    return light_obj


def get_area(context, area_type: str):
    areas = []
    for area in context.screen.areas:
        if area.type == area_type:
            areas.append(area)
    if len(areas) > 0:
        area = max(areas, key=lambda area: area.width * area.height)
        return area
    return None


def format_lights_report(lights: list, message: str, more_message: str, max_display: int = 10) -> str:
    shown = lights[:max_display]
    names = ", ".join(light.name for light in shown)
    extra = len(lights) - len(shown)
    if extra > 0:
        return more_message % (len(lights), names, extra)
    return message % (len(lights), names)


def get_layer_collection_by_coll(context, coll: bpy.types.Collection) -> bpy.types.LayerCollection:
    layer_collection = context.view_layer.layer_collection

    def get_lc(lc: bpy.types.LayerCollection):
        if lc.collection == coll:
            return lc
        for i in lc.children:
            rs = get_lc(i)
            if rs:
                return rs

    return get_lc(layer_collection)


def operator_tooltip_description(properties, default: str) -> str:
    tooltip = properties.tooltip
    if tooltip:
        if default:
            return tooltip + "\n\n" + p_(default)
        return tooltip
    return p_(default) if default else ""
