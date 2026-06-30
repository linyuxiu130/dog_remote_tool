# RTSP bridge offline packages

This directory stores arm64 Ubuntu 22.04 `.deb` packages used by the remote RTSP bridge fallback.

The robot is treated as offline. Do not install these dependencies with remote `apt-get`.
Only non-ROS packages belong here; `rclpy` and `sensor_msgs` are provided by the robot's ROS 2 Humble environment.

Required roots:

- `python3-gi`
- `python3-gst-1.0`
- `gir1.2-gst-rtsp-server-1.0`
- `gstreamer1.0-plugins-base`
- `gstreamer1.0-plugins-good`
- `gstreamer1.0-plugins-ugly`

Populate `debs/` with the root packages and their transitive dependencies by running:

```bash
scripts/fetch_rtsp_bridge_debs.sh
```
