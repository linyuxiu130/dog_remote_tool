from __future__ import annotations

from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QMessageBox, QTableWidgetItem


class RouteEditorHistoryMixin:
    def update_summary(self) -> None:
        graph = self.canvas.graph
        self.editor_summary.setText(f"{len(graph.nodes)} 点 / {len(graph.edges)} 边")

    def refresh_history_table(self) -> None:
        self.history_table.setRowCount(len(self.canvas.history_records))
        for row, record in enumerate(self.canvas.history_records):
            values = (
                str(record["time"]),
                str(record["action"]),
                str(record["nodes"]),
                str(record["edges"]),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if row == len(self.canvas.history_records) - 1:
                    item.setBackground(QColor("#fff8ed"))
                self.history_table.setItem(row, column, item)
        self.history_table.resizeColumnsToContents()

    def undo_history(self) -> None:
        if not self.canvas.undo_last_history():
            self.editor_status.setText("没有可撤销的改动")
            return
        self.editor_status.setText("已撤销上一步改动")
        self.update_summary()
        self.validate_graph()

    def revert_selected_history(self) -> None:
        row = self.history_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "未选择历史", "请先选择一条历史记录。")
            return
        self.jump_to_history_row(row)

    def jump_to_history_row(self, row: int) -> bool:
        if not self.canvas.revert_to_history(row):
            return False
        self.editor_status.setText("已跳转到选中历史状态")
        self.update_summary()
        self.validate_graph()
        return True

    def reset_editor_view(self) -> None:
        self.canvas.reset_view()
        self.editor_status.setText("已回到完整底图视图")
