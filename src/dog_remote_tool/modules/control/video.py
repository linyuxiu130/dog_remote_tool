from __future__ import annotations

from urllib.parse import quote as url_quote

from dog_remote_tool.core.paths import resource_dir
from dog_remote_tool.core.profiles import ProductProfile, get_product
from dog_remote_tool.core.shell import quote, rsync_push_command, ssh_command, sudo_run_shell


RTSP_PORT = 8554
RTSP_BRIDGE_DEB_REMOTE_DIR = "/tmp/dog_remote_rtsp_debs"
RTSP_BRIDGE_DEB_PACKAGES = (
    "python3-gi",
    "python3-gst-1.0",
    "gir1.2-gst-rtsp-server-1.0",
    "gstreamer1.0-plugins-base",
    "gstreamer1.0-plugins-good",
    "gstreamer1.0-plugins-ugly",
)

RTSP_HOST_BY_PROFILE = {
    "xg3588": "192.168.234.1",
    "xg2_3588": "192.168.234.1",
    "zg3588": "192.168.234.1",
    "zg_surround_3588": "192.168.234.1",
    "xg1_nx": "192.168.234.1",
    "zg_lidar_nx": "192.168.234.1",
    "zg_surround_s100": "192.168.234.1",
    "xg2_s100": "192.168.168.100",
}

RTSP_SERVICE_PROFILE_BY_PROFILE = {
    "xg1_nx": "xg3588",
    "zg_lidar_nx": "zg3588",
    "zg_surround_s100": "zg3588",
}

RTSP_BRIDGE_TOPIC_BY_PATH = {
    "front": "/front_camera/image_compressed",
    "test": "/front_camera/image_compressed",
    "back": "/rear_camera/image_compressed",
    "left": "/left_fisheye/image_compressed",
    "right": "/right_fisheye/image_compressed",
    "depth_rgb": "/rs_rgb_img/compressed",
    "depth": "/rs_ir_left/compressed",
}

RTSP_BRIDGE_TOPIC_BY_PROFILE_PATH = {
    ("xg2_s100", "front"): "/front_stereo_camera/image_compressed",
    ("xg2_s100", "back"): "/rear_fisheye/image_compressed",
    ("xg2_s100", "left"): "/left_fisheye/image_compressed",
    ("xg2_s100", "right"): "/right_fisheye/image_compressed",
    ("zg_surround_s100", "front"): "/front_stereo_camera/image_compressed",
    ("zg_surround_s100", "back"): "/rear_fisheye/image_compressed",
    ("zg_surround_s100", "left"): "/left_fisheye/image_compressed",
    ("zg_surround_s100", "right"): "/right_fisheye/image_compressed",
}

RTSP_PATH_BY_TOPIC = {
    "/front_camera/image_compressed": "front",
    "/front_camera/image": "front",
    "/rs_rgb_img/compressed": "front",
    "/rs_rgb_img/compressedDepth": "front",
    "/rs_rgb/image": "front",
    "/rs_rgb/image_raw": "front",
    "/rs_ir_left/compressed": "depth",
    "/rs_ir_right/compressed": "depth",
    "/rs_depth_img/compressed": "depth",
    "/rs_depth_img/compressedDepth": "depth",
    "/rs_depth/image": "depth",
    "/rs_depth/image_raw": "depth",
    "/front_stereo_camera/image_compressed": "front",
    "/front_fisheye/image_compressed": "front",
    "/rear_camera/image_compressed": "back",
    "/rear_camera/image": "back",
    "/rear_fisheye/image_compressed": "back",
    "/left_fisheye/image_compressed": "left",
    "/right_fisheye/image_compressed": "right",
}

RTSP_PATH_BY_PROFILE_SOURCE = {
    ("xg3588", "front"): "test",
    ("xg1_nx", "front"): "test",
    ("xg3588", "/front_camera/image_compressed"): "test",
    ("xg3588", "/front_camera/image"): "test",
    ("xg1_nx", "/front_camera/image_compressed"): "test",
    ("xg1_nx", "/front_camera/image"): "test",
}


def rtsp_host(profile: ProductProfile) -> str:
    return RTSP_HOST_BY_PROFILE.get(profile.key, profile.host)


