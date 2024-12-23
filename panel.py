import bpy
from bpy.app.translations import pgettext_iface as p_

from .utils import CollectionType, StateValue, SAFE_OBJ_NAME
from .utils import get_all_light_effect_items_state, get_linking_coll
from .utils import get_lights_from_effect_obj


def get_light_icon(light):
    data = light.data
    type_icon = {
        'AREA': 'LIGHT_AREA',
        'POINT': 'LIGHT_POINT',
        'SPOT': 'LIGHT_SPOT',
        'SUN': 'LIGHT_SUN',
    }
    if hasattr(data, 'type'):
        return type_icon.get(data.type, 'OBJECT_DATA')

    return 'OBJECT_DATA'


def get_item_icon(item: bpy.types.Object | bpy.types.Collection):
    from bpy.types import UILayout

    if isinstance(item, bpy.types.Collection):
        return {'icon': "OUTLINER_COLLECTION"}
    elif isinstance(item, bpy.types.Object):
        if item.type == "LIGHT":
            from .utils import check_link
            for i in item.data.bl_rna.properties['type'].enum_items:
                if item.data.type == i.identifier:
                    return {"icon": i.icon}
            return {"icon": "OUTLINER_OB_LIGHT" if check_link(item) else "OUTLINER_DATA_LIGHT"}
        elif hasattr(item, 'data'):
            try:
                icon_value = UILayout.icon(item.data)
                if icon_value != 157:
                    return {"icon_value": icon_value}
            except Exception:
                ...
        if item.type == "EMPTY":
            return {"icon": "EMPTY_DATA"}
        else:
            return {"icon": "OBJECT_DATA"}
    return {"icon": "QUESTION"}


def draw_select_btn(layout, item):
    from .ops import LLP_OT_select_item
    row = layout.row()
    if isinstance(item, bpy.types.Object):
        row.context_pointer_set("select_item_object", item)
    else:
        row.context_pointer_set("select_item_collection", item)
    row.operator(LLP_OT_select_item.bl_idname, text=item.name, emboss=False, translate=False, **get_item_icon(item))


def draw_toggle_btn(layout,
                    state_info: dict,
                    light_obj: bpy.types.Object,
                    item: bpy.types.Object | bpy.types.Collection):
    """Draw toggle button for receiver / blocker collection"""
    from .ops import LLP_OT_toggle_light_linking
    row = layout.row()
    row.context_pointer_set("toggle_light_linking_light_obj", light_obj)

    if isinstance(item, bpy.types.Object):
        row.context_pointer_set("toggle_light_linking_object", item)
    else:
        row.context_pointer_set("toggle_light_linking_collection", item)

    if receive_value := state_info.get(CollectionType.RECEIVER):  # exist in receiver collection
        icon = 'OUTLINER_OB_LIGHT' if receive_value == StateValue.INCLUDE else 'OUTLINER_DATA_LIGHT'
        sub = row.row(align=True)
        sub.alert = receive_value == StateValue.INCLUDE
        op = sub.operator(LLP_OT_toggle_light_linking.bl_idname, text='', icon=icon)
        op.coll_type = CollectionType.RECEIVER.value

    if block_value := state_info.get(CollectionType.BLOCKER):  # exist in exclude collection
        icon = 'SHADING_SOLID' if block_value == StateValue.INCLUDE else 'SHADING_RENDERED'
        sub = row.row(align=True)
        sub.alert = block_value == StateValue.INCLUDE
        op = sub.operator(LLP_OT_toggle_light_linking.bl_idname, text='', icon=icon)
        op.coll_type = CollectionType.BLOCKER.value


def draw_remove_button(layout,
                       light_obj: bpy.types.Object,
                       item: bpy.types.Object | bpy.types.Collection):
    from .ops import LLP_OT_remove_light_linking
    row = layout.row()
    row.context_pointer_set("remove_light_linking_light_obj", light_obj)
    if isinstance(item, bpy.types.Object):
        row.context_pointer_set("remove_light_linking_object", item)
    else:
        row.context_pointer_set("remove_light_linking_collection", item)
    op = row.operator(LLP_OT_remove_light_linking.bl_idname, text='', icon="X", translate=False)
    op.remove_all = True


