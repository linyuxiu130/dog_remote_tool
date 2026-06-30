from __future__ import annotations

from dog_remote_tool.core.task_outcomes import mapping_save_continues_after_local_stop


def _save_wait_was_interrupted(code: int, title: str) -> bool:
    return mapping_save_continues_after_local_stop(title, code)


class MappingTransferRunnerMixin:
    def handle_mapping_runner_finished(self, task_id: int, code: int, title: str) -> None:
        if task_id != self.mapping_runner_task_id:
            return
        self.mapping_runner_task_id = 0
        if title == "保存编辑地图":
            if code == 0:
                self.set_mapping_operation("编辑地图已保存", "done")
                self.preview_status.setText("编辑后的 map.pgm 已保存到远端，本地原图备份已保留。")
                if hasattr(self, "edit_map_pgm_button"):
                    self.edit_map_pgm_button.setEnabled(bool(getattr(self, "preview_pixmap", None)))
            else:
                self.set_mapping_operation("编辑地图保存失败", "blocked")
                self.preview_status.setText("远端保存失败；本地已保留编辑后的 map.pgm 和原图备份，请查看日志。")
            self.mapping_operation_active = False
            return
        if title == "删除选中地图":
            if code == 0:
                self.set_mapping_operation("删除完成", "done")
                self.preview_status.setText("地图已删除，正在刷新历史图列表")
                self.preview_remote_pgm = ""
                self.fetching_preview_remote_pgm = ""
                self.preview_file = ""
                self.preview_pixmap = None
                self.refresh_map_list(silent=False, force_preview=True, force_latest=True)
            else:
                self.set_mapping_operation("删除失败", "blocked")
                self.preview_status.setText("地图删除失败，请查看执行日志")
            self.mapping_operation_active = False
            return
        if not self.mapping_operation_active:
            return
        if code == 0 and title == "开始建图":
            self.set_mapping_operation("建图中", "running")
        elif code == 0 and title == "结束并保存建图":
            self.set_mapping_operation("保存完成", "done")
            show_next_steps = getattr(self, "show_mapping_next_steps", None)
            if callable(show_next_steps):
                show_next_steps("地图已保存，可继续编辑路网或进入导航。")
            self.preview_status.setText("建图已保存")
        elif _save_wait_was_interrupted(code, title):
            self.set_mapping_operation("保存确认中", "saving")
            self.preview_status.setText("远端已接收结束保存，本地等待被中断；请刷新状态确认最新地图。")
        else:
            self.set_mapping_operation("完成" if code == 0 else "失败", "done" if code == 0 else "blocked")
        self.mapping_operation_active = _save_wait_was_interrupted(code, title)
