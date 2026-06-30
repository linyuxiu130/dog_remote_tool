#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import time

import rclpy
from builtin_interfaces.msg import Duration
from geometry_msgs.msg import Point
from nav_msgs.msg import Path
from rclpy.node import Node
from rclpy.qos import QoSProfile
from std_msgs.msg import ColorRGBA
from visualization_msgs.msg import Marker, MarkerArray


DEFAULT_SOURCE_TOPIC = "/navigo/cs/ppc/vis/received_global_plan"
DEFAULT_OUTPUT_PREFIX = "/dog_remote_tool/debug/navigation_plan"
DEFAULT_FRAME = "base_link_rviz"


def color(r: float, g: float, b: float, a: float = 1.0) -> ColorRGBA:
    msg = ColorRGBA()
    msg.r = r
    msg.g = g
    msg.b = b
    msg.a = a
    return msg


def make_duration(seconds: float) -> Duration:
    msg = Duration()
    whole = int(math.floor(seconds))
    msg.sec = whole
    msg.nanosec = int((seconds - whole) * 1_000_000_000)
    return msg


class NavigationPlanRvizVisualizer(Node):
    def __init__(
        self,
        *,
        source_topic: str,
        output_prefix: str,
        output_frame: str,
        z_offset: float,
        line_width: float,
        marker_lifetime: float,
    ) -> None:
        super().__init__("dog_remote_navigation_plan_rviz_visualizer")
        self.source_topic = source_topic
        self.output_frame = output_frame
        self.z_offset = z_offset
        self.line_width = line_width
        self.marker_lifetime = marker_lifetime
        qos = QoSProfile(depth=10)
        self.path_pub = self.create_publisher(Path, f"{output_prefix}/path", qos)
        self.marker_pub = self.create_publisher(MarkerArray, f"{output_prefix}/markers", qos)
        self.sub = self.create_subscription(Path, source_topic, self.on_path, qos)
        self.last_log = 0.0
        self.get_logger().info(f"watching {source_topic}")
        self.get_logger().info(f"publishing {output_prefix}/path and {output_prefix}/markers in {output_frame}")

    def on_path(self, msg: Path) -> None:
        now = self.get_clock().now().to_msg()
        path = Path()
        path.header.stamp = now
        path.header.frame_id = self.output_frame
        path.poses = list(msg.poses)
        for pose in path.poses:
            pose.header.stamp = now
            pose.header.frame_id = self.output_frame
            pose.pose.position.z += self.z_offset
        self.path_pub.publish(path)

        markers = MarkerArray()
        markers.markers.append(self.line_marker(path, now))
        markers.markers.append(self.start_marker(path, now))
        markers.markers.append(self.end_marker(path, now))
        self.marker_pub.publish(markers)

        current = time.monotonic()
        if current - self.last_log >= 1.0:
            self.last_log = current
            self.get_logger().info(
                f"{self.source_topic}: poses={len(msg.poses)} "
                f"src_frame={msg.header.frame_id or '<empty>'} rviz_frame={self.output_frame}"
            )

    def base_marker(self, path: Path, stamp, marker_id: int, marker_type: int) -> Marker:
        marker = Marker()
        marker.header.stamp = stamp
        marker.header.frame_id = self.output_frame
        marker.ns = "dog_remote_navigation_plan"
        marker.id = marker_id
        marker.type = marker_type
        marker.action = Marker.ADD
        marker.lifetime = make_duration(self.marker_lifetime)
        marker.pose.orientation.w = 1.0
        return marker

    def line_marker(self, path: Path, stamp) -> Marker:
        marker = self.base_marker(path, stamp, 0, Marker.LINE_STRIP)
        marker.scale.x = self.line_width
        marker.color = color(1.0, 0.45, 0.0, 1.0)
        marker.points = [Point(x=p.pose.position.x, y=p.pose.position.y, z=p.pose.position.z) for p in path.poses]
        return marker

    def start_marker(self, path: Path, stamp) -> Marker:
        marker = self.base_marker(path, stamp, 1, Marker.SPHERE)
        marker.scale.x = marker.scale.y = marker.scale.z = self.line_width * 4.0
        marker.color = color(0.1, 0.8, 1.0, 1.0)
        if path.poses:
            marker.pose.position = path.poses[0].pose.position
        return marker

    def end_marker(self, path: Path, stamp) -> Marker:
        marker = self.base_marker(path, stamp, 2, Marker.SPHERE)
        marker.scale.x = marker.scale.y = marker.scale.z = self.line_width * 5.0
        marker.color = color(1.0, 0.1, 0.1, 1.0)
        if path.poses:
            marker.pose.position = path.poses[-1].pose.position
        return marker


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Republish the active navigation plan for RViz inspection.")
    parser.add_argument("--source-topic", default=DEFAULT_SOURCE_TOPIC)
    parser.add_argument("--output-prefix", default=DEFAULT_OUTPUT_PREFIX)
    parser.add_argument("--output-frame", default=DEFAULT_FRAME)
    parser.add_argument("--z-offset", type=float, default=0.05, help="Lift markers above the ground in RViz.")
    parser.add_argument("--line-width", type=float, default=0.035)
    parser.add_argument("--marker-lifetime", type=float, default=0.8)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rclpy.init()
    node = NavigationPlanRvizVisualizer(
        source_topic=args.source_topic,
        output_prefix=args.output_prefix.rstrip("/"),
        output_frame=args.output_frame,
        z_offset=args.z_offset,
        line_width=args.line_width,
        marker_lifetime=args.marker_lifetime,
    )
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