def rtsp_host_for_source(profile: ProductProfile, source: str) -> str:
    return rtsp_host(profile)


def rtsp_service_profile(profile: ProductProfile) -> ProductProfile:
    key = RTSP_SERVICE_PROFILE_BY_PROFILE.get(profile.key)
    return get_product(key) if key else profile


def rtsp_service_profile_for_source(profile: ProductProfile, source: str) -> ProductProfile:
    return rtsp_service_profile(profile)


def rtsp_path(source: str) -> str:
    source = (source or "").strip()
    if not source:
        return ""
    if source.startswith("rtsp://"):
        return source
    if source.startswith("/"):
        return RTSP_PATH_BY_TOPIC.get(source, source.strip("/").replace("/", "_"))
    return source.strip("/")


def rtsp_path_for_profile(profile: ProductProfile, source: str) -> str:
    source = (source or "").strip()
    if not source:
        return ""
    if source.startswith("rtsp://"):
        return source
    path = rtsp_path(source)
    return RTSP_PATH_BY_PROFILE_SOURCE.get((profile.key, source), RTSP_PATH_BY_PROFILE_SOURCE.get((profile.key, path), path))


def rtsp_url(profile: ProductProfile, source: str) -> str:
    path = rtsp_path_for_profile(profile, source)
    if not path:
        return ""
    if path.startswith("rtsp://"):
        return path
    safe_path = "/".join(url_quote(part) for part in path.split("/") if part)
    return f"rtsp://{rtsp_host_for_source(profile, source)}:{RTSP_PORT}/{safe_path}"


def rtsp_bridge_topic(profile: ProductProfile, path: str) -> str:
    return RTSP_BRIDGE_TOPIC_BY_PROFILE_PATH.get((profile.key, path), RTSP_BRIDGE_TOPIC_BY_PATH.get(path, ""))


def rtsp_bridge_sources(profile: ProductProfile, path: str) -> dict[str, str]:
    if profile.key in {"xg2_s100", "zg_surround_s100"}:
        return {
            mount: topic
            for mount, topic in (
                ("front", rtsp_bridge_topic(profile, "front")),
                ("back", rtsp_bridge_topic(profile, "back")),
                ("left", rtsp_bridge_topic(profile, "left")),
                ("right", rtsp_bridge_topic(profile, "right")),
            )
            if topic
        }
    topic = rtsp_bridge_topic(profile, path)
    return {path: topic} if topic else {}


def rtsp_bridge_deb_dir():
    return resource_dir("rtsp_bridge", "ubuntu22.04-arm64", "debs")


def _rtsp_bridge_deb_upload_prefix(profile: ProductProfile) -> str:
    deb_dir = rtsp_bridge_deb_dir()
    debs = sorted(deb_dir.glob("*.deb")) if deb_dir.is_dir() else []
    if not debs:
        message = f"[RTSP] WARN: 本地离线依赖包缓存为空: {deb_dir}"
        return f"printf '%s\\n' {quote(message)}; "
    prepare_remote = ssh_command(profile, f"mkdir -p {quote(RTSP_BRIDGE_DEB_REMOTE_DIR)}")
    upload = rsync_push_command(
        profile,
        str(deb_dir) + "/",
        RTSP_BRIDGE_DEB_REMOTE_DIR + "/",
        options="-az --delete",
        connect_timeout=10,
    )
    return f"{prepare_remote} && {upload} && "


