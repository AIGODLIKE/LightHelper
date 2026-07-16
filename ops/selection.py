import bpy
from bpy.app.translations import pgettext_iface as p_

from ..utils import is_in_view_layer, view_selected
from .common import (
    LightHelperOperator,
    get_area,
    get_layer_collection_by_coll,
    operator_tooltip_description,
)


class LLP_OT_select_item(LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_select_item'
    bl_label = "Select"
    bl_description = "Select the object in the viewport or the collection in the outliner"
    bl_options = {'REGISTER', 'UNDO'}

    tooltip: bpy.props.StringProperty(default="", options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        obj = getattr(context, "select_item_object", None)
        coll = getattr(context, "select_item_collection", None)
        if obj is None and coll is None:
            cls.poll_message_set(p_("No object or collection to select"))
            return False
        return True

    @classmethod
    def description(cls, context, properties):
        return operator_tooltip_description(properties, cls.bl_description)

    def execute(self, context):
        obj = getattr(context, "select_item_object", None)
        coll = getattr(context, "select_item_collection", None)
        if not obj and not coll:
            self.report({'ERROR'}, p_("No object or collection selected"))
            return {"CANCELLED"}

        if obj:
            area_3d = get_area(context, 'VIEW_3D')
            if not area_3d:
                return {"CANCELLED"}
            self.select_obj_in_view3d(context, obj)
        elif coll:
            area_outliner = get_area(context, 'OUTLINER')
            if not area_outliner:
                return {"CANCELLED"}

            with context.temp_override(area=area_outliner, id=coll, region=area_outliner.regions[0]):
                self.select_coll_in_outliner(context, coll)
        view_selected(context)
        return {"FINISHED"}

    def select_obj_in_view3d(self, context, obj: bpy.types.Object):
        if not is_in_view_layer(context, obj):
            return
        view_layer = context.view_layer
        for selected_obj in view_layer.objects.selected:
            selected_obj.select_set(False)
        view_layer.objects.active = obj
        obj.select_set(True)

    def select_coll_in_outliner(self, context, coll: bpy.types.Collection):
        view_layer = context.view_layer
        for selected_obj in view_layer.objects.selected:
            selected_obj.select_set(False)
        lc = get_layer_collection_by_coll(context, coll)
        if not lc:
            self.report({'ERROR'}, p_("Collection not in scene found"))
            return
        view_layer.active_layer_collection = lc
