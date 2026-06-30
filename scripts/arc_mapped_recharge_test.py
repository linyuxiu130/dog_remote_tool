#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import arc_mapless_recharge_test as base

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import quote, ssh_command
from dog_remote_tool.modules import mapping


def configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.description = "连续有图回充测试，默认 50 次。"
    parser.epilog = "运行中可输入 stop 回车请求停止；按 Ctrl+C 也会转为停止请求，并在退出前发送 exit_charging 出桩清理。"
    parser.add_argument("map_pcd_pos", nargs="?", help="已标记充电桩的远端 map.pcd 路径")
    parser.add_argument("--map-pcd", dest="map_pcd_opt", help="已标记充电桩的远端 map.pcd 路径")
    parser.add_argument("--save-map-path", help="远端地图根目录，默认使用设备配置")


def validate_args(args: argparse.Namespace) -> None:
    positional = (getattr(args, "map_pcd_pos", "") or "").strip()
    optional = (getattr(args, "map_pcd_opt", "") or "").strip()
    if positional and optional and positional != optional:
        raise SystemExit("位置参数 map_pcd 和 --map-pcd 不一致")
    args.map_pcd = optional or positional
    if args.map_pcd and not args.map_pcd.endswith(".pcd"):
        raise SystemExit("--map-pcd 必须指向远端 map.pcd")


def arc_marked_map_list_command(profile: ProductProfile, save_map_path: str) -> str:
    root = save_map_path.rstrip("/")
    history_root = root + "/history_map"
    inner = (
        f"ROOT={quote(root)}; HISTORY={quote(history_root)}; "
        "list_yaml() { "
        "[ -s \"$ROOT/map.yaml\" ] && printf '%s\\n' \"$ROOT/map.yaml\"; "
        "find \"$HISTORY\" -maxdepth 3 -type f -name map.yaml -size +0c -print 2>/dev/null || true; "
        "}; "
        "list_yaml | while IFS= read -r yaml; do "
        "dir=$(dirname \"$yaml\"); pcd=\"$dir/map.pcd\"; pgm=\"$dir/map.pgm\"; "
        "[ -s \"$pcd\" ] || continue; "
        "if grep -Eq '^arc_position_flag:[[:space:]]*(1|true|True|yes|Yes)([[:space:]#]|$)' \"$yaml\"; then "
        "ts=$(stat -c '%Y' \"$pgm\" 2>/dev/null || stat -c '%Y' \"$yaml\" 2>/dev/null || echo 0); "
        "name=$(basename \"$dir\"); "
        "printf '%s\\t%s\\t%s\\n' \"$ts\" \"$name\" \"$pcd\"; "
        "fi; "
        "done | sort -nr"
    )
    return ssh_command(profile, inner)


def list_arc_marked_maps(profile: ProductProfile, save_map_path: str) -> list[tuple[str, str]]:
    result = base.run_command_capture(arc_marked_map_list_command(profile, save_map_path), timeout=45)
    if result.returncode != 0:
        raise SystemExit("读取远端已标记充电桩地图失败：" + base.last_error_line(result.output))
    maps: list[tuple[str, str]] = []
    for raw in result.output.splitlines():
        parts = raw.split("\t")
        if len(parts) < 3:
            continue
        maps.append((parts[1], parts[2]))
    return maps


def choose_map_pcd(maps: list[tuple[str, str]]) -> str:
    if not maps:
        raise SystemExit("远端未发现已标记充电桩的地图，请先在导航页完成充电桩标记。")
    if not sys.stdin.isatty():
        if len(maps) == 1:
            label, path = maps[0]
            print(f"已自动选择已标记充电桩地图：{label} -> {path}")
            return path
        print("远端发现多个已标记充电桩地图，请用 --map-pcd 指定：")
        for index, (label, path) in enumerate(maps, 1):
            print(f"  {index}. {label} -> {path}")
        raise SystemExit("非交互模式不能自动选择多个地图")
    print("请选择已标记充电桩地图：")
    for index, (label, path) in enumerate(maps, 1):
        default_mark = "（默认）" if index == 1 else ""
        print(f"  {index}. {label} -> {path} {default_mark}")
    answer = input("地图编号，直接回车选择第 1 个: ").strip()
    if not answer:
        return maps[0][1]
    if answer.isdigit() and 1 <= int(answer) <= len(maps):
        return maps[int(answer) - 1][1]
    raise SystemExit(f"无效地图选择: {answer}")


def prepare_args(profile: ProductProfile, args: argparse.Namespace) -> None:
    if args.map_pcd:
        return
    save_map_path = (args.save_map_path or "").strip() or mapping.default_save_map_path(profile)
    maps = list_arc_marked_maps(profile, save_map_path)
    args.map_pcd = choose_map_pcd(maps)


def main(argv: list[str] | None = None) -> int:
    return base.main(
        argv,
        test_title="有图回充测试",
        dock_phase="有图回充",
        configure_parser=configure_parser,
        validate_args=validate_args,
        prepare_args=prepare_args,
        dock_runner=base.run_mapped_dock_action,
    )


if __name__ == "__main__":
    raise SystemExit(main())
