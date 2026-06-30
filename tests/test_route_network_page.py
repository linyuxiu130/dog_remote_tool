import inspect
import os
import subprocess
import sys
from pathlib import Path

from PyQt5.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt5.QtGui import QColor, QMouseEvent, QPixmap
from PyQt5.QtWidgets import QApplication, QMessageBox

from dog_remote_tool.core.profiles import get_product
from dog_remote_tool.core.shell import CommandSpec
from dog_remote_tool.modules.navigation import route_network
from dog_remote_tool.modules.navigation.route_network import (
    MapMetadata,
    RouteEdge,
    RouteGraph,
    RouteNode,
    ValidationIssue,
    analyze_geojson_file,
    route_geojson_for_remote_map,
)
from helpers import FakeSignal as _FakeSignal, FakeRunner as _FakeRunner
from dog_remote_tool.ui.pages.route_network import map_history as route_network_map_history
from dog_remote_tool.ui.pages.route_network import actions as route_network_actions
from dog_remote_tool.ui.pages.route_network import inflation as route_network_inflation
from dog_remote_tool.ui.pages.route_network import inspector_panel as route_network_inspector_panel
from dog_remote_tool.ui.pages.route_network import layout as route_network_layout
from dog_remote_tool.ui.pages.route_network import page as route_network_page_module
from dog_remote_tool.ui.pages.route_network import scale_status as route_network_scale_status
from dog_remote_tool.ui.pages.route_network import state as route_network_state
from dog_remote_tool.ui.pages.route_network import state_helpers as route_network_state_helpers
from dog_remote_tool.ui.pages.route_network import map_history_card as route_network_map_history_card
from dog_remote_tool.ui.pages.route_network import map_history_cards as route_network_map_history_cards
from dog_remote_tool.ui.pages.route_network import map_history_fetch as route_network_map_history_fetch
from dog_remote_tool.ui.pages.route_network import map_history_selection as route_network_map_history_selection
from dog_remote_tool.ui.pages.route_network import map_history_sync as route_network_map_history_sync
from dog_remote_tool.ui.pages.route_network import map_history_thumbnails as route_network_map_history_thumbnails
from dog_remote_tool.ui.pages.route_network.page import RouteMapHistoryCard, RouteNetworkPage
from dog_remote_tool.ui import route_editor_history
from dog_remote_tool.ui import route_editor_layout
from dog_remote_tool.ui import route_editor_pose
from dog_remote_tool.ui import route_editor_properties
from dog_remote_tool.ui import route_editor_side_panel
from dog_remote_tool.ui import route_editor_tools
from dog_remote_tool.ui import route_editor_validation
from dog_remote_tool.ui import route_map_canvas as route_map_canvas_module
from dog_remote_tool.ui import route_map_canvas_drawing
from dog_remote_tool.ui import route_map_canvas_edge_rendering
from dog_remote_tool.ui import route_map_canvas_editing
from dog_remote_tool.ui import route_map_canvas_events
from dog_remote_tool.ui import route_map_canvas_geometry
from dog_remote_tool.ui import route_map_canvas_history
from dog_remote_tool.ui import route_map_canvas_node_marker
from dog_remote_tool.ui import route_map_canvas_painting
from dog_remote_tool.ui import route_map_canvas_robot_marker
from dog_remote_tool.ui import route_map_canvas_state
from dog_remote_tool.ui import route_map_canvas_view
from dog_remote_tool.ui.route_inflation_overlay import DEFAULT_ROUTE_INFLATION_RADIUS_M, create_inflation_overlay
from dog_remote_tool.ui.route_editor_dialog import RouteEditorDialog
from dog_remote_tool.ui.route_map_canvas import RouteMapCanvas
from dog_remote_tool.ui import route_editor_export


_QT_APP = None


def _app():
    global _QT_APP
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    _QT_APP = app
    return app


def _scaled_canvas() -> RouteMapCanvas:
    app = _app()
    canvas = RouteMapCanvas()
    canvas.resize(500, 250)
    pixmap = QPixmap(2000, 1000)
    pixmap.fill(QColor("white"))
    canvas.set_map(pixmap, MapMetadata(Path("/tmp/map.png"), 0.05, (0.0, 0.0, 0.0)))
    canvas.show()
    app.processEvents()
    return canvas


class _FakeStyle:
    def __init__(self):
        self.unpolished = 0
        self.polished = 0

    def unpolish(self, _widget):
        self.unpolished += 1

    def polish(self, _widget):
        self.polished += 1


class _FakeStatusLabel:
    def __init__(self):
        self.text = ""
        self.object_name = ""
        self.tooltip = ""
        self.style_obj = _FakeStyle()

    def setText(self, text):
        self.text = text

    def setObjectName(self, name):
        self.object_name = name

    def setToolTip(self, tooltip):
        self.tooltip = tooltip

    def style(self):
        return self.style_obj


def test_route_network_set_status_uses_route_status_roles():
    page = type("FakePage", (), {"status_label": _FakeStatusLabel()})()

    RouteNetworkPage.set_status(page, "校验通过", "success")

    assert page.status_label.text == "校验通过"
    assert page.status_label.object_name == "RouteStatusSuccess"
    assert page.status_label.style_obj.unpolished == 1
    assert page.status_label.style_obj.polished == 1


def test_route_inflation_default_matches_remote_collision_radius():
    assert DEFAULT_ROUTE_INFLATION_RADIUS_M == 0.55


def test_route_network_inflation_uses_default_until_remote_radius_syncs(monkeypatch):
    calls = []

    class Overlay:
        pixmap = "overlay"
        label = "障碍/未知膨胀 0.55m"

    def fake_overlay(metadata, radius_m=None):
        calls.append((metadata, radius_m))
        return Overlay()

    page = RouteNetworkPage.__new__(RouteNetworkPage)
    page.inflation_radius_m = None
    monkeypatch.setattr(route_network_page_module, "create_inflation_overlay", fake_overlay)

    assert RouteNetworkPage.effective_inflation_radius_m(page) == DEFAULT_ROUTE_INFLATION_RADIUS_M
    assert RouteNetworkPage.create_current_inflation_overlay(page, "metadata") is not None
    assert calls == [("metadata", DEFAULT_ROUTE_INFLATION_RADIUS_M)]

    page.inflation_radius_m = 0.2
    RouteNetworkPage.create_current_inflation_overlay(page, "metadata")

    assert calls[-1] == ("metadata", 0.2)


def test_route_network_ui_exposes_current_inflation_radius_labels():
    page_source = inspect.getsource(RouteNetworkPage._make_info_strip) + inspect.getsource(RouteNetworkPage.update_inflation_info)
    editor_source = inspect.getsource(RouteEditorDialog._make_header) + inspect.getsource(RouteEditorDialog.refresh_inflation_label)

    assert "self.inflation_state_label" in page_source
    assert "路网编辑障碍显示使用当前碰撞半径" in page_source
    assert "膨胀：未读取" in page_source
    assert '"回中"' not in inspect.getsource(RouteNetworkPage._make_info_strip)
    assert "self.inflation_label" in editor_source
    assert "可在导航页的导航参数中修改碰撞半径" in editor_source
    assert "膨胀：未读取" in editor_source


def test_route_editor_opens_fullscreen_not_just_maximized():
    source = inspect.getsource(route_network_state.RouteNetworkStateMixin.open_route_editor)

    assert "dialog.showFullScreen()" in source
    assert "dialog.showMaximized()" not in source


def test_route_editor_manual_coordinate_box_is_visible_above_tabs():
    source = inspect.getsource(route_editor_side_panel.RouteEditorSidePanelMixin._make_side_panel)

    assert "layout.addWidget(self._make_manual_coordinate_box())" in source
    assert source.index("layout.addWidget(self._make_manual_coordinate_box())") < source.index("tabs = QTabWidget()")


def test_route_editor_removes_geojson_analysis_ui():
    source = inspect.getsource(route_editor_side_panel.RouteEditorSidePanelMixin._make_side_panel)

    assert "GeoJSON 分析" not in source
    assert "Feature 定位" not in source
    assert "analysis_table" not in source
    assert not hasattr(RouteEditorDialog, "refresh_analysis")
    assert not hasattr(RouteEditorDialog, "locate_feature")


def test_route_editor_removes_manual_path_check_ui():
    source = inspect.getsource(route_editor_side_panel.RouteEditorSidePanelMixin._make_side_panel)

    assert "路径检查" not in source
    assert "editor_start_node" not in source
    assert "editor_goal_node" not in source
    assert not hasattr(RouteEditorDialog, "use_selected_node")
    assert not hasattr(RouteEditorDialog, "preview_path")


def test_route_editor_dialog_is_independent_top_level_window():
    source = inspect.getsource(RouteEditorDialog.__init__)

    assert "super().__init__(None)" in source
    assert "setWindowFlag(Qt.Window, True)" in source
    assert "setModal(True)" in source
    assert "self.page = page" in source


