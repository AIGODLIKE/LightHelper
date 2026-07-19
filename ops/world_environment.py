import bpy
from bpy.app.translations import pgettext_iface as p_

from .common import LightHelperOperator


class LLP_OT_convert_world_environment(LightHelperOperator, bpy.types.Operator):
    bl_idname = "world.light_helper_convert_environment"
    bl_label = "Convert World Environment"
    bl_description = "Convert the connected World HDRI or solid Background color into one code-generated, linkable inward-facing environment sphere"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        from ..utils.world_environment import find_world_environment, get_world_dome
        scene = context.scene
        if scene.render.engine != 'CYCLES':
            cls.poll_message_set(p_("World HDRI conversion is only available in Cycles"))
            return False
        if get_world_dome(scene) is not None:
            return True
        info = find_world_environment(scene)
        if not info.has_source:
            cls.poll_message_set(p_("No usable World environment source was found in the active World"))
            return False
        return True

    def execute(self, context):
        from ..utils.world_environment import (
            convert_world_environment,
            dome_face_stats,
            find_world_environment,
        )
        scene = context.scene
        if scene.render.engine != 'CYCLES':
            self.report({'ERROR'}, p_("World HDRI conversion is only available in Cycles"))
            return {'CANCELLED'}
        info = find_world_environment(scene)
        try:
            dome, status = convert_world_environment(scene)
        except Exception as exc:
            self.report({'ERROR'}, p_("World environment conversion failed: %s") % str(exc))
            return {'CANCELLED'}
        if dome is None:
            self.report({'WARNING'}, p_("No usable World environment source was found in the active World"))
            return {'CANCELLED'}
        total, inward = dome_face_stats(dome)
        if total == 0 or total != inward:
            if status == "CONVERTED":
                try:
                    from ..utils.world_environment import restore_world_environment
                    restore_world_environment(scene)
                except Exception:
                    pass
            self.report({'ERROR'}, p_("The generated environment sphere failed its inward-normal validation"))
            return {'CANCELLED'}
        if info.image is not None and info.connected_image_count > 1:
            self.report(
                {'WARNING'},
                p_("Converted %s; %d connected HDRI images were found and the nearest active image was used")
                % (info.image.name, info.connected_image_count),
            )
        elif status == "EXISTS":
            self.report({'INFO'}, p_("The existing world environment dome was repaired"))
        elif info.image is None:
            self.report({'INFO'}, p_("Converted World Background color to environment dome"))
        else:
            self.report({'INFO'}, p_("Converted World HDRI to environment dome: %s") % info.image.name)
        return {'FINISHED'}


class LLP_OT_restore_world_environment(LightHelperOperator, bpy.types.Operator):
    bl_idname = "world.light_helper_restore_environment"
    bl_label = "Restore Original World"
    bl_description = "Restore the original World and remove only the environment-dome data managed by Light Helper"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        from ..utils.world_environment import get_world_dome
        if get_world_dome(context.scene) is not None:
            return True
        cls.poll_message_set(p_("No managed world environment dome exists"))
        return False

    def execute(self, context):
        from ..utils.world_environment import restore_world_environment
        try:
            restored, status = restore_world_environment(context.scene)
        except Exception as exc:
            self.report({'ERROR'}, p_("World restoration failed: %s") % str(exc))
            return {'CANCELLED'}
        if not restored:
            if status == "SHARED_SCENE_DATA":
                self.report(
                    {'ERROR'},
                    p_("The environment dome is still shared through a user collection; move it back to its managed collection before restoring"),
                )
                return {'CANCELLED'}
            self.report({'WARNING'}, p_("No managed world environment dome exists"))
            return {'CANCELLED'}
        if status == "RESTORED_NO_WORLD":
            self.report({'WARNING'}, p_("The dome was removed, but the original World data-block is no longer available"))
        else:
            self.report({'INFO'}, p_("Original World restored"))
        return {'FINISHED'}


class LLP_OT_sync_world_sun_exclusions(LightHelperOperator, bpy.types.Operator):
    bl_idname = "world.light_helper_sync_sun_exclusions"
    bl_label = "Sync Sun Exclusions"
    bl_description = "Ensure every Sun in the current scene excludes the managed environment dome without changing user links"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        from ..utils.world_environment import get_world_dome
        if context.scene.render.engine != 'CYCLES':
            cls.poll_message_set(p_("World Environment Linking requires Cycles"))
            return False
        if get_world_dome(context.scene) is not None:
            return True
        cls.poll_message_set(p_("No managed world environment dome exists"))
        return False

    def execute(self, context):
        from ..utils.world_environment import ensure_sun_exclusions
        if context.scene.render.engine != 'CYCLES':
            self.report({'ERROR'}, p_("World Environment Linking requires Cycles"))
            return {'CANCELLED'}
        count = ensure_sun_exclusions(context.scene)
        self.report({'INFO'}, p_("Synchronized %d Sun light(s)") % count)
        return {'FINISHED'}


class LLP_OT_select_world_environment_dome(LightHelperOperator, bpy.types.Operator):
    bl_idname = "world.light_helper_select_environment_dome"
    bl_label = "Select Environment Dome"
    bl_description = "Select the managed environment dome in the current view layer"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        from ..utils.world_environment import get_world_dome
        dome = get_world_dome(context.scene)
        if dome is not None and dome.name in context.view_layer.objects:
            return True
        cls.poll_message_set(p_("The environment dome is not available in this view layer"))
        return False

    def execute(self, context):
        from ..utils.world_environment import get_world_dome
        dome = get_world_dome(context.scene)
        if dome is None or dome.name not in context.view_layer.objects:
            return {'CANCELLED'}
        for obj in context.selected_objects:
            obj.select_set(False)
        dome.select_set(True)
        context.view_layer.objects.active = dome
        return {'FINISHED'}
