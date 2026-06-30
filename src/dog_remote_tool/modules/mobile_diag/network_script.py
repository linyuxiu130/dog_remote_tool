from __future__ import annotations


DIAG_SCRIPT = r'''#!/usr/bin/env bash

YELLOW='\033[1;33m'
NC='\033[0m'

section() {
    echo ""
    echo -e "${YELLOW}$1${NC}"
}

latest_log() {
    sudo journalctl -u quectel-cm.service -n 120 --no-pager 2>/dev/null | grep "$1" | tail -"${2:-1}" || true
}

echo "========================================"
echo "  4G/5G 上网模块测试诊断"
echo "========================================"

if ! (systemctl cat quectel-cm.service >/dev/null 2>&1 || \
      [ -f /etc/systemd/system/quectel-cm.service ] || \
      [ -f /lib/systemd/system/quectel-cm.service ]); then
    echo "[WARN] 当前设备未安装 quectel-cm.service。"
    echo "[WARN] 这通常表示当前选择的设备不是带 4G/5G 模块的 3588 端，或该镜像未部署拨号服务。"
    exit 0
fi

section "[第1步] 服务状态"
STATUS=$(systemctl is-active quectel-cm.service 2>/dev/null || true)
ENABLED=$(systemctl is-enabled quectel-cm.service 2>/dev/null || true)
echo "active=${STATUS:-unknown}"
echo "enabled=${ENABLED:-unknown}"

section "[第2步] 获取并分析4G/5G模块状态"
COPS_LOG=$(latest_log 'AT< +COPS:' 1)
QNET_LOG=$(latest_log 'AT< +QNETDEVCTL:' 1)
CGACT_LOG=$(latest_log 'AT< +CGACT:' 2)
CELL_LOG=$(latest_log 'AT< +QENG: "servingcell"' 1)

section "----- 运营商注册状态 (AT+COPS) -----"
if [ -n "$COPS_LOG" ]; then
    echo "$COPS_LOG"
    if [[ "$COPS_LOG" =~ \+COPS:\ ([0-9]),([0-9]),\"([0-9]+)\",([0-9]+) ]]; then
        REG_STATE="${BASH_REMATCH[1]}"
        OPERATOR="${BASH_REMATCH[3]}"
        NET_MODE="${BASH_REMATCH[4]}"
        case "$REG_STATE" in
            0) echo "注册状态: 已注册" ;;
            1) echo "注册状态: 未注册，正在搜索" ;;
            2) echo "注册状态: 未注册" ;;
            3) echo "注册状态: 注册被拒绝" ;;
            5) echo "注册状态: 已注册（漫游）" ;;
            *) echo "注册状态: $REG_STATE" ;;
        esac
        case "$OPERATOR" in
            46000|46002|46007|46008|46004) echo "运营商: 中国移动 ($OPERATOR)" ;;
            46001|46006|46009) echo "运营商: 中国联通 ($OPERATOR)" ;;
            46003|46005|46011) echo "运营商: 中国电信 ($OPERATOR)" ;;
            *) echo "运营商代码: $OPERATOR" ;;
        esac
        case "$NET_MODE" in
            7) echo "网络制式: 4G LTE" ;;
            11) echo "网络制式: 5G NR" ;;
            *) echo "网络制式代码: $NET_MODE" ;;
        esac
    else
        echo "无法解析运营商信息"
    fi
else
    echo "未获取到运营商注册信息"
fi

section "----- 数据业务状态 (AT+QNETDEVCTL) -----"
if [ -n "$QNET_LOG" ]; then
    echo "$QNET_LOG"
    if [[ "$QNET_LOG" =~ \+QNETDEVCTL:\ ([0-9]),([0-9]),([0-9]),([0-9]) ]]; then
        [ "${BASH_REMATCH[1]}" = "1" ] && echo "数据业务开关: 已开启" || echo "数据业务开关: 未开启 [异常]"
        [ "${BASH_REMATCH[2]}" = "1" ] && echo "IPv4能力: 已协商" || echo "IPv4能力: 未协商 [异常]"
        [ "${BASH_REMATCH[3]}" = "1" ] && echo "IPv6能力: 已协商" || echo "IPv6能力: 未协商"
        [ "${BASH_REMATCH[4]}" = "1" ] && echo "PDP上下文: 已激活" || echo "PDP上下文: 未激活 [异常]"
    fi
else
    echo "未获取到数据业务状态信息"
fi

section "----- PDP上下文激活状态 (AT+CGACT) -----"
if [ -n "$CGACT_LOG" ]; then
    echo "$CGACT_LOG"
else
    echo "未获取到PDP上下文状态信息"
fi

section "----- 服务小区详细信息 (AT+QENG) -----"
if [ -n "$CELL_LOG" ]; then
    echo "$CELL_LOG"
    if [[ "$CELL_LOG" =~ \"servingcell\",\"([^\"]+)\",\"([^\"]+)\" ]]; then
        echo "连接状态: ${BASH_REMATCH[1]}"
        echo "网络类型: ${BASH_REMATCH[2]}"
    fi
    if [[ "$CELL_LOG" =~ (-[0-9]{2,3}),(-[0-9]{1,2}),(-?[0-9]{1,2}),([0-9]{1,2}) ]]; then
        RSRP="${BASH_REMATCH[1]}"
        RSRQ="${BASH_REMATCH[2]}"
        SINR="${BASH_REMATCH[3]}"
        CQI="${BASH_REMATCH[4]}"
        echo "RSRP: $RSRP dBm"
        if [ "$RSRP" -ge -85 ]; then echo "  -> 极强 [优秀]"
        elif [ "$RSRP" -ge -95 ]; then echo "  -> 强 [良好]"
        elif [ "$RSRP" -ge -105 ]; then echo "  -> 中等 [一般]"
        elif [ "$RSRP" -ge -115 ]; then echo "  -> 弱 [较差]"
        else echo "  -> 极弱 [差]"; fi
        echo "RSRQ: $RSRQ dB"
        echo "SINR: $SINR dB"
        echo "CQI: $CQI"
    fi
else
    echo "未获取到服务小区信息"
fi

section "===== 诊断总结 ====="
ISSUE_FOUND=0
if [[ "$COPS_LOG" =~ \+COPS:\ ([0-9]) ]]; then
    REG="${BASH_REMATCH[1]}"
    if [ "$REG" != "0" ] && [ "$REG" != "5" ]; then
        echo "[异常] 未注册到网络"
        ISSUE_FOUND=1
    fi
fi
if [[ "$QNET_LOG" =~ \+QNETDEVCTL:\ ([0-9]),([0-9]),([0-9]),([0-9]) ]]; then
    if [ "${BASH_REMATCH[1]}" != "1" ]; then echo "[异常] 数据业务开关未开启"; ISSUE_FOUND=1; fi
    if [ "${BASH_REMATCH[2]}" != "1" ]; then echo "[异常] IPv4未协商成功"; ISSUE_FOUND=1; fi
    if [ "${BASH_REMATCH[4]}" != "1" ]; then echo "[异常] PDP上下文未激活"; ISSUE_FOUND=1; fi
fi
if [ "$ISSUE_FOUND" -eq 0 ] && [ -n "$COPS_LOG$QNET_LOG$CELL_LOG" ]; then
    echo "[正常] 未发现明确异常"
fi
echo ""
echo "===== 诊断完成 ====="
'''
