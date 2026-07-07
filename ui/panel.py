import bpy
from bpy.app.translations import pgettext_iface as p_

from ..utils import (
    CollectionType,
    get_all_light_effect_items_state,
    get_lights_from_effect_obj,
    get_pref,
    is_linking_initialized,
    refresh_drop_poll_context,
)
from ..utils.icon import get_item_icon, get_light_icon


def draw_select_btn(layout, item):
    from ..ops import LLP_OT_select_item
    row = layout.row()
    if isinstance(item, bpy.types.Object):
        row.context_pointer_set("select_item_object", item)
    else:
        row.context_pointer_set("select_item_collection", item)
    row.operator(LLP_OT_select_item.bl_idname, text=item.name, emboss=False, translate=False, **get_item_icon(item))


def draw_toggle_btn(layout,
                    state_info: dict,
                    light_obj: bpy.types.Object,
                    item: bpy.types.Object | bpy.types.Collection):
    """Draw channel toggle buttons for receiver / blocker membership."""
    from ..ops import LLP_OT_toggle_light_linking
    row = layout.row()
    row.context_pointer_set("toggle_light_linking_light_obj", light_obj)

    if isinstance(item, bpy.types.Object):
        row.context_pointer_set("toggle_light_linking_object", item)
    else:
        row.context_pointer_set("toggle_light_linking_collection", item)

    receiver_on = bool(state_info.get(CollectionType.RECEIVER))
    blocker_on = bool(state_info.get(CollectionType.BLOCKER))

    sub = row.row(align=True)
    op = sub.operator(
        LLP_OT_toggle_light_linking.bl_idname, text='', icon='OUTLINER_OB_LIGHT',
        depress=receiver_on,
    )
    op.coll_type = CollectionType.RECEIVER.value

    sub = row.row(align=True)
    op = sub.operator(
        LLP_OT_toggle_light_linking.bl_idname, text='', icon='SHADING_SOLID',
        depress=blocker_on,
    )
    op.coll_type = CollectionType.BLOCKER.value


def draw_remove_button(layout,
                       light_obj: bpy.types.Object,
                       item: bpy.types.Object | bpy.types.Collection):
    from ..ops import LLP_OT_remove_light_linking
    row = layout.row()
    row.context_pointer_set("remove_light_linking_light_obj", light_obj)
    if isinstance(item, bpy.types.Object):
        row.context_pointer_set("remove_light_linking_object", item)
    else:
        row.context_pointer_set("remove_light_linking_collection", item)
    op = row.operator(LLP_OT_remove_light_linking.bl_idname, text='', icon="X", translate=False)
    op.remove_all = True


def draw_add_box(col, context, light_obj):
    from ..ops import LLP_OT_link_selected_objs
    box = col.box()
    row = box.row()
    row.label(text='', icon='ADD')
    row.prop(context.window_manager.light_helper_property, 'light_linking_add_collection', text='',
             icon='OUTLINER_COLLECTION')
    row.prop(context.window_manager.light_helper_property, 'light_linking_add_object', text='',
             icon='OBJECT_DATA')
    row = box.row()
    row.context_pointer_set("link_light_obj", light_obj)
    row.operator(LLP_OT_link_selected_objs.bl_idname, icon='ADD')


class LLT_PT_light_control_panel(bpy.types.Panel):
    bl_label = ""
    bl_idname = "LLT_PT_light_control_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "LH"
    bl_options = {'HEADER_LAYOUT_EXPAND'}

    def draw_header(self, context):
        from ..ops import LLP_OT_question

        pref = get_pref(context)

        layout = self.layout
        row = layout.row(align=True)
        row.label(text="Light Linking")
        row.prop(pref, "moving_view_type", expand=True, icon_only=True)
        row.separator()
        tips = row.operator(LLP_OT_question.bl_idname, text="", icon="QUESTION", emboss=False)
        tips.data = p_(
            """Light Linking Panel
This Panel Lists all the objects that are affected by the selected/pinned light.
Use Exclude/Include mode to control list semantics, and toggle light or shadow per object."""
        )
        row.separator()

    @staticmethod
    def check_support_light_linking(context):
        if bpy.app.version >= (4, 3, 0):
            return context.scene.render.engine in {"CYCLES", "BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"}
        return context.scene.render.engine in {"CYCLES"}

    def draw(self, context):
        layout = self.layout
        if not self.check_support_light_linking(context):
            layout.alert = True
            layout.label(text="This rendering engine does not support light linking")
            layout.label(text=context.scene.render.engine)
            layout = layout.column()
            layout.alert = False
            layout.enabled = False
            layout.active = False
        self.draw_light_list(context, layout)
        self.draw_light_objs_control(context, layout)

    def draw_light_objs_control(self, context, layout):
        from ..ops import LLP_OT_add_light_linking, LLP_OT_clear_light_linking, LLP_OT_instances_data

        refresh_drop_poll_context(context)

        if context.scene.light_helper_property.light_linking_pin:
            light_obj = context.scene.light_helper_property.light_linking_pin_object
        else:
            light_obj = context.object
        if not light_obj:
            return

        not_init = not is_linking_initialized(light_obj)

        col = layout.column()
        row = col.row(align=True)
        row.label(text=f"{light_obj.name}", icon=get_light_icon(light_obj), translate=False)
        row.separator()
        row.prop(context.scene.light_helper_property, 'light_linking_pin', text='', icon='PINNED')
        if LLP_OT_instances_data.poll(context):
            row.operator(LLP_OT_instances_data.bl_idname, text="", icon='RESTRICT_INSTANCED_ON')
        if not not_init:
            row.operator(LLP_OT_clear_light_linking.bl_idname, text="", icon="PANEL_CLOSE")

        if not_init:
            with context.temp_override(add_light_linking_light_obj=light_obj):
                col.context_pointer_set("add_light_linking_light_obj", light_obj)
                col.label(
                    text=p_("Init light linking collections. In Exclude mode, listed objects are excluded from this light."),
                    icon='INFO',
                )
                op = col.operator(LLP_OT_add_light_linking.bl_idname, text='Init', icon='ADD')
                op.init = True
                if LLP_OT_add_light_linking.poll(context) is False:
                    cc = col.column()
                    cc.alert = True
                    cc.label(text="Please select light or can be illuminated object")
                    cc.label(text=pgettext_iface("Current type: ") + context.object.type)
            return

        col.separator()
        col.row(align=True).prop(light_obj.light_helper_property, 'linking_mode', expand=True,
                                  text_ctxt="light_helper_zh_CN")

        obj_state_dict = get_all_light_effect_items_state(light_obj)
        objects = context.scene.objects[:]

        if not obj_state_dict:
            draw_add_box(col, context, light_obj)
            return

        for (item, state_info) in obj_state_dict.items():
            if isinstance(item, bpy.types.Object) and item not in objects:
                continue
            row = col.row(align=False)
            row.scale_x = 1.1
            row.scale_y = 1.1
            draw_select_btn(row, item)
            draw_toggle_btn(row, state_info, light_obj, item)
            row.separator()
            draw_remove_button(row, light_obj, item)

        col.separator()
        draw_add_box(col, context, light_obj)

    def draw_light_list(self, context, layout):
        from ..ops import LLP_OT_switch_filter_show
        from .ui_list import LLT_UL_light

        pref = get_pref(context)
        icon, _ = LLP_OT_switch_filter_show.get_icon(context)

        column = layout.column(align=True)
        column.row(align=True).prop(pref, "light_link_filter_type", expand=True,
                                    text_ctxt="light_helper_zh_CN")

        row = column.row(align=True)
        col = row.column(align=True)
        col.prop(pref, "light_list_filter_type", expand=True, text="", icon_only=True)
        col.separator()
        col.operator(LLP_OT_switch_filter_show.bl_idname, text="", icon=icon)
        row.template_list(LLT_UL_light.__name__, "", context.scene, "objects", context.scene.light_helper_property,
                          "active_object_index")


