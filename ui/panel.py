import bpy
from bpy.app.translations import pgettext_iface as p_

from ..utils import (
    CollectionType,
    get_all_light_effect_items_state,
    get_item_visibility_restrictions,
    get_lights_from_effect_obj,
    get_pref,
    is_linking_initialized,
    iter_sorted_linking_items,
    iter_sorted_linking_lights,
    refresh_drop_poll_context,
)
from ..utils.icon import get_item_icon, get_light_icon


def get_panel_light_obj(context) -> bpy.types.Object | None:
    if context.scene.light_helper_property.light_linking_pin:
        obj = context.scene.light_helper_property.light_linking_pin_object
        if obj and obj.type == 'LIGHT':
            return obj
    obj = context.object
    if obj and obj.type == 'LIGHT':
        return obj
    return None


def get_cycles_light_settings_panel():
    return getattr(bpy.types, 'CYCLES_LIGHT_PT_settings', None)


def _cycles_light_settings_context(context, light_obj: bpy.types.Object):
    return context.temp_override(
        object=light_obj,
        active_object=light_obj,
        selected_objects=[light_obj],
        selected_editable_objects=[light_obj],
        light=light_obj.data,
        id=light_obj.data,
        engine='CYCLES',
    )


def cycles_light_settings_poll(context, light_obj: bpy.types.Object) -> bool:
    panel_cls = get_cycles_light_settings_panel()
    if panel_cls is None:
        return False
    with _cycles_light_settings_context(context, light_obj):
        return panel_cls.poll(context)


def draw_cycles_light_settings(layout, context, light_obj: bpy.types.Object) -> None:
    panel_cls = get_cycles_light_settings_panel()
    if panel_cls is None:
        return

    class _PanelUI:
        pass

    _PanelUI.layout = layout
    with _cycles_light_settings_context(context, light_obj):
        if not panel_cls.poll(context):
            return
        panel_cls.draw(_PanelUI(), context)


def get_item_visibility_tooltip(item: bpy.types.Object | bpy.types.Collection) -> tuple[str, bool]:
    viewport_hidden, render_hidden, restricted = get_item_visibility_restrictions(item)
    if not restricted:
        return "", False

    lines = []
    if viewport_hidden:
        lines.append(p_(
            "Hidden in viewport: not visible in the 3D viewport or disabled in the current view layer"
        ))
    if render_hidden:
        lines.append(p_("Disabled for render: excluded from final render output"))
    title = p_('"%s" has visibility restrictions:') % item.name
    return title + "\n" + "\n".join(lines), True


def draw_select_btn(layout, item, tooltip: str = ""):
    from ..ops import LLP_OT_select_item
    row = layout.row()
    if isinstance(item, bpy.types.Object):
        row.context_pointer_set("select_item_object", item)
    else:
        row.context_pointer_set("select_item_collection", item)
    op = row.operator(
        LLP_OT_select_item.bl_idname, text=item.name, emboss=False, translate=False, **get_item_icon(item),
    )
    op.tooltip = tooltip


def draw_toggle_btn(layout,
                    light_obj: bpy.types.Object,
                    item: bpy.types.Object | bpy.types.Collection,
                    tooltip: str = ""):
    """Draw channel toggle buttons for receiver / blocker membership."""
    from ..ops import LLP_OT_toggle_light_linking
    from ..utils import is_item_in_channel
    row = layout.row()
    row.context_pointer_set("toggle_light_linking_light_obj", light_obj)

    if isinstance(item, bpy.types.Object):
        row.context_pointer_set("toggle_light_linking_object", item)
    else:
        row.context_pointer_set("toggle_light_linking_collection", item)

    receiver_on = is_item_in_channel(light_obj, item, CollectionType.RECEIVER)
    blocker_on = is_item_in_channel(light_obj, item, CollectionType.BLOCKER)

    sub = row.row(align=True)
    op = sub.operator(
        LLP_OT_toggle_light_linking.bl_idname, text='', icon='OUTLINER_OB_LIGHT',
        depress=receiver_on,
    )
    op.coll_type = CollectionType.RECEIVER.value
    op.tooltip = tooltip

    sub = row.row(align=True)
    op = sub.operator(
        LLP_OT_toggle_light_linking.bl_idname, text='', icon='SHADING_SOLID',
        depress=blocker_on,
    )
    op.coll_type = CollectionType.BLOCKER.value
    op.tooltip = tooltip


