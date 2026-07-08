"""Viewport overlay drawing and picking for the light linking tool."""

from __future__ import annotations

import bpy
import blf
import gpu
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from . import (
    CollectionType,
    get_all_light_effect_items_state,
    get_linking_mode,
    get_pref,
)

_draw_handler_3d = None
_draw_handler_hud = None

_bbox_edges = (
    (0, 1), (1, 2), (2, 3), (3, 0),
    (4, 5), (5, 6), (6, 7), (7, 4),
    (0, 4), (1, 5), (2, 6), (3, 7),
)

COLOR_LINE_BOTH = (0.2, 0.9, 0.3, 0.85)
COLOR_LINE_LIGHT = (1.0, 0.75, 0.2, 0.8)
COLOR_LINE_SHADOW = (0.3, 0.6, 1.0, 0.8)
COLOR_LINE_NONE = (0.6, 0.6, 0.6, 0.5)

COLOR_OUTLINE_BOTH = (0.2, 0.9, 0.3, 0.5)
COLOR_OUTLINE_LIGHT = (1.0, 0.6, 0.1, 0.5)
COLOR_OUTLINE_SHADOW = (0.3, 0.55, 1.0, 0.5)

_polyline_shader = None


class LinkDrawTarget:
    __slots__ = (
        "center",
        "corners",
        "receiver",
        "blocker",
        "is_collection",
        "name",
    )

    def __init__(self, center, corners, receiver, blocker, is_collection, name):
        self.center = center
        self.corners = corners
        self.receiver = receiver
        self.blocker = blocker
        self.is_collection = is_collection
        self.name = name


class LinkOverlayCache:
    __slots__ = ("light", "targets", "outlines_hidden", "invalid")

    def __init__(self):
        self.light = None
        self.targets: list[LinkDrawTarget] = []
        self.outlines_hidden = False
        self.invalid = True

    def invalidate(self):
        self.invalid = True


_cache = LinkOverlayCache()


def get_overlay_cache() -> LinkOverlayCache:
    return _cache


def invalidate_overlay_cache():
    _cache.invalidate()


def _world_bbox_from_object(obj: bpy.types.Object) -> tuple[Vector, list[Vector]]:
    matrix = obj.matrix_world
    corners = [matrix @ Vector(corner) for corner in obj.bound_box]
    center = sum(corners, Vector()) / 8.0
    return center, corners


def _world_bbox_from_collection(coll: bpy.types.Collection) -> tuple[Vector | None, list[Vector] | None]:
    corners_all = []
    for obj in coll.objects:
        if obj.hide_viewport or obj.hide_get():
            continue
        if obj.type not in {"MESH", "CURVE", "SURFACE", "META", "FONT", "GPENCIL", "GREASEPENCIL"}:
            continue
        _, corners = _world_bbox_from_object(obj)
        corners_all.extend(corners)
    if not corners_all:
        return None, None
    min_co = Vector((
        min(c.x for c in corners_all),
        min(c.y for c in corners_all),
        min(c.z for c in corners_all),
    ))
    max_co = Vector((
        max(c.x for c in corners_all),
        max(c.y for c in corners_all),
        max(c.z for c in corners_all),
    ))
    corners = [
        Vector((min_co.x, min_co.y, min_co.z)),
        Vector((max_co.x, min_co.y, min_co.z)),
        Vector((max_co.x, max_co.y, min_co.z)),
        Vector((min_co.x, max_co.y, min_co.z)),
        Vector((min_co.x, min_co.y, max_co.z)),
        Vector((max_co.x, min_co.y, max_co.z)),
        Vector((max_co.x, max_co.y, max_co.z)),
        Vector((min_co.x, max_co.y, max_co.z)),
    ]
    center = (min_co + max_co) / 2.0
    return center, corners


def _channel_color(receiver: bool, blocker: bool, both_color, light_color, shadow_color, none_color):
    if receiver and blocker:
        return both_color
    if receiver:
        return light_color
    if blocker:
        return shadow_color
    return none_color


