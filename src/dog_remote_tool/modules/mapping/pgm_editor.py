from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import CommandSpec, echo_message, quote, scp_push_command, ssh_command, sudo_run_shell


BRUSH_OBSTACLE = "obstacle"
BRUSH_ERASE = "erase"
BRUSH_UNKNOWN = "unknown"
BRUSH_RESTORE = "restore"
UNKNOWN_PIXEL_VALUE = 128
KNOWN_PIXEL_VALUES = {0, 255}


@dataclass(frozen=True)
class PgmMap:
    header: bytes
    pixels: bytes
    width: int
    height: int
    maxval: int = 255

    def to_bytes(self) -> bytes:
        return self.header + self.pixels


def _read_token(data: bytes, offset: int) -> tuple[bytes, int]:
    size = len(data)
    while offset < size:
        byte = data[offset]
        if byte in b" \t\r\n":
            offset += 1
            continue
        if byte == ord("#"):
            newline = data.find(b"\n", offset)
            if newline < 0:
                raise ValueError("PGM 头部注释未结束")
            offset = newline + 1
            continue
        break
    start = offset
    while offset < size and data[offset] not in b" \t\r\n":
        offset += 1
    if start == offset:
        raise ValueError("PGM 头部不完整")
    return data[start:offset], offset


def _skip_single_separator(data: bytes, offset: int) -> int:
    if offset >= len(data) or data[offset] not in b" \t\r\n":
        raise ValueError("PGM 头部和像素数据之间缺少分隔符")
    return offset + 1


def load_pgm(path: str | Path) -> PgmMap:
    data = Path(path).read_bytes()
    magic, offset = _read_token(data, 0)
    if magic != b"P5":
        raise ValueError("仅支持二进制 P5 map.pgm")
    width_token, offset = _read_token(data, offset)
    height_token, offset = _read_token(data, offset)
    maxval_token, offset = _read_token(data, offset)
    try:
        width = int(width_token)
        height = int(height_token)
        maxval = int(maxval_token)
    except ValueError as exc:
        raise ValueError("PGM 尺寸或 maxval 不是整数") from exc
    if width <= 0 or height <= 0:
        raise ValueError("PGM 尺寸必须大于 0")
    if maxval != 255:
        raise ValueError("仅支持 maxval=255 的 8-bit map.pgm")
    pixel_offset = _skip_single_separator(data, offset)
    expected = width * height
    actual = len(data) - pixel_offset
    if actual != expected:
        raise ValueError(f"PGM 像素长度不匹配：声明 {expected} 字节，实际 {actual} 字节")
    return PgmMap(header=data[:pixel_offset], pixels=data[pixel_offset:], width=width, height=height, maxval=maxval)


def save_pgm(path: str | Path, pgm: PgmMap, pixels: bytes | bytearray | None = None) -> None:
    payload = bytes(pixels) if pixels is not None else pgm.pixels
    if len(payload) != pgm.width * pgm.height:
        raise ValueError("PGM 保存失败：像素长度不匹配")
    Path(path).write_bytes(pgm.header + payload)


def brush_value(mode: str) -> int:
    if mode == BRUSH_OBSTACLE:
        return 0
    if mode == BRUSH_ERASE:
        return 255
    if mode == BRUSH_UNKNOWN:
        return UNKNOWN_PIXEL_VALUE
    raise ValueError(f"恢复模式没有固定写入值: {mode}")


def is_known_pixel(value: int) -> bool:
    return value in KNOWN_PIXEL_VALUES


def erase_circle(
    pixels: bytearray,
    original: bytes,
    width: int,
    height: int,
    center_x: float,
    center_y: float,
    radius: int,
    mode: str = BRUSH_ERASE,
) -> int:
    radius = max(1, int(radius))
    min_x = max(0, int(center_x - radius))
    max_x = min(width - 1, int(center_x + radius))
    min_y = max(0, int(center_y - radius))
    max_y = min(height - 1, int(center_y + radius))
    radius_sq = radius * radius
    changed = 0
    fixed_value = None if mode == BRUSH_RESTORE else brush_value(mode)
    for y in range(min_y, max_y + 1):
        dy = y - center_y
        for x in range(min_x, max_x + 1):
            dx = x - center_x
            if dx * dx + dy * dy > radius_sq:
                continue
            index = y * width + x
            value = original[index] if fixed_value is None else fixed_value
            if pixels[index] != value:
                pixels[index] = value
                changed += 1
    return changed


