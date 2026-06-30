from __future__ import annotations


def navigation_page_class():
    from dog_remote_tool.ui.pages.navigation.page import NavigationPage

    return NavigationPage


def navigation_page_module():
    from dog_remote_tool.ui.pages.navigation import page as navigation_page

    return navigation_page