def test_route_editor_canvas_exists_before_toolbar_uses_width_setting():
    source = inspect.getsource(RouteEditorDialog.__init__)

    assert source.index("self.canvas = RouteMapCanvas()") < source.index("self.toolbar = self._make_toolbar()")


def test_route_editor_open_raises_fullscreen_dialog():
    source = inspect.getsource(RouteNetworkPage.open_route_editor)

    assert "showFullScreen()" in source
    assert "raise_()" in source
    assert "activateWindow()" in source


def test_route_network_inflation_radius_updates_canvas_and_open_editor(monkeypatch):
    calls = []

    class Overlay:
        pixmap = "overlay-pixmap"
        label = "膨胀：0.20 m"

    class FakeCanvas:
        def __init__(self):
            self.inflation_overlay = None
            self.inflation_overlay_label = ""

        def set_inflation_overlay(self, pixmap, label):
            self.inflation_overlay = pixmap
            self.inflation_overlay_label = label

    class FakeEditor:
        def __init__(self):
            self.canvas = FakeCanvas()
            self.refreshed = 0

        def refresh_inflation_label(self):
            self.refreshed += 1

    def fake_overlay(metadata, radius_m=None):
        calls.append((metadata, radius_m))
        return Overlay()

    page = RouteNetworkPage.__new__(RouteNetworkPage)
    page.map_metadata = object()
    page.canvas = FakeCanvas()
    page.inflation_radius_m = None
    page.inflation_state_label = _FakeStatusLabel()
    page.active_editor_dialog = FakeEditor()
    monkeypatch.setattr(route_network_page_module, "create_inflation_overlay", fake_overlay)

    updated = RouteNetworkPage.set_inflation_radius_m(page, 0.2)

    assert updated is True
    assert calls == [(page.map_metadata, 0.2)]
    assert page.canvas.inflation_overlay == "overlay-pixmap"
    assert page.canvas.inflation_overlay_label == "膨胀：0.20 m"
    assert page.inflation_state_label.text == "膨胀：0.20 m"
    assert page.active_editor_dialog.canvas.inflation_overlay == "overlay-pixmap"
    assert page.active_editor_dialog.canvas.inflation_overlay_label == "膨胀：0.20 m"
    assert page.active_editor_dialog.refreshed == 1


def test_scaled_canvas_hit_testing_uses_screen_sized_node_target():
    canvas = _scaled_canvas()
    canvas.graph.nodes[1] = RouteNode(1, 20.0, 20.0)
    node_point = canvas._world_to_widget(20.0, 20.0).toPoint()
    click_world = canvas._widget_to_world(node_point + QPoint(8, 0))

    assert click_world is not None
    assert canvas._hit_test(*click_world) == ("node", 1)


def test_scaled_canvas_delete_can_hit_edge_near_visible_line():
    canvas = _scaled_canvas()
    canvas.graph.nodes[1] = RouteNode(1, 10.0, 10.0)
    canvas.graph.nodes[2] = RouteNode(2, 50.0, 10.0)
    canvas.graph.edges[1] = RouteEdge(1, 1, 2, [(10.0, 10.0), (50.0, 10.0)])
    mid_point = canvas._world_to_widget(30.0, 10.0).toPoint()
    click_world = canvas._widget_to_world(mid_point + QPoint(0, 8))

    assert click_world is not None
    assert canvas._hit_test(*click_world) == ("edge", 1)


def test_canvas_zoom_keeps_mouse_world_position():
    canvas = _scaled_canvas()
    point = QPoint(260, 120)
    before = canvas._widget_to_world(point)

    canvas.zoom_at_widget_point(point, 1.8)
    after = canvas._widget_to_world(point)

    assert before is not None
    assert after is not None
    assert canvas.view_zoom > 1.0
    assert abs(before[0] - after[0]) < 1e-6
    assert abs(before[1] - after[1]) < 1e-6

    canvas.reset_view()
    assert canvas.view_zoom == 1.0


def test_canvas_keyboard_zoom_pan_and_reset_without_mouse():
    canvas = _scaled_canvas()

    class KeyEvent:
        def __init__(self, key, modifiers=Qt.NoModifier, auto_repeat=False):
            self._key = key
            self._modifiers = modifiers
            self._auto_repeat = auto_repeat
            self.accepted = False

        def key(self):
            return self._key

        def modifiers(self):
            return self._modifiers

        def isAutoRepeat(self):
            return self._auto_repeat

        def accept(self):
            self.accepted = True

    zoom_event = KeyEvent(Qt.Key_Plus)
    canvas.keyPressEvent(zoom_event)
    assert zoom_event.accepted
    assert canvas.view_zoom > 1.0

    before = canvas._view_center()
    pan_event = KeyEvent(Qt.Key_Right)
    canvas.keyPressEvent(pan_event)
    after = canvas._view_center()
    assert pan_event.accepted
    assert after.x() > before.x()

    reset_event = KeyEvent(Qt.Key_0)
    canvas.keyPressEvent(reset_event)
    assert reset_event.accepted
    assert canvas.view_zoom == 1.0
    assert canvas.view_center_px is None


def test_canvas_keyboard_auto_repeat_keeps_panning_without_mouse():
    canvas = _scaled_canvas()
    canvas.zoom_at_center(2.0)

    class KeyEvent:
        def __init__(self, key, auto_repeat=False):
            self._key = key
            self._auto_repeat = auto_repeat
            self.accepted = False

        def key(self):
            return self._key

        def modifiers(self):
            return Qt.NoModifier

        def isAutoRepeat(self):
            return self._auto_repeat

        def accept(self):
            self.accepted = True

    first = KeyEvent(Qt.Key_D)
    repeat = KeyEvent(Qt.Key_D, auto_repeat=True)
    before = canvas._view_center()
    canvas.keyPressEvent(first)
    middle = canvas._view_center()
    canvas.keyPressEvent(repeat)
    after = canvas._view_center()

    assert first.accepted
    assert repeat.accepted
    assert middle.x() > before.x()
    assert after.x() > middle.x()


def test_canvas_history_can_undo_graph_snapshot():
    canvas = _scaled_canvas()
    canvas.graph.nodes[1] = RouteNode(1, 10.0, 10.0)

    canvas.push_history("新增节点")
    canvas.graph.nodes[2] = RouteNode(2, 20.0, 10.0)

    assert canvas.undo_last_history()
    assert set(canvas.graph.nodes) == {1}
    assert not canvas.history_records


def test_route_edge_tool_adds_blank_points_while_connecting():
    _app()
    canvas = RouteMapCanvas()
    canvas.set_mode("edge")

    canvas._edge_click(1.0, 2.0)

    assert set(canvas.graph.nodes) == {1}
    assert canvas.pending_node_id == 1
    assert not canvas.graph.edges

    canvas._edge_click(3.0, 4.0)

    assert set(canvas.graph.nodes) == {1, 2}
    assert len(canvas.graph.edges) == 1
    edge = canvas.graph.edges[1]
    assert edge.startid == 1
    assert edge.endid == 2
    assert edge.direction == "both"
    assert edge.properties["passable_width"] == route_network.DEFAULT_ROUTE_PASSABLE_WIDTH


def test_route_edge_tool_uses_configured_new_edge_passable_width():
    _app()
    canvas = RouteMapCanvas()
    canvas.set_mode("edge")
    canvas.set_new_edge_passable_width(3.4)

    canvas._edge_click(1.0, 2.0)
    canvas._edge_click(3.0, 4.0)

    edge = canvas.graph.edges[1]
    assert edge.properties["passable_width"] == 3.4


def test_route_canvas_right_click_deletes_hit_node_and_clears_pending_start():
    canvas = _scaled_canvas()
    canvas.editing_enabled = True
    canvas.set_mode("edge")
    canvas.graph.nodes[1] = RouteNode(1, 10.0, 10.0)
    canvas.graph.nodes[2] = RouteNode(2, 20.0, 10.0)
    canvas.graph.edges[1] = RouteEdge(1, 1, 2, [(10.0, 10.0), (20.0, 10.0)])
    canvas.pending_node_id = 1
    widget_point = canvas._world_to_widget(10.0, 10.0)

    event = QMouseEvent(
        QEvent.MouseButtonPress,
        QPointF(widget_point),
        Qt.RightButton,
        Qt.RightButton,
        Qt.NoModifier,
    )
    canvas.mousePressEvent(event)

    assert 1 not in canvas.graph.nodes
    assert not canvas.graph.edges
    assert canvas.pending_node_id is None
    assert event.isAccepted()


def test_route_canvas_highlights_warning_and_error_issues():
    canvas = RouteMapCanvas()

    canvas.set_issues(
        [
            ValidationIssue("warning", "isolated_node", "节点 1 是孤立点", "node", 1),
            ValidationIssue("warning", "tiny_edge", "边 2 长度过短", "edge", 2),
            ValidationIssue("warning", "edge_outside_map", "边 3 超出底图", "edge", 3),
            ValidationIssue("error", "missing_start", "边 3 引用不存在的起点", "edge", 3),
        ]
    )

    assert canvas.issue_targets == {("node", 1), ("edge", 2), ("edge", 3)}
    assert canvas.issue_target_levels[("node", 1)] == "warning"
    assert canvas.issue_target_levels[("edge", 2)] == "warning"
    assert canvas.issue_target_levels[("edge", 3)] == "error"


