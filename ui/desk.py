"""GPU renderer and per-area runtime for the full-view Lighting Desk."""

import json

import blf
import bpy
import gpu
from bpy.app.translations import pgettext_iface as p_
from gpu_extras.batch import batch_for_shader

from ..utils.desk_layout import (
    DESK_TABS,
    DeskSnapshot,
    HitRegion,
    LinkCellSnapshot,
    LinkRowSnapshot,
    LinkTargetSnapshot,
    MatrixSelection,
    Rect,
    compute_desk_bounds,
    filter_indices,
    hit_test,
    next_layout_token,
    visible_slice,
)


_ACTIVE_BY_OWNER = {}
_DRAW_HANDLE = None
_SHADER = None

_BACKGROUND = (0.035, 0.04, 0.05, 0.97)
_SURFACE = (0.085, 0.095, 0.115, 0.98)
_SURFACE_ALT = (0.12, 0.135, 0.16, 0.98)
_SELECTION = (0.18, 0.38, 0.66, 0.72)
_TEXT = (0.88, 0.91, 0.96, 1.0)
_MUTED_TEXT = (0.55, 0.58, 0.64, 1.0)
_ACCENT = (0.18, 0.58, 0.92, 1.0)
_STATE_COLORS = {
    "OFF": (0.15, 0.16, 0.18, 1.0),
    "INCLUDE": (0.16, 0.63, 0.30, 1.0),
    "EXCLUDE": (0.78, 0.20, 0.22, 1.0),
    "MIXED": (0.72, 0.52, 0.12, 1.0),
}
_SHADOW_STATE_COLORS = {
    "OFF": (0.15, 0.16, 0.18, 1.0),
    "INCLUDE": (0.17, 0.38, 0.82, 1.0),
    "EXCLUDE": (0.74, 0.20, 0.69, 1.0),
    "MIXED": (0.72, 0.52, 0.12, 1.0),
}


def _pointer(value) -> int:
    try:
        return int(value.as_pointer())
    except (AttributeError, ReferenceError, TypeError):
        return 0


def owner_key(window, area) -> tuple[int, int]:
    return _pointer(window), _pointer(area)


def tag_owner_window(area) -> None:
    try:
        regions = tuple(area.regions)
    except (AttributeError, ReferenceError, TypeError):
        return
    for region in regions:
        if region.type == 'WINDOW':
            region.tag_redraw()
            return


def _normalize_state(value) -> str:
    if isinstance(value, tuple):
        value = value[0] if value else "OFF"
    value = getattr(value, "value", value)
    state = str(value).upper()
    if "." in state:
        state = state.rsplit(".", 1)[-1]
    return state if state in {"OFF", "INCLUDE", "EXCLUDE", "MIXED"} else "OFF"


