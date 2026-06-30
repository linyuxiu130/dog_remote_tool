from __future__ import annotations

from collections import deque
from PyQt5.QtCore import QSignalBlocker, QTimer, Qt
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QShortcut,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from dog_remote_tool.core.runner import ProcessRunner
from dog_remote_tool.modules import mapping
from dog_remote_tool.modules import navigation
from dog_remote_tool.modules.navigation import route_network
from dog_remote_tool.ui.components import CommandPage, DeviceBar, confirm_command_spec
from dog_remote_tool.ui.process_utils import ProcessSlot
from dog_remote_tool.ui.pages.navigation import workspace_dialog as _workspace_dialog
from dog_remote_tool.ui.pages.navigation import status_helpers as _status_helpers
from dog_remote_tool.ui.pages.navigation.actions import NavigationActionsMixin
from dog_remote_tool.ui.pages.navigation.action_buttons import NavigationActionButtonsMixin
from dog_remote_tool.ui.pages.navigation.action_status import NavigationActionStatusMixin
from dog_remote_tool.ui.pages.navigation.camera_overlay import (
    NAV_CAMERA_DISPLAY_INTERVAL_MS,
    NavigationCameraOverlayMixin,
    NavigationOverlayStore,
)
from dog_remote_tool.ui.pages.navigation.layout import NavigationLayoutMixin
from dog_remote_tool.ui.pages.navigation.lifecycle import NavigationLifecycleMixin
from dog_remote_tool.ui.pages.navigation.map_preparation import NavigationMapPreparationMixin
from dog_remote_tool.ui.pages.navigation.map_history import NavigationMapHistoryMixin
from dog_remote_tool.ui.pages.navigation.map_preview import NavigationMapPreviewMixin
from dog_remote_tool.ui.pages.navigation.map_widgets import NavigationMapHistoryCard, NavigationMapLabel
from dog_remote_tool.ui.pages.navigation.route_files import NavigationRouteFilesMixin
from dog_remote_tool.ui.pages.navigation.status_refresh import NavigationStatusRefreshMixin
from dog_remote_tool.ui.pages.navigation.streams import NavigationStreamsMixin
from dog_remote_tool.ui.pages.navigation.target_points import NavigationTargetPointsMixin
from dog_remote_tool.ui.pages.navigation.visualization import NavigationVisualizationMixin


# Existing tests and mixins patch these symbols via dog_remote_tool.ui.pages.navigation.page.
_QT_MONKEYPATCH_EXPORTS = (QSignalBlocker, QMessageBox, confirm_command_spec)

NAV_ACTION_BLOCKED_STYLE = _status_helpers.NAV_ACTION_BLOCKED_STYLE
NAV_ACTION_READY_STYLE = _status_helpers.NAV_ACTION_READY_STYLE
STATUS_STYLES = _status_helpers.STATUS_STYLES
NavigationWorkspaceDialog = _workspace_dialog.NavigationWorkspaceDialog
WaypointTableWidget = _workspace_dialog.WaypointTableWidget
_compact_failure_lines = _status_helpers._compact_failure_lines
_navigation_command_pending_text = _status_helpers._navigation_command_pending_text
_navigation_command_wait_text = _status_helpers._navigation_command_wait_text
_sanitize_log_line = _status_helpers._sanitize_log_line
_status_style = _status_helpers._status_style
_without_remote_navigation_state = _status_helpers._without_remote_navigation_state


