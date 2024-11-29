import bpy
from bpy.props import StringProperty
from bpy.types import AddonPreferences


class LLT_AddonPreferences(AddonPreferences):
    bl_idname = __package__

    def update_panel(self, context):
        from .panel import refresh_panel
        refresh_panel()

    panel_name: StringProperty(name="Panel Name", default="LH", update=update_panel)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "panel_name")


def register():
    bpy.utils.register_class(LLT_AddonPreferences)


def unregister():
    bpy.utils.unregister_class(LLT_AddonPreferences)
