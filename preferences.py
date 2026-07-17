import bpy
from bpy.props import StringProperty, EnumProperty, IntProperty, FloatProperty
from bpy.types import AddonPreferences

is_50 = bpy.app.version >= (5, 0, 0)


def update_filter_settings(_self, context):
    from .filter import invalidate_filter_cache
    invalidate_filter_cache()


class LLT_AddonPreferences(AddonPreferences):
    bl_idname = __package__

    def update_panel(self, context):
        from .ui.panel import refresh_panel
        refresh_panel(context)

    panel_name: StringProperty(name="Panel Name", default="LH", update=update_panel)
    node_search_depth: IntProperty(
        name="Emission Node Search Depth",
        description=(
            "Maximum recursion depth when walking material node trees to detect emissive objects "
            "shown in the light list. Higher values may cause stuttering with complex materials"
        ),
        default=10, max=50, min=3, update=update_filter_settings,
    )
    light_list_filter_type: EnumProperty(
        name="List Filter Type",
        default="ALL",
        translation_context="light_helper_zh_CN",
        update=update_filter_settings,
        items=[
            ("ALL", "All", "Display lights and objects that can emit light", "SCENE_DATA", 0),
            ("LIGHT", "Light", "Only show lights", "OUTLINER_DATA_LIGHT", 1),
            ("EMISSION", "Emission Material", "Only luminous materials are displayed", "MATERIAL", 2),
        ]
    )

    def get_link(self):
        key = f"{self.light_list_filter_type}_link"
        if is_50:
            properties = self.bl_system_properties_get()
            if key in properties:
                return properties[key]
            else:
                return 0
        else:
            if key in self:
                return self[key]
            else:
                return 0

    def set_link(self, value):
        key = f"{self.light_list_filter_type}_link"
        if is_50:
            self.bl_system_properties_get()[key] = value
        else:
            self[key] = value

    light_link_filter_type: EnumProperty(
        name="Link Filter Type",
        default="ALL",
        translation_context="light_helper_zh_CN",
        items=[
            ("ALL", "All", "Show all"),
            ("NOT_LINK", "General", "Only non-light links are displayed"),
            ("LINK", "Linking", "Only light links are displayed"),
        ],
        get=get_link,
        set=set_link,
        update=update_filter_settings,
    )
    moving_view_type: EnumProperty(
        name="View Movement Type",
        default="NONE",
        translation_context="light_helper_zh_CN",
        items=[
            ("NONE", "None", "Only select; do not move the view", "RESTRICT_SELECT_OFF", 0),
            ("MAINTAINING_ZOOM", "Maintaining Zoom", "Switch view position directly, with no animation", "VIEWZOOM", 1),
            ("ANIMATION", "Animation", "Animated switching without fixed zoom", "ANIM", 2),
        ]
    )
    def update_auto_fix_shared_linking(self, _context):
        from .handlers import sync_auto_fix_depsgraph_handler
        sync_auto_fix_depsgraph_handler(self.auto_fix_shared_linking)

    auto_fix_shared_linking: bpy.props.BoolProperty(
        name="Auto Fix Shared Linking",
        description="Opt in to splitting shared light-linking collections for explicitly detected duplicates; never runs while opening a file",
        default=False,
        update=update_auto_fix_shared_linking,
    )
    linking_tool_max_outlines: IntProperty(
        name="Linking Tool Max Outlines",
        description="Maximum number of linked targets to draw outlines for. Lines are always drawn",
        default=25,
        min=0,
        max=500,
    )
    linking_tool_hud_x: IntProperty(
        name="HUD X",
        description="Horizontal position of the linking tool HUD",
        default=100,
        min=0,
        soft_max=4096,
    )
    linking_tool_hud_y: IntProperty(
        name="HUD Y",
        description="Vertical position of the linking tool HUD",
        default=150,
        min=0,
        soft_max=4096,
    )

    def update_linking_tool_hud_scale(self, context):
        from .utils.overlay import tag_view3d_redraw
        tag_view3d_redraw(context)

    linking_tool_hud_scale: FloatProperty(
        name="Shortcut Tip Scale",
        description="Scale of the linking tool shortcut tip HUD in the viewport",
        default=1.0,
        min=0.5,
        max=3.0,
        soft_min=0.5,
        soft_max=2.0,
        step=10,
        precision=2,
        update=update_linking_tool_hud_scale,
    )

    def draw(self, context):
        from bpy.app.translations import pgettext_iface as p_
        from .ops.light_adjust import LLP_OT_reset_linking_hud
        from .ops.maintenance import LLP_OT_cleanup_legacy_data
        layout = self.layout
        column = layout.column(align=True)
        if bpy.app.version < (4, 3, 0):
            column.label(text=p_("Version lower than 4.3.0, only the Cycles renderer can set light exclusion"))
        column.prop(self, "panel_name")
        column.prop(self, "node_search_depth")
        column.prop(self, "light_list_filter_type")
        column.prop(self, "light_link_filter_type", text_ctxt="light_helper_zh_CN")
        column.prop(self, "moving_view_type", text_ctxt="light_helper_zh_CN")
        column.prop(self, "auto_fix_shared_linking")
        column.prop(self, "linking_tool_max_outlines")
        column.separator()
        column.prop(self, "linking_tool_hud_scale")
        row = column.row(align=True)
        row.prop(self, "linking_tool_hud_x")
        row.prop(self, "linking_tool_hud_y")
        column.operator(LLP_OT_reset_linking_hud.bl_idname, icon='LOOP_BACK')
        column.separator()
        cleanup_row = column.row(align=True)
        cleanup_row.enabled = LLP_OT_cleanup_legacy_data.poll(context)
        cleanup_row.operator(LLP_OT_cleanup_legacy_data.bl_idname, icon='BRUSH_DATA')
        column.separator()
        column.label(
            text=p_("Use Exclude mode to omit listed objects from a light, or Include mode to affect only listed objects."),
            icon='INFO',
        )
        column.label(
            text=p_("Restore clears light linking collections and resets default lighting behavior."),
        )


def register():
    bpy.utils.register_class(LLT_AddonPreferences)


def unregister():
    bpy.utils.unregister_class(LLT_AddonPreferences)
