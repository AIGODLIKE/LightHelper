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
    from ..utils import is_tool_light_source
    if context.scene.light_helper_property.light_linking_pin:
        obj = context.scene.light_helper_property.light_linking_pin_object
        if obj and is_tool_light_source(obj, context):
            return obj
    obj = context.object
    if obj and is_tool_light_source(obj, context):
        return obj
    return None


def get_panel_blender_light_obj(context) -> bpy.types.Object | None:
    """Light Properties panels: Blender light objects only, not emissive meshes."""
    if context.scene.light_helper_property.light_linking_pin:
        obj = context.scene.light_helper_property.light_linking_pin_object
        if obj and obj.type == 'LIGHT':
            return obj
    obj = context.object
    if obj and obj.type == 'LIGHT':
        return obj
    return None


def get_panel_effect_obj(context) -> bpy.types.Object | None:
    from ..utils import is_linkable_object
    if context.scene.light_helper_property.object_linking_pin:
        obj = context.scene.light_helper_property.object_linking_pin_object
    else:
        obj = context.object
    if obj is not None and is_linkable_object(obj):
        return obj
    return None


def get_builtin_panel(panel_name: str):
    return getattr(bpy.types, panel_name, None)


def _is_eevee_engine(engine: str) -> bool:
    return engine in {'BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT'}


def _panel_engine_override(engine: str) -> str:
    # Built-in EEVEE light panels declare COMPAT_ENGINES = {'BLENDER_EEVEE'}.
    if engine == 'BLENDER_EEVEE_NEXT':
        return 'BLENDER_EEVEE'
    return engine


def _light_data_context(context, light_obj: bpy.types.Object, engine: str | None = None):
    if engine is None:
        engine = context.scene.render.engine
    return context.temp_override(
        object=light_obj,
        active_object=light_obj,
        selected_objects=[light_obj],
        selected_editable_objects=[light_obj],
        light=light_obj.data,
        id=light_obj.data,
        engine=_panel_engine_override(engine),
    )


def builtin_panel_poll(panel_name: str, context, light_obj: bpy.types.Object,
                       engine: str | None = None) -> bool:
    panel_cls = get_builtin_panel(panel_name)
    if panel_cls is None or light_obj is None or light_obj.type != 'LIGHT':
        return False
    with _light_data_context(context, light_obj, engine):
        return panel_cls.poll(context)


def draw_builtin_panel(panel_name: str, layout, context, light_obj: bpy.types.Object,
                       engine: str | None = None) -> None:
    panel_cls = get_builtin_panel(panel_name)
    if panel_cls is None:
        return

    class _PanelUI:
        bl_space_type = 'PROPERTIES'

    ui = _PanelUI()
    ui.layout = layout
    with _light_data_context(context, light_obj, engine):
        if not panel_cls.poll(context):
            return
        panel_cls.draw(ui, context)


def draw_builtin_panel_header(panel_name: str, layout, context, light_obj: bpy.types.Object,
                              engine: str | None = None) -> None:
    panel_cls = get_builtin_panel(panel_name)
    if panel_cls is None or not hasattr(panel_cls, "draw_header"):
        return

    class _PanelUI:
        bl_space_type = 'PROPERTIES'

    ui = _PanelUI()
    ui.layout = layout
    with _light_data_context(context, light_obj, engine):
        if not panel_cls.poll(context):
            return
        panel_cls.draw_header(ui, context)


def draw_light_ev_controls(layout, context) -> None:
    from ..ops import LLP_OT_adjust_light_ev
    row = layout.row(align=True)
    enabled = LLP_OT_adjust_light_ev.poll(context)
    row.enabled = enabled
    for label, ev in (("-1 EV", -1.0), ("-0.5 EV", -0.5), ("+0.5 EV", 0.5), ("+1 EV", 1.0)):
        op = row.operator(LLP_OT_adjust_light_ev.bl_idname, text=label)
        op.ev = ev


def get_item_visibility_tooltip(
    item: bpy.types.Object | bpy.types.Collection,
    context: bpy.types.Context | None = None,
) -> tuple[str, bool]:
    viewport_hidden, render_hidden, restricted = get_item_visibility_restrictions(item, context)
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