def test_route_canvas_draws_direction_arrows_from_normalized_edge_direction(monkeypatch):
    canvas = _scaled_canvas()
    canvas.graph.nodes[1] = RouteNode(1, 10.0, 10.0)
    canvas.graph.nodes[2] = RouteNode(2, 50.0, 10.0)
    canvas.graph.edges[1] = RouteEdge(1, 1, 2, [(10.0, 10.0), (50.0, 10.0)], "forward")
    calls = []

    class FakePainter:
        def __init__(self):
            self.line_count = 0

        def setPen(self, *_args):
            pass

        def drawLine(self, *_args):
            self.line_count += 1

    def record_arrow(_painter, _points, _color, reverse=False, **_kwargs):
        calls.append(reverse)

    monkeypatch.setattr(canvas, "_draw_direction_arrow", record_arrow)

    painter = FakePainter()
    canvas._draw_edges(painter)

    assert calls == [False]
    assert painter.line_count == 2

    calls.clear()
    painter = FakePainter()
    canvas.graph.edges[1].direction = "both"
    canvas._draw_edges(painter)

    assert calls == [False, True]
    assert painter.line_count == 2


def test_route_canvas_collapses_duplicate_bidirectional_edges(monkeypatch):
    canvas = _scaled_canvas()
    canvas.graph.nodes[1] = RouteNode(1, 10.0, 10.0)
    canvas.graph.nodes[2] = RouteNode(2, 50.0, 10.0)
    canvas.graph.edges[1] = RouteEdge(1, 1, 2, [(10.0, 10.0), (50.0, 10.0)], "both")
    canvas.graph.edges[2] = RouteEdge(2, 1, 2, [(10.0, 10.0), (50.0, 10.0)], "both")
    calls = []

    class FakePainter:
        def __init__(self):
            self.line_count = 0

        def setPen(self, *_args):
            pass

        def drawLine(self, *_args):
            self.line_count += 1

    def record_arrow(_painter, _points, _color, reverse=False, **_kwargs):
        calls.append(reverse)

    monkeypatch.setattr(canvas, "_draw_direction_arrow", record_arrow)

    painter = FakePainter()
    canvas._draw_edges(painter)

    assert calls == [False, True]
    assert painter.line_count == 2


def test_route_canvas_edge_groups_mark_same_knee_motion_color():
    graph = RouteGraph()
    graph.nodes[1] = RouteNode(1, 0.0, 0.0)
    graph.nodes[2] = RouteNode(2, 1.0, 0.0)
    graph.edges[1] = RouteEdge(1, 1, 2, [(0.0, 0.0), (1.0, 0.0)], "both", properties={"road_class": 3})

    group = route_map_canvas_edge_rendering.visual_edge_groups(graph.edges.values())[0]
    color = route_map_canvas_edge_rendering.route_edge_color_for_directions(group["directions"], group["road_classes"])

    assert group["road_classes"] == {3}
    assert color.name() == route_map_canvas_edge_rendering.ROUTE_EDGE_SAME_KNEE_COLOR


def test_route_canvas_edge_groups_keep_opposite_knee_direction_colors():
    graph = RouteGraph()
    graph.nodes[1] = RouteNode(1, 0.0, 0.0)
    graph.nodes[2] = RouteNode(2, 1.0, 0.0)
    graph.edges[1] = RouteEdge(1, 1, 2, [(0.0, 0.0), (1.0, 0.0)], "both", properties={"road_class": 0})

    group = route_map_canvas_edge_rendering.visual_edge_groups(graph.edges.values())[0]
    color = route_map_canvas_edge_rendering.route_edge_color_for_directions(group["directions"], group["road_classes"])

    assert group["road_classes"] == {0}
    assert color.name() == route_map_canvas_edge_rendering.ROUTE_EDGE_BOTH_COLOR


def test_route_editor_toolbar_merges_add_node_into_edge_tool():
    source = (
        inspect.getsource(RouteEditorDialog.__init__)
        + inspect.getsource(RouteEditorDialog._make_header)
        + inspect.getsource(RouteEditorDialog._make_toolbar)
    )

    assert 'self.current_tool = "edge"' in source
    assert 'self.set_tool("edge")' in source
    assert '"上传远端"' in source
    assert '"保存远端"' not in source
    assert '"保存本地"' not in source
    assert '"加点连线"' in source
    assert '"新边路宽"' in source
    assert "Ctrl+Z 撤销" in source
    assert '"左键加点/连线；右键删除命中的点或边"' in source
    assert '"回到全图"' not in source
    assert '"添加节点"' not in inspect.getsource(RouteEditorDialog._make_toolbar)
    assert '"连接两点"' not in inspect.getsource(RouteEditorDialog._make_toolbar)
    assert '"删除对象"' not in inspect.getsource(RouteEditorDialog._make_toolbar)
    assert '"应用修改"' not in inspect.getsource(RouteEditorDialog._make_side_panel)


def test_route_editor_keyboard_remote_button_starts_stops_and_syncs_state():
    class FakeButton:
        def __init__(self):
            self.text = ""
            self.object_name = ""
            self.style_obj = _FakeStyle()

        def setText(self, text):
            self.text = text

        def setObjectName(self, name):
            self.object_name = name

        def style(self):
            return self.style_obj

    class FakeTimer:
        def __init__(self):
            self.active = False

        def isActive(self):
            return self.active

        def start(self):
            self.active = True

        def stop(self):
            self.active = False

    class FakeControlPage:
        def __init__(self):
            self.running = False
            self.gamepad_stream_ready = False
            self.activated = 0
            self.started = 0
            self.stopped_gamepad = 0
            self.stopped_l1 = 0

        def activate_page(self):
            self.activated += 1

        def keyboard_stream_running(self):
            return self.running

        def profile(self):
            return get_product("zg_lidar_nx")

        def start_gamepad_stream(self):
            self.started += 1
            self.running = True
            return True

        def start_l1_sdk_stream(self):
            raise AssertionError("ZG profile should use gamepad stream")

        def stop_gamepad_stream(self):
            was_running = self.running
            self.stopped_gamepad += 1
            self.running = False
            return was_running

        def stop_l1_sdk_stream(self):
            self.stopped_l1 += 1
            return False

    dialog = RouteEditorDialog.__new__(RouteEditorDialog)
    dialog.keyboard_control_page = FakeControlPage()
    dialog.keyboard_remote_btn = FakeButton()
    dialog.editor_status = _FakeStatusLabel()
    dialog.keyboard_remote_status_timer = FakeTimer()
    dialog.keyboard_remote_state = "off"

    assert RouteEditorDialog.toggle_keyboard_remote(dialog) is True
    assert dialog.keyboard_control_page.activated == 1
    assert dialog.keyboard_control_page.started == 1
    assert dialog.keyboard_remote_btn.text == "停止键盘遥控"
    assert dialog.keyboard_remote_btn.object_name == "Danger"
    assert dialog.keyboard_remote_status_timer.active is True
    assert dialog.editor_status.text.startswith("键盘遥控连接中")

    dialog.keyboard_control_page.gamepad_stream_ready = True
    assert RouteEditorDialog.sync_keyboard_remote_state(dialog) is True
    assert dialog.editor_status.text.startswith("键盘遥控已开启")

    assert RouteEditorDialog.toggle_keyboard_remote(dialog) is True
    assert dialog.keyboard_remote_btn.text == "开始键盘遥控"
    assert dialog.keyboard_remote_btn.object_name == "SoftPrimary"
    assert dialog.keyboard_remote_status_timer.active is False
    assert dialog.editor_status.text == "键盘遥控已停止"


def test_route_editor_save_uploads_when_bound_to_remote_history_map():
    class FakePathEdit:
        def text(self):
            return "/tmp/map.geojson"

    class FakePage:
        def __init__(self):
            self.saved = 0
            self.uploaded = 0
            self.validated = 0
            self.notified = 0
            self.pending_route_upload_task_id = 42
            self.geojson_path = FakePathEdit()

        def save_geojson(self, *, notify_saved=True):
            self.saved += 1
            self.notify_saved = notify_saved
            return True

        def save_routes_remotely_by_default(self):
            return True

        def validate_graph(self, show_message=True):
            self.validated += 1
            return True

        def upload_saved_route(self):
            self.uploaded += 1
            return True

        def notify_route_saved(self):
            self.notified += 1
            return True

    class FakeLabel:
        def __init__(self):
            self.text = ""

        def setText(self, text):
            self.text = text

    dialog = RouteEditorDialog.__new__(RouteEditorDialog)
    dialog.page = FakePage()
    dialog.editor_status = FakeLabel()

    RouteEditorDialog.save_editor_geojson(dialog)

    assert dialog.page.saved == 1
    assert dialog.page.notify_saved is False
    assert dialog.page.validated == 1
    assert dialog.page.notified == 0
    assert dialog.page.uploaded == 1
    assert dialog.pending_remote_save_task_id == 42
    assert dialog.editor_status.text == "远端上传中"


