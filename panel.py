import bpy
from bpy.app.translations import pgettext_iface as p_

from .ops import get_lights_from_receiver_obj
from .utils import get_all_light_effect_items_state, get_linking_coll
from .utils import CollectionType, StateValue, SAFE_OBJ_NAME


def get_light_icon(light):
    data = light.data

    if hasattr(data, 'type'):
        if data.type == 'AREA':
            return 'LIGHT_AREA'
        elif data.type == 'POINT':
            return 'LIGHT_POINT'
        elif data.type == 'SPOT':
            return 'LIGHT_SPOT'
        elif data.type == 'SUN':
            return 'LIGHT_SUN'

    return 'OBJECT_DATA'


def get_item_icon(item: bpy.types.Object | bpy.types.Collection):
    if isinstance(item, bpy.types.Object):
        return 'OBJECT_DATA'
    elif isinstance(item, bpy.types.Collection):
        return 'OUTLINER_COLLECTION'
    else:
        return 'QUESTION'


def draw_light_link(object, layout, use_pin=False):
    if object is None: return

    col = layout.column()
    light_linking = object.light_linking

    row = col.row(align=True)

    row.label(text=object.name, icon='LIGHT')
    if use_pin:
        row.prop(bpy.context.scene, 'light_linking_pin', text='', icon='PINNED')

    # col.prop(light_linking, 'receiver_collection', text='')

    if not light_linking.receiver_collection:
        col.operator('object.light_linking_receiver_collection_new', text='', icon='ADD')
        return

    row = col.row(align=True)
    row.prop(object, 'light_linking_state', expand=True)
    row.prop(bpy.context.scene, 'force_light_linking_state', icon='FILE_REFRESH', toggle=True, text='')

    if not object.show_light_linking_collection: return

    col.separator()

    row = col.row(align=True)
    row.template_light_linking_collection(row, light_linking, "receiver_collection")
    row.operator('object.light_linking_unlink_from_collection', text='', icon='REMOVE')


