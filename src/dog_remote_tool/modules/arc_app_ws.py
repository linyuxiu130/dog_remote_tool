from __future__ import annotations


def stale_app_ws_cleanup_shell() -> str:
    return (
        "dog_remote_cleanup_stale_app_ws() { "
        "true; "
        "}; "
        "dog_remote_cleanup_stale_app_ws; "
    )


def common_arc_app_ws_python() -> str:
    return r'''
import base64
import json
import os
import signal
import socket
import struct
import subprocess
import sys
import time

HOST = "127.0.0.1"
PORT = 10010
APP_WS_BROKER_SOCKET = "/tmp/dog_remote_app_ws.sock"
APP_WS_BROKER_SCRIPT = "/tmp/dog_remote_app_ws_broker.py"
APP_WS_BROKER_LOG = "/tmp/dog_remote_app_ws_broker.log"
APP_WS_BROKER_VERSION = 2
NO_VALUE = object()

APP_WS_BROKER_SOURCE = r"""
import base64
import json
import os
import signal
import socket
import struct
import sys
import time

HOST = "127.0.0.1"
PORT = 10010
SOCKET_PATH = "/tmp/dog_remote_app_ws.sock"
CONNECT_RETRIES = 4
BROKER_VERSION = 2
IDLE_SECONDS = 45
LAST_ACTIVITY = time.monotonic()


def ws_send_text(sock, obj):
    payload = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    header = bytearray([0x81])
    size = len(payload)
    if size < 126:
        header.append(0x80 | size)
    elif size < 65536:
        header.append(0x80 | 126)
        header.extend(struct.pack("!H", size))
    else:
        header.append(0x80 | 127)
        header.extend(struct.pack("!Q", size))
    mask = os.urandom(4)
    header.extend(mask)
    sock.sendall(header + bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload)))


def ws_recv_text(sock):
    try:
        header = sock.recv(2)
    except socket.timeout:
        return None
    if not header:
        raise ConnectionError("app websocket closed")
    first, second = header
    opcode = first & 0x0F
    size = second & 0x7F
    if size == 126:
        size = struct.unpack("!H", sock.recv(2))[0]
    elif size == 127:
        size = struct.unpack("!Q", sock.recv(8))[0]
    mask = sock.recv(4) if second & 0x80 else b""
    payload = b""
    while len(payload) < size:
        chunk = sock.recv(size - len(payload))
        if not chunk:
            raise ConnectionError("app websocket closed")
        payload += chunk
    if mask:
        payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    if opcode != 1:
        return None
    return payload.decode("utf-8", errors="replace")


def parse_app_response(message):
    try:
        obj = json.loads(message)
    except Exception:
        return None
    if obj.get("head", {}).get("type") == "machine_body_operation_res":
        result = obj.get("data", {}).get("operation_result", {})
        if not isinstance(result, dict):
            return obj
        return {
            "kind": "machine_body_operation_res",
            "func": result.get("op"),
            "status": result.get("status"),
            "data": result,
            "error_code": None,
            "msg": result.get("ext_desc"),
        }
    if obj.get("head", {}).get("type") != "app_resp":
        return obj
    result = obj.get("data", {}).get("req_result", {})
    if not isinstance(result, dict):
        return obj
    app = result.get("AppResponse")
    if not isinstance(app, dict):
        app = result.get("AppReponseObjectData")
    if not isinstance(app, dict):
        app = result.get("AppResponseData")
    if not isinstance(app, dict):
        return {
            "kind": "app_resp",
            "func": result.get("req_func") or result.get("req_fun"),
            "status": result.get("status"),
            "data": result.get("data"),
            "error_code": result.get("error_code"),
            "msg": result.get("msg"),
        }
    return {
        "kind": "app_resp",
        "func": app.get("req_func"),
        "status": app.get("status"),
        "data": app.get("data"),
        "error_code": app.get("error_code"),
        "msg": app.get("msg"),
    }


def _tcp_10010_inodes():
    inodes = set()
    try:
        with open("/proc/net/tcp", "r", encoding="ascii", errors="ignore") as handle:
            lines = handle.readlines()[1:]
    except Exception:
        return inodes
    for line in lines:
        parts = line.split()
        if len(parts) < 10:
            continue
        remote = parts[2]
        state = parts[3]
        inode = parts[9]
        if state == "01" and remote.rsplit(":", 1)[-1].upper() == "271A":
            inodes.add(inode)
    return inodes


def _cmdline_for_pid(pid):
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as handle:
            return handle.read().replace(b"\0", b" ").decode("utf-8", errors="replace")
    except Exception:
        return ""


def _process_socket_inodes(pid):
    fd_dir = f"/proc/{pid}/fd"
    try:
        fds = os.listdir(fd_dir)
    except Exception:
        return set()
    inodes = set()
    for fd in fds:
        try:
            target = os.readlink(f"{fd_dir}/{fd}")
        except Exception:
            continue
        if target.startswith("socket:[") and target.endswith("]"):
            inodes.add(target[8:-1])
    return inodes


def _is_stale_tool_client(pid):
    if str(pid) == str(os.getpid()):
        return False
    cmdline = _cmdline_for_pid(pid)
    if APP_WS_BROKER_SCRIPT_NAME in cmdline:
        return False
    return cmdline.startswith("python3 ") or cmdline == "python3"


APP_WS_BROKER_SCRIPT_NAME = "dog_remote_app_ws_broker.py"


def cleanup_stale_app_ws_owner():
    inodes = _tcp_10010_inodes()
    if not inodes:
        return False
    stale_pids = []
    for pid in filter(str.isdigit, os.listdir("/proc")):
        if not _is_stale_tool_client(pid):
            continue
        if _process_socket_inodes(pid).intersection(inodes):
            stale_pids.append(pid)
    if not stale_pids:
        return False
    for pid in stale_pids:
        try:
            os.kill(int(pid), signal.SIGTERM)
        except Exception:
            pass
    time.sleep(0.15)
    for pid in stale_pids:
        try:
            os.kill(int(pid), 0)
        except Exception:
            continue
        try:
            os.kill(int(pid), signal.SIGKILL)
        except Exception:
            pass
    return True


APP_SOCK = None


def connect_app_ws():
    global APP_SOCK
    if APP_SOCK is not None:
        return APP_SOCK
    last_error = None
    for attempt in range(1, CONNECT_RETRIES + 1):
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET / HTTP/1.1\r\n"
            f"Host: {HOST}:{PORT}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        try:
            sock = socket.create_connection((HOST, PORT), timeout=5)
            sock.sendall(request.encode("ascii"))
            response = sock.recv(4096)
            if b"101" not in response.split(b"\r\n", 1)[0]:
                raise OSError(response.split(b"\r\n", 1)[0].decode("utf-8", errors="replace"))
            sock.settimeout(0.25)
            APP_SOCK = sock
            return APP_SOCK
        except OSError as exc:
            last_error = exc
            cleanup_stale_app_ws_owner()
            time.sleep(0.2 * attempt)
    raise ConnectionError(f"connect app websocket failed: {last_error}")


def reset_app_ws():
    global APP_SOCK
    if APP_SOCK is not None:
        try:
            APP_SOCK.close()
        except Exception:
            pass
    APP_SOCK = None


def perform_request(request_obj, expected_func, wait_seconds):
    messages = []
    last_error = None
    for attempt in range(2):
        try:
            sock = connect_app_ws()
            ws_send_text(sock, request_obj)
            deadline = time.time() + max(0.2, float(wait_seconds))
            while time.time() < deadline:
                message = ws_recv_text(sock)
                if not message:
                    continue
                if "app_sub_topic" in message and "odom_ground_truth" in message:
                    continue
                messages.append(message)
                parsed = parse_app_response(message)
                if isinstance(parsed, dict) and parsed.get("head", {}).get("type") == "alg_error_code_notify":
                    continue
                if isinstance(parsed, dict) and parsed.get("kind") == "app_resp":
                    if not expected_func or parsed.get("func") == expected_func:
                        return messages, ""
            return messages, ""
        except Exception as exc:
            last_error = str(exc)
            reset_app_ws()
            if attempt == 0:
                continue
    return messages, last_error or "request failed"


def response(handle, payload):
    handle.write((json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
    handle.flush()


def handle_client(conn):
    global LAST_ACTIVITY
    LAST_ACTIVITY = time.monotonic()
    with conn:
        handle = conn.makefile("rwb")
        line = handle.readline()
        if not line:
            return
        try:
            payload = json.loads(line.decode("utf-8"))
        except Exception as exc:
            response(handle, {"ok": False, "error": f"bad json: {exc}"})
            return
        op = payload.get("op")
        if op == "ping":
            response(handle, {"ok": True, "pong": True, "version": BROKER_VERSION})
            LAST_ACTIVITY = time.monotonic()
            return
        if op != "request":
            response(handle, {"ok": False, "error": f"unknown op: {op}"})
            LAST_ACTIVITY = time.monotonic()
            return
        messages, error = perform_request(
            payload.get("request") or {},
            str(payload.get("expected_func") or ""),
            float(payload.get("wait_seconds") or 3),
        )
        response(handle, {"ok": not bool(error), "messages": messages, "error": error})
        LAST_ACTIVITY = time.monotonic()


def main():
    global LAST_ACTIVITY
    try:
        os.unlink(SOCKET_PATH)
    except FileNotFoundError:
        pass
    except OSError:
        pass
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(SOCKET_PATH)
    os.chmod(SOCKET_PATH, 0o666)
    server.listen(8)
    server.settimeout(1.0)
    LAST_ACTIVITY = time.monotonic()
    while True:
        if time.monotonic() - LAST_ACTIVITY > IDLE_SECONDS:
            break
        try:
            conn, _addr = server.accept()
        except socket.timeout:
            continue
        handle_client(conn)
    reset_app_ws()
    try:
        server.close()
    except Exception:
        pass
    try:
        os.unlink(SOCKET_PATH)
    except Exception:
        pass


if __name__ == "__main__":
    main()
"""


def write_app_ws_broker_script():
    current = ""
    try:
        with open(APP_WS_BROKER_SCRIPT, "r", encoding="utf-8") as handle:
            current = handle.read()
    except Exception:
        pass
    if current != APP_WS_BROKER_SOURCE:
        with open(APP_WS_BROKER_SCRIPT, "w", encoding="utf-8") as handle:
            handle.write(APP_WS_BROKER_SOURCE)
        os.chmod(APP_WS_BROKER_SCRIPT, 0o755)


def ping_app_ws_broker():
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(0.6)
        sock.connect(APP_WS_BROKER_SOCKET)
        handle = sock.makefile("rwb")
        handle.write(b'{"op":"ping"}\n')
        handle.flush()
        line = handle.readline()
        sock.close()
        if not line:
            return False
        response = json.loads(line.decode("utf-8", errors="replace"))
        return bool(response.get("ok") and response.get("pong") and response.get("version") == APP_WS_BROKER_VERSION)
    except Exception:
        return False


def _argv_for_pid(pid):
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as handle:
            raw = handle.read()
    except Exception:
        return []
    return [part.decode("utf-8", errors="replace") for part in raw.split(b"\0") if part]


def _is_app_ws_broker_process(pid):
    if str(pid) == str(os.getpid()):
        return False
    argv = _argv_for_pid(pid)
    return APP_WS_BROKER_SCRIPT in argv[1:]


def cleanup_stale_app_ws_broker():
    stale_pids = [pid for pid in filter(str.isdigit, os.listdir("/proc")) if _is_app_ws_broker_process(pid)]
    if not stale_pids:
        return False
    for pid in stale_pids:
        try:
            os.kill(int(pid), signal.SIGTERM)
        except Exception:
            pass
    time.sleep(0.15)
    for pid in stale_pids:
        try:
            os.kill(int(pid), 0)
        except Exception:
            continue
        try:
            os.kill(int(pid), signal.SIGKILL)
        except Exception:
            pass
    return True


def start_app_ws_broker():
    write_app_ws_broker_script()
    cleanup_stale_app_ws_broker()
    try:
        if os.path.exists(APP_WS_BROKER_SOCKET):
            os.unlink(APP_WS_BROKER_SOCKET)
    except Exception:
        pass
    subprocess.Popen(
        ["python3", APP_WS_BROKER_SCRIPT],
        stdin=subprocess.DEVNULL,
        stdout=open(APP_WS_BROKER_LOG, "ab", buffering=0),
        stderr=subprocess.STDOUT,
        close_fds=True,
        start_new_session=True,
    )


def ensure_app_ws_broker():
    if ping_app_ws_broker():
        return True
    cleanup_stale_app_ws_broker()
    start_app_ws_broker()
    deadline = time.time() + 2.0
    while time.time() < deadline:
        if ping_app_ws_broker():
            return True
        time.sleep(0.1)
    return False


class AppWsBrokerClient:
    def __init__(self):
        self.messages = []
        self.pending_request = None
        if not ensure_app_ws_broker():
            raise ConnectionError("app ws broker unavailable")

    def request(self, request_obj, expected_func="", wait_seconds=3):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(max(1.0, float(wait_seconds) + 1.0))
        try:
            sock.connect(APP_WS_BROKER_SOCKET)
            handle = sock.makefile("rwb")
            payload = {
                "op": "request",
                "request": request_obj,
                "expected_func": expected_func,
                "wait_seconds": wait_seconds,
            }
            handle.write((json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
            handle.flush()
            line = handle.readline()
            if not line:
                raise ConnectionError("empty broker response")
            response = json.loads(line.decode("utf-8", errors="replace"))
        finally:
            try:
                sock.close()
            except Exception:
                pass
        if not response.get("ok"):
            error = response.get("error") or "unknown broker error"
            print(f"[ERROR] 系统应用通道代理请求失败: {error}", flush=True)
            raise SystemExit(6)
        return list(response.get("messages") or [])

    def start_request(self, request_obj):
        self.pending_request = request_obj

    def recv_pending(self):
        if self.messages:
            return self.messages.pop(0)
        if self.pending_request is None:
            return None
        request_obj = self.pending_request
        self.pending_request = None
        expected_func = expected_func_from_request(request_obj)
        self.messages.extend(self.request(request_obj, expected_func, 4))
        if self.messages:
            return self.messages.pop(0)
        return None

    def close(self):
        self.messages = []
        self.pending_request = None


def expected_func_from_request(request_obj):
    req_func = request_obj.get("data", {}).get("req_func")
    if isinstance(req_func, dict) and req_func:
        return str(next(iter(req_func)))
    return str(req_func or "")


def send_text(sock, obj):
    if isinstance(sock, AppWsBrokerClient):
        sock.start_request(obj)
        return
    payload = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    header = bytearray([0x81])
    size = len(payload)
    if size < 126:
        header.append(0x80 | size)
    elif size < 65536:
        header.append(0x80 | 126)
        header.extend(struct.pack("!H", size))
    else:
        header.append(0x80 | 127)
        header.extend(struct.pack("!Q", size))
    mask = os.urandom(4)
    header.extend(mask)
    sock.sendall(header + bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload)))


def send_close(sock):
    if isinstance(sock, AppWsBrokerClient):
        sock.close()
        return
    payload = b""
    header = bytearray([0x88])
    mask = os.urandom(4)
    header.append(0x80 | len(payload))
    header.extend(mask)
    sock.sendall(header + payload)


def recv_text(sock):
    if isinstance(sock, AppWsBrokerClient):
        return sock.recv_pending()
    try:
        header = sock.recv(2)
    except socket.timeout:
        return None
    if not header:
        return None
    first, second = header
    opcode = first & 0x0F
    size = second & 0x7F
    if size == 126:
        size = struct.unpack("!H", sock.recv(2))[0]
    elif size == 127:
        size = struct.unpack("!Q", sock.recv(8))[0]
    mask = sock.recv(4) if second & 0x80 else b""
    payload = b""
    while len(payload) < size:
        chunk = sock.recv(size - len(payload))
        if not chunk:
            break
        payload += chunk
    if mask:
        payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    if opcode != 1:
        return None
    return payload.decode("utf-8", errors="replace")


def parse_app_response(message):
    try:
        obj = json.loads(message)
    except Exception:
        return None
    if obj.get("head", {}).get("type") == "machine_body_operation_res":
        result = obj.get("data", {}).get("operation_result", {})
        if not isinstance(result, dict):
            return obj
        return {
            "kind": "machine_body_operation_res",
            "func": result.get("op"),
            "status": result.get("status"),
            "data": result,
            "error_code": None,
            "msg": result.get("ext_desc"),
        }
    if obj.get("head", {}).get("type") != "app_resp":
        return obj
    result = obj.get("data", {}).get("req_result", {})
    if not isinstance(result, dict):
        return obj
    app = result.get("AppResponse")
    if not isinstance(app, dict):
        app = result.get("AppReponseObjectData")
    if not isinstance(app, dict):
        app = result.get("AppResponseData")
    if not isinstance(app, dict):
        return {
            "kind": "app_resp",
            "func": result.get("req_func") or result.get("req_fun"),
            "status": result.get("status"),
            "data": result.get("data"),
            "error_code": result.get("error_code"),
            "msg": result.get("msg"),
        }
    return {
        "kind": "app_resp",
        "func": app.get("req_func"),
        "status": app.get("status"),
        "data": app.get("data"),
        "error_code": app.get("error_code"),
        "msg": app.get("msg"),
    }


def drain_until(sock, deadline):
    messages = []
    while time.time() < deadline:
        message = recv_text(sock)
        if not message:
            continue
        if "app_sub_topic" in message and "odom_ground_truth" in message:
            continue
        parsed = parse_app_response(message)
        if parsed is not None:
            messages.append(parsed)
    return messages


def print_status(prefix, status):
    alg = status.get("get_arc_alg_status") or "NA"
    dock = status.get("get_arc_dock_status") or "NA"
    print(f"[INFO] {prefix}: alg={alg} dock={dock}", flush=True)


def print_arc_notify(parsed):
    data = parsed.get("data", {}) if isinstance(parsed, dict) else {}
    items = data.get("items", []) if isinstance(data, dict) else []
    error_items = [item for item in items if str(item.get("severity", "")).lower() == "error"]
    if not error_items:
        return
    descriptions = [str(item.get("description") or item.get("code") or "") for item in error_items]
    summary = "；".join(text for text in descriptions if text) or json.dumps(data, ensure_ascii=False)
    print(f"[ERROR] ARC 错误通知: {summary}", flush=True)


def handle_arc_notify(parsed):
    print_arc_notify(parsed)


def _direct_connect_ws():
    last_error = None
    for attempt in range(1, 5):
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET / HTTP/1.1\r\n"
            f"Host: {HOST}:{PORT}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        try:
            sock = socket.create_connection((HOST, PORT), timeout=5)
            sock.sendall(request.encode("ascii"))
            response = sock.recv(4096)
            break
        except OSError as exc:
            last_error = exc
            if is_app_channel_busy():
                if cleanup_stale_app_ws_owner():
                    time.sleep(0.25 * attempt)
                    continue
                if attempt < 4:
                    print("[WARN] 系统应用通道被占用，等待重试。", flush=True)
                    time.sleep(0.35 * attempt)
                    continue
                print("[ERROR] 系统应用通道正被其他任务占用，请稍后重试。", flush=True)
                raise SystemExit(6)
            if attempt < 4:
                time.sleep(0.25 * attempt)
                continue
            print(f"[ERROR] 系统应用通道连接失败: {last_error}", flush=True)
            print("[ERROR] 系统应用通道暂不可用，请稍后重试；若持续失败，请检查远端导航服务。", flush=True)
            raise SystemExit(6)
    if b"101" not in response.split(b"\r\n", 1)[0]:
        print("[ERROR] 系统应用通道暂不可用，请等待上一任务结束后重试。", flush=True)
        raise SystemExit(3)
    sock.settimeout(0.25)
    return sock


def connect_ws():
    try:
        return AppWsBrokerClient()
    except Exception as exc:
        print(f"[WARN] 系统应用通道代理不可用，临时使用直连: {exc}", flush=True)
        return _direct_connect_ws()


def _tcp_10010_inodes():
    inodes = set()
    try:
        with open("/proc/net/tcp", "r", encoding="ascii", errors="ignore") as handle:
            lines = handle.readlines()[1:]
    except Exception:
        return inodes
    for line in lines:
        parts = line.split()
        if len(parts) < 10:
            continue
        remote = parts[2]
        state = parts[3]
        inode = parts[9]
        if state != "01":
            continue
        if remote.rsplit(":", 1)[-1].upper() == "271A":
            inodes.add(inode)
    return inodes


def _cmdline_for_pid(pid):
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as handle:
            return handle.read().replace(b"\0", b" ").decode("utf-8", errors="replace")
    except Exception:
        return ""


def _process_socket_inodes(pid):
    fd_dir = f"/proc/{pid}/fd"
    try:
        fds = os.listdir(fd_dir)
    except Exception:
        return set()
    inodes = set()
    for fd in fds:
        try:
            target = os.readlink(f"{fd_dir}/{fd}")
        except Exception:
            continue
        if target.startswith("socket:[") and target.endswith("]"):
            inodes.add(target[8:-1])
    return inodes


def _is_stale_dog_remote_app_ws_client(pid):
    if str(pid) == str(os.getpid()):
        return False
    cmdline = _cmdline_for_pid(pid)
    return cmdline.startswith("python3 ") or cmdline == "python3"


def cleanup_stale_app_ws_owner():
    inodes = _tcp_10010_inodes()
    if not inodes:
        return False
    stale_pids = []
    for pid in filter(str.isdigit, os.listdir("/proc")):
        if not _is_stale_dog_remote_app_ws_client(pid):
            continue
        if _process_socket_inodes(pid).intersection(inodes):
            stale_pids.append(pid)
    if not stale_pids:
        return False
    for pid in stale_pids:
        try:
            os.kill(int(pid), signal.SIGTERM)
        except Exception:
            pass
    time.sleep(0.15)
    for pid in stale_pids:
        try:
            os.kill(int(pid), 0)
        except Exception:
            continue
        try:
            os.kill(int(pid), signal.SIGKILL)
        except Exception:
            pass
    print(
        "[WARN] 已清理遗留系统应用通道客户端，正在重试。",
        flush=True,
    )
    return True


def is_app_channel_busy():
    try:
        return bool(_tcp_10010_inodes())
    except Exception:
        return False


def request(func, frame, value=NO_VALUE):
    req_func = func if value is NO_VALUE else {func: value}
    return {
        "head": {
            "type": "app_req",
            "time_stamp": int(time.time() * 1000),
            "source": "app",
            "frame_count": frame,
        },
        "data": {"req_func": req_func},
    }


def handle_app_response_message(message, func, required=True, log_response=True):
    if "app_sub_topic" in message and "odom_ground_truth" in message:
        return None
    parsed = parse_app_response(message)
    if parsed is None:
        return None
    if isinstance(parsed, dict) and parsed.get("kind") == "app_resp":
        if parsed.get("func") != func:
            return None
        if log_response:
            msg = parsed.get("msg")
            msg_text = f" msg={msg}" if msg else ""
            print(
                f"[INFO] 响应: func={parsed.get('func')} status={parsed.get('status')} "
                f"data={parsed.get('data')} error={parsed.get('error_code')}{msg_text}",
                flush=True,
            )
        if parsed.get("status") not in (None, "ok") and required:
            raise SystemExit(6)
        return parsed
    if isinstance(parsed, dict) and parsed.get("head", {}).get("type") == "alg_error_code_notify":
        handle_arc_notify(parsed)
    return None


def request_once(sock, frame, func, value=NO_VALUE, label=None, wait_seconds=3, required=True, log_response=True):
    if isinstance(sock, AppWsBrokerClient):
        messages = sock.request(request(func, frame, value), func, wait_seconds)
        frame += 1
    if label:
        suffix = "" if value is NO_VALUE else f" data={value}"
        print(f"[INFO] 已发送{label}: {func}{suffix}", flush=True)
    if isinstance(sock, AppWsBrokerClient):
        for message in messages:
            parsed = handle_app_response_message(message, func, required, log_response)
            if parsed is not None:
                return parsed, frame
        if required:
            print(f"[ERROR] {func} 未收到有效响应。", flush=True)
            raise SystemExit(6)
        return None, frame

    send_text(sock, request(func, frame, value))
    frame += 1
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        message = recv_text(sock)
        if not message:
            continue
        parsed = handle_app_response_message(message, func, required, log_response)
        if parsed is not None:
            return parsed, frame
    if required:
        print(f"[ERROR] {func} 未收到有效响应。", flush=True)
        raise SystemExit(6)
    return None, frame


def query_status(sock, frame):
    status = {}
    for func in ("get_arc_alg_status", "get_arc_dock_status"):
        resp, frame = request_once(sock, frame, func, wait_seconds=2, required=False, log_response=False)
        if resp is not None:
            status[func] = resp.get("data")
    return status, frame


def is_location_continuous(value):
    normalized = str(value or "").strip().replace("_", "").replace("-", "").lower()
    return normalized in {"continuousloc", "continuouslocalization", "localized"} or "continuousloc" in normalized


def load_map_until_localized(sock, frame, map_id, next_action_text):
    _resp, frame = request_once(sock, frame, "loc_load_map", map_id, label="定位地图加载", wait_seconds=8)
    deadline = time.time() + 60
    last_loc = None
    while time.time() < deadline:
        loc_resp, frame = request_once(
            sock,
            frame,
            "get_loc_status",
            wait_seconds=2,
            required=False,
            log_response=False,
        )
        loc_status = None if loc_resp is None else loc_resp.get("data")
        if loc_status != last_loc:
            print(f"[INFO] 定位状态: {loc_status}", flush=True)
            last_loc = loc_status
        if is_location_continuous(loc_status):
            print(f"[INFO] 定位已进入连续定位状态，{next_action_text}。", flush=True)
            return frame
        if str(loc_status).strip().lower() in {"failed", "failure", "locfailed", "error"}:
            print(f"[ERROR] 定位失败: {loc_status}", flush=True)
            raise SystemExit(5)
        time.sleep(2)
    print("[ERROR] 等待定位进入连续定位状态超时。", flush=True)
    raise SystemExit(5)
'''
