#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT_DIR="${1:-$ROOT_DIR/resources/rtsp_bridge/ubuntu22.04-arm64/debs}"

mkdir -p "$OUT_DIR"

exec python3 "$SCRIPT_DIR/fetch_rtsp_bridge_debs.py" "$OUT_DIR"
