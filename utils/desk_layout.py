"""Pure layout, selection, and color helpers for the Lighting Desk.

This module deliberately has no Blender imports.  The modal owner captures RNA
into immutable snapshots, then the GPU renderer and tests consume these plain
Python values.
"""

from dataclasses import dataclass, field
import math
from typing import Iterable, Sequence


DESK_TABS = ("LINK", "MIX", "LOOKS", "STUDIO")
MIXER_COLUMN_SETS = {
    "MINIMAL": ("name", "type", "mute", "solo", "render", "energy", "color"),
    "NORMAL": (
        "name", "type", "mute", "solo", "render", "energy", "color",
        "size", "spot", "link_count", "light_group", "visibility",
    ),
    "ADVANCED": (
        "name", "type", "mute", "solo", "render", "energy", "color",
        "size", "spot", "link_count", "light_group", "visibility",
        "diffuse", "specular", "transmission", "volume", "shadow", "normalize",
    ),
}


@dataclass(frozen=True, slots=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def top(self) -> float:
        return self.y + self.height

    def contains(self, x: float, y: float) -> bool:
        return self.x <= x < self.right and self.y <= y < self.top


@dataclass(frozen=True, slots=True)
class VisibleSlice:
    start: int
    stop: int
    offset: float

    @property
    def count(self) -> int:
        return max(0, self.stop - self.start)


@dataclass(frozen=True, slots=True)
class HitRegion:
    token: int
    rect: Rect
    action: str
    payload: tuple = ()


@dataclass(frozen=True, slots=True)
class LinkTargetSnapshot:
    name: str
    kind: str


@dataclass(frozen=True, slots=True)
class LinkCellSnapshot:
    illumination: str
    shadow: str
    illumination_inherited: bool = False
    shadow_inherited: bool = False


@dataclass(frozen=True, slots=True)
class LinkRowSnapshot:
    source_name: str
    source_type: str
    cells: tuple[LinkCellSnapshot, ...]


@dataclass(frozen=True, slots=True)
class MixerRowSnapshot:
    name: str
    light_type: str
    values: tuple[tuple[str, object], ...]

    def value(self, key: str, default=None):
        for item_key, item_value in self.values:
            if item_key == key:
                return item_value
        return default


@dataclass(frozen=True, slots=True)
class DeskSnapshot:
    revision: int
    rows: tuple[LinkRowSnapshot, ...]
    targets: tuple[LinkTargetSnapshot, ...]
    mixer_rows: tuple[MixerRowSnapshot, ...] = ()
    false_color_enabled: bool = False
    render_engine: str = ""
    profiles: tuple[tuple[str, bool], ...] = ()
    light_groups: tuple[tuple[str, float, tuple[float, float, float]], ...] = ()
    studio_items: tuple[tuple[str, str], ...] = ()


def clamp_scroll(offset: float, total: int, extent: float, viewport: float) -> float:
    """Clamp a pixel scroll offset for a one-dimensional virtual list."""
    content = max(0.0, float(total) * max(0.0, float(extent)))
    return min(max(0.0, float(offset)), max(0.0, content - max(0.0, float(viewport))))


def visible_slice(
    total: int,
    offset: float,
    viewport: float,
    extent: float,
    *,
    overscan: int = 1,
) -> VisibleSlice:
    """Return only indexes intersecting a virtual viewport.

    ``offset`` and ``viewport`` are pixels.  One overscan item on either edge
    avoids popping while scrolling without laying out the complete matrix.
    """
    total = max(0, int(total))
    extent = max(float(extent), 1.0)
    viewport = max(float(viewport), 0.0)
    offset = clamp_scroll(offset, total, extent, viewport)
    overscan = max(0, int(overscan))
    first = max(0, int(math.floor(offset / extent)) - overscan)
    last = min(total, int(math.ceil((offset + viewport) / extent)) + overscan)
    return VisibleSlice(first, last, offset)


def filter_indices(
    entries: Sequence,
    query: str = "",
    kind_filter: str = "ALL",
) -> tuple[int, ...]:
    """Return stable source indexes matching a case-insensitive query/type."""
    needle = query.casefold().strip()
    kind_filter = kind_filter.upper()
    result = []
    for index, entry in enumerate(entries):
        name = str(getattr(entry, "name", entry[0] if isinstance(entry, tuple) else entry))
        kind = str(getattr(entry, "kind", entry[1] if isinstance(entry, tuple) and len(entry) > 1 else ""))
        if kind_filter != "ALL" and kind.upper() != kind_filter:
            continue
        if needle and needle not in name.casefold():
            continue
        result.append(index)
    return tuple(result)


@dataclass(slots=True)
class RangeSelection:
    """Stable Ctrl/Shift selection for one virtual axis."""

    values: set[int] = field(default_factory=set)
    anchor: int | None = None

    def clear(self) -> None:
        self.values.clear()
        self.anchor = None

    def select(self, index: int, *, ctrl: bool = False, shift: bool = False) -> None:
        index = int(index)
        if shift and self.anchor is not None:
            lo, hi = sorted((self.anchor, index))
            ranged = set(range(lo, hi + 1))
            if ctrl:
                self.values.update(ranged)
            else:
                self.values = ranged
            return
        if ctrl:
            if index in self.values:
                self.values.remove(index)
            else:
                self.values.add(index)
            self.anchor = index
            return
        self.values = {index}
        self.anchor = index

    def normalized(self, upper_bound: int) -> tuple[int, ...]:
        return tuple(sorted(index for index in self.values if 0 <= index < upper_bound))


@dataclass(slots=True)
class MatrixSelection:
    rows: RangeSelection = field(default_factory=RangeSelection)
    columns: RangeSelection = field(default_factory=RangeSelection)

    def ensure_cell(self, row: int, column: int, *, ctrl: bool = False, shift: bool = False) -> None:
        self.rows.select(row, ctrl=ctrl, shift=shift)
        self.columns.select(column, ctrl=ctrl, shift=shift)

    def selected_cells(self, row_count: int, column_count: int) -> tuple[tuple[int, int], ...]:
        rows = self.rows.normalized(row_count)
        columns = self.columns.normalized(column_count)
        return tuple((row, column) for row in rows for column in columns)


def next_layout_token(current: int) -> int:
    """Increment a frame token while reserving zero as 'no geometry'."""
    value = (int(current) + 1) & 0x7FFFFFFF
    return value or 1


def hit_test(regions: Iterable[HitRegion], token: int, x: float, y: float) -> HitRegion | None:
    """Resolve top-most geometry only when it belongs to the live frame."""
    for region in reversed(tuple(regions)):
        if region.token == token and region.rect.contains(x, y):
            return region
    return None


def _srgb_to_linear(channel: float) -> float:
    channel = min(1.0, max(0.0, channel))
    if channel <= 0.04045:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def kelvin_to_linear_rgb(temperature: float) -> tuple[float, float, float]:
    """Deterministic blackbody approximation converted to scene-linear RGB.

    The approximation is intentionally bounded to 1000-40000 K.  It is used
    for interactive lighting controls, not spectral rendering; converting its
    sRGB result explicitly avoids view-transform dependent values.
    """
    kelvin = min(40000.0, max(1000.0, float(temperature))) / 100.0
    if kelvin <= 66.0:
        red = 255.0
        green = 99.4708025861 * math.log(kelvin) - 161.1195681661
        if kelvin <= 19.0:
            blue = 0.0
        else:
            blue = 138.5177312231 * math.log(kelvin - 10.0) - 305.0447927307
    else:
        red = 329.698727446 * ((kelvin - 60.0) ** -0.1332047592)
        green = 288.1221695283 * ((kelvin - 60.0) ** -0.0755148492)
        blue = 255.0
    srgb = tuple(min(255.0, max(0.0, value)) / 255.0 for value in (red, green, blue))
    return tuple(_srgb_to_linear(value) for value in srgb)


def colors_close(a: Sequence[float], b: Sequence[float], tolerance: float = 1e-5) -> bool:
    return len(a) >= 3 and len(b) >= 3 and all(
        abs(float(a[index]) - float(b[index])) <= tolerance for index in range(3)
    )


def apply_ev(energy: float, ev: float) -> float:
    return max(0.0, float(energy) * (2.0 ** float(ev)))


def apply_linear_tint(color: Sequence[float], tint: Sequence[float]) -> tuple[float, float, float]:
    return tuple(
        min(1.0, max(0.0, float(color[index]) * float(tint[index])))
        for index in range(3)
    )