def draw_light_link(obj, layout, use_pin=False):
    if obj is None:
        return
    scene = bpy.context.scene
    col = layout.column()
    light_linking = obj.light_linking

    row = col.row(align=True)

    row.label(text=obj.name, icon='LIGHT')
    if use_pin:
        row.prop(scene.light_helper_property, 'light_linking_pin', text='', icon='PINNED')

    if not light_linking.receiver_collection:
        col.operator('object.light_linking_receiver_collection_new', text='', icon='ADD')
        return

    row = col.row(align=True)
    row.prop(obj.light_helper_property, 'light_linking_state', expand=True)
    row.prop(scene.light_helper_property, 'force_light_linking_state', icon='FILE_REFRESH', toggle=True, text='')

    if not obj.light_helper_property.show_light_linking_collection:
        return

    col.separator()

    row = col.row(align=True)
    row.template_light_linking_collection(row, light_linking, "receiver_collection")
    row.operator('object.light_linking_unlink_from_collection', text='', icon='REMOVE')


class LLT_PT_light_control_panel(bpy.types.Panel):
    bl_label = ""
    bl_idname = "LLT_PT_light_control_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "LH"
    bl_options = {'HEADER_LAYOUT_EXPAND'}

    @classmethod
    def poll(cls, context):
        if bpy.app.version >= (4, 3, 0):
            return context.scene.render.engine in {"CYCLES", "BLENDER_EEVEE_NEXT"}
        return context.scene.render.engine == "CYCLES"

    def draw_header(self, context):
        from .ops import LLP_OT_question
        from .utils import get_pref

        pref = get_pref()

        layout = self.layout
        row = layout.row(align=True)
        row.label(text="Light Linking")
        row.prop(pref, "moving_view_type", expand=True, icon_only=True)
        row.separator()
        tips = row.operator(LLP_OT_question.bl_idname, text="", icon="QUESTION", emboss=False)
        tips.data = p_(
            """Light Linking Panel
This Panel Lists all the objects that are affected by the selected/pinned light.
Provides buttons to toggle the light effecting state of the objects."""
        )

        row.separator()

    def draw(self, context):
        layout = self.layout
        self.draw_light_list(context, layout)
        self.draw_light_objs_control(context, layout)

    def draw_light_objs_control(self, context, layout):
        from .ops import LLP_OT_add_light_linking, LLP_OT_link_selected_objs, LLP_OT_clear_light_linking, \
            LLP_OT_instances_data

        if context.scene.light_helper_property.light_linking_pin:
            light_obj = context.scene.light_helper_property.light_linking_pin_object
        else:
            light_obj = context.object
        if not light_obj:
            return

        coll_receiver = get_linking_coll(light_obj, CollectionType.RECEIVER)
        coll_blocker = get_linking_coll(light_obj, CollectionType.BLOCKER)
        not_init = (not coll_receiver and not coll_blocker) or (
                coll_receiver and SAFE_OBJ_NAME not in coll_receiver.objects) or (
                           coll_blocker and SAFE_OBJ_NAME not in coll_blocker.objects)

        col = layout.column()
        # top line
        row = col.row(align=True)
        row.label(text=f"{light_obj.name}", icon=get_light_icon(light_obj), translate=False)
        row.separator()
        row.prop(bpy.context.scene.light_helper_property, 'light_linking_pin', text='', icon='PINNED')
        if LLP_OT_instances_data.poll(context):
            row.operator(LLP_OT_instances_data.bl_idname, text="", icon='RESTRICT_INSTANCED_ON')
        if not not_init:
            row.operator(LLP_OT_clear_light_linking.bl_idname, text="", icon="PANEL_CLOSE")

        # return if no receiver/blocker collection (exclude the safe obj)
        if not_init:
            with context.temp_override(add_light_linking_light_obj=light_obj):
                from bpy.app.translations import pgettext_iface
                col.context_pointer_set("add_light_linking_light_obj", light_obj)
                op = col.operator(LLP_OT_add_light_linking.bl_idname, text='Init', icon='ADD')
                op.init = True
                if LLP_OT_add_light_linking.poll(context) is False:
                    cc = col.column()
                    cc.alert = True
                    cc.label(text="Please select light or can be illuminated object")
                    cc.label(
                        text=pgettext_iface("Current type: ") + context.object.type)
                return

        obj_state_dict = get_all_light_effect_items_state(light_obj)

        safe_obj = bpy.data.objects.get(SAFE_OBJ_NAME)
        if len(obj_state_dict) == 1 and safe_obj in obj_state_dict.keys():
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
            return

        col.separator()

        for (item, state_info) in obj_state_dict.items():
            if item.name == SAFE_OBJ_NAME:
                continue  # skip safe obj
            row = col.row(align=False)
            row.scale_x = 1.1
            row.scale_y = 1.1

            draw_select_btn(row, item)
            draw_toggle_btn(row, state_info, light_obj, item)
            row.separator()
            draw_remove_button(row, light_obj, item)

        # extra op
        col.separator()
        box = col.box()
        row = box.row()
        row.label(text='', icon='ADD')
        row.prop(context.window_manager.light_helper_property, 'light_linking_add_collection', text='',
                 icon='OUTLINER_COLLECTION')
        row.prop(context.window_manager.light_helper_property, 'light_linking_add_object', text='', icon='OBJECT_DATA')

        row = box.row()
        row.context_pointer_set("link_light_obj", light_obj)
        row.operator(LLP_OT_link_selected_objs.bl_idname, icon='ADD')

    def draw_light_list(self, context, layout):
        from .utils import get_pref
        pref = get_pref()

        column = layout.column(align=True)
        column.row(align=True).prop(pref, "light_link_filter_type", expand=True,
                                    text_ctxt="light_helper_zh_CN")

        row = column.row(align=True)
        row.column(align=True).prop(pref, "light_list_filter_type", expand=True, text="", icon_only=True)
        row.template_list("LLT_UL_light", "", context.scene, "objects", context.scene.light_helper_property,
                          "active_object_index")


