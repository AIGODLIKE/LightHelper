import bpy
from bpy.app.translations import pgettext_iface as p_

from ..utils import (
    ChannelState,
    CollectionType,
    are_light_linking_collections_editable,
    get_all_light_effect_items_state,
    get_item_visibility_restrictions,
    get_effective_item_channel_state,
    get_effective_linking_mode,
    get_item_channel_state,
    get_linking_edit_mode,
    get_lights_from_effect_obj,
    get_pref,
    is_eevee_engine,
    is_light_linking_source_editable,
    is_linking_initialized,
    iter_sorted_linking_items,
    iter_sorted_linking_lights,
    refresh_drop_poll_context,
)
from ..utils.icon import get_item_icon, get_light_icon, ui_icon


def get_panel_light_obj(context) -> bpy.types.Object | None:
    from ..ops.common import get_light_obj
    return get_light_obj(context)


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


def _light_data_context(context, light_obj: bpy.types.Object, engine: str | None = None):
    # Pass the engine id through unchanged. Each Blender version's built-in
    # EEVEE light panels declare that version's real engine id in
    # COMPAT_ENGINES ('BLENDER_EEVEE_NEXT' in 4.2-4.5, 'BLENDER_EEVEE' in
    # 5.0+), so translating between the two breaks the polls on 4.2-4.5.
    if engine is None:
        engine = context.scene.render.engine
    return context.temp_override(
        object=light_obj,
        active_object=light_obj,
        selected_objects=[light_obj],
        selected_editable_objects=[light_obj],
        light=light_obj.data,
        id=light_obj.data,
        engine=engine,
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
                    tooltip: str = "",
                    restore_default_when_empty: bool = False):
    """Draw legacy booleans in Simple mode and native tri-states in Advanced."""
    if get_linking_edit_mode(light_obj) == 'ADVANCED':
        draw_advanced_channel_states(layout, light_obj, item)
        return
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
        LLP_OT_toggle_light_linking.bl_idname, text='', icon=ui_icon('OUTLINER_OB_LIGHT'),
        depress=receiver_on,
    )
    op.coll_type = CollectionType.RECEIVER.value
    op.restore_default_when_empty = restore_default_when_empty
    op.tooltip = tooltip

    sub = row.row(align=True)
    op = sub.operator(
        LLP_OT_toggle_light_linking.bl_idname, text='', icon=ui_icon('SHADING_SOLID'),
        depress=blocker_on,
    )
    op.coll_type = CollectionType.BLOCKER.value
    op.restore_default_when_empty = restore_default_when_empty
    op.tooltip = tooltip


def draw_advanced_channel_states(layout, light_obj, item):
    from ..ops import LLP_OT_set_item_channel_state

    row = layout.row(align=True)
    row.context_pointer_set("channel_state_light", light_obj)
    row.context_pointer_set("channel_state_item", item)
    for coll_type, prefix in (
            (CollectionType.RECEIVER, "L"),
            (CollectionType.BLOCKER, "S")):
        direct = get_item_channel_state(light_obj, item, coll_type)
        effective = get_effective_item_channel_state(light_obj, item, coll_type)
        for state, suffix in (
                (ChannelState.OFF, "."),
                (ChannelState.INCLUDE, "+"),
                (ChannelState.EXCLUDE, "-")):
            op = row.operator(
                LLP_OT_set_item_channel_state.bl_idname,
                text=prefix + suffix,
                depress=direct == state,
            )
            op.coll_type = coll_type.value
            op.state = state.value
        if effective.inherited_from and direct == ChannelState.OFF:
            row.label(text="", icon=ui_icon('OUTLINER_COLLECTION'))


