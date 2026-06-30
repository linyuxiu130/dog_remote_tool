import base64
import inspect
import json
import math
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import pytest
import yaml
import numpy as np
from PyQt5.QtCore import QPoint, QPointF, QTimer, Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPixmap
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QFrame, QMessageBox

from dog_remote_tool.core.profiles import get_product
from dog_remote_tool.core.shell import CommandSpec, quote
from dog_remote_tool.modules import arc_app_ws
from dog_remote_tool.modules import localization
from dog_remote_tool.modules import navigation
from dog_remote_tool.modules.navigation import arc_calibration as navigation_arc_calibration
from dog_remote_tool.modules.navigation import arc_commands as navigation_arc_commands
from dog_remote_tool.modules.navigation import arc_marking as navigation_arc_marking
from dog_remote_tool.modules.navigation import arc_with_map as navigation_arc_with_map
from dog_remote_tool.modules.navigation import camera_overlay as navigation_camera_overlay_commands
from dog_remote_tool.modules.navigation import control_commands as navigation_control_commands
from dog_remote_tool.modules.navigation import goal_commands as navigation_goal_commands
from dog_remote_tool.modules.navigation import helper_control as navigation_helper_control
from dog_remote_tool.modules.navigation import helper_commands as navigation_helper_commands
from dog_remote_tool.modules.navigation import helper_lifecycle as navigation_helper_lifecycle
from dog_remote_tool.modules.navigation import helper_scripts as navigation_helper_scripts
from dog_remote_tool.modules.navigation import map_commands as navigation_map_commands
from dog_remote_tool.modules.navigation import payloads as navigation_payloads
from dog_remote_tool.modules.navigation import probe as navigation_probe
from dog_remote_tool.modules.navigation import probe_graph as navigation_probe_graph
from dog_remote_tool.modules.navigation import probe_motion as navigation_probe_motion
from dog_remote_tool.modules.navigation import route_commands as navigation_route_commands
from dog_remote_tool.modules.navigation import route_history as navigation_route_history
from dog_remote_tool.modules.navigation import route_network
from dog_remote_tool.modules.navigation import route_pose_commands as navigation_route_pose_commands
from dog_remote_tool.modules.navigation import status as navigation_status
from dog_remote_tool.modules.navigation import status_labels as navigation_status_labels
from dog_remote_tool.ui import navigation_helpers as ui_navigation_helpers
from dog_remote_tool.ui.navigation_helpers import consume_plan_stream_output, read_map_yaml_charging_docks
from dog_remote_tool.ui.pages.navigation import action_status as navigation_action_status
from dog_remote_tool.ui.pages.navigation import action_status_text as navigation_action_status_text
from dog_remote_tool.ui.pages.navigation import action_panel as navigation_action_panel
from dog_remote_tool.ui.pages.navigation import action_buttons as navigation_action_buttons
from dog_remote_tool.ui.pages.navigation import action_arc as navigation_action_arc
from dog_remote_tool.ui.pages.navigation import action_runner as navigation_action_runner
from dog_remote_tool.ui.pages.navigation import action_safety as navigation_action_safety
from dog_remote_tool.ui.pages.navigation import actions as navigation_actions
from dog_remote_tool.ui.pages.navigation import camera_overlay as navigation_camera_overlay_ui
from dog_remote_tool.ui.pages.navigation import layout as navigation_layout
from dog_remote_tool.ui.pages.navigation import lifecycle as navigation_lifecycle
from dog_remote_tool.ui.pages.navigation import map_drawing as navigation_map_drawing
from dog_remote_tool.ui.pages.navigation import map_history as navigation_map_history
from dog_remote_tool.ui.pages.navigation import map_history_card as navigation_map_history_card
from dog_remote_tool.ui.pages.navigation import map_preparation as navigation_map_preparation
from dog_remote_tool.ui.pages.navigation import map_preview as navigation_map_preview
from dog_remote_tool.ui.pages.navigation import map_view as navigation_map_view
from dog_remote_tool.ui.pages.navigation import map_widgets as navigation_map_widgets
from dog_remote_tool.ui.pages.navigation import point_text as navigation_point_text
from dog_remote_tool.ui.pages.navigation import route_file_editor as navigation_route_file_editor
from dog_remote_tool.ui.pages.navigation import route_file_local as navigation_route_file_local
from dog_remote_tool.ui.pages.navigation import route_file_remote as navigation_route_file_remote
from dog_remote_tool.ui.pages.navigation import route_file_upload as navigation_route_file_upload
from dog_remote_tool.ui.pages.navigation import route_files as navigation_route_files
from dog_remote_tool.ui.pages.navigation import route_history as navigation_route_history_ui
from dog_remote_tool.ui.pages.navigation import route_target_geometry as navigation_route_target_geometry
from dog_remote_tool.ui.pages.navigation import target_direction as navigation_target_direction
from dog_remote_tool.ui.pages.navigation import target_edits as navigation_target_edits
from dog_remote_tool.ui.pages.navigation import target_route_points as navigation_target_route_points
from dog_remote_tool.ui.pages.navigation import target_state as navigation_target_state
from dog_remote_tool.ui.pages.navigation import status_helpers as navigation_status_helpers
from dog_remote_tool.ui.pages.navigation import status_refresh as navigation_status_refresh
from dog_remote_tool.ui.pages.navigation import streams as navigation_streams
from dog_remote_tool.ui.pages.navigation import target_points as navigation_target_points
from dog_remote_tool.ui.pages.navigation import visualization as navigation_visualization
from dog_remote_tool.ui.pages.navigation import workspace_dialog as navigation_workspace_dialog
from dog_remote_tool.ui.pages.navigation import workspace_layout as navigation_workspace_layout
from dog_remote_tool.ui.pages.navigation import workspace_panels as navigation_workspace_panels
from dog_remote_tool.ui.pages.navigation import workspace_points as navigation_workspace_points
from dog_remote_tool.ui.pages.navigation import workspace_table as navigation_workspace_table
from dog_remote_tool.ui.pages.navigation.page import (
    NavigationMapLabel,
    NavigationMapHistoryCard,
    NavigationPage,
    NavigationWorkspaceDialog,
    _compact_failure_lines,
    _sanitize_log_line,
)
from dog_remote_tool.ui.route_inflation_overlay import create_inflation_overlay
from helpers import remote_command as _remote_command, FakeSignal as _FakeSignal, FakeRunner as _FakeRunner


def _start_navigation_payloads(command: str) -> list[str]:
    return [
        base64.b64decode(match.encode("ascii")).decode("utf-8")
        for match in re.findall(r"START_NAV_PAYLOAD=([A-Za-z0-9+/=]+);", command)
    ]


def test_navigation_map_card_label_uses_shared_history_helpers():
    assert (
        NavigationMapHistoryCard.compact_label("--", "/opt/data/.robot/map/history_map/2026_05_25_09_30_00/map.pgm")
        == "05-25 09:30:00"
    )
    assert (
        NavigationMapHistoryCard.compact_label(
            "2026-05-25 09:30 | 2.0 KB | 2026_05_25_09_30_00",
            "/opt/data/.robot/map/history_map/custom/map.pgm",
        )
        == "2026-05-25 09:30"
    )
    assert NavigationMapHistoryCard.compact_label("--", "/opt/data/.robot/map/custom/map.pgm") == "custom"


def test_navigation_text_helpers_cover_known_state_codes():
    assert navigation.navigation_state_text("0") == "待机/空闲"
    assert navigation.navigation_state_text("1") == "初始化/旧版待机"
    assert navigation.navigation_state_text("2") == "执行中"
    assert navigation.navigation_state_text("100") == "执行中"
    assert navigation.navigation_state_text("140") == "初始化"
    assert navigation.navigation_state_text("5") == "已到达"
    assert navigation.navigation_state_text("200") == "已到达"
    assert navigation.navigation_state_text("202") == "失败"
    assert navigation.task_status_text("6") == "失败"
    assert navigation.localization_state_text("3") == "连续定位正常"
    assert navigation.localization_state_display_text("6", "Active: localization running normally.") == "连续定位正常"
    assert navigation.localization_state_display_text("6", "Lost: localization lost.") == "定位丢失"
    assert navigation.localization_state_display_text("6", "", "state") == "连续定位正常"
    assert navigation.localization_state_display_text("0", "The localization system is normal.", "state") == "连续定位正常"
    assert navigation.perception_state_text("3") == "运行正常"
    assert navigation.perception_state_text("4") == "运行中"
    assert navigation.active_substate_text("1") == "避障"


def test_navigation_workspace_uses_map_overlay_camera_window():
    source = inspect.getsource(navigation_workspace_layout.NavigationWorkspaceLayoutMixin._build_ui)

    assert "setParent(self.canvas)" in source
    assert "WorkspaceCameraOverlay" in source
    assert "WorkspaceMapPipOverlay" in source
    assert "resize(480, 270)" in source
    assert "background:transparent;border:0" in source
    assert "splitter.addWidget(camera_panel)" not in source
    assert "正在连接导航视角" not in source
    assert hasattr(navigation_workspace_layout.NavigationWorkspaceLayoutMixin, "_nudge_workspace_map_view_right")
    assert hasattr(navigation_workspace_layout.NavigationWorkspaceLayoutMixin, "toggle_workspace_camera_focus")


def test_navigation_workspace_camera_pixmap_fills_without_letterbox():
    source = inspect.getsource(navigation_camera_overlay_ui.NavigationCameraOverlayMixin._set_navigation_camera_label_pixmap)

    assert "WorkspaceCameraOverlay" in source
    assert "Qt.IgnoreAspectRatio" in source


def test_navigation_map_widget_offset_keeps_coordinate_conversion_consistent():
    _ = QApplication.instance() or QApplication([])
    nav_map = NavigationMapLabel()
    nav_map.resize(1000, 800)
    pixmap = QPixmap(500, 500)
    pixmap.fill(QColor("#ffffff"))
    nav_map.set_map(pixmap, 0.1, (0.0, 0.0, 0.0))
    nav_map.view_widget_offset_ratio_x = 0.16

    point = nav_map._world_to_widget(25.0, 25.0)
    world = nav_map._widget_to_world(point)

    assert point.x() > nav_map.rect().center().x()
    assert world == pytest.approx((25.0, 25.0))


def test_navigation_workspace_camera_focus_toggle_geometry():
    _ = QApplication.instance() or QApplication([])
    dialog = NavigationWorkspaceDialog.__new__(NavigationWorkspaceDialog)
    dialog.workspace_camera_expanded = False
    dialog.canvas = NavigationMapLabel()
    dialog.canvas.resize(1200, 800)
    pixmap = QPixmap(600, 500)
    pixmap.fill(QColor("#ffffff"))
    dialog.canvas.set_map(pixmap, 0.1, (0.0, 0.0, 0.0))
    dialog.camera_view = navigation_workspace_layout.NavigationCameraView()
    dialog.camera_view.setParent(dialog.canvas)
    dialog.camera_backdrop = QFrame(dialog.canvas)
    dialog.map_pip_view = navigation_workspace_layout.WorkspaceMapPipView()
    dialog.map_pip_view.setParent(dialog.canvas)

    navigation_workspace_layout.NavigationWorkspaceLayoutMixin._sync_workspace_map_pip(dialog)
    navigation_workspace_layout.NavigationWorkspaceLayoutMixin._position_workspace_camera(dialog)

    assert dialog.map_pip_view.isHidden() is True
    assert dialog.camera_view.geometry().width() < dialog.canvas.width()

    assert navigation_workspace_layout.NavigationWorkspaceLayoutMixin.toggle_workspace_camera_focus(dialog) is True

    assert dialog.map_pip_view.isHidden() is False
    assert dialog.camera_backdrop.isHidden() is False
    assert dialog.camera_view.geometry().width() <= dialog.canvas.width() - 44
    assert dialog.camera_view.geometry().height() <= dialog.canvas.height() - 44
    assert dialog.camera_view.geometry().width() / dialog.camera_view.geometry().height() == pytest.approx(16 / 9, rel=0.01)

    assert navigation_workspace_layout.NavigationWorkspaceLayoutMixin.toggle_workspace_camera_focus(dialog) is False

    assert dialog.map_pip_view.isHidden() is True


def test_navigation_workspace_status_cards_use_compact_single_label_style():
    _ = QApplication.instance() or QApplication([])
    source = navigation_action_status.NavigationStatusCard("当前状态\n? 未知")
    source.set_navigation_state("blocked")
    source.setToolTip("status detail")
    panel = navigation_workspace_panels.NavigationWorkspacePanelsMixin()

    card = panel._workspace_status_card(source)

    assert isinstance(card, navigation_workspace_panels.WorkspaceStatusCard)
    assert card.eyebrow.text() == "当前状态"
    assert card.title.text() == "? 未知"
    assert card.toolTip() == "status detail"
    assert "background:#fff1f2" in card.styleSheet()
    assert card.objectName() == "WorkspaceStatusCard"
    assert card.maximumHeight() >= 104
    assert card.detail.isHidden()

    source.setText("当前状态\n已就绪\n地图加载完成")
    source.set_navigation_state("ready")
    panel._sync_workspace_status_card(card, source)

    assert card.title.text() == "已就绪"
    assert card.detail.text() == "地图加载完成"
    assert not card.detail.isHidden()
    assert "background:#effaf3" in card.styleSheet()


def test_navigation_workspace_exposes_distinct_arc_calibration_and_mark_actions():
    source = inspect.getsource(navigation_workspace_panels.NavigationWorkspacePanelsMixin._add_workspace_action_panel)

    assert 'QPushButton("重新定位")' in source
    assert "make_relocalize_selected_map" in source
    assert 'QPushButton("标定充电桩")' in source
    assert "make_start_arc_calibration" in source
    assert 'QPushButton("标记充电桩")' in source
    assert "make_mark_charging_dock" in source
    assert "arc_calibration_button" in source
    assert "arc_mark_button" in source


def test_navigation_current_status_text_hides_remote_topic_name_for_users():
    text = NavigationPage.current_navigation_status_text(
        object(),
        {"STATUS": "unknown", "NAV_STATE_PUBLISHERS": "0"},
    )

    assert text == "! 导航状态未发布\n等待远端状态更新"
    assert "/navigation_state" not in text


def test_navigation_point_text_helpers_cover_parse_rows_and_summaries():
    fallback = (9.0, 8.0, 0.5)
    points = navigation_point_text.parse_navigation_points("1,2\n3，4，1.5708", fallback)

    assert points == [(1.0, 2.0, 0.0), (3.0, 4.0, 1.5708)]
    assert navigation_point_text.parse_navigation_points("", fallback) == [fallback]
    assert navigation_point_text.visible_navigation_points("", False, fallback) == []
    assert navigation_point_text.format_navigation_point_rows(points[:1], route_target_mode=True) == [
        "1. 路网目标节点  x=1.000, y=2.000, 方向=0°"
    ]
    assert navigation_point_text.format_target_summary([], route_target_mode=False, route_graph=None) == "目标点：点击地图添加目标"
    assert navigation_point_text.robot_pose_summary_text(None, {"LOCALIZATION_READY": "1"}) == "机器人：定位正常，等待位姿"


def test_navigation_route_target_geometry_helpers_match_mixin_entries():
    graph = route_network.RouteGraph()
    graph.nodes[1] = route_network.RouteNode(1, 0.0, 0.0)
    graph.nodes[2] = route_network.RouteNode(2, 1.0, 0.0)
    graph.nodes[3] = route_network.RouteNode(3, 1.0, 1.0)
    graph.edges[1] = route_network.RouteEdge(1, 1, 2, [(0.0, 0.0), (1.0, 0.0)])
    graph.edges[2] = route_network.RouteEdge(2, 2, 3, [(1.0, 0.0), (1.0, 1.0)])

    assert NavigationPage.route_path_yaw(graph, 1, 3) == navigation_route_target_geometry.route_path_yaw(graph, 1, 3)
    assert NavigationPage.route_path_start_yaw(graph, 1, 3) == navigation_route_target_geometry.route_path_start_yaw(graph, 1, 3)
    assert NavigationPage.route_node_outgoing_yaw(graph, 1) == navigation_route_target_geometry.route_node_outgoing_yaw(graph, 1)
    assert NavigationPage.route_segment_yaw(graph, 2, 3, 2) == navigation_route_target_geometry.route_segment_yaw(graph, 2, 3, 2)


def test_navigation_route_editor_selected_remote_does_not_force_local_edit():
    class Page:
        def __init__(self):
            self.calls = []

        def selected_map_pgm(self):
            return "/opt/data/.robot/map/history_map/2026_06_02/map.pgm"

        def open_route_editor_for_selected_map(self, *, force_local_edit=False):
            self.calls.append(force_local_edit)
            return True

    page = Page()

    assert NavigationPage.open_local_route_editor(page) is True
    assert page.calls == [False]


def test_navigation_route_editor_syncs_remote_route_even_with_local_cache(monkeypatch, tmp_path):
    remote = "/opt/data/.robot/map/history_map/2026_06_02/map.pgm"
    (tmp_path / "map.geojson").write_text("{}", encoding="utf-8")

    class DummyBlocker:
        def __init__(self, _object):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class RoutePage:
        def __init__(self):
            self.history_map_selector = _FakeMapSelector("")
            self.history_map_details = {}
            self.history_map_fetch_slot = _FakeSlot(running=False)
            self.history_route_fetch_slot = _FakeSlot(running=False)
            self.require_remote_route_pull_before_edit = False
            self.synced = []
            self.preview_actions = []
            self.opened = 0

        def sync_selected_history_paths(self, load_existing=False):
            self.synced.append(load_existing)

        def ensure_selected_history_preview(self, action):
            self.preview_actions.append(action)
            self.history_route_fetch_slot.running = True
            return False

        def start_new_history_route(self, open_editor=False):
            raise AssertionError("remote edit should not create a new local route")

        def open_route_editor(self):
            self.opened += 1

    class Page:
        def __init__(self):
            self.map_details = {remote: "目录：2026_06_02"}
            self.route_file_states = {remote: True}
            self.nav_status_note = _FakeLabel()
            self.route_page = RoutePage()
            self.workspace_refreshes = 0

        def selected_map_pgm(self):
            return remote

        def route_action_label(self):
            return "编辑路网"

        def _route_editor_backing_page(self):
            return self.route_page

        def local_preview_dir(self, _remote):
            return tmp_path

        def refresh_workspace_from_page(self):
            self.workspace_refreshes += 1

    monkeypatch.setattr(navigation_route_file_editor, "QSignalBlocker", DummyBlocker)
    page = Page()

    assert NavigationPage.open_route_editor_for_selected_map(page) is True
    assert page.route_page.require_remote_route_pull_before_edit is True
    assert page.route_page.preview_actions == ["edit"]
    assert page.nav_status_note.text == "正在同步远端路网，完成后会自动打开编辑器"
    assert page.workspace_refreshes == 1


def test_navigation_route_editor_status_callback_updates_visible_page():
    class Page:
        def __init__(self):
            self.nav_status_note = _FakeLabel()
            self.workspace_refreshes = 0

        def refresh_workspace_from_page(self):
            self.workspace_refreshes += 1

    page = Page()

    NavigationPage._route_editor_status_changed(page, "远端路网同步失败，请检查 map.geojson 或重新上传", "error")

    assert page.nav_status_note.text == "远端路网同步失败，请检查 map.geojson 或重新上传"
    assert page.workspace_refreshes == 1


def test_navigation_route_editor_backing_page_registers_status_callback():
    source = inspect.getsource(navigation_route_file_editor.NavigationRouteFileEditorMixin._route_editor_backing_page)

    assert "page.route_editor_status_callback = self._route_editor_status_changed" in source


def test_navigation_text_helpers_keep_unknown_code_fallbacks():
    assert navigation.navigation_state_text("999") == "状态999"
    assert navigation.active_substate_text("9") == "子状态9"
    assert navigation.task_status_text("9") == "任务9"
    assert navigation.localization_state_text("9") == "定位9"
    assert navigation.perception_state_text("9") == "感知9"
    assert navigation.navigation_state_text("") == "--"


def test_navigation_plan_stream_output_parser_returns_path_updates():
    buffer, updates = consume_plan_stream_output(
        "",
        "PLAN=GLOBAL TOPIC=/rv/trajectory/global COUNT=2 POINTS=1.000,2.000,0.100;2.000,3.000,0.200\n"
        "PLAN=LOCAL TOPIC=/rv/trajectory/local_transformed COUNT=2 POINTS=1.500,2.500,0.150;1.700,2.700,0.250\n",
    )

    assert buffer == ""
    assert updates == [
        ("GLOBAL", "/rv/trajectory/global", [(1.0, 2.0, 0.1), (2.0, 3.0, 0.2)]),
        ("LOCAL", "/rv/trajectory/local_transformed", [(1.5, 2.5, 0.15), (1.7, 2.7, 0.25)]),
    ]


def test_navigation_obstacle_stream_output_parser_returns_latest_points():
    buffer, updates = ui_navigation_helpers.consume_obstacle_stream_output(
        "OBS=ok TOPIC=/laser_scan FRAME=map COUNT=3 POINTS=1.000,2.000;bad;3.500,-4.250\n",
        "OBS=ok TOPIC=/front_lidar FRAME=map COUNT=1 POINTS=5.000,6.000",
    )

    assert buffer == "OBS=ok TOPIC=/front_lidar FRAME=map COUNT=1 POINTS=5.000,6.000"
    assert updates == [("/laser_scan", [(1.0, 2.0), (3.5, -4.25)])]


def test_navigation_plan_stream_command_subscribes_real_path_topics():
    command = localization.navigation_plan_stream_command(get_product("zg_surround_s100"))

    assert "ps -eo pid=,args=" in command
    assert "marker=dog_remote_tool_plan_stream" in command
    assert "$1 != self" in command
    assert "ssh(pass)?" in command
    assert "python3 -u" in command
    assert "/tmp/dog_remote_tool_plan_stream.py" in command
    assert "dog_remote_tool_plan_stream" in command
    assert command.count("dog_remote_tool_plan_stream") >= 2
    assert "xargs -r kill" in command
    assert "/navigo/bn/cmn/vis/global_path" in command
    assert "/rv/trajectory/global" in command
    assert "/navigo/ps/cmn/vis/planned_path" in command
    assert "/navigo/cs/lpc/vis/best_local_plan" not in command
    assert "/rv/trajectory/local_transformed" not in command
    assert "/navigo/bn/cmn/vis/local_path" not in command
    assert "/navigo/cs/lpc/vis/received_global_plan" not in command
    assert "path_is_drawable" not in command


def test_navigation_obstacle_stream_command_uses_only_laser_scan_and_cleans_stale_streams():
    command = localization.obstacle_stream_command(get_product("zg_surround_s100"))

    assert "marker=dog_remote_tool_obstacle_stream" in command
    assert "/tmp/dog_remote_tool_obstacle_stream.py" in command
    assert "dog_remote_tool_obstacle_stream" in command
    assert "xargs -r kill" in command
    assert "/odom/current_pose" in command
    assert "/laser_scan" in command
    assert "/scan" not in command
    assert "/front_lidar" not in command
    assert "/rs_pointcloud" not in command
    assert "PointCloud2" not in command
    assert "point_cloud2" not in command
    assert "max_points = 480" in command
    assert "min_interval = 0.12" in command
    assert "POINTS=" in command


def test_navigation_camera_overlay_output_parser_returns_fresh_snapshot():
    payload = {
        "width": 1920,
        "height": 1080,
        "global": [[100, 200], [300.5, 400.2]],
        "local": [[900, 500], [910, 510], ["bad", 5]],
        "stamp": 1710000000.5,
        "global_topic": "/navigo/bn/cmn/vis/global_path",
        "local_topic": "/navigo/cs/ppc/vis/received_global_plan",
    }
    line = "NAV_CAMERA_OVERLAY_JSON=" + base64.b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")

    buffer, snapshots = navigation_camera_overlay_ui.consume_navigation_overlay_output("", line + "\n", received_at=123.0)

    assert buffer == ""
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.width == 1920
    assert snapshot.height == 1080
    assert snapshot.global_points == ((100.0, 200.0), (300.5, 400.2))
    assert snapshot.local_points == ((900.0, 500.0), (910.0, 510.0))
    assert snapshot.global_topic == "/navigo/bn/cmn/vis/global_path"
    assert snapshot.local_topic == "/navigo/cs/ppc/vis/received_global_plan"
    assert snapshot.is_fresh(now=123.4)
    assert not snapshot.is_fresh(now=123.7)


def test_navigation_camera_overlay_stream_command_uses_calibration_and_real_topics():
    command = navigation.navigation_camera_overlay_stream_command(get_product("zg_surround_s100"))

    assert navigation_camera_overlay_commands.NAV_CAMERA_OVERLAY_MARKER in command
    assert "marker=dog_remote_tool_nav_camera_overlay_stream" in command
    assert "/tmp/dog_remote_tool_nav_camera_overlay_stream.py" in command
    assert "/bash -c/" not in command
    assert "/ota/calibration_results.yaml" in command
    assert "/odom/current_pose" in command
    assert "/navigo/bn/cmn/vis/global_path" in command
    assert "/navigo/ps/cmn/vis/planned_path" not in command
    assert "CmdVelWithTrajectory" not in command
    assert "/cmd_vel_with_trajectory" not in command
    assert "/navigo/cs/ppc/vis/received_global_plan" in command
    assert "/navigo/cs/lpc/vis/received_global_plan" not in command
    assert "/navigo/cs/lpc/vis/best_local_plan" not in command
    assert "PATH_MAX_AGE_SECONDS = 0.8" in command
    assert "GLOBAL_FORWARD_METERS = 4.0" in command
    assert "PATH_VISUAL_Z_OFFSET = 0.12" in command
    assert "map_point_to_base" in command
    assert "yaw_from_quaternion" in command
    assert "keep_global_base_point" in command
    assert "global_age_ms" in command
    assert "local_age_ms" in command
    assert '"/navigo/cs/ppc/vis/received_global_plan"' in command
    assert "pose_frame_mismatch" not in command
    assert "return path_frame_id(msg)" in command
    assert 'return "base_link_rviz"' not in command
    assert "without changing its shape" in command
    assert "IMAGE_WIDTH - 1.0" not in command
    assert "camera_front_to_lidar_front" in command
    assert "lidar_front_to_imu_front" in command
    assert "imu_front_to_base" in command
    assert "NAV_CAMERA_OVERLAY_JSON=" in command


def test_navigation_camera_view_keeps_rgb_frame_without_path_overlay():
    worker_source = inspect.getsource(navigation_camera_overlay_ui.NavigationCameraWorker)
    run_source = inspect.getsource(navigation_camera_overlay_ui.NavigationCameraWorker.run)
    start_source = inspect.getsource(navigation_camera_overlay_ui.NavigationCameraOverlayMixin.start_navigation_camera_overlay)
    panel_source = inspect.getsource(navigation_camera_overlay_ui.NavigationCameraOverlayMixin._build_navigation_camera_panel)

    assert "_draw_overlay" not in worker_source
    assert "_draw_polyline" not in worker_source
    assert "snapshot.global_points" not in worker_source
    assert "snapshot.local_points" not in worker_source
    assert "overlay_store.latest" not in run_source
    assert "start_navigation_camera_overlay_stream()" not in start_source
    assert "RGB 实时画面" in panel_source


def test_navigation_camera_rtsp_preparation_is_silent_for_user_logs():
    prepare_source = inspect.getsource(navigation_camera_overlay_ui.NavigationCameraOverlayMixin._prepare_navigation_camera_rtsp)
    message_source = inspect.getsource(navigation_camera_overlay_ui.NavigationCameraOverlayMixin.log_navigation_camera_message)
    error_source = inspect.getsource(navigation_camera_overlay_ui.NavigationCameraOverlayMixin.log_navigation_camera_error)

    assert "runner.run" not in prepare_source
    assert "QProcess.startDetached" in prepare_source
    assert ">/dev/null 2>&1" in prepare_source
    assert "runner.output.emit" not in message_source
    assert "nav_camera_status_label" in message_source
    assert "runner.output.emit" in error_source


def test_navigation_camera_worker_retries_until_rtsp_is_ready(monkeypatch):
    class FakeCapture:
        def __init__(self, opened: bool) -> None:
            self.opened = opened
            self.released = False

        def isOpened(self) -> bool:
            return self.opened

        def release(self) -> None:
            self.released = True

    captures = [FakeCapture(False), FakeCapture(True)]
    opened = []

    def fake_open(_cv2, pipeline):
        opened.append(pipeline)
        return captures[len(opened) - 1], f"diag-{len(opened)}"

    monkeypatch.setattr(navigation_camera_overlay_ui.control_video, "_open_gstreamer_capture", fake_open)
    monkeypatch.setattr(navigation_camera_overlay_ui.time, "sleep", lambda _seconds: None)

    worker = navigation_camera_overlay_ui.NavigationCameraWorker(
        "rtsp://192.168.234.1:8554/front",
        navigation_camera_overlay_ui.NavigationOverlayStore(),
    )
    capture, diagnostics = worker._open_capture_with_retry(object())

    assert capture is captures[1]
    assert diagnostics == "diag-2"
    assert captures[0].released is True
    assert len(opened) == 2


def test_navigation_camera_read_failures_trigger_reconnect_by_count_or_time(monkeypatch):
    monkeypatch.setattr(navigation_camera_overlay_ui, "NAV_CAMERA_READ_RECONNECT_FAILURES", 3)
    monkeypatch.setattr(navigation_camera_overlay_ui, "NAV_CAMERA_READ_RECONNECT_SECONDS", 4.0)

    assert navigation_camera_overlay_ui.navigation_camera_read_should_reconnect(2, 10.0, 13.0) is False
    assert navigation_camera_overlay_ui.navigation_camera_read_should_reconnect(3, 10.0, 11.0) is True
    assert navigation_camera_overlay_ui.navigation_camera_read_should_reconnect(1, 10.0, 14.1) is True


def test_navigation_camera_worker_ignores_transient_empty_frames(monkeypatch):
    class FakeCapture:
        def __init__(self, failures: int) -> None:
            self.failures = failures
            self.released = False

        def isOpened(self) -> bool:
            return True

        def read(self):
            if self.failures > 0:
                self.failures -= 1
                return False, None
            return True, np.zeros((2, 2, 3), dtype=np.uint8)

        def release(self) -> None:
            self.released = True

    worker = navigation_camera_overlay_ui.NavigationCameraWorker(
        "rtsp://192.168.234.1:8554/front",
        navigation_camera_overlay_ui.NavigationOverlayStore(),
    )
    capture = FakeCapture(failures=10)
    logs = []
    errors = []

    class FakeCv2:
        COLOR_BGR2RGB = 1

        @staticmethod
        def cvtColor(frame, _code):
            worker.stop()
            return frame

    monkeypatch.setitem(sys.modules, "cv2", FakeCv2)
    monkeypatch.setattr(navigation_camera_overlay_ui.NavigationCameraWorker, "_open_capture_with_retry", lambda _self, _cv2: (capture, ""))
    monkeypatch.setattr(navigation_camera_overlay_ui.time, "sleep", lambda _seconds: None)
    worker.log_ready.connect(lambda label, message: logs.append((label, message)))
    worker.error_ready.connect(lambda label, message: errors.append((label, message)))

    worker.run()

    assert capture.released is True
    assert errors == []
    assert logs == [("导航视角", "RTSP 已连接: rtsp://192.168.234.1:8554/front")]
    sequence, image = worker.latest_frame(0)
    assert sequence == 1
    assert image is not None


def test_navigation_camera_worker_reconnects_after_sustained_empty_frames(monkeypatch):
    class FakeCapture:
        def __init__(self, frames) -> None:
            self.frames = list(frames)
            self.released = False

        def isOpened(self) -> bool:
            return True

        def read(self):
            if not self.frames:
                return False, None
            frame = self.frames.pop(0)
            if frame is None:
                return False, None
            return True, frame

        def release(self) -> None:
            self.released = True

    worker = navigation_camera_overlay_ui.NavigationCameraWorker(
        "rtsp://192.168.234.1:8554/front",
        navigation_camera_overlay_ui.NavigationOverlayStore(),
    )
    first_capture = FakeCapture([None, None, None])
    second_capture = FakeCapture([np.zeros((2, 2, 3), dtype=np.uint8)])
    captures = [first_capture, second_capture]
    logs = []

    class FakeCv2:
        COLOR_BGR2RGB = 1

        @staticmethod
        def cvtColor(frame, _code):
            worker.stop()
            return frame

    monkeypatch.setitem(sys.modules, "cv2", FakeCv2)
    monkeypatch.setattr(navigation_camera_overlay_ui, "NAV_CAMERA_READ_RECONNECT_FAILURES", 2)
    monkeypatch.setattr(navigation_camera_overlay_ui, "NAV_CAMERA_READ_RECONNECT_SECONDS", 999.0)
    monkeypatch.setattr(
        navigation_camera_overlay_ui.NavigationCameraWorker,
        "_open_capture_with_retry",
        lambda _self, _cv2: (captures.pop(0), ""),
    )
    monkeypatch.setattr(navigation_camera_overlay_ui.time, "sleep", lambda _seconds: None)
    worker.log_ready.connect(lambda label, message: logs.append((label, message)))

    worker.run()

    assert first_capture.released is True
    assert second_capture.released is True
    assert ("导航视角", "视频已重连。") in logs
    sequence, image = worker.latest_frame(0)
    assert sequence == 1
    assert image is not None


def test_navigation_camera_worker_does_not_report_read_failure_after_stop(monkeypatch):
    class FakeCapture:
        def __init__(self) -> None:
            self.released = False

        def isOpened(self) -> bool:
            return True

        def read(self):
            worker.stop()
            return False, None

        def release(self) -> None:
            self.released = True

    worker = navigation_camera_overlay_ui.NavigationCameraWorker(
        "rtsp://192.168.234.1:8554/front",
        navigation_camera_overlay_ui.NavigationOverlayStore(),
    )
    capture = FakeCapture()
    errors = []

    class FakeCv2:
        COLOR_BGR2RGB = 1

    monkeypatch.setitem(sys.modules, "cv2", FakeCv2)
    monkeypatch.setattr(navigation_camera_overlay_ui.NavigationCameraWorker, "_open_capture_with_retry", lambda _self, _cv2: (capture, ""))
    worker.error_ready.connect(lambda label, message: errors.append((label, message)))

    worker.run()

    assert errors == []
    assert capture.released is True


def test_navigation_camera_worker_reports_sustained_empty_frames_and_recovers(monkeypatch):
    class FakeCapture:
        def __init__(self) -> None:
            self.reads = 0

        def isOpened(self) -> bool:
            return True

        def read(self):
            self.reads += 1
            if self.reads <= navigation_camera_overlay_ui.NAV_CAMERA_READ_FAILURE_REPORT_COUNTS[0]:
                return False, None
            return True, np.zeros((2, 2, 3), dtype=np.uint8)

        def release(self) -> None:
            return None

    worker = navigation_camera_overlay_ui.NavigationCameraWorker(
        "rtsp://192.168.234.1:8554/front",
        navigation_camera_overlay_ui.NavigationOverlayStore(),
    )
    capture = FakeCapture()
    logs = []
    errors = []

    class FakeCv2:
        COLOR_BGR2RGB = 1

        @staticmethod
        def cvtColor(frame, _code):
            worker.stop()
            return frame

    monkeypatch.setitem(sys.modules, "cv2", FakeCv2)
    monkeypatch.setattr(navigation_camera_overlay_ui.NavigationCameraWorker, "_open_capture_with_retry", lambda _self, _cv2: (capture, ""))
    monkeypatch.setattr(navigation_camera_overlay_ui.time, "sleep", lambda _seconds: None)
    worker.log_ready.connect(lambda label, message: logs.append((label, message)))
    worker.error_ready.connect(lambda label, message: errors.append((label, message)))

    worker.run()

    assert errors == [("导航视角", "RTSP 读取失败(90)")]
    assert logs[-1] == ("导航视角", "导航视角已恢复")


def test_navigation_pose_stream_command_cleans_stale_local_streams():
    command = localization.pose_stream_command(get_product("zg_surround_s100"))

    assert "ps -eo pid=,args=" in command
    assert "marker=dog_remote_tool_pose_stream" in command
    assert "$1 != self" in command
    assert "ssh(pass)?" in command
    assert '$2 ~ /(^|\\/)ssh(pass)?$/' in command
    assert '$2 ~ /(^|\\/)python3$/' in command
    assert '$3 == "-u"' in command
    assert '$4 == "-"' in command
    assert "/tmp/dog_remote_tool_pose_stream.py" in command
    assert "dog_remote_tool_pose_stream" in command
    assert command.count("dog_remote_tool_pose_stream") >= 2
    assert "xargs -r kill" in command


def test_cleanup_navigation_tool_helpers_command_targets_only_tool_residue():
    spec = navigation.cleanup_navigation_tool_helpers_command(get_product("zg_surround_s100"))

    assert spec.title == "清理工具导航临时资源"
    assert spec.dangerous is False
    assert spec.concurrency == "parallel"
    assert spec.locks == ("navigation-cleanup",)
    assert "dog_remote_tool_pose_stream" in spec.command
    assert "dog_remote_tool_plan_stream" in spec.command
    assert "dog_remote_tool_nav_camera_overlay_stream" in spec.command
    assert "dog_remote_nav_release_watch.log" not in spec.command
    assert "dog_remote_start_navigation_helper.pid" in spec.command
    assert "dog_remote_nav_mode_switch_helper.pid" not in spec.command
    assert "ros2cli.daemon.daemonize" not in spec.command
    assert "清理 Dog Remote Tool 导航临时进程" not in spec.command
    assert "Dog Remote Tool 导航临时资源清理完成" not in spec.command
    assert "[CLEAN] stopping" not in spec.command

    daemon_spec = navigation.cleanup_navigation_tool_helpers_command(get_product("zg_surround_s100"), include_ros_daemon=True)

    assert daemon_spec.dangerous is True
    assert "ros2cli.daemon.daemonize" in daemon_spec.command
    assert "停止当前用户 ROS 2 后台服务" not in daemon_spec.command


def test_navigation_detached_cleanup_suppresses_terminal_output():
    source = inspect.getsource(navigation_lifecycle.NavigationLifecycleMixin.cleanup_navigation_tool_helpers_detached)

    assert ">/dev/null 2>&1" in source


def test_navigation_map_failure_summary_filters_tool_stream_process_noise():
    output = "\n".join(
        [
            "[ERROR] 导航地图加载失败",
            "256624 bash bash -c IFS= read -r DOG_REMOTE_SUDO_PASS python3 -u - <<'PY' import rclpy node = rclpy.create_node('dog_remote_tool_plan_stream')",
            "262078 bash bash -c IFS= read -r DOG_REMOTE_SUDO_PASS python3 -u - <<'PY' import rclpy node = rclpy.create_node('dog_remote_tool_pose_stream')",
            "262080 bash bash -c IFS= read -r DOG_REMOTE_SUDO_PASS python3 -u - <<'PY' import rclpy node = rclpy.create_node('dog_remote_tool_nav_camera_overlay_stream')",
            "[INFO] 相关 ROS 节点",
            "/robot_localization",
            "[ERROR] /load_map_service 调用退出码: 1",
        ]
    )

    summary = _compact_failure_lines(output)

    assert "导航地图加载失败" in summary
    assert "/load_map_service 调用退出码" in summary
    assert "dog_remote_tool_plan_stream" not in summary
    assert "dog_remote_tool_nav_camera_overlay_stream" not in summary
    assert "python3 -u" not in summary


def test_navigation_logs_strip_ansi_escape_sequences_before_fullscreen_display():
    page = _FakeNavigationActionPage()

    NavigationPage.capture_navigation_log(
        page,
        "\x1b[2m2026-06-04T11:47:53Z\x1b[0m \x1b[33m WARN\x1b[0m zenoh\n"
        "\u241b[31m[ERROR]\u241b[0m load map failed\n",
    )

    assert page.navigation_log_lines == [
        "2026-06-04T11:47:53Z  WARN zenoh",
        "[ERROR] load map failed",
    ]
    assert _sanitize_log_line("\x1b[2mabc\x1b[0m") == "abc"
    assert _sanitize_log_line("\u241b[33mWARN\u241b[0m") == "WARN"


def test_navigation_stream_slots_use_default_stop_timeout():
    source = inspect.getsource(NavigationPage.__init__)
    assert "self.pose_stream_slot = ProcessSlot(self, reserve_runner=False)" in source
    assert "self.plan_stream_slot = ProcessSlot(self, reserve_runner=False)" in source
    assert "stop_timeout_ms=300" not in source


def test_navigation_home_does_not_expose_navigation_parameter_controls():
    source = inspect.getsource(NavigationPage.__init__)
    layout_source = inspect.getsource(navigation_layout.NavigationLayoutMixin)
    page_source = inspect.getsource(NavigationPage)

    assert "self.body.addWidget(advanced_box)" not in source
    assert "_build_advanced_settings_box" not in layout_source
    assert "NavigationConstraintControlsMixin" not in page_source
    assert not hasattr(navigation, "NAVIGATION_CONSTRAINT_PARAMS")
    assert not hasattr(navigation, "navigation_constraints_status_command")
    assert not hasattr(navigation, "set_navigation_constraint_command")
    assert not hasattr(navigation, "restart_navigation_nodes_command")
    assert "navigation_constraint" not in page_source
    assert "collision_radius_slot" not in page_source


def test_navigation_home_only_shows_history_preview():
    source = inspect.getsource(NavigationPage.__init__)

    assert "nav_box.hide()" in source
    assert "self.body.addWidget(nav_box)" not in source
    assert 'QGroupBox("历史图预览")' in source
    assert 'QLabel("历史地图预览")' in source
    assert "self.body.addWidget(history_box, 1)" in source
    assert "self.body.addWidget(advanced_box)" not in source
    assert "history_header.addWidget(self.history_route_editor_button)" not in source
    assert "history_header.addWidget(self.history_upload_route_button)" not in source
    assert "self.history_route_editor_button.hide()" in source
    assert "self.history_upload_route_button.hide()" in source


def test_navigation_profile_change_restarts_active_page_streams(monkeypatch):
    scheduled = []
    monkeypatch.setattr(
        "dog_remote_tool.ui.pages.navigation.page.QTimer.singleShot",
        lambda delay, callback: scheduled.append((delay, callback)),
    )
    page = _FakeNavigationRefreshPage(active=True)
    page.nav_map = _FakeWorkspaceCanvas()
    stop_calls = []
    refresh_calls = []
    pose_calls = []
    plan_calls = []
    page._stop_refresh_processes = lambda clear_maps: stop_calls.append(clear_maps)
    page.refresh_map_list = lambda: refresh_calls.append(True)
    page.start_pose_stream = lambda: pose_calls.append(True)
    page.start_plan_stream = lambda: plan_calls.append(True)

    NavigationPage.on_navigation_profile_changed(page, get_product("zg_surround_s100"))

    assert page.stop_navigation_camera_overlay_calls == 1
    assert stop_calls == [True]
    assert refresh_calls == [True]
    assert pose_calls == [True]
    assert plan_calls == [True]
    assert (600, page.start_navigation_camera_overlay) in scheduled


def test_navigation_marker_scale_tracks_map_zoom_with_cap():
    label = NavigationMapLabel.__new__(NavigationMapLabel)

    label.zoom_scale = 1.0
    assert NavigationMapLabel._marker_scale(label) == 1.0

    label.zoom_scale = 4.0
    assert NavigationMapLabel._marker_scale(label) == 2.0

    label.zoom_scale = 8.0
    assert NavigationMapLabel._marker_scale(label) == 2.4


def test_navigation_route_graph_draws_direction_arrows_and_direction_colors(monkeypatch):
    label = NavigationMapLabel.__new__(NavigationMapLabel)
    label.route_target_node_ids = []
    label._marker_scale = lambda: 1.0
    label._world_to_widget = lambda x, y: QPointF(float(x) * 100.0, float(y) * 100.0)
    label._draw_route_target_path = lambda _painter: None
    lines = []
    arrows = []

    def record_line(_painter, _points, color, _width):
        lines.append(color.name())

    def record_arrow(_painter, points, color, _scale):
        arrows.append((points[0].x(), points[-1].x(), color.name()))

    monkeypatch.setattr(label, "_draw_route_visual_polyline", record_line)
    monkeypatch.setattr(label, "_draw_route_direction_arrow", record_arrow)

    class FakePainter:
        def save(self):
            pass

        def restore(self):
            pass

        def font(self):
            return QFont()

        def setFont(self, _font):
            pass

    label.route_graph = route_network.RouteGraph(
        edges={1: route_network.RouteEdge(1, 1, 2, [(0.0, 0.0), (40.0, 0.0)], "forward")}
    )

    NavigationMapLabel._draw_route_graph(label, FakePainter())

    assert lines == ["#2563eb"]
    assert arrows == [(0.0, 4000.0, "#2563eb")]

    lines.clear()
    arrows.clear()
    label.route_graph.edges[1].direction = "both"

    NavigationMapLabel._draw_route_graph(label, FakePainter())

    assert lines == ["#0f766e"]
    assert arrows == [(0.0, 4000.0, "#0f766e"), (4000.0, 0.0, "#0f766e")]


def test_navigation_route_target_path_is_translucent():
    label = NavigationMapLabel.__new__(NavigationMapLabel)
    label.route_graph = route_network.RouteGraph(
        nodes={
            1: route_network.RouteNode(1, 0.0, 0.0),
            2: route_network.RouteNode(2, 40.0, 0.0),
        },
        edges={1: route_network.RouteEdge(1, 1, 2, [(0.0, 0.0), (40.0, 0.0)], "both")},
    )
    label.route_target_node_ids = [1, 2]
    label.robot_pose = None
    label._marker_scale = lambda: 1.0
    label._world_to_widget = lambda x, y: QPointF(float(x) * 100.0, float(y) * 100.0)

    class FakePainter:
        def __init__(self):
            self.current_pen = None
            self.current_brush = None
            self.line_alphas = []
            self.polygon_brush_alphas = []

        def save(self):
            pass

        def restore(self):
            pass

        def setPen(self, pen):
            self.current_pen = pen

        def setBrush(self, brush):
            self.current_brush = brush

        def drawLine(self, *_args):
            self.line_alphas.append(self.current_pen.color().alpha())

        def drawPolygon(self, *_args):
            self.polygon_brush_alphas.append(self.current_brush.alpha())

    painter = FakePainter()

    NavigationMapLabel._draw_route_target_path(label, painter)

    assert 150 in painter.line_alphas
    assert 175 in painter.polygon_brush_alphas


def test_navigation_route_target_path_coordinates_follow_shortest_path():
    label = NavigationMapLabel.__new__(NavigationMapLabel)
    label.route_graph = route_network.RouteGraph(
        nodes={
            1: route_network.RouteNode(1, 0.0, 0.0),
            2: route_network.RouteNode(2, 1.0, 0.0),
            3: route_network.RouteNode(3, 2.0, 0.0),
        },
        edges={
            10: route_network.RouteEdge(10, 1, 2, [(0.0, 0.0), (1.0, 0.0)], direction="both"),
            11: route_network.RouteEdge(11, 2, 3, [(1.0, 0.0), (1.5, 0.2), (2.0, 0.0)], direction="both"),
        },
    )
    label.route_target_node_ids = [1, 3]
    label.robot_pose = None

    assert NavigationMapLabel._route_target_path_coordinates(label) == [
        [(0.0, 0.0), (1.0, 0.0), (1.5, 0.2), (2.0, 0.0)]
    ]

    label.route_target_node_ids = [3, 1]

    assert NavigationMapLabel._route_target_path_coordinates(label) == [
        [(2.0, 0.0), (1.5, 0.2), (1.0, 0.0), (0.0, 0.0)]
    ]


def test_navigation_route_target_path_coordinates_start_from_robot_pose_for_single_target():
    label = NavigationMapLabel.__new__(NavigationMapLabel)
    label.route_graph = route_network.RouteGraph(
        nodes={
            1: route_network.RouteNode(1, 0.0, 0.0),
            2: route_network.RouteNode(2, 1.0, 0.0),
            3: route_network.RouteNode(3, 2.0, 0.0),
        },
        edges={
            10: route_network.RouteEdge(10, 1, 2, [(0.0, 0.0), (1.0, 0.0)], direction="both"),
            11: route_network.RouteEdge(11, 2, 3, [(1.0, 0.0), (1.5, 0.2), (2.0, 0.0)], direction="both"),
        },
    )
    label.robot_pose = (0.1, 0.0, 0.0)
    label.route_target_node_ids = [3]

    assert NavigationMapLabel._route_target_path_coordinates(label) == [
        [(0.1, 0.0), (0.0, 0.0), (1.0, 0.0), (1.5, 0.2), (2.0, 0.0)]
    ]


def test_navigation_route_target_path_coordinates_prepends_robot_pose_for_multiple_targets():
    label = NavigationMapLabel.__new__(NavigationMapLabel)
    label.route_graph = route_network.RouteGraph(
        nodes={
            1: route_network.RouteNode(1, 0.0, 0.0),
            2: route_network.RouteNode(2, 1.0, 0.0),
            3: route_network.RouteNode(3, 2.0, 0.0),
        },
        edges={
            10: route_network.RouteEdge(10, 1, 2, [(0.0, 0.0), (1.0, 0.0)], direction="both"),
            11: route_network.RouteEdge(11, 2, 3, [(1.0, 0.0), (2.0, 0.0)], direction="both"),
        },
    )
    label.robot_pose = (0.1, 0.0, 0.0)
    label.route_target_node_ids = [2, 3]

    assert NavigationMapLabel._route_target_path_coordinates(label) == [
        [(0.1, 0.0), (0.0, 0.0), (1.0, 0.0)],
        [(1.0, 0.0), (2.0, 0.0)],
    ]


def test_alg_manager_ws_request_payload_uses_verified_head_data_protocol():
    payload = navigation.alg_manager_ws_request_payload("get_nav_status", 9301)

    assert json.loads(payload) == {
        "head": {
            "type": "app_req",
            "time_stamp": 0,
            "source": "app",
            "frame_count": 9301,
        },
        "data": {"req_func": "get_nav_status"},
    }
    assert '"header"' not in payload


def test_alg_manager_start_multi_nav_by_points_payload_uses_app_pose_array():
    payload = navigation.alg_manager_start_multi_nav_by_points_payload(
        "2026_06_23_16_26_59",
        [(0.0, 0.0, 0.0), (1.0, 0.0, math.pi)],
        9303,
    )

    parsed = json.loads(payload)
    value = parsed["data"]["req_func"]["start_multi_nav_by_points"]

    assert parsed["head"]["frame_count"] == 9303
    assert value[0] == "2026_06_23_16_26_59"
    assert value[1] == "dog_remote_points"
    assert value[2][0]["position"] == {"x": 0.0, "y": 0.0, "z": 0.0}
    assert value[2][1]["orientation"]["z"] == pytest.approx(1.0)
    assert value[2][1]["orientation"]["w"] == pytest.approx(0.0)


def test_alg_manager_start_multi_nav_task_route_value_uses_route_goal_task():
    value = navigation.alg_manager_start_multi_nav_task_route_value(
        "2026_06_27_17_38_25",
        "/ota/alg_data/map/history_map/2026_06_27_17_38_25/map.geojson",
        [(0.0, 0.0, 9.0), (0.0, 1.0, 9.0), (1.0, 1.0, 9.0)],
        0.4,
        0.25,
    )

    tasks = value["tasks"]
    task = tasks[0]

    assert value["map_id"] == "2026_06_27_17_38_25"
    assert len(tasks) == 3
    assert task["type"] == "goal"
    assert task["map_type"] == "route"
    assert task["goal_task_type"] == "route"
    assert task["map_path"] == "/ota/alg_data/map/history_map/2026_06_27_17_38_25/map.geojson"
    for route_task in tasks:
        assert route_task["goal"] == route_task["goals"][0]
        assert len(route_task["goals"]) == 1
    assert tasks[0]["goal"]["orientation"]["z"] == pytest.approx(math.sin(math.pi / 4.0))
    assert tasks[1]["goal"]["orientation"]["z"] == pytest.approx(0.0)
    assert task["speed"] == {"x": 0.4, "y": 0.0, "z": 1.2}
    assert task["goal_tolerance"] == {"x": 0.25, "y": 0.25, "theta": 0.1}


def test_map_id_from_map_path_uses_history_directory_name():
    assert navigation.map_id_from_map_path("/opt/data/.robot/map/history_map/2026_06_02/map.pcd") == "2026_06_02"
    assert navigation.map_id_from_map_path("/ota/alg_data/map/map.pcd") == "map"


def test_zg_navigation_start_always_prepares_body_bridge_before_goal_command():
    command = navigation_helper_control._navigation_start_ssh_command(
        get_product("zg_lidar_nx"),
        "echo run_goal",
        require_control_switch=True,
    )

    assert "robot-launch start robot_roamerx" in command
    assert "/robot_control_server/current_requester_info" in command
    assert "enable_forward_cmd_vel" in command
    assert "timeout 3s ros2 param get /robot_roamerx enable_forward_cmd_vel" in command
    assert "/opt/robot/install/robot_roamerx/share/robot_roamerx/config/zsm/robot_roamerx.yaml" in command
    assert "robot-launch restart robot_roamerx" in command
    assert "复用已预热控制权" in command
    assert "导航服务已就绪，直接下发目标" not in command
    assert command.rindex("robot-launch start robot_roamerx") < command.rindex("echo run_goal")
    assert command.index("enable_forward_cmd_vel") < command.index("dog_remote_robot_roamerx_control")
    assert subprocess.run(["bash", "-n", "-c", command]).returncode == 0


def test_navigation_arc_with_map_script_reuses_common_app_ws_helpers():
    common = arc_app_ws.common_arc_app_ws_python()
    script = navigation_arc_commands._arc_with_map_app_ws_python()

    assert script.startswith(common)
    assert "def send_text(sock, obj):" in script
    assert "def recv_text(sock):" in script
    assert "系统应用通道正被其他任务占用" in script
    assert "系统应用通道暂不可用" in script
    assert "is_app_channel_busy()" in script
    assert "start_arc_with_map" in script
    assert "start_arc_align_coarse" in script
    assert "已进入对准阶段，继续进桩" in script


def test_navigation_ros_payloads_are_valid_yaml():
    payloads = [
        navigation._initialize_payload("/ota/alg_data/map/map.yaml", 1),
        navigation._goal_payload("/ota/alg_data/map/map.pcd", 1.0, 2.0, 0.5, 0.4, 0.25),
        navigation._command_payload(4),
    ]

    parsed = [yaml.safe_load(payload) for payload in payloads]

    assert parsed[0]["cmd"] == 0
    assert parsed[0]["tasks"][0]["task_type"] == 2
    assert parsed[1]["cmd"] == 1
    assert parsed[1]["tasks"][0]["task_type"] == 3
    assert parsed[1]["tasks"][0]["goal_task"]["map_type"] == 1
    assert parsed[1]["tasks"][0]["goal_task"]["map_path"] == "/ota/alg_data/map/map.yaml"
    assert parsed[-1]["header"]["frame_id"] == "map"


def test_route_broker_value_orients_each_target_toward_next_route_node():
    value = navigation.alg_manager_start_multi_nav_task_route_value(
        "map_a",
        "/ota/alg_data/route/default.geojson",
        [(0.0, 0.0, 9.0), (0.0, 1.0, 9.0), (1.0, 1.0, 9.0)],
        0.4,
        0.25,
    )

    tasks = value["tasks"]
    first = tasks[0]["goal"]["orientation"]
    second = tasks[1]["goal"]["orientation"]
    third = tasks[2]["goal"]["orientation"]

    assert first["z"] == pytest.approx(math.sin(math.pi / 4.0))
    assert first["w"] == pytest.approx(math.cos(math.pi / 4.0))
    assert second["z"] == pytest.approx(0.0)
    assert second["w"] == pytest.approx(1.0)
    assert third["z"] == pytest.approx(0.0)
    assert third["w"] == pytest.approx(1.0)


def test_route_broker_value_preserves_float_coordinates():
    value = navigation.alg_manager_start_multi_nav_task_route_value(
        "map_a",
        "/ota/alg_data/route/default.geojson",
        [(2.806028840, -7.476321017, 0.0)],
        0.4,
        0.25,
    )

    assert value["tasks"][0]["goals"][0]["position"] == {"x": 2.80602884, "y": -7.476321017, "z": 0.0}


def test_summarize_status_blocks_until_map_localization_and_nav_stack_ready():
    output = "\n".join(
        [
            "STATUS=blocked",
            "TEXT=等待连续定位",
            "MAP_PCD=/opt/data/.robot/map/map.pcd",
            "MAP_OK=1",
            "LOAD_MAP_SERVICE=1",
            "NAV_PROCESS=1",
            "START_NAV_SUBSCRIBERS=1",
            "LOCALIZATION_TOPIC=/localization_state",
            "LOCALIZATION_CODE=2",
            "LOCALIZATION_READY=0",
            "CURRENT_POSE_PUBLISHERS=0",
            "LOCALIZATION_ODOM_PUBLISHERS=1",
            "PERCEPTION_CODE=3",
            "PERCEPTION_READY=1",
            "READY_LIFECYCLE_SERVICES=6",
            "MISSING_LIFECYCLE_SERVICES=/planner_server/get_state",
        ]
    )

    state, text, detail, values = navigation.summarize_status(output)

    assert state == "blocked"
    assert text == "等待连续定位"
    assert values["LOCALIZATION_CODE"] == "2"
    assert "地图：可用" in detail
    assert "/load_map_service" not in detail
    assert "定位：初始定位/重定位中" in detail
    assert "感知：运行正常" in detail
    assert "未就绪：/planner_server/get_state" in detail


def test_summarize_status_treats_zg_status_six_active_description_as_localized():
    output = "\n".join(
        [
            "STATUS=ready",
            "TEXT=导航待命",
            "NAV_PROCESS=1",
            "START_NAV_SUBSCRIBERS=1",
            "LOCALIZATION_TOPIC=/robot_slam/localization_state",
            "LOCALIZATION_CODE=6",
            "LOCALIZATION_DESC=Active: localization running normally.",
            "LOCALIZATION_READY=1",
            "LASER_SCAN_STAMP_AGE_MS=498",
            "CURRENT_POSE_STAMP_AGE_MS=482",
            "LOCALIZATION_STATE_STAMP_AGE_MS=271",
        ]
    )

    state, text, detail, _values = navigation.summarize_status(output)

    assert state == "ready"
    assert text == "导航待命"
    assert "定位：连续定位正常" in detail
    assert "数据延迟：laser_scan=498ms，current_pose=482ms，localization_state=271ms" in detail


def test_summarize_status_treats_robot_slam_state_100_as_localized():
    output = "\n".join(
        [
            "STATUS=ready",
            "TEXT=导航待命",
            "LOCALIZATION_TOPIC=/robot_slam/localization_state",
            "LOCALIZATION_CODE_FIELD=state",
            "LOCALIZATION_CODE=100",
            "LOCALIZATION_DESC=The localization system is normal.",
            "LOCALIZATION_READY=1",
        ]
    )

    state, text, detail, _values = navigation.summarize_status(output)

    assert state == "ready"
    assert text == "导航待命"
    assert "定位：连续定位正常" in detail


def test_fast_localization_probe_uses_alg_without_robot_slam_sample():
    shell = navigation_probe.fast_localization_state_probe_shell(get_product("xg2_s100"))

    assert "get_loc_status" in shell
    assert 'timeout 3s ros2 topic echo --once "$topic"' not in shell


def test_summarize_status_treats_robot_slam_state_six_as_localized_without_description():
    output = "\n".join(
        [
            "STATUS=ready",
            "TEXT=导航待命",
            "LOCALIZATION_TOPIC=/robot_slam/localization_state",
            "LOCALIZATION_CODE_FIELD=state",
            "LOCALIZATION_CODE=6",
            "LOCALIZATION_READY=1",
        ]
    )

    state, text, detail, _values = navigation.summarize_status(output)

    assert state == "ready"
    assert text == "导航待命"
    assert "定位：连续定位正常" in detail


def test_summarize_status_reports_active_navigation_state_and_task():
    output = "\n".join(
        [
            "STATUS=active",
            "TEXT=导航执行中",
            "MAP_OK=1",
            "LOAD_MAP_SERVICE=1",
            "NAV_PROCESS=1",
            "START_NAV_SUBSCRIBERS=1",
            "LOCALIZATION_CODE=3",
            "LOCALIZATION_READY=1",
            "PERCEPTION_CODE=3",
            "PERCEPTION_READY=1",
            "NAV_STATE=2",
            "NAV_ACTIVE_SUBSTATE=1",
            "NAV_TASK_STATUS=2",
            "NAV_CURRENT_TASK_IDX=0",
            "NAV_DISTANCE_FROM_START=1.25",
            "NAV_ESTIMATED_DISTANCE_REMAINING=3.5",
            "NAV_ESTIMATED_TIME_REMAINING_SEC=12",
            "NAV_ERRORS_PUBLISHERS=1",
            "NAV_ERRORS_SUMMARY=error_code: 0",
            "DETECTION2D_PUBLISHERS=1",
            "DETECTION2D_READY=1",
            "NAVIGATION_CMD_PUBLISHERS=1",
            "NAVIGATION_CMD_SUBSCRIBERS=1",
            "NAVIGATION_CMD_VEL=vx=0.300 vy=0.000 wz=0.100",
            "HANDLE_VEL_PUBLISHERS=1",
            "HANDLE_VEL_SUBSCRIBERS=1",
            "HANDLE_VEL_VEL=vx=0.300 vy=0.000 wz=0.100",
            "CMD_VEL_PUBLISHERS=1",
            "CMD_VEL_SUBSCRIBERS=1",
            "CMD_VEL_VEL=vx=0.280 vy=0.000 wz=0.080",
            "ROBOT_CONTROL_SERVER_NAV_POSE_PUBLISHERS=1",
            "ROBOT_CONTROL_SERVER_NAV_POSE_SUBSCRIBERS=1",
            "ROBOT_ROAMERX_IS_IN_NAV_CONTROL_PUBLISHERS=1",
            "ROBOT_ROAMERX_IS_IN_NAV_CONTROL_SUBSCRIBERS=0",
            "ROBOT_CONTROL_SERVER_MC_STATE_PUBLISHERS=1",
            "ROBOT_CONTROL_SERVER_MC_STATE_SUBSCRIBERS=2",
        ]
    )

    state, text, detail, _values = navigation.summarize_status(output)

    assert state == "active"
    assert text == "导航执行中"
    assert "导航状态：导航执行中" in detail
    assert "任务：执行中" not in detail
    assert "剩余 3.5 m" not in detail
    assert "状态码：" not in detail
    assert "技术状态：" not in detail
    assert "state=2" not in detail
    assert "task_status=2" not in detail
    assert "导航错误：error_code: 0" in detail
    assert "障碍物感知：正常" in detail
    assert "运动输出：有速度输出" in detail
    assert "底盘控制：已连接" in detail


def test_summarize_status_uses_partial_probe_output_on_nonzero_exit():
    output = "\n".join(
        [
            "MAP_OK=1",
            "LOAD_MAP_SERVICE=1",
            "NAV_PROCESS=1",
            "START_NAV_SUBSCRIBERS=0",
        ]
    )

    state, text, detail, values = navigation.summarize_status(output, exit_code=255)

    assert state == "blocked"
    assert text == "导航状态通道异常"
    assert values["STATUS"] == "blocked"
    assert "导航服务：未启动" in detail


def test_summarize_status_accepts_current_navigation_state_codes():
    output = "\n".join(
        [
            "STATUS=active",
            "TEXT=导航执行中",
            "NAV_STATE=100",
            "NAV_TASK_STATUS=2",
            "NAV_PROCESS=1",
            "START_NAV_SUBSCRIBERS=1",
            "LOCALIZATION_READY=1",
        ]
    )

    state, text, detail, _values = navigation.summarize_status(output)

    assert state == "active"
    assert text == "导航执行中"
    assert "导航状态：导航执行中" in detail
    assert "任务：执行中" not in detail
    assert "state=100" not in detail


def _derive_navigation_status(**values: str) -> dict[str, str]:
    assignments = "; ".join(f"{key}={shlex.quote(str(value))}" for key, value in values.items())
    output = subprocess.check_output(
        ["bash", "-lc", assignments + "; " + navigation_probe.status_derivation_shell()],
        text=True,
    )
    return navigation.parse_key_values(output)


def test_navigation_status_derivation_gates_idle_and_terminal_states_on_current_map_readiness():
    blocked_idle = _derive_navigation_status(
        NAV_STATE="0",
        MAP_OK="0",
        LOAD_MAP_SERVICE="1",
        NAV_PROCESS="1",
        START_NAV_SUBSCRIBERS="1",
        LOCALIZATION_READY="1",
    )
    blocked_success = _derive_navigation_status(
        NAV_STATE="5",
        MAP_OK="0",
        LOAD_MAP_SERVICE="1",
        NAV_PROCESS="1",
        START_NAV_SUBSCRIBERS="1",
        LOCALIZATION_READY="1",
    )
    ready_success = _derive_navigation_status(
        NAV_STATE="5",
        MAP_OK="1",
        LOAD_MAP_SERVICE="1",
        NAV_PROCESS="1",
        START_NAV_SUBSCRIBERS="1",
        LOCALIZATION_READY="1",
    )
    active = _derive_navigation_status(
        NAV_STATE="100",
        NAV_ACTIVE_SUBSTATE="1",
        MAP_OK="0",
        LOAD_MAP_SERVICE="0",
        NAV_PROCESS="0",
        START_NAV_SUBSCRIBERS="0",
        LOCALIZATION_READY="0",
    )
    blocked_active = _derive_navigation_status(
        NAV_STATE="2",
        NAV_ACTIVE_SUBSTATE="2",
        MAP_OK="1",
        LOAD_MAP_SERVICE="1",
        NAV_PROCESS="1",
        START_NAV_SUBSCRIBERS="1",
        LOCALIZATION_READY="1",
    )
    active_task_on_initializing_state = _derive_navigation_status(
        NAV_STATE="1",
        NAV_TASK_STATUS="2",
        MAP_OK="1",
        LOAD_MAP_SERVICE="1",
        NAV_PROCESS="1",
        START_NAV_SUBSCRIBERS="1",
        LOCALIZATION_READY="1",
    )
    paused_task_on_legacy_standby_state = _derive_navigation_status(
        NAV_STATE="1",
        NAV_TASK_STATUS="3",
        MAP_OK="1",
        LOAD_MAP_SERVICE="1",
        NAV_PROCESS="1",
        START_NAV_SUBSCRIBERS="1",
        LOCALIZATION_READY="1",
    )
    ready_legacy_standby = _derive_navigation_status(
        NAV_STATE="1",
        MAP_OK="1",
        LOAD_MAP_SERVICE="1",
        NAV_PROCESS="1",
        START_NAV_SUBSCRIBERS="1",
        LOCALIZATION_READY="1",
    )

    assert blocked_idle == {"STATUS": "blocked", "TEXT": "地图缺失"}
    assert blocked_success == {"STATUS": "blocked", "TEXT": "地图缺失"}
    assert ready_success == {"STATUS": "success", "TEXT": "导航已到达"}
    assert active == {"STATUS": "active", "TEXT": "避障中"}
    assert blocked_active == {"STATUS": "active", "TEXT": "导航受阻"}
    assert active_task_on_initializing_state == {"STATUS": "active", "TEXT": "导航执行中"}
    assert paused_task_on_legacy_standby_state == {"STATUS": "paused", "TEXT": "导航暂停"}
    assert ready_legacy_standby == {"STATUS": "ready", "TEXT": "导航待命"}


def test_fast_status_probe_reads_remote_navigation_state():
    command = navigation_probe.fast_probe_status_inner(get_product("zg_lidar_nx"), "/opt/data/.robot/map/map.pcd")

    assert "dog_remote_fast_nav_state_probe" in command
    assert "from robots_dog_msgs.msg import NavigationState" in command
    assert 'create_subscription(NavigationState, "/navigation_state"' in command
    assert "NAV_TASK_STATUS" in command


def test_start_goal_command_uses_app_start_nav():
    spec = navigation.start_goal_command(
        get_product("xg2_s100"),
        "/opt/data/.robot/map/map.pcd",
        1.0,
        2.0,
        0.5,
        0.4,
        0.25,
    )

    assert spec.title == "发送导航目标"
    assert spec.dangerous is True
    assert spec.concurrency == "parallel"
    assert spec.locks == ("navigation-command",)
    assert "机器人可能开始移动" in spec.description
    assert "正在提交导航目标" in spec.command
    assert 'request(1, "change_control_right_to", {"owner": "alg"}, wait=3)' in spec.command
    assert 'request(2, "start_nav", REQUEST_VALUE, wait=5)' in spec.command
    assert 'request(9001, "stop_nav")' in spec.command
    assert 'request(9002, "change_control_right_to", {"owner": "app"})' in spec.command
    assert "start_multi_nav_by_points" not in spec.command
    assert "/start_navigation" not in spec.command
    assert "dog_remote_start_navigation_helper.py" not in spec.command
    assert '{"owner": "alg"}' in spec.command
    assert '"map_type":"2d"' in spec.command
    assert '"position":{"x":1.0,"y":2.0,"z":0.0}' in spec.command
    assert '"orientation":{"x":0.0,"y":0.0,"z":0.24740395925452294,"w":0.9689124217106447}' in spec.command
    assert "导航目标已提交" in spec.command
    assert spec.command.index("start_nav") < spec.command.index("导航目标已提交")
    assert "/robot_roamerx/is_in_nav_control" in spec.command


def test_app_start_nav_treats_canceled_as_failure_not_success():
    spec = navigation.start_goal_command(
        get_product("zg_lidar_nx"),
        "/opt/data/.robot/map/map.pcd",
        1.0,
        2.0,
        0.5,
        0.4,
        0.25,
    )

    assert 'elif status in {"Canceled", "Cancel", "Idle"}:' in spec.command
    assert 'raise RuntimeError(f"导航被取消: {status}")' in spec.command
    assert 'elif status in {"Stopped", "StandBy", "Succeeded"} and seen_running:' not in spec.command
    assert "body_cmd(180)" in spec.command
    assert "body_cmd(170)" in spec.command
    assert "get_nav_status" in spec.command
    assert "wait_done(20)" in spec.command
    assert "map.pcd" in spec.command
    assert "map.yaml" in spec.command


def test_l2_point_navigation_click_path_skips_slow_pre_start_state_clear():
    profile = get_product("xg2_s100")

    spec = navigation.start_goal_command(
        profile,
        "/opt/data/.robot/map/map.pcd",
        1.0,
        2.0,
        0.5,
        0.4,
        0.25,
    )
    remote_command = spec.command

    assert "start_nav" in remote_command
    assert "START_NAV_HELPER_FIFO=/tmp/dog_remote_start_navigation.fifo" not in remote_command
    assert "NAV_PRE_MSG=" not in remote_command
    assert "上一导航仍未结束" not in remote_command
    assert "上一导航已停止，继续发送新目标" not in remote_command
    assert "DOG_REMOTE_DISABLE_BODY_NAV_BRIDGE" in spec.command
    assert "robot-launch start robot_roamerx" in spec.command
    assert "/robot_control_server/nav_pose" in spec.command


def test_navigation_release_watcher_does_not_treat_cancel_transition_as_done():
    spec = navigation.start_goal_command(
        get_product("xg2_s100"),
        "/opt/data/.robot/map/map.pcd",
        1.0,
        2.0,
        0.5,
        0.4,
        0.25,
    )

    watcher_start = spec.command.index("WATCH_START_TS=$(date +%s)")
    watcher_end = spec.command.index("done; '", watcher_start)
    watcher = spec.command[watcher_start:watcher_end]

    assert "0|1|4|5|6|7|200|202" in watcher
    assert "0|1|4|5|6|7|200|201|202" not in watcher
    assert "DEADLINE=$(( $(date +%s)" not in watcher
    assert "navigation release watcher timed out" not in watcher
    assert "while true" in watcher
    assert 'if [ "$NAV_TASK_ACTIVE" = 1 ] || [ "$NAV_TASK_PENDING_COUNT" -gt 0 ]; then sleep 1; continue; fi' in watcher
    assert "NAV_TASK_STATUS_LIST=" in watcher
    assert "NAV_TASK_PENDING_COUNT=" in watcher
    assert "NAV_ALL_TASKS_TERMINAL=1" in watcher
    assert "NAV_FAST_TERMINAL=1" in watcher
    assert 'if [ "$NAV_FAST_TERMINAL" = 1 ]; then' in watcher
    assert 'WATCH_START_TS=$(date +%s)' in watcher
    assert 'if [ "$SEEN_NAV_ACTIVE" != 1 ]; then true' in watcher
    assert "observed terminal state before active; keep watching" not in watcher


def test_navigation_parameter_commands_are_removed():
    removed_names = (
        "COLLISION_RADIUS_PARAM",
        "COLLISION_RADIUS_NODES",
        "NAVIGATION_CONSTRAINT_PARAMS",
        "collision_radius_status_command",
        "set_collision_radius_command",
        "navigation_constraints_status_command",
        "set_navigation_constraint_command",
        "set_navigation_constraints_command",
        "reset_navigation_constraints_command",
        "restart_navigation_nodes_command",
    )

    for name in removed_names:
        assert not hasattr(navigation, name)


def test_ensure_navigation_helpers_command_starts_persistent_publishers():
    spec = navigation.ensure_navigation_helpers_command(get_product("xg2_s100"))

    assert spec.title == "准备导航通道"
    assert spec.display_command == "执行：准备导航通道"
    assert spec.concurrency == "parallel"
    assert spec.locks == ("navigation-helper",)
    assert "dog_remote_start_navigation_helper.py" in spec.command
    assert "dog_remote_start_navigation.fifo" in spec.command
    assert "robots_dog_msgs.msg import StartNavigation" in spec.command
    assert "set_message_fields" in spec.command
    assert "dog_remote_nav_mode_switch_helper.py" not in spec.command
    assert "dog_remote_nav_mode_switch.fifo" not in spec.command
    assert "/control_right/test" not in spec.command
    assert "/robot_roamerx/is_in_nav_control" not in spec.command
    assert "rclpy.create_node" in spec.command
    assert "AppWsBrokerClient()" in spec.command
    assert '"get_nav_status"' in spec.command
    assert "app websocket/broker 已就绪" in spec.command
    assert "std_msgs.msg import Bool" not in spec.command
    assert "keep_enabled" not in spec.command
    assert navigation.ensure_mode_switch_helper_command is navigation.ensure_navigation_helpers_command


def test_zg_ensure_navigation_helpers_prewarms_body_bridge_and_control():
    spec = navigation.ensure_navigation_helpers_command(get_product("zg_lidar_nx"))

    assert "robot@192.168.234.1" in spec.command
    assert "robot-launch start robot_roamerx" in spec.command
    assert "enable_forward_cmd_vel" in spec.command
    assert "/opt/robot/install/robot_roamerx/share/robot_roamerx/config/zsm/robot_roamerx.yaml" in spec.command
    assert "robot-launch restart robot_roamerx" in spec.command
    assert "[d]og_remote_app_ws_broker" not in spec.command
    assert "/robot_control_server/current_requester_info" in spec.command
    assert "from robot_common_interface.action import ControlServerSwitchControl" in spec.command
    assert "ros2 action send_goal /robot_control_server/switch_control" not in spec.command
    assert "dog_remote_robot_roamerx_control" in spec.command
    assert spec.command.index("robot-launch start robot_roamerx") < spec.command.index(
        "dog_remote_start_navigation_helper.py"
    )


def test_auto_body_release_keeps_robot_roamerx_warm():
    spec = navigation.release_body_navigation_bridge_command(get_product("zg_lidar_nx"), stop_service=False)

    assert spec is not None
    assert "/control_right/test" not in spec.command
    assert "/robot_roamerx/is_in_nav_control" in spec.command
    assert "robot-launch stop robot_roamerx" not in spec.command
    assert "保留 robot_roamerx" in spec.command


def test_manual_body_release_can_stop_robot_roamerx():
    spec = navigation.release_body_navigation_bridge_command(get_product("zg_lidar_nx"))

    assert spec is not None
    assert "robot-launch stop robot_roamerx" in spec.command
    assert "已停止 robot_roamerx" in spec.command


def test_reference_line_navigation_entrypoints_are_removed():
    assert not hasattr(navigation, "start_reference_line_file_command")
    assert not hasattr(navigation, "start_reference_line_file_loop_command")


def test_zg_lidar_route_navigation_uses_body_bridge_for_fast_alg_managed_start():
    profile = get_product("zg_lidar_nx")

    spec = navigation.start_route_goal_command(
        profile,
        "/ota/alg_data/map/history_map/a/map.pcd",
        "/ota/alg_data/map/history_map/a/map.geojson",
        1.0,
        2.0,
        0.3,
        0.5,
        0.2,
    )
    route_script = _route_stdin_script_text(spec.command)

    assert spec.concurrency == "parallel"
    assert spec.locks == ("navigation-command",)
    assert "robot@192.168.168.100" in spec.command
    assert "robot@192.168.234.1" in spec.command
    assert "robot-launch start robot_roamerx" in spec.command
    assert "/robot_control_server/current_requester_info" in spec.command
    assert "DOG_REMOTE_DISABLE_BODY_NAV_BRIDGE" in spec.command
    assert "导航服务已就绪，直接下发目标" not in spec.command
    assert "导航服务已就绪，使用快速下发" in route_script
    assert spec.command.rindex("robot-launch start robot_roamerx") < spec.command.rindex(
        "bash -s <"
    )
    assert "start_multi_nav_task" in route_script
    assert '"map_type":"route"' in route_script
    assert '"goal_task_type":"route"' in route_script
    assert "start_multi_nav_by_points" not in route_script
    assert "/start_navigation" not in route_script
    assert "START_NAV_PAYLOAD=" not in route_script
    assert "dog_remote_nav_release_watch.log" not in route_script
    assert route_script.index("正在提交路网导航目标") < route_script.index("start_multi_nav_task")


def test_l2_route_navigation_uses_shared_start_multi_nav_task_chain():
    profile = get_product("xg2_s100")

    spec = navigation.start_route_goal_command(
        profile,
        "/opt/data/.robot/map/history_map/a/map.pcd",
        "/opt/data/.robot/map/history_map/a/map.geojson",
        1.0,
        2.0,
        0.3,
        0.5,
        0.2,
    )
    route_script = _route_stdin_script_text(spec.command)

    assert spec.concurrency == "parallel"
    assert spec.locks == ("navigation-command",)
    assert "robot@192.168.168.100" in spec.command
    assert "robot@192.168.234.1" in spec.command
    assert "robot-launch start robot_roamerx" in spec.command
    assert "/robot_control_server/nav_pose" in spec.command
    assert "导航服务已就绪，使用快速下发" in route_script
    assert spec.command.rindex("robot-launch start robot_roamerx") < spec.command.rindex(
        "bash -s <"
    )
    assert "start_multi_nav_task" in route_script
    assert '"map_type":"route"' in route_script
    assert '"goal_task_type":"route"' in route_script
    assert "start_multi_nav_by_points" not in route_script
    assert "/start_navigation" not in route_script


def test_zg_lidar_point_navigation_uses_body_bridge_for_fast_alg_managed_start():
    profile = get_product("zg_lidar_nx")

    spec = navigation.start_goal_command(
        profile,
        "/ota/alg_data/map/history_map/a/map.pcd",
        1.0,
        2.0,
        0.3,
        0.5,
        0.2,
    )

    assert "robot@192.168.168.100" in spec.command
    assert "robot@192.168.234.1" in spec.command
    assert "robot-launch start robot_roamerx" in spec.command
    assert "/robot_control_server/current_requester_info" in spec.command
    assert "DOG_REMOTE_DISABLE_BODY_NAV_BRIDGE" in spec.command
    assert "导航服务已就绪，直接下发目标" not in spec.command
    assert "导航服务已就绪，使用快速下发" not in spec.command
    assert spec.command.rindex("robot-launch start robot_roamerx") < spec.command.rindex("导航目标已提交")
    assert "current_goal_checker general_goal_checker" not in spec.command
    assert "current_progress_checker progress_checker" not in spec.command
    assert 'request(1, "change_control_right_to", {"owner": "alg"}, wait=3)' in spec.command
    assert 'request(2, "start_nav", REQUEST_VALUE, wait=5)' in spec.command
    assert 'request(9002, "change_control_right_to", {"owner": "app"})' in spec.command
    assert "/start_navigation" not in spec.command
    assert spec.command.index("start_nav") < spec.command.index("导航目标已提交")


def test_stop_navigation_command_releases_body_control_right():
    spec = navigation.stop_command(get_product("xg1_nx"))

    assert spec.concurrency == "parallel"
    assert spec.locks == ("navigation-control",)
    assert "/tmp/dog_remote_nav_stop_source.log" in spec.command
    assert "manual" in spec.command
    assert "/control_right/test" not in spec.command
    assert "/robot_roamerx/is_in_nav_control" in spec.command
    assert "stop_nav" in spec.command
    assert "NAV_STOP_PRE_ACTIVE" in spec.command
    assert "当前没有执行中的导航任务，仅释放导航控制权" not in spec.command
    assert "未读到 /navigation_state，仅释放导航控制权" not in spec.command
    assert "已发送 ROS 停止导航命令" not in spec.command
    assert "停止通道暂不可用，继续尝试释放导航控制权" not in spec.command
    assert "导航已停止" not in spec.command
    assert "停止命令已发送，但 /navigation_state 仍在执行中" not in spec.command
    assert "timeout 1.5s python3 -c" in spec.command
    assert "timeout 1.0s ros2 topic pub -1 /start_navigation" not in spec.command
    assert "导航停止已提交，状态刷新交由页面后台完成" in spec.command
    assert spec.command.index('"stop_nav"') < spec.command.index("data: false")
    assert spec.command.index("data: false") < spec.command.index("导航停止已提交")
    assert "DOG_REMOTE_FORCE_BODY_NAV_RIGHT" not in spec.command
    assert "dog_remote_nav_control_state_pub.pid" in spec.command
    assert '"role": "remote", "type": "heartbeat"' in spec.command
    assert '"cmd": 170, "type": "cmd"' in spec.command
    assert "兜底" not in spec.command
    assert "robot-launch start robot_roamerx" not in spec.command


def test_stop_navigation_command_records_source():
    spec = navigation.stop_command(get_product("xg1_nx"), source="map_switch")

    assert "/tmp/dog_remote_nav_stop_source.log" in spec.command
    assert "map_switch" in spec.command


def test_multipoint_commands_use_alg_broker_paths():
    points = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.1)]

    for profile_key in ("xg2_s100", "zg_lidar_nx"):
        profile = get_product(profile_key)
        multi = navigation.start_multipoint_command(profile, "/opt/data/.robot/map/map.pcd", points, 0.4)
        loop = navigation.start_multipoint_loop_command(profile, "/opt/data/.robot/map/map.pcd", points, 0.4)

        assert multi.title == "开始多点导航"
        assert loop.title == "开始多点循环"
        assert "start_multi_nav_by_points" in multi.command
        assert 'expected_func="start_multi_nav"' in multi.command
        assert "position" in multi.command
        assert "orientation" in multi.command
        assert "start_multi_nav_by_points" in loop.command
        assert 'expected_func="start_multi_nav"' in loop.command
        assert "/start_navigation" not in multi.command
        assert "/start_navigation" not in loop.command
        assert "上一导航仍未结束" not in multi.command
        assert "上一导航已停止，继续发送新目标" not in multi.command
        assert "上一导航仍未结束" not in loop.command
        assert "上一导航已停止，继续发送新目标" not in loop.command
        assert "0|1|4|5|6|7|200|201|202" not in multi.command
        assert "0|1|4|5|6|7|200|201|202" not in loop.command
        assert "导航模式已更新" not in multi.command
        assert "导航模式已更新" not in loop.command
        assert "NAV_START_DEADLINE" not in multi.command
        assert "NAV_START_DEADLINE" not in loop.command
        assert multi.command.index("start_multi_nav_by_points") < multi.command.index("多点导航任务已提交")
        assert "/tmp/dog_remote_nav_release_watch.log" not in multi.command
        assert "/tmp/dog_remote_nav_release_watch.log" not in loop.command
        for command in (multi.command, loop.command):
            assert "DOG_REMOTE_DISABLE_BODY_NAV_BRIDGE" in command
            assert "robot-launch start robot_roamerx" in command
            if profile_key == "zg_lidar_nx":
                assert "/robot_control_server/current_requester_info" in command
                assert "enable_forward_cmd_vel" in command
            else:
                assert "/robot_control_server/nav_pose" in command
                assert "enable_forward_cmd_vel" not in command


def test_alg_broker_navigation_task_python_is_valid_for_each_kind():
    for kind in ("single", "multi", "route", "loop", "route_loop"):
        command = navigation_goal_commands._alg_manager_nav_task_inner(kind, "'{}'", 300)
        parts = shlex.split(command)

        assert parts[:2] == ["python3", "-c"]
        compile(parts[2], f"<{kind}>", "exec")


def test_alg_broker_navigation_status_uses_single_app_status_request():
    command = navigation_goal_commands._alg_manager_nav_task_inner("route", "'{}'", 300)
    script = shlex.split(command)[2]

    assert "messages = CLIENT.request(obj, expected, wait)" in script
    assert 'messages = CLIENT.request(obj, "", wait)' not in script
    assert 'app = request(frame, "get_nav_status")' in script
    assert "attempt * 10000" not in script
    assert "for attempt in range(3):" not in script


def test_alg_broker_reset_nav_state_does_not_stop_when_already_standby():
    command = navigation_goal_commands._alg_manager_nav_task_inner("single", "'{}'", 300)
    script = shlex.split(command)[2]

    assert "status = nav_status(frame)" in script
    assert 'if status in {"Stopped", "StandBy"}:' in script
    assert 'request(frame_start, "stop_nav", wait=2)' in script
    assert "raise RuntimeError(f\"启动前导航状态未回空闲: {last or status or 'unknown'}\")" in script
    assert script.index('if status in {"Stopped", "StandBy"}:') < script.index('request(frame_start, "stop_nav", wait=2)')
    assert script.index('request(frame_start, "stop_nav", wait=2)') < script.index("启动前导航状态未回空闲")


def test_multi_point_broker_payload_map_id_rewrite_is_shared():
    source = inspect.getsource(navigation_goal_commands)

    assert source.count("DOG_REMOTE_MULTI_NAV_VALUE=$(python3 - <<'PY'") == 1
    assert source.count("alg_manager_start_multi_nav_by_points_payload(") == 1


def test_route_broker_payload_map_id_rewrite_is_shared():
    source = inspect.getsource(navigation_goal_commands)

    assert source.count("DOG_REMOTE_ROUTE_NAV_VALUE=$(python3 - <<'PY'") == 1
    assert source.count("alg_manager_start_multi_nav_task_route_value(") == 1


def test_alg_broker_cleanup_uses_single_stop_and_control_release_request():
    command = navigation_goal_commands._alg_manager_nav_task_inner("route", "'{}'", 300)
    script = shlex.split(command)[2]

    assert "request_with_retries" not in script
    assert 'request(9001, "stop_nav")' in script
    assert 'request(9002, "change_control_right_to", {"owner": "app"})' in script


def test_navigation_loop_commands_start_remote_loop_and_stop_kills_it():
    profile = get_product("xg1_nx")
    map_path = "/ota/alg_data/map/history_map/2026_06_09_16_57_12/map.pcd"
    route_path = "/ota/alg_data/map/history_map/2026_06_09_16_57_12/map.geojson"
    points = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0)]

    multi = navigation.start_multipoint_loop_command(profile, map_path, points, 0.5)
    route = navigation.start_route_goal_loop_command(profile, map_path, route_path, 2.0, 0.0, 0.0, 0.5, 0.25, points)
    stop = navigation.stop_command(profile)
    route_script = _route_stdin_script_text(route.command)

    for spec in (route,):
        assert "/tmp/dog_remote_nav_loop.pid" in route_script
        assert "/tmp/dog_remote_nav_loop.log" in route_script
        assert ': > "$NAV_LOOP_LOG"' in route_script
        assert "nohup bash -lc" in route_script
        assert "导航循环任务启动后立即退出" in route_script
        assert "wait_nav_done()" not in route_script
        assert "NAV_WAIT_RC=$?" not in route_script
        assert "cleanup_nav_loop()" not in route_script
        assert "while True" in route_script
        assert "路网循环开始第" in route_script
        assert "start_multi_nav_task" in route_script
        assert "get_nav_status" in route_script
        assert "body_cmd(180)" in route_script
        assert "body_cmd(170)" in route_script
        assert "DOG_REMOTE_FORCE_BODY_NAV_RIGHT" not in route_script
        assert "dog_remote_nav_control_state_pub.pid" not in route_script
        assert "/start_navigation" not in route_script
        assert "start_multi_nav_by_points" not in route_script

    assert multi.title == "开始多点循环"
    assert "多点循环 count=3" in multi.command
    assert "batch_rounds=20" not in multi.command
    assert "每批展开 20 轮" not in multi.command
    assert "start_multi_nav_by_points" in multi.command
    assert "get_nav_status" in multi.command
    assert "multi_loop" not in multi.command
    assert "多点循环任务已提交" in multi.command
    assert "多点循环开始第" in multi.command
    assert "/start_navigation" not in multi.command
    assert "wait_nav_done()" not in multi.command
    assert "cleanup_nav_loop()" not in multi.command
    assert "body_cmd(180)" in multi.command
    assert "body_cmd(170)" in multi.command
    assert "/robot_roamerx/is_in_nav_control" in multi.command
    assert multi.command.count('"position":{"x":0.0,"y":0.0,"z":0.0}') >= 20
    assert multi.command.count('"position":{"x":1.0,"y":0.0,"z":0.0}') >= 20
    assert multi.command.count('"position":{"x":2.0,"y":0.0,"z":0.0}') >= 20
    assert route.title == "开始路网循环"
    assert "路网循环 count=3" in route_script
    assert "batch_rounds=20" not in route_script
    assert "每批展开 20 轮" not in route_script
    assert "会按每批 20 轮" not in route.description
    assert route.description == "会循环下发当前路网目标序列，直到点击停止。"
    assert "RouteGraphPlanner" not in route_script
    assert "DOG_REMOTE_ROUTE_GRAPH_CACHE" not in route_script
    assert "路网未变化，跳过重复更新" not in route_script
    assert "NAV_STANDBY_ALLOW_UNKNOWN" not in route_script
    assert '"map_type":"route"' in route_script
    assert '"goal_task_type":"route"' in route_script
    assert route_script.count('"position":{"x":0.0,"y":0.0,"z":0.0}') >= 20
    assert route_script.count('"position":{"x":1.0,"y":0.0,"z":0.0}') >= 20
    assert route_script.count('"position":{"x":2.0,"y":0.0,"z":0.0}') >= 20
    assert "/tmp/dog_remote_nav_loop.pid" in stop.command
    assert "停止远端导航循环任务" in stop.command
    assert "stop_nav" in stop.command


def test_l2_navigation_loop_commands_use_body_bridge():
    profile = get_product("xg2_s100")
    map_path = "/opt/data/.robot/map/map.pcd"
    route_path = "/opt/data/.robot/map/map.geojson"
    points = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)]

    specs = (
        navigation.start_route_goal_loop_command(profile, map_path, route_path, 1.0, 0.0, 0.0, 0.5, 0.25, points),
    )
    point_loop = navigation.start_multipoint_loop_command(profile, map_path, points, 0.5)

    for spec in specs:
        assert "DOG_REMOTE_DISABLE_BODY_NAV_BRIDGE" in spec.command
        assert "robot-launch start robot_roamerx" in spec.command
        assert "/robot_control_server/nav_pose" in spec.command
    assert "start_multi_nav_by_points" in point_loop.command
    assert "/start_navigation" not in point_loop.command
    assert "wait_nav_done()" not in point_loop.command


def test_navigation_control_commands_are_confirmed_before_changing_remote_state():
    profile = get_product("zg_surround_s100")
    pause = navigation.pause_command(profile)
    resume = navigation.continue_command(profile)
    stop = navigation.stop_command(profile)

    assert pause.dangerous is False
    assert resume.dangerous is False
    assert stop.dangerous is True
    assert pause.locks == ("navigation-control",)
    assert resume.locks == ("navigation-control",)
    assert stop.locks == ("navigation-control",)
    assert "会暂停当前远端导航任务" in pause.description
    assert "机器人可能恢复移动" in resume.description
    assert "会停止当前远端导航任务" in stop.description
    assert "pause_nav" in pause.command
    assert "continue_nav" in resume.command
    assert '{header: {frame_id: "map"}, cmd:' not in pause.command
    assert '{header: {frame_id: "map"}, cmd:' not in resume.command
    assert '{header: {frame_id: "map"}, cmd: 4, tasks: []}' not in stop.command
    assert "/control_right/test" not in pause.command
    assert "/robot_roamerx/is_in_nav_control" not in pause.command
    assert "/robot_roamerx/is_in_nav_control" not in resume.command
    assert "data: true" not in pause.command
    assert "data: true" not in resume.command
    assert 'APP_WS_BROKER_SOCKET = "/tmp/dog_remote_app_ws.sock"' in pause.command
    assert 'APP_WS_BROKER_SOCKET = "/tmp/dog_remote_app_ws.sock"' in resume.command
    assert "class AppWsBrokerClient:" in pause.command
    assert "class AppWsBrokerClient:" in resume.command
    assert "timeout 2.0s python3 -c" in pause.command
    assert "timeout 2.0s python3 -c" in resume.command
    assert "/start_navigation" not in pause.command
    assert "/start_navigation" not in resume.command
    assert "change_control_right_to" not in pause.command
    assert "change_control_right_to" not in resume.command
    assert '"stop_nav"' in stop.command
    assert "NAV_STOP_PRE_ACTIVE" in stop.command
    assert "已提交停止导航请求" in stop.command
    assert "已发送 ROS 停止导航命令" not in stop.command
    assert "停止通道暂不可用，继续尝试释放导航控制权" not in stop.command
    assert "导航已停止" not in stop.command
    assert "timeout 1.5s python3 -c" in stop.command
    assert "timeout 1.0s ros2 topic pub -1 /start_navigation" not in stop.command
    assert "change_control_right_to" in stop.command
    assert "OWNER = sys.argv[1]" in stop.command
    assert " app || true" in stop.command
    assert "for _stop_i in 1 2 3 4; do" not in stop.command
    assert "导航停止已提交，状态刷新交由页面后台完成" in stop.command
    assert "当前没有执行中的导航任务，仅释放导航控制权" not in stop.command
    assert "data: false" in stop.command
    assert stop.command.index('"stop_nav"') < stop.command.index("data: false")
    assert stop.command.index("data: false") < stop.command.index("导航停止已提交")


def test_navigation_control_commands_do_not_share_start_navigation_lock():
    profile = get_product("xg2_s100")
    start = navigation.start_goal_command(profile, "/opt/data/.robot/map/map.pcd", 1.0, 2.0, 0.5, 0.4, 0.25)
    pause = navigation.pause_command(profile)
    resume = navigation.continue_command(profile)
    stop = navigation.stop_command(profile)

    assert start.locks == ("navigation-command",)
    assert pause.locks == ("navigation-control",)
    assert resume.locks == ("navigation-control",)
    assert stop.locks == ("navigation-control",)
    assert not set(start.locks).intersection(pause.locks)
    assert not set(start.locks).intersection(resume.locks)
    assert not set(start.locks).intersection(stop.locks)


def test_stop_navigation_alg_fast_stop_uses_app_ws_broker():
    profile = get_product("zg_lidar_nx")

    stop = navigation.stop_command(profile)

    assert 'APP_WS_BROKER_SOCKET = "/tmp/dog_remote_app_ws.sock"' in stop.command
    assert "class AppWsBrokerClient:" in stop.command
    assert "sock = connect()" not in stop.command
    assert "client.request(obj" in stop.command
    assert 'request(alg_client, 1, "stop_nav"' in stop.command


def test_start_arc_calibration_command_publishes_verified_arc_payload():
    profile = get_product("zg_lidar_nx")

    spec = navigation.start_arc_calibration_command(profile, tag_id=0, monitor_seconds=30)
    remote_command = spec.command

    assert spec.title == "标定充电桩"
    assert spec.dangerous is True
    assert spec.display_command == "执行：ARC 标定充电桩"
    assert spec.concurrency == "parallel"
    assert spec.locks == ("arc", "motion")
    assert "会向 ARC 状态机发送充电桩标定请求" in spec.description
    assert "请确认机器狗已经趴在充电桩上正确标定位置" in spec.description
    assert "触点/姿态稳定" in spec.description
    assert "source /opt/robot/robot_arc/install/setup.bash" in remote_command
    assert "robots_dog_msgs/msg/StartArc" in remote_command
    assert "ros2 topic pub --once /arc/start_arc" in remote_command
    assert "cmd: 2" in remote_command
    assert "secondary_cmd: 2" in remote_command
    assert "tag_id: 0" in remote_command
    assert "/arc/calibration_state" in remote_command
    assert "/arc/arc_state" in remote_command
    assert "apriltag_localization_pc_config.yaml" in remote_command
    assert "apriltag_localization_pc_config_middle_dog.yaml" in remote_command
    assert "CFG_CHANGED" in remote_command
    assert "/arc/perception_dock_pose" in remote_command
    assert "核心看 y 横向偏差和 yaw 航向偏差" in remote_command
    assert "对桩精度核心" in remote_command
    assert "mean_yaw" in remote_command
    assert "jitter_yaw" in remote_command
    assert "T_tag_dockbase_calib平移" in remote_command
    assert "重启 ARC 感知、状态机、arc_mapping 后复测" in remote_command


def test_mark_charging_dock_command_uses_arc_mapping_map_state():
    profile = get_product("zg_lidar_nx")

    spec = navigation.mark_charging_dock_command(
        profile,
        "/ota/alg_data/map/history_map/2026_06_04_02_30_13/map.pcd",
        tag_id=0,
        monitor_seconds=30,
        slam_version="0.5.0-r1",
    )
    remote_command = spec.command

    assert spec.title == "标记充电桩"
    assert spec.dangerous is True
    assert spec.concurrency == "parallel"
    assert spec.locks == ("navigation", "app_ws")
    assert "机器狗位于充电桩正前方的标记位" in spec.description
    assert "二维码/桩体在传感器视野内且无遮挡" in spec.description
    assert "不要在斜角过大" in spec.description
    assert "写入当前地图 map.yaml" in spec.description
    assert "不是 ARC/apriltag 标定" in spec.description
    assert "先通过系统应用通道加载定位地图" in spec.description
    assert "source /opt/robot/robot_arc/install/setup.bash" in remote_command
    assert "robots_dog_msgs/msg/ArcModuleCmd" in remote_command
    assert "/arc/perception_mode_cmd" in remote_command
    assert "loc_load_map" in remote_command
    assert "get_loc_status" in remote_command
    assert "continuousloc" in remote_command
    assert "定位已进入连续定位状态" in remote_command
    assert "/arc/perception_state" in remote_command
    assert "--qos-reliability" in remote_command
    assert "best_effort" in remote_command
    assert "ARC 感知未进入 RUNNING，未发送地图标记请求" in remote_command
    assert "ARC 感知未输出 /arc/perception_dock_pose" in remote_command
    assert "robots_dog_msgs/srv/MapState" in remote_command
    assert "/arc_mapping_service" in remote_command
    assert "mapping_type: 1" in remote_command
    assert "call_map_state(0)" in remote_command
    assert "call_map_state(3)" in remote_command
    assert "call_map_state(5)" in remote_command
    assert remote_command.index("ensure_localization()") < remote_command.index("start_perception()")
    assert remote_command.index("start_perception()") < remote_command.index("call_map_state(0)")
    assert remote_command.index("call_map_state(0)") < remote_command.index("call_map_state(3)")
    assert remote_command.index("call_map_state(3)") < remote_command.index("call_map_state(5)")
    assert "ARC mapping 服务成功" in remote_command
    assert "map_path_prefix" in remote_command
    assert "/ota/alg_data/map/history_map/2026_06_04_02_30_13" in remote_command
    assert "arc_position_flag" in remote_command
    assert "/robot_slam/slam_state_service" not in remote_command
    assert "data: 100" not in remote_command


def test_mark_charging_dock_command_uses_app_map_load_without_slam_version_probe():
    profile = get_product("xg1_nx")

    spec = navigation.mark_charging_dock_command(
        profile,
        "/ota/alg_data/map/history_map/2026_06_04_02_30_13/map.pcd",
        tag_id=2,
        monitor_seconds=30,
    )
    remote_command = spec.command

    assert "检测到 robot-slam 版本" not in remote_command
    assert "SLAM_CODE_MODE" not in remote_command
    assert "slam_0_5_r3" not in remote_command
    assert "data: 100" not in remote_command
    assert "loc_load_map" in remote_command
    assert "2026_06_04_02_30_13" in remote_command
    assert "TAG_ID = int(sys.argv[4])" in remote_command
    assert remote_command.rstrip().endswith("/ota/alg_data/map/history_map/2026_06_04_02_30_13/map.yaml 2 30")


def test_mark_charging_dock_r3_uses_arc_mapping_app_flow():
    profile = get_product("zg_lidar_nx")

    spec = navigation.mark_charging_dock_command(
        profile,
        "/ota/alg_data/map/history_map/2026_06_11_18_30_02/map.pcd",
        tag_id=0,
        monitor_seconds=30,
        slam_version="0.5.0-r3",
    )
    remote_command = spec.command

    assert "robots_dog_msgs/srv/GetSlamState" not in remote_command
    assert "SLAM 处于 SUCCESS，先复位" not in remote_command
    assert "SLAM 已处于 ACTIVE" not in remote_command
    assert "{mapping_type: 0, data:" not in remote_command
    assert "/robot_slam/slam_state_service" not in remote_command
    assert "/arc_mapping_service" in remote_command
    assert "loc_load_map" in remote_command
    assert "get_loc_status" in remote_command
    assert "call_map_state(0)" in remote_command
    assert "call_map_state(3)" in remote_command
    assert "call_map_state(5)" in remote_command
    assert "ARC mapping 未进入 READY" in remote_command
    assert "启动 ARC 感知: /arc/perception_mode_cmd RUNNING tag_id={TAG_ID}" in remote_command
    assert "/arc/perception_dock_pose" in remote_command
    assert remote_command.index("ensure_localization()") < remote_command.index("start_perception()")
    assert remote_command.index("start_perception()") < remote_command.index("call_map_state(0)")


def test_start_arc_with_map_command_uses_app_ws_map_id_and_arc_flag_guard():
    profile = get_product("zg_lidar_nx")

    spec = navigation.start_arc_with_map_command(profile, "/ota/alg_data/map/history_map/2026_06_04/map.pcd")
    remote_command = spec.command

    assert spec.title == "有图回充"
    assert spec.dangerous is True
    assert spec.display_command == "执行：ARC 有图回充"
    assert spec.concurrency == "parallel"
    assert spec.locks == ("arc", "motion", "app_ws")
    assert "get_arc_match_status" in remote_command
    assert "get_cur_arc_tagid" in remote_command
    assert "loc_load_map" in remote_command
    assert "get_loc_status" in remote_command
    assert "start_arc_with_map" in remote_command
    assert "send_mapped_recharge_request(sock, frame)" in remote_command
    assert "已发送有图进桩请求" in remote_command
    assert "有图回充前先停止/释放当前导航任务" not in remote_command
    assert "rc=$?" in remote_command
    assert "已停止有图回充任务并释放控制" in remote_command
    assert '"stop_nav"' in remote_command
    assert "ROS_STOP_LOG" not in remote_command
    assert "ros2 topic pub -1 /start_navigation" not in remote_command
    assert "系统应用通道正被其他任务占用" in remote_command
    assert "系统应用通道暂不可用" in remote_command
    assert "send_close(sock)" in remote_command
    assert "PORT = 10010" in remote_command
    assert "准备有图进桩" in remote_command
    assert "/control_right/test" not in remote_command
    assert "/robot_roamerx/is_in_nav_control" in remote_command
    assert "dog_remote_keyboard_control_claim" in remote_command
    assert "dog_remote_arc_pre_release_control_right.log" in remote_command
    assert "sleep 0.5; timeout 70s ros2 topic pub -r 20 /control_right/test" not in remote_command
    assert "清理遗留控制权发布器" not in remote_command
    assert "已启动 ARC 对齐控制权保持" not in remote_command
    assert "stop_navigation_control_guard(control_guard)" not in remote_command
    assert "robot-launch start robot_roamerx" in spec.command
    assert "start_arc_align_coarse" in remote_command
    assert "send_coarse_control_request(sock, frame)" in remote_command
    assert "should_send_coarse_control(alg, dock)" in remote_command
    assert 'return alg == "DockAlignCoarse"' in remote_command
    assert 'alg in {"DockAlignCoarse", "DockAlignFine", "DockContact", "RequestPowerOn"}' in remote_command
    assert "coarse_sent = False" in remote_command
    assert "align_started_at = None" in remote_command
    assert "nav_started_at = time.time()" in remote_command
    assert "expected_funcs={\"start_arc_with_map\", \"start_nav\"}" in remote_command
    assert "expected_funcs={\"start_arc_align_coarse\", \"start_align_coarse\"}" in remote_command
    assert "ARC_ERROR_CODES = set()" in remote_command
    assert "def handle_arc_notify(parsed):" in remote_command
    assert "mapped_arc_error_seen()" in remote_command
    assert "mapped_arc_error_hint()" in remote_command
    assert "ARC 有图回充失败" in remote_command
    assert "精对准失败：对准未完成收敛" in remote_command
    assert (
        'if alg == "Charging" or dock == "Charging":\n'
        '            print("[INFO] 有图回充成功，已进入充电状态。", flush=True)\n'
        '            raise SystemExit(0)'
    ) in remote_command
    assert "已到达桩前，开始粗对准" in remote_command
    assert "已进入对准阶段，继续进桩" in remote_command
    assert "正在精对准" in remote_command
    assert "正在请求充电桩上电" in remote_command
    assert "time.time() - align_started_at >= MONITOR_SECONDS" in remote_command
    assert "等待进入对准阶段超时" in remote_command
    assert "进桩阶段等待超时" in remote_command
    assert 'alg in {"FailureSafe", "Failure", "FailureContact"}' in remote_command
    assert 'alg in {"Passive", "UnDockReset", "ChargedExit"}' in remote_command
    assert '"ChargedExit", "UnDockReset"' not in remote_command
    assert "2026_06_04" in remote_command
    assert "arc_position_flag" in remote_command
    assert "get_arc_alg_status" in remote_command
    assert "stop_arc" in remote_command
    assert "cleanup_mapped_recharge(sock, frame)" in remote_command
    assert '"stop_nav"' in remote_command
    assert "有图进桩未启动" in remote_command


def test_navigation_page_arc_calibration_uses_common_dangerous_runner():
    page = _FakeNavigationActionPage()

    started = NavigationPage.make_start_arc_calibration(page)

    assert started is True
    assert len(page.runs) == 1
    spec, operation = page.runs[0]
    assert spec.title == "标定充电桩"
    assert spec.dangerous is True
    assert operation == "充电桩标定中"
    assert page.navigation_log_lines[-1] == "[ARC] 已开始充电桩标定"


def test_navigation_page_mark_charging_dock_uses_arc_mapping_runner():
    page = _FakeNavigationActionPage()

    started = NavigationPage.make_mark_charging_dock(page)

    assert started is True
    assert len(page.runs) == 1
    spec, operation = page.runs[0]
    assert spec.title == "标记充电桩"
    assert spec.dangerous is True
    assert operation == "标记充电桩中"
    assert page.navigation_log_lines[-1] == "[ARC] 已开始标记充电桩"


def test_navigation_page_mark_charging_dock_blocks_while_map_prepares(monkeypatch):
    page = _FakeNavigationActionPage()
    page.map_prepare_slot = _FakeSlot(running=True)
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda _parent, title, text: messages.append((title, text)))

    started = NavigationPage.make_mark_charging_dock(page)

    assert started is False
    assert page.runs == []
    assert messages == [("暂不能标记充电桩", "正在初始化所选地图")]


def test_navigation_page_refreshes_map_preview_after_mark_charging_dock(monkeypatch):
    scheduled = []
    monkeypatch.setattr(QTimer, "singleShot", lambda delay, callback: scheduled.append((delay, callback)))
    page = _FakeNavigationActionPage()
    page.preview_calls = 0
    page.navigation_command_task_id = 3
    page.navigation_command_operation = "标记充电桩中"

    def fetch_preview(*, force=False):
        page.preview_calls += 1
        page.preview_force = force
        return True

    page.fetch_navigation_map_preview = fetch_preview

    NavigationPage.on_runner_task_finished(page, 3, 0, "执行：标记充电桩")

    assert page.navigation_command_task_id is None
    assert page.navigation_command_operation == ""
    assert page.task_state.text == "任务\n标记完成"
    assert page.task_state.styles[-1] == "ready"
    assert page.nav_status_note.text == "充电桩标记已写入，正在刷新地图预览"
    assert [delay for delay, _callback in scheduled] == [200, 1200, 3200, 1200]
    assert any("充电桩标记完成" in line for line in page.navigation_log_lines)
    assert page.preview_calls == 1
    assert page.preview_force is True
    assert page.status_refreshes == 1
    for _delay, callback in scheduled:
        callback()
    assert page.preview_calls == 1
    assert page.status_refreshes == 5

    scheduled.clear()
    NavigationPage.on_runner_task_finished(page, 4, 1, "执行：标记充电桩")
    NavigationPage.on_runner_task_finished(page, 5, 0, "执行：ARC 有图回充")

    assert [delay for delay, _callback in scheduled] == [1200, 3200]


def test_navigation_page_arc_calibration_failure_is_reported_as_arc_task(monkeypatch):
    scheduled = []
    monkeypatch.setattr(QTimer, "singleShot", lambda delay, callback: scheduled.append((delay, callback)))
    page = _FakeNavigationActionPage()
    page.navigation_command_task_id = 8
    page.navigation_command_operation = "充电桩标定中"

    NavigationPage.on_runner_task_finished(page, 8, 3, "执行：ARC 标定充电桩")

    assert page.navigation_command_task_id is None
    assert page.navigation_command_operation == ""
    assert page.task_state.text == "任务\n标定失败"
    assert page.task_state.styles[-1] == "blocked"
    assert page.nav_status_note.text == "充电桩标定失败，请检查 ARC 状态机和任务日志"
    assert any("[ARC] 标定充电桩失败" in line for line in page.navigation_log_lines)
    assert not any("[导航] 任务失败" in line for line in page.navigation_log_lines)
    assert [delay for delay, _callback in scheduled] == [500, 1500, 3200]


def test_navigation_page_arc_recharge_finish_switches_to_charging(monkeypatch):
    scheduled = []
    monkeypatch.setattr(QTimer, "singleShot", lambda delay, callback: scheduled.append((delay, callback)))
    page = _FakeNavigationActionPage()
    page.workspace_dialog = _FakeWorkspaceDialog()
    page.nav_current_state = _FakeLabel()
    page.nav_action_status = _FakeLabel()
    page.navigation_command_task_id = 5
    page.navigation_command_operation = "有图进桩中"
    page.last_status_values = {
        "STATUS": "ready",
        "TEXT": "导航待命",
        "MAP_OK": "1",
        "LOAD_MAP_SERVICE": "1",
        "NAV_PROCESS": "1",
        "START_NAV_SUBSCRIBERS": "1",
        "LOCALIZATION_READY": "1",
        "PERCEPTION_READY": "1",
    }
    page.device_bar.mark_calls = 0

    def mark_charging_hint():
        page.device_bar.battery_last_charging = True
        page.device_bar.mark_calls += 1
        return True

    page.device_bar.mark_battery_charging_hint = mark_charging_hint

    NavigationPage.on_runner_task_finished(page, 5, 0, "执行：ARC 有图回充")

    assert page.device_bar.battery_last_charging is True
    assert page.device_bar.mark_calls == 1
    assert page.navigation_command_task_id is None
    assert page.navigation_command_operation == ""
    assert page.task_state.text == "任务\n充电中"
    assert page.task_state.styles[-1] == "success"
    assert page.nav_current_state.text == "当前状态\n✓ 充电中\nARC 已进入充电状态"
    assert page.nav_current_state.styles[-1] == "success"
    assert page.nav_status_note.text == "回充成功，已进入充电状态；如需离桩请点击“出桩”"
    assert page.mapped_recharge_button.text == "出桩"
    assert page.mapped_recharge_button.enabled is True
    assert page.workspace_dialog.mapped_recharge_button.text == "出桩"
    assert page.workspace_dialog.mapped_recharge_button.enabled is True
    assert page.last_status_values["ARC_DOCK_STATE"] == "2"
    assert page.last_status_values["ARC_DOCK_TEXT"] == "充电中"
    assert page.last_status_values["ARC_APP_DOCK_STATUS"] == "Charging"
    assert page.last_status_values["ARC_APP_ALG_STATUS"] == "Charging"
    assert "[ARC] 回充成功，已进入充电状态" in page.navigation_log_lines
    assert page.workspace_refreshes == 2
    assert [delay for delay, _callback in scheduled] == [1200, 3200]


def test_navigation_page_arc_undock_finish_switches_back_to_mapped_dock(monkeypatch):
    scheduled = []
    monkeypatch.setattr(QTimer, "singleShot", lambda delay, callback: scheduled.append((delay, callback)))
    page = _FakeNavigationActionPage()
    page.workspace_dialog = _FakeWorkspaceDialog()
    page.nav_current_state = _FakeLabel()
    page.nav_action_status = _FakeLabel()
    page.charging_docks = [(0, 1.0, 2.0, 0.0)]
    page.navigation_command_task_id = 6
    page.navigation_command_operation = "出桩中"
    page.last_status_values.update(
        {
            "STATUS": "success",
            "APP_NAV_STATUS": "Succeeded",
            "TEXT": "充电中",
            "ARC_DOCK_STATE": "2",
            "ARC_DOCK_TEXT": "充电中",
            "ARC_APP_DOCK_STATUS": "Charging",
            "ARC_APP_ALG_STATUS": "Charging",
        }
    )
    page.device_bar.battery_last_charging = True
    page.device_bar.clear_calls = 0

    def clear_charging_hint():
        page.device_bar.battery_last_charging = False
        page.device_bar.clear_calls += 1
        return True

    page.device_bar.clear_battery_charging_hint = clear_charging_hint

    NavigationPage.on_runner_task_finished(page, 6, 0, "执行：ARC 出桩")

    assert page.device_bar.battery_last_charging is False
    assert page.device_bar.clear_calls == 1
    assert page.navigation_command_task_id is None
    assert page.navigation_command_operation == ""
    assert page.task_state.text == "任务\n已出桩"
    assert page.task_state.styles[-1] == "ready"
    assert page.nav_current_state.text == "当前状态\n● 导航就绪"
    assert page.nav_current_state.styles[-1] == "ready"
    assert page.nav_status_note.text == "出桩成功，可再次使用“有图进桩”"
    assert page.mapped_recharge_button.text == "有图进桩"
    assert page.mapped_recharge_button.enabled is True
    assert page.mapped_recharge_button.visible is True
    assert page.workspace_dialog.mapped_recharge_button.text == "有图进桩"
    assert page.workspace_dialog.mapped_recharge_button.enabled is True
    assert "ARC_DOCK_STATE" not in page.last_status_values
    assert "ARC_APP_DOCK_STATUS" not in page.last_status_values
    assert "[ARC] 出桩成功，已离开充电状态" in page.navigation_log_lines
    assert page.workspace_refreshes == 2
    assert [delay for delay, _callback in scheduled] == [500, 1500, 3200]


def test_navigation_command_finish_schedules_remote_status_refresh(monkeypatch):
    scheduled = []
    monkeypatch.setattr(QTimer, "singleShot", lambda delay, callback: scheduled.append((delay, callback)))
    page = _FakeNavigationActionPage()
    page.navigation_command_task_id = 9
    page.navigation_command_operation = "路网导航中"

    NavigationPage.on_runner_task_finished(page, 9, 0, "执行：发送路网导航目标")

    assert [delay for delay, _callback in scheduled] == [200, 1200, 3200]
    for _delay, callback in scheduled:
        callback()
    assert page.status_refreshes == 3
    assert page.navigation_command_operation == "路网导航中"


def test_navigation_command_failure_clears_optimistic_running_state(monkeypatch):
    scheduled = []
    monkeypatch.setattr(QTimer, "singleShot", lambda delay, callback: scheduled.append((delay, callback)))
    page = _FakeNavigationActionPage()
    page.navigation_command_task_id = 9
    page.navigation_command_operation = "路网导航中"
    page.navigation_tracking_enabled = True
    page.navigation_status_watch_running = True

    NavigationPage.on_runner_task_finished(page, 9, 6, "执行：发送路网导航目标")

    assert page.navigation_tracking_enabled is False
    assert page.navigation_command_task_id is None
    assert page.navigation_command_operation == ""
    assert page.nav_status_note.text == "导航命令下发失败，请查看任务日志"
    assert any("任务失败" in line for line in page.navigation_log_lines)
    assert [delay for delay, _callback in scheduled] == [200, 1200, 3200]


def test_stop_navigation_finish_refreshes_remote_status_even_when_command_failed(monkeypatch):
    scheduled = []
    monkeypatch.setattr(QTimer, "singleShot", lambda delay, callback: scheduled.append((delay, callback)))
    page = _FakeNavigationActionPage()
    page.navigation_command_task_id = None
    page.navigation_command_operation = ""
    page.navigation_tracking_enabled = True
    page.navigation_tracking_active_seen = True
    page.navigation_status_watch_running = True
    page.last_status_values.update(
        {
            "STATUS": "active",
            "NAV_STATE": "100",
            "NAV_TASK_STATUS": "2",
            "TEXT": "导航执行中",
        }
    )
    page.navigation_global_route = [(1.0, 2.0, 0.0)]
    page.navigation_realtime_plan = [(1.0, 2.0, 0.0)]

    NavigationPage.on_runner_task_finished(page, 42, 7, "执行：停止导航")

    assert page.navigation_tracking_enabled is False
    assert page.navigation_tracking_active_seen is False
    assert page.navigation_status_watch_running is False
    assert page.navigation_command_task_id is None
    assert page.navigation_command_operation == ""
    assert page.navigation_global_route == []
    assert page.navigation_realtime_plan == []
    assert page.task_state.text == "任务\n停止已发送"
    assert page.nav_status_note.text == "停止命令返回异常，正在刷新远端状态"
    assert any("停止命令返回异常" in line for line in page.navigation_log_lines)
    assert [delay for delay, _callback in scheduled] == [0, 500, 1500, 3200]
    for _delay, callback in scheduled:
        callback()
    assert page.status_refreshes == 4


def test_navigation_page_mapped_dock_uses_start_arc_with_map_when_map_has_dock():
    page = _FakeNavigationActionPage()
    page.charging_docks = [(0, 1.0, 2.0, 0.0)]

    started = NavigationPage.make_mapped_dock_action(page)

    assert started is True
    spec, operation = page.runs[0]
    assert spec.title == "有图回充"
    assert spec.dangerous is True
    assert operation == "有图进桩中"
    assert "start_arc_with_map" in spec.command
    assert "loc_load_map" in spec.command
    assert "start_arc_align_coarse" in spec.command
    assert "已进入对准阶段，继续进桩" in spec.command
    assert page.navigation_log_lines[-1] == "[ARC] 已开始有图进桩"


def test_navigation_page_unmapped_dock_uses_arc_align_coarse():
    page = _FakeNavigationActionPage()

    started = NavigationPage.make_unmapped_dock_action(page)

    assert started is True
    spec, operation = page.runs[0]
    assert spec.title == "回充"
    assert spec.dangerous is True
    assert operation == "无图进桩中"
    assert "start_arc_align_coarse" in spec.command
    assert "start_arc_with_map" not in spec.command
    assert page.navigation_log_lines[-1] == "[ARC] 已开始无图进桩"


def test_navigation_page_unmapped_dock_ignores_map_preparation():
    page = _FakeNavigationActionPage()
    page.map_prepare_slot = _FakeSlot(running=True)

    ready, reason = NavigationPage.unmapped_dock_ready_reason(page, page.last_status_values)
    started = NavigationPage.make_unmapped_dock_action(page)

    assert ready is True
    assert reason == "请确认机器狗位于充电桩二维码正前方"
    assert started is True
    assert page.runs[0][0].title == "回充"


def test_navigation_page_arc_undock_uses_exit_charging_when_charging():
    page = _FakeNavigationActionPage(status_ok=False)
    page.device_bar.battery_last_charging = True

    started = NavigationPage.make_arc_undock_action(page)

    assert started is True
    spec, operation = page.runs[0]
    assert spec.title == "出桩"
    assert operation == "出桩中"
    assert "exit_charging" in spec.command


def test_navigation_page_legacy_mapped_recharge_still_switches_to_undock_when_charging():
    page = _FakeNavigationActionPage(status_ok=False)
    page.device_bar.battery_last_charging = True

    started = NavigationPage.make_mapped_recharge_action(page)

    assert started is True
    spec, operation = page.runs[0]
    assert spec.title == "出桩"
    assert operation == "出桩中"
    assert "exit_charging" in spec.command


def test_navigation_load_map_relocalizes_once_then_initializes_navigation():
    profile = get_product("xg2_s100")
    map_path = "/opt/data/.robot/map/a'map.pcd"

    spec = navigation.load_map_command(profile, map_path)
    remote_command = _remote_command(spec, profile.target)

    assert spec.concurrency == "parallel"
    assert spec.locks == ("navigation-map",)
    assert f"[ ! -s {quote(map_path)} ]" in remote_command
    assert quote(f"[ERROR] 地图 PCD 不存在或为空: {map_path}") in remote_command
    assert quote(f"[INFO] 使用导航地图: {map_path}") not in remote_command
    assert '{header: {frame_id: "map"}, cmd: 0' in _start_navigation_payloads(remote_command)[0]
    assert "地图初始化已发送" in remote_command
    assert "ros2 service call /load_map_service" not in remote_command
    assert "loc_load_map" in remote_command
    assert "get_loc_status" in remote_command
    assert "已通过 alg App 通道触发当前地图定位" not in remote_command
    assert "alg App 定位流程不可用或失败，回退导航定位服务流程" not in remote_command
    assert "from robots_dog_msgs.srv import LoadMap" not in remote_command
    assert 'create_client(LoadMap, "/load_map_service")' not in remote_command
    assert "/robot_slam/localization_state_service" not in remote_command
    assert "已通过 robot_slam 定位状态服务触发当前地图加载" not in remote_command
    assert "已请求定位加载当前地图" not in remote_command
    assert "当前地图定位已确认 ACTIVE" not in remote_command
    assert "dog_remote_clear_stale_slam_mapping_for_localization" not in remote_command
    assert "检测到 SLAM 仍在 ACTIVE" not in remote_command
    assert "SLAM_CANCEL_PAYLOAD='{mapping_type: 0, data: '\"$SLAM_CANCEL_DATA\"'}'" not in remote_command
    assert "取消后 SLAM 仍在 ACTIVE，暂不加载定位地图" not in remote_command
    assert "NAV_LOC_CODE" not in remote_command
    assert "MAP_PREP_LOC_CODE" not in remote_command
    assert "dog_remote_nav_load_map_client" not in remote_command
    assert "dog_remote_load_map_response_lost_ok" not in remote_command
    assert "LOAD_TIMEOUT" not in remote_command
    assert "tail -1000 \"$NAV_LOC_LOG\"" not in remote_command
    assert "grep -h \"map_path_prefix=\" \"$NAV_LOC_LOG\"" not in remote_command
    assert "map_path_prefix=\\([^ ]*\\)" not in remote_command
    assert "map_path_prefix=\\([^ .]*\\)" not in remote_command
    assert "NAV_LOC_ACTIVE_SEEN" not in remote_command
    assert "提前按定位就绪继续" not in remote_command
    assert "MAP_PREP_LOCALIZATION_READY=1" in remote_command
    assert "MAP_PREP_MAP_PCD=" in remote_command
    assert "定位状态已进入 ACTIVE，但未拿到地图加载成功回执" not in remote_command
    assert "导航栈快速检查通过" not in remote_command
    assert "ros2 topic info /start_navigation" not in remote_command
    assert "echo '[ERROR] 地图 PCD 不存在或为空:" not in remote_command
    assert "echo '[INFO] 使用导航地图:" not in remote_command


def test_navigation_prepare_map_command_relocalizes_only_during_map_prepare_then_initializes_nav():
    profile = get_product("xg2_s100")
    spec = navigation.prepare_map_command(profile, "/opt/data/.robot/map/map.pcd")
    remote_command = _remote_command(spec, profile.target)

    assert spec.title == "准备导航地图"
    assert spec.dangerous is False
    assert spec.concurrency == "parallel"
    assert spec.locks == ("navigation-map",)
    assert "ros2 service call /load_map_service" not in remote_command
    assert "loc_load_map" in remote_command
    assert "get_loc_status" in remote_command
    assert "已通过 alg App 通道触发当前地图定位" not in remote_command
    assert "alg App 定位流程不可用或失败，回退导航定位服务流程" not in remote_command
    assert "from robots_dog_msgs.srv import LoadMap" not in remote_command
    assert 'create_client(LoadMap, "/load_map_service")' not in remote_command
    assert "/robot_slam/localization_state_service" not in remote_command
    assert "data: 120" not in remote_command
    assert "已通过 robot_slam 定位状态服务触发当前地图加载" not in remote_command
    assert "已请求定位加载当前地图" not in remote_command
    assert "当前地图定位已确认 ACTIVE" not in remote_command
    assert "dog_remote_clear_stale_slam_mapping_for_localization" not in remote_command
    assert "取消旧建图/ARC标记态" not in remote_command
    assert "取消旧 SLAM ACTIVE 失败" not in remote_command
    assert "dog_remote_load_map_response_lost_ok" not in remote_command
    assert "LOAD_TIMEOUT=90" not in remote_command
    assert '{header: {frame_id: "map"}, cmd: 0' in _start_navigation_payloads(remote_command)[0]
    assert "INITIALIZE" not in remote_command
    assert "/opt/data/.robot/map/map.pcd" in remote_command
    assert "/opt/data/.robot/map/map.yaml" in remote_command
    assert "MAP_PREP_LOCALIZATION_READY=1" in remote_command
    assert "MAP_PREP_MAP_PCD=/opt/data/.robot/map/map.pcd" in remote_command
    assert "app定位地图加载状态回读失败，但 ROS 定位已正常" not in remote_command
    assert "/robot_slam/localization_state" not in remote_command
    assert "MAP_PREP_NAV_READY=1" in remote_command
    assert "MAP_PREP_SECONDS=" in remote_command
    assert "选中地图导航初始化已下发" in remote_command
    assert "start_goal" not in remote_command
    assert "ros2 topic list --no-daemon" not in remote_command
    assert "ros2 topic info /start_navigation" not in remote_command
    assert "导航下发通道" in remote_command
    assert "已提交到导航下发通道" not in remote_command
    assert "ros2 topic pub -1 /start_navigation" in remote_command
    assert "def publish_payload" not in remote_command
    assert "trap 'rm -f \"$INIT_PUB_LOG\" \"$PUB_LOG\"' EXIT" not in remote_command


def _route_stdin_script_text(command: str) -> str:
    match = re.search(r"< (/tmp/dog_remote_nav_scripts/route_nav_[^ ;]+[.]sh)", command)
    assert match is not None
    return Path(match.group(1)).read_text(encoding="utf-8")


def _route_stdin_start_payload(script: str) -> str:
    match = re.search(r"START_NAV_PAYLOAD=([A-Za-z0-9+/=]+)", script)
    assert match is not None
    return base64.b64decode(match.group(1).encode("ascii")).decode("utf-8")


def test_navigation_route_goal_uses_start_multi_nav_task_route_broker_without_route_graph_update():
    profile = get_product("xg1_nx")
    route_path = "/ota/alg_data/map/history_map/a/map.geojson"

    spec = navigation.start_route_goal_command(
        profile,
        "/ota/alg_data/map/history_map/a/map.pcd",
        route_path,
        1.0,
        2.0,
        0.3,
        0.5,
        0.2,
    )
    remote_command = spec.command
    route_script = _route_stdin_script_text(remote_command)

    assert "导航栈快速检查通过" not in remote_command
    assert "ros2 topic info /start_navigation" not in remote_command
    assert len(remote_command) < 16_000
    assert "bash -s < /tmp/dog_remote_nav_scripts/route_nav_" in remote_command
    assert route_path not in remote_command
    assert route_path in route_script
    assert "地图 PCD 不存在或为空" in route_script
    assert "导航地图文件不存在或为空" not in route_script
    assert "路网地图初始化已下发，等待导航回到 STANDBY" not in remote_command
    assert "导航已就绪，可发送目标" not in remote_command
    assert "导航状态未及时回读，继续发送目标" not in remote_command
    assert "导航初始化后未回到 STANDBY" not in remote_command
    assert "dog_remote_nav_standby_wait" not in remote_command
    assert "NAV_STANDBY_ALLOW_UNKNOWN" not in remote_command
    assert "导航栈可能已崩溃或仍在启动，尝试重启 robot-alg-manager" not in remote_command
    assert "robot-launch restart robot-alg-manager" not in remote_command
    assert "正在等待路网服务恢复" not in remote_command
    assert "路网服务已恢复" not in remote_command
    assert "DOG_REMOTE_ROUTE_GRAPH_CACHE" not in remote_command
    assert "ROUTE_GRAPH_CACHE_KEY" not in remote_command
    assert "路网更新服务未就绪: /RouteGraphPlanner/update_graph" not in remote_command
    assert "ROUTE_GRAPH_NAV_CONTAINER_PID" not in remote_command
    assert "/RouteGraphPlanner/update_graph" not in remote_command
    assert "ros2 service list --no-daemon" not in remote_command
    assert "路网未变化，跳过重复更新" not in remote_command
    assert "NAV_PRE_MSG=$(timeout 2s ros2 topic echo --once /navigation_state" not in remote_command
    assert "NAV_PRE_MSG=$(timeout 2s ros2 topic echo --once /navigation_state --no-daemon" not in remote_command
    assert "正在提交路网导航目标" in route_script
    assert "start_multi_nav_by_points" not in remote_command
    assert "start_multi_nav_by_points" not in route_script
    assert '"dog_remote_points"' not in route_script
    assert "START_NAV_PAYLOAD=" not in route_script
    assert "/start_navigation" not in route_script
    assert "dog_remote_start_navigation_helper.py" not in route_script
    assert "start_multi_nav_task" in route_script
    assert '"type":"goal"' in route_script
    assert '"map_type":"route"' in route_script
    assert '"goal_task_type":"route"' in route_script
    assert '"goals":[{"position":{"x":1.0,"y":2.0,"z":0.0}' in route_script
    assert "导航服务已就绪，使用快速下发" in route_script
    assert "快速下发不可用，使用兼容下发" in route_script
    assert route_script.index("正在提交路网导航目标") < route_script.index("start_multi_nav_task")
    assert "导航下发通道" not in route_script
    assert "已提交到导航下发通道" not in remote_command
    assert "NAV_START_DEADLINE" not in remote_command
    assert "导航任务已开始" not in remote_command
    assert "导航目标指令已提交，但任务进入失败状态" not in remote_command
    assert "导航目标指令已提交，但未观察到进入执行状态" not in remote_command
    assert "NAV_START_LAST_ERROR" not in remote_command
    assert "dog_remote_nav_release_watch.log" not in route_script
    route_start = route_script.index("正在提交路网导航目标")
    assert '"stop_nav"' in route_script[route_start:]
    assert "NAV_ALL_TASKS_TERMINAL=1" not in route_script


@pytest.mark.parametrize("profile_key", ["xg1_nx", "zg_lidar_nx"])
def test_navigation_route_goal_multi_points_emit_multiple_route_tasks(profile_key):
    profile = get_product(profile_key)
    route_path = "/ota/alg_data/map/history_map/a/map.geojson"

    spec = navigation.start_route_goal_command(
        profile,
        "/ota/alg_data/map/history_map/a/map.pcd",
        route_path,
        2.0,
        3.0,
        0.0,
        0.5,
        0.2,
        points=[(1.0, 2.0, 0.0), (2.0, 3.0, 0.0)],
    )
    route_script = _route_stdin_script_text(spec.command)

    assert route_script.count('"type":"goal"') == 2
    assert route_script.count('"goal_task_type":"route"') == 2
    assert '"position":{"x":1.0,"y":2.0,"z":0.0}' in route_script
    assert '"position":{"x":2.0,"y":3.0,"z":0.0}' in route_script
    assert '"goals":[{"position":{"x":1.0,"y":2.0,"z":0.0}' in route_script
    assert '"goals":[{"position":{"x":2.0,"y":3.0,"z":0.0}' in route_script
    assert "start_multi_nav_by_points" not in route_script
    assert "/start_navigation" not in route_script


def test_l2_route_navigation_click_path_uses_shared_route_broker_payload():
    profile = get_product("xg2_s100")
    route_path = "/opt/data/.robot/map/history_map/a/map.geojson"

    spec = navigation.start_route_goal_command(
        profile,
        "/opt/data/.robot/map/history_map/a/map.pcd",
        route_path,
        1.0,
        2.0,
        0.3,
        0.5,
        0.2,
    )
    remote_command = spec.command
    route_script = _route_stdin_script_text(remote_command)

    assert "DOG_REMOTE_ROUTE_GRAPH_CACHE" not in remote_command
    assert "路网未变化，跳过重复更新" not in remote_command
    assert "路网更新服务未就绪: /RouteGraphPlanner/update_graph" not in remote_command
    assert "ros2 service call /RouteGraphPlanner/update_graph" not in remote_command
    assert "ros2 service list --no-daemon" not in remote_command
    assert "for _route_wait_i" not in remote_command
    assert "robot-launch restart robot-alg-manager" not in remote_command
    assert "正在等待路网服务恢复" not in remote_command
    assert "NAV_PRE_MSG=" not in remote_command
    assert "上一导航仍未结束" not in remote_command
    assert "start_multi_nav_by_points" not in remote_command
    assert "start_multi_nav_by_points" not in route_script
    assert "/start_navigation" not in route_script
    assert "dog_remote_start_navigation_helper.py" not in route_script
    assert "start_multi_nav_task" in route_script
    assert '"map_type":"route"' in route_script
    assert '"goal_task_type":"route"' in route_script
    assert "dog_remote_nav_release_watch.log" not in route_script
    assert '"stop_nav"' in route_script
    assert "DOG_REMOTE_DISABLE_BODY_NAV_BRIDGE" in spec.command
    assert "robot-launch start robot_roamerx" in spec.command
    assert "/robot_control_server/nav_pose" in spec.command


def test_navigation_route_file_commands_quote_paths_in_status_messages():
    profile = get_product("xg2_s100")
    map_path = "/opt/data/.robot/map/a'map.pcd"
    route_path = "/opt/data/.robot/route/r'oute.geojson"

    route_spec = navigation.start_route_goal_command(profile, map_path, route_path, 1.0, 2.0, 0.3, 0.5, 0.2)
    route_command = route_spec.command
    route_script = _route_stdin_script_text(route_command)

    assert quote(f"[ERROR] 路网文件不存在或为空: {route_path}") in route_script
    assert quote(f"[INFO] 发送路网导航目标 x=1.000 y=2.000 yaw=0.300 speed=0.50 route={route_path}") not in route_script
    assert "正在提交路网导航目标" in route_script
    assert "echo '[ERROR] 路网文件不存在或为空:" not in route_script
    assert "上一导航仍未结束" not in route_script
    assert "上一导航已停止，继续发送新目标" not in route_script
    assert "导航模式已更新" not in route_script


def test_navigation_route_loop_skips_route_initialize_wait():
    profile = get_product("xg1_nx")
    spec = navigation.start_route_goal_loop_command(
        profile,
        "/ota/alg_data/map/history_map/a/map.pcd",
        "/ota/alg_data/map/history_map/a/map.geojson",
        1.0,
        2.0,
        0.3,
        0.5,
        0.2,
        [(1.0, 2.0, 0.3), (2.0, 3.0, 0.4)],
    )
    remote_command = _remote_command(spec, profile.target)

    assert "NAV_STANDBY_ALLOW_ACTIVE_INITIALIZING" not in remote_command
    assert "导航仍在初始化，继续发送路网目标" not in remote_command
    assert "dog_remote_nav_standby_wait" not in remote_command


def test_probe_status_command_checks_navigation_prerequisites():
    assert navigation.probe_status_command is navigation_probe.probe_status_command
    assert navigation.fast_probe_status_command is navigation_probe.fast_probe_status_command
    assert navigation.status_command is navigation_probe.status_command
    assert navigation_probe.navigation_graph_status_probe_shell() == navigation_probe_graph.navigation_graph_status_probe_shell()
    assert navigation_probe.topic_count_assignments("/cmd_vel", "CMD_VEL") == navigation_probe_motion.topic_count_assignments(
        "/cmd_vel", "CMD_VEL"
    )
    assert navigation_probe.motion_velocity_sample_shell(
        "/cmd_vel", "CMD_VEL"
    ) == navigation_probe_motion.motion_velocity_sample_shell("/cmd_vel", "CMD_VEL")
    assert navigation_probe.motion_control_chain_probe_shell() == navigation_probe_motion.motion_control_chain_probe_shell()

    command = navigation.probe_status_command(get_product("xg2_s100"), "/opt/data/.robot/map/map.pcd")
    app_status_command = navigation.probe_status_command(
        get_product("xg2_s100"),
        "/opt/data/.robot/map/map.pcd",
        skip_arc_app_status=False,
    )
    navigation_command = navigation.probe_status_command(
        get_product("xg2_s100"),
        "/opt/data/.robot/map/map.pcd",
        skip_arc_app_status=True,
    )
    lightweight_command = navigation.probe_status_command(
        get_product("xg2_s100"),
        "/opt/data/.robot/map/map.pcd",
        include_motion_chain=False,
    )

    assert "get_loc_status" in command
    assert "LOCALIZATION_TOPIC=alg:get_loc_status" in command
    assert "/navigo/ea/cmn/intf/nav_errors" in command
    assert "/navigation_cmd" in command
    assert "/handle_vel" in command
    assert "/robot_control_server/nav_pose" in command
    assert "/robot_control_server/mc_state" in command
    assert "/robot_roamerx/is_in_nav_control" in command
    assert "NAV_ERRORS_PUBLISHERS" in command
    assert "NAV_CURRENT_TASK_IDX" in command
    assert "NAV_ESTIMATED_DISTANCE_REMAINING" in command
    assert "NAV_ESTIMATED_TIME_REMAINING_SEC" in command
    assert "/arc/dock_state" in command
    assert "/arc/arc_state" in command
    assert "get_arc_alg_status" in command
    assert "get_arc_alg_status" in app_status_command
    assert "DOG_REMOTE_SKIP_ARC_APP_STATUS=1" not in command
    assert "DOG_REMOTE_SKIP_ARC_APP_STATUS=1" not in app_status_command
    assert "DOG_REMOTE_SKIP_ARC_APP_STATUS=1" in navigation_command
    assert "ARC_APP_CHANNEL=SKIPPED_BY_CALLER" in navigation_command
    assert "ARC_APP_DOCK_STATUS" in command
    assert 'case "$NAV_TASK_STATUS" in' in command
    assert "STATUS=starting" in command
    assert "导航初始化" in command
    assert "2) STATUS=active" in command
    assert "$NAV_TASK\" = 1" not in command
    assert "NAVIGATION_CMD_PUBLISHERS" in command
    assert "NAVIGATION_CMD_VEL" in command
    assert "HANDLE_VEL_VEL" in command
    assert "CMD_VEL_VEL" in command
    assert "ros2 topic echo --once /navigation_cmd" in command
    assert "ROBOT_CONTROL_SERVER_NAV_POSE_SUBSCRIBERS" in command
    assert "LOAD_MAP_SERVICE" in command
    assert "/start_navigation" in command
    assert "SLAM_VERSION=$(dpkg-query" in command
    assert "timeout 3s ros2 topic list --no-daemon" in command
    assert "timeout 3s ros2 service list --no-daemon" not in command
    assert "timeout 3s ros2 topic echo --once \"$topic\" --no-daemon" not in command
    assert "timeout 2s ros2 topic echo --once /navigation_state --no-daemon" in command
    assert "timeout 2s ros2 topic echo --once /navigo/ea/cmn/intf/nav_errors --no-daemon" in command
    assert "LASER_SCAN_STAMP_AGE_MS" in command
    assert "CURRENT_POSE_STAMP_AGE_MS" in command
    assert "LOCALIZATION_STATE_STAMP_AGE_MS" not in command
    assert "date +%s%N" in command
    assert "timeout 1.5s ros2 topic echo --once /navigation_cmd --no-daemon" in command
    assert "timeout 2s ros2 topic info /localization_state --no-daemon" not in command
    assert "timeout 2s ros2 topic info /robot_slam/localization_state --no-daemon" not in command
    assert "timeout 2s ros2 topic info /start_navigation --no-daemon" in command
    assert "timeout 2s ros2 topic info /navigation_cmd --no-daemon" in command
    assert "NAVIGATION_CMD_TOPIC_INFO=$(timeout 2s ros2 topic info /navigation_cmd --no-daemon" in command
    assert "HANDLE_VEL_TOPIC_INFO=$(timeout 2s ros2 topic info /handle_vel --no-daemon" in command
    assert "ROBOT_CONTROL_SERVER_NAV_POSE_TOPIC_INFO=$(timeout 2s ros2 topic info /robot_control_server/nav_pose --no-daemon" in command
    assert "NAVIGATION_CMD_TOPIC_INFO=$(timeout 2s ros2 topic info /navigation_cmd --no-daemon" not in lightweight_command
    assert "timeout 2s ros2 topic echo --once /navigation_state --no-daemon" in lightweight_command
    assert "dog_remote_nav_graph_probe" in command
    assert "node.get_subscriptions_info_by_topic(\"/start_navigation\")" in command
    assert command.count("ros2 topic info /navigation_cmd") == 1
    assert command.count("ros2 topic info /handle_vel") == 1
    assert command.count("ros2 topic info /cmd_vel") == 1
    assert command.count("ros2 topic info /robot_roamerx/is_in_nav_control") == 1
    assert command.count("ros2 topic info /robot_control_server/nav_pose") == 1
    assert command.count("ros2 topic info /robot_control_server/mc_state") == 1
    assert "timeout 0.8s ros2 topic list" not in command
    assert "timeout 0.8s ros2 topic echo --once /navigation_state" not in command
    assert "timeout 0.6s ros2 topic echo --once /navigo/ea/cmn/intf/nav_errors" not in command
    assert "timeout 0.5s ros2 topic info /start_navigation" not in command
    assert "MAP_OK" in command
    assert "NAV_TO_POSE_SERVERS" not in command
    assert "DETECTION2D_PUBLISHERS" not in command
    assert "LICENSE_OK" not in command
    assert "CALIBRATION_OK" not in command
    assert "CURRENT_POSE_PUBLISHERS" not in command
    assert "LOCALIZATION_ODOM_PUBLISHERS" not in command
    assert "READY_LIFECYCLE_SERVICES" not in command


def test_fast_probe_status_command_keeps_ui_status_minimal():
    command = navigation.fast_probe_status_command(get_product("xg2_s100"), "/opt/data/.robot/map/map.pcd")

    assert "MAP_OK" in command
    assert "NAV_PROCESS" in command
    assert "timeout 3s ros2 topic list --no-daemon" in command
    assert "get_loc_status" in command
    assert "timeout 3s ros2 topic echo --once \"$topic\" --no-daemon" not in command
    assert "timeout 1s ros2 topic echo --once /navigation_state --no-daemon" not in command
    assert "timeout 1s ros2 topic info /start_navigation --no-daemon" not in command
    assert "START_NAV_SUBSCRIBERS=1" in command
    assert "NAV_STATE_PUBLISHERS" in command
    assert "DOG_REMOTE_SKIP_ARC_APP_STATUS=1" in command
    assert "dog_remote_nav_graph_probe" not in command
    assert "NAVIGATION_CMD_PUBLISHERS" not in command
    assert "LASER_SCAN_STAMP_AGE_MS" not in command
    assert "/navigo/ea/cmn/intf/nav_errors" not in command
    assert "/arc/dock_state" not in command


def test_zg_navigation_probe_accepts_status_six_when_description_is_active():
    command = navigation.probe_status_command(get_product("zg_lidar_nx"), "/ota/alg_data/map/map.pcd")

    assert "get_loc_status" in command
    assert "ContinuousLoc|continuousloc|LocOk|InitLocOk" in command
    assert "require_nav_accepted_status" not in command


def test_navigation_probe_service_exists_quotes_service_name():
    service_name = "/load_map'service"

    command = navigation_probe.service_exists(service_name, 4)

    assert "timeout 4s ros2 service list --no-daemon" in command
    assert f"awk -v target={quote(service_name)}" in command
    assert f'$0=="{service_name}"' not in command



class _FakeLabel:
    def __init__(self):
        self.text = ""
        self.styles = []
        self.tooltip = ""

    def setText(self, text):
        self.text = text

    def setStyleSheet(self, style):
        self.styles.append(style)

    def setToolTip(self, tooltip):
        self.tooltip = tooltip


class _FakeButton:
    def __init__(self):
        self.text = ""
        self.enabled = None
        self.tooltip = ""
        self.visible = True
        self.object_name = ""
        self.checked = False
        self.checkable = False

    def setText(self, text):
        self.text = text

    def setEnabled(self, enabled):
        self.enabled = enabled

    def setToolTip(self, tooltip):
        self.tooltip = tooltip

    def setVisible(self, visible):
        self.visible = visible

    def setCheckable(self, checkable):
        self.checkable = checkable

    def setChecked(self, checked):
        self.checked = checked

    def setObjectName(self, name):
        self.object_name = name

    def style(self):
        class _Style:
            def unpolish(self, _widget):
                return None

            def polish(self, _widget):
                return None

        return _Style()



class _FakeOutput:
    def __init__(self, page=None):
        self.page = page
        self.emits = []

    def emit(self, text):
        self.emits.append(text)
        if self.page is not None:
            NavigationPage.capture_navigation_log(self.page, text)


class _FakeProcess:
    def __init__(self):
        self.readyReadStandardOutput = _FakeSignal()
        self.finished = _FakeSignal()
        self.started = False

    def start(self):
        self.started = True


class _FakeSlot:
    def __init__(self, running=False, read_result=False, output=""):
        self.running = running
        self.start_calls = []
        self.stop_calls = 0
        self.read_result = read_result
        self.read_calls = []
        self.finish_output = output
        self.finish_calls = []
        self.process = _FakeProcess()

    def is_running(self):
        return self.running

    def start_bash(self, command):
        self.start_calls.append(command)
        self.running = True
        return self.process, 15

    def start_spec(self, spec):
        return self.start_bash(spec.command)

    def stop(self):
        self.stop_calls += 1
        self.running = False

    def read_available_output(self, process, request_id):
        self.read_calls.append((process, request_id))
        return self.read_result

    def read_available_text(self, process, request_id):
        self.read_calls.append((process, request_id))
        return self.finish_output

    def finish(self, process, request_id):
        self.finish_calls.append((process, request_id))
        self.running = False
        return self.finish_output


class _FakeTimer:
    def __init__(self):
        self.started = False
        self.stopped = False
        self.start_count = 0
        self.stop_count = 0

    def start(self):
        self.started = True
        self.start_count += 1

    def stop(self):
        self.stopped = True
        self.stop_count += 1


class _FakeText:
    def __init__(self, text=""):
        self._text = text
        self.texts = []

    def text(self):
        return self._text

    def setText(self, text):
        self.texts.append(text)
        self._text = text


class _FakeMapSelector:
    def __init__(self, selected_map="/opt/data/.robot/map/map.pgm"):
        self.items = []
        self.tooltips = {}
        self.current_index = -1
        self.selected_map = selected_map
        if selected_map:
            self.addItem("current", selected_map)
            self.current_index = 0

    def currentData(self):
        if 0 <= self.current_index < len(self.items):
            return self.items[self.current_index][1]
        return self.selected_map

    def clear(self):
        self.items = []
        self.tooltips = {}
        self.current_index = -1

    def addItem(self, label, data):
        self.items.append((label, data))
        if self.current_index < 0:
            self.current_index = 0

    def setItemData(self, index, value, _role):
        self.tooltips[index] = value

    def count(self):
        return len(self.items)

    def findData(self, data):
        for index, (_label, item_data) in enumerate(self.items):
            if item_data == data:
                return index
        return -1

    def setCurrentIndex(self, index):
        self.current_index = index

    def currentIndex(self):
        return self.current_index


class _FakeCursor:
    def __init__(self):
        self.moves = []

    def movePosition(self, position):
        self.moves.append(position)


class _FakeWaypointText:
    def __init__(self, text=""):
        self._text = text
        self.cursor = _FakeCursor()
        self.set_cursors = []

    def toPlainText(self):
        return self._text

    def setPlainText(self, text):
        self._text = text

    def textCursor(self):
        return self.cursor

    def setTextCursor(self, cursor):
        self.set_cursors.append(cursor)


class _FakeSpin:
    def __init__(self, value=0.0):
        self._value = value
        self.values = []

    def value(self):
        return self._value

    def setValue(self, value):
        self.values.append(value)
        self._value = value


class _FakeWaypointList:
    def __init__(self, row=-1):
        self.row = row
        self.rows = []

    def currentRow(self):
        return self.row

    def clear(self):
        self.rows = []

    def addItems(self, rows):
        self.rows.extend(rows)

    def setCurrentRow(self, row):
        self.row = row


class _FakeNavigationWaypointPage:
    def __init__(self, text=""):
        self.waypoints_text = _FakeWaypointText(text)
        self.waypoints_list = _FakeWaypointList()
        self.goal_x = _FakeSpin()
        self.goal_y = _FakeSpin()
        self.goal_yaw = _FakeSpin()
        self.direction_degrees = _FakeSpin()
        self.goal_point_selected = bool(text.strip())
        self.nav_map = _FakeWorkspaceCanvas()
        self.nav_status_note = _FakeLabel()
        self.workspace_refreshes = 0
        self._syncing_direction = False

    def refresh_workspace_from_page(self):
        self.workspace_refreshes += 1

    def update_target_hint(self):
        self.workspace_refreshes += 1


class _FakeWorkspaceCanvas:
    def __init__(self):
        self.global_routes = []
        self.realtime_plans = []
        self.obstacle_points = []
        self.charging_docks = []
        self.points = []
        self.route_graphs = []
        self.route_target_node_ids = []

    def set_global_route(self, route):
        self.global_routes.append(route)

    def set_realtime_plan(self, plan):
        self.realtime_plans.append(plan)

    def set_obstacle_points(self, points):
        self.obstacle_points.append(list(points))

    def set_charging_docks(self, docks):
        self.charging_docks.append(docks)

    def set_points(self, points):
        self.points.append(points)

    def set_route_graph(self, graph):
        self.route_graphs.append(graph)

    def set_route_target_node_ids(self, node_ids):
        self.route_target_node_ids.append(list(node_ids))


class _FakeWorkspaceDialog:
    def __init__(self):
        self.canvas = _FakeWorkspaceCanvas()
        self.point_summary = _FakeLabel()
        self.cruise_button = _FakeButton()
        self.point_nav_button = _FakeButton()
        self.loop_button = _FakeButton()
        self.relocalize_button = _FakeButton()
        self.route_mode_button = _FakeButton()
        self.route_goal_button = _FakeButton()
        self.choose_route_file_button = _FakeButton()
        self.upload_route_file_button = _FakeButton()
        self.export_route_file_button = _FakeButton()
        self.arc_calibration_button = _FakeButton()
        self.arc_mark_button = _FakeButton()
        self.mapped_recharge_button = _FakeButton()
        self.mapped_dock_button = _FakeButton()
        self.unmapped_dock_button = _FakeButton()
        self.arc_undock_button = _FakeButton()
        self.pause_resume_button = _FakeButton()
        self.stop_button = _FakeButton()
        self.action_status_label = _FakeLabel()


class _FakeNavigationRunPage:
    def __init__(self, task_id=None):
        self.runner = _FakeRunner(task_id=task_id)
        self.page_active = True
        self.last_status_values = {
            "STATUS": "ready",
            "MAP_PCD": "/opt/data/.robot/map/map.pcd",
            "MAP_OK": "1",
            "LOAD_MAP_SERVICE": "1",
            "LOCALIZATION_READY": "1",
            "NAV_PROCESS": "1",
            "START_NAV_SUBSCRIBERS": "1",
        }
        self.map_pcd_path = _FakeText("/opt/data/.robot/map/map.pcd")
        self.prepared_map_pcd_path = "/opt/data/.robot/map/map.pcd"
        self.map_prepare_slot = None
        self.cruise_button = _FakeButton()
        self.point_nav_button = _FakeButton()
        self.relocalize_button = _FakeButton()
        self.route_mode_button = _FakeButton()
        self.route_goal_button = _FakeButton()
        self.arc_calibration_button = _FakeButton()
        self.arc_mark_button = _FakeButton()
        self.mapped_recharge_button = _FakeButton()
        self.mapped_dock_button = _FakeButton()
        self.unmapped_dock_button = _FakeButton()
        self.arc_undock_button = _FakeButton()
        self.pause_resume_button = _FakeButton()
        self.stop_button = _FakeButton()
        self.map_state = _FakeLabel()
        self.localization_state = _FakeLabel()
        self.navigation_state = _FakeLabel()
        self.task_state = _FakeLabel()
        self.map_state = _FakeLabel()
        self.localization_state = _FakeLabel()
        self.navigation_state = _FakeLabel()
        self.flow_detail = _FakeLabel()
        self.cruise_button = _FakeButton()
        self.point_nav_button = _FakeButton()
        self.loop_button = _FakeButton()
        self.relocalize_button = _FakeButton()
        self.route_mode_button = _FakeButton()
        self.route_goal_button = _FakeButton()
        self.choose_route_file_button = _FakeButton()
        self.upload_route_file_button = _FakeButton()
        self.export_route_file_button = _FakeButton()
        self.arc_calibration_button = _FakeButton()
        self.arc_mark_button = _FakeButton()
        self.mapped_recharge_button = _FakeButton()
        self.mapped_dock_button = _FakeButton()
        self.unmapped_dock_button = _FakeButton()
        self.arc_undock_button = _FakeButton()
        self.pause_resume_button = _FakeButton()
        self.stop_button = _FakeButton()
        self.nav_status_note = _FakeLabel()
        self.navigation_log_lines = []
        self.current_spec = CommandSpec("旧命令", "true")
        self.workspace_refreshes = 0
        self.finished_visualization_statuses = []

    def profile(self):
        return get_product("xg2_s100")

    def _set_card_style(self, label, state):
        label.setStyleSheet(state)

    def refresh_workspace_from_page(self):
        self.workspace_refreshes += 1


class _FakeNavigationInspectPage:
    def __init__(self, started=False):
        self.started = started
        self.map_state = _FakeLabel()
        self.localization_state = _FakeLabel()
        self.perception_state = _FakeLabel()
        self.nav_current_state = _FakeLabel()
        self.navigation_state = _FakeLabel()
        self.task_state = _FakeLabel()
        self.nav_code_detail = _FakeLabel()
        self.flow_detail = _FakeLabel()
        self.commands = []

    def navigation_values(self):
        return ("/opt/data/.robot/map/map.pcd", 0.0, 0.0, 0.0, 0.5, 0.2)

    def profile(self):
        return get_product("xg2_s100")

    def set_command(self, spec):
        self.commands.append(spec)
        return self.started

    def _set_card_style(self, label, state):
        label.setStyleSheet(state)


class _FakeNavigationActionPage:
    def __init__(self, status_ok=True):
        self.status_ok = status_ok
        self.page_active = True
        self.runs = []
        self.map_pcd = "/opt/data/.robot/map/map.pcd"
        self.last_status_at = time.monotonic()
        self.last_status_values = (
            {
                "MAP_OK": "1",
                "MAP_PCD": "/opt/data/.robot/map/map.pcd",
                "LOAD_MAP_SERVICE": "1",
                "NAV_PROCESS": "1",
                "START_NAV_SUBSCRIBERS": "1",
                "LOCALIZATION_READY": "1",
                "PERCEPTION_READY": "1",
            }
            if status_ok
            else {
                "MAP_OK": "0",
                "LOAD_MAP_SERVICE": "0",
                "START_NAV_SUBSCRIBERS": "0",
                "LOCALIZATION_READY": "0",
                "PERCEPTION_READY": "0",
            }
        )
        self.map_state = _FakeLabel()
        self.localization_state = _FakeLabel()
        self.perception_state = _FakeLabel()
        self.nav_current_state = _FakeLabel()
        self.navigation_state = _FakeLabel()
        self.task_state = _FakeLabel()
        self.nav_code_detail = _FakeLabel()
        self.flow_detail = _FakeLabel()
        self.cruise_button = _FakeButton()
        self.point_nav_button = _FakeButton()
        self.loop_button = _FakeButton()
        self.relocalize_button = _FakeButton()
        self.route_mode_button = _FakeButton()
        self.route_goal_button = _FakeButton()
        self.choose_route_file_button = _FakeButton()
        self.upload_route_file_button = _FakeButton()
        self.export_route_file_button = _FakeButton()
        self.arc_calibration_button = _FakeButton()
        self.arc_mark_button = _FakeButton()
        self.mapped_recharge_button = _FakeButton()
        self.mapped_dock_button = _FakeButton()
        self.unmapped_dock_button = _FakeButton()
        self.arc_undock_button = _FakeButton()
        self.pause_resume_button = _FakeButton()
        self.stop_button = _FakeButton()
        self.route_pull_slot = _FakeSlot(running=False)
        self.route_pull_remote_pgm = ""
        self.route_pull_local_file = ""
        self.nav_status_note = _FakeLabel()
        self.status_refreshes = 0
        self.map_pgm = "/opt/data/.robot/map/history_map/2026_06_02/map.pgm"
        self.route_file_states = {self.map_pgm: True}
        self.route_geojson_path = _FakeText(route_network.DEFAULT_REMOTE_ROUTE_FILE)
        self.goal_point_selected = True
        self.workspace_refreshes = 0
        self.robot_pose = (0.0, 0.0, 0.0)
        self.navigation_global_route = []
        self.navigation_realtime_plan = []
        self.charging_docks = []
        self.navigation_tracking_enabled = False
        self.navigation_tracking_active_seen = False
        self.navigation_status_watch_running = False
        self.navigation_command_task_id = None
        self.navigation_command_operation = ""
        self.navigation_command_idle_confirmations = 0
        self.navigation_body_release_after_terminal_triggered = False
        self.runner = _FakeRunner(task_id=100)
        self.runner.output = _FakeOutput(self)
        self.stop_navigation_waiting_remote_confirm = False
        self.stop_navigation_waiting_started_at = 0.0
        self.navigation_global_plan_topic = ""
        self.navigation_realtime_plan_topic = ""
        self.navigation_log_lines = []
        self.nav_map = _FakeWorkspaceCanvas()
        self.waypoints_text = _FakeWaypointText("1.000,2.000,0.000\n3.000,4.000,0.000")
        self.route_graph = route_network.RouteGraph(
            nodes={
                1: route_network.RouteNode(1, 1.0, 2.0),
                2: route_network.RouteNode(2, 3.0, 4.0),
            },
            edges={
                1: route_network.RouteEdge(1, 1, 2, [(1.0, 2.0), (3.0, 4.0)]),
            },
        )
        self.route_graph_remote_pgm = self.map_pgm
        self.route_graph_local_path = "/opt/data/.robot/map/history_map/2026_06_02/map.geojson"
        self.route_target_mode = True
        self.route_target_node_ids = [1, 2]
        self.goal_x = _FakeSpin(1.0)
        self.goal_y = _FakeSpin(2.0)
        self.goal_yaw = _FakeSpin(0.0)
        self.direction_degrees = _FakeSpin(0.0)
        self.map_pcd_path = _FakeText(self.map_pcd)
        self.prepared_map_pcd_path = self.map_pcd
        self.preparing_map_pcd_path = ""
        self.map_prepare_error = ""
        self.map_prepare_auto_retry_pcd = ""
        self.pending_navigation_action = ""
        self.navigation_loop_enabled = False
        self.map_prepare_slot = None
        self.device_bar = type("DeviceBar", (), {"battery_last_charging": False})()

    def navigation_values(self):
        return (self.map_pcd, self.goal_x.value(), self.goal_y.value(), self.goal_yaw.value(), 0.5, 0.2)

    def navigation_points(self):
        return NavigationPage.navigation_points(self)

    def selected_map_pgm(self):
        return self.map_pgm

    def local_preview_dir(self, _remote_pgm):
        return Path("/tmp/dog_remote_tool_test_preview")

    def target_summary_text(self):
        return "目标点：点击地图添加目标"

    def profile(self):
        return get_product("xg2_s100")

    def navigation_supported(self):
        return True

    def refresh_navigation_status(self):
        self.status_refreshes += 1
        return True

    def _set_card_style(self, label, state):
        label.setStyleSheet(state)

    def run_navigation_spec(self, spec, operation):
        self.runs.append((spec, operation))
        return True

    def run_robot_task_spec(self, spec, operation):
        self.runs.append((spec, operation))
        return True

    def start_selected_map_preparation(self, force=False):
        return NavigationPage.start_selected_map_preparation(self, force=force)

    def refresh_workspace_from_page(self):
        self.workspace_refreshes += 1

    def update_target_hint(self):
        self.workspace_refreshes += 1

    def finish_navigation_visualization_if_terminal(self, status):
        return NavigationPage.finish_navigation_visualization_if_terminal(self, status)


class _FakeNavigationRefreshPage:
    def __init__(self, *, active=True, supported=True, status_running=False, list_running=False, preview_running=False, selected_map="/opt/data/.robot/map/map.pgm"):
        self.page_active = active
        self.supported = supported
        self.status_slot = _FakeSlot(running=status_running)
        self.map_list_slot = _FakeSlot(running=list_running)
        self.map_preview_slot = _FakeSlot(running=preview_running)
        self.map_prepare_slot = _FakeSlot(running=False)
        self.route_check_slot = _FakeSlot(running=False)
        self.route_pull_slot = _FakeSlot(running=False)
        self.mode_switch_helper_slot = _FakeSlot(running=False)
        self.pose_stream_slot = _FakeSlot(running=False)
        self.pose_stream_buffer = ""
        self.plan_stream_slot = _FakeSlot(running=False)
        self.plan_stream_buffer = ""
        self.obstacle_stream_slot = _FakeSlot(running=False)
        self.obstacle_stream_buffer = ""
        self.robot_pose = None
        self.navigation_global_route = []
        self.navigation_realtime_plan = []
        self.navigation_obstacle_points = []
        self.navigation_obstacle_topic = ""
        self.obstacle_overlay_enabled = True
        self.charging_docks = []
        self.route_graph = None
        self.route_graph_remote_pgm = ""
        self.route_graph_local_path = ""
        self.route_target_mode = False
        self.route_target_node_ids = []
        self.route_pull_remote_pgm = ""
        self.route_pull_local_file = ""
        self.navigation_tracking_enabled = False
        self.navigation_tracking_active_seen = False
        self.navigation_status_watch_running = False
        self.navigation_command_task_id = None
        self.stop_navigation_waiting_remote_confirm = False
        self.stop_navigation_waiting_started_at = 0.0
        self.navigation_global_plan_topic = ""
        self.navigation_realtime_plan_topic = ""
        self.navigation_log_lines = []
        self.workspace_dialog = None
        self.open_workspace_after_preview = False
        self.map_selector = _FakeMapSelector(selected_map)
        self.save_map_path = _FakeText("/opt/data/.robot/map")
        self.nav_map = _FakeText()
        self.map_pcd_path = _FakeText()
        self.route_geojson_path = _FakeText(route_network.DEFAULT_REMOTE_ROUTE_FILE)
        self.last_status_values = {"old": "1"}
        self.last_status_state = "old"
        self.last_status_at = 0.0
        self.last_navigation_action_reason = ""
        self.prepared_map_pcd_path = ""
        self.preparing_map_pcd_path = ""
        self.map_prepare_error = ""
        self.map_prepare_auto_retry_pcd = ""
        self.pending_navigation_action = ""
        self.navigation_loop_enabled = False
        self.card_values = []
        self.map_entries_signature = ()
        self.map_details = {}
        self.map_cards = {}
        self.map_card_updates = []
        self.map_card_selection_updates = 0
        self.clear_map_card_calls = 0
        self.route_file_states = {}
        self.local_route_exists = False
        self.detail_updates = 0
        self.preview_calls = 0
        self.preview_force_calls = []
        self.status_refresh_calls = 0
        self.start_navigation_camera_overlay_calls = 0
        self.stop_navigation_camera_overlay_calls = 0
        self.robot_pose_updates = []
        self.finished_visualization_statuses = []
        self.workspace_refreshes = 0
        self.finished_visualization_statuses = []
        self.map_state = _FakeLabel()
        self.localization_state = _FakeLabel()
        self.perception_state = _FakeLabel()
        self.nav_current_state = _FakeLabel()
        self.navigation_state = _FakeLabel()
        self.task_state = _FakeLabel()
        self.nav_code_detail = _FakeLabel()
        self.nav_status_note = _FakeLabel()
        self.nav_action_status = _FakeLabel()
        self.flow_detail = _FakeLabel()
        self.cruise_button = _FakeButton()
        self.point_nav_button = _FakeButton()
        self.loop_button = _FakeButton()
        self.relocalize_button = _FakeButton()
        self.route_mode_button = _FakeButton()
        self.route_goal_button = _FakeButton()
        self.choose_route_file_button = _FakeButton()
        self.upload_route_file_button = _FakeButton()
        self.export_route_file_button = _FakeButton()
        self.arc_calibration_button = _FakeButton()
        self.arc_mark_button = _FakeButton()
        self.mapped_recharge_button = _FakeButton()
        self.mapped_dock_button = _FakeButton()
        self.unmapped_dock_button = _FakeButton()
        self.arc_undock_button = _FakeButton()
        self.pause_resume_button = _FakeButton()
        self.stop_button = _FakeButton()
        self.navigation_log_lines = []

    def profile(self):
        return get_product("xg2_s100")

    def navigation_supported(self):
        return self.supported

    def selected_map_pgm(self):
        return str(self.map_selector.currentData() or "")

    def local_preview_dir(self, _remote_pgm):
        class LocalPreview:
            def __init__(self, exists, name=""):
                self.exists_value = exists
                self.name = name

            def __truediv__(self, name):
                return LocalPreview(self.exists_value if name == "map.geojson" else False, name)

            def exists(self):
                return self.exists_value

        return LocalPreview(self.local_route_exists)

    def navigation_values(self):
        return ("/opt/data/.robot/map/map.pcd", 0.0, 0.0, 0.0, 0.5, 0.2)

    def set_cards_from_values(self, values, detail=""):
        self.card_values.append((values, detail))

    def _set_card_style(self, label, state):
        label.setStyleSheet(state)

    def read_status_output(self, process, request_id):
        return NavigationPage.read_status_output(self, process, request_id)

    def status_finished(self, process, exit_code, request_id):
        return NavigationPage.status_finished(self, process, exit_code, request_id)

    def read_map_list_output(self, process, request_id):
        return NavigationPage.read_map_list_output(self, process, request_id)

    def map_list_finished(self, process, exit_code, request_id):
        return NavigationPage.map_list_finished(self, process, exit_code, request_id)

    def read_map_preview_output(self, process, request_id):
        return NavigationPage.read_map_preview_output(self, process, request_id)

    def map_preview_finished(self, process, exit_code, local_dir, request_id):
        pass

    def update_selected_map_detail(self):
        self.detail_updates += 1

    def update_map_cards(self, entries):
        self.map_card_updates.append(tuple(entries))
        self.map_cards = {remote: object() for _label, remote, _detail in entries[:5]}

    def update_map_card_selection(self):
        self.map_card_selection_updates += 1

    def clear_map_cards(self):
        self.clear_map_card_calls += 1
        self.map_cards = {}

    def fetch_navigation_map_preview(self, *, force=False):
        self.preview_calls += 1
        self.preview_force_calls.append(force)
        return True

    def refresh_navigation_status(self):
        self.status_refresh_calls += 1
        return True

    def refresh_map_list(self):
        return NavigationPage.refresh_map_list(self)

    def start_pose_stream(self):
        return NavigationPage.start_pose_stream(self)

    def start_plan_stream(self):
        return NavigationPage.start_plan_stream(self)

    def start_navigation_camera_overlay(self):
        self.start_navigation_camera_overlay_calls += 1

    def stop_navigation_camera_overlay(self):
        self.stop_navigation_camera_overlay_calls += 1

    def refresh_workspace_from_page(self):
        self.workspace_refreshes += 1

    def finish_navigation_visualization_if_terminal(self, status):
        self.finished_visualization_statuses.append(status)

    def ensure_navigation_helpers(self):
        return NavigationPage.ensure_navigation_helpers(self)

    def read_map_preparation_output(self, process, request_id):
        return NavigationPage.read_map_preparation_output(self, process, request_id)

    def map_preparation_finished(self, process, exit_code, request_id):
        return NavigationPage.map_preparation_finished(self, process, exit_code, request_id)

    def read_navigation_helpers_output(self, process, request_id):
        return NavigationPage.read_navigation_helpers_output(self, process, request_id)

    def navigation_helpers_finished(self, process, exit_code, request_id):
        return NavigationPage.navigation_helpers_finished(self, process, exit_code, request_id)

    ensure_mode_switch_helper = ensure_navigation_helpers
    read_mode_switch_helper_output = read_navigation_helpers_output
    mode_switch_helper_finished = navigation_helpers_finished

    def handle_robot_pose_update(self, pose):
        return NavigationPage.handle_robot_pose_update(self, pose)

    def update_robot_pose_on_maps(self):
        self.robot_pose_updates.append(self.robot_pose)

    def _stop_refresh_processes(self, clear_maps):
        return NavigationPage._stop_refresh_processes(self, clear_maps)


def test_navigation_run_spec_marks_not_started_when_runner_rejects_start():
    page = _FakeNavigationRunPage()
    spec = CommandSpec("发送导航目标", "ros2 topic pub /start_navigation")

    started = NavigationPage.run_navigation_spec(page, spec, "发送目标中")

    assert started is False
    assert page.task_state.text == "任务\n任务未启动"
    assert page.task_state.styles == ["starting", "blocked"]
    assert page.flow_detail.text == "流程摘要\n任务未启动"
    assert page.current_spec is None
    assert len(page.runner.run_calls) == 1
    assert page.workspace_refreshes >= 1


def test_navigation_run_spec_shows_pending_remote_acceptance(monkeypatch):
    monkeypatch.setattr(NavigationPage, "update_navigation_action_buttons", lambda self, values: True)
    page = _FakeNavigationRunPage(task_id=7)
    page.nav_current_state = _FakeLabel()
    page.nav_code_detail = _FakeLabel()
    spec = CommandSpec("发送路网导航目标", "ros2 topic pub /start_navigation")

    started = NavigationPage.run_navigation_spec(page, spec, "路网导航中")

    assert started is True
    assert page.navigation_command_task_id == 7
    assert page.navigation_command_operation == "路网导航中"
    assert page.task_state.text == "任务\n路网目标下发中"
    assert page.nav_current_state.text == "当前状态\n● 路网目标下发中\n等待远端接收路网目标并进入执行中"
    assert page.nav_status_note.text == "等待远端接收路网目标并进入执行中"
    assert page.nav_code_detail.text == "等待远端接收路网目标并进入执行中"
    assert page.nav_code_detail.tooltip == "等待远端接收路网目标并进入执行中"


def test_navigation_run_robot_task_spec_does_not_mark_navigation_pending(monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)
    monkeypatch.setattr(NavigationPage, "update_navigation_action_buttons", lambda self, values: True)
    page = _FakeNavigationRunPage(task_id=7)
    page.navigation_command_task_id = None
    page.navigation_command_operation = ""
    spec = CommandSpec("标定充电桩", "true", dangerous=True, display_command="执行：ARC 标定充电桩")

    started = NavigationPage.run_robot_task_spec(page, spec, "充电桩标定中")

    assert started is True
    assert len(page.runner.run_calls) == 1
    assert page.task_state.text == "任务\n充电桩标定中"
    assert page.navigation_command_task_id is None
    assert page.navigation_command_operation == ""
    assert page.nav_status_note.text == ""


def test_navigation_run_spec_cancelled_dangerous_command_does_not_run(monkeypatch):
    page = _FakeNavigationRunPage(task_id=7)
    spec = CommandSpec("停止导航", "ros2 topic pub /start_navigation", dangerous=True)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.No)

    started = NavigationPage.run_navigation_spec(page, spec, "停止中")

    assert started is False
    assert page.runner.run_calls == []
    assert page.task_state.text == ""


def test_navigation_run_spec_runs_dangerous_command_after_confirm(monkeypatch):
    page = _FakeNavigationRunPage(task_id=7)
    spec = CommandSpec("停止导航", "ros2 topic pub /start_navigation", dangerous=True)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)

    started = NavigationPage.run_navigation_spec(page, spec, "停止中")

    assert started is True
    assert len(page.runner.run_calls) == 1
    assert page.task_state.text == "任务\n停止中"
    assert page.workspace_refreshes >= 1


def test_navigation_inspect_marks_not_started_when_runner_rejects_start():
    page = _FakeNavigationInspectPage(started=False)

    started = NavigationPage.make_inspect_navigation(page)

    assert started is False
    assert [command.title for command in page.commands] == ["解析导航包/状态"]
    assert page.task_state.text == "任务\n任务未启动"
    assert page.task_state.styles == ["blocked"]
    assert page.flow_detail.text == "流程摘要\n导航状态检查未启动，当前有任务运行，请稍后再试。"


def test_navigation_inspect_marks_started_when_runner_starts():
    page = _FakeNavigationInspectPage(started=True)

    started = NavigationPage.make_inspect_navigation(page)

    assert started is True
    assert [command.title for command in page.commands] == ["解析导航包/状态"]
    assert page.task_state.text == ""
    assert page.flow_detail.text == "流程摘要\n导航状态检查已启动"


def test_navigation_add_waypoint_from_map_returns_change_result():
    page = _FakeNavigationWaypointPage(" \n1.000,2.000,0.000\n")

    assert NavigationPage.add_waypoint_from_map(page, 3.2, -4.5678) is True
    assert page.waypoints_text.toPlainText() == "1.000,2.000,0.000\n3.200000000,-4.567800000,0.000000000"
    assert page.waypoints_text.cursor.moves
    assert page.waypoints_text.set_cursors == [page.waypoints_text.cursor]


def test_navigation_delete_selected_waypoint_updates_text_map_and_list():
    page = _FakeNavigationWaypointPage("1.000,2.000,0.000\n3.000,4.000,1.571\n5.000,6.000,0.200")

    assert NavigationPage.delete_navigation_point(page, 1) is True

    assert page.waypoints_text.toPlainText() == "1.000,2.000,0.000\n5.000,6.000,0.200"
    assert page.nav_map.points[-1] == [(1.0, 2.0, 0.0), (5.0, 6.0, 0.2)]
    assert page.waypoints_list.rows == [
        "1. x=1.000, y=2.000, 方向=0°",
        "2. x=5.000, y=6.000, 方向=11°",
    ]
    assert page.waypoints_list.currentRow() == 1
    assert page.goal_x.value() == 5.0
    assert page.goal_y.value() == 6.0
    assert page.goal_yaw.value() == 0.2
    assert page.goal_point_selected is True
    assert page.workspace_refreshes == 1
    assert "已删除目标点 2" in page.nav_status_note.text


def test_navigation_action_wrappers_return_run_result():
    page = _FakeNavigationActionPage()

    assert NavigationPage.make_load_map(page) is True
    assert NavigationPage.make_start_goal(page) is True
    assert NavigationPage.make_stop_navigation(page) is True

    assert [operation for _spec, operation in page.runs] == ["加载地图中", "发送目标中", "停止中"]


def test_navigation_relocalize_forces_current_ready_map_preparation():
    page = _FakeNavigationActionPage()
    page.map_prepare_slot = _FakeSlot(running=False)
    page.prepared_map_pcd_path = page.map_pcd

    assert NavigationPage.make_relocalize_selected_map(page) is True

    assert page.prepared_map_pcd_path == ""
    assert page.preparing_map_pcd_path == page.map_pcd
    assert page.map_prepare_slot.start_calls
    assert page.nav_status_note.text == "正在为所选地图加载定位并初始化导航"
    assert any("已请求重新定位当前地图" in line for line in page.navigation_log_lines)


def test_navigation_pause_resume_toggle_uses_remote_state():
    page = _FakeNavigationActionPage()
    page.last_status_values = {"STATUS": "active", "NAV_STATE": "100", "NAV_TASK_STATUS": "2"}

    assert NavigationPage.make_toggle_navigation_pause(page) is True

    assert page.runs[-1][1] == "暂停中"
    assert "pause_nav" in page.runs[-1][0].command
    assert "{header: {frame_id: \"map\"}, cmd:" not in page.runs[-1][0].command
    assert page.navigation_tracking_enabled is True

    page.last_status_values = {"STATUS": "paused", "NAV_STATE": "3", "NAV_TASK_STATUS": "3"}

    assert NavigationPage.make_toggle_navigation_pause(page) is True

    assert page.runs[-1][1] == "继续中"
    assert "continue_nav" in page.runs[-1][0].command
    assert "{header: {frame_id: \"map\"}, cmd:" not in page.runs[-1][0].command


def test_navigation_pause_finish_switches_button_to_continue():
    page = _FakeNavigationActionPage()
    page.last_status_values.update({"STATUS": "active", "TEXT": "导航执行中"})

    NavigationPage.on_runner_task_finished(page, 101, 0, "执行：暂停导航")

    assert page.last_status_values["STATUS"] == "paused"
    assert page.pause_resume_button.text == "继续"
    assert page.pause_resume_button.enabled is True


def test_navigation_continue_finish_switches_button_to_pause():
    page = _FakeNavigationActionPage()
    page.last_status_values.update({"STATUS": "paused", "TEXT": "导航暂停"})

    NavigationPage.on_runner_task_finished(page, 102, 0, "执行：继续导航")

    assert page.last_status_values["STATUS"] == "active"
    assert page.pause_resume_button.text == "暂停"
    assert page.pause_resume_button.enabled is True


def test_navigation_pause_resume_toggle_rejects_idle_state():
    page = _FakeNavigationActionPage()
    page.last_status_values = {"STATUS": "ready", "NAV_STATE": "1", "NAV_TASK_STATUS": "0"}

    assert NavigationPage.make_toggle_navigation_pause(page) is False

    assert page.runs == []
    assert page.nav_status_note.text == "当前没有可暂停的导航任务"


def test_navigation_loop_button_only_toggles_mode_without_starting_task():
    page = _FakeNavigationActionPage()
    page.runs = []

    assert NavigationPage.toggle_navigation_loop(page) is True

    assert page.navigation_loop_enabled is True
    assert page.runs == []
    assert page.loop_button.text == "循环 ON"
    assert page.loop_button.object_name == "LoopSwitchOn"
    assert page.loop_button.checked is True
    assert "循环模式已开启" in page.nav_status_note.text

    assert NavigationPage.toggle_navigation_loop(page) is False

    assert page.navigation_loop_enabled is False
    assert page.runs == []
    assert page.loop_button.text == "循环 OFF"
    assert page.loop_button.object_name == "LoopSwitchOff"
    assert page.loop_button.checked is False


def test_navigation_goal_start_sets_global_route_and_realtime_plan():
    page = _FakeNavigationActionPage()

    assert NavigationPage.make_start_goal(page) is True

    assert page.navigation_tracking_enabled is True
    assert page.navigation_global_route == []
    assert page.navigation_realtime_plan == []
    assert page.navigation_log_lines == []


def test_navigation_start_enables_fast_status_watch(monkeypatch):
    scheduled = []
    monkeypatch.setattr(
        "dog_remote_tool.ui.pages.navigation.page.QTimer.singleShot",
        lambda delay, callback: scheduled.append((delay, callback)),
    )
    page = _FakeNavigationActionPage()

    NavigationPage.begin_navigation_visualization(page)

    assert page.navigation_status_watch_running is True
    assert [delay for delay, _callback in scheduled] == [500, 0, 0, 0]


def test_navigation_start_skips_obstacle_stream_when_toggle_is_off(monkeypatch):
    scheduled = []
    monkeypatch.setattr(
        "dog_remote_tool.ui.pages.navigation.page.QTimer.singleShot",
        lambda delay, callback: scheduled.append((delay, callback)),
    )
    page = _FakeNavigationActionPage()
    page.obstacle_overlay_enabled = False

    NavigationPage.begin_navigation_visualization(page)

    assert [delay for delay, _callback in scheduled] == [500, 0, 0]


def test_navigation_obstacle_stream_starts_and_updates_maps(monkeypatch):
    monkeypatch.setattr("dog_remote_tool.ui.pages.navigation.streams.localization.obstacle_stream_command", lambda profile: "obstacle-stream")
    page = _FakeNavigationRefreshPage()
    page.workspace_dialog = _FakeWorkspaceDialog()
    page.nav_map = _FakeWorkspaceCanvas()
    page.map_pcd_path.setText("/opt/data/.robot/map/map.pcd")
    page.prepared_map_pcd_path = "/opt/data/.robot/map/map.pcd"
    page.navigation_tracking_enabled = True

    assert NavigationPage.start_obstacle_stream(page) is True

    assert page.obstacle_stream_buffer == ""
    assert page.obstacle_stream_slot.start_calls == ["obstacle-stream"]
    assert page.obstacle_stream_slot.process.started is True

    page.obstacle_stream_slot.finish_output = "OBS=ok TOPIC=/laser_scan FRAME=map COUNT=2 POINTS=1.000,2.000;3.000,4.000\n"
    NavigationPage.read_obstacle_stream_output(page, page.obstacle_stream_slot.process, 15)

    assert page.navigation_obstacle_points == [(1.0, 2.0), (3.0, 4.0)]
    assert page.navigation_obstacle_topic == "/laser_scan"
    assert page.nav_map.obstacle_points[-1] == [(1.0, 2.0), (3.0, 4.0)]
    assert page.workspace_dialog.canvas.obstacle_points[-1] == [(1.0, 2.0), (3.0, 4.0)]


def test_navigation_obstacle_toggle_stops_and_clears_stream():
    page = _FakeNavigationRefreshPage()
    page.workspace_dialog = _FakeWorkspaceDialog()
    page.obstacle_overlay_enabled = True
    page.navigation_obstacle_points = [(1.0, 2.0)]
    page.nav_map = _FakeWorkspaceCanvas()
    page.obstacle_stream_slot = _FakeSlot(running=True)

    assert NavigationPage.toggle_obstacle_overlay(page) is False

    assert page.obstacle_overlay_enabled is False
    assert page.obstacle_stream_slot.stop_calls == 1
    assert page.navigation_obstacle_points == []
    assert page.nav_map.obstacle_points[-1] == []
    assert page.workspace_dialog.canvas.obstacle_points[-1] == []


def test_navigation_status_watch_refreshes_until_terminal(monkeypatch):
    scheduled = []
    monkeypatch.setattr(
        "dog_remote_tool.ui.pages.navigation.page.QTimer.singleShot",
        lambda delay, callback: scheduled.append((delay, callback)),
    )
    page = _FakeNavigationActionPage()
    page.navigation_tracking_enabled = True
    page.navigation_status_watch_running = True

    assert NavigationPage.continue_navigation_status_watch(page) is True

    assert page.status_refreshes == 1
    assert [delay for delay, _callback in scheduled] == [navigation_visualization.NAVIGATION_STATUS_WATCH_INTERVAL_MS]

    page.navigation_tracking_enabled = False
    assert NavigationPage.continue_navigation_status_watch(page) is False
    assert page.navigation_status_watch_running is False
    assert page.status_refreshes == 1


def test_navigation_ready_after_started_task_finishes_and_resets_target_numbering():
    page = _FakeNavigationActionPage()
    page.workspace_dialog = _FakeWorkspaceDialog()
    page.navigation_global_route = [(1.0, 1.0, 0.0), (2.0, 2.0, 0.0)]
    page.navigation_realtime_plan = [(3.0, 3.0, 0.0), (4.0, 4.0, 0.0)]
    page.nav_map.set_global_route(page.navigation_global_route)
    page.nav_map.set_realtime_plan(page.navigation_realtime_plan)
    page.workspace_dialog.canvas.set_global_route(page.navigation_global_route)
    page.workspace_dialog.canvas.set_realtime_plan(page.navigation_realtime_plan)

    NavigationPage.begin_navigation_visualization(page)
    NavigationPage.finish_navigation_visualization_if_terminal(page, "active")
    page.navigation_global_route = [(1.0, 1.0, 0.0), (2.0, 2.0, 0.0)]
    page.navigation_realtime_plan = [(3.0, 3.0, 0.0), (4.0, 4.0, 0.0)]
    page.nav_map.set_global_route(page.navigation_global_route)
    page.nav_map.set_realtime_plan(page.navigation_realtime_plan)
    page.workspace_dialog.canvas.set_global_route(page.navigation_global_route)
    page.workspace_dialog.canvas.set_realtime_plan(page.navigation_realtime_plan)
    NavigationPage.finish_navigation_visualization_if_terminal(page, "success")

    assert page.navigation_tracking_enabled is True
    assert page.navigation_global_route != []

    page.navigation_command_idle_confirmations = 2
    page.last_status_values.update(
        {
            "STATUS": "success",
            "APP_NAV_STATUS": "Succeeded",
            "NAV_STATE": "1",
            "NAV_TASK_STATUS": "",
            "NAV_DISTANCE_FROM_START": "2.0",
            "NAV_ESTIMATED_DISTANCE_REMAINING": "0.0",
        }
    )
    NavigationPage.finish_navigation_visualization_if_terminal(page, "success")

    assert page.navigation_tracking_enabled is False
    assert page.navigation_tracking_active_seen is False
    assert page.navigation_status_watch_running is False
    assert page.navigation_global_route == []
    assert page.navigation_realtime_plan == []
    assert page.nav_map.global_routes[-1] == []
    assert page.nav_map.realtime_plans[-1] == []
    assert page.workspace_dialog.canvas.global_routes[-1] == []
    assert page.workspace_dialog.canvas.realtime_plans[-1] == []
    assert page.goal_point_selected is False
    assert page.waypoints_text.toPlainText() == ""
    assert page.nav_map.points[-1] == []
    assert page.workspace_dialog.canvas.points[-1] == []
    assert page.workspace_dialog.point_summary.text == "目标点：点击地图添加目标"
    assert page.nav_status_note.text == "导航任务已结束，可重新选择目标点"
    assert not any("已清空旧规划线" in line for line in page.navigation_log_lines)


def test_navigation_finish_does_not_release_body_control_automatically():
    page = _FakeNavigationActionPage()
    page.runner = _FakeRunner(task_id=101)
    page.navigation_command_idle_confirmations = 2
    page.last_status_values.update(
        {
            "STATUS": "success",
            "APP_NAV_STATUS": "Succeeded",
            "NAV_STATE": "1",
            "NAV_TASK_STATUS": "",
            "NAV_DISTANCE_FROM_START": "2.0",
            "NAV_ESTIMATED_DISTANCE_REMAINING": "0.0",
        }
    )

    NavigationPage.begin_navigation_visualization(page)
    NavigationPage.finish_navigation_visualization_if_terminal(page, "success")

    assert page.runner.run_calls == []
    assert page.navigation_body_release_after_terminal_triggered is True


def test_navigation_ready_does_not_finish_while_start_command_is_running():
    page = _FakeNavigationActionPage()
    page.runner = _FakeRunner(tasks={7: object()})
    page.navigation_command_task_id = 7

    NavigationPage.begin_navigation_visualization(page)
    NavigationPage.finish_navigation_visualization_if_terminal(page, "ready")

    assert page.navigation_tracking_enabled is True
    assert page.goal_point_selected is True
    assert page.waypoints_text.toPlainText() != ""

    page.runner.tasks.clear()
    NavigationPage.finish_navigation_visualization_if_terminal(page, "active")
    page.navigation_command_idle_confirmations = 2
    page.last_status_values.update(
        {
            "STATUS": "ready",
            "NAV_STATE": "1",
            "NAV_TASK_STATUS": "",
            "NAV_DISTANCE_FROM_START": "2.0",
            "NAV_ESTIMATED_DISTANCE_REMAINING": "0.0",
        }
    )
    NavigationPage.finish_navigation_visualization_if_terminal(page, "ready")

    assert page.navigation_tracking_enabled is False
    assert page.navigation_command_task_id is None
    assert page.goal_point_selected is False
    assert page.waypoints_text.toPlainText() == ""


def test_navigation_ready_finishes_after_idle_confirmations_even_if_active_was_missed():
    page = _FakeNavigationActionPage()
    page.runner = _FakeRunner(tasks={})
    page.navigation_command_task_id = None
    page.navigation_command_operation = ""
    page.navigation_command_idle_confirmations = 2
    page.last_status_values.update(
        {
            "STATUS": "ready",
            "NAV_STATE": "1",
            "NAV_TASK_STATUS": "",
            "NAV_DISTANCE_FROM_START": "2.0",
            "NAV_ESTIMATED_DISTANCE_REMAINING": "0.0",
        }
    )

    NavigationPage.begin_navigation_visualization(page)
    NavigationPage.finish_navigation_visualization_if_terminal(page, "ready")

    assert page.navigation_tracking_enabled is False
    assert page.navigation_command_task_id is None
    assert page.goal_point_selected is False
    assert page.waypoints_text.toPlainText() == ""


def test_navigation_ready_does_not_finish_without_arrival_evidence():
    page = _FakeNavigationActionPage()
    page.runner = _FakeRunner(tasks={})
    page.navigation_command_task_id = None
    page.navigation_command_operation = ""
    page.navigation_command_idle_confirmations = 2
    page.last_status_values.update(
        {
            "STATUS": "ready",
            "NAV_STATE": "1",
            "NAV_TASK_STATUS": "",
            "NAV_DISTANCE_FROM_START": "0.0",
            "NAV_ESTIMATED_DISTANCE_REMAINING": "4.0",
        }
    )

    NavigationPage.begin_navigation_visualization(page)
    NavigationPage.finish_navigation_visualization_if_terminal(page, "active")
    NavigationPage.finish_navigation_visualization_if_terminal(page, "ready")

    assert page.navigation_tracking_enabled is True
    assert page.goal_point_selected is True
    assert page.waypoints_text.toPlainText() != ""


def test_navigation_workspace_events_are_mirrored_to_runner_output():
    page = _FakeNavigationActionPage()
    page.runner = type("Runner", (), {})()
    page.runner.output = _FakeOutput(page)

    NavigationPage.begin_navigation_visualization(page)

    assert page.runner.output.emits == []
    assert page.navigation_log_lines == []
    assert page.workspace_refreshes == 0


def test_navigation_goal_click_queues_while_map_prepares():
    page = _FakeNavigationActionPage()
    page.map_prepare_slot = _FakeSlot(running=True)
    page.prepared_map_pcd_path = ""

    assert NavigationPage.make_start_goal(page) is False

    assert page.runs == []
    assert page.pending_navigation_action == "goal"
    assert page.nav_status_note.text == "单点导航已排队，地图和定位就绪后自动下发"
    assert any("单点导航已排队" in line for line in page.navigation_log_lines)


def test_navigation_stop_clears_pending_auto_goal():
    page = _FakeNavigationActionPage()
    page.pending_navigation_action = "goal"
    page.workspace_dialog = _FakeWorkspaceDialog()

    assert NavigationPage.make_stop_navigation(page) is True

    assert page.pending_navigation_action == ""
    assert page.runs[-1][1] == "停止中"
    assert page.stop_button.enabled is False
    assert page.stop_button.text == "停止中"
    assert page.workspace_dialog.stop_button.enabled is False
    assert page.workspace_dialog.stop_button.text == "停止中"
    assert page.stop_button.tooltip == "停止命令已发送，正在等待远端确认"
    assert page.nav_status_note.text == "已取消等待地图和定位就绪的导航任务"
    assert any("已取消等待地图和定位就绪的导航任务" in line for line in page.navigation_log_lines)


def test_navigation_stop_button_uses_fresh_remote_status_after_stop_request():
    page = _FakeNavigationRefreshPage()
    page.map_pcd_path.setText("/opt/data/.robot/map/map.pcd")
    page.prepared_map_pcd_path = "/opt/data/.robot/map/map.pcd"
    page.stop_navigation_waiting_remote_confirm = True
    page.stop_navigation_waiting_started_at = 10.0
    page.last_status_at = 9.0
    active_values = {
        "STATUS": "active",
        "TEXT": "导航执行中",
        "MAP_PCD": "/opt/data/.robot/map/map.pcd",
        "MAP_OK": "1",
        "LOAD_MAP_SERVICE": "1",
        "NAV_PROCESS": "1",
        "START_NAV_SUBSCRIBERS": "1",
        "LOCALIZATION_READY": "1",
        "NAV_STATE": "100",
        "NAV_TASK_STATUS": "2",
    }

    NavigationPage.update_navigation_action_buttons(page, active_values)

    assert page.stop_button.text == "停止中"
    assert page.stop_button.enabled is False
    assert page.stop_navigation_waiting_remote_confirm is True

    page.last_status_at = 11.0
    NavigationPage.update_navigation_action_buttons(page, active_values)

    assert page.stop_button.text == "停止"
    assert page.stop_button.enabled is True
    assert page.stop_navigation_waiting_remote_confirm is False

    ready_values = dict(active_values)
    ready_values.update({"STATUS": "ready", "TEXT": "导航待命", "NAV_STATE": "1", "NAV_TASK_STATUS": "0"})
    NavigationPage.update_navigation_action_buttons(page, ready_values)

    assert page.stop_button.text == "停止"
    assert page.stop_button.enabled is True
    assert page.stop_button.tooltip == "发送停止命令并释放导航控制权"


def test_navigation_pending_action_rejects_invalid_or_missing_map():
    page = _FakeNavigationActionPage()

    assert NavigationPage.queue_pending_navigation_action(page, "invalid") is False
    assert page.pending_navigation_action == ""

    page.map_pcd_path.setText("")

    assert NavigationPage.queue_pending_navigation_action(page, "goal") is False
    assert page.pending_navigation_action == ""


def test_navigation_pending_goal_continues_after_map_preparation_ready(monkeypatch):
    monkeypatch.setattr(
        "dog_remote_tool.ui.pages.navigation.page.QTimer.singleShot",
        lambda delay, callback: callback() if delay == 0 else None,
    )
    page = _FakeNavigationRefreshPage()
    page.goal_point_selected = True
    page.pending_navigation_action = "goal"
    page.map_pcd_path.setText("/opt/data/.robot/map/map.pcd")
    page.preparing_map_pcd_path = "/opt/data/.robot/map/map.pcd"
    page.map_prepare_slot.running = True
    page.map_prepare_slot.finish_output = "[INFO] 导航地图初始化已下发，不等待状态回读\n"
    page.runs = []

    def run_navigation_spec(spec, operation):
        page.runs.append((spec, operation))
        return True

    page.run_navigation_spec = run_navigation_spec

    assert NavigationPage.map_preparation_finished(page, page.map_prepare_slot.process, 0, 15) is True

    assert page.pending_navigation_action == ""
    assert len(page.runs) == 1
    spec, operation = page.runs[-1]
    assert spec.title == "发送导航目标"
    assert operation == "发送目标中"
    assert page.nav_status_note.text == "地图初始化和定位已确认，正在自动下发导航任务"

    page.status_slot = _FakeSlot(
        output=(
            "STATUS=ready\n"
            "TEXT=可发送目标\n"
            "MAP_PCD=/opt/data/.robot/map/map.pcd\n"
            "MAP_OK=1\n"
            "LOAD_MAP_SERVICE=1\n"
            "LOCALIZATION_READY=1\n"
            "NAV_PROCESS=1\n"
            "START_NAV_SUBSCRIBERS=1\n"
        )
    )

    assert NavigationPage.status_finished(page, page.status_slot.process, 0, 25) is True

    assert page.pending_navigation_action == ""
    assert page.runs
    spec, operation = page.runs[-1]
    assert operation == "发送目标中"
    assert spec.title == "发送导航目标"


def test_navigation_pending_goal_stays_queued_until_status_ready(monkeypatch):
    monkeypatch.setattr(
        "dog_remote_tool.ui.pages.navigation.page.QTimer.singleShot",
        lambda delay, callback: callback() if delay == 0 else None,
    )
    page = _FakeNavigationRefreshPage()
    page.goal_point_selected = True
    page.pending_navigation_action = "goal"
    page.map_pcd_path.setText("/opt/data/.robot/map/map.pcd")
    page.prepared_map_pcd_path = "/opt/data/.robot/map/map.pcd"
    page.runs = []
    page.status_slot = _FakeSlot(
        output=(
            "STATUS=blocked\n"
            "TEXT=等待连续定位\n"
            "MAP_PCD=/opt/data/.robot/map/map.pcd\n"
            "MAP_OK=1\n"
            "LOAD_MAP_SERVICE=1\n"
            "LOCALIZATION_READY=0\n"
            "NAV_PROCESS=1\n"
            "START_NAV_SUBSCRIBERS=1\n"
        )
    )

    assert NavigationPage.status_finished(page, page.status_slot.process, 0, 26) is True

    assert page.pending_navigation_action == "goal"
    assert page.runs == []
    assert page.last_status_state == "blocked"
    assert page.last_status_values["TEXT"] == "等待连续定位"
    assert page.card_values[-1][0]["LOCALIZATION_READY"] == "0"
    assert page.nav_status_note.text == "导航任务已排队：等待连续定位正常"
    assert page.navigation_log_lines == []


def test_navigation_status_ready_marks_failed_map_preparation_as_ready_without_retrying():
    page = _FakeNavigationRefreshPage()
    page.map_pcd_path.setText("/opt/data/.robot/map/map.pcd")
    page.prepared_map_pcd_path = ""
    page.map_prepare_error = "[ERROR] alg定位等待连续定位超时"
    page.status_slot = _FakeSlot(
        output=(
            "STATUS=ready\n"
            "TEXT=导航待命\n"
            "MAP_PCD=/opt/data/.robot/map/map.pcd\n"
            "MAP_OK=1\n"
            "LOAD_MAP_SERVICE=1\n"
            "LOCALIZATION_READY=1\n"
            "NAV_PROCESS=1\n"
            "START_NAV_SUBSCRIBERS=1\n"
        )
    )

    assert NavigationPage.status_finished(page, page.status_slot.process, 0, 28) is True

    assert page.prepared_map_pcd_path == "/opt/data/.robot/map/map.pcd"
    assert page.map_prepare_error == ""
    assert page.map_prepare_auto_retry_pcd == ""
    assert page.map_prepare_slot.start_calls == []
    assert page.nav_status_note.text == "远端已确认当前地图和定位就绪，可发送导航任务"
    assert page.navigation_log_lines == []

    page.map_prepare_slot.running = False
    page.map_prepare_error = "[ERROR] alg定位等待连续定位超时"

    assert NavigationPage.status_finished(page, page.status_slot.process, 0, 29) is True

    assert page.map_prepare_slot.start_calls == []


def test_navigation_status_ready_stops_current_map_preparation_and_marks_ready():
    page = _FakeNavigationRefreshPage()
    page.map_pcd_path.setText("/opt/data/.robot/map/map.pcd")
    page.prepared_map_pcd_path = ""
    page.preparing_map_pcd_path = "/opt/data/.robot/map/map.pcd"
    page.map_prepare_slot.running = True
    page.map_prepare_error = "[ERROR] alg定位等待连续定位超时"
    page.status_slot = _FakeSlot(
        output=(
            "STATUS=ready\n"
            "TEXT=导航待命\n"
            "MAP_PCD=/opt/data/.robot/map/map.pcd\n"
            "MAP_OK=1\n"
            "LOCALIZATION_READY=1\n"
            "NAV_PROCESS=1\n"
            "START_NAV_SUBSCRIBERS=1\n"
        )
    )

    assert NavigationPage.status_finished(page, page.status_slot.process, 0, 30) is True

    assert page.map_prepare_slot.stop_calls == 1
    assert page.preparing_map_pcd_path == ""
    assert page.prepared_map_pcd_path == "/opt/data/.robot/map/map.pcd"
    assert page.map_prepare_error == ""
    assert page.task_state.text == "任务\n导航就绪"


def test_navigation_status_finished_ignores_stale_map_status(monkeypatch):
    scheduled = []
    monkeypatch.setattr(
        "dog_remote_tool.ui.pages.navigation.page.QTimer.singleShot",
        lambda delay, callback: scheduled.append((delay, getattr(callback, "__name__", ""))),
    )
    page = _FakeNavigationRefreshPage(selected_map="/opt/data/.robot/map/history_map/current/map.pgm")
    page.map_pcd_path.setText("/opt/data/.robot/map/history_map/current/map.pcd")
    page.prepared_map_pcd_path = "/opt/data/.robot/map/history_map/current/map.pcd"
    page.last_status_values = {
        "STATUS": "ready",
        "TEXT": "导航就绪",
        "MAP_PCD": "/opt/data/.robot/map/history_map/current/map.pcd",
    }
    page.last_status_state = "ready"
    page.status_slot = _FakeSlot(
        output=(
            "STATUS=ready\n"
            "TEXT=导航待命\n"
            "MAP_PCD=/opt/data/.robot/map/history_map/old/map.pcd\n"
            "MAP_OK=1\n"
            "LOCALIZATION_READY=1\n"
            "NAV_PROCESS=1\n"
            "START_NAV_SUBSCRIBERS=1\n"
        )
    )

    assert NavigationPage.status_finished(page, page.status_slot.process, 0, 31) is True

    assert page.last_status_values["MAP_PCD"] == "/opt/data/.robot/map/history_map/current/map.pcd"
    assert page.last_status_state == "ready"
    assert page.card_values == []
    assert (0, "refresh_navigation_status") in scheduled
    assert page.navigation_log_lines == []


def test_navigation_pending_multi_and_route_wait_for_status_ready(monkeypatch):
    monkeypatch.setattr(
        "dog_remote_tool.ui.pages.navigation.page.QTimer.singleShot",
        lambda delay, callback: callback() if delay == 0 else None,
    )
    cases = [
        ("multipoint", "多点导航中", "开始多点导航"),
        ("route", "路网导航中", "发送路网导航目标"),
    ]
    for action, operation, title in cases:
        page = _FakeNavigationRefreshPage(selected_map="/opt/data/.robot/map/map.pgm")
        page.pending_navigation_action = action
        page.map_pcd_path.setText("/opt/data/.robot/map/map.pcd")
        page.prepared_map_pcd_path = "/opt/data/.robot/map/map.pcd"
        if action == "route":
            page.route_file_states["/opt/data/.robot/map/map.pgm"] = True
            page.route_graph = route_network.RouteGraph(
                nodes={
                    1: route_network.RouteNode(1, 1.0, 2.0),
                    2: route_network.RouteNode(2, 2.0, 3.0),
                },
                edges={1: route_network.RouteEdge(1, 1, 2, [(1.0, 2.0), (2.0, 3.0)])},
            )
            page.route_graph_remote_pgm = "/opt/data/.robot/map/map.pgm"
            page.route_graph_local_path = "/opt/data/.robot/map/map.geojson"
            page.route_target_mode = True
            page.route_target_node_ids = [1, 2]
        page.runs = []
        page.waypoints_text = _FakeWaypointText("1.000,2.000,0.000\n2.000,3.000,0.200")
        page.goal_point_selected = True
        page.navigation_points = lambda: [(1.0, 2.0, 0.0), (2.0, 3.0, 0.2)]
        page.run_navigation_spec = lambda spec, op: page.runs.append((spec, op)) or True
        page.status_slot = _FakeSlot(
            output=(
                "STATUS=ready\n"
                "TEXT=可发送目标\n"
                "MAP_PCD=/opt/data/.robot/map/map.pcd\n"
                "MAP_OK=1\n"
                "LOAD_MAP_SERVICE=1\n"
                "LOCALIZATION_READY=1\n"
                "NAV_PROCESS=1\n"
                "START_NAV_SUBSCRIBERS=1\n"
            )
        )

        assert NavigationPage.status_finished(page, page.status_slot.process, 0, 27) is True

        assert page.pending_navigation_action == ""
        assert page.runs
        spec, actual_operation = page.runs[-1]
        assert actual_operation == operation
        assert spec.title == title


def test_navigation_pending_multipoint_uses_loop_mode_after_status_ready(monkeypatch):
    monkeypatch.setattr(
        "dog_remote_tool.ui.pages.navigation.page.QTimer.singleShot",
        lambda delay, callback: callback() if delay == 0 else None,
    )
    page = _FakeNavigationRefreshPage(selected_map="/opt/data/.robot/map/map.pgm")
    page.pending_navigation_action = "multipoint"
    page.navigation_loop_enabled = True
    page.map_pcd_path.setText("/opt/data/.robot/map/map.pcd")
    page.prepared_map_pcd_path = "/opt/data/.robot/map/map.pcd"
    page.runs = []
    page.waypoints_text = _FakeWaypointText("1.000,2.000,0.000\n2.000,3.000,0.200")
    page.goal_point_selected = True
    page.navigation_points = lambda: [(1.0, 2.0, 0.0), (2.0, 3.0, 0.2)]
    page.run_navigation_spec = lambda spec, op: page.runs.append((spec, op)) or True
    page.status_slot = _FakeSlot(
        output=(
            "STATUS=ready\n"
            "TEXT=可发送目标\n"
            "MAP_PCD=/opt/data/.robot/map/map.pcd\n"
            "MAP_OK=1\n"
            "LOAD_MAP_SERVICE=1\n"
            "LOCALIZATION_READY=1\n"
            "NAV_PROCESS=1\n"
            "START_NAV_SUBSCRIBERS=1\n"
        )
    )

    assert NavigationPage.status_finished(page, page.status_slot.process, 0, 2701) is True

    assert page.pending_navigation_action == ""
    assert page.navigation_loop_enabled is True
    spec, actual_operation = page.runs[-1]
    assert actual_operation == "多点循环中"
    assert spec.title == "开始多点循环"


def test_navigation_plan_stream_updates_global_route_and_ignores_local_plan(monkeypatch):
    monkeypatch.setattr("dog_remote_tool.ui.pages.navigation.streams.localization.navigation_plan_stream_command", lambda profile: "plan-stream")
    page = _FakeNavigationRefreshPage()
    page.workspace_dialog = _FakeWorkspaceDialog()
    page.map_pcd_path.setText("/opt/data/.robot/map/map.pcd")
    page.prepared_map_pcd_path = "/opt/data/.robot/map/map.pcd"
    page.navigation_tracking_enabled = True

    assert NavigationPage.start_plan_stream(page) is True
    assert page.plan_stream_buffer == ""
    assert page.plan_stream_slot.start_calls == ["plan-stream"]
    assert page.plan_stream_slot.process.started is True

    page.plan_stream_slot.finish_output = (
        "PLAN=GLOBAL TOPIC=/navigo/bn/cmn/vis/global_path COUNT=2 POINTS=1.000,2.000,0.100;2.000,3.000,0.200\n"
        "PLAN=LOCAL TOPIC=/navigo/cs/lpc/vis/best_local_plan COUNT=2 POINTS=1.100,2.100,0.100;1.400,2.500,0.160\n"
    )
    NavigationPage.read_plan_stream_output(page, page.plan_stream_slot.process, 15)

    assert page.navigation_global_route == [(1.0, 2.0, 0.1), (2.0, 3.0, 0.2)]
    assert page.navigation_realtime_plan == []
    assert page.navigation_global_plan_topic == "/navigo/bn/cmn/vis/global_path"
    assert page.navigation_realtime_plan_topic == ""


def test_navigation_plan_stream_waits_for_active_navigation_tracking(monkeypatch):
    monkeypatch.setattr("dog_remote_tool.ui.pages.navigation.streams.localization.navigation_plan_stream_command", lambda profile: "plan-stream")
    page = _FakeNavigationRefreshPage()
    page.map_pcd_path.setText("/opt/data/.robot/map/map.pcd")
    page.prepared_map_pcd_path = "/opt/data/.robot/map/map.pcd"

    assert NavigationPage.start_plan_stream(page) is False
    assert page.plan_stream_slot.start_calls == []

    page.workspace_dialog = _FakeWorkspaceDialog()
    assert NavigationPage.start_plan_stream(page) is False
    assert page.plan_stream_slot.start_calls == []

    page.navigation_tracking_enabled = True
    assert NavigationPage.start_plan_stream(page) is True
    assert page.plan_stream_slot.start_calls == ["plan-stream"]


def test_navigation_single_goal_requires_selected_target(monkeypatch):
    page = _FakeNavigationActionPage()
    page.goal_point_selected = False
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda _parent, title, text: messages.append((title, text)))

    assert NavigationPage.make_start_goal(page) is False

    assert page.runs == []
    assert page.nav_status_note.text == "单点导航未下发：请先选择目标点"
    assert page.workspace_refreshes == 1
    assert messages == [("目标点未选择", "请先在地图上点击一个目标点，或手动输入目标坐标后再开始单点导航。")]


def test_navigation_start_buttons_use_loop_commands_when_loop_mode_enabled():
    page = _FakeNavigationActionPage()
    page.navigation_loop_enabled = True
    page.route_target_mode = False

    assert NavigationPage.make_start_multipoint(page) is True
    spec, operation = page.runs[-1]
    assert operation == "多点循环中"
    assert spec.title == "开始多点循环"

    page.route_target_mode = True
    assert NavigationPage.make_start_route_goal(page) is True
    spec, operation = page.runs[-1]
    assert operation == "路网循环中"
    assert spec.title == "开始路网循环"


def test_navigation_route_loop_rejects_unclosed_one_way_route(monkeypatch):
    page = _FakeNavigationActionPage()
    page.navigation_loop_enabled = True
    page.route_graph = route_network.RouteGraph(
        nodes={
            1: route_network.RouteNode(1, 1.0, 2.0),
            2: route_network.RouteNode(2, 3.0, 4.0),
        },
        edges={
            1: route_network.RouteEdge(1, 1, 2, [(1.0, 2.0), (3.0, 4.0)], "forward"),
        },
    )
    page.route_target_node_ids = [1, 2]
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda _parent, title, text: messages.append((title, text)))

    assert NavigationPage.make_start_route_goal(page) is False

    assert page.runs == []
    assert page.nav_status_note.text == "循环不可闭合：最后目标节点 2 无法沿路网回到第一个目标节点 1。"
    assert messages == [
        (
            "循环不可闭合",
            "循环不可闭合：最后目标节点 2 无法沿路网回到第一个目标节点 1。请补充闭合边、调整边方向，或把最后一个目标点改到可回到起点的位置。",
        )
    ]

    page.navigation_loop_enabled = False

    assert NavigationPage.make_start_route_goal(page) is True

    spec, operation = page.runs[-1]
    assert operation == "路网导航中"
    assert spec.title == "发送路网导航目标"


def test_navigation_route_goal_uses_selected_history_map_geojson():
    page = _FakeNavigationActionPage()
    page.route_geojson_path.setText(route_network.DEFAULT_REMOTE_ROUTE_FILE)

    assert NavigationPage.make_start_route_goal(page) is True

    spec, operation = page.runs[-1]
    assert operation == "路网导航中"
    assert spec.title == "发送路网导航目标"
    assert page.route_geojson_path.text() == "/opt/data/.robot/map/history_map/2026_06_02/map.geojson"
    route_script = _route_stdin_script_text(spec.command)
    assert "/opt/data/.robot/map/history_map/2026_06_02/map.geojson" in route_script
    assert route_network.DEFAULT_REMOTE_ROUTE_FILE not in spec.command


def test_navigation_route_goal_first_loads_route_overlay_without_starting(tmp_path):
    page = _FakeNavigationActionPage()
    page.runs = []
    page.route_target_mode = False
    page.route_graph = None
    page.route_graph_remote_pgm = ""
    page.route_graph_local_path = ""
    page.route_target_node_ids = []
    page.waypoints_text = _FakeWaypointText("")
    page.goal_point_selected = False
    graph = route_network.RouteGraph(
        nodes={1: route_network.RouteNode(1, 1.0, 2.0), 2: route_network.RouteNode(2, 3.0, 4.0)},
        edges={1: route_network.RouteEdge(1, 1, 2, [(1.0, 2.0), (3.0, 4.0)])},
    )
    (tmp_path / "map.geojson").write_text(json.dumps(route_network.graph_to_geojson(graph)), encoding="utf-8")
    page.local_preview_dir = lambda _remote: tmp_path
    page.route_file_states[page.selected_map_pgm()] = False

    assert NavigationPage.make_start_route_goal(page) is False

    assert page.runs == []
    assert page.route_target_mode is True
    assert page.route_graph is not None
    assert "请先在路网节点附近选择目标" in page.nav_status_note.text


def test_navigation_enter_route_mode_clears_existing_point_targets(tmp_path):
    page = _FakeNavigationActionPage()
    page.workspace_dialog = _FakeWorkspaceDialog()
    page.route_target_mode = False
    page.route_graph = None
    page.route_graph_remote_pgm = ""
    page.route_graph_local_path = ""
    page.route_target_node_ids = []
    page.waypoints_text = _FakeWaypointText("1.000,2.000,0.000\n3.000,4.000,0.000")
    page.goal_point_selected = True
    page.nav_map.set_points([(1.0, 2.0, 0.0), (3.0, 4.0, 0.0)])
    page.workspace_dialog.canvas.set_points([(1.0, 2.0, 0.0), (3.0, 4.0, 0.0)])
    graph = route_network.RouteGraph(
        nodes={1: route_network.RouteNode(1, 1.0, 2.0), 2: route_network.RouteNode(2, 3.0, 4.0)},
        edges={1: route_network.RouteEdge(1, 1, 2, [(1.0, 2.0), (3.0, 4.0)])},
    )
    (tmp_path / "map.geojson").write_text(json.dumps(route_network.graph_to_geojson(graph)), encoding="utf-8")
    page.local_preview_dir = lambda _remote: tmp_path
    page.route_file_states[page.selected_map_pgm()] = False

    assert NavigationPage.ensure_route_target_mode(page) is True

    assert page.route_target_mode is True
    assert page.route_graph is not None
    assert page.route_target_node_ids == []
    assert page.waypoints_text.toPlainText() == ""
    assert page.goal_point_selected is False
    assert page.nav_map.points[-1] == []
    assert page.workspace_dialog.canvas.points[-1] == []
    assert "路网已加载" in page.nav_status_note.text


def test_navigation_enter_route_mode_pulls_remote_when_remote_route_exists(tmp_path):
    page = _FakeNavigationActionPage()
    page.route_target_mode = False
    page.route_graph = None
    page.route_graph_remote_pgm = ""
    page.route_graph_local_path = ""
    page.route_target_node_ids = []
    graph = route_network.RouteGraph(
        nodes={1: route_network.RouteNode(1, 1.0, 2.0), 2: route_network.RouteNode(2, 3.0, 4.0)},
        edges={1: route_network.RouteEdge(1, 1, 2, [(1.0, 2.0), (3.0, 4.0)])},
    )
    (tmp_path / "map.geojson").write_text(json.dumps(route_network.graph_to_geojson(graph)), encoding="utf-8")
    page.local_preview_dir = lambda _remote: tmp_path
    page.route_file_states[page.selected_map_pgm()] = True

    assert NavigationPage.ensure_route_target_mode(page) is True

    assert page.route_pull_slot.start_calls
    command = page.route_pull_slot.start_calls[-1]
    assert "/opt/data/.robot/map/history_map/2026_06_02/map.geojson" in command
    assert str(tmp_path / "map.geojson") in command
    assert page.route_target_mode is False
    assert page.nav_status_note.text == "正在拉取远端路网并加载到地图"


def test_navigation_toggle_route_mode_exits_and_clears_route_targets():
    page = _FakeNavigationActionPage()
    page.workspace_dialog = _FakeWorkspaceDialog()
    page.nav_map.set_route_graph(page.route_graph)
    page.nav_map.set_route_target_node_ids(page.route_target_node_ids)
    page.nav_map.set_points([(1.0, 2.0, 0.0)])

    assert NavigationPage.toggle_route_target_mode(page) is True

    assert page.route_target_mode is False
    assert page.route_graph is None
    assert page.route_graph_remote_pgm == ""
    assert page.route_target_node_ids == []
    assert page.waypoints_text.toPlainText() == ""
    assert page.goal_point_selected is False
    assert page.nav_map.route_graphs[-1] is None
    assert page.nav_map.route_target_node_ids[-1] == []
    assert page.nav_map.points[-1] == []
    assert page.workspace_dialog.canvas.route_graphs[-1] is None
    assert page.workspace_dialog.canvas.route_target_node_ids[-1] == []
    assert page.workspace_dialog.canvas.points[-1] == []
    assert "已退出路网导航模式" in page.nav_status_note.text


def test_navigation_route_mode_click_accepts_route_node_and_starts_goal(tmp_path):
    page = _FakeNavigationActionPage()
    page.profile = lambda: get_product("xg1_nx")
    page.runs = []
    page.waypoints_text = _FakeWaypointText("")
    page.goal_point_selected = False
    page.route_target_node_ids = []
    page.local_preview_dir = lambda _remote: tmp_path

    assert NavigationPage.on_map_point_clicked(page, 2.0, 3.0) is False
    assert "未命中路网节点" in page.nav_status_note.text

    assert NavigationPage.on_map_point_clicked(page, 1.2, 2.2) is True
    assert page.route_target_node_ids == [1]
    assert page.waypoints_text.toPlainText() == "1.000000000,2.000000000,0.785398163"
    assert math.isclose(page.goal_yaw.value(), math.pi / 4.0, abs_tol=1e-3)
    assert math.isclose(page.direction_degrees.value(), 45.0, abs_tol=1e-3)
    assert "已添加路网目标节点 1" in page.nav_status_note.text
    assert "方向=45°" in page.nav_status_note.text
    assert NavigationPage.navigation_point_rows(page) == ["1. 路网目标节点  x=1.000, y=2.000, 方向=45°"]
    assert "方向=45°" in NavigationPage.target_summary_text(page)

    assert NavigationPage.on_map_point_clicked(page, 1.1, 2.1) is False
    assert page.route_target_node_ids == [1]
    assert "不能连续重复添加" in page.nav_status_note.text

    assert NavigationPage.on_map_point_clicked(page, 3.0, 4.0) is True
    assert page.waypoints_text.toPlainText().splitlines()[-1] == "3.000000000,4.000000000,0.785398163"
    assert NavigationPage.on_map_point_clicked(page, 1.0, 2.0) is True
    assert page.route_target_node_ids == [1, 2, 1]
    assert page.waypoints_text.toPlainText().splitlines()[-1] == "1.000000000,2.000000000,-2.356194490"
    assert NavigationPage.navigation_point_rows(page)[-1] == "3. 路网目标节点  x=1.000, y=2.000, 方向=-135°"

    assert NavigationPage.make_start_route_goal(page) is True

    spec, operation = page.runs[-1]
    assert operation == "路网导航中"
    assert spec.title == "发送路网导航目标"
    route_script = _route_stdin_script_text(spec.command)
    assert '"map_type":"route"' in route_script
    assert '"goal_task_type":"route"' in route_script
    assert '"position":{"x":1.0,"y":2.0,"z":0.0}' in route_script


def test_navigation_route_mode_click_preserves_precise_route_node_coordinates(tmp_path):
    page = _FakeNavigationActionPage()
    page.profile = lambda: get_product("xg1_nx")
    page.runs = []
    page.waypoints_text = _FakeWaypointText("")
    page.goal_point_selected = False
    page.route_target_node_ids = []
    page.local_preview_dir = lambda _remote: tmp_path
    page.route_graph = route_network.RouteGraph(
        nodes={
            1: route_network.RouteNode(1, 0.0, 0.0),
            2: route_network.RouteNode(2, 2.806028840, -7.476321017),
        },
        edges={
            1: route_network.RouteEdge(
                1,
                1,
                2,
                [(0.0, 0.0), (2.806028840, -7.476321017)],
            )
        },
    )

    assert NavigationPage.on_map_point_clicked(page, 2.806028840, -7.476321017) is True

    assert page.route_target_node_ids == [2]
    assert page.waypoints_text.toPlainText().startswith("2.806028840,-7.476321017,")

    assert NavigationPage.make_start_route_goal(page) is True

    route_script = _route_stdin_script_text(page.runs[-1][0].command)
    assert '"position":{"x":2.80602884,"y":-7.476321017,"z":0.0}' in route_script


def test_navigation_route_goal_can_start_when_route_file_cache_is_stale():
    page = _FakeNavigationActionPage()
    page.route_file_states[page.selected_map_pgm()] = False

    assert NavigationPage.make_start_route_goal(page) is True

    spec, operation = page.runs[-1]
    assert operation == "路网导航中"
    assert spec.title == "发送路网导航目标"
    assert any("路网状态未确认" in line for line in page.navigation_log_lines)
    assert "_update_graph_inner" not in spec.command
    assert "/RouteGraphPlanner/update_graph" not in spec.command
    assert "bash -s < /tmp/dog_remote_nav_scripts/route_nav_" in spec.command


def test_navigation_route_history_saves_and_lists_by_selected_map(tmp_path):
    remote = "/opt/data/.robot/map/history_map/2026_06_02/map.pgm"
    other_remote = "/opt/data/.robot/map/history_map/other/map.pgm"

    saved = navigation_route_history.save_route_history(
        name="巡检路线",
        remote_pgm=remote,
        route_geojson_path="/opt/data/.robot/map/history_map/2026_06_02/map.geojson",
        node_ids=[1, 2, 3],
        waypoints_text="1.000,2.000,0.000",
        base_dir=tmp_path,
    )
    navigation_route_history.save_route_history(
        name="其他地图路线",
        remote_pgm=other_remote,
        route_geojson_path="/opt/data/.robot/map/history_map/other/map.geojson",
        node_ids=[9],
        waypoints_text="9.000,9.000,0.000",
        base_dir=tmp_path,
    )

    data = navigation_route_history.read_route_history(saved)
    entries = navigation_route_history.list_route_histories(remote, base_dir=tmp_path)

    assert data["name"] == "巡检路线"
    assert data["node_ids"] == [1, 2, 3]
    assert len(entries) == 1
    assert entries[0].name == "巡检路线"
    assert entries[0].point_count == 3


def test_navigation_route_history_labels_are_compact(tmp_path):
    remote = "/opt/data/.robot/map/history_map/2026_06_02/map.pgm"
    saved = navigation_route_history.save_route_history(
        name="路线 2026-06-13 15:53:27",
        remote_pgm=remote,
        route_geojson_path="/opt/data/.robot/map/history_map/2026_06_02/map.geojson",
        node_ids=[1],
        waypoints_text="1.000,2.000,0.000",
        base_dir=tmp_path,
        now=datetime(2026, 6, 13, 15, 53, 27),
    )

    entry = navigation_route_history.list_route_histories(remote, base_dir=tmp_path)[0]

    assert navigation_route_history.default_route_history_name(datetime(2026, 6, 13, 15, 53, 27)) == "路线 15:53"
    assert entry.title_label() == "路线"
    assert entry.meta_label() == "1点 · 15:53"
    assert entry.label() == "路线 · 1点 · 15:53"
    assert entry.detail_label() == "路线 · 1点 · 15:53"


def test_navigation_load_route_history_restores_route_targets(tmp_path):
    page = _FakeNavigationActionPage()
    page.route_target_mode = True
    page.route_target_node_ids = []
    page.waypoints_text = _FakeWaypointText("")
    page.goal_point_selected = False
    path = navigation_route_history.save_route_history(
        name="本地巡检",
        remote_pgm=page.selected_map_pgm(),
        route_geojson_path=page.route_graph_local_path,
        node_ids=[1, 2],
        waypoints_text="",
        base_dir=tmp_path,
    )

    assert NavigationPage.load_route_history(page, path) is True

    assert page.route_target_node_ids == [1, 2]
    assert page.waypoints_text.toPlainText().splitlines() == [
        "1.000000000,2.000000000,0.785398163",
        "3.000000000,4.000000000,0.785398163",
    ]
    assert page.goal_point_selected is True
    assert page.nav_map.route_target_node_ids[-1] == [1, 2]
    assert page.nav_map.points[-1] == [(1.0, 2.0, 0.785398163), (3.0, 4.0, 0.785398163)]
    assert "已加载路网路线：本地巡检" in page.nav_status_note.text


def test_navigation_route_target_yaw_uses_shortest_route_final_segment():
    page = _FakeNavigationActionPage()
    graph = route_network.RouteGraph(
        nodes={
            1: route_network.RouteNode(1, 0.0, 0.0),
            2: route_network.RouteNode(2, 2.0, 0.0),
            3: route_network.RouteNode(3, 2.0, 2.0),
            4: route_network.RouteNode(4, 0.0, 2.0),
        },
        edges={
            1: route_network.RouteEdge(1, 1, 2, [(0.0, 0.0), (2.0, 0.0)], "both"),
            2: route_network.RouteEdge(2, 2, 3, [(2.0, 0.0), (2.0, 2.0)], "both"),
            3: route_network.RouteEdge(3, 1, 4, [(0.0, 0.0), (0.0, 2.0)], "both", cost=10.0),
            4: route_network.RouteEdge(4, 4, 3, [(0.0, 2.0), (2.0, 2.0)], "both", cost=10.0),
        },
    )
    page.route_target_node_ids = [1]

    yaw = NavigationPage.route_target_yaw(page, graph, 3)

    assert math.isclose(yaw, math.pi / 2.0, abs_tol=1e-6)


def test_navigation_route_target_updates_previous_point_yaw_toward_next_node():
    page = _FakeNavigationActionPage()
    page.robot_pose = None
    page.waypoints_text = _FakeWaypointText("")
    page.goal_point_selected = False
    page.route_target_node_ids = []
    page.route_graph = route_network.RouteGraph(
        nodes={
            1: route_network.RouteNode(1, 0.0, 0.0),
            2: route_network.RouteNode(2, 0.0, 2.0),
            3: route_network.RouteNode(3, 0.5, 0.0),
        },
        edges={
            1: route_network.RouteEdge(1, 1, 3, [(0.0, 0.0), (0.5, 0.0)], "both"),
            2: route_network.RouteEdge(2, 1, 2, [(0.0, 0.0), (0.0, 2.0)], "both"),
        },
    )

    assert NavigationPage.on_map_point_clicked(page, 0.0, 0.0) is True
    assert page.waypoints_text.toPlainText() == "0.000000000,0.000000000,0.000000000"

    assert NavigationPage.on_map_point_clicked(page, 0.0, 2.0) is True

    lines = page.waypoints_text.toPlainText().splitlines()
    assert lines[0] == "0.000000000,0.000000000,1.570796327"
    assert lines[1] == "0.000000000,2.000000000,1.570796327"
    rows = NavigationPage.navigation_point_rows(page)
    assert rows[0] == "1. 路网目标节点  x=0.000, y=0.000, 方向=90°"
    assert "上一目标方向已更新为 90°" in page.nav_status_note.text

    assert NavigationPage.undo_last_added_navigation_point(page) is True
    assert page.route_target_node_ids == [1]
    assert page.waypoints_text.toPlainText() == "0.000000000,0.000000000,0.000000000"


def test_navigation_workspace_route_target_cells_show_direction():
    source = inspect.getsource(NavigationWorkspaceDialog.refresh_point_list)

    assert 'f"路网节点 ({x:.1f},{y:.1f}) {math.degrees(yaw):.0f}°"' in source


def test_navigation_route_overlay_reloads_when_local_geojson_changes(tmp_path):
    remote = "/opt/data/.robot/map/history_map/2026_06_02/map.pgm"
    local_route = tmp_path / "map.geojson"
    old_graph = route_network.RouteGraph(
        nodes={1: route_network.RouteNode(1, 1.0, 2.0)},
        edges={},
    )
    new_graph = route_network.RouteGraph(
        nodes={9: route_network.RouteNode(9, 9.0, 8.0)},
        edges={},
    )
    route_network.save_geojson(old_graph, local_route)

    page = _FakeNavigationRefreshPage(selected_map=remote)
    page.local_preview_dir = lambda _remote: tmp_path
    page.nav_map = _FakeWorkspaceCanvas()
    page.update_target_hint = lambda: None
    page.waypoints_text = _FakeWaypointText("")
    page.goal_x = _FakeSpin(0.0)
    page.goal_y = _FakeSpin(0.0)
    page.goal_yaw = _FakeSpin(0.0)
    page.last_status_values = {"STATUS": "ready", "TEXT": "导航就绪"}

    assert NavigationPage.load_local_route_overlay(page, remote) is True
    assert set(page.route_graph.nodes) == {1}

    page.route_target_node_ids = [1]
    page.waypoints_text.setPlainText("1.000,2.000,0.000")
    page.goal_point_selected = True
    route_network.save_geojson(new_graph, local_route)

    assert NavigationPage.handle_local_route_geojson_updated(page, remote, local_route) is True
    assert set(page.route_graph.nodes) == {9}
    assert page.route_target_node_ids == []
    assert page.waypoints_text.toPlainText() == ""
    assert page.goal_point_selected is False
    assert page.nav_map.points[-1] == []
    assert set(page.nav_map.route_graphs[-1].nodes) == {9}
    assert "原有路网目标点已清空" in page.nav_status_note.text


def test_navigation_refresh_status_returns_start_result():
    inactive = _FakeNavigationRefreshPage(active=False)

    assert NavigationPage.refresh_navigation_status(inactive) is False
    assert inactive.status_slot.start_calls == []

    unsupported = _FakeNavigationRefreshPage(supported=False)

    assert NavigationPage.refresh_navigation_status(unsupported) is False
    assert unsupported.last_status_values == {}
    assert unsupported.last_status_state == "blocked"
    assert unsupported.card_values == [({"STATUS": "blocked", "TEXT": "当前设备不支持导航"}, "")]

    busy = _FakeNavigationRefreshPage(status_running=True)

    assert NavigationPage.refresh_navigation_status(busy) is False
    assert busy.status_slot.start_calls == []

    page = _FakeNavigationRefreshPage()

    assert NavigationPage.refresh_navigation_status(page) is True
    assert page.status_slot.process.started is True
    assert len(page.status_slot.start_calls) == 1
    assert "/opt/data/.robot/map/map.pcd" in page.status_slot.start_calls[0]
    assert "DOG_REMOTE_SKIP_ARC_APP_STATUS=1" in page.status_slot.start_calls[0]
    assert "NAVIGATION_CMD_TOPIC_INFO=$(timeout 2s ros2 topic info /navigation_cmd --no-daemon" not in page.status_slot.start_calls[0]


def test_navigation_read_callbacks_return_slot_result():
    page = _FakeNavigationRefreshPage()
    page.status_slot = _FakeSlot(read_result=True)
    page.map_list_slot = _FakeSlot(read_result=False)
    page.map_preview_slot = _FakeSlot(read_result=True)
    page.mode_switch_helper_slot = _FakeSlot(read_result=True)

    assert NavigationPage.read_status_output(page, page.status_slot.process, request_id=21) is True
    assert page.status_slot.read_calls == [(page.status_slot.process, 21)]

    assert NavigationPage.read_map_list_output(page, page.map_list_slot.process, request_id=22) is False
    assert page.map_list_slot.read_calls == [(page.map_list_slot.process, 22)]

    assert NavigationPage.read_map_preview_output(page, page.map_preview_slot.process, request_id=23) is True
    assert page.map_preview_slot.read_calls == [(page.map_preview_slot.process, 23)]

    assert NavigationPage.read_navigation_helpers_output(page, page.mode_switch_helper_slot.process, request_id=24) is True
    assert page.mode_switch_helper_slot.read_calls == [(page.mode_switch_helper_slot.process, 24)]


def test_navigation_ensure_navigation_helpers_starts_when_page_active():
    inactive = _FakeNavigationRefreshPage(active=False)
    unsupported = _FakeNavigationRefreshPage(supported=False)
    busy = _FakeNavigationRefreshPage()
    busy.mode_switch_helper_slot = _FakeSlot(running=True)

    assert NavigationPage.ensure_navigation_helpers(inactive) is False
    assert inactive.mode_switch_helper_slot.start_calls == []
    assert NavigationPage.ensure_navigation_helpers(unsupported) is False
    assert unsupported.mode_switch_helper_slot.start_calls == []
    assert NavigationPage.ensure_navigation_helpers(busy) is False
    assert busy.mode_switch_helper_slot.start_calls == []

    page = _FakeNavigationRefreshPage()

    assert NavigationPage.ensure_navigation_helpers(page) is True
    assert page.mode_switch_helper_slot.process.started is True
    assert len(page.mode_switch_helper_slot.start_calls) == 1
    assert "dog_remote_nav_mode_switch_helper.py" not in page.mode_switch_helper_slot.start_calls[0]
    assert "dog_remote_start_navigation_helper.py" in page.mode_switch_helper_slot.start_calls[0]


def test_navigation_helpers_finished_reports_helper_error():
    stale = _FakeNavigationRefreshPage()
    stale.mode_switch_helper_slot = _FakeSlot(output=None)

    assert NavigationPage.navigation_helpers_finished(stale, stale.mode_switch_helper_slot.process, 0, 31) is False

    page = _FakeNavigationRefreshPage()
    page.nav_status_note = _FakeLabel()
    page.workspace_refreshes = 0
    page.refresh_workspace_from_page = lambda: setattr(page, "workspace_refreshes", page.workspace_refreshes + 1)

    assert NavigationPage.navigation_helpers_finished(page, page.mode_switch_helper_slot.process, 1, 32) is True
    assert page.nav_status_note.text == "导航通道准备失败，请检查远端导航服务"
    assert page.workspace_refreshes == 1


def test_navigation_pose_stream_starts_and_updates_robot_pose(monkeypatch):
    monkeypatch.setattr("dog_remote_tool.ui.pages.navigation.streams.localization.pose_stream_command", lambda profile: "pose-stream")
    page = _FakeNavigationRefreshPage()
    page.workspace_dialog = _FakeWorkspaceDialog()
    page.map_pcd_path.setText("/opt/data/.robot/map/history_map/a/map.pcd")
    page.prepared_map_pcd_path = "/opt/data/.robot/map/history_map/a/map.pcd"

    assert NavigationPage.start_pose_stream(page) is True
    assert page.pose_stream_buffer == ""
    assert page.pose_stream_slot.start_calls == ["pose-stream"]
    assert page.pose_stream_slot.process.started is True

    page.pose_stream_slot.finish_output = "POSE=ok X=1.250000000 Y=-2.500000000 YAW=0.750000000\n"
    NavigationPage.read_pose_stream_output(page, page.pose_stream_slot.process, 15)

    assert page.robot_pose == (1.25, -2.5, 0.75)
    assert page.robot_pose_updates[-1] == (1.25, -2.5, 0.75)
    assert page.navigation_realtime_plan == []


def test_navigation_pose_stream_waits_until_selected_map_prepared():
    page = _FakeNavigationRefreshPage()
    page.map_pcd_path.setText("/opt/data/.robot/map/history_map/a/map.pcd")
    page.prepared_map_pcd_path = ""

    NavigationPage.handle_robot_pose_update(page, (1.25, -2.5, 0.75))

    assert page.robot_pose is None
    assert page.robot_pose_updates == []

    page.prepared_map_pcd_path = "/opt/data/.robot/map/history_map/a/map.pcd"

    NavigationPage.handle_robot_pose_update(page, (1.25, -2.5, 0.75))

    assert page.robot_pose == (1.25, -2.5, 0.75)
    assert page.robot_pose_updates[-1] == (1.25, -2.5, 0.75)


def test_navigation_pose_stream_accepts_status_confirmed_selected_map(monkeypatch):
    monkeypatch.setattr("dog_remote_tool.ui.pages.navigation.streams.localization.pose_stream_command", lambda profile: "pose-stream")
    page = _FakeNavigationRefreshPage()
    page.map_pcd_path.setText("/opt/data/.robot/map/history_map/a/map.pcd")
    page.prepared_map_pcd_path = ""
    page.last_status_values = {
        "MAP_PCD": "/opt/data/.robot/map/history_map/a/map.pcd",
        "MAP_OK": "1",
        "LOCALIZATION_READY": "1",
    }

    assert NavigationPage.start_pose_stream(page) is True

    NavigationPage.handle_robot_pose_update(page, (1.25, -2.5, 0.75))

    assert page.pose_stream_slot.start_calls == ["pose-stream"]
    assert page.robot_pose == (1.25, -2.5, 0.75)
    assert page.robot_pose_updates[-1] == (1.25, -2.5, 0.75)


def test_navigation_pose_stream_accepts_localization_ready_without_map_echo(monkeypatch):
    monkeypatch.setattr("dog_remote_tool.ui.pages.navigation.streams.localization.pose_stream_command", lambda profile: "pose-stream")
    page = _FakeNavigationRefreshPage()
    page.map_pcd_path.setText("/opt/data/.robot/map/history_map/a/map.pcd")
    page.prepared_map_pcd_path = ""
    page.last_status_values = {
        "MAP_OK": "1",
        "LOCALIZATION_READY": "1",
    }

    assert NavigationPage.start_pose_stream(page) is True

    NavigationPage.handle_robot_pose_update(page, (1.25, -2.5, 0.75))

    assert page.pose_stream_slot.start_calls == ["pose-stream"]
    assert page.robot_pose == (1.25, -2.5, 0.75)
    assert page.robot_pose_updates[-1] == (1.25, -2.5, 0.75)


def test_navigation_pose_stream_rejects_pose_when_status_is_other_map(monkeypatch):
    monkeypatch.setattr("dog_remote_tool.ui.pages.navigation.streams.localization.pose_stream_command", lambda profile: "pose-stream")
    page = _FakeNavigationRefreshPage()
    page.map_pcd_path.setText("/opt/data/.robot/map/history_map/a/map.pcd")
    page.prepared_map_pcd_path = ""
    page.last_status_values = {
        "MAP_PCD": "/opt/data/.robot/map/history_map/b/map.pcd",
        "MAP_OK": "1",
        "LOCALIZATION_READY": "1",
    }

    assert NavigationPage.start_pose_stream(page) is False

    NavigationPage.handle_robot_pose_update(page, (1.25, -2.5, 0.75))

    assert page.pose_stream_slot.start_calls == []
    assert page.robot_pose is None
    assert page.robot_pose_updates == []


def test_navigation_pose_stream_retries_transient_ros_init_failure(monkeypatch):
    scheduled = []
    monkeypatch.setattr(
        "dog_remote_tool.ui.pages.navigation.streams.QTimer.singleShot",
        lambda delay, callback: scheduled.append((delay, getattr(callback, "__name__", ""))),
    )
    page = _FakeNavigationRefreshPage()
    page.map_pcd_path.setText("/opt/data/.robot/map/history_map/a/map.pcd")
    page.prepared_map_pcd_path = "/opt/data/.robot/map/history_map/a/map.pcd"
    page.pose_stream_slot.running = True
    page.pose_stream_slot.finish_output = "STREAM=ros_error MARKER=dog_remote_tool_pose_stream ERROR=Error setting up zenoh session\n"

    NavigationPage.pose_stream_finished(page, page.pose_stream_slot.process, 15)

    assert scheduled == [(3000, "start_pose_stream")]
    assert page.pose_stream_transient_failures == 1
    assert page.nav_status_note.text == "位姿/路径流初始化失败，3 秒后重试"
    assert any("将在 3 秒后重试" in line for line in page.navigation_log_lines)


def test_navigation_status_refresh_starts_pose_without_workspace_but_not_plan(monkeypatch):
    scheduled = []
    monkeypatch.setattr(
        "dog_remote_tool.ui.pages.navigation.page.QTimer.singleShot",
        lambda delay, callback: scheduled.append((delay, getattr(callback, "__name__", ""))),
    )
    page = _FakeNavigationRefreshPage()
    page.map_pcd_path.setText("/opt/data/.robot/map/map.pcd")
    page.prepared_map_pcd_path = "/opt/data/.robot/map/map.pcd"
    page.status_slot.running = True
    page.status_slot.finish_output = "STATUS=ready\nTEXT=导航就绪\nMAP_OK=1\nLOCALIZATION_READY=1\n"

    NavigationPage.status_finished(page, page.status_slot.process, 0, 42)

    assert (0, "start_pose_stream") in scheduled
    assert (0, "start_plan_stream") not in scheduled
    assert page.pose_stream_slot.start_calls == []
    assert page.plan_stream_slot.start_calls == []


def test_navigation_status_refresh_starts_pose_while_current_map_prepare_is_still_running(monkeypatch):
    scheduled = []
    monkeypatch.setattr(
        "dog_remote_tool.ui.pages.navigation.page.QTimer.singleShot",
        lambda delay, callback: scheduled.append((delay, getattr(callback, "__name__", ""))),
    )
    page = _FakeNavigationRefreshPage()
    page.map_pcd_path.setText("/opt/data/.robot/map/history_map/a/map.pcd")
    page.prepared_map_pcd_path = ""
    page.preparing_map_pcd_path = "/opt/data/.robot/map/history_map/a/map.pcd"
    page.map_prepare_slot.running = True
    page.status_slot.running = True
    page.status_slot.finish_output = (
        "STATUS=ready\n"
        "TEXT=可发送目标\n"
        "MAP_PCD=/opt/data/.robot/map/history_map/a/map.pcd\n"
        "MAP_OK=1\n"
        "LOCALIZATION_READY=1\n"
    )

    NavigationPage.status_finished(page, page.status_slot.process, 0, 43)

    assert (0, "start_pose_stream") in scheduled
    assert (0, "start_plan_stream") not in scheduled


def test_navigation_status_refresh_does_not_start_pose_while_other_map_prepare_is_running(monkeypatch):
    scheduled = []
    monkeypatch.setattr(
        "dog_remote_tool.ui.pages.navigation.page.QTimer.singleShot",
        lambda delay, callback: scheduled.append((delay, getattr(callback, "__name__", ""))),
    )
    page = _FakeNavigationRefreshPage()
    page.map_pcd_path.setText("/opt/data/.robot/map/history_map/a/map.pcd")
    page.prepared_map_pcd_path = ""
    page.preparing_map_pcd_path = "/opt/data/.robot/map/history_map/b/map.pcd"
    page.map_prepare_slot.running = True
    page.status_slot.running = True
    page.status_slot.finish_output = (
        "STATUS=ready\n"
        "TEXT=可发送目标\n"
        "MAP_PCD=/opt/data/.robot/map/history_map/a/map.pcd\n"
        "MAP_OK=1\n"
        "LOCALIZATION_READY=1\n"
    )

    NavigationPage.status_finished(page, page.status_slot.process, 0, 44)

    assert (0, "start_pose_stream") not in scheduled
    assert (0, "start_plan_stream") not in scheduled


def test_navigation_map_selection_clears_stale_robot_pose_and_routes():
    page = _FakeNavigationRefreshPage()
    page.nav_map = _FakeWorkspaceCanvas()
    page.robot_pose = (3.0, 4.0, 0.5)
    page.navigation_global_route = [(1.0, 1.0, 0.0), (2.0, 2.0, 0.0)]
    page.navigation_realtime_plan = [(3.0, 3.0, 0.0), (4.0, 4.0, 0.0)]
    page.navigation_global_plan_topic = "/old/global"
    page.navigation_realtime_plan_topic = "/old/local"
    page.navigation_tracking_enabled = True
    page.navigation_tracking_active_seen = True
    page.last_status_values = {"TEXT": "旧图定位正常"}
    page.last_status_state = "success"
    page.last_status_at = 42.0
    page.pending_navigation_action = "goal"
    page.prepared_map_pcd_path = "/old/map.pcd"
    page.waypoints_text = _FakeWaypointText("1.000,2.000,0.000\n3.000,4.000,0.000")
    page.goal_point_selected = True
    page.added_waypoint_undo_stack = [("add", "old")]
    page.route_target_node_ids = [10, 20]
    page.nav_map.set_points([(1.0, 2.0, 0.0), (3.0, 4.0, 0.0)])
    page.nav_map.set_route_target_node_ids([10, 20])

    NavigationPage.on_map_selection_changed(page)

    assert page.robot_pose is None
    assert page.navigation_global_route == []
    assert page.navigation_realtime_plan == []
    assert page.navigation_global_plan_topic == ""
    assert page.navigation_realtime_plan_topic == ""
    assert page.navigation_tracking_enabled is False
    assert page.navigation_tracking_active_seen is False
    assert page.last_status_values == {}
    assert page.last_status_state == "unknown"
    assert page.last_status_at == 0.0
    assert page.pending_navigation_action == ""
    assert page.robot_pose_updates[-1] is None
    assert page.waypoints_text.toPlainText() == ""
    assert page.goal_point_selected is False
    assert page.added_waypoint_undo_stack == []
    assert page.route_target_node_ids == []
    assert page.nav_map.points[-1] == []
    assert page.nav_map.route_target_node_ids[-1] == []


def test_navigation_map_selection_stops_running_navigation_before_switch(monkeypatch):
    old_map_pcd = "/opt/data/.robot/map/history_map/old/map.pcd"
    new_map_pgm = "/opt/data/.robot/map/history_map/new/map.pgm"
    new_map_pcd = "/opt/data/.robot/map/history_map/new/map.pcd"
    page = _FakeNavigationRefreshPage(selected_map=new_map_pgm)
    page.map_pcd_path.setText(old_map_pcd)
    page.prepared_map_pcd_path = old_map_pcd
    page.navigation_tracking_enabled = True
    page.last_status_values = {
        "STATUS": "active",
        "TEXT": "导航执行中",
        "MAP_PCD": old_map_pcd,
        "NAV_STATE": "100",
        "NAV_TASK_STATUS": "2",
    }
    stop_calls = []

    def fake_stop(self):
        stop_calls.append(self.map_pcd_path.text())
        return True

    monkeypatch.setattr(NavigationPage, "stop_navigation_for_map_switch", fake_stop)
    monkeypatch.setattr(NavigationPage, "start_selected_map_preparation", lambda self, force=False: False)

    NavigationPage.on_map_selection_changed(page)

    assert stop_calls == [new_map_pcd]
    assert page.navigation_tracking_enabled is False
    assert page.prepared_map_pcd_path == ""
    assert page.status_refresh_calls == 1


def test_navigation_map_preparation_success_marks_current_map_ready(monkeypatch):
    monkeypatch.setattr("dog_remote_tool.ui.pages.navigation.page.QTimer.singleShot", lambda _ms, _callback: None)
    page = _FakeNavigationRefreshPage(selected_map="/opt/data/.robot/map/history_map/a/map.pgm")
    page.map_pcd_path.setText("/opt/data/.robot/map/history_map/a/map.pcd")
    page.preparing_map_pcd_path = "/opt/data/.robot/map/history_map/a/map.pcd"
    page.map_prepare_slot.running = True
    page.map_prepare_slot.finish_output = "[INFO] 导航地图初始化已下发，不等待状态回读\n"
    page.last_status_values = {
        "STATUS": "ready",
        "TEXT": "旧地图导航就绪",
        "MAP_PCD": "/opt/data/.robot/map/history_map/a/map.pcd",
        "MAP_OK": "1",
        "LOAD_MAP_SERVICE": "1",
        "LOCALIZATION_READY": "1",
        "NAV_PROCESS": "1",
        "START_NAV_SUBSCRIBERS": "1",
    }

    assert NavigationPage.map_preparation_finished(page, page.map_prepare_slot.process, 0, 15) is True

    assert page.prepared_map_pcd_path == "/opt/data/.robot/map/history_map/a/map.pcd"
    assert page.last_status_state == "ready"
    assert page.last_status_values["TEXT"] == "导航就绪"
    assert page.last_status_values["LOCALIZATION_READY"] == "1"
    assert page.last_status_values["MAP_PREP_NAV_READY"] == "1"
    assert page.localization_state.text == "定位\n连续定位正常"
    assert page.localization_state.styles[-1] == "ready"
    assert page.task_state.text == "任务\n导航就绪"
    assert page.task_state.styles[-1] == "ready"
    assert page.nav_current_state.text == "当前状态\n● 导航就绪"
    assert page.nav_current_state.styles[-1] == "ready"
    assert page.nav_status_note.text == "所选地图已初始化，定位已确认，可发送导航任务"
    assert "后台继续刷新完整导航状态" in page.flow_detail.text
    assert page.point_nav_button.enabled is True
    assert page.route_mode_button.enabled is True
    assert page.route_goal_button.enabled is False
    assert "点位" in page.point_nav_button.tooltip


def test_navigation_map_preparation_nonzero_with_ready_status_does_not_show_failure(monkeypatch):
    monkeypatch.setattr("dog_remote_tool.ui.pages.navigation.page.QTimer.singleShot", lambda _ms, _callback: None)
    page = _FakeNavigationRefreshPage(selected_map="/opt/data/.robot/map/history_map/a/map.pgm")
    page.map_pcd_path.setText("/opt/data/.robot/map/history_map/a/map.pcd")
    page.preparing_map_pcd_path = "/opt/data/.robot/map/history_map/a/map.pcd"
    page.pending_navigation_action = "goal"
    page.map_prepare_slot.running = True
    page.map_prepare_slot.finish_output = (
        "MAP_PREP_LOCALIZATION_READY=1\n"
        "MAP_PREP_NAV_READY=1\n"
        "[WARN] 状态回读超时，但地图和导航通道已就绪\n"
    )

    assert NavigationPage.map_preparation_finished(page, page.map_prepare_slot.process, 8, 16) is True

    assert page.prepared_map_pcd_path == "/opt/data/.robot/map/history_map/a/map.pcd"
    assert page.map_prepare_error == ""
    assert page.map_state.text == "地图\n已初始化"
    assert page.localization_state.text == "定位\n连续定位正常"
    assert page.task_state.text == "任务\n导航就绪"
    assert page.nav_status_note.text == "地图初始化和定位已确认，正在自动下发导航任务"
    assert not any("初始化失败：" in line for line in page.navigation_log_lines)


def test_navigation_map_preparation_empty_error_refreshes_status_without_failure(monkeypatch):
    scheduled = []
    monkeypatch.setattr(
        "dog_remote_tool.ui.pages.navigation.page.QTimer.singleShot",
        lambda delay, callback: scheduled.append((delay, getattr(callback, "__name__", ""))),
    )
    page = _FakeNavigationRefreshPage(selected_map="/opt/data/.robot/map/history_map/a/map.pgm")
    page.map_pcd_path.setText("/opt/data/.robot/map/history_map/a/map.pcd")
    page.preparing_map_pcd_path = "/opt/data/.robot/map/history_map/a/map.pcd"
    page.pending_navigation_action = "goal"
    page.map_prepare_slot.running = True
    page.map_prepare_slot.finish_output = ""

    assert NavigationPage.map_preparation_finished(page, page.map_prepare_slot.process, 8, 16) is True

    assert page.map_prepare_error == ""
    assert page.pending_navigation_action == "goal"
    assert page.nav_status_note.text == "地图初始化状态未回读，正在刷新远端状态"
    assert page.flow_detail.text == "流程摘要\n地图初始化命令未返回详细错误，正在刷新远端状态"
    assert scheduled == [(0, "refresh_navigation_status")]
    assert any("初始化状态未回读" in line for line in page.navigation_log_lines)
    assert not any("初始化失败：" in line for line in page.navigation_log_lines)
    assert page.workspace_refreshes >= 1


def test_navigation_map_preparation_skips_when_cached_status_is_ready():
    page = _FakeNavigationRefreshPage(selected_map="/opt/data/.robot/map/history_map/a/map.pgm")
    page.map_pcd_path.setText("/opt/data/.robot/map/history_map/a/map.pcd")
    page.prepared_map_pcd_path = ""
    page.last_status_values = {
        "STATUS": "ready",
        "TEXT": "导航待命",
        "MAP_PCD": "/opt/data/.robot/map/history_map/a/map.pcd",
        "MAP_OK": "1",
        "LOCALIZATION_READY": "1",
        "NAV_PROCESS": "1",
        "START_NAV_SUBSCRIBERS": "1",
    }

    assert NavigationPage.start_selected_map_preparation(page) is False

    assert page.map_prepare_slot.start_calls == []
    assert page.prepared_map_pcd_path == "/opt/data/.robot/map/history_map/a/map.pcd"
    assert page.preparing_map_pcd_path == ""
    assert page.nav_status_note.text == "远端已确认当前地图和定位就绪，可发送导航任务"
    assert page.navigation_log_lines == []


def test_navigation_relocalize_forces_cached_ready_status_remote_prepare():
    page = _FakeNavigationActionPage()
    page.map_prepare_slot = _FakeSlot(running=False)
    page.prepared_map_pcd_path = ""
    page.last_status_values = {
        "STATUS": "ready",
        "TEXT": "导航就绪",
        "MAP_PCD": page.map_pcd,
        "MAP_OK": "1",
        "LOCALIZATION_READY": "1",
        "NAV_PROCESS": "1",
        "START_NAV_SUBSCRIBERS": "1",
    }

    assert NavigationPage.make_relocalize_selected_map(page) is True

    assert page.map_prepare_slot.start_calls
    assert page.prepared_map_pcd_path == ""
    assert page.preparing_map_pcd_path == page.map_pcd
    assert page.nav_status_note.text == "正在为所选地图加载定位并初始化导航"
    assert any("已请求重新定位当前地图" in line for line in page.navigation_log_lines)


def test_navigation_map_preparation_alg_timeout_fails_without_legacy_status_retry(monkeypatch):
    scheduled = []
    monkeypatch.setattr(
        "dog_remote_tool.ui.pages.navigation.page.QTimer.singleShot",
        lambda delay, callback: scheduled.append((delay, getattr(callback, "__name__", ""))),
    )
    page = _FakeNavigationRefreshPage(selected_map="/opt/data/.robot/map/history_map/a/map.pgm")
    page.map_pcd_path.setText("/opt/data/.robot/map/history_map/a/map.pcd")
    page.preparing_map_pcd_path = "/opt/data/.robot/map/history_map/a/map.pcd"
    page.pending_navigation_action = "goal"
    page.map_prepare_slot.running = True
    page.map_prepare_slot.finish_output = (
        "[ERROR] alg定位等待连续定位超时: "
        "map_id=a elapsed=45.1s\n"
    )

    assert NavigationPage.map_preparation_finished(page, page.map_prepare_slot.process, 8, 16) is True

    assert page.prepared_map_pcd_path == ""
    assert page.pending_navigation_action == ""
    assert "alg定位等待连续定位超时" in page.map_prepare_error
    assert page.map_state.text == "地图\n初始化失败"
    assert page.localization_state.text == "定位\n地图未加载"
    assert page.task_state.text == "任务\n地图初始化失败"
    assert page.nav_status_note.text == "地图初始化失败，请查看日志或重新选择地图"
    assert scheduled == []
    assert any("初始化失败：" in line for line in page.navigation_log_lines)


def test_navigation_map_preparation_alg_failure_fails_without_legacy_status_matching(monkeypatch):
    scheduled = []
    monkeypatch.setattr(
        "dog_remote_tool.ui.pages.navigation.page.QTimer.singleShot",
        lambda delay, callback: scheduled.append((delay, getattr(callback, "__name__", ""))),
    )
    page = _FakeNavigationRefreshPage(selected_map="/opt/data/.robot/map/history_map/a/map.pgm")
    page.map_pcd_path.setText("/opt/data/.robot/map/history_map/a/map.pcd")
    page.preparing_map_pcd_path = "/opt/data/.robot/map/history_map/a/map.pcd"
    page.pending_navigation_action = "goal"
    page.map_prepare_slot.running = True
    page.map_prepare_slot.finish_output = (
        "[ERROR] alg定位失败: LocFailed\n"
    )

    assert NavigationPage.map_preparation_finished(page, page.map_prepare_slot.process, 5, 17) is True

    assert page.prepared_map_pcd_path == ""
    assert page.pending_navigation_action == ""
    assert "alg定位失败" in page.map_prepare_error
    assert page.map_state.text == "地图\n初始化失败"
    assert page.localization_state.text == "定位\n地图未加载"
    assert page.task_state.text == "任务\n地图初始化失败"
    assert page.nav_status_note.text == "地图初始化失败，请查看日志或重新选择地图"
    assert scheduled == []
    assert any("初始化失败：" in line for line in page.navigation_log_lines)


def test_navigation_map_switch_cancels_previous_prepare_and_starts_latest_map(monkeypatch):
    monkeypatch.setattr("dog_remote_tool.ui.pages.navigation.page.QTimer.singleShot", lambda _ms, _callback: None)
    page = _FakeNavigationRefreshPage(selected_map="/opt/data/.robot/map/history_map/b/map.pgm")
    page.map_pcd_path.setText("/opt/data/.robot/map/history_map/b/map.pcd")
    page.preparing_map_pcd_path = "/opt/data/.robot/map/history_map/a/map.pcd"
    page.map_prepare_slot = _FakeSlot(running=True, output="[INFO] 导航地图初始化已下发，不等待状态回读\n")

    assert NavigationPage.start_selected_map_preparation(page) is True

    assert page.map_prepare_slot.stop_calls == 1
    assert page.map_prepare_slot.start_calls
    assert "/opt/data/.robot/map/history_map/b/map.pcd" in page.map_prepare_slot.start_calls[-1]
    assert page.preparing_map_pcd_path == "/opt/data/.robot/map/history_map/b/map.pcd"
    assert page.nav_status_note.text == "正在为所选地图加载定位并初始化导航"
    assert page.navigation_log_lines == []


def test_navigation_pose_stream_does_not_start_when_inactive_or_busy(monkeypatch):
    monkeypatch.setattr("dog_remote_tool.ui.pages.navigation.streams.localization.pose_stream_command", lambda profile: "pose-stream")
    inactive = _FakeNavigationRefreshPage(active=False)
    busy = _FakeNavigationRefreshPage()
    busy.pose_stream_slot = _FakeSlot(running=True)

    assert NavigationPage.start_pose_stream(inactive) is False
    assert inactive.pose_stream_slot.start_calls == []
    assert NavigationPage.start_pose_stream(busy) is False
    assert busy.pose_stream_slot.start_calls == []


def test_navigation_deactivate_clears_pending_auto_goal():
    page = _FakeNavigationRefreshPage(status_running=True, list_running=True, preview_running=True)
    page.pending_navigation_action = "goal"

    NavigationPage.deactivate_page(page)

    assert page.page_active is False
    assert page.status_slot.stop_calls == 1
    assert page.map_list_slot.stop_calls == 1
    assert page.map_preview_slot.stop_calls == 1
    assert page.route_check_slot.stop_calls == 1
    assert page.mode_switch_helper_slot.stop_calls == 1
    assert page.pose_stream_slot.stop_calls == 1
    assert page.plan_stream_slot.stop_calls == 1
    assert page.stop_navigation_camera_overlay_calls == 1
    assert page.pending_navigation_action == ""


def test_navigation_cleanup_detached_uses_lifecycle_qprocess(monkeypatch):
    page = _FakeNavigationRefreshPage()
    page.navigation_cleanup_profile = get_product("xg2_s100")
    calls = []

    monkeypatch.setattr(
        navigation_lifecycle.QProcess,
        "startDetached",
        lambda program, args: calls.append((program, args)) or True,
    )

    assert NavigationPage.cleanup_navigation_tool_helpers_detached(page) is True
    assert calls
    program, args = calls[0]
    assert program == "bash"
    assert args[0] == "-lc"
    assert "dog_remote_start_navigation_helper" in args[1]


def test_navigation_activate_waits_for_map_list_before_status_refresh(monkeypatch):
    scheduled = []
    monkeypatch.setattr(
        "dog_remote_tool.ui.pages.navigation.page.QTimer.singleShot",
        lambda delay, callback: scheduled.append((delay, getattr(callback, "__name__", ""))),
    )
    page = _FakeNavigationRefreshPage(active=False)

    NavigationPage.activate_page(page)

    assert page.page_active is True
    assert scheduled == [
        (100, "ensure_navigation_helpers"),
        (150, "refresh_map_list"),
        (600, "start_navigation_camera_overlay"),
    ]

    NavigationPage.activate_page(page)

    assert scheduled == [
        (100, "ensure_navigation_helpers"),
        (150, "refresh_map_list"),
        (600, "start_navigation_camera_overlay"),
    ]


def test_navigation_status_finished_returns_accept_result():
    stale = _FakeNavigationRefreshPage()
    stale.status_slot = _FakeSlot(output=None)

    assert NavigationPage.status_finished(stale, stale.status_slot.process, exit_code=0, request_id=24) is False

    page = _FakeNavigationRefreshPage()
    page.status_slot = _FakeSlot(output="STATUS=ready\nTEXT=导航就绪\nMAP_OK=1\n")

    assert NavigationPage.status_finished(page, page.status_slot.process, exit_code=0, request_id=25) is True
    assert page.last_status_state == "ready"
    assert page.last_status_values["TEXT"] == "导航就绪"
    assert page.card_values[-1][0]["STATUS"] == "ready"
    assert page.card_values[-1][0]["TEXT"] == "导航就绪"


def test_navigation_status_finished_preserves_confirmed_arc_charging_when_probe_lacks_arc_fields():
    page = _FakeNavigationRefreshPage()
    page.map_pcd_path.setText("/opt/data/.robot/map/map.pcd")
    page.last_status_values = {
        "STATUS": "ready",
        "TEXT": "充电中",
        "MAP_PCD": "/opt/data/.robot/map/map.pcd",
        "ARC_DOCK_STATE": "2",
        "ARC_DOCK_TEXT": "充电中",
        "ARC_APP_DOCK_STATUS": "Charging",
        "ARC_APP_ALG_STATUS": "Charging",
    }
    page.status_slot = _FakeSlot(
        output=(
            "STATUS=ready\n"
            "TEXT=导航待命\n"
            "MAP_PCD=/opt/data/.robot/map/map.pcd\n"
            "MAP_OK=1\n"
            "LOAD_MAP_SERVICE=1\n"
            "NAV_PROCESS=1\n"
            "START_NAV_SUBSCRIBERS=1\n"
            "LOCALIZATION_READY=1\n"
        )
    )

    assert NavigationPage.status_finished(page, page.status_slot.process, exit_code=0, request_id=26) is True
    assert page.last_status_values["ARC_DOCK_STATE"] == "2"
    assert page.last_status_values["ARC_APP_DOCK_STATUS"] == "Charging"
    assert page.card_values[-1][0]["ARC_DOCK_TEXT"] == "充电中"


def test_navigation_status_finished_preserves_confirmed_arc_charging_when_arc_probe_is_empty():
    page = _FakeNavigationRefreshPage()
    page.map_pcd_path.setText("/opt/data/.robot/map/map.pcd")
    page.last_status_values = {
        "STATUS": "ready",
        "MAP_PCD": "/opt/data/.robot/map/map.pcd",
        "ARC_DOCK_STATE": "2",
        "ARC_DOCK_TEXT": "充电中",
        "ARC_APP_DOCK_STATUS": "Charging",
        "ARC_APP_ALG_STATUS": "Charging",
    }
    page.status_slot = _FakeSlot(
        output=(
            "STATUS=ready\n"
            "TEXT=导航待命\n"
            "MAP_PCD=/opt/data/.robot/map/map.pcd\n"
            "MAP_OK=1\n"
            "ARC_DOCK_STATE=\n"
            "ARC_DOCK_TEXT=无数据\n"
            "ARC_APP_CHANNEL=BUSY\n"
        )
    )

    assert NavigationPage.status_finished(page, page.status_slot.process, exit_code=0, request_id=27) is True
    assert page.last_status_values["ARC_DOCK_STATE"] == "2"
    assert page.last_status_values["ARC_APP_DOCK_STATUS"] == "Charging"


def test_navigation_status_finished_clears_charging_when_arc_reports_standby():
    page = _FakeNavigationRefreshPage()
    page.map_pcd_path.setText("/opt/data/.robot/map/map.pcd")
    page.last_status_values = {
        "STATUS": "ready",
        "MAP_PCD": "/opt/data/.robot/map/map.pcd",
        "ARC_DOCK_STATE": "2",
        "ARC_DOCK_TEXT": "充电中",
        "ARC_APP_DOCK_STATUS": "Charging",
        "ARC_APP_ALG_STATUS": "Charging",
    }
    page.status_slot = _FakeSlot(
        output=(
            "STATUS=ready\n"
            "TEXT=导航待命\n"
            "MAP_PCD=/opt/data/.robot/map/map.pcd\n"
            "MAP_OK=1\n"
            "ARC_DOCK_STATE=0\n"
            "ARC_DOCK_TEXT=空闲\n"
            "ARC_APP_DOCK_STATUS=StandBy\n"
            "ARC_APP_ALG_STATUS=StandBy\n"
        )
    )

    assert NavigationPage.status_finished(page, page.status_slot.process, exit_code=0, request_id=28) is True
    assert page.last_status_values["ARC_DOCK_STATE"] == "0"
    assert page.last_status_values["ARC_APP_DOCK_STATUS"] == "StandBy"


def test_navigation_cards_show_remote_navigation_status_codes():
    page = _FakeNavigationRefreshPage()

    NavigationPage.set_cards_from_values(
        page,
        {
            "STATUS": "active",
            "TEXT": "导航执行中",
            "MAP_OK": "1",
            "LOAD_MAP_SERVICE": "1",
            "NAV_PROCESS": "1",
            "START_NAV_SUBSCRIBERS": "1",
            "LOCALIZATION_READY": "1",
            "LOCALIZATION_CODE": "3",
            "NAV_STATE": "100",
            "NAV_TASK_STATUS": "2",
            "NAV_ACTIVE_SUBSTATE": "1",
            "NAV_CURRENT_TASK_IDX": "0",
            "NAV_ESTIMATED_DISTANCE_REMAINING": "4.2",
        },
        "导航状态：执行中；任务：执行中；执行：避障；剩余 4.2 m",
    )

    assert page.navigation_state.text == "导航栈\n可用"
    assert page.nav_current_state.text == "当前状态\n▶ 导航执行中"
    assert page.nav_current_state.tooltip == "▶ 导航执行中"
    assert page.nav_current_state.styles[-1] == "active"
    assert page.task_state.text == "任务\n导航中"
    assert page.task_state.styles[-1] == "active"
    assert page.nav_status_note.text == "导航中：导航执行中"
    assert page.nav_code_detail.text == "导航执行中"
    assert page.nav_code_detail.tooltip == "导航状态：执行中；任务：执行中；执行：避障；剩余 4.2 m"
    assert page.finished_visualization_statuses == ["active"]
    assert page.workspace_refreshes >= 1


def test_navigation_cards_hold_pending_command_until_runner_finishes():
    page = _FakeNavigationRefreshPage()
    page.runner = _FakeRunner(tasks={7: object()})
    page.navigation_command_task_id = 7
    page.navigation_command_operation = "路网导航中"

    NavigationPage.set_cards_from_values(
        page,
        {
            "STATUS": "ready",
            "TEXT": "导航待命",
            "MAP_OK": "1",
            "NAV_PROCESS": "1",
            "START_NAV_SUBSCRIBERS": "1",
            "LOCALIZATION_READY": "1",
            "LOCALIZATION_CODE": "3",
            "NAV_STATE": "0",
            "NAV_TASK_STATUS": "0",
        },
    )

    assert page.task_state.text == "任务\n路网目标下发中"
    assert page.task_state.styles[-1] == "starting"
    assert page.nav_current_state.text == "当前状态\n● 路网目标下发中"
    assert page.nav_current_state.styles[-1] == "starting"
    assert page.nav_status_note.text == "路网目标下发中"
    assert page.nav_code_detail.text == "路网目标下发中"
    assert page.nav_code_detail.tooltip == "等待远端接收路网目标并进入执行中"


def test_navigation_runner_app_status_updates_card_immediately():
    page = _FakeNavigationRefreshPage()
    page.navigation_command_task_id = 7
    page.navigation_command_operation = "多点导航中"

    NavigationPage.on_runner_task_output(page, 7, "APP_NAV_STATUS=Active\n")

    assert page.last_status_values["APP_NAV_STATUS"] == "Active"
    assert page.last_status_state == "active"
    assert page.nav_current_state.text == "当前状态\n▶ Active"
    assert page.task_state.text == "任务\n导航中"
    assert page.finished_visualization_statuses == ["active"]

    NavigationPage.on_runner_task_output(page, 7, "APP_NAV_STATUS=Succeeded\n")

    assert page.last_status_values["APP_NAV_STATUS"] == "Succeeded"
    assert page.last_status_state == "success"
    assert page.nav_current_state.text == "当前状态\n✓ Succeeded"
    assert page.navigation_command_task_id is None
    assert page.navigation_command_operation == ""


def test_navigation_cards_clear_route_nodes_after_stable_standby_arrival():
    page = _FakeNavigationActionPage()
    page.runner = _FakeRunner(tasks={})
    page.navigation_tracking_enabled = True
    page.navigation_tracking_active_seen = True
    page.navigation_status_watch_running = True
    page.navigation_command_task_id = None
    page.navigation_command_operation = ""
    values = {
        "STATUS": "ready",
        "TEXT": "导航待命",
        "MAP_OK": "1",
        "NAV_PROCESS": "1",
        "START_NAV_SUBSCRIBERS": "1",
        "LOCALIZATION_READY": "1",
        "LOCALIZATION_CODE": "3",
        "NAV_STATE": "1",
        "NAV_TASK_STATUS": "",
        "NAV_DISTANCE_FROM_START": "2.0",
        "NAV_ESTIMATED_DISTANCE_REMAINING": "0.0",
    }

    page.last_status_values.update(values)
    NavigationPage.set_cards_from_values(page, dict(values))
    page.last_status_values.update(values)
    NavigationPage.set_cards_from_values(page, dict(values))

    assert page.navigation_tracking_enabled is False
    assert page.navigation_status_watch_running is False
    assert page.route_target_node_ids == []
    assert page.waypoints_text.toPlainText() == ""
    assert page.nav_map.route_target_node_ids[-1] == []


def test_navigation_cards_keep_pending_command_until_app_terminal_status():
    page = _FakeNavigationRefreshPage()
    page.runner = _FakeRunner(tasks={})
    page.navigation_command_task_id = 7
    page.navigation_command_operation = "路网导航中"
    values = {
        "STATUS": "ready",
        "TEXT": "导航待命",
        "MAP_OK": "1",
        "NAV_PROCESS": "1",
        "START_NAV_SUBSCRIBERS": "1",
        "LOCALIZATION_READY": "1",
        "LOCALIZATION_CODE": "3",
        "NAV_STATE": "1",
        "NAV_TASK_STATUS": "",
        "NAV_DISTANCE_FROM_START": "0.0",
        "NAV_ESTIMATED_DISTANCE_REMAINING": "0.0",
    }

    NavigationPage.set_cards_from_values(page, dict(values))

    assert page.navigation_command_operation == "路网导航中"
    assert page.navigation_command_idle_confirmations == 0
    assert page.task_state.text == "任务\n路网目标下发中"
    assert page.task_state.styles[-1] == "starting"

    NavigationPage.set_cards_from_values(page, dict(values))

    assert page.navigation_command_task_id == 7
    assert page.navigation_command_operation == "路网导航中"
    assert page.navigation_command_idle_confirmations == 0
    assert page.task_state.text == "任务\n路网目标下发中"
    assert page.task_state.styles[-1] == "starting"
    assert page.nav_status_note.text == "路网目标下发中"


def test_navigation_cards_do_not_report_arrival_from_idle_progress_snapshot():
    page = _FakeNavigationRefreshPage()
    page.runner = _FakeRunner(tasks={7: object()})
    page.navigation_command_task_id = 7
    page.navigation_command_operation = "发送目标中"
    page.navigation_tracking_enabled = True
    page.navigation_tracking_active_seen = True

    NavigationPage.set_cards_from_values(
        page,
        {
            "STATUS": "ready",
            "TEXT": "导航待命",
            "MAP_OK": "1",
            "NAV_PROCESS": "1",
            "START_NAV_SUBSCRIBERS": "1",
            "LOCALIZATION_READY": "1",
            "LOCALIZATION_CODE": "3",
            "NAV_STATE": "1",
            "NAV_DISTANCE_FROM_START": "2.758",
            "NAV_ESTIMATED_DISTANCE_REMAINING": "0.0",
            "NAV_ESTIMATED_TIME_REMAINING_SEC": "0",
        },
    )

    assert page.navigation_command_task_id == 7
    assert page.navigation_command_operation == "发送目标中"
    assert page.task_state.text == "任务\n目标下发中"
    assert page.task_state.styles[-1] == "starting"
    assert page.nav_current_state.text.startswith("当前状态\n● 目标下发中")
    assert page.nav_status_note.text == "目标下发中"
    assert page.finished_visualization_statuses == ["starting"]


def test_navigation_cards_resume_remote_active_state_for_same_map(monkeypatch):
    scheduled = []
    monkeypatch.setattr(
        "dog_remote_tool.ui.pages.navigation.page.QTimer.singleShot",
        lambda ms, callback: scheduled.append((ms, getattr(callback, "__name__", "<lambda>"))),
    )
    map_pcd = "/opt/data/.robot/map/map.pcd"
    page = _FakeNavigationRefreshPage()
    page.map_pcd_path.setText(map_pcd)
    page.prepared_map_pcd_path = ""
    page.navigation_tracking_enabled = False

    NavigationPage.set_cards_from_values(
        page,
        {
            "STATUS": "active",
            "TEXT": "导航执行中",
            "MAP_PCD": map_pcd,
            "MAP_OK": "1",
            "LOAD_MAP_SERVICE": "1",
            "NAV_PROCESS": "1",
            "START_NAV_SUBSCRIBERS": "1",
            "LOCALIZATION_READY": "1",
            "NAV_STATE": "100",
            "NAV_TASK_STATUS": "2",
        },
    )

    assert page.navigation_tracking_enabled is True
    assert page.navigation_tracking_active_seen is True
    assert page.prepared_map_pcd_path == map_pcd
    assert page.navigation_log_lines == []
    assert (500, "<lambda>") in scheduled
    assert (0, "start_plan_stream") in scheduled


def test_navigation_cards_do_not_resume_remote_active_state_for_different_map(monkeypatch):
    scheduled = []
    monkeypatch.setattr(
        "dog_remote_tool.ui.pages.navigation.page.QTimer.singleShot",
        lambda ms, callback: scheduled.append((ms, getattr(callback, "__name__", "<lambda>"))),
    )
    page = _FakeNavigationRefreshPage()
    page.map_pcd_path.setText("/opt/data/.robot/map/current/map.pcd")
    page.prepared_map_pcd_path = ""

    NavigationPage.set_cards_from_values(
        page,
        {
            "STATUS": "active",
            "TEXT": "导航执行中",
            "MAP_PCD": "/opt/data/.robot/map/other/map.pcd",
            "MAP_OK": "1",
            "LOAD_MAP_SERVICE": "1",
            "NAV_PROCESS": "1",
            "START_NAV_SUBSCRIBERS": "1",
            "LOCALIZATION_READY": "1",
            "NAV_STATE": "100",
            "NAV_TASK_STATUS": "2",
        },
    )

    assert page.navigation_tracking_enabled is False
    assert page.navigation_tracking_active_seen is False
    assert page.prepared_map_pcd_path == ""
    assert not any("已接上远端导航状态" in line for line in page.navigation_log_lines)
    assert scheduled == []


def test_navigation_action_buttons_follow_remote_readiness_and_active_state():
    ready_values = {
        "STATUS": "ready",
        "TEXT": "导航就绪",
        "MAP_PCD": "/opt/data/.robot/map/map.pcd",
        "MAP_OK": "1",
        "LOAD_MAP_SERVICE": "1",
        "NAV_PROCESS": "1",
        "START_NAV_SUBSCRIBERS": "1",
        "LOCALIZATION_READY": "1",
        "LOCALIZATION_CODE": "3",
    }
    page = _FakeNavigationRefreshPage()
    page.map_pcd_path.setText("/opt/data/.robot/map/map.pcd")
    page.workspace_dialog = _FakeWorkspaceDialog()

    NavigationPage.set_cards_from_values(page, ready_values)

    assert page.point_nav_button.enabled is False
    assert page.relocalize_button.enabled is True
    assert page.route_mode_button.enabled is False
    assert page.route_goal_button.enabled is False
    assert page.arc_calibration_button.enabled is True
    assert page.arc_mark_button.enabled is False
    assert page.stop_button.enabled is True
    assert page.stop_button.text == "停止"
    assert page.stop_button.tooltip == "发送停止命令并释放导航控制权"
    assert page.pause_resume_button.enabled is False
    assert page.pause_resume_button.text == "暂停"
    assert "初始化" in page.point_nav_button.tooltip
    assert "充电桩标定" in page.arc_calibration_button.tooltip
    assert "初始化当前地图" in page.arc_mark_button.tooltip
    assert page.nav_action_status.text == "导航阻塞：等待所选地图初始化完成"
    assert page.workspace_dialog.action_status_label.text == "导航阻塞：等待所选地图初始化完成"
    assert page.navigation_log_lines == []
    assert page.workspace_dialog.point_nav_button.enabled is False
    assert page.workspace_dialog.relocalize_button.enabled is True
    assert page.workspace_dialog.route_mode_button.enabled is False
    assert page.workspace_dialog.arc_calibration_button.enabled is True
    assert page.workspace_dialog.arc_mark_button.enabled is False

    page.prepared_map_pcd_path = "/opt/data/.robot/map/map.pcd"

    NavigationPage.set_cards_from_values(page, ready_values)

    assert page.point_nav_button.enabled is True
    assert page.relocalize_button.enabled is True
    assert page.route_mode_button.enabled is True
    assert page.route_mode_button.text == "进入路网导航"
    assert page.route_goal_button.enabled is False
    assert page.route_goal_button.text == "开始路网导航"
    assert page.arc_calibration_button.enabled is True
    assert page.arc_mark_button.enabled is True
    assert "点位" in page.point_nav_button.tooltip
    assert "加载 map.geojson" in page.route_mode_button.tooltip
    assert "进入路网导航" in page.route_goal_button.tooltip
    assert "写入当前地图" in page.arc_mark_button.tooltip
    assert page.nav_action_status.text == "导航可用：可发送点位任务"
    assert page.workspace_dialog.action_status_label.text == "导航可用：可发送点位任务"
    assert page.workspace_dialog.route_mode_button.enabled is True
    assert page.workspace_dialog.route_goal_button.enabled is False
    assert page.workspace_dialog.relocalize_button.enabled is True
    assert page.workspace_dialog.arc_calibration_button.enabled is True
    assert page.workspace_dialog.arc_mark_button.enabled is True
    assert page.choose_route_file_button.enabled is True
    assert page.upload_route_file_button.enabled is False
    assert page.export_route_file_button.enabled is False

    page.navigation_loop_enabled = True

    NavigationPage.set_cards_from_values(page, ready_values)

    assert page.loop_button.text == "循环 ON"
    assert page.loop_button.object_name == "LoopSwitchOn"
    assert page.point_nav_button.text == "点位导航"
    assert page.route_goal_button.text == "开始路网导航"
    assert "循环模式已开启" in page.point_nav_button.tooltip

    page.navigation_loop_enabled = False
    page.route_file_states[page.selected_map_pgm()] = True

    NavigationPage.set_cards_from_values(page, ready_values)

    assert page.route_mode_button.enabled is True
    assert page.route_goal_button.enabled is False
    assert page.workspace_dialog.route_mode_button.enabled is True
    assert page.workspace_dialog.route_goal_button.enabled is False
    assert page.choose_route_file_button.enabled is True
    assert page.nav_action_status.text == "导航可用：可发送点位/路网任务"

    page.route_target_mode = True
    page.route_graph = route_network.RouteGraph(
        nodes={1: route_network.RouteNode(1, 1.0, 2.0)},
        edges={},
    )
    page.route_graph_remote_pgm = page.selected_map_pgm()
    page.waypoints_text = _FakeWaypointText("1.000,2.000,0.000")
    page.goal_point_selected = True

    NavigationPage.set_cards_from_values(page, ready_values)

    assert page.route_mode_button.text == "退出路网导航"
    assert page.route_mode_button.enabled is True
    assert page.point_nav_button.text == "点位导航"
    assert page.point_nav_button.enabled is False
    assert page.route_goal_button.enabled is True
    assert "退出" in page.route_mode_button.tooltip
    assert "路网导航模式" in page.point_nav_button.tooltip
    assert page.nav_action_status.text == "路网导航模式：点位导航已暂停，可选择路网目标"

    page.route_target_mode = False
    page.route_graph = None
    page.route_graph_remote_pgm = ""

    active_values = dict(ready_values)
    active_values.update({"STATUS": "active", "TEXT": "导航执行中", "NAV_STATE": "100", "NAV_TASK_STATUS": "2"})
    page.charging_docks = [(0, 1.0, 2.0, 0.0)]

    NavigationPage.set_cards_from_values(page, active_values)

    assert page.point_nav_button.enabled is False
    assert page.relocalize_button.enabled is False
    assert page.route_goal_button.enabled is False
    assert page.arc_calibration_button.enabled is False
    assert page.arc_mark_button.enabled is False
    assert page.mapped_recharge_button.enabled is True
    assert page.mapped_recharge_button.text == "有图进桩"
    assert page.stop_button.enabled is True
    assert page.stop_button.text == "停止"
    assert page.pause_resume_button.enabled is True
    assert page.pause_resume_button.text == "暂停"
    assert "远端已有导航任务" in page.point_nav_button.tooltip
    assert "远端已有导航任务" in page.arc_calibration_button.tooltip
    assert "远端已有导航任务" in page.arc_mark_button.tooltip
    assert page.nav_action_status.text == "导航阻塞：远端已有导航任务运行，先停止或等待结束"
    assert page.workspace_dialog.point_nav_button.enabled is False
    assert page.workspace_dialog.relocalize_button.enabled is False
    assert page.workspace_dialog.mapped_recharge_button.enabled is True
    assert page.workspace_dialog.stop_button.enabled is True
    assert page.workspace_dialog.stop_button.text == "停止"
    assert page.workspace_dialog.pause_resume_button.enabled is True

    paused_values = dict(ready_values)
    paused_values.update({"STATUS": "paused", "TEXT": "导航暂停", "NAV_STATE": "3", "NAV_TASK_STATUS": "3"})

    NavigationPage.set_cards_from_values(page, paused_values)

    assert page.pause_resume_button.enabled is True
    assert page.pause_resume_button.text == "继续"
    assert "恢复移动" in page.pause_resume_button.tooltip
    assert page.workspace_dialog.pause_resume_button.text == "继续"


def test_navigation_cards_show_status_six_active_description_as_localized():
    page = _FakeNavigationRefreshPage()

    NavigationPage.set_cards_from_values(
        page,
        {
            "STATUS": "ready",
            "TEXT": "导航待命",
            "MAP_OK": "1",
            "LOAD_MAP_SERVICE": "1",
            "NAV_PROCESS": "1",
            "START_NAV_SUBSCRIBERS": "1",
            "LOCALIZATION_READY": "1",
            "LOCALIZATION_CODE": "6",
            "LOCALIZATION_DESC": "Active: localization running normally.",
        },
    )

    assert page.localization_state.text == "定位\n连续定位正常"
    assert page.localization_state.styles[-1] == "ready"


def test_navigation_cards_show_robot_slam_state_100_as_localized():
    page = _FakeNavigationRefreshPage()

    NavigationPage.set_cards_from_values(
        page,
        {
            "STATUS": "ready",
            "TEXT": "导航待命",
            "LOCALIZATION_READY": "1",
            "LOCALIZATION_CODE_FIELD": "state",
            "LOCALIZATION_CODE": "100",
            "LOCALIZATION_DESC": "The localization system is normal.",
        },
    )

    assert page.localization_state.text == "定位\n连续定位正常"
    assert page.localization_state.styles[-1] == "ready"


def test_navigation_point_button_label_is_concise_and_uses_shared_readiness_gate():
    source = (
        inspect.getsource(NavigationPage)
        + inspect.getsource(NavigationWorkspaceDialog)
        + inspect.getsource(navigation_workspace_layout.NavigationWorkspaceLayoutMixin)
        + inspect.getsource(navigation_workspace_panels.NavigationWorkspacePanelsMixin)
        + inspect.getsource(navigation_action_panel.NavigationActionPanelMixin)
        + inspect.getsource(navigation_action_buttons.NavigationActionButtonsMixin)
    )

    assert 'QPushButton("点位导航")' in source
    assert 'QPushButton("有图进桩")' in source
    assert 'QPushButton("无图进桩")' not in source
    assert 'QPushButton("出桩")' not in source
    assert "开始点位导航" not in source
    assert '"point_nav_button": "使用当前点位开始导航；多个点按多点导航"' in source
    assert ".navigation_action_ready_reason(self, values or {})" in source


def test_navigation_action_readiness_does_not_require_load_map_service_state():
    page = _FakeNavigationRefreshPage()
    page.map_pcd_path.setText("/opt/data/.robot/map/map.pcd")
    page.prepared_map_pcd_path = "/opt/data/.robot/map/map.pcd"
    values = {
        "STATUS": "ready",
        "TEXT": "导航就绪",
        "MAP_PCD": "/opt/data/.robot/map/map.pcd",
        "MAP_OK": "1",
        "NAV_PROCESS": "1",
        "START_NAV_SUBSCRIBERS": "1",
        "LOCALIZATION_READY": "1",
    }

    ready, reason = NavigationPage.navigation_action_ready_reason(page, values)
    assert ready is True
    assert reason == "导航状态已就绪"

    values["LOAD_MAP_SERVICE"] = "0"

    ready, reason = NavigationPage.navigation_action_ready_reason(page, values)
    assert ready is True
    assert reason == "导航状态已就绪"

    values["LOAD_MAP_SERVICE"] = "1"

    ready, reason = NavigationPage.navigation_action_ready_reason(page, values)
    assert ready is True
    assert reason == "导航状态已就绪"


def test_navigation_action_readiness_blocks_when_charging():
    page = _FakeNavigationRefreshPage()
    page.map_pcd_path.setText("/opt/data/.robot/map/map.pcd")
    page.prepared_map_pcd_path = "/opt/data/.robot/map/map.pcd"
    values = {
        "STATUS": "ready",
        "TEXT": "导航就绪",
        "MAP_PCD": "/opt/data/.robot/map/map.pcd",
        "MAP_OK": "1",
        "NAV_PROCESS": "1",
        "START_NAV_SUBSCRIBERS": "1",
        "LOCALIZATION_READY": "1",
        "ARC_APP_DOCK_STATUS": "Charging",
    }

    ready, reason = NavigationPage.navigation_action_ready_reason(page, values)

    assert ready is False
    assert reason == "当前已检测到充电中，请先出桩"


def test_robot_summary_distinguishes_localization_ready_from_pose_missing():
    class Page:
        robot_pose = None
        last_status_values = {"LOCALIZATION_READY": "1"}

    assert NavigationPage.robot_pose_summary_text(Page()) == "机器人：定位正常，等待位姿"

    Page.last_status_values = {"LOCALIZATION_READY": "0"}
    assert NavigationPage.robot_pose_summary_text(Page()) == "机器人：等待定位"


def test_navigation_action_readiness_rejects_status_from_previous_map():
    page = _FakeNavigationRefreshPage()
    page.map_pcd_path.setText("/opt/data/.robot/map/current/map.pcd")
    page.prepared_map_pcd_path = "/opt/data/.robot/map/current/map.pcd"
    values = {
        "STATUS": "ready",
        "TEXT": "导航就绪",
        "MAP_PCD": "/opt/data/.robot/map/old/map.pcd",
        "MAP_OK": "1",
        "LOAD_MAP_SERVICE": "1",
        "NAV_PROCESS": "1",
        "START_NAV_SUBSCRIBERS": "1",
        "LOCALIZATION_READY": "1",
    }

    ready, reason = NavigationPage.navigation_action_ready_reason(page, values)

    assert ready is False
    assert reason == "等待当前地图状态刷新"


def test_navigation_map_list_finished_returns_accept_result(monkeypatch):
    class FakeBlocker:
        def __init__(self, _target):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr("dog_remote_tool.ui.pages.navigation.page.QSignalBlocker", FakeBlocker)

    stale = _FakeNavigationRefreshPage()
    stale.map_list_slot = _FakeSlot(output=None)

    assert NavigationPage.map_list_finished(stale, stale.map_list_slot.process, exit_code=0, request_id=26) is False

    failed = _FakeNavigationRefreshPage()
    failed.map_list_slot = _FakeSlot(output="ssh failed")

    assert NavigationPage.map_list_finished(failed, failed.map_list_slot.process, exit_code=1, request_id=27) is True
    assert failed.map_selector.items == [("current", "/opt/data/.robot/map/map.pgm")]
    assert failed.detail_updates == 0
    assert failed.status_refresh_calls == 1

    success = _FakeNavigationRefreshPage(selected_map="")
    success.map_list_slot = _FakeSlot(output="2026\t100\t2048\t/opt/data/.robot/map/history_map/a/map.pgm\n")

    assert NavigationPage.map_list_finished(success, success.map_list_slot.process, exit_code=0, request_id=28) is True
    assert success.map_entries_signature
    assert success.map_selector.items[0][1] == "/opt/data/.robot/map/history_map/a/map.pgm"
    assert success.map_pcd_path.text() == "/opt/data/.robot/map/history_map/a/map.pcd"
    assert success.route_geojson_path.text() == "/opt/data/.robot/map/history_map/a/map.geojson"
    assert success.detail_updates == 1
    assert success.preview_calls == 1
    assert success.status_refresh_calls == 1
    assert success.map_prepare_slot.start_calls == []
    assert success.map_state.text == ""
    assert success.last_status_values == {}
    assert success.last_status_state == "unknown"


def test_navigation_map_list_keeps_existing_cards_when_entries_are_unchanged(monkeypatch):
    class FakeBlocker:
        def __init__(self, _target):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr("dog_remote_tool.ui.pages.navigation.page.QSignalBlocker", FakeBlocker)
    remote = "/opt/data/.robot/map/history_map/a/map.pgm"
    output = f"2026\t100\t2048\t{remote}\n"
    page = _FakeNavigationRefreshPage(selected_map=remote)
    page.map_list_slot = _FakeSlot(output=output)
    page.map_entries_signature = tuple(navigation_status_refresh.parse_map_list_entries(output))
    page.map_cards = {remote: object()}
    page.preview_remote_pgm = remote

    assert NavigationPage.map_list_finished(page, page.map_list_slot.process, exit_code=0, request_id=29) is True

    assert page.map_card_updates == []
    assert page.map_card_selection_updates >= 1
    assert page.preview_calls == 0
    assert page.status_refresh_calls == 1


def test_navigation_map_list_refreshes_selected_preview_once_after_page_activation(monkeypatch):
    class FakeBlocker:
        def __init__(self, _target):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr("dog_remote_tool.ui.pages.navigation.page.QSignalBlocker", FakeBlocker)
    remote = "/opt/data/.robot/map/history_map/a/map.pgm"
    output = f"2026\t100\t2048\t{remote}\n"
    page = _FakeNavigationRefreshPage(selected_map=remote)
    page.map_list_slot = _FakeSlot(output=output)
    page.map_entries_signature = tuple(navigation_status_refresh.parse_map_list_entries(output))
    page.map_cards = {remote: object()}
    page.preview_remote_pgm = remote
    page.refresh_selected_map_preview_once = True

    assert NavigationPage.map_list_finished(page, page.map_list_slot.process, exit_code=0, request_id=30) is True

    assert page.map_card_updates == []
    assert page.map_card_selection_updates >= 1
    assert page.preview_calls == 1
    assert page.preview_force_calls == [True]
    assert page.refresh_selected_map_preview_once is False
    assert page.status_refresh_calls == 1


def test_navigation_map_list_returns_start_result():
    inactive = _FakeNavigationRefreshPage(active=False)

    assert NavigationPage.refresh_map_list(inactive) is False
    assert inactive.map_list_slot.start_calls == []

    busy = _FakeNavigationRefreshPage(list_running=True)

    assert NavigationPage.refresh_map_list(busy) is False
    assert busy.map_list_slot.start_calls == []

    page = _FakeNavigationRefreshPage()

    assert NavigationPage.refresh_map_list(page) is True
    assert page.map_list_slot.process.started is True
    assert len(page.map_list_slot.start_calls) == 1
    assert "/opt/data/.robot/map" in page.map_list_slot.start_calls[0]


def test_navigation_map_preview_returns_start_result():
    inactive = _FakeNavigationRefreshPage(active=False)

    assert NavigationPage.fetch_navigation_map_preview(inactive) is False
    assert inactive.map_preview_slot.start_calls == []

    unsupported = _FakeNavigationRefreshPage(supported=False)

    assert NavigationPage.fetch_navigation_map_preview(unsupported) is False
    assert unsupported.map_preview_slot.start_calls == []

    no_map = _FakeNavigationRefreshPage(selected_map="")

    assert NavigationPage.fetch_navigation_map_preview(no_map) is False
    assert no_map.map_preview_slot.start_calls == []

    busy = _FakeNavigationRefreshPage(preview_running=True)

    assert NavigationPage.fetch_navigation_map_preview(busy) is True
    assert busy.map_preview_slot.stop_calls == 1
    assert busy.map_preview_slot.process.started is True
    assert len(busy.map_preview_slot.start_calls) == 1
    assert "/opt/data/.robot/map/map.pgm" in busy.map_preview_slot.start_calls[0]


def test_navigation_map_preview_skips_fetch_when_selected_map_is_already_loaded():
    class LoadedPixmap:
        def isNull(self):
            return False

    remote = "/opt/data/.robot/map/history_map/a/map.pgm"
    page = _FakeNavigationRefreshPage(selected_map=remote)
    page.preview_remote_pgm = remote
    page.nav_map.source_pixmap = LoadedPixmap()

    assert NavigationPage.fetch_navigation_map_preview(page) is False

    assert page.map_preview_slot.start_calls == []
    assert page.map_preview_slot.stop_calls == 0


def test_navigation_map_preview_uses_local_cache_without_rsync(monkeypatch, tmp_path):
    class FakePixmap:
        def __init__(self, _path=""):
            pass

        def isNull(self):
            return False

    class FakeNavMap(_FakeText):
        def __init__(self):
            super().__init__()
            self.source_pixmap = None
            self.map_calls = []
            self.dock_calls = []

        def set_map(self, pixmap, resolution, origin):
            self.source_pixmap = pixmap
            self.map_calls.append((pixmap, resolution, origin))

        def set_charging_docks(self, docks):
            self.dock_calls.append(docks)

    remote = "/opt/data/.robot/map/history_map/a/map.pgm"
    (tmp_path / "map.pgm").write_bytes(b"cached")
    (tmp_path / "map.yaml").write_text("image: map.pgm\nresolution: 0.05\norigin: [1.0, 2.0, 0.0]\n", encoding="utf-8")
    monkeypatch.setattr(navigation_map_preview, "QPixmap", FakePixmap)
    monkeypatch.setattr(navigation_map_preview, "local_map_preview_dir", lambda *_args: tmp_path)
    monkeypatch.setattr(
        navigation_map_preview.NavigationMapPreviewMixin,
        "create_navigation_safety_overlay",
        staticmethod(lambda *_args, **_kwargs: None),
    )
    page = _FakeNavigationRefreshPage(selected_map=remote)
    page.nav_map = FakeNavMap()
    page.update_target_hint = lambda: None
    page.update_nav_map_points = lambda: None

    assert NavigationPage.fetch_navigation_map_preview(page) is True

    assert page.map_preview_slot.start_calls == []
    assert page.preview_remote_pgm == remote
    assert page.nav_map_preview_path == str(tmp_path / "map.pgm")
    assert page.nav_map.map_calls[0][1:] == (0.05, (1.0, 2.0, 0.0))
    assert page.nav_status_note.text == "地图已加载，确认后可开始导航"


def test_read_map_yaml_charging_docks_requires_arc_flag(tmp_path):
    yaml_path = tmp_path / "map.yaml"
    yaml_path.write_text(
        "image: map.pgm\n"
        "resolution: 0.05\n"
        "origin: [0.0, 0.0, 0.0]\n"
        "arc_position_flag: 1\n"
        "arc: [{tag_id: 0, arc_position: [1.2, -0.3, 0.4]}]\n",
        encoding="utf-8",
    )

    assert read_map_yaml_charging_docks(str(yaml_path)) == [(0, 1.2, -0.3, 0.4)]

    yaml_path.write_text(
        "image: map.pgm\narc_position_flag: 0\narc: [{tag_id: 0, arc_position: [1.2, -0.3, 0.4]}]\n",
        encoding="utf-8",
    )

    assert read_map_yaml_charging_docks(str(yaml_path)) == []


def test_navigation_map_preview_finished_refetches_when_selection_changed(monkeypatch, tmp_path):
    old_remote = "/opt/data/.robot/map/history_map/old/map.pgm"
    new_remote = "/opt/data/.robot/map/history_map/new/map.pgm"

    class _FakePixmap:
        def __init__(self, _path):
            pass

        def isNull(self):
            return False

    class _FakeNavMap(_FakeText):
        def __init__(self):
            super().__init__()
            self.map_calls = []
            self.dock_calls = []

        def set_map(self, pixmap, resolution, origin):
            self.map_calls.append((pixmap, resolution, origin))

        def set_charging_docks(self, docks):
            self.dock_calls.append(docks)

    monkeypatch.setattr("dog_remote_tool.ui.pages.navigation.map_preview.QPixmap", _FakePixmap)
    monkeypatch.setattr(
        "dog_remote_tool.ui.pages.navigation.map_preview.read_map_yaml_metadata",
        lambda _path: (0.05, (0.0, 0.0, 0.0)),
    )

    page = _FakeNavigationRefreshPage(selected_map=new_remote)
    page.map_preview_slot = _FakeSlot(output="")
    page.fetching_preview_remote_pgm = old_remote
    page.preview_remote_pgm = ""
    page.open_workspace_after_preview = False
    page.nav_map = _FakeNavMap()
    page.nav_status_note = _FakeLabel()
    page.update_target_hint = lambda: None
    page.update_nav_map_points = lambda: None

    NavigationPage.map_preview_finished(page, page.map_preview_slot.process, exit_code=0, local_dir=tmp_path, request_id=15)

    assert page.preview_calls == 1
    assert page.nav_map.map_calls == []
    assert page.nav_map.dock_calls == []


def test_navigation_map_label_rejects_obstacle_and_unknown_pixels():
    app = QApplication.instance() or QApplication([])
    label = NavigationMapLabel()
    label.setFixedSize(120, 90)
    pixmap = QPixmap(30, 30)
    pixmap.fill(QColor(205, 205, 205))
    painter = QPainter(pixmap)
    painter.fillRect(0, 0, 30, 10, QColor(255, 255, 255))
    painter.fillRect(0, 20, 30, 10, QColor(0, 0, 0))
    painter.end()
    label.set_map(pixmap, 1.0, (0.0, 0.0, 0.0))
    label.show()
    app.processEvents()
    clicked = []
    rejected = []
    label.point_clicked.connect(lambda x, y: clicked.append((x, y)))
    label.point_rejected.connect(rejected.append)

    QTest.mouseClick(label, Qt.LeftButton, Qt.NoModifier, QPoint(60, 17))
    QTest.mouseClick(label, Qt.LeftButton, Qt.NoModifier, QPoint(60, 45))
    QTest.mouseClick(label, Qt.LeftButton, Qt.NoModifier, QPoint(60, 73))

    assert len(clicked) == 1
    assert rejected == [
        "目标点未添加：点击位置在未知/不可通行区域",
        "目标点未添加：点击位置在障碍区",
    ]


def test_navigation_map_label_mouse_wheel_zooms_without_adding_point():
    _ = QApplication.instance() or QApplication([])
    label = NavigationMapLabel()
    label.setFixedSize(120, 90)
    pixmap = QPixmap(30, 30)
    pixmap.fill(QColor(255, 255, 255))
    label.set_map(pixmap, 1.0, (0.0, 0.0, 0.0))
    clicked = []
    label.point_clicked.connect(lambda x, y: clicked.append((x, y)))

    class _Delta:
        def y(self):
            return 120

    class _Wheel:
        accepted = False

        def angleDelta(self):
            return _Delta()

        def pos(self):
            return QPoint(60, 45)

        def accept(self):
            self.accepted = True

    event = _Wheel()
    label.wheelEvent(event)

    assert event.accepted is True
    assert label.zoom_scale > 1.0
    assert clicked == []


def test_navigation_map_label_right_click_requests_nearest_point_delete():
    app = QApplication.instance() or QApplication([])
    label = NavigationMapLabel()
    label.setFixedSize(120, 90)
    pixmap = QPixmap(30, 30)
    pixmap.fill(QColor(255, 255, 255))
    label.set_map(pixmap, 1.0, (0.0, 0.0, 0.0))
    label.set_points([(15.0, 15.0, 0.0), (25.0, 25.0, 0.0)])
    label.show()
    app.processEvents()
    deleted = []
    clicked = []
    label.point_delete_requested.connect(deleted.append)
    label.point_clicked.connect(lambda x, y: clicked.append((x, y)))

    QTest.mouseClick(label, Qt.RightButton, Qt.NoModifier, QPoint(60, 45))

    assert deleted == [0]
    assert clicked == []


def test_navigation_map_label_shift_drag_pans_without_adding_point():
    _ = QApplication.instance() or QApplication([])
    label = NavigationMapLabel()
    label.setFixedSize(120, 90)
    pixmap = QPixmap(30, 30)
    pixmap.fill(QColor(255, 255, 255))
    label.set_map(pixmap, 1.0, (0.0, 0.0, 0.0))
    label.zoom_scale = 2.0
    label.view_center_px = (15.0, 15.0)
    clicked = []
    label.point_clicked.connect(lambda x, y: clicked.append((x, y)))

    class _Mouse:
        def __init__(self, button, modifiers, point):
            self._button = button
            self._modifiers = modifiers
            self._point = point
            self.accepted = False

        def button(self):
            return self._button

        def modifiers(self):
            return self._modifiers

        def pos(self):
            return self._point

        def accept(self):
            self.accepted = True

    press = _Mouse(Qt.LeftButton, Qt.ShiftModifier, QPoint(60, 45))
    move = _Mouse(Qt.NoButton, Qt.ShiftModifier, QPoint(72, 45))
    release = _Mouse(Qt.LeftButton, Qt.ShiftModifier, QPoint(72, 45))

    label.mousePressEvent(press)
    label.mouseMoveEvent(move)
    label.mouseReleaseEvent(release)

    assert press.accepted is True
    assert move.accepted is True
    assert release.accepted is True
    assert clicked == []
    assert label.view_center_px[0] < 15.0


def test_navigation_map_label_rejects_inflated_safety_area(tmp_path):
    app = QApplication.instance() or QApplication([])
    image = tmp_path / "map.pgm"
    image.write_bytes(b"P5\n7 7\n255\n" + bytes([255] * 24 + [0] + [255] * 24))
    yaml_path = tmp_path / "map.yaml"
    yaml_path.write_text(
        "image: map.pgm\nresolution: 1.0\norigin: [0, 0, 0]\noccupied_thresh: 0.65\nfree_thresh: 0.196\nnegate: 0\n",
        encoding="utf-8",
    )
    overlay = create_inflation_overlay(route_network.read_map_yaml(yaml_path), radius_m=2.0)
    assert overlay is not None
    label = NavigationMapLabel()
    label.setFixedSize(70, 70)
    label.set_map(QPixmap(str(image)), 1.0, (0.0, 0.0, 0.0))
    label.set_safety_overlay(overlay)
    label.show()
    app.processEvents()

    assert label.safety_status_at_world(3.0, 4.0) == "blocked"
    assert label.safety_status_at_world(3.0, 2.0) == "inflated"
    assert label.safety_status_at_world(0.0, 1.0) == "free"


def test_navigation_single_goal_rejects_inflated_manual_target(monkeypatch):
    _ = QApplication.instance() or QApplication([])
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda _parent, title, text: messages.append((title, text)))
    page = _FakeNavigationActionPage()
    page.route_target_mode = False
    page.navigation_points = lambda: NavigationPage.navigation_points(page)
    unsafe_pixmap = QPixmap(1, 1)
    unsafe_pixmap.fill(QColor("white"))
    page.nav_map = type(
        "UnsafeMap",
        (),
        {"source_pixmap": unsafe_pixmap, "safety_status_at_world": lambda self, _x, _y: "inflated"},
    )()

    assert NavigationPage.make_start_goal(page) is False

    assert page.runs == []
    assert page.nav_status_note.text == "单点导航未下发：第 1 个目标点在障碍/未知膨胀区内"
    assert messages and messages[0][0] == "目标点不可用"


def test_navigation_multipoint_rejects_blocked_point_before_send(monkeypatch):
    _ = QApplication.instance() or QApplication([])
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda _parent, title, text: messages.append((title, text)))
    page = _FakeNavigationActionPage()
    page.route_target_mode = False
    page.navigation_points = lambda: NavigationPage.navigation_points(page)
    unsafe_pixmap = QPixmap(1, 1)
    unsafe_pixmap.fill(QColor("white"))

    def status_at_world(_self, x, _y):
        return "blocked" if x > 2.0 else "free"

    page.nav_map = type("UnsafeMap", (), {"source_pixmap": unsafe_pixmap, "safety_status_at_world": status_at_world})()

    assert NavigationPage.make_start_multipoint(page) is False

    assert page.runs == []
    assert page.nav_status_note.text == "多点导航未下发：第 2 个目标点在障碍区内"
    assert messages and "第 2 个目标点" in messages[0][1]


def test_undo_last_added_navigation_point_removes_only_recorded_line():
    class Page:
        def __init__(self):
            self.waypoints_text = _FakeWaypointText("1.000,2.000,0.000\n3.000,4.000,0.300")
            self.added_waypoint_undo_stack = [(1, "3.000,4.000,0.300", None)]
            self.last_added_waypoint_undo = None
            self.goal_x = _FakeSpin()
            self.goal_y = _FakeSpin()
            self.goal_yaw = _FakeSpin()
            self.goal_point_selected = True
            self.nav_status_note = _FakeLabel()
            self.nav_map = _FakeWorkspaceCanvas()
            self.workspace_dialog = None
            self.workspace_refreshes = 0

        def refresh_workspace_from_page(self):
            self.workspace_refreshes += 1

    page = Page()

    assert NavigationPage.undo_last_added_navigation_point(page) is True
    assert page.waypoints_text.toPlainText() == "1.000,2.000,0.000"
    assert page.added_waypoint_undo_stack == []
    assert page.nav_map.points[-1] == [(1.0, 2.0, 0.0)]
    assert "已撤销新增目标点" in page.nav_status_note.text

    assert NavigationPage.undo_last_added_navigation_point(page) is False
    assert page.waypoints_text.toPlainText() == "1.000,2.000,0.000"
    assert page.nav_status_note.text == "没有可撤销的新增目标点"


def test_navigation_map_preview_finished_sets_charging_dock_overlay(monkeypatch, tmp_path):
    remote = "/opt/data/.robot/map/history_map/with_arc/map.pgm"
    (tmp_path / "map.yaml").write_text(
        "image: map.pgm\nresolution: 0.05\norigin: [0, 0, 0]\n"
        "arc_position_flag: 1\narc: [{tag_id: 7, arc_position: [2.5, 1.0, -0.2]}]\n",
        encoding="utf-8",
    )

    class _FakePixmap:
        def __init__(self, _path):
            pass

        def isNull(self):
            return False

    class _FakeNavMap(_FakeText):
        def __init__(self):
            super().__init__()
            self.map_calls = []
            self.dock_calls = []

        def set_map(self, pixmap, resolution, origin):
            self.map_calls.append((pixmap, resolution, origin))

        def set_charging_docks(self, docks):
            self.dock_calls.append(docks)

    monkeypatch.setattr("dog_remote_tool.ui.pages.navigation.map_preview.QPixmap", _FakePixmap)

    page = _FakeNavigationRefreshPage(selected_map=remote)
    page.map_preview_slot = _FakeSlot(output="")
    page.fetching_preview_remote_pgm = remote
    page.preview_remote_pgm = ""
    page.open_workspace_after_preview = False
    page.nav_map = _FakeNavMap()
    page.nav_status_note = _FakeLabel()
    page.update_target_hint = lambda: None
    page.update_nav_map_points = lambda: None

    NavigationPage.map_preview_finished(page, page.map_preview_slot.process, exit_code=0, local_dir=tmp_path, request_id=16)

    assert page.charging_docks == [(7, 2.5, 1.0, -0.2)]
    assert page.nav_map.dock_calls == [[(7, 2.5, 1.0, -0.2)]]
    assert "已显示 1 个充电桩标记" in page.nav_status_note.text


def test_navigation_history_card_opens_workspace_before_preview_load():
    remote = "/opt/data/.robot/map/history_map/2026_06_02/map.pgm"

    class _NoPixmap:
        source_pixmap = None

    class _ImmediatePage:
        def __init__(self):
            self.map_selector = _FakeMapSelector(remote)
            self.nav_map = _NoPixmap()
            self.preview_remote_pgm = ""
            self.events = []

        def select_history_map(self, remote_pgm):
            return NavigationPage.select_history_map(self, remote_pgm)

        def on_map_selection_changed(self):
            self.events.append("select")

        def open_navigation_workspace(self):
            self.events.append("open")
            return True

        def fetch_navigation_map_preview(self):
            self.events.append("fetch")
            return True

        def refresh_route_file_state(self, remote_pgm):
            self.events.append("route")
            return True

    page = _ImmediatePage()

    assert NavigationPage.open_history_map_workspace(page, remote) is True
    assert page.events == ["select", "open"]


def test_navigation_history_card_switches_to_each_clicked_map_without_stale_preview():
    old_remote = "/opt/data/.robot/map/history_map/old/map.pgm"
    new_remote = "/opt/data/.robot/map/history_map/new/map.pgm"

    class _LoadedPixmap:
        def isNull(self):
            return False

    class _PreviewMap(_FakeText):
        def __init__(self):
            super().__init__()
            self.source_pixmap = _LoadedPixmap()
            self.clear_calls = []
            self.dock_calls = []

        def clear_map(self, text):
            self.clear_calls.append(text)
            self.source_pixmap = None
            self.setText(text)

        def set_charging_docks(self, docks):
            self.dock_calls.append(docks)

        def setToolTip(self, tooltip):
            self.tooltip = tooltip

    page = _FakeNavigationRefreshPage(selected_map=old_remote)
    page.map_selector.addItem("new", new_remote)
    page.nav_map = _PreviewMap()
    page.preview_remote_pgm = old_remote
    page.charging_docks = [(7, 1.0, 2.0, 0.0)]
    page.preview_requests = []
    page.open_calls = []
    page.select_history_map = lambda remote: NavigationPage.select_history_map(page, remote)
    page.on_map_selection_changed = lambda: NavigationPage.on_map_selection_changed(page)
    page.fetch_navigation_map_preview = lambda: page.preview_requests.append(page.selected_map_pgm()) or True
    page.open_navigation_workspace = lambda: page.open_calls.append(page.selected_map_pgm()) or True

    assert NavigationPage.open_history_map_workspace(page, new_remote) is True

    assert page.selected_map_pgm() == new_remote
    assert page.map_pcd_path.text() == "/opt/data/.robot/map/history_map/new/map.pcd"
    assert page.route_geojson_path.text() == "/opt/data/.robot/map/history_map/new/map.geojson"
    assert page.preview_requests == [new_remote]
    assert page.open_calls == [new_remote]
    assert page.nav_map.clear_calls == ["正在加载地图预览"]
    assert page.nav_map.source_pixmap is None
    assert page.preview_remote_pgm == ""
    assert page.charging_docks == []
    assert page.map_prepare_slot.start_calls
    assert "/opt/data/.robot/map/history_map/new/map.pcd" in page.map_prepare_slot.start_calls[-1]


def test_navigation_route_action_label_follows_route_file_state(tmp_path):
    remote = "/opt/data/.robot/map/history_map/2026_06_02/map.pgm"

    class _RouteActionPage:
        def __init__(self):
            self.route_check_slot = _FakeSlot()
            self.route_check_remote_pgm = ""
            self.route_file_states = {}
            self.refreshes = 0

        def selected_map_pgm(self):
            return remote

        def local_preview_dir(self, _remote):
            return tmp_path

        def refresh_workspace_from_page(self):
            self.refreshes += 1

    page = _RouteActionPage()

    assert NavigationPage.route_action_label(page) == "检查路网"

    page.route_check_slot = _FakeSlot(output="ROUTE_FILE_OK=1\n")
    assert NavigationPage.route_check_finished(page, page.route_check_slot.process, 0, remote, 1) is True
    assert NavigationPage.route_action_label(page) == "编辑路网"

    page.route_file_states[remote] = False
    assert NavigationPage.route_action_label(page) == "新建路网"

    (tmp_path / "map.geojson").write_text("{}", encoding="utf-8")
    assert NavigationPage.route_action_label(page) == "编辑路网"


def test_navigation_route_goal_requires_remote_route_when_local_file_exists(tmp_path):
    remote = "/opt/data/.robot/map/history_map/2026_06_02/map.pgm"
    (tmp_path / "map.geojson").write_text("{}", encoding="utf-8")

    class _RouteReadyPage:
        def __init__(self):
            self.route_file_states = {remote: False}

        def selected_map_pgm(self):
            return remote

        def local_preview_dir(self, _remote):
            return tmp_path

    page = _RouteReadyPage()

    ready, reason = NavigationPage.route_navigation_ready_reason(page)

    assert ready is False
    assert "上传路网" in reason


def test_navigation_upload_route_uses_selected_history_map_geojson(tmp_path):
    remote = "/opt/data/.robot/map/history_map/2026_06_02/map.pgm"
    local_route = tmp_path / "map.geojson"
    local_route.write_text("{}", encoding="utf-8")

    class _UploadRoutePage:
        def __init__(self):
            self.route_geojson_path = _FakeText(route_network.DEFAULT_REMOTE_ROUTE_FILE)
            self.nav_status_note = _FakeLabel()
            self.last_status_values = {}
            self.workspace_refreshes = 0
            self.navigation_log_lines = []
            self.route_file_states = {remote: False}
            self.runs = []

        def selected_map_pgm(self):
            return remote

        def local_preview_dir(self, _remote):
            return tmp_path

        def profile(self):
            return get_product("xg2_s100")

        def run_route_file_spec(self, spec, operation):
            self.runs.append((spec, operation))
            return True

        def refresh_workspace_from_page(self):
            self.workspace_refreshes += 1

    page = _UploadRoutePage()

    assert NavigationPage.upload_selected_route_geojson(page, str(local_route)) is True

    spec, operation = page.runs[-1]
    assert operation == "上传路网中"
    assert spec.title == "上传路网 GeoJSON"
    assert str(local_route) in spec.command
    assert "/opt/data/.robot/map/history_map/2026_06_02/map.geojson" in spec.command
    assert page.route_geojson_path.text() == "/opt/data/.robot/map/history_map/2026_06_02/map.geojson"


def test_navigation_upload_route_cancelled_when_remote_route_exists(tmp_path, monkeypatch):
    remote = "/opt/data/.robot/map/history_map/2026_06_02/map.pgm"
    local_route = tmp_path / "map.geojson"
    local_route.write_text("{}", encoding="utf-8")

    class _UploadRoutePage:
        def __init__(self):
            self.route_file_states = {remote: True}
            self.route_geojson_path = _FakeText(route_network.DEFAULT_REMOTE_ROUTE_FILE)
            self.nav_status_note = _FakeLabel()
            self.workspace_refreshes = 0
            self.navigation_log_lines = []
            self.runs = []

        def selected_map_pgm(self):
            return remote

        def local_preview_dir(self, _remote):
            return tmp_path

        def run_route_file_spec(self, spec, operation):
            self.runs.append((spec, operation))
            return True

        def refresh_workspace_from_page(self):
            self.workspace_refreshes += 1

    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.No)
    page = _UploadRoutePage()

    assert NavigationPage.upload_selected_route_geojson(page, str(local_route)) is False

    assert page.runs == []
    assert page.nav_status_note.text == "已取消上传，远端路网未替换"
    assert page.workspace_refreshes == 2


def test_navigation_upload_route_checks_remote_state_before_unknown_upload(tmp_path):
    remote = "/opt/data/.robot/map/history_map/2026_06_02/map.pgm"
    local_route = tmp_path / "map.geojson"
    local_route.write_text("{}", encoding="utf-8")

    class _UploadRoutePage:
        def __init__(self):
            self.route_file_states = {}
            self.route_geojson_path = _FakeText(route_network.DEFAULT_REMOTE_ROUTE_FILE)
            self.nav_status_note = _FakeLabel()
            self.workspace_refreshes = 0
            self.navigation_log_lines = []
            self.checks = []
            self.runs = []

        def selected_map_pgm(self):
            return remote

        def local_preview_dir(self, _remote):
            return tmp_path

        def refresh_route_file_state(self, remote_pgm):
            self.checks.append(remote_pgm)
            return True

        def run_route_file_spec(self, spec, operation):
            self.runs.append((spec, operation))
            return True

        def refresh_workspace_from_page(self):
            self.workspace_refreshes += 1

    page = _UploadRoutePage()

    assert NavigationPage.upload_selected_route_geojson(page, str(local_route)) is False

    assert page.checks == [remote]
    assert page.runs == []
    assert page.nav_status_note.text == "已选择本地路网，正在检查远端是否已有 map.geojson，检查完成后再上传"


def test_navigation_upload_route_sends_map_files_when_local_map_exists(tmp_path, monkeypatch):
    remote = "/opt/data/.robot/map/history_map/2026_06_02/map.pgm"
    for name in ("map.pgm", "map.yaml", "map.geojson"):
        (tmp_path / name).write_text("data", encoding="utf-8")

    class _UploadRoutePage:
        def __init__(self):
            self.route_file_states = {remote: True}
            self.route_geojson_path = _FakeText(route_network.DEFAULT_REMOTE_ROUTE_FILE)
            self.nav_status_note = _FakeLabel()
            self.workspace_refreshes = 0
            self.navigation_log_lines = []
            self.runs = []

        def selected_map_pgm(self):
            return remote

        def local_preview_dir(self, _remote):
            return tmp_path

        def profile(self):
            return get_product("xg2_s100")

        def run_route_file_spec(self, spec, operation):
            self.runs.append((spec, operation))
            return True

        def refresh_workspace_from_page(self):
            self.workspace_refreshes += 1

    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)
    page = _UploadRoutePage()

    assert NavigationPage.upload_selected_route_geojson(page, str(tmp_path / "map.geojson")) is True

    spec, operation = page.runs[-1]
    assert operation == "上传路网中"
    assert spec.title == "上传地图和路网文件"
    assert str(tmp_path / "map.pgm") in spec.command
    assert str(tmp_path / "map.yaml") in spec.command
    assert str(tmp_path / "map.geojson") in spec.command
    assert "/opt/data/.robot/map/history_map/2026_06_02/map.geojson" in spec.command


def test_navigation_upload_route_copies_selected_external_geojson_to_history_cache(tmp_path):
    remote = "/opt/data/.robot/map/history_map/2026_06_02/map.pgm"
    cache_dir = tmp_path / "cache"
    source = tmp_path / "external.geojson"
    source.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")

    class _UploadRoutePage:
        def __init__(self):
            self.route_geojson_path = _FakeText(route_network.DEFAULT_REMOTE_ROUTE_FILE)
            self.nav_status_note = _FakeLabel()
            self.last_status_values = {}
            self.workspace_refreshes = 0
            self.navigation_log_lines = []
            self.route_file_states = {remote: False}
            self.runs = []

        def selected_map_pgm(self):
            return remote

        def local_preview_dir(self, _remote):
            return cache_dir

        def profile(self):
            return get_product("xg2_s100")

        def run_route_file_spec(self, spec, operation):
            self.runs.append((spec, operation))
            return True

        def refresh_workspace_from_page(self):
            self.workspace_refreshes += 1

    page = _UploadRoutePage()

    assert NavigationPage.upload_selected_route_geojson(page, str(source)) is True

    cached_route = cache_dir / "map.geojson"
    assert cached_route.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")
    spec, _operation = page.runs[-1]
    assert str(cached_route) in spec.command


def test_navigation_workspace_route_check_button_stays_clickable():
    class _Page:
        def route_action_label(self):
            return "检查路网"

    dialog = NavigationWorkspaceDialog.__new__(NavigationWorkspaceDialog)
    dialog.page = _Page()
    dialog.route_button = _FakeButton()

    NavigationWorkspaceDialog.update_route_button(dialog)

    assert dialog.route_button.text == "检查路网"
    assert dialog.route_button.enabled is True
    assert "map.geojson" in dialog.route_button.tooltip
