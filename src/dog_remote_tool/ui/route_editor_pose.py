from __future__ import annotations

from PyQt5.QtCore import QProcess, QTimer
from PyQt5.QtWidgets import QMessageBox

from dog_remote_tool.core.shell import CommandSpec
from dog_remote_tool.modules import localization
from dog_remote_tool.modules.navigation import route_network
from dog_remote_tool.modules.navigation.route_pose_commands import CurrentPose
from dog_remote_tool.ui.navigation_helpers import consume_pose_stream_output


class RouteEditorPoseMixin:
    def add_current_pose_node(self) -> bool:
        pose = getattr(self.page, "robot_pose", None)
        if pose is not None:
            self._add_current_pose_node(CurrentPose(float(pose[0]), float(pose[1]), float(pose[2])))
            return True
        if self.page.current_pose_slot.is_running():
            self.editor_status.setText("正在读取当前车位置")
            return False
        process, request_id = self.page.current_pose_slot.start_spec(
            CommandSpec(
                "读取编辑器当前点",
                route_network.current_pose_command(self.page.profile()),
                concurrency="parallel",
                locks=("route-current-pose",),
            )
        )
        if process is None:
            return False
        process.readyReadStandardOutput.connect(lambda: self._read_editor_current_pose_output(process, request_id))
        process.finished.connect(lambda exit_code, _status: self._editor_current_pose_finished(process, request_id, exit_code))
        process.start()
        self.editor_status.setText("正在读取当前车位置")
        return True

    def _read_editor_current_pose_output(self, process: QProcess, request_id: int) -> bool:
        return self.page.current_pose_slot.read_available_output(process, request_id)

    def _editor_current_pose_finished(self, process: QProcess, request_id: int, exit_code: int) -> bool:
        output = self.page.current_pose_slot.finish(process, request_id)
        if output is None:
            return False
        pose = route_network.parse_current_pose_output(output)
        if exit_code != 0 or pose is None:
            self.editor_status.setText("当前车位置不可用")
            QMessageBox.information(
                self,
                "当前车位置不可用",
                route_network.current_pose_failure_message(output, exit_code),
            )
            return False
        self._add_current_pose_node(pose)
        return True

    def _add_current_pose_node(self, pose: CurrentPose) -> None:
        self.canvas.push_history("按当前位置添加节点")
        try:
            result = route_network.add_coordinate_route_node(
                self.canvas.graph,
                pose.x,
                pose.y,
                edge_starts_at_new=True,
            )
        except ValueError:
            node_id = self.canvas.graph.next_node_id()
            self.canvas.graph.nodes[node_id] = route_network.RouteNode(
                node_id,
                pose.x,
                pose.y,
                {"id": node_id, "source": "current_pose"},
            )
            result = None
        else:
            node_id = result.node_id
            self.canvas.graph.nodes[node_id].properties["source"] = "current_pose"
            edge = self.canvas.graph.edges[result.edge_id]
            edge.properties["source"] = "auto_attach_isolated"
        self.canvas._select("node", node_id)
        self.on_graph_changed()
        suffix = "，已自动接入路网" if result is not None else ""
        self.editor_status.setText(f"已按当前位置新增节点 {node_id}{suffix}")

    def start_pose_stream(self) -> bool:
        slot = getattr(self.page, "pose_stream_slot", None)
        if slot is None or slot.is_running():
            return False
        self.pose_stream_active = True
        self.page.pose_stream_buffer = ""
        process, request_id = slot.start_spec(
            CommandSpec(
                "路网编辑位姿流",
                localization.pose_stream_command(self.page.profile()),
                concurrency="parallel",
                locks=("route-editor-pose-stream",),
            )
        )
        if process is None:
            self.pose_stream_active = False
            return False
        process.readyReadStandardOutput.connect(lambda: self.read_pose_stream_output(process, request_id))
        process.finished.connect(lambda _exit_code, _status: self.pose_stream_finished(process, request_id))
        process.start()
        self.editor_status.setText("正在显示当前车位置")
        return True

    def stop_pose_stream(self) -> bool:
        self.pose_stream_active = False
        self.page.pose_stream_buffer = ""
        slot = getattr(self.page, "pose_stream_slot", None)
        return bool(slot.stop()) if slot is not None else False

    def read_pose_stream_output(self, process: QProcess, request_id: int) -> None:
        slot = getattr(self.page, "pose_stream_slot", None)
        if slot is None:
            return
        chunk = slot.read_available_text(process, request_id)
        if not chunk:
            return
        self.page.pose_stream_buffer, pose = consume_pose_stream_output(self.page.pose_stream_buffer, chunk)
        if pose:
            self.page.robot_pose = pose
            self.canvas.set_robot_pose(pose)
            if callable(getattr(self.page.canvas, "set_robot_pose", None)):
                self.page.canvas.set_robot_pose(pose)

    def pose_stream_finished(self, process: QProcess, request_id: int) -> None:
        slot = getattr(self.page, "pose_stream_slot", None)
        if slot is None:
            return
        output = slot.finish(process, request_id)
        if output is None:
            return
        if self.pose_stream_active and self.isVisible():
            QTimer.singleShot(1500, self.start_pose_stream)
