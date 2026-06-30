from __future__ import annotations

import shutil
from pathlib import Path

from PyQt5.QtGui import QPixmap

from dog_remote_tool.modules import mapping
from dog_remote_tool.modules.mapping import pgm_editor
from dog_remote_tool.ui.command_confirm import confirm_command_spec
from dog_remote_tool.ui.map_helpers import local_map_preview_dir
from dog_remote_tool.ui.pages.mapping.pgm_editor_dialog import PgmEditorDialog


def _mapping_page_class():
    from dog_remote_tool.ui.pages.mapping.page import MappingPage

    return MappingPage


def _mapping_page_module():
    from dog_remote_tool.ui.pages.mapping import page as mapping_page

    return mapping_page


def _show_mapping_conflict_if_idle(page) -> None:
    if not getattr(page, "mapping_operation_active", False):
        page.set_mapping_operation("任务运行中", "blocked")


def _stop_inflight_status_probe(page) -> None:
    slot = getattr(page, "status_slot", None)
    if slot is not None and callable(getattr(slot, "stop", None)):
        slot.stop()


class MappingActionsMixin:
    def show_mapping_next_steps(self, hint: str) -> None:
        self.next_steps_hint.setText(hint)
        self.next_steps_box.setToolTip(hint)
        self.next_steps_box.show()

    def hide_mapping_next_steps(self) -> None:
        self.next_steps_box.hide()

    def _clear_mapping_run_tracking(self) -> None:
        self.mapping_runner_task_id = 0

    def _handle_mapping_run_not_started(self) -> None:
        self._clear_mapping_run_tracking()
        self.mapping_operation_active = False
        self.set_mapping_operation("任务未启动", "blocked")

    def mapping_values(self) -> tuple[str, str, str, str]:
        profile = self.profile()
        return (
            self.sensor_type.text().strip() or mapping.default_sensor_type(profile),
            self.save_map_path.text().strip() or mapping.default_save_map_path(profile),
            self.calibration_file_path.text().strip() or mapping.default_calibration_file_path(profile),
            self.arc_calibration_file_path.text().strip() or mapping.default_arc_calibration_file_path(profile),
        )

    def local_preview_dir(self, remote_pgm: str, profile=None) -> Path:
        profile = profile or self.profile()
        root = Path(mapping.DEFAULT_LOCAL_MAP_DIR)
        return local_map_preview_dir(profile.key, profile.host, remote_pgm, str(root))

    def open_preview_image(self, title: str, pixmap: QPixmap | None, image_path: str) -> bool:
        return _mapping_page_module().show_zoomable_pixmap(self, title, pixmap, image_path, fullscreen=True)

    def open_map_pgm_editor(self) -> bool:
        mapping_page = _mapping_page_module()
        remote_pgm = self.selected_remote_map_pgm()
        if not remote_pgm:
            mapping_page.QMessageBox.information(self, "未选择地图", "请先选择一个历史 map.pgm。")
            return False
        preview_file = Path(getattr(self, "preview_file", "") or "")
        if not preview_file.is_file() or self.preview_remote_pgm != remote_pgm:
            mapping_page.QMessageBox.information(self, "地图未加载", "请先等待当前选中地图预览加载完成。")
            return False
        try:
            dialog = PgmEditorDialog(
                preview_file,
                lambda pgm_bytes, remote=remote_pgm, local=preview_file: self.save_edited_map_pgm(
                    pgm_bytes,
                    local,
                    remote,
                ),
                self,
            )
        except Exception as exc:
            mapping_page.QMessageBox.warning(self, "无法打开编辑器", f"map.pgm 读取失败：{exc}")
            return False
        dialog.showFullScreen()
        dialog.exec_()
        return True

    def save_edited_map_pgm(self, pgm_bytes: bytes, local_pgm: Path, remote_pgm: str) -> bool:
        mapping_page = _mapping_page_module()
        spec = mapping.upload_edited_map_pgm_command(self.profile(), str(local_pgm), remote_pgm)
        conflict = self.runner.conflict_reason(spec)
        if conflict:
            _show_mapping_conflict_if_idle(self)
            self.runner.output.emit(f"[WARN] 当前已有任务运行，未保存编辑地图。{conflict}\n")
            return False
        if not confirm_command_spec(self, spec):
            return False
        try:
            backup = pgm_editor.local_backup_path(local_pgm)
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(local_pgm, backup)
            local_pgm.write_bytes(pgm_bytes)
        except OSError as exc:
            mapping_page.QMessageBox.warning(self, "本地保存失败", f"无法写入编辑后的 map.pgm：{exc}")
            return False
        pixmap = QPixmap(str(local_pgm))
        if pixmap.isNull():
            try:
                shutil.copy2(backup, local_pgm)
            except OSError:
                pass
            mapping_page.QMessageBox.warning(self, "本地保存失败", "编辑后的 map.pgm 无法被 Qt 读取，已尝试恢复本地备份。")
            return False
        self.preview_pixmap = pixmap
        self.update_map_card_thumbnail(remote_pgm, local_pgm.parent)
        self.current_spec = None
        self.mapping_operation_active = True
        self.set_mapping_operation("保存编辑地图中", "running")
        self.runner.output.emit(f"[INFO] 本地 map.pgm 原图备份：{backup}\n")
        self.runner.output.emit(f"[INFO] 正在保存编辑地图到远端：{remote_pgm}\n")
        task_id = self.runner.run(spec, spec.display_command or spec.title)
        if task_id is None:
            try:
                shutil.copy2(backup, local_pgm)
                self.preview_pixmap = QPixmap(str(local_pgm))
                self.update_map_card_thumbnail(remote_pgm, local_pgm.parent)
            except OSError:
                pass
            self._handle_mapping_run_not_started()
            return False
        self.mapping_runner_task_id = task_id
        return True

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)

    def make_finish_mapping(self) -> bool:
        _sensor_type, save_map_path, _calibration_file_path, _arc_calibration_file_path = self.mapping_values()
        spec = mapping.finish_mapping_command(self.profile(), save_map_path)
        conflict = self.runner.conflict_reason(spec)
        if conflict:
            _show_mapping_conflict_if_idle(self)
            self.runner.output.emit(f"[WARN] 当前已有任务运行，未发送结束保存请求。{conflict}\n")
            return False
        self.current_spec = None
        hide_next_steps = getattr(self, "hide_mapping_next_steps", None)
        if callable(hide_next_steps):
            hide_next_steps()
        self.mapping_operation_active = True
        self.set_mapping_operation("结束保存中", "saving")
        self.runner.output.emit("[INFO] 建图：已请求结束保存。\n")
        _stop_inflight_status_probe(self)
        task_id = self.runner.run(spec, spec.title)
        if task_id is None:
            self._handle_mapping_run_not_started()
            return False
        self.mapping_runner_task_id = task_id
        return True

    def make_start_mapping(self) -> bool:
        sensor_type, save_map_path, calibration_file_path, arc_calibration_file_path = self.mapping_values()
        spec = mapping.start_mapping_command(
            self.profile(),
            sensor_type,
            save_map_path,
            calibration_file_path,
            arc_calibration_file_path,
        )
        conflict = self.runner.conflict_reason(spec)
        if conflict:
            _show_mapping_conflict_if_idle(self)
            self.runner.output.emit(f"[WARN] 当前已有任务运行，未发送开始建图请求。{conflict}\n")
            return False
        hide_next_steps = getattr(self, "hide_mapping_next_steps", None)
        if callable(hide_next_steps):
            hide_next_steps()
        self.mapping_operation_active = True
        self.mapping_runner_task_id = 0
        self.set_mapping_operation("开始建图中", "running")
        self.current_spec = None
        self.runner.output.emit("[INFO] 建图：已请求开始建图。\n")
        _stop_inflight_status_probe(self)
        task_id = self.runner.run(spec, spec.title)
        if task_id is None:
            self._handle_mapping_run_not_started()
            return False
        self.mapping_runner_task_id = task_id
        return True

    def make_cancel_mapping(self) -> bool:
        mapping_page = _mapping_page_module()
        status_age = mapping_page.time.monotonic() - self.last_mapping_status_at if self.last_mapping_status_at else 999999.0
        if not mapping.is_mapping_active_alg_status(
            self.profile(),
            self.last_mapping_alg_status,
        ):
            current = self.last_mapping_alg_status or "unknown"
            mapping_page.QMessageBox.information(
                self,
                "当前未处于可取消建图状态",
                f"最近一次远端状态不是建图中，未发送取消请求。\n当前远端状态：{current}\n请先刷新状态确认。",
            )
            self.runner.output.emit(f"[WARN] 未发送取消建图请求：最近一次远端 alg 状态 {current} 不是建图中。\n")
            self.refresh_mapping_status()
            return False
        if status_age > 30:
            mapping_page.QMessageBox.information(
                self,
                "状态已过期",
                f"最近一次远端 alg 状态 {self.last_mapping_alg_status} 已超过 30 秒，请先刷新状态确认。",
            )
            self.runner.output.emit(
                f"[WARN] 未发送取消建图请求：最近一次远端 alg 状态 {self.last_mapping_alg_status} 已过期。\n"
            )
            self.refresh_mapping_status()
            return False
        spec = mapping.cancel_mapping_command(self.profile())
        conflict = self.runner.conflict_reason(spec)
        if conflict:
            _show_mapping_conflict_if_idle(self)
            self.runner.output.emit(f"[WARN] 当前已有任务运行，未发送取消建图请求。{conflict}\n")
            return False
        self.mapping_operation_active = True
        self.mapping_runner_task_id = 0
        self.set_mapping_operation("取消建图中", "blocked")
        self.current_spec = None
        self.runner.output.emit("[INFO] 建图：已请求取消建图。\n")
        _stop_inflight_status_probe(self)
        task_id = self.runner.run(spec, spec.title)
        if task_id is None:
            self._handle_mapping_run_not_started()
            return False
        self.mapping_runner_task_id = task_id
        return True

    def run_current(self) -> bool:
        if not self.current_spec:
            return False
        spec = self.current_spec
        conflict = self.runner.conflict_reason(spec)
        if conflict:
            _show_mapping_conflict_if_idle(self)
            self.runner.output.emit(f"[WARN] {conflict}\n")
            return False
        if not _mapping_page_module().confirm_command_spec(self, spec):
            return False
        self.mapping_operation_active = True
        self.set_mapping_operation(spec.title, "running")
        task_id = self.runner.run(spec, self.display_command_for_log())
        if task_id is None:
            self._handle_mapping_run_not_started()
            return False
        self.mapping_runner_task_id = task_id
        return True

    def display_command_for_log(self) -> str:
        if not self.current_spec:
            return ""
        return self.current_spec.title
