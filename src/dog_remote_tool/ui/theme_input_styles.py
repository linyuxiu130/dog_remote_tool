from __future__ import annotations


INPUT_STYLESHEET = """
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {
            background: #ffffff;
            border: 1px solid #d7e1ed;
            border-radius: 8px;
            padding: 5px 9px;
            selection-background-color: #2f6fa8;
        }
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QTextEdit:focus, QPlainTextEdit:focus {
            border-color: #4f93d8;
        }
        QSlider::groove:horizontal {
            height: 8px;
            border-radius: 4px;
            background: #d8e1ee;
        }
        QSlider::sub-page:horizontal {
            border-radius: 4px;
            background: #2f6fa8;
        }
        QSlider::handle:horizontal {
            width: 18px;
            height: 18px;
            margin: -6px 0;
            border-radius: 9px;
            background: #ffffff;
            border: 2px solid #2f6fa8;
        }
        QSlider::handle:horizontal:hover {
            border-color: #255985;
            background: #eef6ff;
        }
"""