def test_route_editor_save_keeps_local_fallback_without_remote_history_map():
    class FakePage:
        def __init__(self):
            self.saved = 0
            self.uploaded = 0

        def save_geojson(self, *, notify_saved=True):
            self.saved += 1
            self.notify_saved = notify_saved
            return True

        def upload_saved_route(self):
            self.uploaded += 1
            return True

    class FakeLabel:
        def __init__(self):
            self.text = ""

        def setText(self, text):
            self.text = text

    dialog = RouteEditorDialog.__new__(RouteEditorDialog)
    dialog.page = FakePage()
    dialog.editor_status = FakeLabel()

    RouteEditorDialog.save_editor_geojson(dialog)

    assert dialog.page.saved == 0
    assert dialog.page.uploaded == 0
    assert dialog.editor_status.text == "当前未绑定远端历史图，本地路网已自动保存"


def test_route_network_save_geojson_without_notify_marks_preparing_upload(tmp_path):
    class FakePathEdit:
        def __init__(self, path):
            self.path = str(path)

        def text(self):
            return self.path

        def setText(self, value):
            self.path = value

    class FakeCanvas:
        def __init__(self):
            self.graph = RouteGraph()

    class FakePage:
        def __init__(self, path):
            self.geojson_path = FakePathEdit(path)
            self.canvas = FakeCanvas()
            self.statuses = []
            self.notified = 0

        def set_status(self, text, state):
            self.statuses.append((text, state))

        def notify_route_saved(self, path=None):
            self.notified += 1
            return True

    page = FakePage(tmp_path / "map.geojson")

    saved = RouteNetworkPage.save_geojson(page, notify_saved=False)

    assert saved is True
    assert Path(page.geojson_path.text()).exists()
    assert page.statuses == [("准备上传", "warning")]
    assert page.notified == 0


def test_route_editor_graph_change_autosaves_local_geojson():
    class FakePathEdit:
        def text(self):
            return "/tmp/map.geojson"

    class FakePage:
        def __init__(self):
            self.graph = None
            self.saved = 0
            self.notify_saved = None
            self.geojson_path = FakePathEdit()
            self.canvas = type("Canvas", (), {"set_graph": lambda *_args: None})()

        def save_geojson(self, *, notify_saved=True):
            self.saved += 1
            self.notify_saved = notify_saved
            return True

        def update_scale_info(self):
            pass

    class FakeCanvas:
        def __init__(self):
            self.graph = RouteGraph()
            self.updated = 0

        def update(self):
            self.updated += 1

    class FakeLabel:
        def __init__(self):
            self.text = ""

        def setText(self, text):
            self.text = text

    dialog = RouteEditorDialog.__new__(RouteEditorDialog)
    dialog.page = FakePage()
    dialog.canvas = FakeCanvas()
    dialog.editor_status = FakeLabel()
    dialog.refresh_validation_highlights = lambda: None

    RouteEditorDialog.on_graph_changed(dialog)

    assert dialog.page.saved == 1
    assert dialog.page.notify_saved is True
    assert dialog.canvas.updated == 1
    assert dialog.editor_status.text == "已自动保存本地路网"


def test_route_editor_remote_save_validation_failure_does_not_notify_or_upload():
    class FakePathEdit:
        def text(self):
            return "/tmp/map.geojson"

    class FakePage:
        def __init__(self):
            self.saved = 0
            self.uploaded = 0
            self.validated = 0
            self.notified = 0
            self.geojson_path = FakePathEdit()
            self.last_issues = [
                ValidationIssue("error", "endpoint_mismatch", "边 7 几何终点与节点 2 偏差 0.40m", "edge", 7)
            ]

        def save_geojson(self, *, notify_saved=True):
            self.saved += 1
            self.notify_saved = notify_saved
            return True

        def save_routes_remotely_by_default(self):
            return True

        def validate_graph(self, show_message=True):
            self.validated += 1
            return False

        def notify_route_saved(self):
            self.notified += 1
            return True

        def upload_saved_route(self):
            self.uploaded += 1
            return True

    class FakeLabel:
        def __init__(self):
            self.text = ""

        def setText(self, text):
            self.text = text

    dialog = RouteEditorDialog.__new__(RouteEditorDialog)
    dialog.page = FakePage()
    dialog.editor_status = FakeLabel()

    RouteEditorDialog.save_editor_geojson(dialog)

    assert dialog.page.saved == 1
    assert dialog.page.notify_saved is False
    assert dialog.page.validated == 1
    assert dialog.page.notified == 0
    assert dialog.page.uploaded == 0
    assert "边 7 几何终点与节点 2 偏差 0.40m" in dialog.editor_status.text


def test_route_editor_history_row_click_jumps_to_snapshot():
    class FakeCanvas:
        def __init__(self):
            self.rows = []

        def revert_to_history(self, row):
            self.rows.append(row)
            return True

    class FakeLabel:
        def __init__(self):
            self.text = ""

        def setText(self, text):
            self.text = text

    dialog = RouteEditorDialog.__new__(RouteEditorDialog)
    dialog.canvas = FakeCanvas()
    dialog.editor_status = FakeLabel()
    dialog.update_summary = lambda: None
    dialog.validate_graph = lambda: True

    assert RouteEditorDialog.jump_to_history_row(dialog, 2) is True
    assert dialog.canvas.rows == [2]
    assert dialog.editor_status.text == "已跳转到选中历史状态"


def test_route_editor_refresh_validation_highlights_warning_nodes():
    class FakeLabel:
        def __init__(self):
            self.text = ""

        def setText(self, text):
            self.text = text

    class FakeList:
        def __init__(self):
            self.items = []

        def clear(self):
            self.items = []

        def addItem(self, item):
            self.items.append(item)

    dialog = RouteEditorDialog.__new__(RouteEditorDialog)
    _app()
    dialog.canvas = RouteMapCanvas()
    dialog.canvas.graph.nodes[1] = RouteNode(1, 0.0, 0.0)
    page_canvas = RouteMapCanvas()
    dialog.page = type("Page", (), {"last_issues": [], "canvas": page_canvas})()
    dialog.editor_summary = FakeLabel()
    dialog.editor_status = FakeLabel()
    dialog.editor_issue_summary = FakeLabel()
    dialog.editor_issue_list = FakeList()

    assert RouteEditorDialog.refresh_validation_highlights(dialog) is False

    assert ("node", 1) in dialog.canvas.issue_targets
    assert dialog.canvas.issue_target_levels[("node", 1)] == "warning"
    assert "警告" in dialog.editor_status.text


def test_route_page_direction_buttons_store_canonical_values():
    class FakeCanvas:
        def __init__(self):
            self.selected_type = "edge"
            self.selected_id = 1
            self.graph = RouteGraph()
            self.graph.nodes[1] = RouteNode(1, 0.0, 0.0)
            self.graph.nodes[2] = RouteNode(2, 1.0, 0.0)
            self.graph.edges[1] = RouteEdge(1, 1, 2, [(0.0, 0.0), (1.0, 0.0)], 1, 1.0, {"direction": 1})
            self.updates = 0

        def update(self):
            self.updates += 1

    page = RouteNetworkPage.__new__(RouteNetworkPage)
    page._updating_properties = False
    page.canvas = FakeCanvas()

    RouteNetworkPage.apply_direction(page, route_network.ROUTE_DIRECTION_BOTH)

    edge = page.canvas.graph.edges[1]
    assert edge.direction == "both"
    assert edge.properties["direction"] == "both"
    assert edge.is_reverse_allowed()
    assert page.canvas.graph.dirty is True
    assert page.canvas.updates == 1

    RouteNetworkPage.apply_direction(page, route_network.ROUTE_DIRECTION_FORWARD)

    assert edge.direction == "forward"
    assert edge.properties["direction"] == "forward"
    assert not edge.is_reverse_allowed()
    assert page.canvas.updates == 2

    RouteNetworkPage.apply_direction(page, route_network.ROUTE_DIRECTION_FORWARD)

    assert edge.startid == 2
    assert edge.endid == 1
    assert edge.coordinates == [(1.0, 0.0), (0.0, 0.0)]
    assert edge.direction == "forward"
    assert edge.properties["startid"] == 2
    assert edge.properties["endid"] == 1
    assert page.canvas.updates == 3


