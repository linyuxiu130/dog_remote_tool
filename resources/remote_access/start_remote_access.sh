#!/bin/bash
# 通过 SSID 向服务器申请配置并启动 remote_access (frpc)

set -e

SERVER="https://47.102.113.200:7501"
STREAM_ID=""
LOCAL_USER=""
USER_SUPPLIED_SSID=0
MODULE_SSH_HOST="${MODULE_SSH_HOST:-${DOG_REMOTE_MODULE_SSH_HOST:-}}"
MODULE_SSH_USER="${MODULE_SSH_USER:-${DOG_REMOTE_MODULE_SSH_USER:-}}"
MODULE_SSH_PASSWORD="${MODULE_SSH_PASSWORD:-${DOG_REMOTE_MODULE_SSH_PASSWORD:-}}"

log_info() {
    printf '[INFO] %s\n' "$*"
}

log_warn() {
    printf '[WARN] %s\n' "$*"
}

log_error() {
    printf '[ERROR] %s\n' "$*"
}

normalize_server() {
    case "$1" in
        http://*|https://*) SERVER="$1" ;;
        *) SERVER="https://$1:7501" ;;
    esac
}

detect_release_name() {
    find /etc/release -maxdepth 1 -type f -name '*.yaml' -printf '%f\n' 2>/dev/null | sort | tail -1
}

is_029b_or_newer() {
    case "$1" in
        *0029*B.yaml|*003[0-9]*.yaml|*00[3-9][0-9]*.yaml) return 0 ;;
        *) return 1 ;;
    esac
}

# 解析命名参数
SKIP=0
for i in "$@"; do
    if [ "$SKIP" = "1" ]; then
        SKIP=0
        continue
    fi
    case "$i" in
        -h|--help)
            echo "用法: $0 [选项]"
            echo ""
            echo "选项:"
            echo "  --ssid <name>       设备 SSID (不传则自动检测)"
            echo "  --server-ip <IP>    服务器 IP 地址 (默认: 47.102.113.200)"
            echo "  --user <name>       SSH 用户名 (默认: 当前登录用户)"
            echo "  MODULE_SSH_HOST/USER/PASSWORD 可选配置 5G 模块 SSID 探测"
            echo "  -h, --help          显示帮助"
            exit 0 ;;
        --ssid) SKIP=1 ;;
        --ssid=*) STREAM_ID="${i#*=}"; USER_SUPPLIED_SSID=1 ;;
        --server-ip) SKIP=1 ;;
        --server-ip=*) normalize_server "${i#*=}" ;;
        --user) SKIP=1 ;;
        --user=*) LOCAL_USER="${i#*=}" ;;
    esac
done

# 从 --ssid / --server-ip / --user 提取值
for ((idx=1; idx<=$#; idx++)); do
    arg="${!idx}"
    NEXT=$((idx+1))
    [ "$NEXT" -le "$#" ] || continue
    case "$arg" in
        --ssid) STREAM_ID="${!NEXT}"; USER_SUPPLIED_SSID=1 ;;
        --server-ip) normalize_server "${!NEXT}" ;;
        --user) LOCAL_USER="${!NEXT}" ;;
    esac
done

# 0.2.9(B) 及以后版本可自动获取 SSID；传入 --ssid 时仅作为自动获取失败后的兜底。
MANUAL_STREAM_ID="$STREAM_ID"
AUTO_FIRST=0
RELEASE_NAME="$(detect_release_name)"
if is_029b_or_newer "$RELEASE_NAME"; then
    AUTO_FIRST=1
    log_info "版本识别：/etc/release/$RELEASE_NAME，使用 0.2.9(B)+ 自动 SSID 探测流程"
    if [ "$USER_SUPPLIED_SSID" = "1" ]; then
        log_info "当前版本优先自动探测 SSID，--ssid 仅作为兜底：$MANUAL_STREAM_ID"
        STREAM_ID=""
    fi
elif [ -n "$RELEASE_NAME" ]; then
    log_info "版本识别：/etc/release/$RELEASE_NAME，使用兼容 SSID 流程"
else
    log_warn "未找到 /etc/release/*.yaml，使用兼容 SSID 流程"
fi

