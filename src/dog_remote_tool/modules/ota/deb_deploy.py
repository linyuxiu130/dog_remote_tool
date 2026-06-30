from __future__ import annotations

import io
import subprocess
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DebPackageInfo:
    file_name: str
    package: str
    version: str
    architecture: str


@dataclass(frozen=True)
class WheelPackageInfo:
    file_name: str
    package: str
    version: str


@dataclass(frozen=True)
class SmallPackageArchiveMember:
    path: str
    file_name: str
    kind: str
    size: int


def is_deb_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() == ".deb"


def is_whl_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() == ".whl"


def is_small_package_file(path: Path) -> bool:
    return is_deb_file(path) or is_whl_file(path)


def is_small_package_archive(path: Path) -> bool:
    return bool(small_package_archive_members(path))


def is_deploy_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    return any(path.glob("*.deb")) or any(path.glob("*.whl"))


def is_small_package_path(path: Path) -> bool:
    return is_small_package_file(path) or is_deploy_dir(path) or is_small_package_archive(path)


def small_package_files(path: Path) -> list[Path]:
    if is_small_package_file(path):
        return [path]
    if not path.is_dir():
        return []
    return sorted(
        [item for item in path.iterdir() if item.is_file() and item.suffix.lower() in {".deb", ".whl"}],
        key=lambda item: item.name,
    )


def small_package_entries(path: Path) -> list[tuple[str, int]]:
    if is_small_package_archive(path):
        return [(member.path, member.size) for member in small_package_archive_members(path)]
    return [(item.name, item.stat().st_size) for item in small_package_files(path)]


def small_package_archive_members(path: Path) -> list[SmallPackageArchiveMember]:
    if not path.is_file():
        return []
    suffixes = [suffix.lower() for suffix in path.suffixes]
    if path.suffix.lower() == ".zip":
        return _zip_small_members(path)
    if suffixes[-2:] == [".tar", ".gz"]:
        return _tar_small_members(path)
    return []


def deb_package_info(path: Path) -> DebPackageInfo | None:
    if not is_deb_file(path):
        return None
    control = _read_control_with_stdlib(path) or _read_control_with_dpkg(path)
    if not control:
        return None
    fields = _parse_control_fields(control)
    package = fields.get("Package", "")
    version = fields.get("Version", "")
    architecture = fields.get("Architecture", "")
    if not package and not version and not architecture:
        return None
    return DebPackageInfo(path.name, package or path.stem, version or "未知", architecture or "未知")


def deploy_dir_packages(path: Path) -> list[DebPackageInfo]:
    if not path.is_dir():
        return []
    packages: list[DebPackageInfo] = []
    for deb in sorted(path.glob("*.deb"), key=lambda item: item.name):
        info = deb_package_info(deb)
        if info:
            packages.append(info)
        else:
            packages.append(DebPackageInfo(deb.name, deb.stem, "未识别", "未知"))
    return packages


def wheel_package_info(path: Path) -> WheelPackageInfo | None:
    if not is_whl_file(path):
        return None
    stem = path.name[:-4]
    parts = stem.split("-")
    package = parts[0].replace("_", "-") if parts and parts[0] else path.stem
    version = parts[1] if len(parts) > 1 and parts[1] else "未知"
    return WheelPackageInfo(path.name, package, version)


def deploy_dir_wheels(path: Path) -> list[WheelPackageInfo]:
    if not path.is_dir():
        return []
    return [
        info
        for info in (wheel_package_info(item) for item in sorted(path.glob("*.whl"), key=lambda item: item.name))
        if info
    ]


def deploy_scripts(path: Path) -> list[str]:
    if not path.is_dir():
        return []
    return [name for name in ("deploy.sh", "deploy_rootfs.sh") if (path / name).is_file()]


def deb_detail_rows(path: Path) -> list[tuple[str, str]]:
    if is_deb_file(path):
        info = deb_package_info(path)
        if not info:
            return [("包类型", "Debian 小包"), ("包状态", "未识别 deb 控制信息")]
        return [
            ("包类型", "Debian 小包"),
            ("Package", info.package),
            ("Version", info.version),
            ("Architecture", info.architecture),
        ]
    if is_whl_file(path):
        info = wheel_package_info(path)
        if not info:
            return [("包类型", "Python wheel 小包"), ("包状态", "未识别 wheel 文件名")]
        return [
            ("包类型", "Python wheel 小包"),
            ("Package", info.package),
            ("Version", info.version),
        ]
    if is_deploy_dir(path):
        packages = deploy_dir_packages(path)
        wheels = deploy_dir_wheels(path)
        scripts = deploy_scripts(path)
        architectures = sorted({item.architecture for item in packages if item.architecture and item.architecture != "未知"})
        rows: list[tuple[str, str]] = [
            ("包类型", "小包部署目录"),
            ("脚本", "、".join(scripts) if scripts else "未发现"),
            ("小包数量", f"{len(packages) + len(wheels)} 个"),
            ("架构", "、".join(architectures) if architectures else "未知"),
        ]
        for item in packages[:16]:
            rows.append((f"小包 · {item.package}", f"{item.version} ({item.architecture})"))
        shown = len(packages[:16])
        for item in wheels[: max(0, 16 - shown)]:
            rows.append((f"wheel · {item.package}", item.version))
            shown += 1
        total = len(packages) + len(wheels)
        if total > shown:
            rows.append(("小包", f"另 {total - shown} 个"))
        return rows
    members = small_package_archive_members(path)
    if members:
        deb_count = sum(1 for item in members if item.kind == "deb")
        whl_count = sum(1 for item in members if item.kind == "whl")
        rows = [
            ("包类型", "小包压缩包"),
            ("小包数量", f"{len(members)} 个"),
            ("内容", f"{deb_count} 个 deb / {whl_count} 个 whl"),
        ]
        for item in members[:16]:
            rows.append((f"{item.kind} · {item.file_name}", _human_bytes(item.size)))
        if len(members) > 16:
            rows.append(("小包", f"另 {len(members) - 16} 个"))
        return rows
    return []