def _rtsp_bridge_dependency_script() -> str:
    packages = " ".join(RTSP_BRIDGE_DEB_PACKAGES)
    return f"""
dog_remote_rtsp_bridge_deps_ready() {{
python3 - <<'PY' >/dev/null 2>&1
import gi
gi.require_version("Gst", "1.0")
gi.require_version("GstRtspServer", "1.0")
from gi.repository import Gst, GstRtspServer
import rclpy
from sensor_msgs.msg import CompressedImage
Gst.init(None)
for name in ("appsrc", "jpegdec", "videoconvert", "videoscale", "x264enc", "rtph264pay"):
    if Gst.ElementFactory.find(name) is None:
        raise RuntimeError("missing GStreamer element: " + name)
PY
}}
if dog_remote_rtsp_bridge_deps_ready; then
    echo '[RTSP] RTSP 桥接依赖已满足'
else
    echo '[RTSP] 使用工具内置离线包安装 RTSP 桥接依赖: {packages}'
    if ls {RTSP_BRIDGE_DEB_REMOTE_DIR}/*.deb >/dev/null 2>&1; then
        : >/tmp/dog_remote_rtsp_deps_missing.list
        for deb in {RTSP_BRIDGE_DEB_REMOTE_DIR}/*.deb; do
            pkg="$(dpkg-deb -f "$deb" Package 2>/dev/null || true)"
            if [ -n "$pkg" ] && ! dpkg-query -W -f='${{Status}}' "$pkg" 2>/dev/null | grep -q 'install ok installed'; then
                printf '%s\\n' "$deb" >>/tmp/dog_remote_rtsp_deps_missing.list
            fi
        done
        if [ -s /tmp/dog_remote_rtsp_deps_missing.list ]; then
            : >/tmp/dog_remote_rtsp_deps_install.log
            sudo_run dpkg --configure -a >>/tmp/dog_remote_rtsp_deps_install.log 2>&1 || true
            if sudo_run dpkg -i $(cat /tmp/dog_remote_rtsp_deps_missing.list) >>/tmp/dog_remote_rtsp_deps_install.log 2>&1; then
                echo '[RTSP] RTSP 桥接依赖安装完成'
            else
                echo '[RTSP] ERROR: RTSP 桥接依赖安装失败，最近日志如下'
                tail -80 /tmp/dog_remote_rtsp_deps_install.log 2>/dev/null || true
            fi
        else
            echo '[RTSP] 离线包已上传，未发现缺失的 deb 包'
        fi
    else
        echo '[RTSP] ERROR: 远端未收到离线依赖包: {RTSP_BRIDGE_DEB_REMOTE_DIR}/*.deb'
    fi
fi
"""


def _rtsp_path_ready_function(path: str) -> str:
    return f"""
dog_remote_rtsp_path_ready() {{
python3 - <<'PY'
import socket
import sys

host = "127.0.0.1"
port = {RTSP_PORT}
path = {path!r}
try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.8)
    sock.connect((host, port))
    request = f"DESCRIBE rtsp://{{host}}:{{port}}/{{path}} RTSP/1.0\\r\\nCSeq: 1\\r\\nAccept: application/sdp\\r\\n\\r\\n".encode()
    sock.sendall(request)
    first = sock.recv(256).decode(errors="replace").splitlines()[0]
    ok = " 200 " in first
except Exception:
    ok = False
finally:
    try:
        sock.close()
    except Exception:
        pass
sys.exit(0 if ok else 1)
PY
}}
"""


