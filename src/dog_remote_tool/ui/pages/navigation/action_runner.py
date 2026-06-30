from __future__ import annotations

from dog_remote_tool.ui.pages.navigation.page_refs import navigation_page_class, navigation_page_module
from dog_remote_tool.ui.pages.navigation.status_helpers import (
    _navigation_command_pending_text,
    _without_remote_navigation_state,
)


class NavigationActionRunnerMixin:
    def run_robot_task_spec(self, spec, operation: str) -> bool:
        page = navigation_page_class()
        conflict = self.runner.conflict_reason(spec)
        if conflict:
            self.flow_detail.setText(f"流程摘要\n{conflict}")
            return False
        if not navigation_page_module().confirm_command_spec(self, spec):
            return False
        self.task_state.setText(f"任务\n{operation}")
        self._set_card_style(self.task_state, "starting")
        task_id = self.runner.run(spec, spec.display_command or spec.title)
        if task_id is None:
            self.task_state.setText("任务\n任务未启动")
            self._set_card_style(self.task_state, "blocked")
            self.flow_detail.setText("流程摘要\n任务未启动")
            self.refresh_workspace_from_page()
            return False
        page.update_navigation_action_buttons(self, self.last_status_values)
        self.refresh_workspace_from_page()
        return True

    def run_navigation_spec(self, spec, operation: str) -> bool:
        page = navigation_page_class()
        conflict = self.runner.conflict_reason(spec)
        if conflict:
            self.flow_detail.setText(f"流程摘要\n{conflict}")
            return False
        if not navigation_page_module().confirm_command_spec(self, spec):
            return False
        display_operation = _navigation_command_pending_text(operation)
        self.task_state.setText(f"任务\n{display_operation}")
        self._set_card_style(self.task_state, "starting")
        self.current_spec = None
        task_id = self.runner.run(spec, spec.display_command or spec.title)
        if task_id is None:
            self.task_state.setText("任务\n任务未启动")
            self._set_card_style(self.task_state, "blocked")
            self.flow_detail.setText("流程摘要\n任务未启动")
            self.refresh_workspace_from_page()
            return False
        if operation != "停止中":
            self.navigation_command_task_id = task_id
            self.navigation_command_operation = operation
            optimistic_values = _without_remote_navigation_state(dict(getattr(self, "last_status_values", {})))
            optimistic_values.setdefault("MAP_OK", "1")
            optimistic_values.setdefault("LOAD_MAP_SERVICE", "1")
            optimistic_values.setdefault("LOCALIZATION_READY", "1")
            optimistic_values.setdefault("NAV_PROCESS", "1")
            optimistic_values.setdefault("START_NAV_SUBSCRIBERS", "1")
            optimistic_values["STATUS"] = "starting"
            optimistic_values["TEXT"] = display_operation
            page.show_pending_navigation_command(self, operation, optimistic_values)
            page.update_navigation_action_buttons(self, optimistic_values)
        self.refresh_workspace_from_page()
        return True

    def run_route_file_spec(self, spec, operation: str) -> bool:
        page = navigation_page_class()
        conflict = self.runner.conflict_reason(spec)
        if conflict:
            self.flow_detail.setText(f"流程摘要\n{conflict}")
            return False
        if not navigation_page_module().confirm_command_spec(self, spec):
            return False
        self.task_state.setText(f"任务\n{operation}")
        self._set_card_style(self.task_state, "starting")
        task_id = self.runner.run(spec, spec.display_command or spec.title)
        if task_id is None:
            self.task_state.setText("任务\n任务未启动")
            self._set_card_style(self.task_state, "blocked")
            self.flow_detail.setText("流程摘要\n任务未启动")
            self.refresh_workspace_from_page()
            return False
        page.update_navigation_action_buttons(self, self.last_status_values)
        self.refresh_workspace_from_page()
        return True
