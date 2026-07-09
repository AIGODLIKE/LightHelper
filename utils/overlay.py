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

HUD_FONT_SIZE = 13
HUD_LINE_HEIGHT = 18
HUD_PADDING = 8

_hud_consumed_click = False

_bbox_edges = (
    (0, 1), (1, 2), (2, 3), (3, 0),
    (4, 5), (5, 6), (6, 7), (7, 4),
    (0, 4), (1, 5), (2, 6), (3, 7),
)

COLOR_LINE_SHADOW = (0.3, 0.6, 1.0, 0.8)
COLOR_LINE_NONE = (0.6, 0.6, 0.6, 0.5)
COLOR_OUTLINE_SHADOW = (0.3, 0.55, 1.0, 0.25)

COLOR_INCLUDE_LINE_BOTH = (0.2, 0.9, 0.3, 0.85)
COLOR_INCLUDE_LINE_LIGHT = (0.35, 0.95, 0.4, 0.8)
COLOR_INCLUDE_OUTLINE_BOTH = (0.2, 0.9, 0.3, 0.25)
COLOR_INCLUDE_OUTLINE_LIGHT = (0.35, 0.95, 0.4, 0.25)

COLOR_EXCLUDE_LINE_BOTH = (0.95, 0.22, 0.18, 0.85)
COLOR_EXCLUDE_LINE_LIGHT = (1.0, 0.35, 0.25, 0.8)
COLOR_EXCLUDE_OUTLINE_BOTH = (0.95, 0.22, 0.18, 0.25)
COLOR_EXCLUDE_OUTLINE_LIGHT = (1.0, 0.3, 0.2, 0.25)

COLOR_SUBJECT_OUTLINE = (0.95, 0.95, 0.95, 0.25)

OVERLAY_MODE_OFF = 'OFF'
OVERLAY_MODE_SELECTED = 'SELECTED'
OVERLAY_MODE_ALL = 'ALL'
INACTIVE_LINK_ALPHA_SCALE = 0.1

_polyline_shader = None


class LinkDrawTarget:
    __slots__ = (
        "item",
        "receiver",
        "blocker",
        "is_collection",
        "name",
    )

    def __init__(self, item, receiver, blocker, is_collection, name):
        self.item = item
        self.receiver = receiver
        self.blocker = blocker
        self.is_collection = is_collection
        self.name = name


class LinkDrawGroup:
    __slots__ = ("subject", "targets", "is_active")

    def __init__(self, subject: bpy.types.Object | None, targets: list[LinkDrawTarget], is_active: bool):
        self.subject = subject
        self.targets = targets
        self.is_active = is_active


class LinkOverlayCache:
    __slots__ = ("overlay_mode", "subject_mode", "light", "object", "groups", "outlines_hidden", "invalid")

    def __init__(self):
        self.overlay_mode = OVERLAY_MODE_SELECTED
        self.subject_mode = 'LIGHT'
        self.light = None
        self.object = None
        self.groups: list[LinkDrawGroup] = []
        self.outlines_hidden = False
        self.invalid = True

    def invalidate(self):
        self.invalid = True


_cache = LinkOverlayCache()


def notify_linking_changed(context: bpy.types.Context | None = None) -> None:
    ctx = context if context is not None else bpy.context
    if ctx is None or ctx.window_manager is None:
        return
    wm_props = ctx.window_manager.light_helper_property
    if not wm_props.linking_tool_active:
        return
    invalidate_overlay_cache()
    refresh_overlay_cache(ctx)
    tag_view3d_redraw(ctx)


def hud_consumed_click() -> bool:
    return _hud_consumed_click


def clear_hud_consumed_click() -> None:
    global _hud_consumed_click
    _hud_consumed_click = False


def mark_hud_consumed_click() -> None:
    global _hud_consumed_click
    _hud_consumed_click = True


