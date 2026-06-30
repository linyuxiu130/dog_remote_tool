from __future__ import annotations


def bag_page_class():
    from dog_remote_tool.ui.pages.bag.page import BagPage

    return BagPage


def bag_page_module():
    from dog_remote_tool.ui.pages.bag import page as bag_page

    return bag_page