def draw_linking_edit_mode(layout, light_obj, enabled: bool) -> None:
    from ..ops import LLP_OT_set_linking_edit_mode

    edit_mode = get_linking_edit_mode(light_obj)
    row = layout.row(align=True)
    row.enabled = enabled
    row.context_pointer_set("linking_edit_mode_light", light_obj)
    if edit_mode == 'SIMPLE':
        op = row.operator(
            LLP_OT_set_linking_edit_mode.bl_idname,
            text=p_("Simple"),
            depress=True,
        )
        op.edit_mode = 'SIMPLE'
        op.simple_mode = light_obj.light_helper_property.linking_mode
    else:
        for mode, label in (('INCLUDE', "Simple +"), ('EXCLUDE', "Simple -")):
            op = row.operator(
                LLP_OT_set_linking_edit_mode.bl_idname,
                text=p_(label),
            )
            op.edit_mode = 'SIMPLE'
            op.simple_mode = mode
    op = row.operator(
        LLP_OT_set_linking_edit_mode.bl_idname,
        text=p_("Advanced"),
        depress=edit_mode == 'ADVANCED',
    )
    op.edit_mode = 'ADVANCED'

    effective = get_effective_linking_mode(light_obj)
    if edit_mode == 'SIMPLE' and effective != 'MIXED':
        mode_row = layout.row(align=True)
        mode_row.enabled = enabled
        mode_row.prop(
            light_obj.light_helper_property,
            'linking_mode',
            expand=True,
            text_ctxt="light_helper_zh_CN",
        )
    else:
        label = p_("Mixed") if effective == 'MIXED' else p_(effective.title())
        layout.label(text=p_("Native state: %s") % label, icon=ui_icon('INFO'))
        if edit_mode == 'SIMPLE' and effective == 'MIXED':
            layout.label(
                text=p_("Switch to Advanced to preserve and edit mixed states"),
                icon=ui_icon('ERROR'),
            )

def draw_remove_button(layout,
                       light_obj: bpy.types.Object,
                       item: bpy.types.Object | bpy.types.Collection,
                       tooltip: str = "",
                       restore_default_when_empty: bool = False):
    from ..ops import LLP_OT_remove_light_linking
    row = layout.row()
    row.context_pointer_set("remove_light_linking_light_obj", light_obj)
    if isinstance(item, bpy.types.Object):
        row.context_pointer_set("remove_light_linking_object", item)
    else:
        row.context_pointer_set("remove_light_linking_collection", item)
    op = row.operator(LLP_OT_remove_light_linking.bl_idname, text='', icon=ui_icon("X"), translate=False)
    op.remove_all = True
    op.restore_default_when_empty = restore_default_when_empty
    op.tooltip = tooltip


def draw_add_box(col, context, light_obj):
    from ..ops import LLP_OT_link_selected_objs
    box = col.box()
    row = box.row()
    row.label(text='', icon=ui_icon('ADD'))
    row.prop(context.window_manager.light_helper_property, 'light_linking_add_collection', text='',
             icon=ui_icon('OUTLINER_COLLECTION'))
    row.prop(context.window_manager.light_helper_property, 'light_linking_add_object', text='',
             icon=ui_icon('OBJECT_DATA'))
    row = box.row()
    row.context_pointer_set("link_light_obj", light_obj)
    row.operator(LLP_OT_link_selected_objs.bl_idname, icon=ui_icon('ADD'))


