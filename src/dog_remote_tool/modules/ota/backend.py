from __future__ import annotations

import argparse
import subprocess
from datetime import datetime
from pathlib import Path

from dog_remote_tool.core.quoting import quote
import dog_remote_tool.modules.ota.backend_runner as _runner
import dog_remote_tool.modules.ota.inspect as _ota_inspect
from dog_remote_tool.modules.ota import deb_deploy
from dog_remote_tool.modules.ota import local_validation
import dog_remote_tool.modules.ota.manifest_reader as _ota_manifest_reader
from dog_remote_tool.modules.ota import package_locator
from dog_remote_tool.modules.ota import remote_execution
from dog_remote_tool.modules.ota.package_utils import (
    human_bytes,
    is_zip,
)
import dog_remote_tool.modules.ota.manifest as _ota_manifest
from dog_remote_tool.modules.ota.inspect import inspect_nx_package, inspect_rk3588_package, nx_system_archive_size
from dog_remote_tool.modules.ota.package_classifier import package_family as _package_family
from dog_remote_tool.modules.ota import remote_checks
from dog_remote_tool.modules.ota import remote_nx
from dog_remote_tool.modules.ota import remote_rk
from dog_remote_tool.modules.ota.targets import TARGETS
from dog_remote_tool.modules.ota.types import OtaPackageManifest, OtaTarget


SSH_OPTS = _runner.SSH_OPTS
REMOTE_DIR_CANDIDATES = ("~/ota",)


def package_family(package: Path) -> str:
    return _package_family(package)


is_zg3588_full_zip_manifest = _ota_manifest.is_zg3588_full_zip_manifest
manifest_summary = _ota_manifest.manifest_summary
rk3588_firmware_coverage = _ota_manifest.rk3588_firmware_coverage
log = _runner.log
die = _runner.die
run_stream = _runner.run_stream
capture = _runner.capture
ssh_args = _runner.ssh_args
scp_args = _runner.scp_args
rsync_args = _runner.rsync_args
remote_supports_rsync = _runner.remote_supports_rsync
ensure_tools = _runner.ensure_tools
package_manifest = _ota_manifest_reader.package_manifest
inspect_tools_package = _ota_inspect.inspect_tools_package


def package_candidates(patterns: tuple[str, ...]) -> list[Path]:
    return package_locator.package_candidates(patterns)


def latest_local(pattern: str) -> Path | None:
    return package_locator.latest_local(pattern)


def latest_package_for_family(family: str) -> Path | None:
    return package_locator.latest_package_for_family(family)


def default_nx_tools() -> Path | None:
    return package_locator.default_nx_tools()


def resolve_remote_dir(target: OtaTarget, remote_dir: str) -> str:
    script = r"""
set -euo pipefail
REMOTE_DIR_INPUT=__REMOTE_DIR__
if [ -n "$REMOTE_DIR_INPUT" ]; then
  case "$REMOTE_DIR_INPUT" in
    ~*) REMOTE_DIR="$HOME${REMOTE_DIR_INPUT#\~}" ;;
    *) REMOTE_DIR="$REMOTE_DIR_INPUT" ;;
  esac
  mkdir -p "$REMOTE_DIR"
else
  REMOTE_DIR="$HOME/ota"
  mkdir -p "$REMOTE_DIR"
fi
test_file="$REMOTE_DIR/.ota_write_test_$$"
: > "$test_file"
rm -f "$test_file"
printf '%s\n' "$REMOTE_DIR"
""".replace("__REMOTE_DIR__", quote(remote_dir))
    return capture(ssh_args(target, script)).strip().splitlines()[-1]


def remote_file_size(target: OtaTarget, remote_path: str) -> int:
    output = capture(ssh_args(target, f"stat -c '%s' {quote(remote_path)}"))
    return int(output.strip().splitlines()[-1])


def remote_file_size_or_zero(target: OtaTarget, remote_path: str) -> int:
    output = capture(ssh_args(target, f"stat -c '%s' {quote(remote_path)} 2>/dev/null || echo 0"))
    return int(output.strip().splitlines()[-1])


