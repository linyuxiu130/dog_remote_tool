from __future__ import annotations

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


APP_STYLESHEET = BASE_STYLESHEET + """
""" + DIALOG_STYLESHEET + """
""" + BAG_STYLESHEET + """
""" + CONTROL_STYLESHEET + """
""" + ROUTE_STYLESHEET + """
""" + FILE_MANAGER_STYLESHEET + """
""" + STATUS_PANEL_STYLESHEET + """
""" + USER_CONSOLE_STYLESHEET + """
""" + OTA_STYLESHEET + """
""" + MAIN_WINDOW_STYLESHEET + """
""" + BUTTON_STYLESHEET + """
""" + INPUT_STYLESHEET + """
""" + VIEW_STYLESHEET + """
""" + SCROLLBAR_STYLESHEET + """
""" + GENERAL_WIDGET_STYLESHEET + """
"""
