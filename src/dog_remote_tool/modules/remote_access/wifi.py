from __future__ import annotations

import base64
import re
from dataclasses import dataclass

from dog_remote_tool.core.parsers import parse_key_value_fields, parse_key_values
from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import quote, ssh_command, sudo_run_shell
from dog_remote_tool.modules.remote_access import public as _public


DEFAULT_WIFI_IFACE = "auto"
PUBLIC_ACCESS_HOST = _public.PUBLIC_SERVER
PUBLIC_ACCESS_PORT = _public.PUBLIC_PORT_MANAGER_PORT


@dataclass(frozen=True)
class WifiNetwork:
    ssid: str
    signal: str = ""


def supports_3588_wifi(profile: ProductProfile) -> bool:
    return profile.platform == "RK3588"


def _signal_value(signal: str) -> float:
    try:
        return float(signal)
    except ValueError:
        return -999.0


def _decode_ssid(raw: str) -> str:
    value = raw.strip()
    if not value:
        return ""
    if "\\x" in value:
        try:
            hex_bytes = re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), value)
            value = hex_bytes.encode("latin1").decode("utf-8")
        except (UnicodeDecodeError, UnicodeEncodeError, ValueError):
            return ""
    value = value.replace("\x00", "").strip()
    value = "".join(ch for ch in value if ch == "\t" or ch == " " or not ch.isspace() or ch in "\u4e00-\u9fff")
    value = "".join(ch for ch in value if ch.isprintable()).strip()
    if "\ufffd" in value:
        return ""
    return value


def parse_scan_output(output: str) -> list[WifiNetwork]:
    by_ssid: dict[str, WifiNetwork] = {}
    for line in output.splitlines():
        if not line.startswith(("SSID=", "SSID_B64=")):
            continue
        parts = parse_key_value_fields(line, separator="\t")
        ssid_raw = parts.get("SSID", "").strip()
        if "SSID_B64" in parts:
            try:
                ssid_raw = base64.b64decode(parts["SSID_B64"], validate=True).decode("utf-8", errors="replace")
            except (ValueError, UnicodeDecodeError):
                ssid_raw = ""
        ssid = _decode_ssid(ssid_raw)
        if not ssid:
            continue
        signal = parts.get("SIGNAL", "").strip()
        current = by_ssid.get(ssid)
        if current is None or _signal_value(signal) > _signal_value(current.signal):
            by_ssid[ssid] = WifiNetwork(ssid=ssid, signal=signal)
    return sorted(by_ssid.values(), key=lambda item: (-_signal_value(item.signal), item.ssid.lower()))


parse_status_output = parse_key_values


def _iface_select_shell(iface: str) -> str:
    return (
        f"REQUESTED_IFACE={quote(iface)}; "
        "if [ \"$REQUESTED_IFACE\" = auto ] || [ -z \"$REQUESTED_IFACE\" ]; then "
        "IFACE=; "
        "for candidate in wlan1 wlan0; do iw dev \"$candidate\" info >/dev/null 2>&1 && { IFACE=\"$candidate\"; break; }; done; "
        "if [ -z \"$IFACE\" ]; then IFACE=$(iw dev 2>/dev/null | awk '/Interface/ {print $2; exit}'); fi; "
        "else IFACE=\"$REQUESTED_IFACE\"; fi; "
        "[ -n \"$IFACE\" ] || { printf '[ERROR] 未发现无线网卡\\n'; exit 1; }; "
        "iw dev \"$IFACE\" info >/dev/null 2>&1 || { printf '[ERROR] 无线网卡不存在: %s\\n' \"$IFACE\"; exit 1; }; "
    )


def scan_command(profile: ProductProfile, iface: str = DEFAULT_WIFI_IFACE) -> str:
    parser = (
        "import base64,re,sys\n"
        "signal=''\n"
        "seen=set()\n"
        "for raw in sys.stdin.buffer:\n"
        "    line=raw.rstrip(b'\\r\\n')\n"
        "    m=re.search(rb'\\bsignal:\\s*(-?\\d+(?:\\.\\d+)?)', line)\n"
        "    if m:\n"
        "        signal=m.group(1).decode('ascii', 'ignore')\n"
        "    stripped=line.lstrip()\n"
        "    if stripped.startswith(b'SSID:'):\n"
        "        ssid=stripped.split(b':', 1)[1].strip()\n"
        "        if ssid and ssid not in seen:\n"
        "            seen.add(ssid)\n"
        "            print('SSID_B64=%s\\tSIGNAL=%s' % (base64.b64encode(ssid).decode('ascii'), signal))\n"
    )
    remote = (
        "set -e; "
        + sudo_run_shell(fallback_without_sudo=False)
        + _iface_select_shell(iface)
        + "printf '[INFO] WiFi扫描网卡: %s\\n' \"$IFACE\"; "
        "sudo_run ip link set \"$IFACE\" up >/dev/null 2>&1 || true; "
        "SCAN_OUTPUT=$(printf '%s\\n' \"$DOG_REMOTE_SUDO_PASS\" | timeout 18 sudo -S -p '' iw dev \"$IFACE\" scan 2>&1) || "
        "{ code=$?; printf '[ERROR] WiFi扫描失败(%s): %s\\n' \"$code\" \"$(printf '%s' \"$SCAN_OUTPUT\" | tail -n 1)\"; exit \"$code\"; }; "
        f"printf '%s\\n' \"$SCAN_OUTPUT\" | python3 -c {quote(parser)}"
    )
    return ssh_command(profile, remote)


