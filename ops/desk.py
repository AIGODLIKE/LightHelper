"""Lighting Desk modal owner and undoable link-matrix sibling operators."""

import json

import bpy
from bpy.app.translations import pgettext_iface as p_

from .common import LightHelperOperator


def _operator_setattr(operator, name, value) -> None:
    try:
        object.__setattr__(operator, name, value)
    except TypeError:
        setattr(operator, name, value)


def _resolve_item(item_name: str, item_kind: str):
    if item_kind == "COLLECTION":
        return bpy.data.collections.get(item_name)
    return bpy.data.objects.get(item_name)


def _set_advanced_mode(source) -> None:
    props = getattr(source, "light_helper_property", None)
    if props is not None and hasattr(props, "linking_edit_mode"):
        try:
            props.linking_edit_mode = 'ADVANCED'
        except (AttributeError, TypeError, ValueError):
            pass


def _apply_channel_state(
    context, source_name, item_name, item_kind, channel, state, *, notify=True,
    sync_helpers=True,
) -> bool:
    from ..utils import CollectionType, set_item_channel_state

    source = context.scene.objects.get(source_name)
    item = _resolve_item(item_name, item_kind)
    if source is None or source.type != 'LIGHT' or item is None:
        return False
    coll_type = CollectionType.RECEIVER if channel == "RECEIVER" else CollectionType.BLOCKER
    _set_advanced_mode(source)
    return set_item_channel_state(
        source,
        item,
        coll_type,
        state,
        context,
        notify=notify,
        sync_helpers=sync_helpers,
    )


class LLP_OT_lighting_desk(LightHelperOperator, bpy.types.Operator):
    bl_idname = "view3d.light_helper_lighting_desk"
    bl_label = "Lighting Desk"
    bl_description = "Open the full-area LightHelper linking, mixer, looks, and studio desk"
    bl_options = {'REGISTER', 'BLOCKING'}

    @classmethod
    def poll(cls, context):
        if context.area is None or context.area.type != 'VIEW_3D':
            cls.poll_message_set(p_("Open Lighting Desk from a 3D View"))
            return False
        if context.region is None or context.region.type != 'WINDOW':
            cls.poll_message_set(p_("Lighting Desk requires the 3D View window region"))
            return False
        return True

    def invoke(self, context, _event):
        from ..ui.desk import new_desk_session

        _operator_setattr(self, "_session", None)
        session = new_desk_session(context, self)
        if session is None:
            self.report({'INFO'}, p_("Lighting Desk is already open in this area"))
            return {'CANCELLED'}
        _operator_setattr(self, "_session", session)
        try:
            context.window_manager.modal_handler_add(self)
        except BaseException:
            session.cleanup()
            raise
        return {'RUNNING_MODAL'}

    def _finish(self, cancelled=False):
        session = getattr(self, "_session", None)
        if session is not None:
            session.cleanup()
        return {'CANCELLED'} if cancelled else {'FINISHED'}

    def modal(self, context, event):
        session = getattr(self, "_session", None)
        if session is None or session.cleaned:
            return {'FINISHED'}
        try:
            if session.close_requested:
                return self._finish()
            if event.type == 'WINDOW_DEACTIVATE':
                return self._finish(cancelled=True)
            if not session.is_owner_alive():
                return self._finish(cancelled=True)
            if event.type == 'ESC' and event.value == 'PRESS':
                return self._finish()

            same_area = context.window is session.window and context.area is session.area
            if not same_area:
                return {'PASS_THROUGH'}
            if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
                session.handle_motion(event)
                return {'RUNNING_MODAL'}
            if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and event.value == 'PRESS':
                session.handle_wheel(context, event)
                return {'RUNNING_MODAL'}
            if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
                result = session.handle_click(context, event)
                if result == "CLOSE":
                    return self._finish()
                return {'RUNNING_MODAL'}
            if session.handle_text(event):
                return {'RUNNING_MODAL'}
            return {'RUNNING_MODAL'}
        except BaseException:
            self._finish(cancelled=True)
            raise

    def cancel(self, _context):
        self._finish(cancelled=True)


class LLP_OT_close_lighting_desk(LightHelperOperator, bpy.types.Operator):
    bl_idname = "view3d.light_helper_close_lighting_desk"
    bl_label = "Close Lighting Desk"
    bl_description = "Request the Lighting Desk in this area to close"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        from ..ui.desk import get_desk_session

        return get_desk_session(context.window, context.area) is not None

    def execute(self, context):
        from ..ui.desk import get_desk_session, tag_owner_window

        session = get_desk_session(context.window, context.area)
        if session is None:
            return {'CANCELLED'}
        session.close_requested = True
        try:
            tag_owner_window(session.area)
        finally:
            session.cleanup()
        return {'FINISHED'}