def _generic_rtsp_bridge_script(path: str, sources: dict[str, str]) -> str:
    topic = sources.get(path, "")
    sources_value = ";".join(f"{mount}={source_topic}" for mount, source_topic in sources.items())
    if not sources:
        return f"""
echo '[RTSP] WARN: /{path} 没有可自动桥接的默认 compressed image topic'
"""
    return f"""
echo '[RTSP] 自动部署 RTSP 桥接: {topic} -> /{path}'
echo '[RTSP] 桥接挂载: {sources_value}'
{_rtsp_bridge_dependency_script()}
if ! dog_remote_rtsp_bridge_deps_ready; then
    echo '[RTSP] ERROR: 缺少 GstRtspServer/GStreamer 插件/rclpy/sensor_msgs，自动部署失败；非 ROS 依赖请先缓存到工具内置离线包目录'
    tail -80 /tmp/dog_remote_rtsp_deps_install.log 2>/dev/null || true
elif python3 - <<'PY' >/dev/null 2>&1
import socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(0.5)
sock.connect(("127.0.0.1", {RTSP_PORT}))
sock.close()
PY
then
    echo '[RTSP] 8554 已有 RTSP 服务占用但 /{path} 不可读，尝试切换到自动桥接'
    if command -v robot-launch >/dev/null 2>&1; then
        for name in push_video push_ffmedia push_image remote-video remote_video media_server; do
            robot-launch stop "$name" >/dev/null 2>&1 || true
        done
    fi
fi
if python3 - <<'PY' >/dev/null 2>&1
import socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(0.5)
sock.connect(("127.0.0.1", {RTSP_PORT}))
sock.close()
PY
then
    echo '[RTSP] WARN: 8554 仍被占用，自动桥接无法绑定；保留现有媒体服务'
else
cat >/tmp/dog_remote_rtsp_bridge.py <<'PY'
import os
import signal
import threading
import time

import gi
gi.require_version("Gst", "1.0")
gi.require_version("GstRtspServer", "1.0")
from gi.repository import GLib, Gst, GstRtspServer

import rclpy
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CompressedImage


class BridgeFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, mount, topic):
        super().__init__()
        self.mount = mount
        self.topic = topic
        self.appsrc = None
        self.last_push = 0.0
        self.last_msg = {{"time": 0.0, "size": 0}}
        self.set_shared(True)
        self.set_launch(
            "appsrc name=source is-live=true block=false format=time do-timestamp=true "
            "caps=image/jpeg,framerate=15/1 "
            "! jpegdec ! videoconvert ! videoscale "
            "! video/x-raw,width=960,height=540 "
            "! x264enc tune=zerolatency speed-preset=ultrafast bitrate=1200 key-int-max=15 "
            "! rtph264pay name=pay0 pt=96"
        )

    def do_configure(self, media):
        element = media.get_element()
        self.appsrc = element.get_child_by_name("source")

    def push(self, payload):
        if self.appsrc is None:
            return
        buffer = Gst.Buffer.new_allocate(None, len(payload), None)
        buffer.fill(0, payload)
        result = self.appsrc.emit("push-buffer", buffer)
        if result == Gst.FlowReturn.OK:
            self.last_push = time.time()


def main():
    source_text = os.environ.get("DOG_REMOTE_RTSP_SOURCES", "front=/front_camera/image_compressed")
    port = os.environ.get("DOG_REMOTE_RTSP_PORT", "8554")
    sources = []
    for item in source_text.split(";"):
        if "=" not in item:
            continue
        mount, topic = item.split("=", 1)
        mount = mount.strip().strip("/")
        topic = topic.strip()
        if mount and topic:
            sources.append((mount, topic))
    if not sources:
        raise SystemExit("DOG_REMOTE_RTSP_SOURCES is empty")
    Gst.init(None)
    rclpy.init(args=None)
    node = rclpy.create_node("dog_remote_rtsp_bridge")
    server = GstRtspServer.RTSPServer()
    server.set_service(port)
    mount_points = server.get_mount_points()
    factories = []
    for mount, topic in sources:
        factory = BridgeFactory(mount, topic)
        factories.append(factory)
        mount_points.add_factory("/" + mount, factory)
    server.attach(None)
    qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT, history=HistoryPolicy.KEEP_LAST)
    for factory in factories:
        def callback(msg, target=factory):
            if msg.data:
                payload = bytes(msg.data)
                target.last_msg["time"] = time.time()
                target.last_msg["size"] = len(payload)
                target.push(payload)

        node.create_subscription(CompressedImage, factory.topic, callback, qos)

    def spin():
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.1)

    threading.Thread(target=spin, daemon=True).start()
    for mount, topic in sources:
        print("[RTSP] bridge ready: rtsp://0.0.0.0:" + port + "/" + mount + " topic=" + topic, flush=True)

    def report():
        for factory in factories:
            age = time.time() - factory.last_msg["time"] if factory.last_msg["time"] else -1
            if age < 0:
                print("[RTSP] WARN: " + factory.topic + " 尚未收到图像消息", flush=True)
            else:
                print("[RTSP] " + factory.topic + " last=" + format(age, ".1f") + "s size=" + str(factory.last_msg["size"]), flush=True)
        return True

    GLib.timeout_add_seconds(5, report)
    loop = GLib.MainLoop()

    def stop(_signum, _frame):
        loop.quit()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        loop.run()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
PY
    bridge_pid_file=/tmp/dog_remote_rtsp_bridge_{path}.pid
    if [ -r "$bridge_pid_file" ]; then
        old_bridge_pid="$(cat "$bridge_pid_file" 2>/dev/null || true)"
        if [ -n "$old_bridge_pid" ] && kill -0 "$old_bridge_pid" >/dev/null 2>&1; then
            kill "$old_bridge_pid" >/dev/null 2>&1 || true
        fi
    fi
    DOG_REMOTE_RTSP_SOURCES={sources_value!r} DOG_REMOTE_RTSP_PORT={RTSP_PORT} \\
        bash -lc 'source /opt/ros/humble/setup.bash >/dev/null 2>&1 || true; source /opt/robot/robot-driver/install/setup.bash >/dev/null 2>&1 || true; source /opt/runtime/env.bash >/dev/null 2>&1 || true; export ROS_DOMAIN_ID=24 RMW_IMPLEMENTATION=rmw_zenoh_cpp ROS_LOCALHOST_ONLY=0; nohup python3 /tmp/dog_remote_rtsp_bridge.py >/tmp/dog_remote_rtsp_bridge_{path}.log 2>&1 & echo $! >/tmp/dog_remote_rtsp_bridge_{path}.pid'
    tail -20 /tmp/dog_remote_rtsp_bridge_{path}.log 2>/dev/null || true
fi
"""


