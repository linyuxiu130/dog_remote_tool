from __future__ import annotations

from typing import Protocol

from dog_remote_tool.core.shell import quote


class S100RemoteTarget(Protocol):
    key: str
    host: str
    user: str
    password: str


def s100_remote_setup_lines(target: S100RemoteTarget) -> list[str]:
    if target.key == "zg_surround_s100":
        default_host = "192.168.168.100"
        default_candidates = "$S100_REMOTE_HOST 192.168.168.100"
    else:
        default_host = target.host
        default_candidates = "$S100_REMOTE_HOST"
    return [
        f"S100_REMOTE_HOST={quote(default_host)}",
        f"S100_REMOTE_EXPECTED_HOST={quote(target.host)}",
        f"S100_REMOTE_USER={quote(target.user)}",
        f"S100_REMOTE_PASSWORD={quote(target.password)}",
        'S100_GATEWAY_HOST="${DOG_REMOTE_TOOL_S100_GATEWAY:-192.168.234.1}"',
        'S100_GATEWAY_USER="${DOG_REMOTE_TOOL_S100_GATEWAY_USER:-robot}"',
        'S100_GATEWAY_PASSWORD="${DOG_REMOTE_TOOL_S100_GATEWAY_PASSWORD:-bot}"',
        'if [ -n "${DOG_REMOTE_TOOL_S100_REMOTE_HOST:-}" ]; then S100_REMOTE_HOST="$DOG_REMOTE_TOOL_S100_REMOTE_HOST"; fi',
        'S100_REMOTE_HOST_CANDIDATES="${DOG_REMOTE_TOOL_S100_REMOTE_HOSTS:-}"',
        'if [ -z "$S100_REMOTE_HOST_CANDIDATES" ]; then',
        '  if [ -n "${DOG_REMOTE_TOOL_S100_REMOTE_HOST:-}" ]; then',
        '    S100_REMOTE_HOST_CANDIDATES="$S100_REMOTE_HOST"',
        "  else",
        f'    S100_REMOTE_HOST_CANDIDATES="{default_candidates}"',
        "  fi",
        "fi",
    ]


def s100_password_ssh_options(connect_timeout: int) -> str:
    return (
        "-o StrictHostKeyChecking=no "
        "-o UserKnownHostsFile=/dev/null "
        f"-o ConnectTimeout={connect_timeout} "
        "-o PreferredAuthentications=password "
        "-o PubkeyAuthentication=no"
    )