def test_route_page_road_class_buttons_store_motion_model_class():
    class FakeCanvas:
        def __init__(self):
            self.selected_type = "edge"
            self.selected_id = 1
            self.graph = RouteGraph()
            self.graph.nodes[1] = RouteNode(1, 0.0, 0.0)
            self.graph.nodes[2] = RouteNode(2, 1.0, 0.0)
            self.graph.edges[1] = RouteEdge(1, 1, 2, [(0.0, 0.0), (1.0, 0.0)], "both")
            self.history = []
            self.updates = 0

        def push_history(self, action):
            self.history.append(action)

        def update(self):
            self.updates += 1

    class FakeLabel:
        def __init__(self):
            self.text = ""

        def setText(self, text):
            self.text = text

    page = RouteNetworkPage.__new__(RouteNetworkPage)
    page._updating_properties = False
    page.canvas = FakeCanvas()
    page.object_metric = FakeLabel()
    page.on_graph_changed = lambda: None

    RouteNetworkPage.apply_road_class(page, 3)

    edge = page.canvas.graph.edges[1]
    assert route_network.edge_road_class(edge) == 3
    assert edge.properties["road_class"] == 3
    assert page.canvas.graph.dirty is True
    assert page.canvas.history == ["修改路网运动模式"]
    assert page.canvas.updates == 1
    assert "3 同膝 WALK" in page.object_metric.text


def test_route_editor_direction_button_can_reverse_forward_edge():
    class FakeCanvas:
        def __init__(self):
            self.selected_type = "edge"
            self.selected_id = 1
            self.graph = RouteGraph()
            self.graph.nodes[1] = RouteNode(1, 0.0, 0.0)
            self.graph.nodes[2] = RouteNode(2, 1.0, 0.0)
            self.graph.edges[1] = RouteEdge(1, 1, 2, [(0.0, 0.0), (1.0, 0.0)], "both")
            self.history = []

        def push_history(self, action):
            self.history.append(action)

    class FakeLine:
        def __init__(self):
            self.text = ""

        def setText(self, text):
            self.text = text

    dialog = RouteEditorDialog.__new__(RouteEditorDialog)
    dialog._updating_properties = False
    dialog.canvas = FakeCanvas()
    dialog.editor_edge_start = FakeLine()
    dialog.editor_edge_end = FakeLine()
    dialog.editor_metric = FakeLine()
    dialog.graph_changed = 0
    dialog.on_graph_changed = lambda: setattr(dialog, "graph_changed", dialog.graph_changed + 1)

    RouteEditorDialog.apply_editor_direction(dialog, route_network.ROUTE_DIRECTION_FORWARD)
    RouteEditorDialog.apply_editor_direction(dialog, route_network.ROUTE_DIRECTION_FORWARD)

    edge = dialog.canvas.graph.edges[1]
    assert edge.startid == 2
    assert edge.endid == 1
    assert edge.coordinates == [(1.0, 0.0), (0.0, 0.0)]
    assert edge.direction == "forward"
    assert edge.properties["startid"] == 2
    assert edge.properties["endid"] == 1
    assert dialog.editor_edge_start.text == "2"
    assert dialog.editor_edge_end.text == "1"
    assert dialog.canvas.history == ["修改连边方向", "切换单向方向"]
    assert dialog.graph_changed == 2


def test_route_editor_node_properties_show_nine_decimal_precision():
    class FakeCanvas:
        def __init__(self):
            self.graph = RouteGraph()
            self.graph.nodes[12] = RouteNode(12, 2.806028840, -7.476321017)

    class FakeLine:
        def __init__(self):
            self.text = ""
            self.read_only = False

        def setText(self, text):
            self.text = text

        def clear(self):
            self.text = ""

        def setReadOnly(self, read_only):
            self.read_only = read_only

    class FakeEnabled:
        def __init__(self):
            self.enabled = None

        def setEnabled(self, enabled):
            self.enabled = enabled

    class FakeSpin(FakeEnabled):
        def __init__(self):
            super().__init__()
            self.value = None

        def setValue(self, value):
            self.value = value

    class FakeButton:
        def __init__(self):
            self.checked = False

        def setChecked(self, checked):
            self.checked = checked

    class FakeTabs:
        def __init__(self):
            self.index = None

        def setCurrentIndex(self, index):
            self.index = index

    dialog = RouteEditorDialog.__new__(RouteEditorDialog)
    dialog.canvas = FakeCanvas()
    dialog.editor_object_label = FakeLine()
    dialog.editor_object_id = FakeLine()
    dialog.editor_node_x = FakeLine()
    dialog.editor_node_y = FakeLine()
    dialog.editor_edge_start = FakeLine()
    dialog.editor_edge_end = FakeLine()
    dialog.editor_direction_buttons = FakeEnabled()
    dialog.editor_passable_width = FakeSpin()
    dialog.editor_road_class_buttons = FakeEnabled()
    dialog.editor_road_class_buttons_by_value = {0: FakeButton()}
    dialog.editor_metric = FakeLine()
    dialog.editor_tabs = FakeTabs()

    RouteEditorDialog.update_properties(dialog, "node", 12)

    assert dialog.editor_node_x.text == "2.806028840"
    assert dialog.editor_node_y.text == "-7.476321017"
    assert dialog.editor_node_x.read_only is False
    assert dialog.editor_node_y.read_only is False


def test_route_editor_apply_object_changes_updates_passable_width():
    class FakeCanvas:
        def __init__(self):
            self.selected_type = "edge"
            self.selected_id = 1
            self.graph = RouteGraph()
            self.graph.nodes[1] = RouteNode(1, 0.0, 0.0)
            self.graph.nodes[2] = RouteNode(2, 1.0, 0.0)
            self.graph.edges[1] = RouteEdge(1, 1, 2, [(0.0, 0.0), (1.0, 0.0)], "both")
            self.history = []

        def push_history(self, action):
            self.history.append(action)

    class FakeButton:
        def __init__(self, checked):
            self._checked = checked

        def isChecked(self):
            return self._checked

    class FakeSpin:
        def __init__(self, value):
            self._value = value

        def value(self):
            return self._value

    dialog = RouteEditorDialog.__new__(RouteEditorDialog)
    dialog.canvas = FakeCanvas()
    dialog.editor_direction_both = FakeButton(True)
    dialog.editor_direction_forward = FakeButton(False)
    dialog.editor_passable_width = FakeSpin(3.2)
    dialog.graph_changed = 0
    dialog.update_properties = lambda *_args: None
    dialog.on_graph_changed = lambda: setattr(dialog, "graph_changed", dialog.graph_changed + 1)

    RouteEditorDialog.apply_object_changes(dialog)

    edge = dialog.canvas.graph.edges[1]
    assert route_network.edge_passable_width(edge) == 3.2
    assert edge.properties["passable_width"] == 3.2
    assert dialog.canvas.history == ["修改连边属性"]
    assert dialog.graph_changed == 1


def test_route_editor_passable_width_auto_applies_without_apply_button():
    class FakeCanvas:
        def __init__(self):
            self.selected_type = "edge"
            self.selected_id = 1
            self.graph = RouteGraph()
            self.graph.nodes[1] = RouteNode(1, 0.0, 0.0)
            self.graph.nodes[2] = RouteNode(2, 1.0, 0.0)
            self.graph.edges[1] = RouteEdge(1, 1, 2, [(0.0, 0.0), (1.0, 0.0)], "both")
            self.history = []

        def push_history(self, action):
            self.history.append(action)

    class FakeLabel:
        def __init__(self):
            self.text = ""

        def setText(self, text):
            self.text = text

    dialog = RouteEditorDialog.__new__(RouteEditorDialog)
    dialog._updating_properties = False
    dialog.canvas = FakeCanvas()
    dialog.editor_metric = FakeLabel()
    dialog.graph_changed = 0
    dialog.on_graph_changed = lambda: setattr(dialog, "graph_changed", dialog.graph_changed + 1)

    RouteEditorDialog.apply_editor_passable_width(dialog, 2.8)

    edge = dialog.canvas.graph.edges[1]
    assert route_network.edge_passable_width(edge) == 2.8
    assert edge.properties["passable_width"] == 2.8
    assert dialog.canvas.history == ["修改连边属性"]
    assert dialog.graph_changed == 1


def test_route_editor_apply_object_changes_updates_road_class():
    class FakeCanvas:
        def __init__(self):
            self.selected_type = "edge"
            self.selected_id = 1
            self.graph = RouteGraph()
            self.graph.nodes[1] = RouteNode(1, 0.0, 0.0)
            self.graph.nodes[2] = RouteNode(2, 1.0, 0.0)
            self.graph.edges[1] = RouteEdge(1, 1, 2, [(0.0, 0.0), (1.0, 0.0)], "both")
            self.history = []

        def push_history(self, action):
            self.history.append(action)

    class FakeButton:
        def __init__(self, checked):
            self._checked = checked

        def isChecked(self):
            return self._checked

    class FakeSpin:
        def __init__(self, value):
            self._value = value

        def value(self):
            return self._value

    class FakeGroup:
        def checkedId(self):
            return 3

    dialog = RouteEditorDialog.__new__(RouteEditorDialog)
    dialog.canvas = FakeCanvas()
    dialog.editor_direction_both = FakeButton(True)
    dialog.editor_direction_forward = FakeButton(False)
    dialog.editor_passable_width = FakeSpin(route_network.DEFAULT_ROUTE_PASSABLE_WIDTH)
    dialog.editor_road_class_group = FakeGroup()
    dialog.graph_changed = 0
    dialog.update_properties = lambda *_args: None
    dialog.on_graph_changed = lambda: setattr(dialog, "graph_changed", dialog.graph_changed + 1)

    RouteEditorDialog.apply_object_changes(dialog)

    edge = dialog.canvas.graph.edges[1]
    assert route_network.edge_road_class(edge) == 3
    assert edge.properties["road_class"] == 3
    assert dialog.canvas.history == ["修改连边属性"]
    assert dialog.graph_changed == 1


