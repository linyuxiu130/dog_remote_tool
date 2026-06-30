from __future__ import annotations

from dog_remote_tool.core.quoting import quote
from dog_remote_tool.modules.ota import remote_mcu_checks
from dog_remote_tool.modules.ota import remote_precheck_scripts


def device_info_script(remote_dir: str, target_key: str = "", *, mcu_maintenance: bool = False) -> str:
    maintenance_block = remote_mcu_checks.mcu_maintenance_block(mcu_maintenance)
    mcu_probe_block = remote_mcu_checks.mcu_probe_block(mcu_maintenance)
    mcu_helper_block = remote_mcu_checks.mcu_helper_block(mcu_maintenance)
    return r"""
set +e
REMOTE_DIR=__REMOTE_DIR__
TARGET_KEY=__TARGET_KEY__
MCU_MAINTENANCE=__MCU_MAINTENANCE__
SUDO_PASSWORD="${SUDO_PASSWORD:-}"
case "$REMOTE_DIR" in
  ~*) REMOTE_DIR="$HOME${REMOTE_DIR#\~}" ;;
esac
__MCU_HELPER_BLOCK__
echo "目标主机: $(hostname 2>/dev/null || true)"
echo "登录用户: $(whoami)"
__MCU_MAINTENANCE_BLOCK__
__MCU_PROBE_BLOCK__
if [ "$MCU_MAINTENANCE" = "1" ]; then
  exit 0
fi
if [ -r /opt/release/version.yaml ]; then
  awk -F: '/^[[:space:]]*version[[:space:]]*:/ {gsub(/["[:space:]]/, "", $2); if ($2) print "业务版本: "$2; exit}' /opt/release/version.yaml
  awk -F: '/^[[:space:]]*release_date[[:space:]]*:/ {gsub(/["[:space:]]/, "", $2); if ($2) print "发布日期: "$2; exit}' /opt/release/version.yaml
fi
if [ -r /etc/user_release_version ]; then
  sed -n '1p' /etc/user_release_version | awk '{print "用户版本: "$0}'
fi
if [ -r /etc/nv_tegra_release ]; then
  nv_line="$(head -n 1 /etc/nv_tegra_release)"
  nv_major="$(printf '%s\n' "$nv_line" | sed -n 's/^# \(R[0-9][0-9]*\).*/\1/p')"
  nv_revision="$(printf '%s\n' "$nv_line" | sed -n 's/.*REVISION: \([0-9.][0-9.]*\).*/\1/p')"
  if [ -n "$nv_major" ] && [ -n "$nv_revision" ]; then
    printf 'L4T版本: %s.%s\n' "$nv_major" "$nv_revision"
  else
    printf 'L4T版本: %s\n' "$nv_line"
  fi
fi
release_files="$(ls -1t /etc/release/*.yaml 2>/dev/null | grep -v '/rootfs_.*\.yaml$')"
if [ -n "$release_files" ]; then
  echo "$release_files" | while IFS= read -r path; do
    [ -n "$path" ] || continue
    printf '设备版本: %s\n' "$(basename "$path" .yaml)"
  done
else
  echo "设备版本: 未找到 /etc/release/*.yaml"
fi
if [ "$TARGET_KEY" = "xg_l1_point_nx" ] || [ "$TARGET_KEY" = "xg_l1_wheel_nx" ] || [ "$TARGET_KEY" = "zgnx" ]; then
  if [ -d /ota ]; then
    df -hP /ota 2>/dev/null | awk 'NR==2 {printf "升级空间: /ota %s\n", $4}'
  elif [ -d "$REMOTE_DIR" ]; then
    df -hP "$REMOTE_DIR" 2>/dev/null | awk 'NR==2 {printf "升级空间: remote %s\n", $4}'
  else
    printf '升级空间: 路径不存在\n'
  fi
elif [ -d /userdata/update ]; then
  df -hP /userdata/update 2>/dev/null | awk 'NR==2 {printf "升级空间: /userdata/update %s\n", $4}'
elif [ -d "$REMOTE_DIR" ]; then
  df -hP "$REMOTE_DIR" 2>/dev/null | awk 'NR==2 {printf "升级空间: remote %s\n", $4}'
else
  printf '升级空间: 路径不存在\n'
fi
exit 0
""".replace("__REMOTE_DIR__", quote(remote_dir)).replace("__TARGET_KEY__", quote(target_key)).replace(
        "__MCU_MAINTENANCE__", "1" if mcu_maintenance else "0"
    ).replace("__MCU_HELPER_BLOCK__", mcu_helper_block).replace("__MCU_MAINTENANCE_BLOCK__", maintenance_block).replace(
        "__MCU_PROBE_BLOCK__", mcu_probe_block
    )


def nx_precheck_script(
    remote_dir: str,
    package_name: str,
    package_is_zip: bool,
    package_size: int,
    payload_size: int,
    system_archive_size: int,
    tools_size: int,
    zip_extract_size: int,
) -> str:
    return remote_precheck_scripts.nx_precheck_script(
        remote_dir,
        package_name,
        package_is_zip,
        package_size,
        payload_size,
        system_archive_size,
        tools_size,
        zip_extract_size,
    )


def rk_precheck_script(remote_dir: str, package_name: str, package_size: int, img_path: str, img_size: int) -> str:
    return remote_precheck_scripts.rk_precheck_script(remote_dir, package_name, package_size, img_path, img_size)