def draw_remove_button(layout,
                       light_obj: bpy.types.Object,
                       item: bpy.types.Object | bpy.types.Collection,
                       tooltip: str = ""):
    from ..ops import LLP_OT_remove_light_linking
    row = layout.row()
    row.context_pointer_set("remove_light_linking_light_obj", light_obj)
    if isinstance(item, bpy.types.Object):
        row.context_pointer_set("remove_light_linking_object", item)
    else:
        row.context_pointer_set("remove_light_linking_collection", item)
    op = row.operator(LLP_OT_remove_light_linking.bl_idname, text='', icon="X", translate=False)
    op.remove_all = True
    op.tooltip = tooltip


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
        from ..ops import (
            LLP_OT_question,
            LLP_OT_init_all_light_linking,
            LLP_OT_instances_data_all,
        )

        pref = get_pref(context)
        layout = self.layout

        action_row = layout.row(align=True)
        action_row.label(text=p_("Light Linking"))
        action_row.separator(factor=1.5)
        buttons = action_row.row(align=True)
        init_row = buttons.row(align=True)
        init_row.enabled = LLP_OT_init_all_light_linking.poll(context)
        init_row.operator(
            LLP_OT_init_all_light_linking.bl_idname,
            text="",
            icon='OUTLINER_OB_LIGHT',
        )
        inst_row = buttons.row(align=True)
        inst_row.enabled = LLP_OT_instances_data_all.poll(context)
        inst_row.operator(
            LLP_OT_instances_data_all.bl_idname,
            text="",
            icon='RESTRICT_INSTANCED_ON',
        )

        view_row = layout.row(align=True)
        view_row.prop(pref, "moving_view_type", expand=True, icon_only=True)
        view_row.separator()
        tips = view_row.operator(LLP_OT_question.bl_idname, text="", icon="QUESTION", emboss=False)
        tips.data = p_(
            """Light Linking Panel
This Panel Lists all the objects that are affected by the selected/pinned light.
Use Exclude/Include mode to control list semantics, and toggle light or shadow per object."""
        )
        view_row.separator()

    @staticmethod
    def check_support_light_linking(context):
        if bpy.app.version >= (4, 3, 0):
            return context.scene.render.engine in {"CYCLES", "BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"}
        return context.scene.render.engine in {"CYCLES"}

    def draw(self, context):
        layout = self.layout
        if not self.check_support_light_linking(context):
            layout.alert = True
            layout.label(text=p_("This rendering engine does not support light linking"))
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

        light_obj = get_panel_light_obj(context)
        if not light_obj:
            layout.label(text=p_("No light selected"), icon='INFO')
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
                    cc.label(text=p_("Please select light or can be illuminated object"))
                    cc.label(text=p_("Current type: ") + context.object.type)
            return

        col.separator()
        col.row(align=True).prop(light_obj.light_helper_property, 'linking_mode', expand=True,
                                  text_ctxt="light_helper_zh_CN")

        obj_state_dict = get_all_light_effect_items_state(light_obj)
        objects = context.scene.objects[:]

        if not obj_state_dict:
            draw_add_box(col, context, light_obj)
            return

        for (item, state_info) in iter_sorted_linking_items(obj_state_dict):
            if isinstance(item, bpy.types.Object) and item not in objects:
                continue
            tooltip, restricted = get_item_visibility_tooltip(item)
            row = col.row(align=False)
            if restricted:
                row.active = False
            row.scale_x = 1.1
            row.scale_y = 1.1
            draw_select_btn(row, item, tooltip)
            draw_toggle_btn(row, light_obj, item, tooltip)
            row.separator()
            draw_remove_button(row, light_obj, item, tooltip)

        col.separator()
        draw_add_box(col, context, light_obj)

    def draw_light_list(self, context, layout):
        from ..ops import LLP_OT_switch_filter_show, LLP_OT_invert_filter_show
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
        invert_row = col.row(align=True)
        invert_row.enabled = LLP_OT_invert_filter_show.poll(context)
        invert_row.operator(LLP_OT_invert_filter_show.bl_idname, text="", icon='ARROW_LEFTRIGHT')
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
        row.label(text=p_("Object Linking"))
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
            layout.label(text=p_("Light can't be an effected object"))
            return

        col = layout.column()
        row = col.row(align=True)
        row.label(text=f"{item.name}", icon=get_light_icon(item), translate=False)
        row.separator()
        row.prop(context.scene.light_helper_property, 'object_linking_pin', text='', icon='PINNED')

        col.separator()

        obj_state_dict = get_lights_from_effect_obj(item, context)
        if len(obj_state_dict) == 0:
            col.label(text=p_('No Link type lights effecting this object'), icon='LIGHT')
            box = col.box()
            box.prop(context.window_manager.light_helper_property, 'object_linking_add_object', text='', icon='ADD')
            return

        objects = context.scene.objects[:]
        for (light_obj, state_info) in iter_sorted_linking_lights(obj_state_dict):
            if light_obj not in objects:
                continue
            tooltip, restricted = get_item_visibility_tooltip(light_obj)
            row = col.row()
            if restricted:
                row.active = False
            sub = row.row(align=True)
            sub.label(text='', icon=get_light_icon(light_obj))
            sub.prop(light_obj.light_helper_property, 'linking_mode', text='', text_ctxt="light_helper_zh_CN")
            draw_select_btn(row, light_obj, tooltip)
            draw_toggle_btn(row, light_obj, item, tooltip)
            row.separator()
            draw_remove_button(row, light_obj, item, tooltip)

        box = col.box()
        box.prop(context.window_manager.light_helper_property, 'object_linking_add_object', text='', icon='ADD')


class LLT_PT_light_settings(bpy.types.Panel):
    bl_label = "Settings"
    bl_idname = "LLT_PT_light_settings"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "LH"
    bl_options = set()

    @classmethod
    def poll(cls, context):
        if context.scene.render.engine != 'CYCLES':
            return False
        light_obj = get_panel_light_obj(context)
        if light_obj is None:
            return False
        return cycles_light_settings_poll(context, light_obj)

    def draw(self, context):
        light_obj = get_panel_light_obj(context)
        if light_obj is None:
            return
        draw_cycles_light_settings(self.layout, context, light_obj)


panel_list = [
    LLT_PT_light_control_panel,
    LLT_PT_obj_control_panel,
    LLT_PT_light_settings,
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
    category = "LH"
    try:
        category = get_pref(bpy.context).panel_name
    except (KeyError, AttributeError, TypeError):
        pass
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