# 获取 stream_id：传参或 0.2.9(B)+ 自动检测 > 本地 hostapd.conf > SSH 到 5G 模块 > 同目录下 wifi.conf
if [ -z "$STREAM_ID" ]; then
    if [ -f "/userdata/bak/system/hostapd.conf" ]; then
        STREAM_ID=$(awk -F'=' '/^ssid=/ {print $2; exit}' /userdata/bak/system/hostapd.conf | tr -d ' \n\r\t')
    fi

    if [ -z "$STREAM_ID" ]; then
        STREAM_ID=$(iwgetid -r wlan0 2>/dev/null | tr -d ' \n\r\t') || true
    fi

    if [ -z "$STREAM_ID" ]; then
        STREAM_ID=$(iw dev wlan0 info 2>/dev/null | awk '/ssid/ {print $2; exit}' | tr -d ' \n\r\t') || true
    fi

    if [ -z "$STREAM_ID" ]; then
        if [ -n "$MODULE_SSH_HOST" ] && [ -n "$MODULE_SSH_USER" ] && [ -n "$MODULE_SSH_PASSWORD" ]; then
            log_info "通过 5G 模块 SSH 探测 SSID"
            STREAM_ID=$(SSHPASS="$MODULE_SSH_PASSWORD" sshpass -e ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 \
                "$MODULE_SSH_USER@$MODULE_SSH_HOST" \
                "awk -F'=' '/^ssid=/ {print \$2; exit}' /userdata/bak/system/hostapd.conf" 2>/dev/null \
                | tr -d ' \n\r\t') || true
        else
            log_info "未配置 MODULE_SSH_HOST/USER/PASSWORD，跳过 5G 模块 SSH 探测"
        fi
    fi

    if [ -z "$STREAM_ID" ]; then
        SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
        WIFI_CONF="$SCRIPT_DIR/wifi.conf"
        if [ -f "$WIFI_CONF" ]; then
            AP_SSID=$(grep "^AP_SSID=" "$WIFI_CONF" | cut -d= -f2- | tr -d ' \n\r\t')
            AP_AUTO_PREFIX=$(grep "^AP_AUTO_PREFIX=" "$WIFI_CONF" | cut -d= -f2- | tr -d ' \n\r\t')
            if [ -n "$AP_SSID" ]; then
                if [ "$AP_AUTO_PREFIX" = "1" ]; then
                    STREAM_ID="ZG50G_${AP_SSID}"
                else
                    STREAM_ID="$AP_SSID"
                fi
                log_info "从 wifi.conf 读取 SSID：$STREAM_ID"
            fi
        fi
    fi

    if [ -z "$STREAM_ID" ] && [ "$AUTO_FIRST" = "1" ] && [ -n "$MANUAL_STREAM_ID" ]; then
        STREAM_ID="$MANUAL_STREAM_ID"
        log_warn "自动 SSID 探测失败，使用 --ssid 兜底：$STREAM_ID"
    fi

    if [ -z "$STREAM_ID" ]; then
        log_error "无法获取 stream_id"
        echo "用法: $0 --ssid <SSID> [选项]"
        echo "  $0 --server-ip <IP> --ssid <SSID> --user <name>"
        echo "或者在脚本同目录下创建 wifi.conf 文件，设置 AP_SSID 和 AP_AUTO_PREFIX 来指定 SSID"
        exit 1
    fi
fi

log_info "stream_id：$STREAM_ID"

# 获取本地用户名（用于飞书通知中的 SSH 连接命令）
LOCAL_USER="${LOCAL_USER:-$(whoami)}"
log_info "本地 SSH 用户：$LOCAL_USER"

# 1. 注册（确保设备在服务器上有分配，上报用户名）
log_info "注册公网访问会话"
REGISTER_RESP=$(curl -sk -X POST "$SERVER/register" \
  -H "Content-Type: application/json" \
  -d "{\"ssid\":\"$STREAM_ID\",\"username\":\"$LOCAL_USER\"}")

SUCCESS=$(echo "$REGISTER_RESP" | grep -o '"success":true')
if [ -z "$SUCCESS" ]; then
    log_error "公网访问注册失败：$REGISTER_RESP"
    exit 1
fi
log_info "公网访问注册完成"

# 2. 下载配置文件
TMP_CONFIG=$(mktemp /tmp/frpc_XXXXXX.toml)
log_info "下载 remote_access 配置"
curl -sk "$SERVER/config/$STREAM_ID" -o "$TMP_CONFIG"

if [ ! -s "$TMP_CONFIG" ]; then
    log_error "remote_access 配置下载失败"
    rm -f "$TMP_CONFIG"
    exit 1
fi
log_info "配置文件已写入：$TMP_CONFIG"

# 3. 下载 CA 证书（frpc TLS 验证服务端用）
CA_CERT="/tmp/access_service.crt"
log_info "下载 TLS CA 证书"
curl -sk "$SERVER/ca_cert" -o "$CA_CERT"
if [ ! -s "$CA_CERT" ]; then
    log_warn "TLS CA 证书下载失败，将按非加密链路启动"
else
    log_info "TLS CA 证书已写入：$CA_CERT"
    # 修正配置中的 CA 证书路径为绝对路径
    sed -i "s|trustedCaFile = \".*\"|trustedCaFile = \"$CA_CERT\"|" "$TMP_CONFIG"
fi

# 4. 捕获退出信号，清理临时文件
cleanup() {
    log_info "清理 remote_access 临时文件"
    rm -f "$TMP_CONFIG" "$CA_CERT"
}
trap cleanup EXIT INT TERM

# 5. 启动 remote_access（frpc）
log_info "启动 remote_access 客户端"
if command -v stdbuf >/dev/null 2>&1; then
    stdbuf -oL -eL remote_access -c "$TMP_CONFIG"
else
    remote_access -c "$TMP_CONFIG"
fi

# 如果 remote_access 退出，脚本也会退出（trap 会自动清理）