class NavigationPage(
    NavigationActionsMixin,
    CommandPage,
    NavigationMapHistoryMixin,
    NavigationMapPreparationMixin,
    NavigationCameraOverlayMixin,
    NavigationActionButtonsMixin,
    NavigationActionStatusMixin,
    NavigationLayoutMixin,
    NavigationTargetPointsMixin,
    NavigationMapPreviewMixin,
    NavigationRouteFilesMixin,
    NavigationStatusRefreshMixin,
    NavigationStreamsMixin,
    NavigationVisualizationMixin,
    NavigationLifecycleMixin,
):
    def __init__(self, runner: ProcessRunner, device_bar: DeviceBar) -> None:
        super().__init__("导航", runner, device_bar)
        self.controls_panel.hide()
        self.status_slot = ProcessSlot(self, reserve_runner=False)
        self.map_list_slot = ProcessSlot(self, reserve_runner=False)
        self.map_preview_slot = ProcessSlot(self, reserve_runner=False)
        self.map_prepare_slot = ProcessSlot(self)
        self.map_thumbnail_slot = ProcessSlot(self, reserve_runner=False)
        self.route_check_slot = ProcessSlot(self, reserve_runner=False)
        self.route_pull_slot = ProcessSlot(self, reserve_runner=False)
        self.mode_switch_helper_slot = ProcessSlot(self)
        self.pose_stream_slot = ProcessSlot(self, reserve_runner=False)
        self.pose_stream_buffer = ""
        self.plan_stream_slot = ProcessSlot(self, reserve_runner=False)
        self.plan_stream_buffer = ""
        self.obstacle_stream_slot = ProcessSlot(self, reserve_runner=False)
        self.obstacle_stream_buffer = ""
        self.nav_camera_overlay_slot = ProcessSlot(self, reserve_runner=False)
        self.nav_camera_overlay_buffer = ""
        self.nav_camera_overlay_store = NavigationOverlayStore()
        self.nav_camera_video_thread = None
        self.nav_camera_video_worker = None
        self.nav_camera_video_last_sequence = 0
        self.nav_camera_expanded = False
        self.runner.task_finished_detail.connect(self.on_runner_task_finished)
        self.runner.task_output.connect(self.on_runner_task_output)
        self.navigation_cleanup_profile = self.profile()
        self.robot_pose: tuple[float, float, float] | None = None
        self.navigation_global_route: list[tuple[float, float, float]] = []
        self.navigation_realtime_plan: list[tuple[float, float, float]] = []
        self.navigation_obstacle_points: list[tuple[float, float]] = []
        self.navigation_obstacle_topic = ""
        self.obstacle_overlay_enabled = True
        self.charging_docks: list[tuple[int, float, float, float]] = []
        self.route_graph: route_network.RouteGraph | None = None
        self.route_graph_remote_pgm = ""
        self.route_graph_local_path = ""
        self.route_target_mode = False
        self.route_target_node_ids: list[int] = []
        self.route_pull_remote_pgm = ""
        self.route_pull_local_file = ""
        self.navigation_tracking_enabled = False
        self.navigation_tracking_active_seen = False
        self.navigation_status_watch_running = False
        self.navigation_command_task_id: int | None = None
        self.navigation_command_operation = ""
        self.navigation_body_release_after_terminal_triggered = False
        self.stop_navigation_waiting_remote_confirm = False
        self.stop_navigation_waiting_started_at = 0.0
        self.navigation_global_plan_topic = ""
        self.navigation_realtime_plan_topic = ""
        self.navigation_log_lines: deque[str] = deque(maxlen=180)
        self.map_details: dict[str, str] = {}
        self.map_entries_signature: tuple[tuple[str, str, str], ...] = ()
        self.map_cards: dict[str, NavigationMapHistoryCard] = {}
        self.map_thumbnail_queue: list[str] = []
        self.route_file_states: dict[str, bool] = {}
        self.route_check_remote_pgm = ""
        self.open_workspace_after_preview = False
        self.preview_remote_pgm = ""
        self.fetching_preview_remote_pgm = ""
        self.refresh_selected_map_preview_once = False
        self.workspace_dialog: NavigationWorkspaceDialog | None = None
        self.route_editor_page = None
        self.last_status_values: dict[str, str] = {}
        self.last_status_state = "unknown"
        self.last_status_at = 0.0
        self.last_navigation_action_reason = ""
        self.prepared_map_pcd_path = ""
        self.preparing_map_pcd_path = ""
        self.map_prepare_error = ""
        self.map_prepare_auto_retry_pcd = ""
        self.pending_navigation_action = ""
        self.navigation_loop_enabled = False
        self.page_active = False
        self._syncing_direction = False
        self.goal_point_selected = False
        self.added_waypoint_undo_stack: list[tuple[int, str, int | None, tuple[int, str] | None]] = []
        undo_shortcut = QShortcut(QKeySequence.Undo, self)
        undo_shortcut.activated.connect(self.undo_last_added_navigation_point)

        self.save_map_path = QLineEdit(mapping.default_save_map_path(self.profile()))
        self.map_selector = QComboBox()
        self.map_selector.setMinimumWidth(360)
        self.map_selector.setMaxVisibleItems(12)
        self.map_selector.currentIndexChanged.connect(self.on_map_selection_changed)
        self.map_pcd_path = QLineEdit(mapping.default_map_pcd_path(self.profile()))
        self.route_geojson_path = QLineEdit(route_network.DEFAULT_REMOTE_ROUTE_FILE)
        self.selected_map_detail = QLabel("远端目录：--")
        self.selected_map_detail.setObjectName("Muted")
        self.selected_map_detail.setWordWrap(True)
        self.selected_map_detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.selected_map_detail.hide()

        self.goal_x = self._spin(-2000.0, 2000.0, 0.0, " m")
        self.goal_y = self._spin(-2000.0, 2000.0, 0.0, " m")
        self.goal_yaw = self._spin(-3.1416, 3.1416, 0.0, " rad")
        self.goal_x.valueChanged.connect(self.on_goal_coordinate_changed)
        self.goal_y.valueChanged.connect(self.on_goal_coordinate_changed)
        self.goal_yaw.valueChanged.connect(self.on_goal_yaw_changed)
        self.goal_speed = self._spin(0.05, 3.0, 0.5, " m/s")
        self.goal_tolerance = self._spin(0.05, 2.0, 0.25, " m")
        self.goal_tolerance.setToolTip("路网导航目标容差")
        self.direction_degrees = QDoubleSpinBox()
        self.direction_degrees.setRange(-180.0, 180.0)
        self.direction_degrees.setDecimals(0)
        self.direction_degrees.setSingleStep(5.0)
        self.direction_degrees.setSuffix("°")
        self.direction_degrees.setToolTip("目标朝向角，0° 为地图 +X 方向")
        self.direction_degrees.valueChanged.connect(self.on_direction_degrees_changed)
        self.waypoints_text = QTextEdit()
        self.waypoints_text.setPlaceholderText("每行一个点：x,y 或 x,y,yaw")
        self.waypoints_text.setMinimumHeight(86)
        self.waypoints_text.textChanged.connect(self.on_waypoints_text_changed)
        self.waypoints_list = QListWidget()
        self.waypoints_list.setObjectName("WaypointList")
        self.waypoints_list.setMinimumHeight(96)
        self.waypoints_list.setMaximumHeight(148)
        self.waypoints_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.waypoints_list.setAlternatingRowColors(True)
        self.waypoints_list.currentRowChanged.connect(self.on_navigation_point_selection_changed)
        self.delete_waypoint_button = QPushButton("删除选中")
        self.delete_waypoint_button.setToolTip("删除点位列表中选中的目标点")
        self.delete_waypoint_button.clicked.connect(self.delete_selected_navigation_point)
        self.nav_map = NavigationMapLabel()
        self.nav_map.point_clicked.connect(self.on_map_point_clicked)
        self.nav_map.point_rejected.connect(self.on_map_point_rejected)
        self.nav_map.point_delete_requested.connect(self.delete_navigation_point)
        self.nav_map.preview_requested.connect(self.open_navigation_map_preview)
        self.nav_map_preview_path = ""

        nav_box = self._build_navigation_box()
        nav_box.hide()

        history_box = QGroupBox("历史图预览")
        history_layout = QVBoxLayout(history_box)
        history_layout.setContentsMargins(16, 14, 16, 14)
        history_layout.setSpacing(12)
        history_header = QHBoxLayout()
        history_title = QLabel("历史地图预览")
        history_title.setObjectName("FieldLabel")
        refresh_history = QPushButton("刷新历史图")
        refresh_history.setToolTip("读取远端历史图并加载预览")
        refresh_history.clicked.connect(self.refresh_map_list)
        self.history_route_editor_button = QPushButton("编辑路网")
        self.history_route_editor_button.setObjectName("SoftPrimary")
        self.history_route_editor_button.setToolTip("选择历史图后打开路网编辑器；保存后默认同步到机器人当前历史图目录")
        self.history_route_editor_button.clicked.connect(self.open_local_route_editor)
        self.history_upload_route_button = QPushButton("上传路网")
        self.history_upload_route_button.setToolTip("选择本地 GeoJSON 并上传到机器人当前历史图目录")
        self.history_upload_route_button.clicked.connect(lambda _checked=False: self.upload_selected_route_geojson())
        self.history_route_editor_button.hide()
        self.history_upload_route_button.hide()
        history_header.addWidget(history_title)
        history_header.addStretch(1)
        history_header.addWidget(refresh_history)
        history_layout.addLayout(history_header)
        self.map_cards_empty = QLabel("暂无历史图")
        self.map_cards_empty.setObjectName("Muted")
        self.map_cards_empty.setAlignment(Qt.AlignCenter)
        self.map_cards_empty.setMinimumHeight(260)
        self.map_cards_panel = QWidget()
        self.map_cards_layout = QHBoxLayout(self.map_cards_panel)
        self.map_cards_layout.setContentsMargins(0, 0, 0, 0)
        self.map_cards_layout.setSpacing(10)
        self.map_cards_panel.hide()
        history_layout.addWidget(self.map_cards_empty, 1)
        history_layout.addWidget(self.map_cards_panel, 1)
        self.nav_status_note.hide()

        self.flow_detail = QLabel("流程摘要\n等待状态刷新")
        self.flow_detail.setObjectName("Muted")
        self.flow_detail.setWordWrap(True)
        self.flow_detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.flow_detail.setMinimumHeight(118)
        self.flow_detail.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.flow_detail.setStyleSheet(
            "background:#ffffff;color:#334155;border:1px solid #e3eaf3;border-radius:8px;padding:10px 12px;line-height:130%;"
        )
        self.flow_detail.hide()
        self.body.addWidget(history_box, 1)

        self.set_command(navigation.status_command(self.profile(), self.map_pcd_path.text().strip()))
        self.nav_camera_frame_timer = QTimer(self)
        self.nav_camera_frame_timer.setInterval(NAV_CAMERA_DISPLAY_INTERVAL_MS)
        self.nav_camera_frame_timer.timeout.connect(self.flush_latest_navigation_camera_frame)
        self.runner.finished.connect(
            lambda _code: QTimer.singleShot(900, self.refresh_navigation_status) if self.page_active else None
        )
        self.runner.output.connect(self.capture_navigation_log)
        self.device_bar.profile_changed.connect(self.on_navigation_profile_changed)
        self.refresh_navigation_points_list()
        self.update_navigation_action_buttons({})

    def _spin(self, minimum: float, maximum: float, value: float, suffix: str) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(3)
        spin.setSingleStep(0.05)
        spin.setValue(value)
        spin.setSuffix(suffix)
        return spin