def _hud_info_lines(context: bpy.types.Context) -> list[str]:
    from bpy.app.translations import pgettext_iface as p_

    wm_props = context.window_manager.light_helper_property
    subject_mode = wm_props.linking_tool_subject_mode
    lines = []

    if subject_mode == 'OBJECT':
        obj = wm_props.linking_tool_object
        if obj is None:
            lines.append(p_("Object: (none)"))
        else:
            lines.append(f"{p_('Object')}: {obj.name}")
    else:
        light = wm_props.linking_tool_light
        if light is None:
            lines.append(p_("Light: (none)"))
        else:
            mode = get_linking_mode(light)
            mode_label = p_("Exclude") if mode == "EXCLUDE" else p_("Include")
            lines.append(f"{p_('Light')}: {light.name}  [{mode_label}]")

    if cache_needs_refresh(context):
        refresh_overlay_cache(context)
    link_count = len(_active_group_targets())
    if link_count > 0:
        if _cache.outlines_hidden:
            lines.append(p_("Links: %d, outlines hidden") % link_count)
        else:
            lines.append(p_("Links: %d") % link_count)
    else:
        lines.append(p_("Links: %d") % 0)

    overlay_mode = wm_props.linking_tool_overlay_mode
    if overlay_mode == OVERLAY_MODE_OFF:
        lines.append(p_("Overlay: Off"))
    elif overlay_mode == OVERLAY_MODE_ALL:
        lines.append(p_("Overlay: All"))
    else:
        lines.append(p_("Overlay: Selected"))
    return lines


def _hud_shortcut_lines(subject_mode: str) -> list[str]:
    from bpy.app.translations import pgettext_iface as p_

    lines = [p_("Ctrl+LClick: Switch Subject Mode")]
    if subject_mode == 'OBJECT':
        lines.extend([
            p_("LClick: Switch Object Subject"),
            p_("LClick Light: Toggle Light Link"),
        ])
    else:
        lines.append(p_("LClick: Select/Toggle Link"))
    lines.extend([
        f"L / {p_('Spacebar')}: {p_('Toggle Light')}",
        f"S: {p_('Toggle Shadow')}",
        f"A: {p_('Exclude')}/{p_('Include')}",
        f"X: {p_('Cycle Overlay')}",
        f"Esc: {p_('Exit Tool')}",
    ])
    if subject_mode == 'OBJECT':
        lines.append(p_("Ctrl+Wheel: Prev/Next Object"))
    else:
        lines.append(p_("Ctrl+Wheel: Prev/Next Light"))
    lines.append(p_("LDrag on HUD: Move HUD"))
    return lines


def _hud_lines(context: bpy.types.Context) -> list[str]:
    """Top-to-bottom: status info, blank separator, then shortcuts."""
    wm_props = context.window_manager.light_helper_property
    info = _hud_info_lines(context)
    shortcuts = _hud_shortcut_lines(wm_props.linking_tool_subject_mode)
    return info + [""] + shortcuts


def _hud_line_color(subject_mode: str, line: str) -> tuple[float, float, float, float]:
    from bpy.app.translations import pgettext_iface as p_

    if subject_mode == 'OBJECT' and line == p_("Ctrl+LClick: Switch Subject Mode"):
        return (1.0, 0.35, 0.3, 1.0)
    if not line:
        return (1.0, 1.0, 1.0, 0.0)
    return (1.0, 1.0, 1.0, 0.95)


def _hud_bounds(context: bpy.types.Context, region: bpy.types.Region) -> tuple[float, float, float, float]:
    wm_props = context.window_manager.light_helper_property
    x = float(wm_props.linking_tool_hud_x)
    y = float(wm_props.linking_tool_hud_y)
    lines = _hud_lines(context)
    font_id = 0
    blf.size(font_id, HUD_FONT_SIZE)
    max_w = 0.0
    for line in lines:
        if not line:
            continue
        width, _height = blf.dimensions(font_id, line)
        max_w = max(max_w, width)
    total_h = len(lines) * HUD_LINE_HEIGHT if lines else HUD_LINE_HEIGHT
    # Anchor is bottom-left; content grows upward.
    return (
        x - HUD_PADDING,
        y - HUD_PADDING,
        x + max_w + HUD_PADDING,
        y + total_h + HUD_PADDING,
    )


def mouse_over_hud(context: bpy.types.Context, event) -> bool:
    wm_props = context.window_manager.light_helper_property
    if not wm_props.linking_tool_active or not wm_props.linking_tool_show_hud:
        return False
    region = context.region
    if region is None or region.type != 'WINDOW':
        return False
    x0, y0, x1, y1 = _hud_bounds(context, region)
    mx = float(event.mouse_region_x)
    my = float(event.mouse_region_y)
    return x0 <= mx <= x1 and y0 <= my <= y1


