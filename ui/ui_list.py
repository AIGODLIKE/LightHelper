import bpy

from ..utils.icon import get_item_icon


class LLT_UL_light(bpy.types.UIList):
    sort_type: bpy.props.EnumProperty(
        name="Use Sort",
        default="TYPE",
        translation_context="light_helper_zh_CN",
        items=[("TYPE", "Type", ""),
               ("NAME", "Name", "")],
        options=set(),
        description="",
    )
    show_type: bpy.props.BoolProperty(name="Show Type", default=False)
    show_in_view: bpy.props.BoolProperty(name="Show View Button", default=True)

    def draw_filter(self, context, layout):
        from ..utils import get_pref
        from bpy.app.translations import pgettext_iface

        pref = get_pref(context)
        tctx = "light_helper_zh_CN"

        sp = layout.column(align=True).split(factor=0.2, align=True)

        sc = sp.column(align=True)

        for i in (
                "Sort Type",
                "Show",
                "Moving View Type",
        ):
            sc.label(text=f"{pgettext_iface(i, tctx)}:")

        sc = sp.column(align=True)
        sc.row(align=True).prop(self, "sort_type", expand=True, text_ctxt=tctx)

        row = sc.row(align=True)
        row.prop(self, "show_type", emboss=True, toggle=True)
        row.prop(self, "show_in_view", emboss=True, toggle=True)

        sc.row(align=True).prop(pref, "moving_view_type", expand=True)
        sc.prop(pref, "node_search_depth")

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        from ..utils import check_link
        from ..ops import LLP_OT_add_light_linking, LLP_OT_clear_light_linking, LLP_OT_solo_light
        split = layout.split(factor=0.2, align=True)

        left = split.row(align=True)

        if self.show_in_view:
            icon = "HIDE_OFF" if item.light_helper_property.show_in_view else "HIDE_ON"

            left.prop(item.light_helper_property, "show_in_view", text='', icon=icon, emboss=False)
            left.separator()

            index = context.scene.objects[:].index(item)
            if item.type == 'LIGHT':
                solo = context.window_manager.light_helper_property.solo_light
                solo_active = solo is not None and solo.name == item.name
                solo_row = left.row(align=True)
                solo_row.context_pointer_set("solo_light_object", item)
                op = solo_row.operator(
                    LLP_OT_solo_light.bl_idname,
                    text="",
                    icon='CLIPUV_HLT',
                    depress=solo_active,
                    emboss=False
                )
                op.index = index

        left.label(**get_item_icon(item))
        if self.show_type:
            left.label(text=item.type.title())

        right = split.row(align=True)
        right.label(text=item.name, translate=False)
        right.separator()
        rs = right.split()
        rs.separator()
        if check_link(item):
            rs.context_pointer_set("clear_light_linking_object", item)
            rs.operator(LLP_OT_clear_light_linking.bl_idname, text="Restore").index = index
        else:
            with context.temp_override(add_light_linking_light_obj=item):
                rs.context_pointer_set("add_light_linking_light_obj", item)
                op = rs.operator(LLP_OT_add_light_linking.bl_idname, text='Init')
                op.index = index
                op.init = True

    def filter_items(self, context, data, propname):
        from ..filter import filter_list

        helper_funcs = bpy.types.UI_UL_list
        objects = getattr(data, propname)[:]

        flt_neworder = []
        flt_flags = filter_list(context, self.bitflag_filter_item)

        if self.sort_type == "TYPE":
            flt_neworder = helper_funcs.sort_items_by_name(objects, "type")
        elif self.sort_type == "NAME":
            flt_neworder = helper_funcs.sort_items_by_name(objects, "name")
        return flt_flags, flt_neworder


def register():
    bpy.utils.register_class(LLT_UL_light)


def unregister():
    bpy.utils.unregister_class(LLT_UL_light)
