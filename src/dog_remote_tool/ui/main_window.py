from __future__ import annotations

import inspect
from pathlib import Path

from PyQt5.QtCore import QSettings, QTimer, Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.runner import ProcessRunner
from ..core.log_format import log_line
from ..core.task_outcomes import mapping_save_continues_after_local_stop
from . import main_window_restart
from .components import DeviceBar, LogPanel
from .main_window_layout import MainWindowLayoutMixin
from .main_window_logs import MainWindowLogsMixin
from .main_window_pages import MainWindowPagesMixin
from .main_window_profiles import MainWindowProfilesMixin
from .runtime_info import source_runtime_detail
from .user_console import TaskToast


MainWindowRestartMixin = main_window_restart.MainWindowRestartMixin
RESTART_CONFIRM_EXEMPT_TITLES = main_window_restart.RESTART_CONFIRM_EXEMPT_TITLES


class MainWindow(
    MainWindowLayoutMixin,
    MainWindowRestartMixin,
    MainWindowProfilesMixin,
    MainWindowLogsMixin,
    MainWindowPagesMixin,
    QMainWindow,
):
    def __init__(self, app_root: Path) -> None:
        super().__init__()
        self.app_root = app_root
        self.setWindowTitle("远程调试平台")
        self._apply_adaptive_window_size()
        self._active_page_index = -1
        self._closing = False
        self._skip_page_shutdown_for_smoke = False
        self._user_adjusted_log_splitter = False
        self._fitting_log_splitter = False
        self.log_expanded = False
        self.settings = QSettings()

        self.runner = ProcessRunner(self)
        self.runner.output.connect(self._append_log)
        self.runner.technical_output.connect(self._append_technical_log)
        self.runner.state_changed.connect(self._runner_state)
        self.runner.finished.connect(self._runner_finished)
        self.runner.task_started.connect(self._runner_task_started)
        self.runner.task_finished_detail.connect(self._runner_task_finished_detail)

        self._loaded_pages: dict[int, QWidget] = {}
        self.file_manager_page: QWidget | None = None
        self.log_fullscreen_dialog: QDialog | None = None
        self.log_fullscreen_view: LogPanel | None = None
        self.log_fullscreen_technical_view: LogPanel | None = None

        root = QWidget()
        main = QHBoxLayout(root)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("SideBar")
        sidebar_width = self._adaptive_sidebar_width()
        sidebar.setFixedWidth(sidebar_width)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 16, 12, 12)
        sidebar_layout.setSpacing(10)

        self.nav = QListWidget()
        self.nav.setObjectName("Nav")
        self.nav.setSpacing(4)
        self.nav.setUniformItemSizes(True)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        sidebar_layout.addWidget(self.nav, 1)

        runtime_panel = QFrame()
        runtime_panel.setObjectName("RuntimePanel")
        runtime_layout = QVBoxLayout(runtime_panel)
        runtime_layout.setContentsMargins(10, 9, 10, 9)
        runtime_layout.setSpacing(3)
        runtime_label = QLabel("运行模式")
        runtime_label.setObjectName("SideMetaLabel")
        runtime_value = QLabel("本机控制台")
        runtime_value.setObjectName("SideMetaValue")
        runtime_layout.addWidget(runtime_label)
        runtime_layout.addWidget(runtime_value)
        sidebar_layout.addWidget(runtime_panel)
        main.addWidget(sidebar)

        content = QFrame()
        content.setObjectName("Workspace")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(12, 12, 12, 12)
        content_layout.setSpacing(12)
        self.device_bar = DeviceBar(self.runner)
        content_layout.addWidget(self.device_bar)

        self.stack = QStackedWidget()
        self.main_splitter = QSplitter(Qt.Vertical)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.addWidget(self.stack)

        log_panel = QFrame()
        self.log_panel = log_panel
        log_panel.setObjectName("LogPanelFrame")
        log_panel.setMinimumHeight(52)
        log_layout = QVBoxLayout(log_panel)
        log_layout.setContentsMargins(10, 8, 10, 10)
        log_layout.setSpacing(6)
        log_header = QHBoxLayout()
        log_title = QLabel("执行日志")
        log_title.setObjectName("FieldLabel")
        self.log_summary = QLabel("暂无执行日志")
        self.log_summary.setObjectName("Muted")
        self.log_summary.setWordWrap(False)
        self.log_summary.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.log_toggle_btn = QPushButton("打开日志")
        self.log_toggle_btn.setObjectName("SoftPrimary")
        self.log_toggle_btn.setMinimumWidth(82)
        self.log_toggle_btn.clicked.connect(self.toggle_log_panel)
        self.restart_tool_btn = QPushButton("重启工具")
        self.restart_tool_btn.setObjectName("SoftPrimary")
        self.restart_tool_btn.setMinimumWidth(82)
        self.restart_tool_btn.setToolTip("关闭当前窗口并重新打开工具")
        self.restart_tool_btn.clicked.connect(self.restart_tool)
        fullscreen_log = QPushButton("全屏")
        fullscreen_log.setObjectName("SoftPrimary")
        fullscreen_log.setMinimumWidth(72)
        fullscreen_log.setToolTip("全屏查看执行日志")
        fullscreen_log.clicked.connect(self.open_log_fullscreen)
        clear_log = QPushButton("清空")
        clear_log.clicked.connect(self.clear_logs)
        log_header.addWidget(log_title)
        log_header.addWidget(self.log_summary, 1)
        log_header.addStretch(1)
        log_header.addWidget(self.log_toggle_btn)
        log_header.addWidget(self.restart_tool_btn)
        log_header.addWidget(fullscreen_log)
        log_header.addWidget(clear_log)
        self.log = LogPanel()
        self.log.setMinimumHeight(64)
        self.log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.log.hide()
        self.technical_log = LogPanel(self, mode="technical")
        self.technical_log.hide()
        log_layout.addLayout(log_header)
        log_layout.addWidget(self.log)
        self.main_splitter.addWidget(log_panel)
        self.main_splitter.setStretchFactor(0, 3)
        self.main_splitter.setStretchFactor(1, 2)
        self.main_splitter.splitterMoved.connect(self._mark_log_splitter_adjusted)
        content_layout.addWidget(self.main_splitter, 1)
        main.addWidget(content, 1)
        self.setCentralWidget(root)
        self.task_toast = TaskToast(root)

        self.page_specs = self._build_page_specs()
        for spec in self.page_specs:
            self.nav.addItem(QListWidgetItem(spec.title))
            self.stack.addWidget(self._make_page_placeholder(spec.title))

        self.nav.currentRowChanged.connect(self._select_page)
        self.stack.currentChanged.connect(self._page_changed)
        self.device_bar.profile_changed.connect(self._profile_changed_for_current_page)
        self.nav.setCurrentRow(self._saved_page_index())
        self._select_page(self.nav.currentRow())
        self._page_changed(self.stack.currentIndex())
        self._append_log(log_line("info", "远程调试平台已启动。"))
        self._append_log(log_line("info", f"远程调试平台：{source_runtime_detail()}"))
        QTimer.singleShot(0, self._position_task_toast)
        QTimer.singleShot(0, self._fit_log_splitter_to_window)

    def _select_page(self, index: int) -> None:
        if not (0 <= index < len(self.page_specs)):
            return
        self._ensure_page_profile(index)
        self._apply_page_platform_restrictions(index)
        if index not in self._loaded_pages:
            page = self.page_specs[index].factory()
            self._loaded_pages[index] = page
            old = self.stack.widget(index)
            self.stack.removeWidget(old)
            old.deleteLater()
            self.stack.insertWidget(index, page)
        self.stack.setCurrentIndex(index)

    def closeEvent(self, event) -> None:
        self._closing = True
        if self.log_fullscreen_dialog is not None:
            self.log_fullscreen_dialog.close()
        self.runner.shutdown()
        self.device_bar.save_current_profile()
        self.device_bar.shutdown_processes()
        if not self._skip_page_shutdown_for_smoke:
            for page in list(self._loaded_pages.values()):
                shutdown = getattr(page, "shutdown_processes", None)
                if callable(shutdown):
                    shutdown()
        super().closeEvent(event)

    def _saved_page_index(self) -> int:
        saved_title = self.settings.value("main_window/current_page_title", "", type=str)
        if saved_title:
            for index in range(self.nav.count()):
                item = self.nav.item(index)
                if item is not None and item.text() == saved_title:
                    return index
            return 0
        saved_index = self.settings.value("main_window/current_page_index", 0, type=int)
        if 0 <= saved_index < self.stack.count():
            return saved_index
        return 0

    def _page_changed(self, index: int) -> None:
        if index == self._active_page_index:
            return
        if self._active_page_index in self._loaded_pages:
            old_page = self._loaded_pages[self._active_page_index]
            deactivate = getattr(old_page, "deactivate_page", None)
            if callable(deactivate):
                next_title = self.page_specs[index].title if 0 <= index < len(self.page_specs) else ""
                parameters = inspect.signature(deactivate).parameters
                if "next_page_title" in parameters:
                    deactivate(next_page_title=next_title)
                else:
                    deactivate()
        self._stop_keyboard_remote_outside_recording(index)
        self._active_page_index = index
        if 0 <= index < self.stack.count():
            self.settings.setValue("main_window/current_page_title", self.page_specs[index].title)
            self.settings.setValue("main_window/current_page_index", index)
            page = self._loaded_pages.get(index)
            if page is not None:
                activate = getattr(page, "activate_page", None)
                if callable(activate):
                    activate()

    def _stop_keyboard_remote_outside_recording(self, next_index: int) -> None:
        if not (0 <= next_index < len(self.page_specs)):
            return
        next_title = self.page_specs[next_index].title
        if next_title in {"遥控", "录包", "建图"}:
            return
        for page_index, page in list(self._loaded_pages.items()):
            if not (0 <= page_index < len(self.page_specs)):
                continue
            if self.page_specs[page_index].title != "遥控":
                continue
            keyboard_stream_running = getattr(page, "keyboard_stream_running", None)
            deactivate = getattr(page, "deactivate_page", None)
            if callable(keyboard_stream_running) and callable(deactivate) and keyboard_stream_running():
                deactivate(next_page_title=next_title)

    def _runner_state(self, _running: bool) -> None:
        return

    def _runner_finished(self, _code: int) -> None:
        return

    def _runner_task_started(self, _task_id: int, title: str) -> None:
        if self._closing:
            return
        if self._is_video_prepare_title(title):
            return
        self._show_task_toast("任务已开始", self._user_task_title(title), "running", duration_ms=2200)

    def _runner_task_finished_detail(self, _task_id: int, code: int, title: str) -> None:
        if self._closing:
            return
        if code == 0 and self._is_video_prepare_title(title):
            pass
        elif code == 0:
            self._show_task_toast("任务已完成", self._user_task_title(title), "success")
        elif mapping_save_continues_after_local_stop(title, code):
            self._show_task_toast("保存完成", "建图保存已提交，正在刷新状态和历史地图。", "success")
        else:
            self._show_task_toast("任务失败", f"{self._user_task_title(title)}，请查看下方日志。", "danger", duration_ms=5200)
        if not title.startswith("执行：ARC "):
            return
        if code == 0 and title == "执行：ARC 出桩":
            self.device_bar.clear_battery_charging_hint()
        elif code == 0 and title in {"执行：ARC 回充", "执行：ARC 有图回充"}:
            mark_charging = getattr(self.device_bar, "mark_battery_charging_hint", None)
            if callable(mark_charging):
                mark_charging()
        for delay in (300, 3_000, 8_000):
            QTimer.singleShot(delay, lambda: None if self._closing else self.device_bar.refresh_battery(force=True))

    @staticmethod
    def _is_video_prepare_title(title: str) -> bool:
        return title == "准备视频" or title.startswith("准备 RTSP 视频:")

    def _show_task_toast(self, title: str, detail: str, tone: str, *, duration_ms: int = 3600) -> None:
        toast = self._task_toast_widget()
        if toast is None:
            return
        toast.show_message(title, detail, tone, duration_ms=duration_ms)
        self._position_task_toast()

    def _position_task_toast(self) -> None:
        toast = self._task_toast_widget()
        if toast is not None:
            toast.reposition()

    def _task_toast_widget(self) -> TaskToast | None:
        try:
            toast = getattr(self, "task_toast", None)
        except RuntimeError:
            return None
        return toast

    def _user_task_title(self, title: str) -> str:
        display = (title or "执行任务").strip()
        if display.startswith("执行："):
            display = display.removeprefix("执行：")
        return display or "执行任务"
