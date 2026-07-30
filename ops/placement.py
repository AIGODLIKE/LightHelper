import bpy
from bpy.app.translations import pgettext_iface as p_
from bpy_extras import view3d_utils
from mathutils import Matrix, Quaternion, Vector

from ..utils.placement import (
    PlacementMode,
    adaptive_size_distance,
    adjust_distance,
    adjust_energy,
    adjust_roll,
    adjust_size,
    adjust_spot_size,
    ray_plane_intersection,
    solve_placement,
)
from ..utils.studio import (
    StudioEngineError,
    create_flag,
    create_reflector,
    create_scrim,
    ensure_track_to,
    is_studio_object,
    remove_studio_object,
    scrim_exposure,
    set_scrim_exposure,
    studio_kind,
)
from .common import LightHelperOperator


_ACTIVE_PLACEMENTS = {}


PLACEMENT_MODE_ITEMS = (
    ('REFLECT', "Reflect", "Place the light for a highlight reflected toward the view"),
    ('DIRECT', "Direct", "Place the light along the hit surface normal"),
    ('ORBIT', "Orbit", "Keep the current radial direction and distance around the target"),
)

TARGET_KIND_ITEMS = (
    ('AUTO', "Auto", "Adjust the selected light or managed studio object, otherwise create an Area light"),
    ('LIGHT', "Light", "Create a native Blender light"),
    ('SCRIM', "Scrim", "Create a managed Cycles emissive scrim"),
    ('FLAG', "Flag", "Create a managed light-blocking flag"),
    ('REFLECTOR', "Reflector", "Create a managed Cycles diffuse reflector"),
)

LIGHT_TYPE_ITEMS = (
    ('POINT', "Point", "Create a Point light"),
    ('AREA', "Area", "Create an Area light"),
    ('SPOT', "Spot", "Create a Spot light"),
    ('SUN', "Sun", "Create a Sun light"),
)


def _operator_setattr(operator, name, value) -> None:
    try:
        object.__setattr__(operator, name, value)
    except TypeError:
        setattr(operator, name, value)


def _copy_value(value):
    return value.copy() if hasattr(value, "copy") else value


def _snapshot_target(obj) -> dict:
    snapshot = {
        "matrix_world": obj.matrix_world.copy(),
        "rotation_mode": obj.rotation_mode,
    }
    if obj.type == 'LIGHT' and obj.data is not None:
        data = obj.data
        for name in (
                "energy", "color", "shadow_soft_size", "size", "size_y", "shape",
                "spot_size", "spot_blend", "angle"):
            if hasattr(data, name):
                snapshot[f"data.{name}"] = _copy_value(getattr(data, name))
    elif studio_kind(obj) == 'SCRIM':
        snapshot["scrim.exposure"] = scrim_exposure(obj)
    return snapshot


def _restore_target(obj, snapshot: dict) -> None:
    if obj is None or not snapshot:
        return
    obj.rotation_mode = snapshot["rotation_mode"]
    obj.matrix_world = snapshot["matrix_world"]
    if obj.type != 'LIGHT' or obj.data is None:
        if studio_kind(obj) == 'SCRIM' and "scrim.exposure" in snapshot:
            set_scrim_exposure(obj, snapshot["scrim.exposure"])
        return
    for path, value in snapshot.items():
        if path.startswith("data."):
            setattr(obj.data, path[5:], value)


def _light_size(light_data) -> float:
    if light_data.type == 'AREA':
        return max(0.001, float(light_data.size))
    if light_data.type in {'POINT', 'SPOT'}:
        return max(0.001, float(light_data.shadow_soft_size))
    return max(0.001, float(light_data.angle))


def _set_light_size(light_data, value: float) -> None:
    value = max(0.001, float(value))
    if light_data.type == 'AREA':
        if getattr(light_data, "shape", 'DISK') in {'RECTANGLE', 'ELLIPSE'}:
            ratio = light_data.size_y / max(0.001, light_data.size)
            if light_data.size != value:
                light_data.size = value
            size_y = max(0.001, value * ratio)
            if light_data.size_y != size_y:
                light_data.size_y = size_y
        elif light_data.size != value:
            light_data.size = value
    elif light_data.type in {'POINT', 'SPOT'}:
        if light_data.shadow_soft_size != value:
            light_data.shadow_soft_size = value
    else:
        value = min(3.141592653589793, value)
        if light_data.angle != value:
            light_data.angle = value