def test_route_editor_current_pose_node_auto_attaches_to_nearest_route_node():
    class FakeLabel:
        def __init__(self):
            self.text = ""

        def setText(self, text):
            self.text = text

    class FakeCanvas:
        def __init__(self):
            self.graph = RouteGraph()
            self.graph.nodes[1] = RouteNode(1, 0.0, 0.0)
            self.graph.nodes[2] = RouteNode(2, 5.0, 0.0)
            self.graph.edges[1] = RouteEdge(1, 1, 2, [(0.0, 0.0), (5.0, 0.0)], "both")
            self.history = []
            self.selection = None

        def push_history(self, label):
            self.history.append(label)

        def _select(self, object_type, object_id):
            self.selection = (object_type, object_id)

    dialog = RouteEditorDialog.__new__(RouteEditorDialog)
    dialog.canvas = FakeCanvas()
    dialog.page = type("Page", (), {"current_pose_slot": _FakeFinishedSlot("POSE=ok\nX=4.7\nY=0.2\nYAW=0.0\n")})()
    dialog.editor_status = FakeLabel()
    dialog.graph_changed = 0
    dialog.on_graph_changed = lambda: setattr(dialog, "graph_changed", dialog.graph_changed + 1)

    assert RouteEditorDialog._editor_current_pose_finished(dialog, object(), request_id=12, exit_code=0) is True

    graph = dialog.canvas.graph
    assert set(graph.nodes) == {1, 2, 3}
    assert graph.nodes[3].properties["source"] == "current_pose"
    assert len(graph.edges) == 2
    edge = graph.edges[2]
    assert edge.startid == 3
    assert edge.endid == 2
    assert edge.direction == "both"
    assert edge.properties["source"] == "auto_attach_isolated"
    assert dialog.canvas.selection == ("node", 3)
    assert dialog.canvas.history == ["按当前位置添加节点"]
    assert dialog.graph_changed == 1
    assert "已自动接入路网" in dialog.editor_status.text


def test_route_editor_manual_coordinate_node_preserves_precision_and_attaches_nearest():
    class FakeText:
        def __init__(self, text):
            self._text = text

        def text(self):
            return self._text

    class FakeLabel:
        def __init__(self):
            self.text = ""

        def setText(self, text):
            self.text = text

    class FakeCanvas:
        def __init__(self):
            self.graph = RouteGraph()
            self.graph.nodes[1] = RouteNode(1, 0.0, 0.0)
            self.graph.nodes[2] = RouteNode(2, 3.0, -7.0)
            self.graph.edges[1] = RouteEdge(1, 1, 2, [(0.0, 0.0), (3.0, -7.0)], "both")
            self.history = []
            self.selection = None

        def push_history(self, label):
            self.history.append(label)

        def _select(self, object_type, object_id):
            self.selection = (object_type, object_id)

    dialog = RouteEditorDialog.__new__(RouteEditorDialog)
    dialog.canvas = FakeCanvas()
    dialog.manual_route_x = FakeText("2.806028840")
    dialog.manual_route_y = FakeText("-7.476321017")
    dialog.editor_status = FakeLabel()
    dialog.graph_changed = 0
    dialog.on_graph_changed = lambda: setattr(dialog, "graph_changed", dialog.graph_changed + 1)

    assert RouteEditorDialog.add_manual_coordinate_node(dialog) is True

    graph = dialog.canvas.graph
    assert graph.nodes[3].x == 2.806028840
    assert graph.nodes[3].y == -7.476321017
    assert graph.nodes[3].properties["source"] == "manual_coordinate"
    assert graph.edges[2].startid == 2
    assert graph.edges[2].endid == 3
    assert graph.edges[2].coordinates == [(3.0, -7.0), (2.806028840, -7.476321017)]
    assert dialog.canvas.selection == ("node", 3)
    assert dialog.canvas.history == ["按坐标添加节点"]
    assert dialog.graph_changed == 1
    assert "2.806028840" in dialog.editor_status.text
    assert "最近节点 2" in dialog.editor_status.text


def test_route_editor_current_pose_add_uses_cached_realtime_pose():
    class FakeLabel:
        def __init__(self):
            self.text = ""

        def setText(self, text):
            self.text = text

    class FakeCanvas:
        def __init__(self):
            self.graph = RouteGraph()
            self.graph.nodes[1] = RouteNode(1, 0.0, 0.0)
            self.history = []
            self.selection = None

        def push_history(self, label):
            self.history.append(label)

        def _select(self, object_type, object_id):
            self.selection = (object_type, object_id)

    class Slot:
        def __init__(self):
            self.start_calls = []

        def is_running(self):
            return False

        def start_bash(self, command):
            self.start_calls.append(command)
            raise AssertionError("cached pose should not start remote current-pose command")

    dialog = RouteEditorDialog.__new__(RouteEditorDialog)
    dialog.canvas = FakeCanvas()
    dialog.page = type("Page", (), {"current_pose_slot": Slot(), "robot_pose": (4.7, 0.2, 0.1)})()
    dialog.editor_status = FakeLabel()
    dialog.graph_changed = 0
    dialog.on_graph_changed = lambda: setattr(dialog, "graph_changed", dialog.graph_changed + 1)

    assert RouteEditorDialog.add_current_pose_node(dialog) is True

    assert dialog.page.current_pose_slot.start_calls == []
    assert dialog.canvas.graph.nodes[2].x == 4.7
    assert dialog.canvas.graph.nodes[2].y == 0.2
    assert dialog.canvas.graph.nodes[2].properties["source"] == "current_pose"
    assert dialog.canvas.history == ["按当前位置添加节点"]


def test_route_network_current_pose_add_uses_cached_realtime_pose():
    class FakeCanvas:
        def __init__(self):
            self.graph = RouteGraph()
            self.selection = None

        def _select(self, object_type, object_id):
            self.selection = (object_type, object_id)

    class FakeLabel:
        def __init__(self):
            self.text = ""

        def setText(self, text):
            self.text = text

    class Slot:
        def __init__(self):
            self.start_calls = []

        def is_running(self):
            return False

        def start_bash(self, command):
            self.start_calls.append(command)
            raise AssertionError("cached pose should not start remote current-pose command")

    page = RouteNetworkPage.__new__(RouteNetworkPage)
    page.current_pose_slot = Slot()
    page.robot_pose = (1.25, -2.5, 0.75)
    page.canvas = FakeCanvas()
    page.cursor_label = FakeLabel()
    page.statuses = []
    page.update_scale_info = lambda: None
    page.set_status = lambda text, state="": page.statuses.append((text, state))

    assert RouteNetworkPage.add_current_pose_node(page) is True

    assert page.current_pose_slot.start_calls == []
    assert page.canvas.graph.nodes[1].x == 1.25
    assert page.canvas.graph.nodes[1].y == -2.5
    assert page.canvas.selection == ("node", 1)
    assert page.statuses == [("已新增当前点 1", "success")]
    assert page.cursor_label.text == "当前点：x=1.250, y=-2.500"


def test_analyze_geojson_file_reports_navigation_fields(tmp_path):
    geojson_path = tmp_path / "map.geojson"
    geojson_path.write_text(
        """
{
  "type": "FeatureCollection",
  "features": [
    {"type": "Feature", "geometry": {"type": "Point", "coordinates": [1.0, 2.0]}, "properties": {"id": 1, "name": "A"}},
    {"type": "Feature", "geometry": {"type": "Point", "coordinates": [3.0, 2.0]}, "properties": {"id": 2, "name": "B"}},
    {"type": "Feature", "geometry": {"type": "MultiLineString", "coordinates": [[[1.0, 2.0], [3.0, 2.0]]]}, "properties": {"id": 10, "startid": 1, "endid": 2, "direction": "both", "cost": 2.0}}
  ]
}
""",
        encoding="utf-8",
    )

    analysis = analyze_geojson_file(geojson_path)

    assert analysis["feature_count"] == 3
    assert analysis["geometry_counts"]["Point"] == 2
    assert analysis["geometry_counts"]["MultiLineString"] == 1
    assert analysis["point_required"]["id"] == 2
    assert analysis["edge_required"]["startid"] == 1
    assert analysis["bounds"] == (1.0, 2.0, 3.0, 2.0)
    assert analysis["coordinate_dimensions"][2] == 4
    assert analysis["third_coordinate_stats"] is None
    assert "direction" in analysis["property_stats"]