class VIEW3D_PT_light_helper_light_control(bpy.types.Panel):
    bl_label = ""
    bl_idname = "VIEW3D_PT_light_helper_light_control"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "LH"
    bl_order = 0
    bl_options = {'HEADER_LAYOUT_EXPAND'}

    def draw_header(self, context):
        from ..ops import (
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
        if light_obj.type == 'LIGHT':
            icon = get_light_icon(light_obj)
        else:
            icon = get_item_icon(light_obj).get('icon', 'OBJECT_DATA')
        row.label(text=f"{light_obj.name}", icon=icon, translate=False)
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
                    text=p_(
                        "Init light linking collections. In Exclude mode, listed objects are excluded from this light."),
                    icon='INFO',
                )
                op = col.operator(LLP_OT_add_light_linking.bl_idname, text='Init', icon='ADD')
                op.init = True
                if LLP_OT_add_light_linking.poll(context) is False:
                    cc = col.column()
                    cc.alert = True
                    cc.label(text=p_("Please select a light or an object that can be illuminated"))
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
            tooltip, restricted = get_item_visibility_tooltip(item, context)
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
        from ..ops import (
            LLP_OT_clear_selected_light_linking,
            LLP_OT_invert_filter_show,
            LLP_OT_switch_filter_show,
        )
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
        clear_row = col.row(align=True)
        clear_row.enabled = LLP_OT_clear_selected_light_linking.poll(context)
        clear_row.operator(LLP_OT_clear_selected_light_linking.bl_idname, text="", icon='TRASH')
        col.separator()
        col.prop(pref, "auto_fix_shared_linking", text="", icon='AUTO', toggle=True)
        row.template_list(
            LLT_UL_light.__name__, "",
            context.scene, "objects",
            context.scene.light_helper_property, "active_object_index",
            rows=7,
        )


class VIEW3D_PT_light_helper_object_control(bpy.types.Panel):
    bl_label = ""
    bl_idname = "VIEW3D_PT_light_helper_object_control"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "LH"
    bl_order = 1
    bl_options = {'HEADER_LAYOUT_EXPAND'}

    @classmethod
    def poll(cls, context):
        if not VIEW3D_PT_light_helper_light_control.check_support_light_linking(context):
            return False
        from ..utils import iter_objects_linked_by_lights
        if iter_objects_linked_by_lights(context):
            return True
        return get_panel_effect_obj(context) is not None

    def draw_header(self, context):
        layout = self.layout
        row = layout.row(align=True)
        row.label(text=p_("Object Linking"))
        row.separator()
        scene_props = context.scene.light_helper_property
        row.prop(
            scene_props,
            "show_object_linking_panel",
            text="",
            icon='HIDE_OFF' if scene_props.show_object_linking_panel else 'HIDE_ON',
            emboss=False,
        )
        row.separator()
        row.separator()

    def draw(self, context):
        layout = self.layout
        if context.scene.light_helper_property.show_object_linking_panel:
            self.draw_linked_object_list(context, layout)
        self.draw_object(context, layout)

    def draw_linked_object_list(self, context, layout):
        from .ui_list import LLT_UL_linked_object
        from ..utils import iter_objects_linked_by_lights

        linked = iter_objects_linked_by_lights(context)
        col = layout.column(align=True)
        col.label(text=p_("Linked Objects"))
        if not linked:
            col.label(text=p_("No linked objects"), icon='INFO')
            return
        col.template_list(
            LLT_UL_linked_object.__name__,
            "",
            context.scene,
            "objects",
            context.scene.light_helper_property,
            "active_linked_object_index",
            rows=4,
        )

    def draw_object(self, context, layout):
        refresh_drop_poll_context(context)

        item = get_panel_effect_obj(context)
        if item is None:
            return

        col = layout.column()
        row = col.row(align=True)
        row.label(text=f"{item.name}", icon=get_light_icon(item), translate=False)
        row.separator()
        row.prop(context.scene.light_helper_property, 'object_linking_pin', text='', icon='PINNED')

        col.separator()

        obj_state_dict = get_lights_from_effect_obj(item, context)
        if len(obj_state_dict) == 0:
            col.label(text=p_("No linking lights are affecting this object"), icon='LIGHT')
            box = col.box()
            box.prop(context.window_manager.light_helper_property, 'object_linking_add_object', text='', icon='ADD')
            return

        objects = context.scene.objects[:]
        for (light_obj, state_info) in iter_sorted_linking_lights(obj_state_dict):
            if light_obj not in objects:
                continue
            tooltip, restricted = get_item_visibility_tooltip(light_obj, context)
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


class VIEW3D_PT_light_helper_light_properties(bpy.types.Panel):
    bl_label = "Light Properties"
    bl_idname = "VIEW3D_PT_light_helper_light_properties"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "LH"
    bl_order = 2
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return get_panel_blender_light_obj(context) is not None

    def draw_header(self, context):
        light_obj = get_panel_blender_light_obj(context)
        if light_obj is None:
            return
        self.layout.label(text=light_obj.name, icon=get_light_icon(light_obj), translate=False)

    def draw(self, context):
        draw_light_ev_controls(self.layout, context)


