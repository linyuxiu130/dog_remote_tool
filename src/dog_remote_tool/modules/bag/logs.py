from __future__ import annotations

import shlex


LOG_PATHS = {
    "xg": ["/tmp/zsibot/log", "/home/firefly/.ros/log"],
    "zg": ["/tmp/zsibot/log", "/home/robot/.ros/log"],
    "nx": ["/tmp/log/alg_data", "/tmp/zsibot/log", "/home/robot/.ros/log"],
    "nxl2": ["/tmp/log/alg_data", "/tmp/zsibot/log", "/home/robot/.ros/log"],
    "net": ["/tmp/zsibot/log", "/home/jszr/.ros/log"],
    "zgnx": ["/tmp/log/alg_data", "/tmp/zsibot/log", "/home/robot/.ros/log"],
}


def candidate_log_paths(product: str, log_kind: str = "all") -> list[str]:
    paths = LOG_PATHS.get(product, ["/tmp/zsibot/log"])
    if log_kind == "ros":
        return [path for path in paths if "/.ros/log" in path]
    if log_kind == "runtime":
        return [path for path in paths if "/.ros/log" not in path]
    return paths


def resolve_log_paths_command(candidates: list[str]) -> str:
    quoted_candidates = " ".join(shlex.quote(path) for path in candidates)
    return f"for path in {quoted_candidates}; do [ -d \"$path\" ] && printf '%s\\n' \"$path\"; done"


def parse_resolved_log_paths(output: str, candidates: list[str]) -> list[str]:
    candidate_set = set(candidates)
    return [line.strip() for line in output.splitlines() if line.strip() in candidate_set]