def _build_targets(light: bpy.types.Object, max_outlines: int) -> tuple[list[LinkDrawTarget], bool]:
    items_state = get_all_light_effect_items_state(light)
    targets = []
    for item, state in items_state.items():
        receiver = state[CollectionType.RECEIVER] is True
        blocker = state[CollectionType.BLOCKER] is True
        if isinstance(item, bpy.types.Object):
            if item.hide_viewport or item.hide_get():
                continue
            center, corners = _world_bbox_from_object(item)
            targets.append(LinkDrawTarget(center, corners, receiver, blocker, False, item.name))
        elif isinstance(item, bpy.types.Collection):
            if item.hide_viewport:
                continue
            center, corners = _world_bbox_from_collection(item)
            if center is None:
                continue
            targets.append(LinkDrawTarget(center, corners, receiver, blocker, True, item.name))
    outlines_hidden = max_outlines >= 0 and len(targets) > max_outlines
    return targets, outlines_hidden


def refresh_overlay_cache(context: bpy.types.Context, light: bpy.types.Object | None):
    if light is None:
        _cache.light = None
        _cache.targets = []
        _cache.outlines_hidden = False
        _cache.invalid = False
        return
    pref = get_pref(context)
    targets, outlines_hidden = _build_targets(light, pref.linking_tool_max_outlines)
    _cache.light = light
    _cache.targets = targets
    _cache.outlines_hidden = outlines_hidden
    _cache.invalid = False


def _get_polyline_shader():
    global _polyline_shader
    if _polyline_shader is None:
        _polyline_shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    return _polyline_shader


def _viewport_size(context: bpy.types.Context) -> tuple[float, float]:
    region = context.region
    if region is not None:
        return float(region.width), float(region.height)
    viewport = gpu.state.viewport_get()
    return float(viewport[2]), float(viewport[3])


def _draw_lines_batch(context: bpy.types.Context, coords, color, width=1.5):
    if len(coords) < 2:
        return
    shader = _get_polyline_shader()
    shader.bind()
    shader.uniform_float("viewportSize", _viewport_size(context))
    shader.uniform_float("lineWidth", width)
    shader.uniform_float("color", color)
    batch = batch_for_shader(shader, 'LINES', {"pos": coords})
    batch.draw(shader)


def _draw_overlay_3d():
    context = bpy.context
    wm_props = context.window_manager.light_helper_property
    if not wm_props.linking_tool_active or not wm_props.show_linking_overlay:
        return
    light = wm_props.linking_tool_light
    if light is None:
        return
    if _cache.invalid or _cache.light != light:
        refresh_overlay_cache(context, light)

    targets = _cache.targets
    if not targets:
        return

    light_pos = light.matrix_world.translation.copy()
    gpu.state.blend_set('ALPHA')
    gpu.state.depth_test_set('LESS_EQUAL')

    line_coords = []
    for target in targets:
        color = _channel_color(
            target.receiver, target.blocker,
            COLOR_LINE_BOTH, COLOR_LINE_LIGHT, COLOR_LINE_SHADOW, COLOR_LINE_NONE,
        )
        _draw_lines_batch(context, [light_pos, target.center], color, width=2.0)

    if not _cache.outlines_hidden:
        for target in targets:
            if target.corners is None:
                continue
            color = _channel_color(
                target.receiver, target.blocker,
                COLOR_OUTLINE_BOTH, COLOR_OUTLINE_LIGHT, COLOR_OUTLINE_SHADOW, COLOR_LINE_NONE,
            )
            edge_coords = []
            for i0, i1 in _bbox_edges:
                edge_coords.append(target.corners[i0])
                edge_coords.append(target.corners[i1])
            _draw_lines_batch(context, edge_coords, color, width=1.5)

    gpu.state.depth_test_set('NONE')
    gpu.state.blend_set('NONE')