def invalidate_overlay_cache():
    _cache.invalidate()
    _cache.light = None
    _cache.object = None
    _cache.groups = []
    _cache.outlines_hidden = False


def _scale_color_alpha(color, scale: float):
    return (color[0], color[1], color[2], color[3] * scale)


def _active_group_targets() -> list[LinkDrawTarget]:
    for group in _cache.groups:
        if group.is_active:
            return group.targets
    return []


def get_active_link_count(context: bpy.types.Context | None = None) -> int:
    """Read cached active link count. Does not refresh from draw paths."""
    return len(_active_group_targets())


def cycle_overlay_mode(current_mode: str) -> str:
    modes = (OVERLAY_MODE_OFF, OVERLAY_MODE_SELECTED, OVERLAY_MODE_ALL)
    if current_mode not in modes:
        return OVERLAY_MODE_SELECTED
    return modes[(modes.index(current_mode) + 1) % len(modes)]


def _is_light_overlay_ready(light: bpy.types.Object, context: bpy.types.Context | None = None) -> bool:
    from . import is_linking_initialized, is_tool_light_source
    return is_tool_light_source(light, context) and is_linking_initialized(light)


def _subject_cache_key(subject_mode: str, subject: bpy.types.Object | None) -> tuple[str, str | None]:
    if subject is None:
        return subject_mode, None
    from . import resolve_original_id
    subject = resolve_original_id(subject)
    return subject_mode, subject.name


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


def _resolve_target_linking_mode(group: LinkDrawGroup, target: LinkDrawTarget, subject_mode: str,
                                 context: bpy.types.Context | None = None) -> str:
    from . import is_tool_light_source
    if (subject_mode == 'OBJECT'
            and isinstance(target.item, bpy.types.Object)
            and is_tool_light_source(target.item, context)):
        return get_linking_mode(target.item)
    if group.subject is not None and is_tool_light_source(group.subject, context):
        return get_linking_mode(group.subject)
    return "INCLUDE"


def _target_line_colors(linking_mode: str):
    if linking_mode == "EXCLUDE":
        return (
            COLOR_EXCLUDE_LINE_BOTH,
            COLOR_EXCLUDE_LINE_LIGHT,
            COLOR_LINE_SHADOW,
            COLOR_LINE_NONE,
        )
    return (
        COLOR_INCLUDE_LINE_BOTH,
        COLOR_INCLUDE_LINE_LIGHT,
        COLOR_LINE_SHADOW,
        COLOR_LINE_NONE,
    )


def _target_outline_colors(linking_mode: str):
    if linking_mode == "EXCLUDE":
        return (
            COLOR_EXCLUDE_OUTLINE_BOTH,
            COLOR_EXCLUDE_OUTLINE_LIGHT,
            COLOR_OUTLINE_SHADOW,
            COLOR_LINE_NONE,
        )
    return (
        COLOR_INCLUDE_OUTLINE_BOTH,
        COLOR_INCLUDE_OUTLINE_LIGHT,
        COLOR_OUTLINE_SHADOW,
        COLOR_LINE_NONE,
    )


def _target_world_bbox(target: LinkDrawTarget) -> tuple[Vector | None, list[Vector] | None]:
    if target.is_collection:
        if target.item.hide_viewport:
            return None, None
        return _world_bbox_from_collection(target.item)
    if isinstance(target.item, bpy.types.Object):
        if target.item.hide_viewport or target.item.hide_get():
            return None, None
        return _world_bbox_from_object(target.item)
    return None, None


def _build_targets_from_light(light: bpy.types.Object, max_outlines: int) -> tuple[list[LinkDrawTarget], bool]:
    items_state = get_all_light_effect_items_state(light)
    targets = []
    for item, state in items_state.items():
        receiver = state[CollectionType.RECEIVER] is True
        blocker = state[CollectionType.BLOCKER] is True
        if isinstance(item, bpy.types.Object):
            if item.hide_viewport or item.hide_get():
                continue
            targets.append(LinkDrawTarget(item, receiver, blocker, False, item.name))
        elif isinstance(item, bpy.types.Collection):
            if item.hide_viewport:
                continue
            center, corners = _world_bbox_from_collection(item)
            if center is None:
                continue
            targets.append(LinkDrawTarget(item, receiver, blocker, True, item.name))
    outlines_hidden = max_outlines >= 0 and len(targets) > max_outlines
    return targets, outlines_hidden


