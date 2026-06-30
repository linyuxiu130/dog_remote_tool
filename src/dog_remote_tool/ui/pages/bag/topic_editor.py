from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QListWidget, QTableWidget, QTableWidgetItem

from dog_remote_tool.ui.pages.bag.topic_helpers import normalize_topic_values


def selected_topic_keys(topic_list: QListWidget) -> list[str]:
    return [item.data(Qt.UserRole) for item in topic_list.selectedItems()]


def active_topic_key(topic_list: QListWidget) -> str:
    current = topic_list.currentItem()
    if current and current.isSelected():
        return str(current.data(Qt.UserRole))
    selected = topic_list.selectedItems()
    if selected:
        return str(selected[0].data(Qt.UserRole))
    return ""


def set_topic_table_rows(topic_table: QTableWidget, topics: list[str]) -> None:
    topic_table.setRowCount(0)
    for topic in topics:
        row = topic_table.rowCount()
        topic_table.insertRow(row)
        topic_item = QTableWidgetItem(topic)
        topic_item.setData(Qt.UserRole, topic)
        topic_table.setItem(row, 0, topic_item)


def topic_table_values(topic_table: QTableWidget) -> list[str]:
    values: list[str] = []
    for row in range(topic_table.rowCount()):
        item = topic_table.item(row, 0)
        values.append(item.text().strip() if item else "")
    return normalize_topic_values(values)


def selected_topic_table_values(topic_table: QTableWidget) -> tuple[list[int], list[str]]:
    rows = sorted({index.row() for index in topic_table.selectionModel().selectedRows()}, reverse=True)
    topics = []
    for row in rows:
        item = topic_table.item(row, 0)
        topic = normalize_topic_values([item.text() if item else ""])
        if topic:
            topics.append(topic[0])
    return rows, topics
