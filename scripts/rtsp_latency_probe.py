#!/usr/bin/env python3
from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dog_remote_tool.ui.pages.control import video as control_video  # noqa: E402


def _open_capture(cv2, url: str):
    pipeline = control_video.gstreamer_rtsp_pipeline(url)
    capture, diagnostics = control_video._open_gstreamer_capture(cv2, pipeline)
    if capture.isOpened():
        return capture, control_video.RTSP_BACKEND_GSTREAMER
    if diagnostics:
        print(f"gstreamer_open_diagnostics={diagnostics}", file=sys.stderr)
    return capture, control_video.RTSP_BACKEND_GSTREAMER


def _read_latest(capture):
    return capture.read()


def probe_url(url: str, frames: int) -> int:
    import cv2

    start = time.monotonic()
    capture, backend = _open_capture(cv2, url)
    open_ms = (time.monotonic() - start) * 1000
    print(f"url={url}")
    print(f"backend={backend}")
    print(f"open_ms={open_ms:.1f}")
    if not capture.isOpened():
        print("status=failed_open")
        return 2

    timestamps: list[float] = []
    read_times: list[float] = []
    try:
        for index in range(frames):
            read_start = time.monotonic()
            ok, frame = _read_latest(capture)
            read_ms = (time.monotonic() - read_start) * 1000
            if not ok or frame is None:
                print(f"frame_{index}=failed read_ms={read_ms:.1f}")
                break
            timestamps.append(time.monotonic())
            read_times.append(read_ms)
            if index == 0:
                print(f"first_frame_shape={frame.shape}")
                print(f"first_frame_since_open_ms={(timestamps[-1] - start) * 1000:.1f}")
    finally:
        capture.release()

    if not timestamps:
        print("status=failed_read")
        return 3
    if len(timestamps) > 1:
        intervals = [(new - old) * 1000 for old, new in zip(timestamps, timestamps[1:])]
        print(f"interval_avg_ms={statistics.mean(intervals):.1f}")
        print(f"interval_p95_ms={sorted(intervals)[max(0, int(len(intervals) * 0.95) - 1)]:.1f}")
        print(f"interval_max_ms={max(intervals):.1f}")
    print(f"read_avg_ms={statistics.mean(read_times):.1f}")
    print(f"read_max_ms={max(read_times):.1f}")
    print("status=ok")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe Dog Remote Tool RTSP receive latency.")
    parser.add_argument("urls", nargs="+", help="RTSP URL(s) to probe")
    parser.add_argument("--frames", type=int, default=20, help="Frames to read per URL")
    args = parser.parse_args()

    exit_code = 0
    for url in args.urls:
        result = probe_url(url, max(1, args.frames))
        exit_code = max(exit_code, result)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