def _build_targets_from_object(obj: bpy.types.Object, context: bpy.types.Context,
                               max_outlines: int) -> tuple[list[LinkDrawTarget], bool]:
    from . import get_object_overlay_lights_state

    targets = []
    for light_obj, state in get_object_overlay_lights_state(obj, context).items():
        if light_obj.hide_viewport or light_obj.hide_get():
            continue
        receiver = state[CollectionType.RECEIVER] is True
        blocker = state[CollectionType.BLOCKER] is True
        targets.append(LinkDrawTarget(light_obj, receiver, blocker, False, light_obj.name))
    outlines_hidden = max_outlines >= 0 and len(targets) > max_outlines
    return targets, outlines_hidden


def _build_all_light_groups(context: bpy.types.Context, active_light: bpy.types.Object | None,
                            max_outlines: int) -> tuple[list[LinkDrawGroup], bool]:
    from . import resolve_original_id

    active_light = resolve_original_id(active_light)
    groups = []
    total_targets = 0
    for light in context.scene.objects:
        if not _is_light_overlay_ready(light, context):
            continue
        if light.hide_viewport or light.hide_get():
            continue
        targets, _ = _build_targets_from_light(light, -1)
        if not targets:
            continue
        is_active = active_light is not None and light == active_light
        groups.append(LinkDrawGroup(light, targets, is_active))
        total_targets += len(targets)
    groups.sort(key=lambda group: (not group.is_active, group.subject.name.casefold() if group.subject else ""))
    outlines_hidden = max_outlines >= 0 and total_targets > max_outlines
    return groups, outlines_hidden


def _build_all_object_groups(context: bpy.types.Context, active_obj: bpy.types.Object | None,
                             max_outlines: int) -> tuple[list[LinkDrawGroup], bool]:
    from . import is_linkable_object, resolve_original_id

    active_obj = resolve_original_id(active_obj)
    groups = []
    total_targets = 0
    for obj in context.scene.objects:
        if not is_linkable_object(obj):
            continue
        if obj.hide_viewport or obj.hide_get():
            continue
        targets, _ = _build_targets_from_object(obj, context, -1)
        if not targets:
            continue
        is_active = active_obj is not None and obj == active_obj
        groups.append(LinkDrawGroup(obj, targets, is_active))
        total_targets += len(targets)
    groups.sort(key=lambda group: (not group.is_active, group.subject.name.casefold() if group.subject else ""))
    outlines_hidden = max_outlines >= 0 and total_targets > max_outlines
    return groups, outlines_hidden


def _draw_subject_outline(context: bpy.types.Context, subject: bpy.types.Object, alpha_scale: float = 1.0):
    if subject is None:
        return
    _center, corners = _world_bbox_from_object(subject)
    edge_coords = []
    for i0, i1 in _bbox_edges:
        edge_coords.append(corners[i0])
        edge_coords.append(corners[i1])
    color = _scale_color_alpha(COLOR_SUBJECT_OUTLINE, alpha_scale)
    _draw_lines_batch(context, edge_coords, color, width=1.8)


