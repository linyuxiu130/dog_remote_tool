from __future__ import annotations


MAPPING_SAVE_TITLE = "结束并保存建图"
MAPPING_SAVE_INTERRUPTED_CODES = {143, -1}
MAPPING_SAVE_ACCEPTED_MARKERS = (
    "MappingSaveBegin",
    "MappingSaving",
    "建图状态：保存中",
    "建图状态: 保存中",
    "保存中",
    "结束保存请求已确认",
)


def mapping_save_continues_after_local_stop(
    title: str,
    code: int,
    lines: list[str] | tuple[str, ...] | None = None,
) -> bool:
    if title != MAPPING_SAVE_TITLE or code not in MAPPING_SAVE_INTERRUPTED_CODES:
        return False
    if lines is None:
        return True
    text = "\n".join(lines)
    return any(marker in text for marker in MAPPING_SAVE_ACCEPTED_MARKERS)
