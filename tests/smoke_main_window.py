from pathlib import Path
import sys

from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication

from dog_remote_tool.ui.main_window import MainWindow


EXPECTED_PAGES = ["总览", "遥控", "建图", "导航", "录包", "文件管理", "远程访问", "OTA", "诊断"]
STARTUP_FORBIDDEN_MODULES = {
    "dog_remote_tool.modules.bag",
    "dog_remote_tool.modules.control",
    "dog_remote_tool.modules.mapping",
    "dog_remote_tool.modules.localization",
    "dog_remote_tool.modules.navigation",
    "dog_remote_tool.modules.ota",
    "dog_remote_tool.modules.remote_access",
    "dog_remote_tool.ui.pages.file_manager.page",
    "dog_remote_tool.ui.pages.bag.page",
    "dog_remote_tool.ui.pages.control.page",
    "dog_remote_tool.ui.pages.mapping.page",
    "dog_remote_tool.ui.pages.route_network.page",
    "dog_remote_tool.ui.pages.navigation.page",
    "dog_remote_tool.ui.pages.ota.page",
    "dog_remote_tool.ui.pages.remote_access.page",
}


def main() -> int:
    app = QApplication.instance() or QApplication([])
    settings = QSettings()
    settings.setValue("main_window/current_page_title", "总览")
    settings.setValue("main_window/current_page_index", 0)
    window = MainWindow(Path.cwd())
    try:
        loaded_forbidden = sorted(module for module in STARTUP_FORBIDDEN_MODULES if module in sys.modules)
        if loaded_forbidden:
            raise AssertionError(f"heavy modules should not be imported during startup: {loaded_forbidden!r}")
        titles = [window.nav.item(index).text() for index in range(window.nav.count())]
        if titles != EXPECTED_PAGES:
            raise AssertionError(f"unexpected pages: {titles!r}")
        if window.stack.count() != len(EXPECTED_PAGES):
            raise AssertionError(f"unexpected stack count: {window.stack.count()}")
        if set(window._loaded_pages) != {window.nav.currentRow()}:
            raise AssertionError(f"startup should lazy-load only the selected page: {window._loaded_pages.keys()!r}")
        mapping_index = EXPECTED_PAGES.index("建图")
        window.nav.setCurrentRow(mapping_index)
        app.processEvents()
        if mapping_index not in window._loaded_pages:
            raise AssertionError("mapping page was not loaded on first navigation")
    finally:
        window.close()
        app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
