"""Pure planning helpers for the managed Light Group compositor chain."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from typing import Iterable, Mapping


class CompositeConnectionDecision(str, Enum):
    CONNECT = "CONNECT"
    REPLACE_MANAGED = "REPLACE_MANAGED"
    PRESERVE_USER = "PRESERVE_USER"


@dataclass(frozen=True)
class GroupAdjustment:
    name: str
    ev: float = 0.0
    tint: tuple[float, float, float] = (1.0, 1.0, 1.0)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Light Group name cannot be empty")
        if len(self.tint) != 3 or any(component < 0.0 for component in self.tint):
            raise ValueError("Tint must contain three non-negative components")


def group_key(name: str) -> str:
    return sha256(name.encode("utf-8")).hexdigest()[:16]


def decide_composite_connection(
    *, input_is_linked: bool, source_is_managed: bool
) -> CompositeConnectionDecision:
    if not input_is_linked:
        return CompositeConnectionDecision.CONNECT
    if source_is_managed:
        return CompositeConnectionDecision.REPLACE_MANAGED
    return CompositeConnectionDecision.PRESERVE_USER


def build_light_group_plan(
    group_names: Iterable[str],
    adjustments: Mapping[str, GroupAdjustment] | None = None,
) -> dict:
    """Return a deterministic residual-plus-adjusted-group operation graph."""
    names = list(group_names)
    if any(not isinstance(name, str) or not name for name in names):
        raise ValueError("Light Group names must be non-empty strings")
    if len(set(names)) != len(names):
        raise ValueError("Light Group names must be unique")
    settings = adjustments or {}
    steps: list[dict] = []
    residual = "combined"
    for name in names:
        key = group_key(name)
        output = f"residual:{key}"
        steps.append(
            {"role": output, "operation": "SUBTRACT", "inputs": [residual, f"raw:{key}"]}
        )
        residual = output
    total = residual
    groups: list[dict] = []
    for name in names:
        key = group_key(name)
        setting = settings.get(name, GroupAdjustment(name=name))
        exposure = f"exposure:{key}"
        tinted = f"tint:{key}"
        summed = f"sum:{key}"
        steps.extend(
            [
                {
                    "role": exposure,
                    "operation": "EXPOSURE",
                    "inputs": [f"raw:{key}"],
                    "ev": float(setting.ev),
                },
                {
                    "role": tinted,
                    "operation": "MULTIPLY",
                    "inputs": [exposure],
                    "tint": [float(value) for value in setting.tint],
                },
                {"role": summed, "operation": "ADD", "inputs": [total, tinted]},
            ]
        )
        total = summed
        groups.append(
            {"name": name, "key": key, "ev": float(setting.ev), "tint": list(setting.tint)}
        )
    return {"groups": groups, "steps": steps, "output": total}


__all__ = [
    "CompositeConnectionDecision",
    "GroupAdjustment",
    "build_light_group_plan",
    "decide_composite_connection",
    "group_key",
]
