from dog_remote_tool.core.profiles import get_product
from dog_remote_tool.modules.remote_access import wifi as remote_wifi


def test_parse_scan_output_deduplicates_ssids():
    output = "\n".join(
        [
            "noise",
            "SSID=ZSXC-SH\tSIGNAL=-35",
            "SSID=ZSXC-SH\tSIGNAL=-60",
            "SSID=Lab\tSIGNAL=-70",
            "SSID=\tSIGNAL=-80",
        ]
    )

    networks = remote_wifi.parse_scan_output(output)

    assert networks == [
        remote_wifi.WifiNetwork("ZSXC-SH", "-35"),
        remote_wifi.WifiNetwork("Lab", "-70"),
    ]


def test_parse_scan_output_decodes_clean_names_and_keeps_strongest_signal():
    output = "\n".join(
        [
            "SSID_B64=5Lit5paHV2ktRmk=\tSIGNAL=-45",
            "SSID_B64=5Lit5paHV2ktRmk=\tSIGNAL=-70",
            "SSID=\\xE5\\xAE\\x9E\\xE9\\xAA\\x8CWiFi\tSIGNAL=-30",
            "SSID_B64=//4=\tSIGNAL=-20",
            "SSID=\\x82\\x84\\x8b\tSIGNAL=-10",
        ]
    )

    networks = remote_wifi.parse_scan_output(output)

    assert networks == [
        remote_wifi.WifiNetwork("实验WiFi", "-30"),
        remote_wifi.WifiNetwork("中文Wi-Fi", "-45"),
    ]


def test_parse_status_output_reads_key_values():
    values = remote_wifi.parse_status_output(
        "STATE=connected\nSSID=ZSXC-SH\nIP=192.168.112.144\nPUBLIC_TCP=ok\n"
    )

    assert values["STATE"] == "connected"
    assert values["SSID"] == "ZSXC-SH"
    assert values["PUBLIC_TCP"] == "ok"


def test_wifi_commands_auto_detect_interface():
    profile = get_product("xg3588")

    scan = remote_wifi.scan_command(profile)
    status = remote_wifi.status_command(profile)
    connect = remote_wifi.connect_command(profile, "Lab", "pw")

    assert "REQUESTED_IFACE=auto" in scan
    assert "for candidate in wlan1 wlan0" in scan
    assert "WiFi扫描网卡" in scan
    assert "WiFi扫描失败" in scan
    assert "sudo_run() {" in scan
    assert "command -v sudo" not in scan
    assert "REQUESTED_IFACE=auto" in status
    assert "REQUESTED_IFACE=auto" in connect
    assert "sudo_run() {" in connect
    assert "command -v sudo" not in connect