class VIEW3D_PT_light_helper_cycles_light(bpy.types.Panel):
    bl_label = "Light"
    bl_idname = "VIEW3D_PT_light_helper_cycles_light"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "LH"
    bl_parent_id = "VIEW3D_PT_light_helper_light_properties"
    bl_options = set()

    @classmethod
    def poll(cls, context):
        if context.scene.render.engine != 'CYCLES':
            return False
        return builtin_panel_poll('CYCLES_LIGHT_PT_light', context, get_panel_blender_light_obj(context), 'CYCLES')

    def draw(self, context):
        light_obj = get_panel_blender_light_obj(context)
        if light_obj is None:
            return
        draw_builtin_panel('CYCLES_LIGHT_PT_light', self.layout, context, light_obj, 'CYCLES')


class VIEW3D_PT_light_helper_light_settings(bpy.types.Panel):
    bl_label = "Settings"
    bl_idname = "VIEW3D_PT_light_helper_light_settings"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "LH"
    bl_parent_id = "VIEW3D_PT_light_helper_light_properties"
    bl_options = set()

    @classmethod
    def poll(cls, context):
        if context.scene.render.engine != 'CYCLES':
            return False
        return builtin_panel_poll('CYCLES_LIGHT_PT_settings', context, get_panel_blender_light_obj(context), 'CYCLES')

    def draw(self, context):
        light_obj = get_panel_blender_light_obj(context)
        if light_obj is None:
            return
        draw_builtin_panel('CYCLES_LIGHT_PT_settings', self.layout, context, light_obj, 'CYCLES')


class VIEW3D_PT_light_helper_eevee_light(bpy.types.Panel):
    bl_label = "Light"
    bl_idname = "VIEW3D_PT_light_helper_eevee_light"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "LH"
    bl_parent_id = "VIEW3D_PT_light_helper_light_properties"
    bl_options = set()

    @classmethod
    def poll(cls, context):
        if not _is_eevee_engine(context.scene.render.engine):
            return False
        return builtin_panel_poll('DATA_PT_EEVEE_light', context, get_panel_blender_light_obj(context))

    def draw(self, context):
        light_obj = get_panel_blender_light_obj(context)
        if light_obj is None:
            return
        draw_builtin_panel('DATA_PT_EEVEE_light', self.layout, context, light_obj)


class VIEW3D_PT_light_helper_eevee_light_shadow(bpy.types.Panel):
    bl_label = "Shadow"
    bl_idname = "VIEW3D_PT_light_helper_eevee_light_shadow"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "LH"
    bl_parent_id = "VIEW3D_PT_light_helper_eevee_light"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        if not _is_eevee_engine(context.scene.render.engine):
            return False
        return builtin_panel_poll('DATA_PT_EEVEE_light_shadow', context, get_panel_blender_light_obj(context))

    def draw_header(self, context):
        light_obj = get_panel_blender_light_obj(context)
        if light_obj is None:
            return
        draw_builtin_panel_header('DATA_PT_EEVEE_light_shadow', self.layout, context, light_obj)

    def draw(self, context):
        light_obj = get_panel_blender_light_obj(context)
        if light_obj is None:
            return
        draw_builtin_panel('DATA_PT_EEVEE_light_shadow', self.layout, context, light_obj)


class VIEW3D_PT_light_helper_eevee_light_influence(bpy.types.Panel):
    bl_label = "Influence"
    bl_idname = "VIEW3D_PT_light_helper_eevee_light_influence"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "LH"
    bl_parent_id = "VIEW3D_PT_light_helper_eevee_light"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        if not _is_eevee_engine(context.scene.render.engine):
            return False
        return builtin_panel_poll('DATA_PT_EEVEE_light_influence', context, get_panel_blender_light_obj(context))

    def draw(self, context):
        light_obj = get_panel_blender_light_obj(context)
        if light_obj is None:
            return
        draw_builtin_panel('DATA_PT_EEVEE_light_influence', self.layout, context, light_obj)


panel_list = [
    VIEW3D_PT_light_helper_light_control,
    VIEW3D_PT_light_helper_object_control,
    VIEW3D_PT_light_helper_light_properties,
    VIEW3D_PT_light_helper_cycles_light,
    VIEW3D_PT_light_helper_light_settings,
    VIEW3D_PT_light_helper_eevee_light,
    VIEW3D_PT_light_helper_eevee_light_shadow,
    VIEW3D_PT_light_helper_eevee_light_influence,
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
