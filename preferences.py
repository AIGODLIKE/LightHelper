import bpy
from bpy.props import StringProperty, EnumProperty, IntProperty
from bpy.types import AddonPreferences

is_50 = bpy.app.version[:2] > (5, 0)


class LLT_AddonPreferences(AddonPreferences):
    bl_idname = __package__

    def update_panel(self, context):
        from .panel import refresh_panel
        refresh_panel()

    panel_name: StringProperty(name="Panel Name", default="LH", update=update_panel)
    node_search_depth: IntProperty(name="Node search depth",
                                   description="If the setting is too high or the materials in the scene are too complex, stuttering may occur",
                                   default=10, max=50, min=3)
    light_list_filter_type: EnumProperty(
        name="List Filter Type",
        default="ALL",
        translation_context="light_helper_zh_CN",
        items=[
            ("ALL", "All", "Display lights and objects that can emit light", "SCENE_DATA", 0),
            ("LIGHT", "Light", "Only show the lights", "OUTLINER_DATA_LIGHT", 1),
            ("EMISSION", "Emission Material", "Only luminous material are displayed", "MATERIAL", 2),
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
    )
    moving_view_type: EnumProperty(
        name="Moving View Type",
        default="NONE",
        items=[
            ("NONE", "None", "Only Select, Do not move the view", "RESTRICT_SELECT_OFF", 0),
            ("MAINTAINING_ZOOM", "Maintaining Zoom", "Direct switching of view position,no animation", "VIEWZOOM", 1),
            ("ANIMATION", "Animation", "Animation switching, no fixed zoom", "ANIM", 2),
        ]
    )

    def draw(self, context):
        layout = self.layout
        column = layout.column(align=True)
        if bpy.app.version < (4, 3, 0):
            column.label(text="Version lower than 4.3.0, only the CYCLE renderer can set light exclusion")
        column.prop(self, "panel_name")
        column.prop(self, "node_search_depth")
        column.prop(self, "light_list_filter_type")
        column.prop(self, "light_link_filter_type", text_ctxt="light_helper_zh_CN")
        column.prop(self, "moving_view_type")


def register():
    bpy.utils.register_class(LLT_AddonPreferences)


def unregister():
    bpy.utils.unregister_class(LLT_AddonPreferences)