def test_route_geojson_for_remote_map_uses_same_history_directory():
    assert (
        route_geojson_for_remote_map("/ota/alg_data/map/history_map/2026_06_02_00_25_27/map.pgm")
        == "/ota/alg_data/map/history_map/2026_06_02_00_25_27/map.geojson"
    )


def test_route_map_card_root_map_uses_time_label_instead_of_fixed_name():
    assert (
        RouteMapHistoryCard.compact_label(
            "2026-06-02 11:43 | 42.9 MB | 地图",
            "/ota/alg_data/map/map.pgm",
        )
        == "2026-06-02 11:43"
    )


def test_route_inflation_overlay_marks_obstacle_expansion(tmp_path):
    _app()
    image = tmp_path / "map.pgm"
    pgm = b"P5\n7 7\n255\n" + bytes([255] * 24 + [0] + [255] * 24)
    image.write_bytes(pgm)
    yaml_path = tmp_path / "map.yaml"
    yaml_path.write_text(
        "image: map.pgm\nresolution: 0.05\norigin: [0, 0, 0]\noccupied_thresh: 0.65\nfree_thresh: 0.196\nnegate: 0\n",
        encoding="utf-8",
    )
    metadata = route_network.read_map_yaml(yaml_path)

    overlay = create_inflation_overlay(metadata, radius_m=0.10)

    assert overlay is not None
    assert overlay.radius_px == 2
    assert overlay.obstacle_pixels == 1
    assert overlay.inflated_pixels > 0
    result = overlay.pixmap.toImage()
    assert result.pixelColor(3, 3).alpha() == 0
    assert result.pixelColor(3, 5).alpha() > 0
    assert result.pixelColor(0, 0).alpha() == 0


def test_route_inflation_overlay_uses_unknown_as_blocked_source(tmp_path):
    _app()
    image = tmp_path / "map.pgm"
    pgm = b"P5\n7 7\n255\n" + bytes([255] * 24 + [205] + [255] * 24)
    image.write_bytes(pgm)
    yaml_path = tmp_path / "map.yaml"
    yaml_path.write_text(
        "image: map.pgm\nresolution: 0.05\norigin: [0, 0, 0]\noccupied_thresh: 0.65\nfree_thresh: 0.196\nnegate: 0\n",
        encoding="utf-8",
    )
    metadata = route_network.read_map_yaml(yaml_path)

    overlay = create_inflation_overlay(metadata, radius_m=0.10)

    assert overlay is not None
    assert overlay.obstacle_pixels == 1
    result = overlay.pixmap.toImage()
    assert result.pixelColor(3, 3).alpha() == 0
    assert result.pixelColor(3, 5).alpha() > 0


def test_route_canvas_inflation_overlay_visibility_can_toggle():
    _app()
    canvas = RouteMapCanvas()
    overlay = QPixmap(8, 8)
    overlay.fill(QColor(220, 38, 38, 160))

    canvas.set_inflation_overlay(overlay, "障碍膨胀 0.30m")
    canvas.set_show_inflation_overlay(False)

    assert canvas.inflation_overlay is overlay
    assert canvas.inflation_overlay_label == "障碍膨胀 0.30m"
    assert canvas.show_inflation_overlay is False


def test_route_canvas_stores_robot_pose_for_overlay():
    canvas = RouteMapCanvas()

    canvas.set_robot_pose((1.25, -2.5, 0.75))

    assert canvas.robot_pose == (1.25, -2.5, 0.75)


def test_analyze_geojson_file_reports_third_coordinate_as_z(tmp_path):
    geojson_path = tmp_path / "map.geojson"
    geojson_path.write_text(
        """
{
  "type": "FeatureCollection",
  "features": [
    {"type": "Feature", "geometry": {"type": "Point", "coordinates": [1.0, 2.0, -0.2]}, "properties": {"id": 1}},
    {"type": "Feature", "geometry": {"type": "Point", "coordinates": [3.0, 2.0, 0.4]}, "properties": {"id": 2}},
    {"type": "Feature", "geometry": {"type": "MultiLineString", "coordinates": [[[1.0, 2.0, -0.2], [3.0, 2.0, 0.4]]]}, "properties": {"id": 10, "startid": 1, "endid": 2, "direction": "both"}}
  ]
}
""",
        encoding="utf-8",
    )

    analysis = analyze_geojson_file(geojson_path)

    assert analysis["coordinate_dimensions"][3] == 4
    assert analysis["third_coordinate_stats"]["min"] == -0.2
    assert analysis["third_coordinate_stats"]["max"] == 0.4


def test_dragging_node_preserves_z_on_connected_edge():
    canvas = _scaled_canvas()
    canvas.graph.nodes[1] = RouteNode(1, 10.0, 10.0, z=-0.25)
    canvas.graph.nodes[2] = RouteNode(2, 50.0, 10.0, z=-0.1)
    canvas.graph.edges[1] = RouteEdge(1, 1, 2, [(10.0, 10.0, -0.25), (50.0, 10.0, -0.1)])
    canvas.dragging_node_id = 1
    canvas.drag_history_recorded = True
    target = canvas._world_to_widget(20.0, 15.0).toPoint()

    canvas.mouseMoveEvent(type("Event", (), {"pos": lambda self: target})())

    assert canvas.graph.edges[1].coordinates[0] == (20.0, 15.0, -0.25)


def test_route_editor_pose_stream_updates_editor_and_page_canvases():
    class FakePoseSlot:
        def read_available_text(self, _process, _request_id):
            return "POSE=ok X=1.250000000 Y=-2.500000000 YAW=0.750000000\n"

    dialog = RouteEditorDialog.__new__(RouteEditorDialog)
    dialog.canvas = RouteMapCanvas()
    page_canvas = RouteMapCanvas()
    dialog.page = type(
        "Page",
        (),
        {
            "pose_stream_slot": FakePoseSlot(),
            "pose_stream_buffer": "",
            "robot_pose": None,
            "canvas": page_canvas,
        },
    )()

    RouteEditorDialog.read_pose_stream_output(dialog, object(), 7)

    assert dialog.page.robot_pose == (1.25, -2.5, 0.75)
    assert dialog.canvas.robot_pose == (1.25, -2.5, 0.75)
    assert page_canvas.robot_pose == (1.25, -2.5, 0.75)



class _FakeRoutePage:
    def __init__(self, *, conflict="", task_id=None):
        self.runner = _FakeRunner(conflict=conflict, task_id=task_id)
        self.statuses = []

    def set_status(self, text, state=""):
        self.statuses.append((text, state))

    def ensure_selected_history_route(self, next_action):
        return RouteNetworkPage.ensure_selected_history_route(self, next_action)

    def notify_route_saved(self, path=None):
        self.notified_path = path
        return True


class _FakeRouteLifecyclePage:
    def __init__(self, *, active=False, loaded=False):
        self.page_active = active
        self.history_map_list_loaded_once = loaded
        self.history_map_slot = _FakeSlot()
        self.history_map_thumbnail_slot = _FakeSlot()
        self.refresh_calls = 0

    def refresh_history_map_list(self):
        self.refresh_calls += 1
        return True


class _FakeSlot:
    def __init__(self):
        self.stop_calls = 0

    def stop(self):
        self.stop_calls += 1


class _FakeFinishedSlot:
    def __init__(self, output="ok"):
        self.output = output
        self.finish_calls = []

    def finish(self, process, request_id):
        self.finish_calls.append((process, request_id))
        return self.output



class _FakeProcess:
    def __init__(self):
        self.readyReadStandardOutput = _FakeSignal()
        self.finished = _FakeSignal()

    def start(self):
        pass


class _FakeStartSlot:
    def __init__(self):
        self.start_calls = []
        self.process = _FakeProcess()
        self.running = False

    def is_running(self):
        return self.running

    def start_bash(self, command):
        self.start_calls.append(command)
        self.running = True
        return self.process, 17

    def start_spec(self, spec, **_kwargs):
        return self.start_bash(spec.command)

    def read_available_output(self, process, request_id):
        return True


class _FakeHistoryFetchPage:
    def __init__(self):
        self.history_map_fetch_slot = _FakeFinishedSlot()
        self.history_route_fetch_slot = _FakeStartSlot()
        self.pending_history_action = "edit"
        self.pending_history_route_action = ""
        self.require_remote_route_pull_before_edit = False
        self.selected_remote = "/remote/b/map.pgm"
        self.loaded_maps = []
        self.loaded_geojson = []
        self.synced = []
        self.opened = 0
        self.new_routes = []
        self.statuses = []
        self.editor_statuses = []
        self.route_editor_status_callback = lambda message, state="": self.editor_statuses.append((message, state))

    def selected_history_map_pgm(self):
        return self.selected_remote

    def sync_selected_history_paths(self, load_existing=False):
        self.synced.append(load_existing)
        return True

    def load_map(self, path):
        self.loaded_maps.append(path)
        return True

    def load_geojson(self, path):
        self.loaded_geojson.append(path)
        return True

    def local_paths_for_history(self, remote_pgm):
        root = getattr(self, "local_root", Path("/tmp"))
        return root / "map.pgm", root / "map.yaml", root / "map.geojson"

    def profile(self):
        return get_product("zg_lidar_nx")

    def open_route_editor(self):
        self.opened += 1

    def start_new_history_route(self, open_editor=False):
        self.new_routes.append(open_editor)

    def set_status(self, text, state=""):
        self.statuses.append((text, state))

    def ensure_selected_history_route(self, next_action):
        return RouteNetworkPage.ensure_selected_history_route(self, next_action)


