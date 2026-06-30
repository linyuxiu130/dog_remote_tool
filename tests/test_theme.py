from dog_remote_tool.ui import theme
from dog_remote_tool.ui import dialogs
from dog_remote_tool.ui import message_dialogs
from dog_remote_tool.ui.theme_bag_styles import BAG_STYLESHEET
from dog_remote_tool.ui.theme_base_styles import BASE_STYLESHEET
from dog_remote_tool.ui.theme_button_styles import BUTTON_STYLESHEET
from dog_remote_tool.ui.theme_control_styles import CONTROL_STYLESHEET
from dog_remote_tool.ui.theme_dialog_styles import DIALOG_STYLESHEET
from dog_remote_tool.ui.theme_file_manager_styles import FILE_MANAGER_STYLESHEET
from dog_remote_tool.ui.theme_general_widget_styles import GENERAL_WIDGET_STYLESHEET
from dog_remote_tool.ui.theme_input_styles import INPUT_STYLESHEET
from dog_remote_tool.ui.theme_main_window_styles import MAIN_WINDOW_STYLESHEET
from dog_remote_tool.ui.theme_ota_styles import OTA_STYLESHEET
from dog_remote_tool.ui.theme_route_styles import ROUTE_STYLESHEET
from dog_remote_tool.ui.theme_scrollbar_styles import SCROLLBAR_STYLESHEET
from dog_remote_tool.ui.theme_status_panel_styles import STATUS_PANEL_STYLESHEET
from dog_remote_tool.ui.theme_user_console_styles import USER_CONSOLE_STYLESHEET
from dog_remote_tool.ui.theme_view_styles import VIEW_STYLESHEET
from dog_remote_tool.ui.theme_styles import APP_STYLESHEET


class _FakeApp:
    def __init__(self) -> None:
        self.style = None
        self.stylesheet = None

    def setStyle(self, style: str) -> None:
        self.style = style

    def setStyleSheet(self, stylesheet: str) -> None:
        self.stylesheet = stylesheet


def test_apply_theme_uses_shared_stylesheet_and_dialog_polish(monkeypatch):
    app = _FakeApp()
    polished = []
    monkeypatch.setattr(theme, "install_dialog_polish", polished.append)

    theme.apply_theme(app)

    assert app.style == "Fusion"
    assert app.stylesheet is APP_STYLESHEET
    assert "QMainWindow, QWidget" in app.stylesheet
    assert "QScrollBar::add-line:horizontal" in app.stylesheet
    assert polished == [app]