def upload_file(target: OtaTarget, src: Path, remote_dir: str, *, remote_has_rsync: bool | None = None) -> str:
    remote_path = f"{remote_dir}/{src.name}"
    local_size = src.stat().st_size
    log(f"[upload] {src.name} ({human_bytes(local_size)}) -> {target.remote}:{remote_dir}")
    if remote_has_rsync is None:
        remote_has_rsync = remote_supports_rsync(target)
    if remote_has_rsync:
        run_stream(rsync_args(target, src, remote_dir))
    else:
        run_stream(scp_args(target, src, remote_dir))
    size = remote_file_size(target, remote_path)
    if size != local_size:
        die(f"上传校验失败: {src.name} 本地 {local_size}, 远端 {size}")
    log("[upload] 大小校验通过")
    return remote_path


def create_remote_dir(target: OtaTarget, remote_dir: str) -> None:
    capture(ssh_args(target, f"mkdir -p {quote(remote_dir)}"))


def remote_device_info(target: OtaTarget, remote_dir: str, *, mcu_maintenance: bool = False) -> None:
    script = remote_checks.device_info_script(remote_dir, target.key, mcu_maintenance=mcu_maintenance)
    remote = "IFS= read -r SUDO_PASSWORD || SUDO_PASSWORD=; export SUDO_PASSWORD; bash -lc " + quote(script)
    run_stream(ssh_args(target, remote), input_text=target.password + "\n")


def remote_precheck(
    target: OtaTarget,
    remote_dir: str,
    package: Path,
    tools: Path | None,
    manifest: OtaPackageManifest | None = None,
) -> None:
    package_size = package.stat().st_size
    if target.family == "nx":
        payload_size = manifest.system_size if manifest else inspect_nx_package(package)
        system_archive_size = nx_system_archive_size(package)
        tools_size = tools.stat().st_size if tools else 0
        zip_extract_size = system_archive_size if is_zip(package) else 0
        script = remote_checks.nx_precheck_script(
            remote_dir,
            package.name,
            is_zip(package),
            package_size,
            payload_size,
            system_archive_size,
            tools_size,
            zip_extract_size,
        )
        remote = "IFS= read -r SUDO_PASSWORD || exit 1; export SUDO_PASSWORD; bash -lc " + quote(script)
        run_stream(ssh_args(target, remote), input_text=target.password + "\n")
        return

    if manifest:
        img_path, img_size = manifest.system_image, manifest.system_size
    else:
        img_path, img_size = inspect_rk3588_package(package)
    script = remote_checks.rk_precheck_script(remote_dir, package.name, package_size, img_path, img_size)
    remote = "IFS= read -r SUDO_PASSWORD || exit 1; export SUDO_PASSWORD; bash -lc " + quote(script)
    run_stream(ssh_args(target, remote), input_text=target.password + "\n")


def small_deploy_remote_script() -> str:
    return r"""
set -euo pipefail
REMOTE_STAGE="${REMOTE_STAGE:?}"
SUDO_PASSWORD="${SUDO_PASSWORD:?}"
RUN_UPGRADE="${RUN_UPGRADE:-1}"
log() { printf '[small-deploy] %s\n' "$*"; }
die() { printf '[ERROR] %s\n' "$*" >&2; exit 1; }
sudo_run() {
  if command -v sudo >/dev/null 2>&1; then
    printf '%s\n' "$SUDO_PASSWORD" | sudo -S -p '' "$@"
  else
    "$@"
  fi
}
test -d "$REMOTE_STAGE" || die "远端小包目录不存在: $REMOTE_STAGE"
DEBS=("$REMOTE_STAGE"/*.deb)
WHLS=("$REMOTE_STAGE"/*.whl)
if [ ! -e "${DEBS[0]}" ] && [ ! -e "${WHLS[0]}" ]; then
  die "远端小包目录未找到 .deb 或 .whl"
fi
log "远端目录: $REMOTE_STAGE"
if [ "$RUN_UPGRADE" != "1" ]; then
  log "prepare-only：仅完成上传，不执行安装"
  exit 0
fi
echo "[DOG_REMOTE_STAGE] upgrade_locked"
log "停止 robot-launch.service"
sudo_run systemctl stop robot-launch.service || true
if [ -e "${DEBS[0]}" ]; then
  for deb in "${DEBS[@]}"; do
    log "安装 deb: ${deb##*/}"
    sudo_run dpkg -i --force-all "$deb"
  done
fi
if [ -e "${WHLS[0]}" ]; then
  command -v python3 >/dev/null 2>&1 || die "远端缺少 python3"
  for whl in "${WHLS[@]}"; do
    log "安装 whl: ${whl##*/}"
    python3 -m pip install --upgrade --no-index --find-links "$REMOTE_STAGE" "$whl"
  done
fi
sync
log "重启 robot-launch.service"
sudo_run systemctl restart robot-launch.service || sudo_run systemctl start robot-launch.service || true
log "小包部署完成"
"""