def deb_light_summary(path: Path) -> str:
    if is_deb_file(path):
        info = deb_package_info(path)
        if not info:
            return "Debian 小包；控制信息未识别"
        return f"Debian 小包：{info.package} {info.version}；架构：{info.architecture}"
    if is_whl_file(path):
        info = wheel_package_info(path)
        if not info:
            return "Python wheel 小包；文件名未识别"
        return f"Python wheel 小包：{info.package} {info.version}"
    if is_deploy_dir(path):
        packages = deploy_dir_packages(path)
        wheels = deploy_dir_wheels(path)
        scripts = deploy_scripts(path)
        architectures = sorted({item.architecture for item in packages if item.architecture and item.architecture != "未知"})
        parts = [f"小包部署目录：{len(packages)} 个 deb / {len(wheels)} 个 whl"]
        if scripts:
            parts.append("脚本：" + "、".join(scripts))
        if architectures:
            parts.append("架构：" + "、".join(architectures))
        return "；".join(parts)
    members = small_package_archive_members(path)
    if members:
        deb_count = sum(1 for item in members if item.kind == "deb")
        whl_count = sum(1 for item in members if item.kind == "whl")
        total_size = sum(item.size for item in members)
        return f"小包压缩包：{deb_count} 个 deb / {whl_count} 个 whl；展开大小：{_human_bytes(total_size)}"
    return ""


def _read_control_with_stdlib(path: Path) -> str:
    payload = _read_ar_member(path, lambda name: name.startswith("control.tar"))
    if not payload:
        return ""
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:*") as tf:
            for member in tf:
                if member.name.lstrip("./") == "control":
                    stream = tf.extractfile(member)
                    return stream.read().decode("utf-8", errors="ignore") if stream else ""
    except (tarfile.TarError, OSError, EOFError):
        return ""
    return ""


def _read_control_with_dpkg(path: Path) -> str:
    try:
        result = subprocess.run(
            ["dpkg-deb", "-f", str(path)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout if result.returncode == 0 else ""


def _parse_control_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    current_key = ""
    for raw in text.splitlines():
        if not raw:
            current_key = ""
            continue
        if raw[:1].isspace():
            if current_key:
                fields[current_key] += "\n" + raw.strip()
            continue
        if ":" not in raw:
            current_key = ""
            continue
        key, value = raw.split(":", 1)
        current_key = key.strip()
        fields[current_key] = value.strip()
    return fields


def _zip_small_members(path: Path) -> list[SmallPackageArchiveMember]:
    try:
        with zipfile.ZipFile(path) as zf:
            return [
                SmallPackageArchiveMember(item.filename, Path(item.filename).name, suffix.lstrip("."), item.file_size)
                for item in zf.infolist()
                if not item.is_dir()
                for suffix in (Path(item.filename).suffix.lower(),)
                if suffix in {".deb", ".whl"} and Path(item.filename).name
            ]
    except (OSError, zipfile.BadZipFile):
        return []


def _tar_small_members(path: Path) -> list[SmallPackageArchiveMember]:
    try:
        with tarfile.open(path, mode="r:*") as tf:
            return [
                SmallPackageArchiveMember(item.name, Path(item.name).name, suffix.lstrip("."), item.size)
                for item in tf.getmembers()
                if item.isfile()
                for suffix in (Path(item.name).suffix.lower(),)
                if suffix in {".deb", ".whl"} and Path(item.name).name
            ]
    except (OSError, tarfile.TarError, EOFError):
        return []


def _human_bytes(size: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.2f} {unit}"
        value /= 1024


def _read_ar_member(path: Path, predicate) -> bytes:
    try:
        stream = path.open("rb")
    except OSError:
        return b""
    with stream:
        if stream.read(8) != b"!<arch>\n":
            return b""
        while True:
            header = stream.read(60)
            if not header:
                return b""
            if len(header) < 60:
                return b""
            try:
                name = header[:16].decode("utf-8", errors="ignore").strip()
                size = int(header[48:58].decode("ascii", errors="ignore").strip())
            except ValueError:
                return b""
            clean_name = name.rstrip("/").split("/", 1)[0]
            if predicate(clean_name):
                return stream.read(size)
            stream.seek(size + (size % 2), 1)
