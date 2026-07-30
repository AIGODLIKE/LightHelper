import bpy
from bpy.app.translations import pgettext_iface as p_

from .common import LightHelperOperator, format_lights_report, get_light_obj


class LLP_OT_cleanup_legacy_data(LightHelperOperator, bpy.types.Operator):
    bl_idname = 'wm.light_helper_cleanup_legacy_data'
    bl_label = "Clean Up Legacy Data"
    bl_description = (
        "Remove leftover data from older Light Helper versions "
        "and update light linking settings"
    )
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        from ..migration import has_legacy_residue
        if has_legacy_residue():
            return True
        cls.poll_message_set(p_("No legacy Light Helper data found"))
        return False

    def execute(self, context):
        from ..migration import run_legacy_cleanup
        removed, migrated = run_legacy_cleanup()
        if removed == 0 and migrated == 0:
            self.report({'INFO'}, p_("No legacy Light Helper data found"))
            return {'CANCELLED'}
        self.report(
            {'INFO'},
            p_("Cleaned up legacy data: %d object(s), %d scene(s)") % (removed, migrated),
        )
        return {'FINISHED'}


class LLP_OT_instances_data(LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_instances_data'
    bl_label = "Instance Data"
    bl_description = "Make shared light linking collections single-user for this light"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        from ..utils import (
            has_shared_linking_collections,
            is_light_linking_source_editable,
            is_tool_light_source,
        )
        light_obj = get_light_obj(context)
        if light_obj is None or not is_tool_light_source(light_obj, context) or not hasattr(light_obj, "light_linking"):
            cls.poll_message_set(p_("No light selected"))
            return False
        if not is_light_linking_source_editable(light_obj):
            cls.poll_message_set(p_("Light linking data is read-only"))
            return False
        if has_shared_linking_collections(light_obj):
            return True
        cls.poll_message_set(p_("Light linking collections are not shared"))
        return False

    def execute(self, context):
        from ..utils import (
            is_light_linking_source_editable,
            is_tool_light_source,
            make_light_linking_single_user,
        )
        light_obj = get_light_obj(context)
        # Match poll: emissive-mesh light sources are valid subjects too.
        if (light_obj is None or not is_tool_light_source(light_obj, context)
                or not hasattr(light_obj, "light_linking")):
            self.report({'ERROR'}, p_("No light selected"))
            return {"CANCELLED"}
        if not is_light_linking_source_editable(light_obj):
            self.report({'WARNING'}, p_("Light linking data is read-only"))
            return {"CANCELLED"}
        if not make_light_linking_single_user(light_obj):
            self.report({'WARNING'}, p_("Light linking collections are not shared"))
            return {"CANCELLED"}
        self.report({'INFO'}, p_("Light linking collections are now single-user"))
        return {"FINISHED"}


class LLP_OT_init_all_light_linking(LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_init_all_light_linking'
    bl_label = "Init All Lights"
    bl_description = "Initialize light linking collections for all lights in the scene"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        from ..utils import are_light_linking_collections_editable, is_linking_initialized

        engine = context.scene.render.engine
        supported = engine == 'CYCLES' or (
            bpy.app.version >= (4, 3, 0)
            and engine in {'BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE'}
        )
        if not supported:
            cls.poll_message_set(p_("This rendering engine does not support light linking"))
            return False
        has_read_only = False
        for obj in context.scene.objects:
            if obj.type != 'LIGHT' or not hasattr(obj, "light_linking") or is_linking_initialized(obj):
                continue
            if are_light_linking_collections_editable(obj):
                return True
            has_read_only = True
        if has_read_only:
            cls.poll_message_set(p_("Light linking data is read-only"))
            return False
        cls.poll_message_set(p_("All lights are already initialized"))
        return False

    def execute(self, context):
        from ..utils import init_all_light_linking
        initialized = init_all_light_linking(context.scene, context)
        if not initialized:
            self.report({'WARNING'}, p_("All lights are already initialized"))
            return {"CANCELLED"}
        message = format_lights_report(
            initialized,
            p_("Initialized light linking for %d light(s): %s"),
            p_("Initialized light linking for %d light(s): %s, and %d more"),
        )
        self.report({'INFO'}, message)
        return {"FINISHED"}


class LLP_OT_instances_data_all(LightHelperOperator, bpy.types.Operator):
    bl_idname = 'object.light_helper_instances_data_all'
    bl_label = "Make All Single-User"
    bl_description = "Make shared light linking collections single-user for all lights in the scene"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        from ..utils import has_shared_linking_collections, is_light_linking_source_editable

        if any(
                hasattr(obj, "light_linking")
                and is_light_linking_source_editable(obj)
                and has_shared_linking_collections(obj)
                for obj in context.scene.objects):
            return True
        cls.poll_message_set(p_("No lights with shared linking collections"))
        return False

    def execute(self, context):
        from ..utils import fix_all_shared_light_linking
        fixed_lights = fix_all_shared_light_linking(context.scene)
        if not fixed_lights:
            self.report({'WARNING'}, p_("No lights with shared linking collections"))
            return {"CANCELLED"}
        message = format_lights_report(
            fixed_lights,
            p_("Made %d light(s) single-user: %s"),
            p_("Made %d light(s) single-user: %s, and %d more"),
        )
        self.report({'INFO'}, message)
        return {"FINISHED"}