def s100_remote_probe_lines() -> list[str]:
    return [
        's100_route_target_via_gateway() {',
        '  local target_ip="$1"',
        '  local subnet="$2"',
        '  local gateway="${S100_GATEWAY_HOST:-192.168.234.1}"',
        '  command -v ip >/dev/null 2>&1 || return 0',
        '  local route_info=""',
        '  route_info="$(ip route get "$target_ip" 2>&1 || true)"',
        '  if printf "%s\\n" "$route_info" | grep -q "via $gateway"; then',
        "    return 0",
        "  fi",
        '  echo "[WARN] $target_ip 当前路由不是经 $gateway: ${route_info:-未返回}"',
        '  local gateway_route=""',
        '  local gateway_dev=""',
        '  gateway_route="$(ip route get "$gateway" 2>&1 || true)"',
        '  gateway_dev="$(printf "%s\\n" "$gateway_route" | awk \'{ for (i=1; i<=NF; i++) if ($i=="dev") { print $(i+1); exit } }\')"',
        '  if [ -z "$gateway_dev" ]; then',
        '    echo "[WARN] 无法找到到 $gateway 的网卡，不能自动修复 $subnet 路由。"',
        '    echo "[flash] 可手动执行: sudo ip route replace $subnet via $gateway"',
        "    return 1",
        "  fi",
        '  if command -v sudo >/dev/null 2>&1; then',
        '    sudo -n ip route replace "$subnet" via "$gateway" dev "$gateway_dev" >/dev/null 2>&1 || true',
        '    if ! ip rule 2>/dev/null | grep -q "to $subnet lookup main"; then',
        '      sudo -n ip rule add pref 100 to "$subnet" lookup main >/dev/null 2>&1 || true',
        "    fi",
        "  fi",
        '  route_info="$(ip route get "$target_ip" 2>&1 || true)"',
        '  if printf "%s\\n" "$route_info" | grep -q "via $gateway"; then',
        '    echo "[flash] 已修正 $subnet 路由: $route_info"',
        "    return 0",
        "  fi",
        '  echo "[WARN] 未能自动修正 $subnet 路由；有线默认路由、VPN 或策略路由可能仍在抢占。"',
        '  if command -v sudo >/dev/null 2>&1 && ! sudo -n true >/dev/null 2>&1; then',
        '    echo "[WARN] 当前用户没有免密 sudo，脚本不能自动修改系统路由。"',
        "  fi",
        '  echo "[flash] 建议手动执行: sudo ip route replace $subnet via $gateway dev $gateway_dev"',
        '  echo "[flash] 如仍走 VPN，再执行: sudo ip rule add pref 100 to $subnet lookup main"',
        "  return 1",
        "}",
        's100_probe_gateway_to_targets() {',
        '  [ -n "${S100_GATEWAY_HOST:-}" ] || return 0',
        '  [ -n "${S100_GATEWAY_USER:-}" ] || return 0',
        '  [ -n "${S100_GATEWAY_PASSWORD:-}" ] || return 0',
        '  command -v sshpass >/dev/null 2>&1 || return 0',
        '  local targets=""',
        '  local candidate=""',
        '  local seen=" "',
        '  for candidate in $S100_REMOTE_HOST_CANDIDATES; do',
        '    case "$seen" in *" $candidate "*) continue ;; esac',
        '    seen="$seen$candidate "',
        '    case "$candidate" in 192.168.168.*) targets="$targets $candidate" ;; esac',
        "  done",
        '  [ -n "$targets" ] || return 0',
        '  local remote_cmd="for ip in $targets; do if ping -c 1 -W 1 \\"\\$ip\\" >/dev/null 2>&1; then echo GATEWAY_REACHABLE:\\$ip; else echo GATEWAY_UNREACHABLE:\\$ip; fi; done"',
        '  local out=""',
        f'  if out="$(timeout 8 sshpass -p "$S100_GATEWAY_PASSWORD" ssh {s100_password_ssh_options(3)} "$S100_GATEWAY_USER@$S100_GATEWAY_HOST" "$remote_cmd" 2>/dev/null)"; then',
        '    printf "%s\\n" "$out" | sed "s/^/[flash] 网关检查: /"',
        '    if printf "%s\\n" "$out" | grep -q "GATEWAY_REACHABLE:"; then',
        "      return 0",
        "    fi",
        '    echo "[WARN] $S100_GATEWAY_HOST 网关也无法连到 S100；这不是本机路由单独能解决的问题。"',
        '    echo "[flash] 请确认 S100 已上电并处于系统态，或手动按 BOOT/RECOVERY 进入 3652:6610/fastboot。" ',
        "  else",
        '    echo "[WARN] 无法通过 SSH 登录网关 $S100_GATEWAY_USER@$S100_GATEWAY_HOST 做 S100 内网检查。"',
        "  fi",
        "  return 0",
        "}",
        's100_prepare_remote_routes() {',
        '  case " $S100_REMOTE_HOST_CANDIDATES " in',
        '    *" 192.168.168."*) s100_route_target_via_gateway "192.168.168.100" "192.168.168.0/24" || true ;;',
        "  esac",
        '  s100_probe_gateway_to_targets',
        "}",
        's100_remote_candidate_matches_target() {',
        '  local candidate="$1"',
        '  local output="$2"',
        '  if [ "$candidate" = "$S100_REMOTE_EXPECTED_HOST" ] || [ -z "$S100_REMOTE_EXPECTED_HOST" ]; then',
        "    return 0",
        "  fi",
        '  if printf "%s\\n" "$output" | grep -Fq "$S100_REMOTE_EXPECTED_HOST"; then',
        "    return 0",
        "  fi",
        '  echo "[WARN] SSH $candidate 可登录，但远端网卡未显示目标地址 $S100_REMOTE_EXPECTED_HOST，跳过以避免刷错设备。"',
        "  return 1",
        "}",
        's100_select_reachable_remote_host() {',
        '  [ -n "${S100_REMOTE_HOST_CANDIDATES:-}" ] || return 1',
        '  [ -n "${S100_REMOTE_USER:-}" ] || return 1',
        '  [ -n "${S100_REMOTE_PASSWORD:-}" ] || return 1',
        '  command -v sshpass >/dev/null 2>&1 || return 1',
        '  s100_prepare_remote_routes',
        '  local candidate=""',
        '  local seen=" "',
        '  local out=""',
        '  local probe_timeout="${DOG_REMOTE_TOOL_S100_SSH_PROBE_TIMEOUT:-5}"',
        '  for candidate in $S100_REMOTE_HOST_CANDIDATES; do',
        '    case "$seen" in *" $candidate "*) continue ;; esac',
        '    seen="$seen$candidate "',
        '    [ -n "$candidate" ] || continue',
        f'    if out="$(timeout "$probe_timeout" sshpass -p "$S100_REMOTE_PASSWORD" ssh {s100_password_ssh_options(2)} "$S100_REMOTE_USER@$candidate" "hostname; ip -br addr" 2>/dev/null)"; then',
        '      if s100_remote_candidate_matches_target "$candidate" "$out"; then',
        '        S100_REMOTE_HOST="$candidate"',
        '        S100_REMOTE_PROBE_OUTPUT="$out"',
        '        echo "[flash] S100 SSH 可达入口: $S100_REMOTE_USER@$S100_REMOTE_HOST"',
        '        if [ -n "$S100_REMOTE_EXPECTED_HOST" ] && [ "$S100_REMOTE_HOST" != "$S100_REMOTE_EXPECTED_HOST" ]; then',
        '          echo "[flash] 目标地址 $S100_REMOTE_EXPECTED_HOST 不直通，改用同一 S100 的可达地址 $S100_REMOTE_HOST。"',
        "        fi",
        "        return 0",
        "      fi",
        "    else",
        '      echo "[flash] S100 SSH 探测不可用: $S100_REMOTE_USER@$candidate"',
        "    fi",
        "  done",
        "  return 1",
        "}",
    ]
