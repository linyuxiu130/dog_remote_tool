from __future__ import annotations

from dog_remote_tool.modules import control


KEYBOARD_REMOTE_PERSIST_PAGES = {"录包", "建图"}


def _control_page_module():
    from dog_remote_tool.ui.pages.control import page as control_page

    return control_page


class ControlLifecycleMixin:
    def on_control_profile_changed(self, _profile) -> None:
        self.stop_video_stream()
        self.stop_gamepad_stream()
        self.stop_l1_sdk_stream()
        self.stop_l2_telemetry_stream()
        arc_status_slot = getattr(self, "arc_status_slot", None)
        if arc_status_slot is not None:
            arc_status_slot.stop_async()
        if hasattr(self, "arc_action_btn"):
            self.set_remote_arc_action({}, "读取中")
        self.refresh_video_sources()
        self.update_l2_nav_target()

    def activate_page(self) -> None:
        control_page = _control_page_module()
        if self.page_active:
            return
        self.page_active = True
        self.update_l2_nav_target()
        if self.arc_controls_supported():
            control_page.QTimer.singleShot(100, self.refresh_remote_arc_status)
        self._auto_start_remote_control()

    def _auto_start_remote_control(self) -> None:
        control_page = _control_page_module()
        profile = self.profile()
        if control.l2_control_profile(profile) or control.robot_sdk_control_profile(profile):
            if not self.keyboard_stream_running():
                control_page.QTimer.singleShot(150, self._start_l2_remote_if_active)
            if not self.video_stream_running("body"):
                control_page.QTimer.singleShot(250, self._start_body_video_if_active)
        elif control.l1_control_profile(profile):
            if not self.keyboard_stream_running():
                control_page.QTimer.singleShot(150, self._start_l1_remote_if_active)
            if not self.video_stream_running("l1"):
                control_page.QTimer.singleShot(250, self._start_l1_video_if_active)

    def _start_l2_remote_if_active(self) -> None:
        if self.page_active and not self.keyboard_stream_running():
            self.start_gamepad_stream()

    def _start_l1_remote_if_active(self) -> None:
        if self.page_active and not self.keyboard_stream_running():
            self.start_l1_sdk_stream()

    def _start_body_video_if_active(self) -> None:
        if self.page_active and not self.video_stream_running("body"):
            self.start_video_stream("body")

    def _start_l1_video_if_active(self) -> None:
        if self.page_active and not self.video_stream_running("l1"):
            self.start_video_stream("l1")

    def keyboard_stream_running(self) -> bool:
        control_page = _control_page_module()
        processes = (self.gamepad_stream_process, self.l1_sdk_stream_process)
        return any(process is not None and process.state() != control_page.QProcess.NotRunning for process in processes)

    def deactivate_page(self, next_page_title: str = "") -> None:
        control_page = _control_page_module()
        self.page_active = False
        arc_status_slot = getattr(self, "arc_status_slot", None)
        if arc_status_slot is not None:
            arc_status_slot.stop_async()
        self.stop_video_stream()
        self.stop_l2_telemetry_stream()
        keyboard_was_running = self.keyboard_stream_running()
        keep_keyboard_remote = keyboard_was_running and next_page_title in KEYBOARD_REMOTE_PERSIST_PAGES
        if keep_keyboard_remote:
            if self.gamepad_stream_process and self.gamepad_stream_process.state() != control_page.QProcess.NotRunning:
                self.send_gamepad_neutral()
            if self.l1_sdk_stream_process and self.l1_sdk_stream_process.state() != control_page.QProcess.NotRunning:
                self.l1_pressed_keys.clear()
                self.l1_sdk_last_vector = None
                self._write_l1_sdk_stream({"cmd": "neutral"})
            self.runner.output.emit(f"[遥控] 切换到{next_page_title}页面，键盘遥控保持开启。\n")
        else:
            self.stop_gamepad_stream()
            self.stop_l1_sdk_stream()
            self._set_control_low_load(False)
        if keyboard_was_running and not keep_keyboard_remote and next_page_title in {"建图", "导航"}:
            self.runner.output.emit(f"[遥控] 切换到{next_page_title}页面，已停止键盘遥控并释放控制权。\n")

    def shutdown_processes(self) -> None:
        control_page = _control_page_module()
        self.page_active = False
        app = control_page.QApplication.instance()
        if app is not None:
            try:
                app.removeEventFilter(self)
            except TypeError:
                pass
        arc_status_slot = getattr(self, "arc_status_slot", None)
        if arc_status_slot is not None:
            arc_status_slot.stop()
        self.stop_video_stream()
        self.stop_l2_telemetry_stream(wait_for_exit=True)
        self.stop_gamepad_stream(wait_for_exit=True)
        self.stop_l1_sdk_stream(wait_for_exit=True)