class LLT_PT_obj_control_panel(bpy.types.Panel):
    bl_label = ""
    bl_idname = "LLT_PT_obj_control_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "LH"
    bl_options = {'HEADER_LAYOUT_EXPAND'}

    @classmethod
    def poll(cls, context):
        return LLT_PT_light_control_panel.poll(context)

    def draw_header(self, context):
        from .ops import LLP_OT_question
        layout = self.layout
        row = layout.row(align=True)
        row.label(text="Object Linking")
        tips = row.operator(LLP_OT_question.bl_idname, text='', icon='QUESTION', emboss=False)
        if tips:
            tips.data = p_(
                """Object Linking Panel
    This Panel Lists all the lights that affected the selected/pinned object.
    Provides buttons to toggle the light effecting state of the objects."""
            )
        row.separator()

    def draw(self, context):
        layout = self.layout
        self.draw_object(context, layout)

    def draw_object(self, context, layout):
        if context.scene.light_helper_property.object_linking_pin:
            item = context.scene.light_helper_property.object_linking_pin_object
        else:
            item = context.object
        if not item:
            return
        if item.type == 'LIGHT':
            layout.label(text="Light can't be an effected object")
            return

        col = layout.column()
        # top line
        row = col.row(align=True)
        row.label(text=f"{item.name}", icon=get_light_icon(item))
        row.separator()
        row.prop(bpy.context.scene.light_helper_property, 'object_linking_pin', text='', icon='PINNED')

        col.separator()

        obj_state_dict = get_lights_from_effect_obj(item)
        if len(obj_state_dict) == 0:
            col.label(text='No Link type lights effecting this object', icon='LIGHT')
            box = col.box()
            box.prop(context.window_manager.light_helper_property, 'object_linking_add_object', text='', icon='ADD')
            return
        for (light_obj, state_info) in obj_state_dict.items():
            row = col.row()
            draw_select_btn(row, light_obj)
            draw_toggle_btn(row, state_info, light_obj, item)
            row.separator()
            draw_remove_button(row, light_obj, item)

        box = col.box()
        box.prop(context.window_manager.light_helper_property, 'object_linking_add_object', text='', icon='ADD')


