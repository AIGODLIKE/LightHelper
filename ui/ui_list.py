import bpy
from bpy.app.translations import pgettext_iface as p_

from ..utils.icon import get_item_icon

_TCTX = "light_helper_zh_CN"


def _apply_name_filter(helper_funcs, objects, flt_flags, filter_name, use_filter_invert, bitflag):
    if not filter_name:
        return flt_flags
    name_flags = helper_funcs.filter_items_by_name(
        filter_name, bitflag, objects, "name", reverse=use_filter_invert,
    )
    if not name_flags:
        return flt_flags
    return [flag & name_flag for flag, name_flag in zip(flt_flags, name_flags)]


def _apply_hide_not_shown(context, objects, flt_flags, bitflag):
    from ..utils import is_shown_in_view_layer

    return [
        flag if (flag != bitflag or is_shown_in_view_layer(context, obj)) else 0
        for obj, flag in zip(objects, flt_flags)
    ]


def _sort_by_link_count(helper_funcs, objects, count_fn):
    sort_data = [
        (i, count_fn(obj), obj.name.casefold())
        for i, obj in enumerate(objects)
    ]
    return helper_funcs.sort_items_helper(sort_data, lambda e: (-e[1], e[2]))


def _draw_search_row(layout, uilist):
    row = layout.row(align=True)
    row.prop(uilist, "filter_name", text="", icon="VIEWZOOM")
    row.prop(uilist, "use_filter_invert", text="", icon="ARROW_LEFTRIGHT")


_LINK_COUNT_NARROW_PX = 300


def _format_list_link_count(context, count, long_msg):
    """Shorter link-count text when the sidebar region is narrow."""
    region = getattr(context, "region", None)
    if region is not None and region.width < _LINK_COUNT_NARROW_PX:
        return "×%d" % count
    return p_(long_msg) % count


class LLT_UL_light(bpy.types.UIList):
    sort_type: bpy.props.EnumProperty(
        name="Use Sort",
        default="TYPE",
        translation_context=_TCTX,
        items=[
            ("TYPE", "Type", ""),
            ("LINK_COUNT", "Link Count", ""),
            ("NAME", "Name", ""),
        ],
        options=set(),
        description="",
    )
    show_type: bpy.props.BoolProperty(name="Type", default=False)
    show_in_view: bpy.props.BoolProperty(name="View", default=True)
    show_render: bpy.props.BoolProperty(name="Render", default=True)
    show_link_count: bpy.props.BoolProperty(name="Link Count", default=True)
    filter_hide_not_shown: bpy.props.BoolProperty(
        name="Hide Items Not in Scene",
        default=False,
        description="Hide lights and emissive objects that are not shown in the current scene",
    )

    def draw_filter(self, context, layout):
        from ..utils import get_pref
        from bpy.app.translations import pgettext_iface

        pref = get_pref(context)

        _draw_search_row(layout, self)

        sp = layout.column(align=True).split(factor=0.35, align=True)
        sc = sp.column(align=True)
        for i, tctx in (
                ("Show", _TCTX),
                ("Sort Type", _TCTX),
                ("Emission Node Search Depth", None),
        ):
            sc.label(text=f"{pgettext_iface(i, tctx)}:")

        sc = sp.column(align=True)
        row = sc.row(align=True)
        row.prop(self, "show_type", emboss=True, toggle=True, text_ctxt=_TCTX)
        row.prop(self, "show_in_view", emboss=True, toggle=True, text_ctxt=_TCTX)
        row.prop(self, "show_render", emboss=True, toggle=True, text_ctxt=_TCTX)
        row.prop(self, "show_link_count", emboss=True, toggle=True, text_ctxt=_TCTX)

        sc.row(align=True).prop(self, "sort_type", expand=True, text_ctxt=_TCTX)
        sc.prop(pref, "node_search_depth", text="")

        layout.prop(self, "filter_hide_not_shown", toggle=True)

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        from ..utils import check_link, get_light_link_item_count, is_shown_in_view_layer
        from ..ops import LLP_OT_add_light_linking, LLP_OT_clear_light_linking, LLP_OT_solo_light

        props = item.light_helper_property
        index = context.scene.objects[:].index(item)

        row = layout.row(align=True)
        if not is_shown_in_view_layer(context, item):
            row.active = False

        # Icons-only left column; type text sits with the name to avoid crowding.
        split = row.split(factor=0.28, align=True)
        left = split.row(align=True)

        if self.show_in_view:
            view_icon = "HIDE_OFF" if props.show_in_view else "HIDE_ON"
            left.prop(props, "show_in_view", text="", icon=view_icon, emboss=False)

        if self.show_render:
            render_icon = "RESTRICT_RENDER_OFF" if props.show_render else "RESTRICT_RENDER_ON"
            left.prop(props, "show_render", text="", icon=render_icon, emboss=False)

        if item.type == "LIGHT":
            solo = context.window_manager.light_helper_property.solo_light
            solo_active = solo is not None and solo == item
            solo_row = left.row(align=True)
            solo_row.alert = solo_active
            solo_row.context_pointer_set("solo_light_object", item)
            op = solo_row.operator(
                LLP_OT_solo_light.bl_idname,
                text="",
                icon="CLIPUV_DEHLT" if solo_active else "CLIPUV_HLT",
                emboss=solo_active,
            )
            op.index = index

        left.label(**get_item_icon(item))

        # Keep Restore/Init in a fixed-width column so missing link-count text
        # does not stretch the action button.
        rest = split.split(factor=0.72, align=True)
        info_right = rest.row(align=True)
        if self.show_type:
            info_right.label(text=item.type.title())
        info_right.label(text=item.name, translate=False)
        if self.show_link_count and check_link(item):
            count = get_light_link_item_count(item)
            info_right.label(text=_format_list_link_count(context, count, "Links: %d"))

        action = rest.row(align=True)
        if check_link(item):
            action.context_pointer_set("clear_light_linking_object", item)
            action.operator(LLP_OT_clear_light_linking.bl_idname, text="Restore").index = index
        elif item.type == "LIGHT":
            with context.temp_override(add_light_linking_light_obj=item):
                action.context_pointer_set("add_light_linking_light_obj", item)
                op = action.operator(LLP_OT_add_light_linking.bl_idname, text="Init")
                op.index = index
                op.init = True

    def filter_items(self, context, data, propname):
        from ..filter import filter_list
        from ..utils import get_light_link_item_count

        helper_funcs = bpy.types.UI_UL_list
        objects = getattr(data, propname)[:]
        bitflag = self.bitflag_filter_item

        flt_flags = filter_list(context, bitflag)
        flt_flags = _apply_name_filter(
            helper_funcs, objects, flt_flags, self.filter_name, self.use_filter_invert, bitflag,
        )
        if self.filter_hide_not_shown:
            flt_flags = _apply_hide_not_shown(context, objects, flt_flags, bitflag)

        if self.sort_type == "TYPE":
            flt_neworder = helper_funcs.sort_items_by_name(objects, "type")
        elif self.sort_type == "LINK_COUNT":
            flt_neworder = _sort_by_link_count(helper_funcs, objects, get_light_link_item_count)
        elif self.sort_type == "NAME":
            flt_neworder = helper_funcs.sort_items_by_name(objects, "name")
        else:
            flt_neworder = []

        return flt_flags, flt_neworder


