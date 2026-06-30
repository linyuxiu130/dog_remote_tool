from __future__ import annotations

from dog_remote_tool.ui.pages.navigation.route_file_editor import NavigationRouteFileEditorMixin
from dog_remote_tool.ui.pages.navigation.route_file_local import NavigationRouteFileLocalMixin
from dog_remote_tool.ui.pages.navigation.route_file_remote import NavigationRouteFileRemoteMixin
from dog_remote_tool.ui.pages.navigation.route_file_upload import NavigationRouteFileUploadMixin
from dog_remote_tool.ui.pages.navigation.map_history import NavigationMapHistoryMixin
from dog_remote_tool.ui.pages.navigation.route_history import NavigationRouteHistoryMixin


class NavigationRouteFilesMixin(
    NavigationRouteFileEditorMixin,
    NavigationRouteFileRemoteMixin,
    NavigationRouteFileUploadMixin,
    NavigationRouteFileLocalMixin,
    NavigationRouteHistoryMixin,
):
    def _log_route_event(self, text: str) -> None:
        log = getattr(self, "log_navigation_event", None)
        if callable(log):
            log(text)
            return
        lines = getattr(self, "navigation_log_lines", None)
        if lines is not None:
            lines.append(text)
            refresh = getattr(self, "refresh_workspace_from_page", None)
            if callable(refresh):
                refresh()

    def _update_route_action_buttons(self) -> bool:
        update = getattr(self, "update_navigation_action_buttons", None)
        if not callable(update):
            return False
        update(getattr(self, "last_status_values", {}))
        return True

    def route_action_label(self) -> str:
        remote_pgm = self.selected_map_pgm()
        if not remote_pgm:
            return "新建路网"
        if self.route_check_slot.is_running() and self.route_check_remote_pgm == remote_pgm:
            return "检查路网"
        local_route = NavigationMapHistoryMixin.local_route_geojson_path(self, remote_pgm)
        if local_route is not None and local_route.exists():
            return "编辑路网"
        state = self.route_file_states.get(remote_pgm)
        if state is None:
            return "检查路网"
        return "编辑路网" if state else "新建路网"
