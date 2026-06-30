from __future__ import annotations

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QDialog,
    QMessageBox,
    QShortcut,
    QSplitter,
    QVBoxLayout,
)

from ..modules.navigation.route_network import (
    RouteGraph,
)
from .route_editor_export import RouteEditorExportMixin
from .route_editor_history import RouteEditorHistoryMixin
from .route_editor_layout import RouteEditorLayoutMixin
from .route_editor_pose import RouteEditorPoseMixin
from .route_editor_properties import RouteEditorPropertiesMixin
from .route_editor_tools import RouteEditorToolsMixin
from .route_editor_validation import RouteEditorValidationMixin
from .route_map_canvas import RouteMapCanvas
from .widget_roles import set_button_role


class RouteEditorDialog(
    RouteEditorExportMixin,
    RouteEditorPropertiesMixin,
    RouteEditorToolsMixin,
    RouteEditorValidationMixin,
    RouteEditorHistoryMixin,
    RouteEditorLayoutMixin,
    RouteEditorPoseMixin,
    QDialog,
):
    def __init__(self, page) -> None:
        super().__init__(None)
        self.page = page
        self.setWindowTitle("路网全屏编辑")
        self.setObjectName("RouteEditorDialog")
        self.setWindowFlag(Qt.Window, True)
        self.setModal(True)
        self.resize(1440, 900)
        self.current_tool = "edge"
        self._updating_properties = False
        self.keyboard_control_page = None
        self.keyboard_remote_state = "off"
        self.keyboard_remote_status_timer = QTimer(self)
        self.keyboard_remote_status_timer.setInterval(300)
        self.keyboard_remote_status_timer.timeout.connect(self.sync_keyboard_remote_state)
        self.pose_stream_active = False
        self.pending_remote_save_task_id: int | None = None
        self.undo_shortcut = QShortcut(QKeySequence.Undo, self)
        self.undo_shortcut.setContext(Qt.WindowShortcut)
        self.undo_shortcut.activated.connect(self.undo_history)
        self.canvas = RouteMapCanvas()
        self.canvas.set_new_edge_passable_width(
            getattr(page.canvas, "new_edge_passable_width", self.canvas.new_edge_passable_width)
        )
        self.canvas.editing_enabled = True
        self.canvas.set_display_options(show_nodes=True, show_node_labels=False, show_direction_arrows=True)
        self.canvas.hover_text = "左键加点/连线，右键删除；方向键/WASD 平移，+/- 缩放"

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        root.addWidget(self._make_header())

        self.toolbar = self._make_toolbar()
        root.addWidget(self.toolbar)
        main = QSplitter(Qt.Horizontal)
        main.setChildrenCollapsible(False)
        if page.canvas.pixmap and page.map_metadata:
            self.canvas.set_map(page.canvas.pixmap, page.map_metadata)
            self.canvas.set_inflation_overlay(page.canvas.inflation_overlay, page.canvas.inflation_overlay_label)
            self.canvas.set_show_inflation_overlay(page.canvas.show_inflation_overlay)
            self.refresh_inflation_label()
        self.canvas.set_graph(page.canvas.graph)
        self.canvas.set_issues(page.last_issues)
        self.canvas.selection_changed.connect(self.update_properties)
        self.canvas.graph_changed.connect(self.on_graph_changed)
        self.canvas.history_changed.connect(self.refresh_history_table)
        self.canvas.cursor_moved.connect(self.on_cursor_moved)
        self.canvas.point_picked.connect(self.on_point_picked)
        self.side_panel = self._make_side_panel()
        main.addWidget(self.canvas)
        main.addWidget(self.side_panel)
        main.setSizes([980, 380])
        root.addWidget(main, 1)
        self.set_tool("edge")
        self.update_summary()
        self.refresh_validation_highlights()
        self.refresh_history_table()
        self.start_pose_stream()

    def set_tool(self, mode: str) -> None:
        self.current_tool = mode
        for key, button in self.editor_tool_buttons.items():
            button.setChecked(key == mode)
        self.canvas.set_mode(mode)
        hints = {
            "select": "选取/移动：点击点或边查看属性；方向键/WASD 平移，+/- 缩放",
            "node": "添加节点：点击底图空白处创建节点；靠近已有点会自动选中已有点",
            "edge": "加点连线：左键加点/连线，方向键/WASD 平移，+/- 缩放",
            "delete": "删除对象：右键也可直接删除命中的点或边",
        }
        self.editor_status.setText(hints.get(mode, "选择工具后在地图上操作"))

    def set_inflation_visible(self, visible: bool) -> None:
        self.canvas.set_show_inflation_overlay(visible)
        self.page.canvas.set_show_inflation_overlay(visible)
        self.refresh_inflation_label()

    def refresh_inflation_label(self) -> None:
        text = getattr(self.canvas, "inflation_overlay_label", "") or "膨胀：未读取"
        self.inflation_label.setText(text)
        self.inflation_label.setToolTip(
            "当前显示的是路网编辑障碍膨胀边缘，使用默认障碍膨胀半径。"
            if text != "膨胀：未读取"
            else "底图尚未加载，暂未生成障碍膨胀显示。"
        )

    def on_cursor_moved(self, x: float, y: float) -> None:
        self.editor_status.setText(f"坐标：x={x:.3f}, y={y:.3f}")

    def on_point_picked(self, x: float, y: float) -> None:
        self.editor_status.setText(f"点击：x={x:.3f}, y={y:.3f}")

    def toggle_keyboard_remote(self) -> bool:
        control_page = self._ensure_keyboard_control_page()
        if control_page is None:
            return False
        if control_page.keyboard_stream_running():
            stopped_gamepad = control_page.stop_gamepad_stream()
            stopped_l1 = control_page.stop_l1_sdk_stream()
            stopped = stopped_gamepad or stopped_l1
            self._set_keyboard_remote_button("开始键盘遥控", "SoftPrimary")
            self._stop_keyboard_remote_status_sync()
            self.editor_status.setText("键盘遥控已停止" if stopped else "键盘遥控未运行")
            self.keyboard_remote_state = "off"
            return bool(stopped)
        from dog_remote_tool.modules import control

        if control.l1_control_profile(control_page.profile()):
            started = control_page.start_l1_sdk_stream()
        else:
            started = control_page.start_gamepad_stream()
        if started:
            self._set_keyboard_remote_button("停止键盘遥控", "Danger")
            self.keyboard_remote_state = "connecting"
            self.editor_status.setText("键盘遥控连接中，就绪后可使用 W/S/A/D/Q/E，X 回中")
            self._start_keyboard_remote_status_sync()
        else:
            self._set_keyboard_remote_button("开始键盘遥控", "SoftPrimary")
            self.keyboard_remote_state = "off"
            self.editor_status.setText("键盘遥控未启动")
        return bool(started)

    def _ensure_keyboard_control_page(self):
        if self.keyboard_control_page is None:
            from .pages.control.page import ControlPage

            self.keyboard_control_page = ControlPage(self.page.runner, self.page.device_bar)
            self.keyboard_control_page.hide()
        self.keyboard_control_page.activate_page()
        return self.keyboard_control_page

    def stop_keyboard_remote(self) -> bool:
        control_page = self.keyboard_control_page
        if control_page is None:
            return False
        stopped_gamepad = control_page.stop_gamepad_stream()
        stopped_l1 = control_page.stop_l1_sdk_stream()
        stopped = stopped_gamepad or stopped_l1
        control_page.deactivate_page()
        self._set_keyboard_remote_button("开始键盘遥控", "SoftPrimary")
        self._stop_keyboard_remote_status_sync()
        self.keyboard_remote_state = "off"
        return bool(stopped)

    def _set_keyboard_remote_button(self, text: str, role: str) -> None:
        set_button_role(self.keyboard_remote_btn, text, role)

    def _start_keyboard_remote_status_sync(self) -> None:
        if not self.keyboard_remote_status_timer.isActive():
            self.keyboard_remote_status_timer.start()

    def _stop_keyboard_remote_status_sync(self) -> None:
        if self.keyboard_remote_status_timer.isActive():
            self.keyboard_remote_status_timer.stop()

    def sync_keyboard_remote_state(self) -> bool:
        control_page = self.keyboard_control_page
        running = bool(control_page is not None and control_page.keyboard_stream_running())
        if running:
            ready = bool(
                getattr(control_page, "gamepad_stream_ready", False)
                or getattr(control_page, "l1_sdk_stream_ready", False)
            )
            state = "ready" if ready else "connecting"
            self._set_keyboard_remote_button("停止键盘遥控", "Danger")
            self._start_keyboard_remote_status_sync()
            if state != self.keyboard_remote_state:
                self.keyboard_remote_state = state
                self.editor_status.setText(
                    "键盘遥控已开启，W/S/A/D/Q/E 控制移动，X 回中"
                    if ready
                    else "键盘遥控连接中，就绪后可使用 W/S/A/D/Q/E，X 回中"
                )
            return True
        self._set_keyboard_remote_button("开始键盘遥控", "SoftPrimary")
        self._stop_keyboard_remote_status_sync()
        if self.keyboard_remote_state != "off":
            self.keyboard_remote_state = "off"
            self.editor_status.setText("键盘遥控已关闭")
        return False

    def done(self, result: int) -> None:
        self.stop_pose_stream()
        super().done(result)

    def on_graph_changed(self) -> None:
        self.canvas.graph.dirty = True
        self.canvas.update()
        self.page.graph = self.canvas.graph
        self.page.canvas.set_graph(self.canvas.graph)
        self.page.update_scale_info()
        self._autosave_local_geojson()
        self.refresh_validation_highlights()

    def new_editor_graph(self) -> None:
        if self.canvas.graph.nodes or self.canvas.graph.edges:
            answer = QMessageBox.question(self, "新建路网", "清空当前路网并新建？")
            if answer != QMessageBox.Yes:
                return
        self.canvas.set_graph(RouteGraph())
        self.canvas.set_issues([])
        self.page.graph = self.canvas.graph
        self.page.canvas.set_graph(self.canvas.graph)
        self.page.canvas.set_issues([])
        self.page.last_issues = []
        self.page.geojson_path.setText(str(self.page.default_local_geojson_path()))
        self.page.issue_list.clear()
        self.page.issue_summary.setText("空路网")
        self.page.update_scale_info()
        self.page.set_status("新建路网", "ready")
        self.populate_issues([])
        self.refresh_history_table()
        self.update_summary()
        self._autosave_local_geojson()
        self.editor_status.setText("已新建空路网")

    def save_editor_geojson(self) -> None:
        if not self._save_to_remote_by_default():
            self.editor_status.setText("当前未绑定远端历史图，本地路网已自动保存")
            return
        if not self._autosave_local_geojson(mark_upload=True):
            return
        validator = getattr(self.page, "validate_graph", None)
        if callable(validator) and not validator(show_message=True):
            detail = self._validation_error_summary()
            suffix = f"：{detail}" if detail else ""
            self.editor_status.setText(f"路网已保存到本地，校验未通过，未上传远端{suffix}")
            return
        uploader = getattr(self.page, "upload_saved_route", None)
        if callable(uploader) and uploader():
            self.pending_remote_save_task_id = getattr(self.page, "pending_route_upload_task_id", None)
            self._set_remote_save_running()
        else:
            self.editor_status.setText("远端上传未启动")
            self._set_remote_save_idle()

    def _autosave_local_geojson(self, *, mark_upload: bool = False) -> bool:
        if not self._ensure_local_geojson_path():
            self.editor_status.setText("本地保存路径不可用")
            setter = getattr(self.page, "set_status", None)
            if callable(setter):
                setter("保存路径不可用", "error")
            return False
        saver = getattr(self.page, "save_geojson", None)
        if not callable(saver):
            setter = getattr(self.page, "set_status", None)
            if callable(setter):
                setter("自动保存不可用", "error")
            return False
        saved = bool(saver(notify_saved=not mark_upload))
        if saved:
            self.editor_status.setText("已自动保存本地路网")
        else:
            self.editor_status.setText("自动保存未完成")
        return saved

    def _ensure_local_geojson_path(self) -> bool:
        path_widget = getattr(self.page, "geojson_path", None)
        if path_widget is None or not callable(getattr(path_widget, "text", None)):
            return False
        path = path_widget.text().strip()
        if path:
            return True
        default_path = self.page.default_local_geojson_path() if callable(getattr(self.page, "default_local_geojson_path", None)) else None
        if default_path is None or not callable(getattr(path_widget, "setText", None)):
            return False
        path_widget.setText(str(default_path))
        return True

    def _set_remote_save_running(self) -> None:
        self.editor_status.setText("远端上传中")
        progress = self._optional_widget("remote_save_progress")
        if progress is not None:
            progress.setVisible(True)
            progress.setRange(0, 0)
            progress.setFormat("上传中")
        button = self._optional_widget("save_route_button")
        if button is not None:
            button.setEnabled(False)

    def _set_remote_save_idle(self) -> None:
        progress = self._optional_widget("remote_save_progress")
        if progress is not None:
            progress.setVisible(True)
            progress.setRange(0, 100)
            progress.setValue(0)
            progress.setFormat("待上传")
        button = self._optional_widget("save_route_button")
        if button is not None:
            button.setEnabled(True)

    def remote_route_upload_finished(self, code: int) -> None:
        self.pending_remote_save_task_id = None
        progress = self._optional_widget("remote_save_progress")
        if progress is not None:
            progress.setVisible(True)
            progress.setRange(0, 100)
            progress.setValue(100 if code == 0 else 0)
            progress.setFormat("上传完成" if code == 0 else "上传失败")
        button = self._optional_widget("save_route_button")
        if button is not None:
            button.setEnabled(True)
        if code == 0:
            self.editor_status.setText("远端上传完成")
            if progress is not None:
                QTimer.singleShot(3500, self._set_remote_save_idle)
        else:
            self.editor_status.setText("远端上传失败，请查看日志")

    def _optional_widget(self, name: str):
        try:
            return getattr(self, name, None)
        except RuntimeError:
            return None

    def _validation_error_summary(self) -> str:
        issues = getattr(self.page, "last_issues", []) or []
        errors = [getattr(issue, "message", "") for issue in issues if getattr(issue, "severity", "") == "error"]
        errors = [message for message in errors if message]
        if not errors:
            return ""
        if len(errors) == 1:
            return errors[0]
        return f"{len(errors)} 个错误，首个：{errors[0]}"

    def _save_to_remote_by_default(self) -> bool:
        checker = getattr(self.page, "save_routes_remotely_by_default", None)
        return bool(callable(checker) and checker())

    def accept(self) -> None:
        self.stop_keyboard_remote()
        self.page.graph = self.canvas.graph
        self.page.canvas.set_graph(self.canvas.graph)
        self.page.canvas.set_issues(self.page.last_issues)
        self.page.update_scale_info()
        super().accept()

    def closeEvent(self, event) -> None:
        self.stop_keyboard_remote()
        super().closeEvent(event)