class LLT_UL_linked_object(bpy.types.UIList):
    """Lists objects that are referenced by any light linking collection."""

    sort_type: bpy.props.EnumProperty(
        name="Use Sort",
        default="NAME",
        translation_context=_TCTX,
        items=[
            ("TYPE", "Type", ""),
            ("LINK_COUNT", "Link Count", ""),
            ("NAME", "Name", ""),
        ],
        options=set(),
        description="",
    )
    filter_hide_not_shown: bpy.props.BoolProperty(
        name="Hide Items Not in Scene",
        default=False,
        description="Hide objects that are not shown in the current scene",
    )

    def draw_filter(self, context, layout):
        from bpy.app.translations import pgettext_iface

        _draw_search_row(layout, self)

        sp = layout.column(align=True).split(factor=0.2, align=True)
        sc = sp.column(align=True)
        sc.label(text=f"{pgettext_iface('Sort Type', _TCTX)}:")
        sc = sp.column(align=True)
        sc.row(align=True).prop(self, "sort_type", expand=True, text_ctxt=_TCTX)

        layout.prop(self, "filter_hide_not_shown", toggle=True)

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        from ..utils import get_object_link_light_count, is_shown_in_view_layer

        props = item.light_helper_property
        row = layout.row(align=True)
        if not is_shown_in_view_layer(context, item):
            row.active = False

        view_icon = "HIDE_OFF" if props.show_viewport else "HIDE_ON"
        row.prop(props, "show_viewport", text="", icon=view_icon, emboss=False)
        render_icon = "RESTRICT_RENDER_OFF" if props.show_render else "RESTRICT_RENDER_ON"
        row.prop(props, "show_render", text="", icon=render_icon, emboss=False)

        info = row.row(align=True)
        info.label(text=item.name, translate=False, **get_item_icon(item))
        count = get_object_link_light_count(item, context)
        if count:
            info.label(text=_format_list_link_count(context, count, "Lights: %d"))

    def filter_items(self, context, data, propname):
        from ..utils import get_object_link_light_count, iter_objects_linked_by_lights

        helper_funcs = bpy.types.UI_UL_list
        objects = getattr(data, propname)[:]
        bitflag = self.bitflag_filter_item
        linked = set(iter_objects_linked_by_lights(context))

        flt_flags = [
            bitflag if obj in linked else 0
            for obj in objects
        ]
        flt_flags = _apply_name_filter(
            helper_funcs, objects, flt_flags, self.filter_name, self.use_filter_invert, bitflag,
        )
        if self.filter_hide_not_shown:
            flt_flags = _apply_hide_not_shown(context, objects, flt_flags, bitflag)

        if self.sort_type == "TYPE":
            flt_neworder = helper_funcs.sort_items_by_name(objects, "type")
        elif self.sort_type == "LINK_COUNT":
            flt_neworder = _sort_by_link_count(
                helper_funcs,
                objects,
                lambda obj: get_object_link_light_count(obj, context),
            )
        elif self.sort_type == "NAME":
            flt_neworder = helper_funcs.sort_items_by_name(objects, "name")
        else:
            flt_neworder = []

        return flt_flags, flt_neworder


def register():
    bpy.utils.register_class(LLT_UL_light)
    bpy.utils.register_class(LLT_UL_linked_object)


def unregister():
    bpy.utils.unregister_class(LLT_UL_linked_object)
    bpy.utils.unregister_class(LLT_UL_light)