class VIEW3D_PT_light_helper_workflow(bpy.types.Panel):
    bl_label = "Lighting Workflow"
    bl_idname = "VIEW3D_PT_light_helper_workflow"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "LH"
    bl_order = 0

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        row.operator(
            "view3d.light_helper_lighting_desk",
            text=p_("Lighting Desk"),
            icon=ui_icon('WINDOW'),
        )
        tool = row.operator(
            "wm.tool_set_by_id",
            text=p_("Placement"),
            icon=ui_icon('ORIENTATION_NORMAL'),
        )
        tool.name = "light_helper.placement"

        row = layout.row(align=True)
        from ..ops.light_mixer import is_false_color_enabled
        false_color_enabled = is_false_color_enabled(context.scene)
        false_color = row.operator(
            "scene.light_helper_toggle_false_color",
            text=p_("Disable False Color") if false_color_enabled else p_("False Color"),
            icon=ui_icon('SEQ_LUMA_WAVEFORM'),
        )
        false_color.enabled = not false_color_enabled
        row.operator(
            "object.light_helper_add_track_target",
            text=p_("Track Target"),
            icon=ui_icon('CON_TRACKTO'),
        )
        row.operator(
            "object.light_helper_remove_track_target",
            text="",
            icon=ui_icon('X'),
        )
        row = layout.row(align=True)
        for action, label in (
                ('SET_ENERGY', "Batch Energy"),
                ('SET_RGB', "Batch RGB"),
                ('SET_KELVIN', "Batch Kelvin")):
            operator = row.operator(
                "object.light_helper_mixer_batch",
                text=p_(label),
            )
            operator.action = action
            operator.target_names_json = "[]"
        if context.collection is not None:
            collection_edit = layout.operator(
                "object.light_helper_mixer_collection_transform",
                text=p_("Collection EV / Tint"),
                icon=ui_icon('OUTLINER_COLLECTION'),
            )
            collection_edit.collection_name = context.collection.name

        profiles = layout.box()
        profiles.label(text=p_("Lighting Profiles"), icon=ui_icon('PRESET'))
        if hasattr(context.scene, "light_helper_profiles"):
            profiles.template_list(
                "UI_UL_list",
                "light_helper_profiles",
                context.scene,
                "light_helper_profiles",
                context.scene,
                "light_helper_profile_index",
                rows=3,
            )
            row = profiles.row(align=True)
            row.operator(
                "scene.light_helper_profile_capture", text=p_("Capture"), icon=ui_icon('ADD'),
            )
            row.operator(
                "scene.light_helper_profile_apply", text=p_("Apply"), icon=ui_icon('CHECKMARK'),
            )
            row.operator(
                "scene.light_helper_profile_remove", text="", icon=ui_icon('REMOVE'),
            )
            row = profiles.row(align=True)
            row.operator(
                "scene.light_helper_profile_import", text=p_("Import"), icon=ui_icon('IMPORT'),
            )
            row.operator(
                "scene.light_helper_profile_export", text=p_("Export"), icon=ui_icon('EXPORT'),
            )

        groups = layout.box()
        groups.label(text=p_("Cycles Light Groups"), icon=ui_icon('RENDERLAYERS'))
        groups.enabled = context.scene.render.engine == 'CYCLES'
        row = groups.row(align=True)
        row.operator(
            "scene.light_helper_light_groups_sync", text=p_("Sync"), icon=ui_icon('FILE_REFRESH'),
        )
        row.operator(
            "scene.light_helper_light_group_build_compositor",
            text=p_("Build Mixer"),
            icon=ui_icon('NODETREE'),
        )
        row.operator(
            "scene.light_helper_light_group_remove_compositor",
            text="",
            icon=ui_icon('X'),
        )
        for setting in getattr(context.scene, "light_helper_light_group_settings", ()):
            row = groups.row(align=True)
            row.prop(setting, "name", text="")
            row.prop(setting, "ev", text="EV")
            row.prop(setting, "tint", text="")
            assign = row.operator(
                "object.light_helper_assign_light_group",
                text="",
                icon=ui_icon('LINKED'),
            )
            assign.group_name = setting.name
            world = row.operator(
                "world.light_helper_assign_light_group",
                text="W",
                icon=ui_icon('WORLD'),
            )
            world.group_name = setting.name
            remove = row.operator(
                "scene.light_helper_light_group_remove",
                text="",
                icon=ui_icon('REMOVE'),
            )
            remove.group_name = setting.name

        studio = layout.box()
        studio.label(text=p_("Studio Shaping"), icon=ui_icon('MESH_PLANE'))
        row = studio.row(align=True)
        cycles = context.scene.render.engine == 'CYCLES'
        scrim = row.row(align=True)
        scrim.enabled = cycles
        scrim.operator(
            "object.light_helper_create_scrim", text=p_("Scrim"), icon=ui_icon('LIGHT_AREA'),
        )
        row.operator(
            "object.light_helper_create_flag", text=p_("Flag"), icon=ui_icon('MESH_PLANE'),
        )
        reflector = row.row(align=True)
        reflector.enabled = cycles
        reflector.operator(
            "object.light_helper_create_reflector",
            text=p_("Reflector"),
            icon=ui_icon('SHADING_RENDERED'),
        )
        try:
            from ..utils.studio import is_studio_object
            is_studio = is_studio_object(context.active_object)
        except (ImportError, AttributeError, ReferenceError, TypeError):
            is_studio = False
        if is_studio:
            row = studio.row(align=True)
            row.operator(
                "object.light_helper_make_studio_single_user",
                text=p_("Make Single User"),
                icon=ui_icon('DUPLICATE'),
            )
            row.operator(
                "object.light_helper_remove_studio_object",
                text=p_("Remove"),
                icon=ui_icon('TRASH'),
            )