def status_command(profile: ProductProfile, iface: str = DEFAULT_WIFI_IFACE) -> str:
    remote = (
        _iface_select_shell(iface)
        + "SSID=$(iw dev \"$IFACE\" link 2>/dev/null | awk -F': ' '/SSID:/ {print $2; exit}'); "
        "IP=$(ip -4 -o addr show dev \"$IFACE\" 2>/dev/null | awk '{split($4,a,\"/\"); print a[1]; exit}'); "
        "GW=$(ip route show default dev \"$IFACE\" 2>/dev/null | awk '/default/ {print $3; exit}'); "
        "TCP=fail; "
        f"timeout 4 bash -lc {quote(f'</dev/tcp/{PUBLIC_ACCESS_HOST}/{PUBLIC_ACCESS_PORT}')} >/dev/null 2>&1 && TCP=ok || true; "
        "if [ -n \"$SSID\" ]; then STATE=connected; else STATE=disconnected; fi; "
        "printf 'STATE=%s\\nSSID=%s\\nIP=%s\\nGATEWAY=%s\\nPUBLIC_TCP=%s\\n' \"$STATE\" \"$SSID\" \"$IP\" \"$GW\" \"$TCP\""
    )
    return ssh_command(profile, remote)


def connect_command(profile: ProductProfile, ssid: str, password: str, iface: str = DEFAULT_WIFI_IFACE) -> str:
    remote = (
        "set -e; "
        + sudo_run_shell(fallback_without_sudo=False)
        + _iface_select_shell(iface)
        + f"SSID={quote(ssid)}; "
        f"WIFI_PASS={quote(password)}; "
        "CONF=/tmp/dog_remote_wifi_${IFACE}.conf; "
        "printf '[准备] 使用 %s 连接 WiFi\\n' \"$IFACE\"; "
        "sudo_run ip link set \"$IFACE\" up; "
        "sudo_run wpa_cli -i \"$IFACE\" terminate >/dev/null 2>&1 || true; "
        "sleep 1; "
        "wpa_passphrase \"$SSID\" \"$WIFI_PASS\" > \"$CONF\"; "
        "chmod 600 \"$CONF\"; "
        "printf '[连接] SSID=%s\\n' \"$SSID\"; "
        "sudo_run wpa_supplicant -B -i \"$IFACE\" -c \"$CONF\"; "
        "for _ in $(seq 1 12); do "
        "current=$(iw dev \"$IFACE\" link 2>/dev/null | awk -F': ' '/SSID:/ {print $2; exit}'); "
        "[ \"$current\" = \"$SSID\" ] && break; "
        "sleep 1; "
        "done; "
        "current=$(iw dev \"$IFACE\" link 2>/dev/null | awk -F': ' '/SSID:/ {print $2; exit}'); "
        "if [ \"$current\" != \"$SSID\" ]; then printf '[失败] 未连接到目标 SSID\\n'; iw dev \"$IFACE\" link || true; exit 1; fi; "
        "printf '[DHCP] 获取地址\\n'; "
        "sudo_run dhclient -r \"$IFACE\" >/dev/null 2>&1 || true; "
        "sudo_run dhclient -v \"$IFACE\"; "
        "sudo_run resolvectl dns \"$IFACE\" 8.8.8.8 1.1.1.1 >/dev/null 2>&1 || true; "
        "sudo_run resolvectl domain \"$IFACE\" '~.' >/dev/null 2>&1 || true; "
        "IP=$(ip -4 -o addr show dev \"$IFACE\" | awk '{split($4,a,\"/\"); print a[1]; exit}'); "
        "GW=$(ip route show default dev \"$IFACE\" | awk '/default/ {print $3; exit}'); "
        f"timeout 5 bash -lc {quote(f'</dev/tcp/{PUBLIC_ACCESS_HOST}/{PUBLIC_ACCESS_PORT}')} >/dev/null 2>&1 && TCP=ok || TCP=fail; "
        "printf '[完成] WiFi 已连接\\n'; "
        "printf 'STATE=connected\\nSSID=%s\\nIP=%s\\nGATEWAY=%s\\nPUBLIC_TCP=%s\\n' \"$SSID\" \"$IP\" \"$GW\" \"$TCP\""
    )
    return ssh_command(profile, remote)
