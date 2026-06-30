from __future__ import annotations


SCROLLBAR_STYLESHEET = """
        QScrollBar:vertical {
            background: #f3f7fb;
            width: 10px;
            margin: 0;
        }
        QScrollBar::handle:vertical {
            background: #c3d0df;
            min-height: 28px;
            border-radius: 5px;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0;
        }
        QScrollBar:horizontal {
            background: #f3f7fb;
            height: 10px;
            margin: 0;
        }
        QScrollBar::handle:horizontal {
            background: #c3d0df;
            min-width: 28px;
            border-radius: 5px;
        }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
            width: 0;
        }
"""
