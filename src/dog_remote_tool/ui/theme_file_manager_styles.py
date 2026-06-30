from __future__ import annotations


FILE_MANAGER_STYLESHEET = """
        QFrame#FileLocationBar {
            background: #ffffff;
            border: 1px solid #e3eaf3;
            border-radius: 8px;
        }
        QFrame#TransferPanel {
            background: #ffffff;
            border: 1px solid #e3eaf3;
            border-radius: 8px;
        }
        QPushButton#PathCrumbButton {
            min-height: 24px;
            padding: 2px 8px;
            background: transparent;
            border: 1px solid transparent;
            border-radius: 5px;
            color: #1e293b;
            font-weight: 600;
        }
        QPushButton#PathCrumbButton:hover {
            background: #eef6ff;
            border-color: #bfdbfe;
            color: #0f4c8a;
        }
        QLabel#PathCrumbMuted {
            color: #94a3b8;
            padding: 0 1px;
            font-weight: 600;
        }
"""
