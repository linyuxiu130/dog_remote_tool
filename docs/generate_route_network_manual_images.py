from __future__ import annotations

import math
import os
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from PyQt5.QtCore import QObject, QPoint, QSignalBlocker, Qt
from PyQt5.QtGui import QColor, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import QApplication, QPushButton, QTabWidget, QWidget


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
OUT = ROOT / "docs" / "route_network_manual_images"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(SRC))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dog_remote_tool.core.profiles import get_product  # noqa: E402
from dog_remote_tool.core.runner import ProcessRunner  # noqa: E402
from dog_remote_tool.modules.navigation.route_network import MapMetadata, RouteEdge, RouteGraph, RouteNode  # noqa: E402
from dog_remote_tool.ui.pages.route_network.map_history_card import RouteMapHistoryCard  # noqa: E402
from dog_remote_tool.ui.pages.route_network.page import RouteNetworkPage  # noqa: E402
from dog_remote_tool.ui.route_editor_dialog import RouteEditorDialog  # noqa: E402
from dog_remote_tool.ui.theme import apply_theme  # noqa: E402


class FakeDeviceBar(QObject):
    def __init__(self) -> None:
        super().__init__()
        self._profile = get_product("zg_surround_s100")

    def current_profile(self):
        return self._profile


def font_path() -> str:
    try:
        path = subprocess.check_output(
            ["fc-match", "-f", "%{file}", "Noto Sans CJK SC"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if path:
            return path
    except Exception:
        pass
    return "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


FONT = ImageFont.truetype(font_path(), 24)
FONT_BOLD = ImageFont.truetype(font_path(), 28)
RED = (220, 38, 38, 255)
BLUE = (37, 99, 235, 255)
WHITE = (255, 255, 255, 245)
BLACK = (17, 24, 39, 255)


def sample_map_pixmap(width: int = 980, height: int = 620) -> QPixmap:
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor("#eef2f7"))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor("#d4dbe7"), 1))
    for x in range(0, width, 40):
        painter.drawLine(x, 0, x, height)
    for y in range(0, height, 40):
        painter.drawLine(0, y, width, y)
    painter.setPen(QPen(QColor("#64748b"), 3))
    painter.setBrush(QColor("#cbd5e1"))
    painter.drawRect(120, 110, 190, 80)
    painter.drawRect(560, 90, 140, 180)
    painter.drawRect(350, 390, 260, 70)
    painter.setPen(QPen(QColor("#94a3b8"), 2))
    painter.setBrush(QColor("#f8fafc"))
    painter.drawRect(60, 45, width - 120, height - 90)
    painter.end()
    return pixmap


def sample_graph() -> RouteGraph:
    graph = RouteGraph()
    points = {
        1: (0.8, 0.7),
        2: (2.4, 0.8),
        3: (3.6, 1.8),
        4: (5.0, 1.7),
        5: (5.8, 3.0),
        6: (2.0, 3.5),
    }
    for node_id, (x, y) in points.items():
        graph.nodes[node_id] = RouteNode(node_id, x, y, {"id": node_id})
    edges = [
        (1, 1, 2, "both"),
        (2, 2, 3, "both"),
        (3, 3, 4, "forward"),
        (4, 4, 5, "both"),
        (5, 3, 6, "both"),
        (6, 6, 1, "both"),
    ]
    for edge_id, start, end, direction in edges:
        coords = [(points[start][0], points[start][1]), (points[end][0], points[end][1])]
        graph.edges[edge_id] = RouteEdge(edge_id, start, end, coords, direction, properties={"id": edge_id})
    return graph