def refresh_overlay_cache(context: bpy.types.Context):
    from . import refresh_drop_poll_context

    wm_props = context.window_manager.light_helper_property
    pref = get_pref(context)
    overlay_mode = wm_props.linking_tool_overlay_mode
    subject_mode = wm_props.linking_tool_subject_mode
    max_outlines = pref.linking_tool_max_outlines

    _cache.overlay_mode = overlay_mode

    if overlay_mode == OVERLAY_MODE_OFF:
        _cache.subject_mode = subject_mode
        _cache.light = None
        _cache.object = None
        _cache.groups = []
        _cache.outlines_hidden = False
        _cache.invalid = False
        return

    groups: list[LinkDrawGroup] = []
    outlines_hidden = False

    if subject_mode == 'OBJECT':
        refresh_drop_poll_context(context)
        active_obj = wm_props.linking_tool_object
        if overlay_mode == OVERLAY_MODE_SELECTED:
            if active_obj is not None:
                targets, outlines_hidden = _build_targets_from_object(active_obj, context, max_outlines)
                groups = [LinkDrawGroup(active_obj, targets, True)]
        else:
            groups, outlines_hidden = _build_all_object_groups(context, active_obj, max_outlines)
        _cache.subject_mode = 'OBJECT'
        _cache.light = None
        _cache.object = active_obj
    else:
        active_light = wm_props.linking_tool_light
        if overlay_mode == OVERLAY_MODE_SELECTED:
            if active_light is not None:
                targets, outlines_hidden = _build_targets_from_light(active_light, max_outlines)
                groups = [LinkDrawGroup(active_light, targets, True)]
        else:
            groups, outlines_hidden = _build_all_light_groups(context, active_light, max_outlines)
        _cache.subject_mode = 'LIGHT'
        _cache.light = active_light
        _cache.object = None

    _cache.groups = groups
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


def _current_subject_key(context: bpy.types.Context) -> tuple:
    wm_props = context.window_manager.light_helper_property
    if wm_props.linking_tool_subject_mode == 'OBJECT':
        return _subject_cache_key('OBJECT', wm_props.linking_tool_object)
    return _subject_cache_key('LIGHT', wm_props.linking_tool_light)


def _current_cache_key(context: bpy.types.Context) -> tuple:
    wm_props = context.window_manager.light_helper_property
    subject_key = _current_subject_key(context)
    return (wm_props.linking_tool_overlay_mode, subject_key[0], subject_key[1])


def cache_needs_refresh(context: bpy.types.Context) -> bool:
    if _cache.invalid:
        return True
    current_key = _current_cache_key(context)
    cached_subject = _cache.object if _cache.subject_mode == 'OBJECT' else _cache.light
    cached_key = (_cache.overlay_mode, _cache.subject_mode, _subject_cache_key(_cache.subject_mode, cached_subject)[1])
    return current_key != cached_key


def _draw_overlay_3d():
    context = bpy.context
    wm_props = context.window_manager.light_helper_property
    if not wm_props.linking_tool_active or wm_props.linking_tool_overlay_mode == OVERLAY_MODE_OFF:
        return

    if cache_needs_refresh(context):
        refresh_overlay_cache(context)

    if not _cache.groups:
        return

    subject_mode = wm_props.linking_tool_subject_mode
    gpu.state.blend_set('ALPHA')
    gpu.state.depth_test_set('LESS_EQUAL')

    for group in _cache.groups:
        if group.subject is None:
            continue
        alpha_scale = 1.0 if group.is_active else INACTIVE_LINK_ALPHA_SCALE
        subject_pos = group.subject.matrix_world.translation.copy()

        if subject_mode == 'OBJECT' and group.is_active:
            _draw_subject_outline(context, group.subject, alpha_scale)

        if not group.targets:
            continue

        for target in group.targets:
            center, corners = _target_world_bbox(target)
            if center is None:
                continue
            linking_mode = _resolve_target_linking_mode(group, target, subject_mode, context)
            color = _channel_color(
                target.receiver, target.blocker,
                *_target_line_colors(linking_mode),
            )
            color = _scale_color_alpha(color, alpha_scale)
            _draw_lines_batch(context, [subject_pos, center], color, width=2.0)

        if not _cache.outlines_hidden:
            for target in group.targets:
                center, corners = _target_world_bbox(target)
                if corners is None:
                    continue
                linking_mode = _resolve_target_linking_mode(group, target, subject_mode, context)
                color = _channel_color(
                    target.receiver, target.blocker,
                    *_target_outline_colors(linking_mode),
                )
                color = _scale_color_alpha(color, alpha_scale)
                edge_coords = []
                for i0, i1 in _bbox_edges:
                    edge_coords.append(corners[i0])
                    edge_coords.append(corners[i1])
                _draw_lines_batch(context, edge_coords, color, width=1.5)

    gpu.state.depth_test_set('NONE')
    gpu.state.blend_set('NONE')


