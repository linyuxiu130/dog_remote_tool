from __future__ import annotations

from pathlib import Path

from dog_remote_tool.modules import mapping
from dog_remote_tool.ui.command_confirm import confirm_dangerous_action
from dog_remote_tool.ui.pages.mapping.transfer_runner import MappingTransferRunnerMixin
from dog_remote_tool.ui.status_text import task_not_started_text


def _mapping_page_module():
    from dog_remote_tool.ui.pages.mapping import page as mapping_page

    return mapping_page


class MappingTransferActionsMixin(MappingTransferRunnerMixin):
    def make_delete_selected_map(self) -> bool:
        remote_pgm = self.selected_remote_map_pgm()
        if not remote_pgm:
            mapping_page = _mapping_page_module()
            mapping_page.QMessageBox.information(self, "未选择地图", "请等待地图列表自动加载后选择一个 map.pgm。")
            return False
        remote_dir = str(Path(remote_pgm).parent)
        map_label = Path(remote_dir).name or Path(remote_pgm).name
        _sensor_type, save_map_path, _calibration_file_path, _arc_calibration_file_path = self.mapping_values()
        root_note = "\n\n当前选择的是根地图，将只删除根目录下的地图文件，不会删除 history_map。"
        confirmed = confirm_dangerous_action(
            self,
            "确认删除地图",
            f"将删除地图：{map_label}{root_note if remote_dir == save_map_path.rstrip('/') else ''}\n\n该操作不可恢复。",
            confirm_text="确认删除这张地图？",
        )
        if not confirmed:
            return False
        started = self.set_command(mapping.delete_history_map_command(self.profile(), remote_pgm, save_map_path))
        if started is False:
            self.set_mapping_operation("任务未启动", "blocked")
            self.preview_status.setText(task_not_started_text("地图删除"))
        return bool(started)
