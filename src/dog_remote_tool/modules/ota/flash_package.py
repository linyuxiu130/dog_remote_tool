from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tarfile

from dog_remote_tool.modules.ota.package_utils import human_bytes, is_tar_gz, package_release_name


S100_MARKERS = (
    "product/img_packages/flash_all.sh",
    "product/img_packages/s100-gpt.json",
    "product/img_packages/disk/emmc_disk.simg",
)

S100_BOOT_SECURITY_FILES = {
    "secure_ohp": (
        "xmodem_tools/sec/out/s100/cmd_load_hsmfw_ohp",
        "xmodem_tools/sec/out/s100/hsmfw_se_ohp.pkg",
        "xmodem_tools/sec/out/s100/cmd_exit_hsmfw_ohp",
        "xmodem_tools/sec/out/s100/fpt.img",
        "xmodem_tools/sec/out/s100/keyimage_ohp.img",
        "xmodem_tools/sec/out/s100/SBL.img",
        "xmodem_tools/sec/out/s100/hsmrca_ohp.pkg",
        "xmodem_tools/sec/out/s100/spl.img",
        "xmodem_tools/sec/out/s100/MCU_S100_V1.0.img",
        "xmodem_tools/sec/out/s100/acore_cfg.img",
        "xmodem_tools/sec/out/s100/bl31.img",
        "xmodem_tools/sec/out/s100/optee.img",
        "xmodem_tools/sec/out/s100/uboot.img",
    ),
    "secure": (
        "xmodem_tools/sec/out/s100/cmd_load_hsmfw",
        "xmodem_tools/sec/out/s100/hsmfw_se.pkg",
        "xmodem_tools/sec/out/s100/cmd_exit_hsmfw",
        "xmodem_tools/sec/out/s100/fpt.img",
        "xmodem_tools/sec/out/s100/keyimage.img",
        "xmodem_tools/sec/out/s100/SBL.img",
        "xmodem_tools/sec/out/s100/hsmrca.pkg",
        "xmodem_tools/sec/out/s100/spl.img",
        "xmodem_tools/sec/out/s100/MCU_S100_V1.0.img",
        "xmodem_tools/sec/out/s100/acore_cfg.img",
        "xmodem_tools/sec/out/s100/bl31.img",
        "xmodem_tools/sec/out/s100/optee.img",
        "xmodem_tools/sec/out/s100/uboot.img",
    ),
    "nosecure": (
        "xmodem_tools/nosec/out/s100/cmd_load_sbl",
        "xmodem_tools/nosec/out/s100/sbl.pkg",
        "xmodem_tools/nosec/out/s100/cmd_exit_sbl",
        "xmodem_tools/nosec/out/s100/u-boot-spl_ddr.bin",
        "xmodem_tools/nosec/out/s100/S100_MCU_V1.0.bin",
        "xmodem_tools/nosec/out/s100/hobot-s100-bl31.dtb",
        "xmodem_tools/nosec/out/s100/bl31.bin",
        "xmodem_tools/nosec/out/s100/tee-pager_v2.bin",
        "xmodem_tools/nosec/out/s100/u-boot.bin",
    ),
}

ORIN_MARKERS = (
    "bootloader/flashcmd.txt",
    "bootloader/system.img",
)


def flash_type_label(package_type: str) -> str:
    return {
        "s100_flash": "S100 线刷包",
        "orin_flash": "Orin NX 线刷包",
        "line_flash": "线刷包",
    }.get(package_type, "未知线刷包")


def flash_type_hint(path: str | Path, *, inspect: bool = False) -> str:
    package = Path(path).expanduser()
    name = package.name.lower()
    if "s100" in name:
        return "s100_flash"
    if "flash" in name and any(token in name for token in ("orin", "nx", "zgnx", "xgnx")):
        return "orin_flash"
    if not inspect or not package.is_file():
        return ""
    return inspect_flash_package(package)


def inspect_flash_package(package: Path) -> str:
    if not is_tar_gz(package):
        return ""
    try:
        with tarfile.open(package, "r:gz") as tf:
            seen: set[str] = set()
            for index, member in enumerate(tf):
                if index > 1600:
                    break
                name = member.name.lstrip("./").lower()
                if name.endswith("/"):
                    continue
                seen.add(name)
                if any(marker in seen for marker in S100_MARKERS):
                    return "s100_flash"
                if any(marker in seen for marker in ORIN_MARKERS):
                    return "orin_flash"
    except (EOFError, OSError, tarfile.TarError):
        return ""
    return ""