class LLT_PT_obj_control_panel(bpy.types.Panel):
    bl_label = ""
    bl_idname = "LLT_PT_obj_control_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "LH"
    bl_options = {'HEADER_LAYOUT_EXPAND'}

    def draw_header(self, context):
        from ..ops import LLP_OT_question
        layout = self.layout
        row = layout.row(align=True)
        row.label(text="Object Linking")
        tips = row.operator(LLP_OT_question.bl_idname, text='', icon='QUESTION', emboss=False)
        if tips:
            tips.data = p_(
                """Object Linking Panel
This Panel Lists all the lights that affected the selected/pinned object.
Provides buttons to toggle light or shadow channel per light."""
            )
        row.separator()

    def draw(self, context):
        layout = self.layout
        self.draw_object(context, layout)

    def draw_object(self, context, layout):
        refresh_drop_poll_context(context)

        if context.scene.light_helper_property.object_linking_pin:
            item = context.scene.light_helper_property.object_linking_pin_object
        else:
            item = context.object
        if not item:
            return
        if item.type == 'LIGHT':
            layout.label(text="Light can't be an effected object")
            return

        col = layout.column()
        row = col.row(align=True)
        row.label(text=f"{item.name}", icon=get_light_icon(item), translate=False)
        row.separator()
        row.prop(context.scene.light_helper_property, 'object_linking_pin', text='', icon='PINNED')

        col.separator()

        obj_state_dict = get_lights_from_effect_obj(item, context)
        if len(obj_state_dict) == 0:
            col.label(text='No Link type lights effecting this object', icon='LIGHT')
            box = col.box()
            box.prop(context.window_manager.light_helper_property, 'object_linking_add_object', text='', icon='ADD')
            return

        objects = context.scene.objects[:]
        for (light_obj, state_info) in obj_state_dict.items():
            if light_obj not in objects:
                continue
            row = col.row()
            sub = row.row(align=True)
            sub.label(text='', icon=get_light_icon(light_obj))
            sub.prop(light_obj.light_helper_property, 'linking_mode', text='', text_ctxt="light_helper_zh_CN")
            draw_select_btn(row, light_obj)
            draw_toggle_btn(row, state_info, light_obj, item)
            row.separator()
            draw_remove_button(row, light_obj, item)

        box = col.box()
        box.prop(context.window_manager.light_helper_property, 'object_linking_add_object', text='', icon='ADD')


panel_list = [
    LLT_PT_light_control_panel,
    LLT_PT_obj_control_panel,
]
register_class, unregister_class = bpy.utils.register_classes_factory(panel_list)
_registered_category = None


def _tag_ui_redraw(context):
    if context is None:
        return
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()


def register():
    global _registered_category
    from ..utils import get_pref
    try:
        category = get_pref(bpy.context).panel_name
    except KeyError:
        category = "LH"
    _registered_category = category
    for panel in panel_list:
        panel.bl_category = category
    register_class()


def unregister():
    unregister_class()


def refresh_panel(context):
    global _registered_category
    from ..utils import get_pref
    category = get_pref(context).panel_name
    if category == _registered_category:
        _tag_ui_redraw(context)
        return
    _registered_category = category
    unregister_class()
    for panel in panel_list:
        panel.bl_category = category
    register_class()
    _tag_ui_redraw(context)