def prepare_page(app: QApplication) -> RouteNetworkPage:
    runner = ProcessRunner()
    page = RouteNetworkPage(runner, FakeDeviceBar())
    page.resize(1500, 980)
    page.map_metadata = MapMetadata(Path("/tmp/route_manual/map.pgm"), 0.05, (0.0, 0.0, 0.0))
    page.canvas.set_map(sample_map_pixmap(), page.map_metadata)
    page.canvas.set_graph(sample_graph())
    page.graph = page.canvas.graph
    page.map_path.setText("/home/robot/.robot/map/history_map/2026_06_18_02_11_20/map.yaml")
    page.geojson_path.setText(str(Path.home() / "data/maps/2026_06_18_02_11_20/map.geojson"))
    page.remote_route_path.setText("/ota/alg_data/map/history_map/2026_06_18_02_11_20/map.geojson")
    page.selected_history_detail.setText("远端目录：/ota/alg_data/map/history_map/2026_06_18_02_11_20/")
    selected_remote = "/ota/alg_data/map/history_map/2026_06_18_02_11_20/map.pgm"
    with QSignalBlocker(page.history_map_selector):
        page.history_map_selector.addItem("2026_06_18_02_11_20", selected_remote)
        page.history_map_selector.setCurrentIndex(0)
    page.status_label.setText("已选历史图")
    page.graph_summary_label.setText("路网：6 点 / 6 边")
    page.map_scale_label.setText("底图：0.05 m/px")
    page.scale_state_label.setText("比例：正常")
    page.inflation_state_label.setText("膨胀：0.55 m")
    page.history_map_cards_empty.hide()
    page.history_map_cards_panel.show()
    for index, label in enumerate(("2026_06_18_02_11_20", "2026_06_18_01_35_42", "2026_06_17_19_02_11")):
        remote = f"/ota/alg_data/map/history_map/{label}/map.pgm"
        card = RouteMapHistoryCard(label, remote, f"历史地图 {label}", lambda _remote: None)
        card.set_selected(index == 0)
        card.thumbnail_pixmap = sample_map_pixmap(320, 168)
        card.update_thumbnail()
        page.history_map_cards_layout.addWidget(card, 1)
    page.show()
    app.processEvents()
    return page


def prepare_editor(app: QApplication, page: RouteNetworkPage) -> RouteEditorDialog:
    RouteEditorDialog.start_pose_stream = lambda self: None
    RouteEditorDialog.stop_pose_stream = lambda self: None
    editor = RouteEditorDialog(page)
    editor.resize(1600, 980)
    editor.show()
    editor.canvas._select("edge", 2)
    editor.update_properties("edge", 2)
    app.processEvents()
    return editor


def grab(widget: QWidget, name: str) -> Path:
    app = QApplication.instance()
    if app:
        app.processEvents()
    path = OUT / name
    widget.grab().save(str(path))
    return path


def center_in(widget: QWidget, root: QWidget) -> tuple[int, int]:
    point = widget.mapTo(root, QPoint(widget.width() // 2, widget.height() // 2))
    return point.x(), point.y()


def find_button(root: QWidget, text: str) -> QWidget | None:
    for button in root.findChildren(QPushButton):
        if button.text().replace("\n", "") == text.replace("\n", ""):
            return button
    return None


def draw_arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], color=RED) -> None:
    draw.line([start, end], fill=color, width=6)
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    size = 18
    left = (end[0] - size * math.cos(angle - math.pi / 6), end[1] - size * math.sin(angle - math.pi / 6))
    right = (end[0] - size * math.cos(angle + math.pi / 6), end[1] - size * math.sin(angle + math.pi / 6))
    draw.polygon([end, left, right], fill=color)


def label_box(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, num: int) -> tuple[int, int]:
    x, y = xy
    label = f"{num}. {text}"
    bbox = draw.textbbox((0, 0), label, font=FONT)
    width = bbox[2] - bbox[0] + 28
    height = bbox[3] - bbox[1] + 22
    draw.rounded_rectangle([x, y, x + width, y + height], radius=12, fill=WHITE, outline=RED, width=3)
    draw.text((x + 14, y + 9), label, font=FONT, fill=BLACK)
    return x + width, y + height // 2