def small_archive_extract_script() -> str:
    return r"""
set -euo pipefail
REMOTE_ARCHIVE="${REMOTE_ARCHIVE:?}"
REMOTE_STAGE="${REMOTE_STAGE:?}"
python3 - "$REMOTE_ARCHIVE" "$REMOTE_STAGE" <<'PY'
import os
import posixpath
import shutil
import sys
import tarfile
import zipfile

archive, stage = sys.argv[1], sys.argv[2]
os.makedirs(stage, exist_ok=True)

def safe_name(raw):
    name = posixpath.basename(raw.replace("\\", "/"))
    if not name or name in (".", ".."):
        return ""
    lower = name.lower()
    if not (lower.endswith(".deb") or lower.endswith(".whl")):
        return ""
    return name

def write_member(name, stream):
    out_path = os.path.join(stage, name)
    if os.path.exists(out_path):
        raise SystemExit(f"duplicate package name in archive: {name}")
    with open(out_path, "wb") as out:
        shutil.copyfileobj(stream, out)

count = 0
lower_archive = archive.lower()
if lower_archive.endswith(".zip"):
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = safe_name(info.filename)
            if not name:
                continue
            with zf.open(info) as src:
                write_member(name, src)
            count += 1
else:
    with tarfile.open(archive, mode="r:*") as tf:
        for member in tf.getmembers():
            if not member.isfile():
                continue
            name = safe_name(member.name)
            if not name:
                continue
            src = tf.extractfile(member)
            if src is None:
                continue
            with src:
                write_member(name, src)
            count += 1
if count <= 0:
    raise SystemExit("archive does not contain .deb or .whl packages")
print(f"[small-deploy] extracted small packages: {count}")
PY
"""


def log_small_package_inputs(package: Path) -> list[tuple[str, int]]:
    entries = deb_deploy.small_package_entries(package)
    if not entries:
        die("小包路径未找到 .deb 或 .whl")
    log(f"[local] 小包路径: {package}")
    if deb_deploy.is_small_package_archive(package):
        log(f"[local] 小包压缩包: {package.name} ({human_bytes(package.stat().st_size)})")
    log(f"[local] 小包数量: {len(entries)}")
    for name, size in entries:
        log(f"[local] 小包: {name} ({human_bytes(size)})")
    return entries


def remote_small_precheck(target: OtaTarget, remote_dir: str, package: Path) -> None:
    entries = log_small_package_inputs(package)
    total_size = sum(size for _name, size in entries)
    log(f"[local] 小包总大小: {human_bytes(total_size)}")
    script = (
        "set -euo pipefail; "
        f"mkdir -p {quote(remote_dir)}; "
        f"df -hP {quote(remote_dir)} 2>/dev/null | awk 'NR==2 {{printf \"远端目录可用空间: %s\\n\", $4}}'; "
        "command -v dpkg >/dev/null 2>&1 && echo '远端 dpkg: ok' || echo '远端 dpkg: missing'; "
        "command -v python3 >/dev/null 2>&1 && echo '远端 python3: ok' || echo '远端 python3: missing'"
    )
    run_stream(ssh_args(target, script))


