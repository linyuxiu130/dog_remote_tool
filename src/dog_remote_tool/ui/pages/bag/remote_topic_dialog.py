from __future__ import annotations

from PyQt5.QtCore import QSignalBlocker, Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from dog_remote_tool.core.profiles import ProductProfile
import dog_remote_tool.ui.pages.bag.remote_topics as bag_remote_topics


class RemoteTopicDialog(QDialog):
    def __init__(self, profile: ProductProfile, parent: QWidget | None, refresh_callback, view_changed_callback) -> None:
        super().__init__(parent)
        self.setObjectName("ToolDialog")
        self.setWindowTitle(f"远端Topic - {profile.label}")
        self.setModal(False)
        self.setSizeGripEnabled(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        layout.addWidget(self._build_header(profile, refresh_callback, view_changed_callback))

        self.topic_table = QTableWidget(0, 5)
        self.topic_table.setHorizontalHeaderLabels(["主题", "Topic", "类型", "Hz", "状态"])
        self.topic_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.topic_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.topic_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.topic_table.setAlternatingRowColors(True)
        self.topic_table.verticalHeader().setVisible(False)
        self.topic_table.verticalHeader().setDefaultSectionSize(28)
        header_view = self.topic_table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(1, QHeaderView.Stretch)
        header_view.setSectionResizeMode(2, QHeaderView.Stretch)
        header_view.setSectionResizeMode(3, QHeaderView.Fixed)
        header_view.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.topic_table.setColumnWidth(3, 90)
        self.topic_table.setSortingEnabled(False)
        layout.addWidget(self.topic_table, 1)
        self._resize_to_screen()

    def _build_header(self, profile: ProductProfile, refresh_callback, view_changed_callback) -> QFrame:
        header = QFrame()
        header.setObjectName("PageHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(12, 10, 12, 10)
        header_layout.setSpacing(8)

        title_row = QHBoxLayout()
        title = QLabel("远端话题列表")
        title.setObjectName("DiagSectionTitle")
        target = QLabel(profile.label)
        target.setObjectName("Muted")
        self.status_label = QLabel("准备读取")
        self.status_label.setObjectName("Muted")
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.setObjectName("SoftPrimary")
        self.refresh_btn.clicked.connect(refresh_callback)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        title_row.addWidget(title)
        title_row.addWidget(target)
        title_row.addStretch(1)
        title_row.addWidget(self.status_label)
        title_row.addWidget(self.refresh_btn)
        title_row.addWidget(close_btn)
        header_layout.addLayout(title_row)

        view_row = QHBoxLayout()
        view_label = QLabel("显示主题")
        view_label.setObjectName("FieldLabel")
        self.theme_combo = QComboBox()
        self.theme_combo.setMinimumWidth(220)
        self.theme_combo.currentIndexChanged.connect(view_changed_callback)
        hint = QLabel("Hz 为 1.5 秒批量快照；低频或事件触发 Topic 可能显示未取到/采样不足")
        hint.setObjectName("Muted")
        view_row.addWidget(view_label)
        view_row.addWidget(self.theme_combo)
        view_row.addWidget(hint, 1)
        header_layout.addLayout(view_row)
        return header

    def _resize_to_screen(self) -> None:
        screen = QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()
            min_width = min(1320, max(1000, int(available.width() * 0.78)))
            min_height = min(780, max(640, int(available.height() * 0.72)))
            width = min(1840, max(1320, int(available.width() * 0.96)))
            height = min(940, max(840, int(available.height() * 0.88)))
            self.setMinimumSize(min_width, min_height)
            self.resize(width, height)
        else:
            self.setMinimumSize(1180, 760)
            self.resize(1180, 760)

    def set_busy(self, busy: bool) -> None:
        self.refresh_btn.setEnabled(not busy)

    def clear_rows(self) -> None:
        self.topic_table.setRowCount(0)

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def current_view_key(self) -> str:
        return str(self.theme_combo.currentData() or bag_remote_topics.VIEW_ALL)

    def refresh_theme_combo(self, record_topics: dict, display_name) -> None:
        current = self.theme_combo.currentData()
        with QSignalBlocker(self.theme_combo):
            self.theme_combo.clear()
            for label, key in bag_remote_topics.default_view_items():
                self.theme_combo.addItem(label, key)
            for label, key in bag_remote_topics.topic_theme_items(record_topics, display_name):
                self.theme_combo.addItem(label, key)
            index = self.theme_combo.findData(current)
            self.theme_combo.setCurrentIndex(index if index >= 0 else 0)

    def display_rows(self, rows: list[dict], record_topics: dict, display_name, selected_keys: set[str]) -> list[dict]:
        entries = bag_remote_topics.theme_entries(record_topics, display_name)
        return bag_remote_topics.view_rows(rows, entries, self.current_view_key(), selected_keys)

    def populate_rows(self, rows: list[dict], record_topics: dict, display_name, selected_keys: set[str]) -> None:
        display_rows = self.display_rows(rows, record_topics, display_name, selected_keys)
        table = self.topic_table
        table.setSortingEnabled(False)
        table.setRowCount(len(display_rows))
        for row_index, row in enumerate(display_rows):
            self._populate_row(row_index, row)
        if rows:
            ok_count = sum(1 for item in display_rows if item.get("hz") is not None)
            self.set_status(f"显示 {len(display_rows)}/{len(rows)}，Hz {ok_count} 个")

    def _populate_row(self, row_index: int, row: dict) -> None:
        theme, values, numeric_hz = bag_remote_topics.table_row_values(row)
        row_color = QColor(bag_remote_topics.theme_color_hex(str(theme["key"]), int(theme["order"])))
        for column, value in enumerate(values):
            if column == 3 and numeric_hz is not None:
                item = QTableWidgetItem()
                item.setData(Qt.DisplayRole, numeric_hz)
            else:
                item = QTableWidgetItem(value)
            item.setBackground(row_color)
            if column == 0:
                item.setToolTip(str(theme["all"]))
            if row.get("status") != "正常":
                item.setForeground(QColor("#64748b"))
            self.topic_table.setItem(row_index, column, item)
