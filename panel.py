import bpy


def get_light_icon(light):
    data = light.data
    if data.type == 'AREA':
        return 'LIGHT_AREA'
    elif data.type == 'POINT':
        return 'LIGHT_POINT'
    elif data.type == 'SPOT':
        return 'LIGHT_SPOT'
    elif data.type == 'SUN':
        return 'LIGHT_SUN'

    return 'LIGHT'


def draw_light_link(object, layout, use_pin=False):
    if object is None: return

    col = layout.column()
    light_linking = object.light_linking

    row = col.row(align=True)

    row.label(text=object.name, icon='LIGHT')
    if use_pin:
        row.prop(bpy.context.scene, 'light_linking_pin', text='', icon='PINNED')

    col.prop(light_linking, 'receiver_collection', text='')

    if not light_linking.receiver_collection:
        row.operator('object.light_linking_receiver_collection_new', text='', icon='ADD')
        return

    row = col.row(align=True)
    row.prop(object, 'light_linking_state', expand=True)

    if not object.show_light_linking_collection: return

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
        layout.prop(context.scene, 'light_linking_ui', expand=True)

        if context.scene.light_linking_ui == 'SCENE':
            for obj in context.scene.objects:
                if obj.type == 'LIGHT':
                    draw_light_link(obj, layout)

        elif context.scene.light_linking_ui == 'OBJECT':
            if context.scene.light_linking_pin:
                obj = context.scene.light_linking_pin_object
                if not obj: return
                draw_light_link(obj, layout, use_pin=True)
            else:
                if not context.object:
                    layout.label(text="No object selected")
                elif context.object.type != 'LIGHT':
                    layout.label(text="Selected object is not a light")
                    return

                draw_light_link(context.object, layout, use_pin=True)


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
            ('OBJECT', 'Object', ''),
            ('SCENE', 'Scene', '')
        ]
    )
    bpy.types.Scene.light_linking_pin_object = bpy.props.PointerProperty(
        poll=lambda self, obj: obj.type == 'LIGHT', type=bpy.types.Object,
    )

    bpy.types.Scene.light_linking_pin = bpy.props.BoolProperty(name='Pin', update=update_pin_object)

    bpy.utils.register_class(LLT_PT_panel)


def unregister():
    del bpy.types.Scene.light_linking_ui
    del bpy.types.Scene.light_linking_pin_object
    del bpy.types.Scene.light_linking_pin

    bpy.utils.unregister_class(LLT_PT_panel)