class VIEW3D_PT_light_helper_light_control(bpy.types.Panel):
    bl_label = ""
    bl_idname = "VIEW3D_PT_light_helper_light_control"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "LH"
    bl_order = 1
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
        buttons.operator(
            LLP_OT_init_all_light_linking.bl_idname,
            text="",
            icon=ui_icon('OUTLINER_OB_LIGHT'),
        )
        buttons.operator(
            LLP_OT_instances_data_all.bl_idname,
            text="",
            icon=ui_icon('RESTRICT_INSTANCED_ON'),
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
        from ..utils import is_tool_light_source

        refresh_drop_poll_context(context)

        scene_props = context.scene.light_helper_property
        pinned = scene_props.light_linking_pin_object
        invalid_pin = scene_props.light_linking_pin and not is_tool_light_source(pinned, context)
        if invalid_pin:
            warning = layout.box()
            warning.alert = True
            row = warning.row(align=True)
            row.label(text=p_("Pinned light source is unavailable in the current renderer"), icon=ui_icon('INFO'))
            row.prop(scene_props, 'light_linking_pin', text="", icon=ui_icon('PINNED'))

        light_obj = get_panel_light_obj(context)
        if not light_obj:
            layout.label(text=p_("No light selected"), icon=ui_icon('INFO'))
            return

        not_init = not is_linking_initialized(light_obj)
        source_editable = is_light_linking_source_editable(light_obj)
        collections_editable = are_light_linking_collections_editable(light_obj)

        col = layout.column()
        row = col.row(align=True)
        if light_obj.type == 'LIGHT':
            icon = get_light_icon(light_obj)
        else:
            icon = get_item_icon(light_obj).get('icon', 'OBJECT_DATA')
        row.label(text=f"{light_obj.name}", icon=icon, translate=False)
        row.separator()
        row.prop(context.scene.light_helper_property, 'light_linking_pin', text='', icon=ui_icon('PINNED'))
        if LLP_OT_instances_data.poll(context):
            row.operator(LLP_OT_instances_data.bl_idname, text="", icon=ui_icon('RESTRICT_INSTANCED_ON'))
        if not not_init:
            row.operator(LLP_OT_clear_light_linking.bl_idname, text="", icon=ui_icon("PANEL_CLOSE"))

        if not source_editable or not collections_editable:
            warning = col.row()
            warning.alert = True
            warning.label(text=p_("Light linking data is read-only"), icon=ui_icon('INFO'))

        if not_init:
            with context.temp_override(add_light_linking_light_obj=light_obj):
                col.context_pointer_set("add_light_linking_light_obj", light_obj)
                col.label(
                    text=p_(
                        "Init light linking collections. In Exclude mode, listed objects are excluded from this light."),
                    icon=ui_icon('INFO'),
                )
                op = col.operator(LLP_OT_add_light_linking.bl_idname, text='Init', icon=ui_icon('ADD'))
                op.init = True
                if LLP_OT_add_light_linking.poll(context) is False:
                    cc = col.column()
                    cc.alert = True
                    cc.label(text=p_("Please select a light or an object that can be illuminated"))
                    if context.object is not None:
                        cc.label(text=p_("Current type: ") + context.object.type)
            return

        col.separator()
        draw_linking_edit_mode(col, light_obj, collections_editable)

        obj_state_dict = get_all_light_effect_items_state(light_obj)

        if not obj_state_dict:
            draw_add_box(col, context, light_obj)
            return

        for (item, state_info) in iter_sorted_linking_items(obj_state_dict):
            if (isinstance(item, bpy.types.Object)
                    and context.scene.objects.get(item.name) != item):
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
        if context.scene.render.engine == 'CYCLES':
            col.prop(pref, "light_list_filter_type", expand=True, text="", icon_only=True)
        col.separator()
        col.operator(LLP_OT_switch_filter_show.bl_idname, text="", icon=ui_icon(icon))
        col.operator(LLP_OT_invert_filter_show.bl_idname, text="", icon=ui_icon('ARROW_LEFTRIGHT'))
        col.operator(LLP_OT_clear_selected_light_linking.bl_idname, text="", icon=ui_icon('TRASH'))
        col.separator()
        col.prop(pref, "auto_fix_shared_linking", text="", icon=ui_icon('AUTO'), toggle=True)
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
    bl_order = 2
    bl_options = {'HEADER_LAYOUT_EXPAND'}

    @classmethod
    def poll(cls, context):
        return VIEW3D_PT_light_helper_light_control.check_support_light_linking(context)

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
            icon=ui_icon('HIDE_OFF' if scene_props.show_object_linking_panel else 'HIDE_ON'),
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
            col.label(text=p_("No linked objects"), icon=ui_icon('INFO'))
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
        row.prop(context.scene.light_helper_property, 'object_linking_pin', text='', icon=ui_icon('PINNED'))

        col.separator()

        obj_state_dict = get_lights_from_effect_obj(item, context)
        if len(obj_state_dict) == 0:
            col.label(text=p_("No linking lights are affecting this object"), icon=ui_icon('LIGHT'))
            box = col.box()
            box.prop(context.window_manager.light_helper_property, 'object_linking_add_object', text='', icon=ui_icon('ADD'))
            return

        for (light_obj, state_info) in iter_sorted_linking_lights(obj_state_dict):
            if context.scene.objects.get(light_obj.name) != light_obj:
                continue
            tooltip, restricted = get_item_visibility_tooltip(light_obj, context)
            row = col.row()
            if restricted:
                row.active = False
            sub = row.row(align=True)
            sub.label(text='', icon=get_light_icon(light_obj))
            mode = sub.row(align=True)
            mode.enabled = are_light_linking_collections_editable(light_obj)
            if get_linking_edit_mode(light_obj) == 'SIMPLE':
                mode.prop(
                    light_obj.light_helper_property,
                    'linking_mode',
                    text='',
                    text_ctxt="light_helper_zh_CN",
                )
            else:
                effective = get_effective_linking_mode(light_obj)
                mode.label(
                    text=p_("Mixed") if effective == 'MIXED' else p_(effective.title()),
                    icon=ui_icon('MODIFIER'),
                )
            draw_select_btn(row, light_obj, tooltip)
            draw_toggle_btn(
                row, light_obj, item, tooltip,
                restore_default_when_empty=True,
            )
            row.separator()
            draw_remove_button(
                row, light_obj, item, tooltip,
                restore_default_when_empty=True,
            )

        box = col.box()
        box.prop(context.window_manager.light_helper_property, 'object_linking_add_object', text='', icon=ui_icon('ADD'))


class VIEW3D_PT_light_helper_world_environment(bpy.types.Panel):
    bl_label = "World Environment Linking"
    bl_idname = "VIEW3D_PT_light_helper_world_environment"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "LH"
    bl_order = 3
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return context.scene is not None and context.scene.render.engine == 'CYCLES'

    def draw(self, context):
        from ..ops import (
            LLP_OT_convert_world_environment,
            LLP_OT_restore_world_environment,
            LLP_OT_select_world_environment_dome,
            LLP_OT_sync_world_sun_exclusions,
        )
        from ..utils.world_environment import (
            WORLD_DOME_SOURCE_IMAGE_KEY,
            WORLD_DOME_SOURCE_TYPE_KEY,
            WORLD_SOURCE_COLOR,
            WORLD_SOURCE_HDRI,
            get_world_dome,
        )

        layout = self.layout
        scene = context.scene
        props = scene.light_helper_property
        dome = get_world_dome(scene)

        if dome is None:
            world = scene.world
            if world is None:
                box = layout.box()
                box.alert = True
                box.label(text=p_("The current scene has no World"), icon=ui_icon('ERROR'))
            else:
                source = layout.box()
                source.label(text=p_("Source World: %s") % world.name, icon=ui_icon('WORLD_DATA'), translate=False)
                source.label(
                    text=p_("The HDRI or solid-color source is detected when conversion starts"),
                    icon=ui_icon('INFO'),
                )
            convert = layout.row()
            convert.enabled = world is not None
            convert.operator(LLP_OT_convert_world_environment.bl_idname, icon=ui_icon('WORLD'))
            return

        header = layout.box()
        row = header.row(align=True)
        row.label(text=dome.name, icon=ui_icon('SPHERE'), translate=False)
        row.operator(LLP_OT_convert_world_environment.bl_idname, text="", icon=ui_icon('FILE_REFRESH'))
        row.operator(LLP_OT_select_world_environment_dome.bl_idname, text="", icon=ui_icon('RESTRICT_SELECT_OFF'))
        row.prop(props, "world_dome_show_viewport", text="",
                 icon=ui_icon('HIDE_OFF' if props.world_dome_show_viewport else 'HIDE_ON'))
        row.prop(props, "world_dome_lock_selection", text="",
                 icon=ui_icon('LOCKED' if props.world_dome_lock_selection else 'UNLOCKED'))
        image_name = dome.get(WORLD_DOME_SOURCE_IMAGE_KEY, "")
        source_type = dome.get(
            WORLD_DOME_SOURCE_TYPE_KEY,
            WORLD_SOURCE_HDRI if image_name else WORLD_SOURCE_COLOR,
        )
        if image_name:
            header.label(text=p_("HDRI: %s") % image_name, icon=ui_icon('IMAGE_DATA'), translate=False)
        else:
            header.label(text=p_("Source: Solid Color"), icon=ui_icon('COLOR'))

        depths = layout.box()
        depths.label(text=p_("Ray Depth Limits (Cycles)"), icon=ui_icon('NODE_MATERIAL'))
        row = depths.row(align=True)
        row.prop(props, "world_dome_max_bounces")
        row.prop(props, "world_dome_max_diffuse_bounces")
        row = depths.row(align=True)
        row.prop(props, "world_dome_max_glossy_bounces")
        row.prop(props, "world_dome_max_transmission_bounces")
        depths.label(text=p_("0 keeps direct rays and blocks indirect rays of that type"), icon=ui_icon('INFO'))

        visibility = layout.box()
        visibility.label(text=p_("Ray Visibility"), icon=ui_icon('HIDE_OFF'))
        row = visibility.row(align=True)
        row.prop(props, "world_dome_visible_camera", toggle=True)
        row.prop(props, "world_dome_visible_diffuse", toggle=True)
        row.prop(props, "world_dome_visible_glossy", toggle=True)
        row = visibility.row(align=True)
        row.prop(props, "world_dome_visible_transmission", toggle=True)
        row.prop(props, "world_dome_visible_volume_scatter", toggle=True)

        color = layout.box()
        color.label(text=p_("Environment"), icon=ui_icon('WORLD_DATA'))
        if source_type == WORLD_SOURCE_COLOR:
            color.prop(props, "world_dome_color")
        color.prop(props, "world_dome_strength")
        row = color.row(align=True)
        row.prop(props, "world_dome_gamma")
        row.prop(props, "world_dome_saturation")
        color.prop(props, "world_dome_tint_factor", slider=True)
        tint_row = color.row()
        tint_row.enabled = props.world_dome_tint_factor > 0.0
        tint_row.prop(props, "world_dome_tint")
        if source_type == WORLD_SOURCE_HDRI:
            color.prop(props, "world_dome_rotation")

        geometry = layout.box()
        geometry.label(
            text=p_("Dome and Mapping") if source_type == WORLD_SOURCE_HDRI else p_("Dome"),
            icon=ui_icon('MESH_UVSPHERE'),
        )
        geometry.prop(props, "world_dome_radius")
        if source_type == WORLD_SOURCE_HDRI:
            geometry.prop(props, "world_dome_mapping_location")
            geometry.prop(props, "world_dome_mapping_scale")

        suns = layout.box()
        suns.label(text=p_("Sun exclusions are synchronized automatically"), icon=ui_icon('LIGHT_SUN'))
        suns.label(text=p_("Sun exclusions are internal and do not replace user-authored links"), icon=ui_icon('INFO'))
        suns.operator(LLP_OT_sync_world_sun_exclusions.bl_idname, icon=ui_icon('FILE_REFRESH'))

        restore = layout.row()
        restore.alert = True
        restore.operator(LLP_OT_restore_world_environment.bl_idname, icon=ui_icon('LOOP_BACK'))


class VIEW3D_PT_light_helper_light_properties(bpy.types.Panel):
    bl_label = "Light Properties"
    bl_idname = "VIEW3D_PT_light_helper_light_properties"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "LH"
    bl_order = 4
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
        if not is_eevee_engine(context.scene.render.engine):
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
        if not is_eevee_engine(context.scene.render.engine):
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
        if not is_eevee_engine(context.scene.render.engine):
            return False
        return builtin_panel_poll('DATA_PT_EEVEE_light_influence', context, get_panel_blender_light_obj(context))

    def draw(self, context):
        light_obj = get_panel_blender_light_obj(context)
        if light_obj is None:
            return
        draw_builtin_panel('DATA_PT_EEVEE_light_influence', self.layout, context, light_obj)


panel_list = [
    VIEW3D_PT_light_helper_workflow,
    VIEW3D_PT_light_helper_light_control,
    VIEW3D_PT_light_helper_object_control,
    VIEW3D_PT_light_helper_world_environment,
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