def _tag_region(region) -> None:
    try:
        if region is not None:
            region.tag_redraw()
    except (ReferenceError, RuntimeError):
        pass


class LLP_OT_place_light(LightHelperOperator, bpy.types.Operator):
    """Transactional native-light and managed studio placement operator."""

    bl_idname = 'view3d.light_helper_place'
    bl_label = "Light Placement"
    bl_description = "Place or adjust a light using Direct, Reflect, or Orbit behavior"
    bl_options = {'REGISTER', 'UNDO', 'BLOCKING'}

    mode: bpy.props.EnumProperty(name="Mode", items=PLACEMENT_MODE_ITEMS, default='REFLECT')
    target_kind: bpy.props.EnumProperty(name="Target", items=TARGET_KIND_ITEMS, default='AUTO')
    light_type: bpy.props.EnumProperty(name="Light Type", items=LIGHT_TYPE_ITEMS, default='AREA')
    adjust_selected: bpy.props.BoolProperty(
        name="Adjust Selected",
        description="Adjust the active supported object instead of creating a new one",
        default=True,
    )
    use_track_target: bpy.props.BoolProperty(
        name="Track Target",
        description="Create an optional managed Track To target when placement is confirmed",
        default=False,
    )
    distance: bpy.props.FloatProperty(name="Distance", default=5.0, min=0.001, soft_max=1000.0, subtype='DISTANCE')
    size: bpy.props.FloatProperty(name="Size", default=1.0, min=0.001, soft_max=100.0, subtype='DISTANCE')

    @classmethod
    def poll(cls, context):
        if context.area is None or context.area.type != 'VIEW_3D' or context.region is None or context.region.type != 'WINDOW':
            cls.poll_message_set(p_("Run Light Placement in a 3D Viewport"))
            return False
        if context.mode != 'OBJECT':
            cls.poll_message_set(p_("Light Placement requires Object Mode"))
            return False
        return context.scene is not None

    def _initialize_runtime(self, context) -> None:
        _operator_setattr(self, "_cleaned", False)
        _operator_setattr(self, "_finished", False)
        _operator_setattr(self, "_registry_key", None)
        _operator_setattr(self, "_target", None)
        _operator_setattr(self, "_created", False)
        _operator_setattr(self, "_snapshot", {})
        _operator_setattr(self, "_last_hit", None)
        _operator_setattr(self, "_last_normal", None)
        _operator_setattr(self, "_last_view", None)
        _operator_setattr(self, "_last_orbit", None)
        _operator_setattr(self, "_roll", 0.0)
        _operator_setattr(self, "_roll_modifier", False)
        _operator_setattr(self, "_adaptive_initialized", False)
        _operator_setattr(self, "_owner_window", context.window)
        _operator_setattr(self, "_owner_area", context.area)
        _operator_setattr(self, "_owner_region", context.region)
        _operator_setattr(self, "_window_key", context.window.as_pointer())
        _operator_setattr(self, "_area_key", context.area.as_pointer())
        _operator_setattr(self, "_region_key", context.region.as_pointer())
        _operator_setattr(self, "_previous_active", context.view_layer.objects.active)
        _operator_setattr(self, "_previous_selection", [(obj, obj.select_get()) for obj in context.selected_objects])

    def _supported_active_target(self, context):
        obj = context.active_object
        if obj is None or not self.adjust_selected:
            return None
        if obj.type == 'LIGHT':
            if self.target_kind in {'AUTO', 'LIGHT'}:
                return obj
            return None
        if is_studio_object(obj):
            kind = studio_kind(obj)
            if self.target_kind in {'AUTO', kind}:
                return obj
        return None

    def _resolve_new_kind(self) -> str:
        return 'LIGHT' if self.target_kind == 'AUTO' else self.target_kind

    def _create_target(self, context, location: Vector):
        kind = self._resolve_new_kind()
        if kind == 'LIGHT':
            data = bpy.data.lights.new(f"LH {self.light_type.title()}", self.light_type)
            obj = bpy.data.objects.new(data.name, data)
            collection = context.collection if context.collection is not None else context.scene.collection
            collection.objects.link(obj)
            obj.location = location
        elif kind == 'SCRIM':
            obj = create_scrim(context.scene, width=self.size, height=self.size)
        elif kind == 'FLAG':
            obj = create_flag(context.scene, width=self.size, height=self.size)
        elif kind == 'REFLECTOR':
            obj = create_reflector(context.scene, width=self.size, height=self.size)
        else:
            raise ValueError(f"Unsupported placement target: {kind}")
        for selected in list(context.selected_objects):
            selected.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        _operator_setattr(self, "_target", obj)
        _operator_setattr(self, "_created", True)
        return obj

    def _ray_hit(self, context, event):
        region = self._owner_region
        area = self._owner_area
        space = area.spaces.active
        region_3d = space.region_3d
        coord = (event.mouse_region_x, event.mouse_region_y)
        ray_origin = view3d_utils.region_2d_to_origin_3d(region, region_3d, coord)
        ray_direction = view3d_utils.region_2d_to_vector_3d(region, region_3d, coord).normalized()
        hit, location, normal, _face, hit_obj, _matrix = context.scene.ray_cast(
            context.evaluated_depsgraph_get(), ray_origin, ray_direction,
        )
        if hit:
            view_from_surface = (ray_origin - location).normalized()
            return location, normal.normalized(), view_from_surface, hit_obj

        center = (region.width * 0.5, region.height * 0.5)
        view_direction = view3d_utils.region_2d_to_vector_3d(region, region_3d, center).normalized()
        plane_normal = -view_direction
        fallback = ray_plane_intersection(
            tuple(ray_origin),
            tuple(ray_direction),
            tuple(context.scene.cursor.location),
            tuple(plane_normal),
        )
        if fallback is None:
            return None
        location = Vector(fallback)
        return location, plane_normal, (ray_origin - location).normalized(), None

    def _initialize_adaptive_values(self, hit_obj, target: Vector) -> None:
        if self._adaptive_initialized:
            return
        obj = self._target
        if not self._created and obj is not None:
            current_distance = (obj.matrix_world.translation - target).length
            if current_distance > 0.001:
                self.distance = current_distance
            if obj.type == 'LIGHT' and obj.data is not None:
                self.size = _light_size(obj.data)
            elif is_studio_object(obj):
                self.size = max(0.001, float(max(obj.scale.x, obj.scale.y)))
        else:
            diagonal = float(hit_obj.dimensions.length) if hit_obj is not None else 2.0
            self.size, self.distance = adaptive_size_distance(diagonal)
        _operator_setattr(self, "_adaptive_initialized", True)

    def _apply_size(self) -> None:
        obj = self._target
        if obj is None:
            return
        if obj.type == 'LIGHT' and obj.data is not None:
            _set_light_size(obj.data, self.size)
        elif is_studio_object(obj):
            current = max(0.001, float(max(obj.scale.x, obj.scale.y)))
            factor = self.size / current
            if factor != 1.0:
                obj.scale.x *= factor
                obj.scale.y *= factor

    def _apply_last_solution(self) -> bool:
        if self._target is None or self._last_hit is None:
            return False
        solution = solve_placement(
            tuple(self._last_hit),
            tuple(self._last_normal),
            tuple(self._last_view),
            self.distance,
            PlacementMode(self.mode),
            tuple(self._last_orbit) if self._last_orbit is not None else None,
        )
        obj = self._target
        position = Vector(solution.position)
        current_matrix = obj.matrix_world.copy()
        is_sun = obj.type == 'LIGHT' and obj.data is not None and obj.data.type == 'SUN'
        is_point = obj.type == 'LIGHT' and obj.data is not None and obj.data.type == 'POINT'
        desired_position = current_matrix.translation if is_sun else position
        if is_point:
            desired_rotation = current_matrix.to_quaternion()
        else:
            toward_target = -Vector(solution.direction_from_target)
            desired_rotation = (
                toward_target.to_track_quat('-Z', 'Y')
                @ Quaternion((0.0, 0.0, 1.0), self._roll)
            )
        desired_matrix = Matrix.LocRotScale(
            desired_position,
            desired_rotation,
            current_matrix.to_scale(),
        )
        if current_matrix != desired_matrix:
            obj.matrix_world = desired_matrix
        return True

    def _update_from_event(self, context, event) -> bool:
        hit = self._ray_hit(context, event)
        if hit is None:
            context.workspace.status_text_set(p_("No surface or cursor plane intersection"))
            return False
        location, normal, view_from_surface, hit_obj = hit
        if self._target is None:
            self._create_target(context, location)
        self._initialize_adaptive_values(hit_obj, location)
        if self._created:
            self._apply_size()
        if self.mode == 'ORBIT':
            current = self._target.matrix_world.translation - location
            orbit = current.normalized() if current.length > 1.0e-8 else normal
        else:
            orbit = None
        _operator_setattr(self, "_last_hit", location.copy())
        _operator_setattr(self, "_last_normal", normal.copy())
        _operator_setattr(self, "_last_view", view_from_surface.copy())
        _operator_setattr(self, "_last_orbit", orbit.copy() if orbit is not None else None)
        return self._apply_last_solution()

    def _adjust_wheel(self, event, steps: int) -> None:
        obj = self._target
        if obj is None:
            return
        if self._roll_modifier:
            _operator_setattr(self, "_roll", adjust_roll(self._roll, steps))
            self._apply_last_solution()
        elif event.shift:
            self.size = adjust_size(self.size, steps)
            self._apply_size()
        elif event.alt:
            self.distance = adjust_distance(self.distance, steps)
            self._apply_last_solution()
        elif event.ctrl:
            if obj.type == 'LIGHT' and obj.data is not None and obj.data.type == 'SPOT':
                value = adjust_spot_size(obj.data.spot_size, steps)
                if obj.data.spot_size != value:
                    obj.data.spot_size = value
        elif obj.type == 'LIGHT' and obj.data is not None:
            value = adjust_energy(obj.data.energy, steps)
            energy_property = obj.data.bl_rna.properties.get("energy")
            if energy_property is not None:
                value = min(float(energy_property.hard_max), max(float(energy_property.hard_min), value))
            if obj.data.energy != value:
                obj.data.energy = value
        elif studio_kind(obj) == 'SCRIM':
            set_scrim_exposure(obj, scrim_exposure(obj) + steps * 0.25)

    def _restore_selection(self, context) -> None:
        try:
            for obj in list(context.selected_objects):
                obj.select_set(False)
            for obj, was_selected in self._previous_selection:
                if was_selected and obj.name in context.view_layer.objects:
                    obj.select_set(True)
            previous = self._previous_active
            if previous is not None and previous.name in context.view_layer.objects:
                context.view_layer.objects.active = previous
        except (ReferenceError, RuntimeError):
            pass

    def _cancel_transaction(self, context) -> None:
        obj = self._target
        if obj is None:
            return
        if self._created:
            try:
                if is_studio_object(obj):
                    remove_studio_object(obj)
                else:
                    data = obj.data if obj.type == 'LIGHT' else None
                    bpy.data.objects.remove(obj, do_unlink=True)
                    if data is not None and data.users == 0:
                        bpy.data.lights.remove(data)
            finally:
                self._restore_selection(context)
        else:
            _restore_target(obj, self._snapshot)

    def _cleanup(self, context, *, restore: bool):
        if self._cleaned:
            return None
        _operator_setattr(self, "_cleaned", True)
        restore_error = None
        try:
            if restore:
                self._cancel_transaction(context)
        except BaseException as exc:
            restore_error = exc
        finally:
            try:
                context.workspace.status_text_set(None)
            except (AttributeError, ReferenceError, RuntimeError):
                pass
            try:
                context.window.cursor_modal_restore()
            except (AttributeError, ReferenceError, RuntimeError):
                pass
            _tag_region(self._owner_region)
            registry_key = self._registry_key
            if registry_key is not None and _ACTIVE_PLACEMENTS.get(registry_key) is self:
                _ACTIVE_PLACEMENTS.pop(registry_key, None)
        return restore_error

    def invoke(self, context, event):
        self._initialize_runtime(context)
        registry_key = (self._window_key, self._area_key)
        current_owner = _ACTIVE_PLACEMENTS.get(registry_key)
        if current_owner is not None and not getattr(current_owner, "_cleaned", True):
            self.report({'WARNING'}, p_("Light Placement is already active in this viewport"))
            return {'CANCELLED'}
        target = self._supported_active_target(context)
        if target is not None:
            _operator_setattr(self, "_target", target)
            _operator_setattr(self, "_snapshot", _snapshot_target(target))
        try:
            if not self._update_from_event(context, event):
                self._cleanup(context, restore=True)
                self.report({'WARNING'}, p_("No valid placement point"))
                return {'CANCELLED'}
            context.window.cursor_modal_set('CROSSHAIR')
            context.workspace.status_text_set(
                p_("LMB/Enter Confirm | Esc/RMB Cancel | Wheel EV | Shift Size | Alt Distance | Ctrl Spot | Z Roll"),
            )
            context.window_manager.modal_handler_add(self)
            _operator_setattr(self, "_registry_key", registry_key)
            _ACTIVE_PLACEMENTS[registry_key] = self
            return {'RUNNING_MODAL'}
        except (RuntimeError, StudioEngineError, ValueError) as exc:
            self._cleanup(context, restore=True)
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

    def modal(self, context, event):
        if self._cleaned:
            return {'FINISHED'}
        if event.type == 'WINDOW_DEACTIVATE':
            self._cleanup(context, restore=True)
            return {'CANCELLED'}
        try:
            if (context.window is None or context.area is None or context.region is None
                    or context.window.as_pointer() != self._window_key
                    or context.area.as_pointer() != self._area_key
                    or context.region.as_pointer() != self._region_key):
                self._cleanup(context, restore=True)
                return {'CANCELLED'}
        except (ReferenceError, RuntimeError):
            self._cleanup(context, restore=True)
            return {'CANCELLED'}

        try:
            if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
                self._cleanup(context, restore=True)
                return {'CANCELLED'}
            if event.type == 'Z':
                _operator_setattr(self, "_roll_modifier", event.value == 'PRESS')
                return {'RUNNING_MODAL'}
            if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
                self._update_from_event(context, event)
                _tag_region(self._owner_region)
                return {'RUNNING_MODAL'}
            if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and event.value == 'PRESS':
                steps = 1 if event.type == 'WHEELUPMOUSE' else -1
                self._adjust_wheel(event, steps)
                _tag_region(self._owner_region)
                return {'RUNNING_MODAL'}
            if event.type in {'LEFTMOUSE', 'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
                if self.use_track_target and self._target is not None:
                    is_point = self._target.type == 'LIGHT' and self._target.data.type == 'POINT'
                    if not is_point:
                        ensure_track_to(context.scene, self._target, location=self._last_hit)
                _operator_setattr(self, "_finished", True)
                self._cleanup(context, restore=False)
                return {'FINISHED'}
        except BaseException as exc:
            self._cleanup(context, restore=True)
            self.report({'ERROR'}, p_("Placement cancelled after an error: %s") % exc)
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        self._cleanup(context, restore=not self._finished)


def cancel_all_placements() -> None:
    """Best-effort transaction restore before add-on unregister or reload."""

    context = bpy.context
    for instance in list(_ACTIVE_PLACEMENTS.values()):
        if getattr(instance, "_cleaned", True):
            continue
        window = getattr(instance, "_owner_window", None)
        area = getattr(instance, "_owner_area", None)
        region = getattr(instance, "_owner_region", None)
        try:
            with context.temp_override(window=window, area=area, region=region):
                instance._cleanup(bpy.context, restore=True)
        except (AttributeError, ReferenceError, RuntimeError, TypeError):
            try:
                instance._cleanup(context, restore=True)
            except BaseException:
                pass
    _ACTIVE_PLACEMENTS.clear()


PLACEMENT_OPERATOR_CLASSES = (LLP_OT_place_light,)
