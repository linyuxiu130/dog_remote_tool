from __future__ import annotations


BASE_STYLESHEET = """
        QMainWindow, QWidget {
            background: #f5f8fc;
            color: #243044;
            font-family: "Noto Sans CJK SC";
            font-size: 10pt;
        }
        QLabel {
            background: transparent;
        }
        QLabel#AppTitle {
            font-size: 14pt;
            font-weight: 700;
            color: #17324d;
        }
        QLabel#PathBadge {
            background: #ffffff;
            color: #1f334a;
            border: 1px solid #e3eaf3;
            border-radius: 8px;
            padding: 6px 10px;
            font-weight: 700;
        }
        QLabel#BrandTitle {
            background: #17324d;
            color: #ffffff;
            font-size: 14pt;
            font-weight: 700;
        }
        QLabel#BrandSubTitle {
            background: #17324d;
            color: #b7c7da;
            font-size: 9pt;
        }
        QLabel#Muted {
            color: #68788d;
            font-size: 9pt;
        }
        QFrame#TopBar, QFrame#Panel, QFrame#PageHeader {
            background: #ffffff;
            border: 1px solid #e3eaf3;
            border-radius: 10px;
        }
"""
