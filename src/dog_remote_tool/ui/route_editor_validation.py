from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QListWidgetItem

from dog_remote_tool.modules.navigation import route_network
from dog_remote_tool.modules.navigation.route_network import ValidationIssue


class RouteEditorValidationMixin:
    def validate_graph(self) -> bool:
        ok = self.refresh_validation_highlights()
        if self.page.last_issues:
            self.editor_tabs.setCurrentWidget(self.editor_issue_tab)
        return ok

    def refresh_validation_highlights(self) -> bool:
        image_size = None
        if self.canvas.pixmap and not self.canvas.pixmap.isNull():
            image_size = (self.canvas.pixmap.width(), self.canvas.pixmap.height())
        issues = route_network.validate_graph(self.canvas.graph, self.canvas.map_metadata, image_size)
        self.page.last_issues = issues
        self.canvas.set_issues(issues)
        self.page.canvas.set_issues(issues)
        self.populate_issues(issues)
        self.update_summary()
        errors = sum(1 for issue in issues if issue.severity == "error")
        warnings = sum(1 for issue in issues if issue.severity == "warning")
        if errors or warnings:
            self.editor_status.setText(f"异常高亮：错误 {errors}，警告 {warnings}")
        return errors == 0

    def populate_issues(self, issues: list[ValidationIssue]) -> None:
        self.editor_issue_list.clear()
        errors = sum(1 for issue in issues if issue.severity == "error")
        warnings = sum(1 for issue in issues if issue.severity == "warning")
        self.editor_issue_summary.setText("校验通过" if not issues else f"错误 {errors}，警告 {warnings}")
        for issue in issues:
            item = QListWidgetItem(f"{'错误' if issue.severity == 'error' else '警告'} · {issue.message}")
            item.setData(Qt.UserRole, issue)
            self.editor_issue_list.addItem(item)

    def focus_issue(self, item: QListWidgetItem) -> None:
        issue = item.data(Qt.UserRole)
        if isinstance(issue, ValidationIssue) and issue.object_id is not None:
            self.canvas.selected_type = issue.object_type
            self.canvas.selected_id = issue.object_id
            self.update_properties(issue.object_type, issue.object_id)
            self.canvas.update()