def video_stream_command(profile: ProductProfile, source: str = "front", max_fps: int = 0, jpeg_quality: int = 0) -> str:
    del max_fps, jpeg_quality
    url = rtsp_url(profile, source)
    if not url:
        return "echo '[RTSP] 视频源不能为空'; exit 2"
    path = rtsp_path_for_profile(profile, source)
    service_profile = rtsp_service_profile_for_source(profile, source)
    service_script = """
if command -v robot-launch >/dev/null 2>&1; then
    launch_list="$(robot-launch list 2>/dev/null || true)"
    for name in media_server push_video push_ffmedia push_image remote-video remote_video; do
        if printf '%s\\n' "$launch_list" | grep -q "$name"; then
            robot-launch start "$name" >/dev/null 2>&1 || true
        fi
    done
fi
"""
    bridge_script = _generic_rtsp_bridge_script(path, rtsp_bridge_sources(profile, path))
    inner = f"""
set +e
echo '[RTSP] 准备远端媒体服务: {url}'
{sudo_run_shell(probe_sudo=True)}
if [ -f /tmp/video_stream.pid ]; then
    video_stream_pid="$(tr -cd '0-9' < /tmp/video_stream.pid 2>/dev/null || true)"
    if [ -n "$video_stream_pid" ] && ! kill -0 "$video_stream_pid" >/dev/null 2>&1; then
        echo "[RTSP] 清理失效 video_stream pid: $video_stream_pid"
        sudo_run rm -f /tmp/video_stream.pid >/dev/null 2>&1 || true
    fi
fi
{service_script}
{_rtsp_path_ready_function(path)}
if ! dog_remote_rtsp_path_ready; then
    echo '[RTSP] 远端路径 /{path} 未就绪，尝试自动部署桥接'
{bridge_script}
fi
python3 - <<'PY'
import socket
host = "127.0.0.1"
port = {RTSP_PORT}
path = {path!r}
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(1.0)
try:
    sock.connect((host, port))
except Exception as exc:
    print(f"[RTSP] WARN: 远端 {{host}}:{{port}} 暂不可连接: {{exc}}")
else:
    print(f"[RTSP] 远端 {{host}}:{{port}} 已响应")
finally:
    sock.close()
try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1.0)
    sock.connect((host, port))
    request = f"DESCRIBE rtsp://{{host}}:{{port}}/{{path}} RTSP/1.0\\r\\nCSeq: 1\\r\\nAccept: application/sdp\\r\\n\\r\\n".encode()
    sock.sendall(request)
    first = sock.recv(256).decode(errors="replace").splitlines()[0]
except Exception as exc:
    print(f"[RTSP] WARN: 远端路径 /{{path}} 暂不可读: {{exc}}")
else:
    print(f"[RTSP] 远端路径 /{{path}}: {{first}}")
finally:
    try:
        sock.close()
    except Exception:
        pass
PY
echo '[RTSP] 本地将直连播放: {url}'
"""
    return _rtsp_bridge_deb_upload_prefix(service_profile) + ssh_command(service_profile, inner)
