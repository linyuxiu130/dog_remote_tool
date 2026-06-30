from __future__ import annotations

from collections.abc import Mapping

StatusStyle = tuple[str, str, str]
StatusStyleMap = Mapping[str, StatusStyle]


def style_for_state(styles: StatusStyleMap, state: str, default_state: str = "unknown") -> StatusStyle:
    return styles.get(state, styles[default_state])
