"""Workspace toolbar entry for transactional LightHelper placement."""

import bpy

from ..utils.icon import ui_icon


class VIEW3D_WT_light_helper_placement(bpy.types.WorkSpaceTool):
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'OBJECT'
    bl_idname = "light_helper.placement"
    bl_label = "Light Placement"
    bl_description = (
        "Create or adjust native lights and LightHelper studio shapes with "
        "Reflect, Direct, or Orbit placement"
    )
    bl_icon = "ops.light_helper.light_linking"
    bl_widget = None
    bl_keymap = (
        (
            "view3d.light_helper_place",
            {"type": 'LEFTMOUSE', "value": 'PRESS'},
            None,
        ),
    )

    @staticmethod
    def draw_settings(_context, layout, tool):
        props = tool.operator_properties("view3d.light_helper_place")
        row = layout.row(align=True)
        row.prop(props, "mode", text="")
        row.prop(props, "target_kind", text="")
        row.prop(props, "light_type", text="")
        row.prop(
            props,
            "adjust_selected",
            text="",
            icon=ui_icon('RESTRICT_SELECT_OFF'),
        )
        row.prop(
            props,
            "use_track_target",
            text="",
            icon=ui_icon('CON_TRACKTO'),
        )


_registered = False


def register():
    global _registered
    bpy.utils.register_tool(
        VIEW3D_WT_light_helper_placement,
        after={"light_helper.light_linking"},
        separator=False,
        group=False,
    )
    _registered = True


def unregister():
    global _registered
    if _registered:
        bpy.utils.unregister_tool(VIEW3D_WT_light_helper_placement)
        _registered = False
