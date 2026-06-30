from __future__ import annotations


MAIN_WINDOW_STYLESHEET = """
        QFrame#SideBar {
            background: #17324d;
            border: none;
        }
        QFrame#Workspace {
            background: #f5f8fc;
            border: none;
        }
        QListWidget#Nav {
            background: #17324d;
            color: #d7e4f0;
            border: none;
            padding: 6px 4px 8px 4px;
            outline: 0;
            font-size: 10.5pt;
            font-weight: 500;
        }
        QListWidget#Nav::item {
            min-height: 38px;
            padding-left: 14px;
            padding-right: 10px;
            border-left: 3px solid transparent;
            border-radius: 8px;
        }
        QListWidget#Nav::item:hover {
            background: #203f5f;
            color: #ffffff;
        }
        QListWidget#Nav::item:selected {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2f73a7, stop:1 #234f78);
            border-left: 3px solid #a9ddff;
            color: #ffffff;
            font-weight: 600;
        }
        QListWidget#Nav::item:selected:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #347fb6, stop:1 #285985);
            border-left: 3px solid #c7e9ff;
        }
        QFrame#RuntimePanel {
            background: #17324d;
            border: 1px solid #203f5f;
            border-radius: 9px;
        }
        QLabel#SideMetaLabel {
            color: #b7c7da;
            font-size: 8.5pt;
            font-weight: 600;
        }
        QLabel#SideMetaValue {
            color: #ffffff;
            font-size: 10pt;
            font-weight: 700;
        }
        QFrame#LogPanelFrame {
            background: #f8fbff;
            border: 1px solid #d6e3f0;
            border-radius: 10px;
        }
"""