def test_route_network_run_spec_cancelled_dangerous_command_does_not_run(monkeypatch):
    page = _FakeRoutePage(task_id=7)
    spec = CommandSpec("停止导航", "ros2 topic pub /start_navigation", dangerous=True)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.No)

    started = RouteNetworkPage._run_route_spec(page, spec, "急停中")

    assert started is False
    assert page.runner.run_calls == []
    assert page.statuses == []


def test_route_network_run_spec_runs_dangerous_command_after_confirm(monkeypatch):
    page = _FakeRoutePage(task_id=7)
    spec = CommandSpec("停止导航", "ros2 topic pub /start_navigation", dangerous=True)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)

    started = RouteNetworkPage._run_route_spec(page, spec, "急停中")

    assert started is True
    assert len(page.runner.run_calls) == 1
    assert page.statuses == [("急停中", "warning")]


def test_route_network_upload_finish_notifies_only_after_remote_success():
    class FakePath:
        def text(self):
            return "/tmp/map.geojson"

    class FakeDialog:
        def __init__(self):
            self.codes = []

        def remote_route_upload_finished(self, code):
            self.codes.append(code)

    page = _FakeRoutePage()
    page.geojson_path = FakePath()
    page.active_editor_dialog = FakeDialog()
    page.pending_route_upload_task_id = 12

    handled = RouteNetworkPage.handle_route_runner_finished(page, 12, 0, "上传路网 GeoJSON")

    assert handled is True
    assert page.pending_route_upload_task_id is None
    assert page.statuses == [("上传完成", "success")]
    assert page.notified_path == "/tmp/map.geojson"
    assert page.active_editor_dialog.codes == [0]


def test_route_network_upload_finish_failure_does_not_notify_saved_route():
    page = _FakeRoutePage()
    page.geojson_path = type("FakePath", (), {"text": lambda self: "/tmp/map.geojson"})()
    page.active_editor_dialog = None
    page.pending_route_upload_task_id = 12

    handled = RouteNetworkPage.handle_route_runner_finished(page, 12, 1, "上传路网 GeoJSON")

    assert handled is True
    assert page.pending_route_upload_task_id is None
    assert page.statuses == [("上传失败", "error")]
    assert not hasattr(page, "notified_path")


def test_route_network_shutdown_stops_local_process_slots():
    page = type(
        "Page",
        (),
        {
            "current_pose_slot": _FakeSlot(),
            "history_map_slot": _FakeSlot(),
            "history_map_fetch_slot": _FakeSlot(),
        },
    )()

    RouteNetworkPage.shutdown_processes(page)

    assert page.current_pose_slot.stop_calls == 1
    assert page.history_map_slot.stop_calls == 1
    assert page.history_map_fetch_slot.stop_calls == 1


def test_route_network_activate_page_does_not_repeat_history_map_refresh():
    page = _FakeRouteLifecyclePage(active=False, loaded=False)

    RouteNetworkPage.activate_page(page)

    assert page.page_active is True
    assert page.refresh_calls == 1

    RouteNetworkPage.activate_page(page)

    assert page.refresh_calls == 1

    loaded = _FakeRouteLifecyclePage(active=False, loaded=True)

    RouteNetworkPage.activate_page(loaded)

    assert loaded.page_active is True
    assert loaded.refresh_calls == 0


def test_route_network_deactivate_stops_history_map_processes():
    page = _FakeRouteLifecyclePage(active=True, loaded=False)

    RouteNetworkPage.deactivate_page(page)

    assert page.page_active is False
    assert page.history_map_slot.stop_calls == 1
    assert page.history_map_thumbnail_slot.stop_calls == 1


def test_route_network_history_fetch_ignores_changed_selection(tmp_path):
    page = _FakeHistoryFetchPage()
    local_yaml = tmp_path / "map.yaml"
    local_yaml.write_text("resolution: 0.05\norigin: [0, 0, 0]\n", encoding="utf-8")

    accepted = RouteNetworkPage.history_map_fetch_finished(
        page,
        process=object(),
        exit_code=0,
        remote_pgm="/remote/a/map.pgm",
        local_yaml=local_yaml,
        request_id=7,
    )

    assert accepted is True
    assert page.pending_history_action == ""
    assert page.synced == [True]
    assert page.loaded_maps == []
    assert page.opened == 0
    assert page.new_routes == []


def test_route_network_edit_history_pulls_remote_route_before_opening_cached_editor(tmp_path):
    page = _FakeHistoryFetchPage()
    page.local_root = tmp_path
    page.require_remote_route_pull_before_edit = True
    local_yaml = tmp_path / "map.yaml"
    local_geojson = tmp_path / "map.geojson"
    local_yaml.write_text("resolution: 0.05\norigin: [0, 0, 0]\n", encoding="utf-8")
    local_geojson.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")

    opened = RouteNetworkPage.ensure_selected_history_preview(page, "edit")

    assert opened is False
    assert page.opened == 0
    assert page.loaded_maps == [str(local_yaml)]
    assert page.history_route_fetch_slot.start_calls
    command = page.history_route_fetch_slot.start_calls[-1]
    assert "/remote/b/map.geojson" in command
    assert str(local_geojson) in command
    assert page.statuses[-1] == ("同步远端路网中", "warning")


def test_route_network_edit_history_pulls_remote_route_when_local_route_missing(tmp_path):
    page = _FakeHistoryFetchPage()
    page.local_root = tmp_path
    page.require_remote_route_pull_before_edit = True
    local_yaml = tmp_path / "map.yaml"
    local_geojson = tmp_path / "map.geojson"
    local_yaml.write_text("resolution: 0.05\norigin: [0, 0, 0]\n", encoding="utf-8")

    opened = RouteNetworkPage.ensure_selected_history_preview(page, "edit")

    assert opened is False
    assert page.opened == 0
    assert page.loaded_maps == [str(local_yaml)]
    assert page.history_route_fetch_slot.start_calls
    command = page.history_route_fetch_slot.start_calls[-1]
    assert "/remote/b/map.geojson" in command
    assert str(local_geojson) in command
    assert page.statuses[-1] == ("同步远端路网中", "warning")


def test_route_network_history_route_fetch_loads_fresh_geojson_then_opens(tmp_path, monkeypatch):
    page = _FakeHistoryFetchPage()
    page.local_root = tmp_path
    page.history_route_fetch_slot = _FakeFinishedSlot(output="ok")
    page.pending_history_route_action = "edit"
    page.require_remote_route_pull_before_edit = True
    local_geojson = tmp_path / "map.geojson"
    local_geojson.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    monkeypatch.setattr(route_network_map_history_fetch.QTimer, "singleShot", lambda _ms, callback: callback())

    handled = RouteNetworkPage.history_route_fetch_finished(
        page,
        process=object(),
        exit_code=0,
        remote_pgm="/remote/b/map.pgm",
        local_geojson=local_geojson,
        request_id=18,
    )

    assert handled is True
    assert page.require_remote_route_pull_before_edit is False
    assert page.loaded_geojson == [str(local_geojson)]
    assert page.opened == 1
    assert page.editor_statuses[-1] == ("远端路网已同步，正在打开编辑器", "ready")


def test_route_network_history_route_fetch_failure_notifies_navigation_page(tmp_path, monkeypatch):
    page = _FakeHistoryFetchPage()
    page.local_root = tmp_path
    page.history_route_fetch_slot = _FakeFinishedSlot(output="missing")
    page.pending_history_route_action = "edit"
    page.require_remote_route_pull_before_edit = True
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: messages.append(args))

    handled = RouteNetworkPage.history_route_fetch_finished(
        page,
        process=object(),
        exit_code=1,
        remote_pgm="/remote/b/map.pgm",
        local_geojson=tmp_path / "map.geojson",
        request_id=18,
    )

    assert handled is True
    assert page.require_remote_route_pull_before_edit is False
    assert page.loaded_geojson == []
    assert page.opened == 0
    assert page.editor_statuses[-1] == ("远端路网同步失败，请检查 map.geojson 或重新上传", "error")
    assert messages == []


def test_dog_remote_tool_package_smoke_starts_offscreen():
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONPATH"] = str(Path.cwd() / "src")

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from dog_remote_tool.app import main; raise SystemExit(main(['dog_remote_tool', '--smoke-test']))",
        ],
        text=True,
        capture_output=True,
        timeout=20,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert "远程调试平台" in result.stdout
    assert "pages=" in result.stdout