def flash_detail_rows(path: str) -> list[tuple[str, str]]:
    if not path:
        return []
    package = Path(path).expanduser()
    if not package.is_file():
        return [("包状态", "文件不存在")]
    package_type = flash_type_hint(package, inspect=True)
    if not package_type:
        return []
    rows = [
        ("包设备版本", package_release_name(package)),
        ("包类型", flash_type_label(package_type)),
        ("包大小", human_bytes(package.stat().st_size)),
    ]
    if package_type == "s100_flash":
        rows.extend(
            [
                ("刷机入口", "product/img_packages/flash_all.sh"),
                ("刷机方式", "本机 USB DFU 引导到 fastboot 后线刷，默认 -m all"),
            ]
        )
        rows.extend(_s100_reusable_tree_detail_rows(package))
    elif package_type == "orin_flash":
        rows.extend(
            [
                ("刷机入口", "bootloader/flashcmd.txt"),
                ("系统镜像", "bootloader/system.img"),
                ("刷机方式", "本机 USB recovery/flash 脚本线刷"),
            ]
        )
    return rows


def _s100_reusable_tree_detail_rows(package: Path) -> list[tuple[str, str]]:
    for tree_root in _s100_reusable_tree_candidates(package):
        if not tree_root.is_dir():
            continue
        flash_script = _s100_find_flash_script(tree_root)
        if not flash_script:
            continue
        flash_dir = flash_script.parent
        product_root = flash_dir.parent
        rows: list[tuple[str, str]] = [("已解压目录", str(tree_root))]
        media = []
        if (flash_dir / "disk" / "emmc_disk.simg").is_file():
            media.append("eMMC(disk/emmc_disk.simg)")
        if (flash_dir / "disk" / "ufs_disk.simg").is_file():
            media.append("UFS(disk/ufs_disk.simg)")
        rows.append(("整盘镜像", "、".join(media) if media else "未确认 eMMC/UFS 整盘镜像"))
        security, count, missing = _s100_detect_boot_security(product_root)
        if security:
            rows.append(("DFU 引导安全类型", f"{security} ({count} 个文件)"))
        elif missing:
            rows.append(("DFU 引导安全类型", f"缺少文件: {missing[0]}" + (f" 等 {len(missing)} 个" if len(missing) > 1 else "")))
        else:
            rows.append(("DFU 引导安全类型", "未确认"))
        return rows
    return [("整盘镜像", "执行预检时检查 eMMC/UFS 镜像")]


def _s100_reusable_tree_candidates(package: Path) -> list[Path]:
    stem = str(package)
    if stem.endswith(".tar.gz"):
        stem = stem[:-7]
    elif stem.endswith(".tgz"):
        stem = stem[:-4]
    candidates = [Path(f"{stem}_extracted")]
    if package.is_file():
        stat = package.stat()
        digest = hashlib.sha256(f"{stat.st_size}_{int(stat.st_mtime)}".encode("utf-8")).hexdigest()[:16]
        base = package.name
        if base.endswith(".tar.gz"):
            base = base[:-7]
        elif base.endswith(".tgz"):
            base = base[:-4]
        root = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "dog_remote_tool" / "line_flash"
        candidates.append(root / f"{base}_{digest}")
    return candidates


def _s100_find_flash_script(tree_root: Path) -> Path | None:
    direct = tree_root / "product" / "img_packages" / "flash_all.sh"
    if direct.is_file():
        return direct
    for candidate in tree_root.rglob("product/img_packages/flash_all.sh"):
        if candidate.is_file():
            return candidate
    return None


def _s100_detect_boot_security(product_root: Path) -> tuple[str, int, list[str]]:
    requested = os.environ.get("DOG_REMOTE_TOOL_S100_BOOT_SECURITY", "")
    order = [requested] if requested else ["secure_ohp", "secure", "nosecure"]
    for security in order:
        files = S100_BOOT_SECURITY_FILES.get(security)
        if not files:
            continue
        missing = [path for path in files if not (product_root / path).is_file()]
        if not missing:
            return security, len(files), []
    if requested and requested not in S100_BOOT_SECURITY_FILES:
        return "", 0, [f"DOG_REMOTE_TOOL_S100_BOOT_SECURITY={requested}"]
    security = order[0] if order else "secure_ohp"
    files = S100_BOOT_SECURITY_FILES.get(security, ())
    missing = [path for path in files if not (product_root / path).is_file()]
    return "", 0, missing


_package_release_name = package_release_name