def upload_small_package(target: OtaTarget, package: Path, remote_dir: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = package.name if package.is_dir() else package.stem
    remote_stage = f"{remote_dir}/{stem}_small_{stamp}"
    create_remote_dir(target, remote_stage)
    remote_has_rsync = remote_supports_rsync(target)
    if deb_deploy.is_small_package_archive(package):
        remote_archive = upload_file(target, package, remote_stage, remote_has_rsync=remote_has_rsync)
        env = f"REMOTE_ARCHIVE={quote(remote_archive)} REMOTE_STAGE={quote(remote_stage)} "
        run_stream(ssh_args(target, env + "bash -lc " + quote(small_archive_extract_script())))
    else:
        items = deb_deploy.small_package_files(package)
        if not items:
            die("小包路径未找到 .deb 或 .whl")
        for item in items:
            upload_file(target, item, remote_stage, remote_has_rsync=remote_has_rsync)
    return remote_stage


nx_remote_script = remote_nx.nx_remote_script
rk_remote_script = remote_rk.rk_remote_script


def run_remote_script(target: OtaTarget, script: str, env: dict[str, str]) -> None:
    remote_execution.run_remote_script(target, script, env)


def command_device_info(args: argparse.Namespace) -> None:
    target = make_target(args)
    ensure_tools()
    remote_device_info(target, args.remote_dir, mcu_maintenance=args.mcu_maintenance)


def command_verify(args: argparse.Namespace) -> None:
    target = make_target(args)
    ensure_tools()
    log(f"[verify] 目标: {target.label} -> {target.remote}")
    remote_device_info(target, args.remote_dir)


def command_precheck(args: argparse.Namespace) -> None:
    target = make_target(args)
    ensure_tools()
    package = resolve_package(args.package)
    tools = resolve_tools(args.tools) if target.family == "nx" else None
    manifest = validate_local_inputs(target, package, tools)
    remote_dir = resolve_remote_dir(target, args.remote_dir)
    log(f"[precheck] 目标: {target.label} -> {target.remote}")
    log(f"[precheck] 远程目录: {remote_dir}")
    remote_device_info(target, remote_dir)
    remote_precheck(target, remote_dir, package, tools, manifest)


def command_small_precheck(args: argparse.Namespace) -> None:
    target = make_target(args)
    ensure_tools()
    package = resolve_small_package(args.package)
    remote_dir = resolve_remote_dir(target, args.remote_dir)
    log(f"[small-precheck] 目标: {target.label} -> {target.remote}")
    log(f"[small-precheck] 远程目录: {remote_dir}")
    remote_device_info(target, remote_dir)
    remote_small_precheck(target, remote_dir, package)


def command_run(args: argparse.Namespace) -> None:
    target = make_target(args)
    ensure_tools()
    package = resolve_package(args.package)
    tools = resolve_tools(args.tools) if target.family == "nx" else None
    manifest = validate_local_inputs(target, package, tools)
    remote_dir = resolve_remote_dir(target, args.remote_dir)
    log(f"[run] 目标: {target.label} -> {target.remote}")
    log(f"[run] 远程目录: {remote_dir}")
    remote_precheck(target, remote_dir, package, tools, manifest)
    remote_has_rsync = remote_supports_rsync(target)
    if target.family == "nx" and not is_zip(package) and remote_file_size_or_zero(target, f"/ota/{package.name}") == package.stat().st_size:
        log(f"[upload] /ota/{package.name} 已存在且大小一致，跳过升级包上传")
    else:
        upload_file(target, package, remote_dir, remote_has_rsync=remote_has_rsync)
    if tools:
        upload_file(target, tools, remote_dir, remote_has_rsync=remote_has_rsync)

    env = {
        "PACKAGE_NAME": package.name,
        "REMOTE_DIR": remote_dir,
        "SUDO_PASSWORD": target.password,
        "RUN_UPGRADE": "0" if args.prepare_only else "1",
        "TARGET_KEY": target.key,
        "SKIP_NX_MCU": "1" if args.skip_mcu else "0",
    }
    if target.family == "nx":
        assert tools is not None
        env["TOOLS_NAME"] = tools.name
        run_remote_script(target, nx_remote_script(), env)
    else:
        run_remote_script(target, rk_remote_script(), env)
    log("[run] OTA 流程结束")


def command_small_deploy(args: argparse.Namespace) -> None:
    target = make_target(args)
    ensure_tools()
    package = resolve_small_package(args.package)
    remote_dir = resolve_remote_dir(target, args.remote_dir)
    log(f"[small-deploy] 目标: {target.label}")
    log(f"[small-deploy] 远程目录: {remote_dir}")
    remote_small_precheck(target, remote_dir, package)
    remote_stage = upload_small_package(target, package, remote_dir)
    env = {
        "REMOTE_STAGE": remote_stage,
        "SUDO_PASSWORD": target.password,
        "RUN_UPGRADE": "0" if args.prepare_only else "1",
    }
    run_remote_script(target, small_deploy_remote_script(), env)
    log("[small-deploy] 小包部署流程结束")


def resolve_package(value: str) -> Path:
    if value:
        path = Path(value).expanduser()
    else:
        path = Path()
    if not path or not path.is_file():
        die("未找到 OTA 升级包，请在界面中选择 *.tar.gz 或 *.zip")
    return path.resolve()


def resolve_small_package(value: str) -> Path:
    path = Path(value).expanduser() if value else Path()
    if not path.exists():
        die("未找到小包路径，请选择 .deb/.whl、包含小包的目录或小包压缩包")
    if not deb_deploy.is_small_package_path(path):
        die("小包路径必须是 .deb/.whl 文件、包含 .deb/.whl 的目录或小包压缩包")
    return path.resolve()


def resolve_tools(value: str) -> Path:
    if value:
        path = Path(value).expanduser()
    else:
        path = default_nx_tools() or Path()
    if not path or not path.is_file():
        die("未找到 NX OTA 工具包 ota_tools*.tbz2")
    return path.resolve()


def validate_local_inputs(target: OtaTarget, package: Path, tools: Path | None):
    return local_validation.validate_local_inputs(target, package, tools)


def make_target(args: argparse.Namespace) -> OtaTarget:
    base = TARGETS[args.target]
    return OtaTarget(
        key=base.key,
        label=base.label,
        family=base.family,
        host=args.host or base.host,
        user=args.user or base.user,
        password=args.password or base.password,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Remote Debug Platform OTA backend")
    parser.add_argument("command", choices=("device-info", "precheck", "run", "verify", "small-precheck", "small-deploy"))
    parser.add_argument("--target", choices=sorted(TARGETS), default="nx")
    parser.add_argument("-H", "--host", default="")
    parser.add_argument("-u", "--user", default="")
    parser.add_argument("-p", "--password", default="")
    parser.add_argument("-d", "--remote-dir", default="~/ota")
    parser.add_argument("--package", default="")
    parser.add_argument("--tools", default="")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--skip-mcu", action="store_true", help="NX ZIP OTA 时跳过随包 rtk_mcu 刷写，仅执行系统 OTA")
    parser.add_argument("--mcu-maintenance", action="store_true", help="临时停止 robot-launch.service 后读取 MCU 版本，结束后恢复")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "device-info":
            command_device_info(args)
        elif args.command == "verify":
            command_verify(args)
        elif args.command == "precheck":
            command_precheck(args)
        elif args.command == "small-precheck":
            command_small_precheck(args)
        elif args.command == "small-deploy":
            command_small_deploy(args)
        elif args.command == "run":
            command_run(args)
        else:
            parser.error("unknown command")
    except subprocess.CalledProcessError as exc:
        output = getattr(exc, "output", "")
        if output:
            print(output, end="" if output.endswith("\n") else "\n")
        die(f"命令执行失败，返回码 {exc.returncode}: {' '.join(map(str, exc.cmd))}", exc.returncode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
