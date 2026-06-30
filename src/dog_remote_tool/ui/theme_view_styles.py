from __future__ import annotations


VIEW_STYLESHEET = """
        QListWidget {
            background: #ffffff;
            border: 1px solid #d7e1ed;
            border-radius: 8px;
            padding: 6px;
            outline: 0;
            alternate-background-color: #f8fafc;
        }
        QListWidget::item {
            min-height: 25px;
            padding: 4px 7px;
            border-radius: 5px;
        }
        QListWidget::item:hover {
            background: #eef6ff;
        }
        QListWidget::item:selected {
            background: #dbeafe;
            color: #10233f;
        }
        QTableWidget {
            background: #ffffff;
            color: #1f2f45;
            border: 1px solid #cfdbea;
            border-radius: 8px;
            gridline-color: #e1e9f3;
            selection-background-color: #cfe6ff;
            selection-color: #0e243f;
            alternate-background-color: #f5f9fd;
            font-size: 10pt;
        }
        QTableWidget::item {
            padding: 7px 8px;
        }
        QTreeWidget {
            background: #ffffff;
            border: 1px solid #d7e1ed;
            border-radius: 8px;
            selection-background-color: #dbeafe;
            selection-color: #10233f;
            alternate-background-color: #f8fafc;
            outline: 0;
        }
        QTreeWidget::item {
            min-height: 28px;
            padding: 4px 7px;
        }
        QTreeWidget::item:hover {
            background: #eef6ff;
        }
        QTableView#RemoteFileTreeView {
            background: #ffffff;
            color: #1f2f45;
            border: 1px solid #cfdbea;
            border-radius: 8px;
            selection-background-color: #cfe6ff;
            selection-color: #0e243f;
            alternate-background-color: #f5f9fd;
            outline: 0;
            font-size: 10pt;
        }
        QTableView#RemoteFileTreeView::item {
            padding: 6px 8px;
        }
        QTableView#RemoteFileTreeView::item:hover {
            background: #eef6ff;
        }
        QListView#RemoteFileIconView {
            background: #ffffff;
            border: 1px solid #d7e1ed;
            border-radius: 8px;
            padding: 16px;
            outline: 0;
        }
        QListView#RemoteFileIconView::item {
            padding: 0px;
            border-radius: 8px;
            color: #10233f;
        }
        QListView#RemoteFileIconView::item:hover {
            background: transparent;
        }
        QListView#RemoteFileIconView::item:selected {
            background: transparent;
            color: #10233f;
        }
        QHeaderView::section {
            background: #e8f1fb;
            color: #33465d;
            border: none;
            border-right: 1px solid #d9e4f0;
            border-bottom: 1px solid #cfdbea;
            padding: 7px 8px;
            font-weight: 800;
        }
"""