class LLT_UL_light(bpy.types.UIList):
    EMPTY = 1 << 0

    sort_type: bpy.props.EnumProperty(
        name="Use Sort",
        default="TYPE",
        items=[("TYPE", "Type", ""),
               ("NAME", "Name", "")],
        options=set(),
        description="",
    )
    show_type: bpy.props.BoolProperty(name="Show Type", default=False)
    show_in_view: bpy.props.BoolProperty(name="Show View Button", default=True)

    def draw_filter(self, context, layout):
        from .utils import get_pref
        from bpy.app.translations import pgettext_iface

        pref = get_pref()

        sp = layout.column(align=True).split(factor=0.2, align=True)

        sc = sp.column(align=True)

        for i in (
                "Sort Type",
                "Show",
                "Moving View Type",
        ):
            sc.label(text=f"{pgettext_iface(i)}:")

        sc = sp.column(align=True)
        sc.row(align=True).prop(self, "sort_type", expand=True)

        row = sc.row(align=True)
        row.prop(self, "show_type", emboss=True, toggle=True)
        row.prop(self, "show_in_view", emboss=True, toggle=True)

        sc.row(align=True).prop(pref, "moving_view_type", expand=True)

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        from .utils import check_link
        from .ops import LLP_OT_add_light_linking, LLP_OT_clear_light_linking
        split = layout.split(factor=0.2, align=True)

        left = split.row(align=True)

        if self.show_in_view:
            icon = "HIDE_OFF" if item.light_helper_property.show_in_view else "HIDE_ON"

            left.prop(item.light_helper_property, "show_in_view", text='', icon=icon, emboss=False)
            left.separator()

        left.label(**get_item_icon(item))
        if self.show_type:
            left.label(text=item.type.title())

        right = split.row(align=True)
        right.label(text=item.name, translate=False)
        right.separator()

        if check_link(item):
            right.context_pointer_set("clear_light_linking_object", item)
            right.operator(LLP_OT_clear_light_linking.bl_idname, text="Restore", icon="PANEL_CLOSE")
        else:
            with context.temp_override(add_light_linking_light_obj=item):
                from bpy.app.translations import pgettext_iface
                right.context_pointer_set("add_light_linking_light_obj", item)
                op = right.operator(LLP_OT_add_light_linking.bl_idname, text='Init', icon="ADD")
                op.init = True

    def filter_items(self, context, data, propname):
        from .utils import get_pref, check_link
        helper_funcs = bpy.types.UI_UL_list
        objects = getattr(data, propname)[:]
        pref = get_pref()
        filter_type = pref.light_list_filter_type
        link_type = pref.light_link_filter_type

        flt_flags = []
        flt_neworder = []

        if not flt_flags:
            flt_flags = [self.bitflag_filter_item] * len(objects)

        from .utils import check_material_including_emission
        for idx, obj in enumerate(objects):
            if filter_type == "ALL":
                is_show = obj.type == "LIGHT" or check_material_including_emission(obj)
                flag = self.bitflag_filter_item if is_show else self.EMPTY
            elif filter_type == "LIGHT":
                flag = self.bitflag_filter_item if obj.type == 'LIGHT' else self.EMPTY
            elif filter_type == "EMISSION":
                flag = self.bitflag_filter_item if check_material_including_emission(obj) else self.EMPTY
            else:
                flag = self.EMPTY

            if flag == self.bitflag_filter_item and link_type != "ALL":
                is_link = check_link(obj)

                is_ok = link_type == "LINK" and is_link or link_type == "NOT_LINK" and not is_link
                flag = self.bitflag_filter_item if is_ok else self.EMPTY
            flt_flags[idx] = flag

        if self.sort_type == "TYPE":
            flt_neworder = helper_funcs.sort_items_by_name(objects, "type")
        elif self.sort_type == "NAME":
            flt_neworder = helper_funcs.sort_items_by_name(objects, "name")
        return flt_flags, flt_neworder


panel_list = [
    LLT_PT_light_control_panel,
    LLT_PT_obj_control_panel,
    LLT_UL_light,
]
register_class, unregister_class = bpy.utils.register_classes_factory(panel_list)


def register():
    from .utils import get_pref
    pref = get_pref()
    for panel in panel_list:
        panel.bl_category = pref.panel_name
    register_class()


def unregister():
    unregister_class()


def refresh_panel():
    unregister()
    register()
