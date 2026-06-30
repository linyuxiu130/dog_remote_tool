from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QProcess
from PyQt5.QtWidgets import QFileDialog, QMessageBox

from dog_remote_tool.core.shell import CommandSpec
from dog_remote_tool.modules import navigation
from dog_remote_tool.modules.navigation import route_network
from dog_remote_tool.modules.navigation.route_network import RouteNode
from dog_remote_tool.modules.navigation.route_pose_commands import CurrentPose
from dog_remote_tool.ui.components import confirm_command_spec


class RouteNetworkActionsMixin:
    def pull_remote_route(self) -> bool:
        remote_pgm = self.selected_history_map_pgm()
        if remote_pgm:
            self.sync_selected_history_paths(load_existing=False)
            _local_pgm, _local_yaml, local_geojson = self.local_paths_for_history(remote_pgm)
            path = str(local_geojson)
        else:
            default_name = Path.home() / "map.geojson"
            path, _filter = QFileDialog.getSaveFileName(self, "保存远端路网到本地", str(default_name), "GeoJSON (*.geojson)")
            if not path:
                return False
        spec = route_network.pull_route_file_command(
            self.profile(),
            self.remote_route_path.text().strip() or route_network.DEFAULT_REMOTE_ROUTE_FILE,
            path,
        )
        self.geojson_path.setText(path)
        return self._run_route_spec(spec, "拉取中")

    def check_remote_status(self) -> bool:
        spec = route_network.route_status_spec(
            self.profile(),
            self.remote_route_path.text().strip() or route_network.DEFAULT_REMOTE_ROUTE_FILE,
        )
        return self._run_route_spec(spec, "检查中")

    def upload_route(self) -> bool:
        if not self.validate_graph(show_message=True):
            return False
        if not self.save_geojson():
            return False
        return self.upload_saved_route()

    def upload_saved_route(self) -> bool:
        spec = route_network.upload_route_file_command(
            self.profile(),
            self.geojson_path.text().strip(),
            self.remote_route_path.text().strip() or route_network.DEFAULT_REMOTE_ROUTE_FILE,
        )
        return self._run_route_spec(spec, "上传中", track_upload=True)

    def load_remote_graph(self) -> bool:
        spec = route_network.update_graph_command(
            self.profile(),
            self.remote_route_path.text().strip() or route_network.DEFAULT_REMOTE_ROUTE_FILE,
        )
        return self._run_route_spec(spec, "加载中")

    def add_current_pose_node(self) -> bool:
        pose = getattr(self, "robot_pose", None)
        if pose is not None:
            self._add_current_pose_node(CurrentPose(float(pose[0]), float(pose[1]), float(pose[2])))
            return True
        if self.current_pose_slot.is_running():
            self.set_status("正在读取当前点", "warning")
            return False
        process, request_id = self.current_pose_slot.start_spec(
            CommandSpec("读取当前点", route_network.current_pose_command(self.profile()), concurrency="parallel", locks=("route-current-pose",))
        )
        if process is None:
            return False
        process.readyReadStandardOutput.connect(lambda: self._read_current_pose_output(process, request_id))
        process.finished.connect(lambda exit_code, _status: self._current_pose_finished(process, request_id, exit_code))
        process.start()
        self.set_status("读取当前点", "warning")
        return True

    def _read_current_pose_output(self, process: QProcess, request_id: int) -> bool:
        return self.current_pose_slot.read_available_output(process, request_id)

    def _current_pose_finished(self, process: QProcess, request_id: int, exit_code: int) -> bool:
        output = self.current_pose_slot.finish(process, request_id)
        if output is None:
            return False
        pose = route_network.parse_current_pose_output(output)
        if exit_code != 0 or pose is None:
            self.set_status("当前点不可用", "error")
            QMessageBox.information(
                self,
                "当前点不可用",
                route_network.current_pose_failure_message(output, exit_code),
            )
            return False
        self._add_current_pose_node(pose)
        return True

    def _add_current_pose_node(self, pose: CurrentPose) -> None:
        node_id = self.canvas.graph.next_node_id()
        self.canvas.graph.nodes[node_id] = RouteNode(
            node_id,
            pose.x,
            pose.y,
            {"id": node_id, "source": "current_pose"},
        )
        self.canvas.graph.dirty = True
        self.graph = self.canvas.graph
        self.canvas._select("node", node_id)
        self.update_scale_info()
        self.set_status(f"已新增当前点 {node_id}", "success")
        self.cursor_label.setText(f"当前点：x={pose.x:.3f}, y={pose.y:.3f}")

    def emergency_stop(self) -> bool:
        return self._run_route_spec(navigation.stop_command(self.profile(), source="route_network_emergency_stop"), "急停中")

    def _run_route_spec(self, spec, status: str, *, track_upload: bool = False) -> bool:
        conflict = self.runner.conflict_reason(spec)
        if conflict:
            self.set_status(conflict, "error")
            return False
        if not confirm_command_spec(self, spec):
            return False
        task_id = self.runner.run(spec, spec.display_command or spec.title)
        if task_id is None:
            self.set_status("任务未启动", "error")
            return False
        if track_upload:
            self.pending_route_upload_task_id = task_id
        self.set_status(status, "warning")
        return True

    def handle_route_runner_finished(self, task_id: int, code: int, title: str) -> bool:
        if task_id != getattr(self, "pending_route_upload_task_id", None):
            return False
        self.pending_route_upload_task_id = None
        if code == 0:
            self.set_status("上传完成", "success")
            self.notify_route_saved(self.geojson_path.text().strip())
        else:
            self.set_status("上传失败", "error")
        dialog = getattr(self, "active_editor_dialog", None)
        if dialog is not None:
            handler = getattr(dialog, "remote_route_upload_finished", None)
            if callable(handler):
                handler(code)
        return True