def _hud_lines(context: bpy.types.Context) -> list[str]:
    from bpy.app.translations import pgettext_iface as p_

    wm_props = context.window_manager.light_helper_property
    light = wm_props.linking_tool_light
    lines = []
    if light is None:
        lines.append(p_("Light: (none)"))
    else:
        mode = get_linking_mode(light)
        mode_label = p_("Exclude") if mode == "EXCLUDE" else p_("Include")
        lines.append(f"{p_('Light')}: {light.name}  [{mode_label}]")
    lines.append(p_("LClick: Select/Toggle Link"))
    lines.append(f"{p_('Spacebar')}: {p_('Toggle Light')}   D: {p_('Toggle Shadow')}")
    lines.append(f"A: {p_('Exclude')}/{p_('Include')}    X: {p_('Toggle Overlay')}")
    lines.append(p_("Ctrl+Wheel: Prev/Next Light"))

    if _cache.invalid or _cache.light != light:
        refresh_overlay_cache(context, light)
    link_count = len(_cache.targets)
    if link_count > 0:
        if _cache.outlines_hidden:
            lines.append(p_("Links: %d, outlines hidden") % link_count)
        else:
            lines.append(p_("Links: %d") % link_count)
    if not wm_props.show_linking_overlay:
        lines.append(p_("Overlay hidden"))
    return lines


def _draw_overlay_hud():
    context = bpy.context
    wm_props = context.window_manager.light_helper_property
    if not wm_props.linking_tool_active:
        return

    region = context.region
    if region is None:
        return

    lines = _hud_lines(context)
    font_id = 0
    font_size = 13
    line_height = 18
    margin = 16
    blf.size(font_id, font_size)

    blf.enable(font_id, blf.SHADOW)
    blf.shadow(font_id, 3, 0.0, 0.0, 0.0, 0.7)
    for i, line in enumerate(lines):
        blf.position(font_id, margin, margin + i * line_height, 0)
        blf.color(font_id, 1.0, 1.0, 1.0, 0.95)
        blf.draw(font_id, line)
    blf.disable(font_id, blf.SHADOW)


def tag_view3d_redraw(context: bpy.types.Context | None = None):
    ctx = context if context is not None else bpy.context
    if ctx is None:
        return
    for window in ctx.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def register_draw_handlers():
    global _draw_handler_3d, _draw_handler_hud
    if _draw_handler_3d is None:
        _draw_handler_3d = bpy.types.SpaceView3D.draw_handler_add(
            _draw_overlay_3d, (), 'WINDOW', 'POST_VIEW',
        )
    if _draw_handler_hud is None:
        _draw_handler_hud = bpy.types.SpaceView3D.draw_handler_add(
            _draw_overlay_hud, (), 'WINDOW', 'POST_PIXEL',
        )


def unregister_draw_handlers():
    global _draw_handler_3d, _draw_handler_hud
    if _draw_handler_3d is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handler_3d, 'WINDOW')
        _draw_handler_3d = None
    if _draw_handler_hud is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handler_hud, 'WINDOW')
        _draw_handler_hud = None


def _view3d_window_at_mouse(context: bpy.types.Context, event):
    if context.area and context.area.type == 'VIEW_3D':
        region = context.region
        if region and region.type == 'WINDOW':
            return context.area, region
    if context.screen is None:
        return None, None
    mx, my = event.mouse_x, event.mouse_y
    for area in context.screen.areas:
        if area.type != 'VIEW_3D':
            continue
        for region in area.regions:
            if region.type != 'WINDOW':
                continue
            if (region.x <= mx < region.x + region.width
                    and region.y <= my < region.y + region.height):
                return area, region
    return None, None


def _event_region_coord(context, event, region) -> tuple[float, float]:
    if context.region == region:
        return event.mouse_region_x, event.mouse_region_y
    return event.mouse_x - region.x, event.mouse_y - region.y


def raycast_object_under_mouse(context: bpy.types.Context, event) -> bpy.types.Object | None:
    area, region = _view3d_window_at_mouse(context, event)
    if area is None or region is None:
        return None
    coord = _event_region_coord(context, event, region)
    with context.temp_override(window=context.window, screen=context.screen, area=area, region=region):
        rv3d = context.region_data
        if rv3d is None:
            return None
        origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
        direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
        depsgraph = context.evaluated_depsgraph_get()
        hit, _loc, _normal, _index, obj, _matrix = context.scene.ray_cast(depsgraph, origin, direction)
        if not hit or obj is None:
            return None
        from . import resolve_original_id
        return resolve_original_id(obj)