def erase_stroke(
    pixels: bytearray,
    original: bytes,
    width: int,
    height: int,
    start: tuple[float, float],
    end: tuple[float, float],
    radius: int,
    mode: str = BRUSH_ERASE,
) -> int:
    x0, y0 = start
    x1, y1 = end
    distance = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
    step = max(1.0, radius / 2.0)
    segments = max(1, int(distance / step))
    changed = 0
    for index in range(segments + 1):
        t = index / segments
        changed += erase_circle(
            pixels,
            original,
            width,
            height,
            x0 + (x1 - x0) * t,
            y0 + (y1 - y0) * t,
            radius,
            mode,
        )
    return changed


def local_backup_path(map_pgm_path: str | Path, now: datetime | None = None) -> Path:
    timestamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    return Path(map_pgm_path).parent / "backups" / f"map_original_{timestamp}.pgm"


def upload_edited_map_pgm_command(profile: ProductProfile, local_pgm: str, remote_pgm: str) -> CommandSpec:
    remote_dir = str(Path(remote_pgm).parent)
    remote_yaml = str(Path(remote_pgm).with_name("map.yaml"))
    temp_dir = f"{profile.home.rstrip('/')}/dog_remote_tool_map_edit_upload"
    temp_file = temp_dir + "/map.pgm"
    prepare = ssh_command(profile, f"rm -rf {quote(temp_dir)} && mkdir -p {quote(temp_dir)}")
    upload = scp_push_command(profile, local_pgm, temp_file)
    remote_install = (
        sudo_run_shell()
        + f"TARGET={quote(remote_pgm)}; TARGET_DIR={quote(remote_dir)}; TARGET_YAML={quote(remote_yaml)}; TMP={quote(temp_file)}; "
        "case \"$TARGET\" in */map.pgm) ;; *) echo '[ERROR] 目标不是 map.pgm，拒绝替换'; exit 2 ;; esac; "
        "if [ ! -s \"$TARGET\" ]; then echo '[ERROR] 远端 map.pgm 不存在或为空: '$TARGET; exit 3; fi; "
        "if [ ! -s \"$TARGET_YAML\" ]; then echo '[ERROR] 远端 map.yaml 不存在或为空: '$TARGET_YAML; exit 4; fi; "
        "if [ ! -s \"$TMP\" ]; then echo '[ERROR] 上传临时 map.pgm 不存在或为空: '$TMP; exit 5; fi; "
        "BACKUP=\"$TARGET.bak.$(date +%Y%m%d_%H%M%S)\"; "
        "sudo_run cp -a -- \"$TARGET\" \"$BACKUP\" && "
        "sudo_run install -m 0644 \"$TMP\" \"$TARGET\" || exit $?; "
        "rm -rf -- "
        + quote(temp_dir)
        + "; "
        "echo '[INFO] 远端 map.pgm 已替换'; "
        "echo '[INFO] 远端备份: '\"$BACKUP\"; "
        "ls -lh \"$TARGET\" \"$BACKUP\""
    )
    command = (
        f"test -s {quote(local_pgm)} || {{ {echo_message(f'[ERROR] 本地编辑后 map.pgm 不存在或为空: {local_pgm}')}; exit 2; }}; "
        f"{prepare} && {upload} && {ssh_command(profile, remote_install)}"
    )
    return CommandSpec(
        "保存编辑地图",
        command,
        dangerous=True,
        description=f"远端 map.pgm：{remote_pgm}\n本地编辑文件：{local_pgm}\n远端会先生成 map.pgm.bak.<时间> 备份。",
        display_command="保存编辑地图",
        concurrency="parallel",
        locks=(f"host:{profile.host}:map:{remote_pgm}",),
    )