class LLP_OT_desk_set_channel(LightHelperOperator, bpy.types.Operator):
    bl_idname = "object.light_helper_desk_set_channel"
    bl_label = "Set Light Link State"
    bl_description = "Set one Lighting Desk illumination or shadow link state"
    bl_options = {'REGISTER', 'UNDO'}

    source_name: bpy.props.StringProperty(default="", options={'HIDDEN', 'SKIP_SAVE'})
    item_name: bpy.props.StringProperty(default="", options={'HIDDEN', 'SKIP_SAVE'})
    item_kind: bpy.props.EnumProperty(
        items=(("OBJECT", "Object", ""), ("COLLECTION", "Collection", "")),
        options={'HIDDEN', 'SKIP_SAVE'},
    )
    channel: bpy.props.EnumProperty(
        items=(("RECEIVER", "Illumination", ""), ("BLOCKER", "Shadow", "")),
        options={'HIDDEN', 'SKIP_SAVE'},
    )
    state: bpy.props.EnumProperty(
        items=(("OFF", "Off", ""), ("INCLUDE", "Include", ""), ("EXCLUDE", "Exclude", "")),
        options={'HIDDEN', 'SKIP_SAVE'},
    )

    def execute(self, context):
        if not _apply_channel_state(
            context,
            self.source_name,
            self.item_name,
            self.item_kind,
            self.channel,
            self.state,
        ):
            # Setting the current value is a successful no-op.  Only reject
            # missing/unusable identities, which are rechecked here.
            source = context.scene.objects.get(self.source_name)
            item = _resolve_item(self.item_name, self.item_kind)
            if source is None or source.type != 'LIGHT' or item is None:
                self.report({'WARNING'}, p_("Lighting Desk item is no longer available"))
                return {'CANCELLED'}
        return {'FINISHED'}


class LLP_OT_desk_set_channel_bulk(LightHelperOperator, bpy.types.Operator):
    bl_idname = "object.light_helper_desk_set_channel_bulk"
    bl_label = "Set Selected Light Link States"
    bl_description = "Set one channel state for the selected Lighting Desk matrix cells"
    bl_options = {'REGISTER', 'UNDO'}

    entries_json: bpy.props.StringProperty(default="[]", options={'HIDDEN', 'SKIP_SAVE'})
    channel: bpy.props.EnumProperty(
        items=(("RECEIVER", "Illumination", ""), ("BLOCKER", "Shadow", "")),
        options={'HIDDEN', 'SKIP_SAVE'},
    )
    state: bpy.props.EnumProperty(
        items=(("OFF", "Off", ""), ("INCLUDE", "Include", ""), ("EXCLUDE", "Exclude", "")),
        options={'HIDDEN', 'SKIP_SAVE'},
    )

    def execute(self, context):
        try:
            entries = json.loads(self.entries_json)
        except (TypeError, ValueError):
            entries = None
        if not isinstance(entries, list):
            self.report({'WARNING'}, p_("Invalid Lighting Desk selection"))
            return {'CANCELLED'}
        changed = 0
        skipped = 0
        touched_sources = set()
        for entry in entries:
            if not isinstance(entry, (list, tuple)) or len(entry) != 3:
                skipped += 1
                continue
            if _apply_channel_state(
                context,
                str(entry[0]),
                str(entry[1]),
                str(entry[2]),
                self.channel,
                self.state,
                notify=False,
                sync_helpers=False,
            ):
                changed += 1
                touched_sources.add(str(entry[0]))
        if changed:
            from ..utils import sync_safe_helpers_for_light
            for source_name in touched_sources:
                source = context.scene.objects.get(source_name)
                if source is not None:
                    sync_safe_helpers_for_light(source)
            from ..utils.overlay import notify_linking_changed

            notify_linking_changed(context)
        if skipped:
            self.report({'WARNING'}, p_("Skipped %d unavailable Lighting Desk items") % skipped)
        if not changed and not entries:
            self.report({'INFO'}, p_("No Lighting Desk cells selected"))
        return {'FINISHED'}


DESK_CLASSES = (
    LLP_OT_lighting_desk,
    LLP_OT_close_lighting_desk,
    LLP_OT_desk_set_channel,
    LLP_OT_desk_set_channel_bulk,
)


__all__ = [
    "DESK_CLASSES",
    "LLP_OT_close_lighting_desk",
    "LLP_OT_desk_set_channel",
    "LLP_OT_desk_set_channel_bulk",
    "LLP_OT_lighting_desk",
]
