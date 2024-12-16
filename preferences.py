import bpy
from bpy.props import StringProperty, EnumProperty
from bpy.types import AddonPreferences


class LLT_AddonPreferences(AddonPreferences):
    bl_idname = __package__

    def update_panel(self, context):
        from .panel import refresh_panel
        refresh_panel()

    panel_name: StringProperty(name="Panel Name", default="LH", update=update_panel)

    light_list_filter_type: EnumProperty(
        default="ALL",
        items=[
            ("ALL", "All", "Display lights and objects that can emit light", "OUTLINER", 0),
            ("LIGHT", "Light", "Only show the lights", "OUTLINER_DATA_LIGHT", 1),
            ("EMISSION", "Emission Material", "Only luminous material are displayed", "MATERIAL", 2),
        ]
    )

    def get_link(self):
        key = f"{self.light_list_filter_type}_link"
        if key in self:
            return self[key]
        else:
            return 1 << 0

    def set_link(self, value):
        key = f"{self.light_list_filter_type}_link"
        self[key] = value

    light_link_filter_type: EnumProperty(
        default="ALL",
        items=[
            ("ALL", "All", "Show all", "ALIGN_LEFT", 1 << 0),
            ("LINK", "LINK", "Only light links are displayed", "OUTLINER_OB_LIGHT", 1 << 1),
            ("NOT_LINK", "NOT_LINK", "Only non-light links are displayed", "OUTLINER_DATA_LIGHT", 1 << 2),
        ],
        get=get_link,
        set=set_link,
    )
    moving_view_type: EnumProperty(
        default="ANIMATION",
        items=[
            ("NONE", "None", "", "RESTRICT_SELECT_ON", 0),
            ("MAINTAINING_ZOOM", "Maintaining Zoom", "Direct switching of view position, no animation", "VIEWZOOM", 1),
            ("ANIMATION", "Animation", "Animation switching, no fixed zoom", "ANIM", 2),
        ]
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "panel_name")
        layout.prop(self, "light_list_filter_type", expand=True)
        layout.prop(self, "light_link_filter_type", expand=True)
        layout.prop(self, "moving_view_type", expand=True)


def register():
    bpy.utils.register_class(LLT_AddonPreferences)


def unregister():
    bpy.utils.unregister_class(LLT_AddonPreferences)