def _draw_overlay_hud():
    context = bpy.context
    wm_props = context.window_manager.light_helper_property
    if not wm_props.linking_tool_active or not wm_props.linking_tool_show_hud:
        return

    region = context.region
    if region is None:
        return

    subject_mode = wm_props.linking_tool_subject_mode
    lines = _hud_lines(context)
    font_id = 0
    margin_x = wm_props.linking_tool_hud_x
    margin_y = wm_props.linking_tool_hud_y
    blf.size(font_id, HUD_FONT_SIZE)

    # Draw top-to-bottom so list order matches on-screen reading order.
    top_y = margin_y + max(0, len(lines) - 1) * HUD_LINE_HEIGHT
    blf.enable(font_id, blf.SHADOW)
    blf.shadow(font_id, 3, 0.0, 0.0, 0.0, 0.7)
    for i, line in enumerate(lines):
        if not line:
            continue
        blf.position(font_id, margin_x, top_y - i * HUD_LINE_HEIGHT, 0)
        color = _hud_line_color(subject_mode, line)
        blf.color(font_id, *color)
        blf.draw(font_id, line)
    blf.disable(font_id, blf.SHADOW)


def _collect_overlay_object_names() -> set[str]:
    names = set()
    for group in _cache.groups:
        if group.subject is not None:
            names.add(group.subject.name)
        for target in group.targets:
            if target.is_collection:
                for obj in target.item.objects:
                    names.add(obj.name)
            elif isinstance(target.item, bpy.types.Object):
                names.add(target.item.name)
    return names


def _collect_overlay_collection_names() -> set[str]:
    names = set()
    for group in _cache.groups:
        if group.subject is not None and hasattr(group.subject, "light_linking"):
            linking = group.subject.light_linking
            if linking.receiver_collection is not None:
                names.add(linking.receiver_collection.name)
            if linking.blocker_collection is not None:
                names.add(linking.blocker_collection.name)
        for target in group.targets:
            if target.is_collection:
                names.add(target.item.name)
    return names


@bpy.app.handlers.persistent
def _depsgraph_update_post(_scene, depsgraph: bpy.types.Depsgraph):
    try:
        context = bpy.context
        if context is None or context.window_manager is None:
            return
        wm_props = context.window_manager.light_helper_property
        if not wm_props.linking_tool_active:
            return
        if wm_props.linking_tool_overlay_mode == OVERLAY_MODE_OFF:
            return

        relevant_names = _collect_overlay_object_names()
        collection_names = _collect_overlay_collection_names()
        needs_cache_refresh = False
        needs_redraw = False

        for update in depsgraph.updates:
            id_ref = update.id
            if isinstance(id_ref, bpy.types.Collection):
                if id_ref.is_evaluated:
                    id_ref = id_ref.original
                    if id_ref is None:
                        continue
                if id_ref.name in collection_names:
                    needs_cache_refresh = True
                    break
                continue

            if not isinstance(id_ref, bpy.types.Object):
                continue
            if id_ref.is_evaluated:
                id_ref = id_ref.original
                if id_ref is None:
                    continue
            if id_ref.name not in relevant_names:
                continue
            if update.is_updated_transform or update.is_updated_geometry:
                needs_redraw = True

        if needs_cache_refresh:
            invalidate_overlay_cache()
            refresh_overlay_cache(context)
            tag_view3d_redraw(context)
        elif needs_redraw:
            tag_view3d_redraw(context)
    except (AttributeError, ReferenceError, TypeError):
        pass


_undo_handler_registered = False
_depsgraph_handler_registered = False


@bpy.app.handlers.persistent
def _undo_redo_post(_dummy):
    try:
        context = bpy.context
        if context is None or context.window_manager is None:
            return
        if not context.window_manager.light_helper_property.linking_tool_active:
            return
        invalidate_overlay_cache()
        refresh_overlay_cache(context)
        tag_view3d_redraw(context)
    except (AttributeError, ReferenceError, TypeError):
        pass