def annotate(source: Path, output: str, callouts: list[tuple[str, tuple[int, int], tuple[int, int]]]) -> Path:
    image = Image.open(source).convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for index, (text, label_xy, target_xy) in enumerate(callouts, start=1):
        label_tip = label_box(draw, label_xy, text, index)
        draw_arrow(draw, label_tip, target_xy)
        draw.ellipse([target_xy[0] - 12, target_xy[1] - 12, target_xy[0] + 12, target_xy[1] + 12], fill=BLUE, outline=(255, 255, 255, 255), width=3)
    result = Image.alpha_composite(image, overlay).convert("RGB")
    out = OUT / output
    result.save(out, quality=94)
    return out


def make_images() -> None:
    app = QApplication([])
    apply_theme(app)
    page = prepare_page(app)

    raw = grab(page, "_raw_route_page.png")
    refresh = find_button(page, "刷新地图")
    new_route = find_button(page, "新建路网")
    edit_route = find_button(page, "编辑路网")
    upload = find_button(page, "上传路网")
    load = find_button(page, "加载路网")
    status = find_button(page, "检查状态")
    annotate(
        raw,
        "01_route_page_overview.png",
        [
            ("先刷新远端历史地图", (28, 96), center_in(refresh, page) if refresh else (1130, 105)),
            ("选择要编辑的历史图卡片", (28, 190), (310, 250)),
            ("新建路网或进入编辑器", (28, 286), center_in(new_route, page) if new_route else (560, 382)),
            ("确认远端 map.geojson 路径", (28, 382), (740, 350)),
        ],
    )
    annotate(
        raw,
        "02_upload_load_flow.png",
        [
            ("编辑完成后先上传路网", (940, 345), center_in(upload, page) if upload else (1120, 382)),
            ("再加载到导航栈", (940, 438), center_in(load, page) if load else (1240, 382)),
            ("用检查状态确认文件和服务", (940, 531), center_in(status, page) if status else (1365, 382)),
            ("下方画布只预览，不在此直接改线", (940, 624), (720, 700)),
        ],
    )

    editor = prepare_editor(app, page)
    raw_editor = grab(editor, "_raw_route_editor.png")
    edge = find_button(editor, "加点连线")
    select = find_button(editor, "选取移动")
    add_pose = find_button(editor, "当前位置加点")
    save = find_button(editor, "上传远端")
    close = find_button(editor, "关闭")
    annotate(
        raw_editor,
        "03_editor_draw_and_properties.png",
        [
            ("用加点连线在地图上画路网", (28, 108), center_in(edge, editor) if edge else (220, 115)),
            ("左键点空白处加节点，继续点可连边", (28, 206), (620, 520)),
            ("选中边后在右侧改路宽、方向、运动模式", (28, 304), (1330, 390)),
            ("需要实测路径时可当前位置加点", (28, 402), center_in(add_pose, editor) if add_pose else (1180, 52)),
        ],
    )

    if editor.editor_tabs:
        editor.editor_tabs.setCurrentWidget(editor.editor_issue_tab)
    app.processEvents()
    raw_validation = grab(editor, "_raw_route_editor_validation.png")
    fix_cross = find_button(editor, "自动补交点")
    fix_iso = find_button(editor, "自动接孤立点")
    annotate(
        raw_validation,
        "04_editor_validation.png",
        [
            ("查看校验结果，有错误不能上传远端", (28, 120), (1262, 406)),
            ("相交但未连通时用自动补交点", (28, 220), center_in(fix_cross, editor) if fix_cross else (1390, 250)),
            ("孤立节点用自动接孤立点处理", (28, 320), center_in(fix_iso, editor) if fix_iso else (1390, 300)),
            ("确认无错误后点击上传远端", (28, 420), center_in(save, editor) if save else (1440, 52)),
        ],
    )

    annotate(
        raw_editor,
        "05_editor_finish.png",
        [
            ("编辑器会自动保存本地 GeoJSON", (1020, 100), (790, 52)),
            ("上传完成后关闭回到路网页", (1020, 196), center_in(close, editor) if close else (1540, 52)),
            ("回到路网页后再执行加载路网", (1020, 292), center_in(load, page) if load else (1240, 382)),
        ],
    )

    print("generated:")
    for path in sorted(OUT.glob("[0-9][0-9]_*.png")):
        print(path)


if __name__ == "__main__":
    make_images()
