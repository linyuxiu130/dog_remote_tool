from __future__ import annotations

from typing import Any


ROUTE_DIRECTION_BOTH = "both"
ROUTE_DIRECTION_FORWARD = "forward"
ROUTE_DIRECTION_BOTH_VALUES = {"0", "2", "both", "bidirectional", "双向"}


def normalized_direction(direction: int | str | None) -> str:
    if str(direction).strip().lower() in ROUTE_DIRECTION_BOTH_VALUES:
        return ROUTE_DIRECTION_BOTH
    return ROUTE_DIRECTION_FORWARD


def direction_label(direction: int | str | None) -> str:
    return "双向" if normalized_direction(direction) == ROUTE_DIRECTION_BOTH else "单向"


def edge_direction_change(edge: Any, direction: int | str | None, *, toggle_forward: bool = False) -> str:
    normalized = normalized_direction(direction)
    current = normalized_direction(edge.direction)
    if normalized == ROUTE_DIRECTION_FORWARD and current == ROUTE_DIRECTION_FORWARD and toggle_forward:
        return "reverse"
    if normalized == current:
        return "none"
    return "set"


def apply_edge_direction(edge: Any, direction: int | str | None, *, toggle_forward: bool = False) -> str:
    change = edge_direction_change(edge, direction, toggle_forward=toggle_forward)
    if change == "reverse":
        reverse_edge_direction(edge)
        edge.cost = edge.length()
    elif change == "set":
        edge.direction = normalized_direction(direction)
        edge.properties["direction"] = edge.direction
    return change


def reverse_edge_direction(edge: Any) -> None:
    edge.startid, edge.endid = edge.endid, edge.startid
    edge.coordinates = list(reversed(edge.coordinates))
    edge.direction = ROUTE_DIRECTION_FORWARD
    edge.properties["startid"] = edge.startid
    edge.properties["endid"] = edge.endid
    edge.properties["direction"] = ROUTE_DIRECTION_FORWARD