def tag_view3d_redraw(context: bpy.types.Context | None = None):
    ctx = context if context is not None else bpy.context
    if ctx is None:
        return
    for window in ctx.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def register_draw_handlers():
    global _draw_handler_3d, _draw_handler_hud, _depsgraph_handler_registered, _undo_handler_registered
    if _draw_handler_3d is None:
        _draw_handler_3d = bpy.types.SpaceView3D.draw_handler_add(
            _draw_overlay_3d, (), 'WINDOW', 'POST_VIEW',
        )
    if _draw_handler_hud is None:
        _draw_handler_hud = bpy.types.SpaceView3D.draw_handler_add(
            _draw_overlay_hud, (), 'WINDOW', 'POST_PIXEL',
        )
    if not _depsgraph_handler_registered:
        if _depsgraph_update_post not in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.append(_depsgraph_update_post)
        _depsgraph_handler_registered = True
    if not _undo_handler_registered:
        if _undo_redo_post not in bpy.app.handlers.undo_post:
            bpy.app.handlers.undo_post.append(_undo_redo_post)
        if _undo_redo_post not in bpy.app.handlers.redo_post:
            bpy.app.handlers.redo_post.append(_undo_redo_post)
        _undo_handler_registered = True


def unregister_draw_handlers():
    global _draw_handler_3d, _draw_handler_hud, _depsgraph_handler_registered, _undo_handler_registered
    if _draw_handler_3d is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handler_3d, 'WINDOW')
        _draw_handler_3d = None
    if _draw_handler_hud is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handler_hud, 'WINDOW')
        _draw_handler_hud = None
    if _depsgraph_handler_registered:
        if _depsgraph_update_post in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.remove(_depsgraph_update_post)
        _depsgraph_handler_registered = False
    if _undo_handler_registered:
        if _undo_redo_post in bpy.app.handlers.undo_post:
            bpy.app.handlers.undo_post.remove(_undo_redo_post)
        if _undo_redo_post in bpy.app.handlers.redo_post:
            bpy.app.handlers.redo_post.remove(_undo_redo_post)
        _undo_handler_registered = False


def view3d_window_at_mouse(context: bpy.types.Context, event):
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


def _region_coord_from_event(event, region) -> tuple[float, float]:
    return float(event.mouse_x - region.x), float(event.mouse_y - region.y)


def _depth_along_view(origin: Vector, direction: Vector, world_co: Vector) -> float:
    return (world_co - origin).dot(direction)


def _pick_object_at_coord(context: bpy.types.Context, area, region, coord) -> bpy.types.Object | None:
    from . import resolve_original_id

    space = area.spaces.active
    region_data = getattr(space, "region_3d", None)
    if region_data is None:
        return None

    override_kwargs = {
        "window": context.window,
        "screen": context.screen,
        "area": area,
        "region": region,
        "space_data": space,
        "region_data": region_data,
    }

    with context.temp_override(**override_kwargs):
        rv3d = context.region_data
        if rv3d is None:
            return None

        mouse = Vector(coord)
        origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
        direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
        depsgraph = context.evaluated_depsgraph_get()

        candidates: list[tuple[float, bpy.types.Object]] = []

        hit, loc, _normal, _index, hit_obj, _matrix = context.scene.ray_cast(
            depsgraph, origin, direction,
        )
        if hit and hit_obj is not None:
            depth = _depth_along_view(origin, direction, loc)
            if depth > 0:
                candidates.append((depth, resolve_original_id(hit_obj)))

        pick_radius = 22.0
        for obj in context.view_layer.objects:
            if obj.hide_viewport or obj.hide_get() or not obj.visible_get():
                continue
            if obj.type in {'MESH', 'CURVE', 'SURFACE', 'META', 'FONT'}:
                continue

            screen_co = view3d_utils.location_3d_to_region_2d(region, rv3d, obj.matrix_world.translation)
            if screen_co is None:
                continue
            if (Vector(screen_co) - mouse).length > pick_radius:
                continue

            depth = _depth_along_view(origin, direction, obj.matrix_world.translation)
            if depth > 0:
                candidates.append((depth, resolve_original_id(obj)))

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]


def pick_object_under_mouse(context: bpy.types.Context, event) -> bpy.types.Object | None:
    """Pick the object under the cursor without changing the current selection."""
    area, region = view3d_window_at_mouse(context, event)
    if area is None or region is None:
        return None
    coord = _region_coord_from_event(event, region)
    return _pick_object_at_coord(context, area, region, coord)