def _direct_channel_state(source, item, channel) -> str:
    try:
        from ..utils import get_item_channel_state

        return _normalize_state(get_item_channel_state(source, item, channel))
    except (ImportError, AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
        try:
            from ..utils import get_linking_mode, is_item_in_channel

            if is_item_in_channel(source, item, channel):
                return _normalize_state(get_linking_mode(source))
        except (ImportError, AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
            pass
    return "OFF"


def _effective_channel_state(source, item, channel) -> tuple[str, bool]:
    try:
        from ..utils import get_effective_item_channel_state

        effective = get_effective_item_channel_state(source, item, channel)
        if bool(getattr(effective, "mixed", False)):
            return "MIXED", bool(getattr(effective, "inherited_from", ()))
        state = _normalize_state(getattr(effective, "state", effective))
        inherited = bool(getattr(effective, "inherited_from", ())) and not bool(
            getattr(effective, "direct", False)
        )
        return state, inherited
    except (ImportError, AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
        pass
    direct = _direct_channel_state(source, item, channel)
    if direct != "OFF" or not isinstance(item, bpy.types.Object):
        return direct, False
    states = {
        _direct_channel_state(source, collection, channel)
        for collection in tuple(getattr(item, "users_collection", ()))
    }
    states.discard("OFF")
    if not states:
        return "OFF", False
    if len(states) > 1:
        return "MIXED", True
    return states.pop(), True


def _scene_collections(scene) -> tuple:
    result = []

    def visit(collection):
        for child in tuple(collection.children):
            result.append(child)
            visit(child)

    visit(scene.collection)
    return tuple(result)


def capture_desk_snapshot(scene, revision: int = 0) -> DeskSnapshot:
    """Capture all RNA used by draw into immutable plain-data rows."""
    from ..ops.light_mixer import is_false_color_enabled, mixer_row_snapshot
    from ..utils import CollectionType, is_linkable_object

    sources = tuple(
        obj for obj in scene.objects
        if obj.type == 'LIGHT' and obj.data is not None
    )
    target_objects = tuple(
        obj for obj in scene.objects
        if obj not in sources
        and is_linkable_object(obj)
        and not obj.get("light_helper_safe")
        and obj.get("light_helper_world_dome_role") is None
        and obj.get("light_helper_studio_role") != "TRACK_TARGET"
    )
    targets = tuple(LinkTargetSnapshot(obj.name, "OBJECT") for obj in target_objects)
    collections = _scene_collections(scene)
    targets += tuple(LinkTargetSnapshot(collection.name, "COLLECTION") for collection in collections)
    target_rna = target_objects + collections

    rows = []
    mixer_rows = []
    for source in sources:
        cells = []
        link_count = 0
        for target in target_rna:
            illumination, illumination_inherited = _effective_channel_state(
                source, target, CollectionType.RECEIVER,
            )
            shadow, shadow_inherited = _effective_channel_state(
                source, target, CollectionType.BLOCKER,
            )
            if illumination != "OFF" or shadow != "OFF":
                link_count += 1
            cells.append(LinkCellSnapshot(
                illumination,
                shadow,
                illumination_inherited,
                shadow_inherited,
            ))
        rows.append(LinkRowSnapshot(source.name, source.data.type, tuple(cells)))
        mixer_rows.append(mixer_row_snapshot(source, link_count))
    profile_index = int(getattr(scene, "light_helper_profile_index", -1))
    profiles = tuple(
        (item.name, index == profile_index)
        for index, item in enumerate(getattr(scene, "light_helper_profiles", ()))
    )
    light_groups = tuple(
        (
            item.name,
            float(item.ev),
            tuple(float(value) for value in item.tint[:3]),
        )
        for item in getattr(scene, "light_helper_light_group_settings", ())
        if item.name
    )
    try:
        from ..utils.studio import is_studio_object, studio_kind
        studio_items = tuple(
            (obj.name, studio_kind(obj) or "STUDIO")
            for obj in scene.objects
            if is_studio_object(obj)
        )
    except (ImportError, AttributeError, ReferenceError, RuntimeError, TypeError):
        studio_items = ()
    return DeskSnapshot(
        int(revision),
        tuple(rows),
        targets,
        tuple(mixer_rows),
        is_false_color_enabled(scene),
        str(scene.render.engine),
        profiles,
        light_groups,
        studio_items,
    )


def _draw_callback() -> None:
    context = bpy.context
    session = _ACTIVE_BY_OWNER.get(owner_key(context.window, context.area))
    if session is None or context.region is None or context.region.type != 'WINDOW':
        return
    if _pointer(context.region) != session.region_key:
        return
    session.draw(context.region)


def _ensure_draw_handler() -> bool:
    global _DRAW_HANDLE
    if _DRAW_HANDLE is not None:
        return True
    try:
        _DRAW_HANDLE = bpy.types.SpaceView3D.draw_handler_add(
            _draw_callback, (), 'WINDOW', 'POST_PIXEL',
        )
    except (AttributeError, RuntimeError, TypeError):
        _DRAW_HANDLE = None
    return _DRAW_HANDLE is not None


def _remove_draw_handler_if_unused() -> None:
    global _DRAW_HANDLE, _SHADER
    if _ACTIVE_BY_OWNER or _DRAW_HANDLE is None:
        return
    handle = _DRAW_HANDLE
    _DRAW_HANDLE = None
    try:
        bpy.types.SpaceView3D.draw_handler_remove(handle, 'WINDOW')
    except (AttributeError, RuntimeError, TypeError):
        pass
    _SHADER = None


def _rect_vertices(rect: Rect):
    x0, y0, x1, y1 = rect.x, rect.y, rect.right, rect.top
    return ((x0, y0), (x1, y0), (x1, y1), (x0, y0), (x1, y1), (x0, y1))


def _draw_rect_batch(rectangles) -> None:
    global _SHADER
    if not rectangles:
        return
    if _SHADER is None:
        _SHADER = gpu.shader.from_builtin('SMOOTH_COLOR')
    positions = []
    colors = []
    for rect, color in rectangles:
        vertices = _rect_vertices(rect)
        positions.extend(vertices)
        colors.extend((color,) * len(vertices))
    batch = batch_for_shader(_SHADER, 'TRIS', {"pos": positions, "color": colors})
    _SHADER.bind()
    batch.draw(_SHADER)


def _draw_text_batch(text_items) -> None:
    font_id = 0
    for text, x, y, size, color in text_items:
        blf.position(font_id, x, y, 0)
        blf.size(font_id, size)
        blf.color(font_id, *color)
        blf.draw(font_id, str(text))


def _state_cycle(state: str) -> str:
    return {"OFF": "INCLUDE", "INCLUDE": "EXCLUDE", "EXCLUDE": "OFF"}.get(state, "OFF")


class DeskSession:
    """Transient, area-scoped state.  No member is stored in Blender RNA."""

    def __init__(self, context, operator):
        self.operator = operator
        self.window_manager = context.window_manager
        self.window = context.window
        self.screen = context.screen
        self.area = context.area
        self.region = context.region
        self.scene = context.scene
        self.window_key = _pointer(self.window)
        self.screen_key = _pointer(self.screen)
        self.area_key = _pointer(self.area)
        self.region_key = _pointer(self.region)
        self.key = (self.window_key, self.area_key)
        self.cleaned = False
        self.close_requested = False
        self.expanded = False
        wm_props = context.window_manager.light_helper_property
        self.tab = getattr(wm_props, "lighting_desk_tab", "LINK")
        try:
            from ..utils import get_pref

            preference = get_pref(context)
            configured_columns = getattr(preference, "lighting_desk_mixer_columns", "NORMAL")
            configured_sync = bool(getattr(preference, "lighting_desk_sync_selection", True))
        except (AttributeError, KeyError, RuntimeError, TypeError):
            configured_columns = "NORMAL"
            configured_sync = True
        self.mixer_columns = configured_columns if configured_columns in {"MINIMAL", "NORMAL", "ADVANCED"} else "NORMAL"
        self.kelvin_preset_index = 3
        self.sync_selection = configured_sync
        self.show_help = False
        self.search_focus = ""
        self.light_search = ""
        self.light_filter = "ALL"
        self.target_search = ""
        self.target_filter = "ALL"
        self.row_scroll = 0.0
        self.column_scroll = 0.0
        self.layout_token = 0
        self.hit_regions = ()
        self.hover = None
        self.selection = MatrixSelection()
        self.revision = 1
        self.snapshot = capture_desk_snapshot(self.scene, self.revision)
        selected_names = {
            obj.name for obj in tuple(getattr(context, "selected_objects", ()))
            if obj.type == 'LIGHT'
        }
        selected_indexes = {
            index for index, row in enumerate(self.snapshot.rows)
            if row.source_name in selected_names
        }
        self.selection.rows.values.update(selected_indexes)
        if selected_indexes:
            self.selection.rows.anchor = min(selected_indexes)

    def acquire(self) -> bool:
        current = _ACTIVE_BY_OWNER.get(self.key)
        if current is not None:
            return False
        _ACTIVE_BY_OWNER[self.key] = self
        if _ensure_draw_handler():
            wm_props = self.window_manager.light_helper_property
            wm_props.lighting_desk_active = True
            wm_props.lighting_desk_tab = self.tab
            wm_props.lighting_desk_sync_selection = self.sync_selection
            tag_owner_window(self.area)
            return True
        if _ACTIVE_BY_OWNER.get(self.key) is self:
            _ACTIVE_BY_OWNER.pop(self.key, None)
        try:
            self.window_manager.light_helper_property.lighting_desk_active = bool(
                _ACTIVE_BY_OWNER
            )
        except (AttributeError, ReferenceError, RuntimeError, TypeError):
            pass
        return False

    def refresh_snapshot(self) -> None:
        if self.cleaned:
            return
        self.revision += 1
        self.snapshot = capture_desk_snapshot(self.scene, self.revision)
        tag_owner_window(self.area)

    def cleanup(self) -> None:
        if self.cleaned:
            return
        self.cleaned = True
        self.hit_regions = ()
        self.hover = None
        if _ACTIVE_BY_OWNER.get(self.key) is self:
            _ACTIVE_BY_OWNER.pop(self.key, None)
        try:
            tag_owner_window(self.area)
        finally:
            _remove_draw_handler_if_unused()

    def is_owner_alive(self) -> bool:
        if self.cleaned:
            return False
        try:
            live_screen = self.window.screen
            if _pointer(live_screen) != self.screen_key:
                return False
            live_area = next(
                (
                    area
                    for area in live_screen.areas
                    if _pointer(area) == self.area_key
                ),
                None,
            )
            if live_area is None:
                return False
            return any(
                _pointer(region) == self.region_key
                for region in live_area.regions
            )
        except (AttributeError, ReferenceError, TypeError):
            return False

    def _add_hit(self, hits, rect, action, *payload) -> None:
        hits.append(HitRegion(self.layout_token, rect, action, tuple(payload)))

    def desk_bounds(self, region=None) -> Rect:
        region = region or self.region
        try:
            width = float(region.width)
            height = float(region.height)
        except (AttributeError, ReferenceError, TypeError, ValueError):
            return Rect(0.0, 0.0, 0.0, 0.0)
        return compute_desk_bounds(width, height, expanded=self.expanded)

    def owns_region(self, region) -> bool:
        return _pointer(region) == self.region_key

    def event_is_inside(self, region, event) -> bool:
        try:
            return self.desk_bounds(region).contains(
                float(event.mouse_region_x),
                float(event.mouse_region_y),
            )
        except (AttributeError, TypeError, ValueError):
            return False

    def clear_pointer_state(self, *, clear_search=False) -> None:
        changed = self.hover is not None
        self.hover = None
        if clear_search and self.search_focus:
            self.search_focus = ""
            changed = True
        if changed:
            tag_owner_window(self.area)

    @staticmethod
    def _label(texts, text, rect, *, size=12, color=_TEXT, inset=6.0) -> None:
        texts.append((p_(str(text)), rect.x + inset, rect.y + max(2.0, (rect.height - size) * 0.48), size, color))

    def _draw_header(self, width, height, rectangles, texts, hits):
        header = Rect(0, height - 44, width, 44)
        rectangles.append((header, (0.055, 0.065, 0.085, 1.0)))
        self._label(texts, "LIGHTING DESK", Rect(10, header.y + 6, 180, 32), size=17)
        false_rect = Rect(max(210, width - 382), header.y + 8, 104, 28)
        rectangles.append((false_rect, _ACCENT if self.snapshot.false_color_enabled else _SURFACE_ALT))
        self._label(texts, "False Color", false_rect, size=12)
        self._add_hit(hits, false_rect, "FALSE_COLOR")
        expand_rect = Rect(width - 272, header.y + 8, 82, 28)
        rectangles.append((expand_rect, _SURFACE_ALT))
        self._label(texts, "Dock" if self.expanded else "Expand", expand_rect, size=11)
        self._add_hit(hits, expand_rect, "EXPAND")
        help_rect = Rect(width - 184, header.y + 8, 70, 28)
        rectangles.append((help_rect, _SURFACE_ALT))
        self._label(texts, "Help", help_rect, size=12)
        self._add_hit(hits, help_rect, "HELP")
        close_rect = Rect(width - 108, header.y + 8, 96, 28)
        rectangles.append((close_rect, (0.47, 0.14, 0.16, 1.0)))
        self._label(texts, "Close  Esc", close_rect, size=12)
        self._add_hit(hits, close_rect, "CLOSE")

    def _draw_tabs(self, width, height, rectangles, texts, hits):
        y = height - 78
        tab_width = min(150.0, max(90.0, (width - 24.0) / len(DESK_TABS)))
        for index, tab in enumerate(DESK_TABS):
            rect = Rect(12 + index * tab_width, y, tab_width - 4, 28)
            rectangles.append((rect, _ACCENT if tab == self.tab else _SURFACE))
            self._label(texts, tab.title(), rect, size=13)
            self._add_hit(hits, rect, "TAB", tab)

    def _draw_link(self, width, height, rectangles, texts, hits):
        toolbar_y = height - 112
        row_search = Rect(12, toolbar_y, 120, 26)
        light_filter = Rect(138, toolbar_y, 84, 26)
        target_search = Rect(228, toolbar_y, 130, 26)
        type_filter = Rect(364, toolbar_y, 102, 26)
        for rect in (row_search, light_filter, target_search, type_filter):
            rectangles.append((rect, _SURFACE_ALT))
        self._label(texts, "Lights: " + (self.light_search or "Search"), row_search, size=11)
        self._label(texts, self.light_filter.title(), light_filter, size=10)
        self._label(texts, "Targets: " + (self.target_search or "Search"), target_search, size=11)
        self._label(texts, self.target_filter.title(), type_filter, size=11)
        self._add_hit(hits, row_search, "SEARCH", "LIGHT")
        self._add_hit(hits, light_filter, "LIGHT_FILTER")
        self._add_hit(hits, target_search, "SEARCH", "TARGET")
        self._add_hit(hits, type_filter, "TARGET_FILTER")

        bulk_x = 478.0
        for channel, label in (("RECEIVER", "Light"), ("BLOCKER", "Shadow")):
            self._label(texts, label, Rect(bulk_x, toolbar_y, 54, 26), size=10)
            bulk_x += 52
            for state, short in (("OFF", "Off"), ("INCLUDE", "+"), ("EXCLUDE", "−")):
                rect = Rect(bulk_x, toolbar_y, 38, 26)
                color_map = _STATE_COLORS if channel == "RECEIVER" else _SHADOW_STATE_COLORS
                rectangles.append((rect, color_map[state]))
                self._label(texts, short, rect, size=11, inset=12)
                self._add_hit(hits, rect, "BULK", channel, state)
                bulk_x += 42
            bulk_x += 10

        content = Rect(12, 16, max(1, width - 24), max(1, toolbar_y - 24))
        row_header_width = 184.0
        column_header_height = 34.0
        row_height = 27.0
        column_width = 86.0
        rectangles.append((content, (0.045, 0.05, 0.062, 1.0)))

        filtered_rows = filter_indices(
            tuple((row.source_name, row.source_type) for row in self.snapshot.rows),
            self.light_search,
            self.light_filter,
        )
        filtered_targets = filter_indices(self.snapshot.targets, self.target_search, self.target_filter)
        row_view = visible_slice(len(filtered_rows), self.row_scroll, content.height - column_header_height, row_height)
        column_view = visible_slice(
            len(filtered_targets), self.column_scroll, content.width - row_header_width, column_width,
        )

        corner = Rect(content.x, content.top - column_header_height, row_header_width, column_header_height)
        rectangles.append((corner, _SURFACE_ALT))
        self._label(texts, f"{len(filtered_rows)} lights × {len(filtered_targets)} targets", corner, size=10)

        for virtual_column in range(column_view.start, column_view.stop):
            target_index = filtered_targets[virtual_column]
            target = self.snapshot.targets[target_index]
            x = content.x + row_header_width + virtual_column * column_width - column_view.offset
            rect = Rect(x, content.top - column_header_height, column_width - 2, column_header_height)
            if rect.right <= content.x + row_header_width or rect.x >= content.right:
                continue
            selected = target_index in self.selection.columns.values
            rectangles.append((rect, _SELECTION if selected else _SURFACE_ALT))
            prefix = "C: " if target.kind == "COLLECTION" else ""
            self._label(texts, prefix + target.name[:11], rect, size=10, inset=4)
            self._add_hit(hits, rect, "SELECT_COLUMN", target_index)

        for virtual_row in range(row_view.start, row_view.stop):
            row_index = filtered_rows[virtual_row]
            row = self.snapshot.rows[row_index]
            y = content.top - column_header_height - (virtual_row + 1) * row_height + row_view.offset
            if y + row_height <= content.y or y >= content.top - column_header_height:
                continue
            header_rect = Rect(content.x, y, row_header_width - 2, row_height - 2)
            selected = row_index in self.selection.rows.values
            rectangles.append((header_rect, _SELECTION if selected else _SURFACE))
            self._label(texts, f"{row.source_name}  [{row.source_type}]", header_rect, size=10)
            self._add_hit(hits, header_rect, "SELECT_ROW", row_index)

            for virtual_column in range(column_view.start, column_view.stop):
                target_index = filtered_targets[virtual_column]
                if target_index >= len(row.cells):
                    continue
                cell = row.cells[target_index]
                x = content.x + row_header_width + virtual_column * column_width - column_view.offset
                cell_rect = Rect(x, y, column_width - 2, row_height - 2)
                if cell_rect.right <= content.x + row_header_width or cell_rect.x >= content.right:
                    continue
                half = cell_rect.width * 0.5
                light_rect = Rect(cell_rect.x, cell_rect.y, half - 1, cell_rect.height)
                shadow_rect = Rect(cell_rect.x + half, cell_rect.y, half - 1, cell_rect.height)
                rectangles.append((light_rect, _STATE_COLORS.get(cell.illumination, _STATE_COLORS["OFF"])))
                rectangles.append((shadow_rect, _SHADOW_STATE_COLORS.get(cell.shadow, _SHADOW_STATE_COLORS["OFF"])))
                light_mark = "↗" if cell.illumination_inherited else cell.illumination[:1]
                shadow_mark = "↗" if cell.shadow_inherited else cell.shadow[:1]
                self._label(texts, light_mark or "·", light_rect, size=9, inset=4)
                self._label(texts, shadow_mark or "·", shadow_rect, size=9, inset=4)
                self._add_hit(hits, light_rect, "CELL", row_index, target_index, "RECEIVER", cell.illumination)
                self._add_hit(hits, shadow_rect, "CELL", row_index, target_index, "BLOCKER", cell.shadow)

        if not filtered_rows or not filtered_targets:
            message = "No lights match the filters" if not filtered_rows else "No targets match the filters"
            self._label(texts, message, Rect(content.x + 190, content.y + 40, 300, 30), color=_MUTED_TEXT)

    def _draw_mix(self, width, height, rectangles, texts, hits):
        from ..ops.light_mixer import KELVIN_PRESETS, get_mixer_columns

        toolbar_y = height - 112
        mode_rect = Rect(12, toolbar_y, 126, 26)
        sync_rect = Rect(144, toolbar_y, 116, 26)
        copy_rect = Rect(266, toolbar_y, 74, 26)
        paste_rect = Rect(346, toolbar_y, 78, 26)
        full_rect = Rect(430, toolbar_y, 94, 26)
        kelvin_rect = Rect(530, toolbar_y, 100, 26)
        for rect in (mode_rect, sync_rect, copy_rect, paste_rect, full_rect, kelvin_rect):
            rectangles.append((rect, _SURFACE_ALT))
        self._label(texts, self.mixer_columns.title(), mode_rect, size=11)
        self._label(texts, "Sync Selection" if self.sync_selection else "Desk Selection", sync_rect, size=10)
        self._label(texts, "Copy", copy_rect, size=11)
        self._label(texts, "Paste", paste_rect, size=11)
        self._label(texts, "Paste Full", full_rect, size=11)
        kelvin = KELVIN_PRESETS[self.kelvin_preset_index][2]
        self._label(texts, f"Kelvin {kelvin:.0f}", kelvin_rect, size=10)
        self._add_hit(hits, mode_rect, "MIX_COLUMNS")
        self._add_hit(hits, sync_rect, "SYNC_SELECTION")
        self._add_hit(hits, copy_rect, "MIX_COPY")
        self._add_hit(hits, paste_rect, "MIX_PASTE", False)
        self._add_hit(hits, full_rect, "MIX_PASTE", True)
        self._add_hit(hits, kelvin_rect, "MIX_KELVIN")

        content = Rect(12, 16, width - 24, toolbar_y - 24)
        rectangles.append((content, (0.045, 0.05, 0.062, 1.0)))
        columns = get_mixer_columns(self.mixer_columns)
        widths = {"name": 170.0, "type": 66.0, "color": 84.0, "visibility": 105.0, "spot": 90.0}
        column_widths = tuple(widths.get(column, 76.0) for column in columns)
        row_height = 28.0
        header_height = 30.0
        row_view = visible_slice(len(self.snapshot.mixer_rows), self.row_scroll, content.height - header_height, row_height)
        x = content.x - self.column_scroll
        for column, column_width in zip(columns, column_widths):
            rect = Rect(x, content.top - header_height, column_width - 2, header_height)
            if rect.right > content.x and rect.x < content.right:
                rectangles.append((rect, _SURFACE_ALT))
                self._label(texts, column.replace("_", " ").title(), rect, size=9, inset=4)
            x += column_width
        for virtual_row in range(row_view.start, row_view.stop):
            row = self.snapshot.mixer_rows[virtual_row]
            y = content.top - header_height - (virtual_row + 1) * row_height + row_view.offset
            if y + row_height <= content.y or y >= content.top - header_height:
                continue
            x = content.x - self.column_scroll
            for column, column_width in zip(columns, column_widths):
                rect = Rect(x, y, column_width - 2, row_height - 2)
                if rect.right > content.x and rect.x < content.right:
                    base = _SELECTION if virtual_row in self.selection.rows.values else _SURFACE
                    if column == "mute" and row.value("mute"):
                        base = (0.55, 0.18, 0.16, 1.0)
                    rectangles.append((rect, base))
                    value = row.name if column == "name" else row.light_type if column == "type" else row.value(column, "—")
                    if isinstance(value, float):
                        label = f"{value:.3g}"
                    elif isinstance(value, tuple):
                        label = " / ".join(f"{item:.2g}" if isinstance(item, float) else str(item) for item in value if item is not None)
                    elif isinstance(value, bool):
                        label = "On" if value else "Off"
                    else:
                        label = str(value)
                    self._label(texts, label[:22], rect, size=9, inset=4)
                    action = {
                        "mute": "MIX_MUTE",
                        "solo": "MIX_SOLO",
                        "render": "MIX_RENDER",
                        "energy": "MIX_ENERGY",
                        "color": "MIX_COLOR",
                        "size": "MIX_SCALAR",
                        "spot": "MIX_SCALAR",
                        "diffuse": "MIX_SCALAR",
                        "specular": "MIX_SCALAR",
                        "transmission": "MIX_SCALAR",
                        "volume": "MIX_SCALAR",
                        "shadow": "MIX_SHADOW",
                        "normalize": "MIX_NORMALIZE",
                        "visibility": "MIX_VISIBILITY",
                    }.get(column, "MIX_SELECT")
                    self._add_hit(hits, rect, action, virtual_row, row.name, column)
                x += column_width

    def _draw_looks(self, width, height, rectangles, texts, hits):
        top = height - 108
        content_height = max(150.0, top - 28.0)
        gap = 12.0
        left_width = max(300.0, (width - 60.0) * 0.5)
        profiles_panel = Rect(18, 18, left_width, content_height)
        groups_panel = Rect(profiles_panel.right + gap, 18, max(260, width - profiles_panel.right - 30), content_height)
        rectangles.extend(((profiles_panel, _SURFACE), (groups_panel, _SURFACE)))

        self._label(texts, "Lighting Profiles", Rect(profiles_panel.x + 10, profiles_panel.top - 38, profiles_panel.width - 20, 28), size=16)
        y = profiles_panel.top - 72
        if not self.snapshot.profiles:
            self._label(texts, "No stored profiles", Rect(profiles_panel.x + 12, y, profiles_panel.width - 24, 24), color=_MUTED_TEXT)
        for index, (name, active) in enumerate(self.snapshot.profiles[:10]):
            rect = Rect(profiles_panel.x + 10, y - index * 28, profiles_panel.width - 20, 24)
            rectangles.append((rect, _SELECTION if active else _SURFACE_ALT))
            self._label(texts, name[:48], rect, size=10)
            self._add_hit(hits, rect, "PROFILE_SELECT", index)
        button_y = profiles_panel.y + 12
        x = profiles_panel.x + 10
        for action, label, button_width in (
                ("PROFILE_CAPTURE", "Capture", 74),
                ("PROFILE_APPLY", "Apply", 62),
                ("PROFILE_CREATE", "Create Missing", 104),
                ("PROFILE_REMOVE", "Remove", 72)):
            rect = Rect(x, button_y, button_width, 28)
            rectangles.append((rect, _SURFACE_ALT))
            self._label(texts, label, rect, size=10)
            self._add_hit(hits, rect, action)
            x += button_width + 6
        x = profiles_panel.x + 10
        for action, label in (("PROFILE_IMPORT", "Import"), ("PROFILE_EXPORT", "Export")):
            rect = Rect(x, button_y + 34, 82, 26)
            rectangles.append((rect, _SURFACE_ALT))
            self._label(texts, label, rect, size=10)
            self._add_hit(hits, rect, action)
            x += 88

        self._label(texts, "Cycles Light Groups", Rect(groups_panel.x + 10, groups_panel.top - 38, groups_panel.width - 20, 28), size=16)
        false_rect = Rect(groups_panel.x + 10, groups_panel.top - 72, 124, 26)
        rectangles.append((false_rect, _ACCENT if self.snapshot.false_color_enabled else _SURFACE_ALT))
        self._label(texts, "False Color", false_rect, size=10)
        self._add_hit(hits, false_rect, "FALSE_COLOR")
        for index, (name, ev, tint) in enumerate(self.snapshot.light_groups[:9]):
            row = Rect(groups_panel.x + 10, groups_panel.top - 104 - index * 30, groups_panel.width - 20, 26)
            rectangles.append((row, _SURFACE_ALT))
            self._label(texts, f"{name[:22]}  {ev:+.2f} EV", row, size=10)
            minus = Rect(row.right - 126, row.y + 2, 36, 22)
            plus = Rect(row.right - 86, row.y + 2, 36, 22)
            assign = Rect(row.right - 46, row.y + 2, 42, 22)
            for rect, label in ((minus, "-.5"), (plus, "+.5"), (assign, "Set")):
                rectangles.append((rect, _SURFACE))
                self._label(texts, label, rect, size=9, inset=5)
            self._add_hit(hits, minus, "GROUP_EV", name, -0.5)
            self._add_hit(hits, plus, "GROUP_EV", name, 0.5)
            self._add_hit(hits, assign, "GROUP_ASSIGN", name)
        x = groups_panel.x + 10
        for action, label, button_width in (
                ("GROUP_SYNC", "Sync", 62),
                ("GROUP_BUILD", "Build Mixer", 92),
                ("GROUP_REMOVE", "Remove Mixer", 104)):
            rect = Rect(x, groups_panel.y + 12, button_width, 28)
            rectangles.append((rect, _SURFACE_ALT))
            self._label(texts, label, rect, size=10)
            self._add_hit(hits, rect, action)
            x += button_width + 6

    def _draw_studio(self, width, height, rectangles, texts, hits):
        panel = Rect(24, 24, max(360, width - 48), max(170, height - 136))
        rectangles.append((panel, _SURFACE))
        self._label(texts, "Studio Shaping", Rect(panel.x + 12, panel.top - 40, panel.width - 24, 28), size=17)
        cycles = self.snapshot.render_engine == 'CYCLES'
        x = panel.x + 12
        for action, label, supported in (
                ("STUDIO_SCRIM", "Create Scrim", cycles),
                ("STUDIO_FLAG", "Create Flag", True),
                ("STUDIO_REFLECTOR", "Create Reflector", cycles),
                ("PLACEMENT_TOOL", "Placement Tool", True)):
            rect = Rect(x, panel.top - 78, 126, 30)
            rectangles.append((rect, _SURFACE_ALT if supported else (0.09, 0.09, 0.09, 1.0)))
            self._label(texts, label, rect, size=10, color=_TEXT if supported else _MUTED_TEXT)
            if supported:
                self._add_hit(hits, rect, action)
            x += 134
        self._label(
            texts,
            f"Engine: {self.snapshot.render_engine} · Scrim/Reflector are Cycles-only; Flag is physical in both engines.",
            Rect(panel.x + 12, panel.top - 110, panel.width - 24, 22),
            size=10,
            color=_MUTED_TEXT,
        )
        y = panel.top - 144
        for index, (name, kind) in enumerate(self.snapshot.studio_items[:12]):
            rect = Rect(panel.x + 12, y - index * 28, min(440, panel.width - 24), 24)
            rectangles.append((rect, _SURFACE_ALT))
            self._label(texts, f"{kind.title()}: {name}", rect, size=10)
            self._add_hit(hits, rect, "STUDIO_SELECT", name)
        bottom_x = panel.x + 12
        for action, label in (
                ("TRACK_ADD", "Track Target"),
                ("TRACK_REMOVE", "Remove Track"),
                ("STUDIO_SINGLE", "Single User"),
                ("STUDIO_DELETE", "Remove Object")):
            rect = Rect(bottom_x, panel.y + 12, 108, 28)
            rectangles.append((rect, _SURFACE_ALT))
            self._label(texts, label, rect, size=9)
            self._add_hit(hits, rect, action)
            bottom_x += 114

    def draw(self, region) -> None:
        if self.cleaned:
            return
        self.layout_token = next_layout_token(self.layout_token)
        bounds = self.desk_bounds(region)
        rectangles = [
            (bounds, _BACKGROUND),
            (Rect(bounds.x, max(bounds.y, bounds.top - 2), bounds.width, 2), _ACCENT),
        ]
        texts = []
        hits = []
        self._draw_header(bounds.width, bounds.height, rectangles, texts, hits)
        self._draw_tabs(bounds.width, bounds.height, rectangles, texts, hits)
        if self.tab == "LINK":
            self._draw_link(bounds.width, bounds.height, rectangles, texts, hits)
        elif self.tab == "MIX":
            self._draw_mix(bounds.width, bounds.height, rectangles, texts, hits)
        elif self.tab == "LOOKS":
            self._draw_looks(bounds.width, bounds.height, rectangles, texts, hits)
        else:
            self._draw_studio(bounds.width, bounds.height, rectangles, texts, hits)
        if self.show_help:
            help_rect = Rect(max(12, bounds.width - 430), 18, min(410, bounds.width - 24), 68)
            rectangles.append((help_rect, (0.08, 0.10, 0.14, 0.98)))
            self._label(texts, "Click cells to cycle Off / Include / Exclude.  Ctrl/Shift select ranges.", help_rect, size=10)
            self._label(texts, "Move above the Desk to navigate the scene.  Esc closes Desk.", Rect(help_rect.x, help_rect.y + 24, help_rect.width, 24), size=10)
        try:
            gpu.state.blend_set('ALPHA')
            _draw_rect_batch(rectangles)
            _draw_text_batch(texts)
        finally:
            gpu.state.blend_set('NONE')
        self.hit_regions = tuple(hits)

    def resolve_hit(self, x: float, y: float):
        return hit_test(self.hit_regions, self.layout_token, x, y)

    def handle_motion(self, event) -> bool:
        hit = self.resolve_hit(event.mouse_region_x, event.mouse_region_y)
        signature = None if hit is None else (hit.action, hit.payload)
        if signature == self.hover:
            return False
        self.hover = signature
        tag_owner_window(self.area)
        return True

    def handle_wheel(self, context, event) -> bool:
        direction = -1.0 if event.type == 'WHEELUPMOUSE' else 1.0
        hit = self.resolve_hit(event.mouse_region_x, event.mouse_region_y)
        if self.tab == "MIX" and hit is not None and hit.action == "MIX_ENERGY":
            names = self._selected_light_names(hit.payload[0])
            bpy.ops.object.light_helper_mixer_batch(
                action="ADJUST_EV",
                value=-direction * 0.25,
                target_names_json=json.dumps(names),
            )
            self.refresh_snapshot()
            return True
        if self.tab == "MIX" and hit is not None and hit.action == "MIX_SCALAR":
            row_index, _name, column = hit.payload
            row = self.snapshot.mixer_rows[row_index]
            names = self._selected_light_names(row_index)
            property_name = column
            current = row.value(column, 0.0)
            if column == "size":
                property_name = {
                    'AREA': 'size',
                    'POINT': 'shadow_soft_size',
                    'SPOT': 'shadow_soft_size',
                    'SUN': 'angle',
                }.get(row.light_type, 'size')
            elif column == "spot":
                property_name = 'spot_size'
                current = current[0] if isinstance(current, tuple) and current[0] is not None else 0.0
            if column in {"diffuse", "specular", "transmission", "volume"}:
                candidate = max(0.0, float(current) - direction * 0.1)
                property_name += "_factor"
            else:
                candidate = max(0.0001, float(current) * (1.1 ** (-direction)))
            bpy.ops.object.light_helper_mixer_batch(
                action="SET_SCALAR",
                property_name=property_name,
                value=candidate,
                target_names_json=json.dumps(names),
            )
            self.refresh_snapshot()
            return True
        if event.shift:
            self.column_scroll = max(0.0, self.column_scroll + direction * 100.0)
        else:
            self.row_scroll = max(0.0, self.row_scroll + direction * 81.0)
        tag_owner_window(self.area)
        return True

    def handle_text(self, event) -> bool:
        if not self.search_focus:
            return False
        attribute = "light_search" if self.search_focus == "LIGHT" else "target_search"
        value = getattr(self, attribute)
        if event.type == 'BACK_SPACE' and event.value == 'PRESS':
            setattr(self, attribute, value[:-1])
        elif event.value == 'PRESS' and getattr(event, "unicode", "") and event.unicode.isprintable():
            setattr(self, attribute, value + event.unicode)
        else:
            return False
        self.row_scroll = 0.0
        self.column_scroll = 0.0
        tag_owner_window(self.area)
        return True

    def _selected_light_names(self, fallback_row=None) -> list[str]:
        indexes = self.selection.rows.normalized(len(self.snapshot.rows))
        if fallback_row is not None and int(fallback_row) not in indexes:
            indexes = (int(fallback_row),)
        return [self.snapshot.rows[index].source_name for index in indexes]

    def _sync_blender_selection(self, context) -> None:
        if not self.sync_selection:
            return
        names = set(self._selected_light_names())
        for obj in context.selected_objects:
            if obj.name not in names:
                obj.select_set(False)
        active = None
        for name in names:
            obj = context.scene.objects.get(name)
            if obj is not None:
                obj.select_set(True)
                active = active or obj
        if active is not None:
            context.view_layer.objects.active = active

    def _dispatch_cell(self, row_index, target_index, channel, state) -> None:
        row = self.snapshot.rows[row_index]
        target = self.snapshot.targets[target_index]
        bpy.ops.object.light_helper_desk_set_channel(
            source_name=row.source_name,
            item_name=target.name,
            item_kind=target.kind,
            channel=channel,
            state=_state_cycle(state),
        )
        self.refresh_snapshot()

    def _dispatch_bulk(self, channel, state) -> None:
        cells = self.selection.selected_cells(len(self.snapshot.rows), len(self.snapshot.targets))
        payload = []
        for row_index, target_index in cells:
            row = self.snapshot.rows[row_index]
            target = self.snapshot.targets[target_index]
            payload.append((row.source_name, target.name, target.kind))
        if not payload:
            return
        bpy.ops.object.light_helper_desk_set_channel_bulk(
            entries_json=json.dumps(payload),
            channel=channel,
            state=state,
        )
        self.refresh_snapshot()

    def handle_click(self, context, event) -> str:
        hit = self.resolve_hit(event.mouse_region_x, event.mouse_region_y)
        if hit is None:
            self.search_focus = ""
            return "HANDLED"
        action = hit.action
        payload = hit.payload
        if action == "CLOSE":
            return "CLOSE"
        if action == "TAB":
            self.tab = payload[0]
            self.search_focus = ""
            context.window_manager.light_helper_property.lighting_desk_tab = self.tab
        elif action == "HELP":
            self.show_help = not self.show_help
        elif action == "EXPAND":
            self.expanded = not self.expanded
            self.hit_regions = ()
            self.hover = None
        elif action == "FALSE_COLOR":
            bpy.ops.scene.light_helper_toggle_false_color(enabled=not self.snapshot.false_color_enabled)
            self.refresh_snapshot()
        elif action == "SEARCH":
            self.search_focus = payload[0]
        elif action == "TARGET_FILTER":
            values = ("ALL", "OBJECT", "COLLECTION")
            self.target_filter = values[(values.index(self.target_filter) + 1) % len(values)]
            self.column_scroll = 0.0
        elif action == "LIGHT_FILTER":
            values = ("ALL", "AREA", "POINT", "SPOT", "SUN")
            self.light_filter = values[(values.index(self.light_filter) + 1) % len(values)]
            self.row_scroll = 0.0
        elif action == "SELECT_ROW":
            self.selection.rows.select(payload[0], ctrl=event.ctrl, shift=event.shift)
            self._sync_blender_selection(context)
        elif action == "SELECT_COLUMN":
            self.selection.columns.select(payload[0], ctrl=event.ctrl, shift=event.shift)
        elif action == "CELL":
            row_index, target_index, channel, state = payload
            self.selection.ensure_cell(row_index, target_index, ctrl=event.ctrl, shift=event.shift)
            self._sync_blender_selection(context)
            self._dispatch_cell(row_index, target_index, channel, state)
        elif action == "BULK":
            self._dispatch_bulk(*payload)
        elif action == "MIX_COLUMNS":
            values = ("MINIMAL", "NORMAL", "ADVANCED")
            self.mixer_columns = values[(values.index(self.mixer_columns) + 1) % len(values)]
        elif action == "SYNC_SELECTION":
            self.sync_selection = not self.sync_selection
            context.window_manager.light_helper_property.lighting_desk_sync_selection = self.sync_selection
            if self.sync_selection:
                self._sync_blender_selection(context)
        elif action in {"MIX_SELECT", "MIX_ENERGY"}:
            self.selection.rows.select(payload[0], ctrl=event.ctrl, shift=event.shift)
            self._sync_blender_selection(context)
        elif action == "MIX_MUTE":
            if payload[0] not in self.selection.rows.values or event.ctrl or event.shift:
                self.selection.rows.select(payload[0], ctrl=event.ctrl, shift=event.shift)
            names = self._selected_light_names(payload[0])
            bpy.ops.object.light_helper_mixer_batch(
                action="TOGGLE_MUTE", target_names_json=json.dumps(names),
            )
            self.refresh_snapshot()
        elif action == "MIX_SOLO":
            row_index, light_name, _column = payload
            light = context.scene.objects.get(light_name)
            if light is not None:
                with context.temp_override(solo_light_object=light):
                    bpy.ops.object.light_helper_solo_light(index=-1)
                self.refresh_snapshot()
        elif action == "MIX_RENDER":
            if payload[0] not in self.selection.rows.values or event.ctrl or event.shift:
                self.selection.rows.select(payload[0], ctrl=event.ctrl, shift=event.shift)
            names = self._selected_light_names(payload[0])
            row = self.snapshot.mixer_rows[payload[0]]
            bpy.ops.object.light_helper_mixer_batch(
                action="SET_RENDER",
                enabled=not bool(row.value("render", True)),
                target_names_json=json.dumps(names),
            )
            self.refresh_snapshot()
        elif action in {"MIX_SHADOW", "MIX_NORMALIZE"}:
            row_index, _light_name, column = payload
            row = self.snapshot.mixer_rows[row_index]
            names = self._selected_light_names(row_index)
            value = bool(row.value(column, False))
            bpy.ops.object.light_helper_mixer_batch(
                action="SET_BOOL",
                property_name="use_shadow" if column == "shadow" else "normalize",
                enabled=not value,
                target_names_json=json.dumps(names),
            )
            self.refresh_snapshot()
        elif action == "MIX_VISIBILITY":
            row_index, _light_name, _column = payload
            row = self.snapshot.mixer_rows[row_index]
            names = self._selected_light_names(row_index)
            visibility = row.value("visibility", (True,))
            camera_visible = bool(visibility[0]) if visibility else True
            bpy.ops.object.light_helper_mixer_batch(
                action="SET_BOOL",
                property_name="visible_camera",
                enabled=not camera_visible,
                target_names_json=json.dumps(names),
            )
            self.refresh_snapshot()
        elif action == "MIX_COPY":
            names = self._selected_light_names()
            if names:
                bpy.ops.object.light_helper_mixer_copy(source_name=names[0], full=False)
        elif action == "MIX_PASTE":
            names = self._selected_light_names()
            if names:
                bpy.ops.object.light_helper_mixer_paste(
                    target_names_json=json.dumps(names), full=bool(payload[0]),
                )
                self.refresh_snapshot()
        elif action == "MIX_KELVIN":
            from ..ops.light_mixer import KELVIN_PRESETS

            names = self._selected_light_names()
            if names:
                self.kelvin_preset_index = (self.kelvin_preset_index + 1) % len(KELVIN_PRESETS)
                temperature = KELVIN_PRESETS[self.kelvin_preset_index][2]
                bpy.ops.object.light_helper_mixer_batch(
                    action="SET_KELVIN",
                    value=temperature,
                    target_names_json=json.dumps(names),
                )
                self.refresh_snapshot()
        elif action == "MIX_COLOR":
            row_index, _light_name, _column = payload
            names = self._selected_light_names(row_index)
            self.close_requested = True
            bpy.ops.object.light_helper_mixer_batch(
                'INVOKE_DEFAULT',
                action="SET_RGB",
                target_names_json=json.dumps(names),
            )
        elif action == "PROFILE_SELECT":
            bpy.ops.scene.light_helper_profile_select(index=int(payload[0]))
            self.refresh_snapshot()
        elif action == "PROFILE_CAPTURE":
            bpy.ops.scene.light_helper_profile_capture(name="Lighting Look")
            self.refresh_snapshot()
        elif action == "PROFILE_APPLY":
            bpy.ops.scene.light_helper_profile_apply('EXEC_DEFAULT', create_missing=False)
            self.refresh_snapshot()
        elif action == "PROFILE_CREATE":
            bpy.ops.scene.light_helper_profile_apply('EXEC_DEFAULT', create_missing=True)
            self.refresh_snapshot()
        elif action == "PROFILE_REMOVE":
            bpy.ops.scene.light_helper_profile_remove()
            self.refresh_snapshot()
        elif action == "PROFILE_IMPORT":
            self.close_requested = True
            bpy.ops.scene.light_helper_profile_import('INVOKE_DEFAULT')
        elif action == "PROFILE_EXPORT":
            self.close_requested = True
            bpy.ops.scene.light_helper_profile_export('INVOKE_DEFAULT')
        elif action == "GROUP_SYNC":
            bpy.ops.scene.light_helper_light_groups_sync()
            self.refresh_snapshot()
        elif action == "GROUP_BUILD":
            bpy.ops.scene.light_helper_light_group_build_compositor()
            self.refresh_snapshot()
        elif action == "GROUP_REMOVE":
            bpy.ops.scene.light_helper_light_group_remove_compositor()
            self.refresh_snapshot()
        elif action == "GROUP_EV":
            bpy.ops.scene.light_helper_light_group_adjust(
                group_name=str(payload[0]), ev_delta=float(payload[1]),
            )
            self.refresh_snapshot()
        elif action == "GROUP_ASSIGN":
            bpy.ops.object.light_helper_assign_light_group(group_name=str(payload[0]))
            self.refresh_snapshot()
        elif action == "STUDIO_SCRIM":
            bpy.ops.object.light_helper_create_scrim()
            self.refresh_snapshot()
        elif action == "STUDIO_FLAG":
            bpy.ops.object.light_helper_create_flag()
            self.refresh_snapshot()
        elif action == "STUDIO_REFLECTOR":
            bpy.ops.object.light_helper_create_reflector()
            self.refresh_snapshot()
        elif action == "PLACEMENT_TOOL":
            self.close_requested = True
            bpy.ops.wm.tool_set_by_id(name="light_helper.placement")
        elif action == "STUDIO_SELECT":
            obj = context.scene.objects.get(str(payload[0]))
            if obj is not None:
                for selected in tuple(context.selected_objects):
                    selected.select_set(False)
                obj.select_set(True)
                context.view_layer.objects.active = obj
        elif action == "TRACK_ADD":
            bpy.ops.object.light_helper_add_track_target()
            self.refresh_snapshot()
        elif action == "TRACK_REMOVE":
            bpy.ops.object.light_helper_remove_track_target()
            self.refresh_snapshot()
        elif action == "STUDIO_SINGLE":
            bpy.ops.object.light_helper_make_studio_single_user()
            self.refresh_snapshot()
        elif action == "STUDIO_DELETE":
            bpy.ops.object.light_helper_remove_studio_object()
            self.refresh_snapshot()
        tag_owner_window(self.area)
        return "HANDLED"


def new_desk_session(context, operator) -> DeskSession | None:
    if context.area is None or context.area.type != 'VIEW_3D':
        return None
    if context.region is None or context.region.type != 'WINDOW':
        return None
    session = DeskSession(context, operator)
    return session if session.acquire() else None


def get_desk_session(window, area) -> DeskSession | None:
    return _ACTIVE_BY_OWNER.get(owner_key(window, area))


def refresh_active_desks() -> None:
    for session in tuple(_ACTIVE_BY_OWNER.values()):
        try:
            session.refresh_snapshot()
        except (AttributeError, ReferenceError, RuntimeError, TypeError):
            session.close_requested = True


def cleanup_all_desks() -> None:
    for session in tuple(_ACTIVE_BY_OWNER.values()):
        try:
            session.cleanup()
        except (AttributeError, ReferenceError, RuntimeError, TypeError):
            pass
    _ACTIVE_BY_OWNER.clear()
    _remove_draw_handler_if_unused()


def active_desk_count() -> int:
    return len(_ACTIVE_BY_OWNER)


def register() -> None:
    """UI registration hook; GPU resources remain lazy until the Desk opens."""


def unregister() -> None:
    cleanup_all_desks()


__all__ = [
    "DeskSession",
    "active_desk_count",
    "capture_desk_snapshot",
    "cleanup_all_desks",
    "get_desk_session",
    "new_desk_session",
    "owner_key",
    "register",
    "refresh_active_desks",
    "tag_owner_window",
    "unregister",
]
