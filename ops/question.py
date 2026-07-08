import bpy


class LLP_OT_question(bpy.types.Operator):
    bl_idname = 'wm.light_helper_question'
    bl_label = ""
    bl_options = {'INTERNAL'}

    data: bpy.props.StringProperty(options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, properties):
        return properties.data

    def execute(self, context):
        return {"FINISHED"}
