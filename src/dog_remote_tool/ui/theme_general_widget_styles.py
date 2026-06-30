from __future__ import annotations


GENERAL_WIDGET_STYLESHEET = """
        QProgressBar {
            background: #edf3fa;
            border: 1px solid #d7e1ed;
            border-radius: 8px;
            color: #10233f;
            min-height: 16px;
            text-align: center;
            font-weight: 700;
        }
        QProgressBar::chunk {
            background: #2f6fa8;
            border-radius: 7px;
        }
        QPlainTextEdit#Log {
            background: #08111f;
            color: #dce6f3;
            border: 1px solid #18314d;
            border-radius: 8px;
            padding: 10px 12px;
            selection-background-color: #215fa8;
            selection-color: #ffffff;
            font-family: "DejaVu Sans Mono", "Consolas", monospace;
            font-size: 10pt;
        }
        QScrollArea#MapPreviewScroll {
            background: #ffffff;
            border: 1px solid #e3eaf3;
            border-radius: 8px;
        }
        QLabel#MapPreview {
            background: #ffffff;
            color: #607085;
            padding: 2px;
        }
        QGroupBox {
            background: #ffffff;
            border: 1px solid #e3eaf3;
            border-radius: 10px;
            margin-top: 14px;
            padding: 12px 12px 12px 12px;
            font-size: 10pt;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 8px;
            color: #17324d;
            font-weight: 700;
        }
        QLabel#FieldLabel {
            color: #64748b;
            font-size: 9pt;
        }
        QCheckBox {
            spacing: 8px;
        }
"""