class LLT_PT_panel(bpy.types.Panel):
    bl_label = "Light Linking"
    bl_idname = "LLT_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Light Linking"

    # bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return context.scene.render.engine == 'CYCLES'

    def draw(self, context):
        layout = self.layout
        # layout.prop(context.scene, 'light_linking_ui', expand=True)

        self.draw_light_objs_control(context, layout)
        # if context.scene.light_linking_ui == 'LIGHT_EX':
        #     self.draw_light_objs_control(context, layout)
        #
        # elif context.scene.light_linking_ui == 'LIGHT':
        #     self.draw_light(context, layout)
        #
        # elif context.scene.light_linking_ui == 'OBJECT':
        #     self.draw_object(context, layout)

    # def draw_light(self, context, layout):
    #     if context.scene.light_linking_pin:
    #         obj = context.scene.light_linking_pin_object
    #         if not obj: return
    #         draw_light_link(obj, layout, use_pin=True)
    #     else:
    #         if not context.object:
    #             layout.label(text="No object selected")
    #         elif context.object.type != 'LIGHT':
    #             layout.label(text="Selected object is not a light")
    #             layout.operator('object.light_linking_receiver_collection_new', text='As light', icon='ADD')
    #             return
    #
    #         draw_light_link(context.object, layout, use_pin=True)
    #
    # def draw_object(self, context, layout):
    #     lights = get_lights_from_receiver_obj(context.object)
    #     layout.label(text='仅显示排除灯光')
    #     for (light, state) in lights:
    #         if state != 'EXCLUDE': continue
    #
    #         row = layout.row(align=True)
    #         row.label(text=f"'{light.name}'", icon=get_light_icon(light))
    #         op = row.operator('llp.remove_light_linking', text='', icon="REMOVE")
    #
    #         op.obj = context.object.name
    #         op.light = light.name
    #         op.coll_type = CollectionType.RECEIVER.value

    def draw_light_objs_control(self, context, layout):
        if context.scene.light_linking_pin:
            light_obj = context.scene.light_linking_pin_object
        else:
            light_obj = context.object
        if not light_obj: return

        col = layout.column()
        # top line
        row = col.row(align=True)
        row.label(text=f"{light_obj.name}", icon=get_light_icon(light_obj))
        row.separator()
        row.prop(bpy.context.scene, 'light_linking_pin', text='', icon='PINNED')

        select_op_id = 'llp.select_item'
        toggle_op_id = 'llp.toggle_light_linking'
        add_op_id = 'llp.add_light_linking'
        remove_op_id = 'llp.remove_light_linking'

        coll_receiver = get_linking_coll(light_obj, CollectionType.RECEIVER)
        coll_blocker = get_linking_coll(light_obj, CollectionType.BLOCKER)

        if (not coll_receiver and not coll_blocker) or (
                SAFE_OBJ_NAME not in coll_receiver.objects) or (
                SAFE_OBJ_NAME not in coll_blocker.objects):
            op = col.operator(add_op_id, text='Init', icon='ADD')
            op.add_all = True
            op.light = light_obj.name
            return

        obj_state_dict = get_all_light_effect_items_state(light_obj)

        safe_obj = bpy.data.objects.get(SAFE_OBJ_NAME)
        if len(obj_state_dict) == 1 and safe_obj in obj_state_dict.keys():
            col.label(text='No Effect Object')
            return

        col.separator()

        for item in obj_state_dict.keys():
            if item.name == SAFE_OBJ_NAME: continue  # skip safe obj
            row = col.row(align=False)
            row.scale_x = 1.1
            row.scale_y = 1.1
            op = row.operator(select_op_id, text=item.name, icon=get_item_icon(item), emboss=False)
            if isinstance(item, bpy.types.Object):
                op.obj = item.name
            else:
                op.coll = item.name

            state_info = obj_state_dict[item]
            # print(state_info)
            if receive_value := state_info.get(CollectionType.RECEIVER):  # exist in receiver collection
                icon = 'OUTLINER_OB_LIGHT' if receive_value == StateValue.INCLUDE else 'OUTLINER_DATA_LIGHT'
                # text = 'Include' if receive_value == StateValue.INCLUDE else 'Exclude'
                toggle = True if receive_value == StateValue.INCLUDE else False
                sub = row.row(align=True)
                sub.alert = toggle
                op = sub.operator(toggle_op_id, text='', icon=icon)
                op.coll_type = CollectionType.RECEIVER.value
                op.light = light_obj.name
                if isinstance(item, bpy.types.Object):
                    op.obj = item.name
                else:
                    op.coll = item.name

            if block_value := state_info.get(CollectionType.BLOCKER):  # exist in exclude collection
                icon = 'SHADING_SOLID' if block_value == StateValue.INCLUDE else 'SHADING_RENDERED'
                # text = 'Include' if block_value == StateValue.INCLUDE else 'Exclude'
                toggle = True if block_value == StateValue.INCLUDE else False
                sub = row.row(align=True)
                sub.alert = toggle
                op = sub.operator(toggle_op_id, text='', icon=icon)
                op.coll_type = CollectionType.BLOCKER.value
                op.light = light_obj.name
                if isinstance(item, bpy.types.Object):
                    op.obj = item.name
                else:
                    op.coll = item.name

            row.separator()
            op = row.operator(remove_op_id, text='', icon="X")
            if isinstance(item, bpy.types.Object):
                op.obj = item.name
            else:
                op.coll = item.name
            op.light = light_obj.name
            op.remove_all = True


def update_pin_object(self, context):
    if context.scene.light_linking_pin is True:
        if context.object and context.object.select_get():
            context.scene.light_linking_pin_object = context.object
        else:
            context.scene.light_linking_pin = False
    else:
        context.scene.light_linking_pin_object = None


def register():
    bpy.types.Scene.light_linking_ui = bpy.props.EnumProperty(
        items=[
            ('LIGHT', 'Simple', ''),
            ('LIGHT_EX', 'Advanced', ''),
            # ('OBJECT', 'Object', '')
        ]
    )
    bpy.types.Scene.light_linking_pin_object = bpy.props.PointerProperty(
        poll=lambda self, obj: obj.type in {'LIGHT', 'MESH'}, type=bpy.types.Object,
    )

    bpy.types.Scene.light_linking_pin = bpy.props.BoolProperty(name='Pin', update=update_pin_object)

    bpy.utils.register_class(LLT_PT_panel)


def unregister():
    del bpy.types.Scene.light_linking_ui
    del bpy.types.Scene.light_linking_pin_object
    del bpy.types.Scene.light_linking_pin

    bpy.utils.unregister_class(LLT_PT_panel)
