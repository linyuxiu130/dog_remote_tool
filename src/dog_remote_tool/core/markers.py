from __future__ import annotations


def extract_marked_payload(text: str, begin: str, end: str) -> str:
    collecting = False
    payload_lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if line == begin:
            collecting = True
            payload_lines = []
            continue
        if line == end:
            break
        if collecting:
            payload_lines.append(raw)
    return "\n".join(payload_lines)
