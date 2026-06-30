from __future__ import annotations


USER_CONSOLE_STYLESHEET = """
        QFrame#ConsoleStatusCard {
            background: #ffffff;
            border: 1px solid #dfe8f3;
            border-radius: 8px;
        }
        QFrame#ConsoleStatusCard[tone="running"] {
            background: #eef6ff;
            border-color: #b9d7f4;
        }
        QFrame#ConsoleStatusCard[tone="success"] {
            background: #effaf3;
            border-color: #bfebcf;
        }
        QFrame#ConsoleStatusCard[tone="warning"] {
            background: #fff8ed;
            border-color: #f3d6ad;
        }
        QFrame#ConsoleStatusCard[tone="danger"] {
            background: #fff1f2;
            border-color: #efc0c6;
        }
        QLabel#ConsoleEyebrow {
            color: #64748b;
            font-size: 9pt;
            font-weight: 700;
        }
        QLabel#ConsoleStatusTitle {
            color: #10233f;
            font-size: 17pt;
            font-weight: 800;
        }
        QLabel#ConsoleHint {
            color: #52677e;
            font-size: 10pt;
        }
        QFrame#ConsoleStatusCard[compact="true"] QLabel#ConsoleEyebrow {
            font-size: 8pt;
        }
        QFrame#ConsoleStatusCard[compact="true"] QLabel#ConsoleStatusTitle {
            font-size: 14pt;
        }
        QFrame#ConsoleStatusCard[compact="true"] QLabel#ConsoleHint {
            font-size: 9pt;
        }
        QFrame#ConsoleStatusCard[compact="true"] QLabel#StatusBadge {
            font-size: 8pt;
            padding: 3px 8px;
        }
        QLabel#StatusBadge {
            border-radius: 13px;
            padding: 4px 10px;
            font-size: 9pt;
            font-weight: 800;
        }
        QLabel#StatusBadge[tone="neutral"] {
            background: #f1f5f9;
            color: #475569;
            border: 1px solid #d8e1ee;
        }
        QLabel#StatusBadge[tone="running"] {
            background: #dcecff;
            color: #174f87;
            border: 1px solid #aacbea;
        }
        QLabel#StatusBadge[tone="success"] {
            background: #dff6e7;
            color: #17643a;
            border: 1px solid #b7e7c7;
        }
        QLabel#StatusBadge[tone="warning"] {
            background: #fff0d4;
            color: #8b4513;
            border: 1px solid #eecb93;
        }
        QLabel#StatusBadge[tone="danger"] {
            background: #ffe4e6;
            color: #9f2d2d;
            border: 1px solid #efb7bd;
        }
        QFrame#InfoMetric {
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
        }
        QLabel#InfoMetricLabel {
            color: #64748b;
            font-size: 9pt;
            font-weight: 700;
        }
        QLabel#InfoMetricValue {
            color: #10233f;
            font-size: 11pt;
            font-weight: 800;
        }
        QFrame#ActionCard {
            background: #ffffff;
            border: 1px solid #dfe8f3;
            border-radius: 8px;
        }
        QFrame#ActionCard[tone="primary"] {
            background: #eef6ff;
            border-color: #b9d7f4;
        }
        QLabel#ActionCardTitle {
            color: #10233f;
            font-size: 12pt;
            font-weight: 800;
        }
        QLabel#ActionCardDetail {
            color: #52677e;
            font-size: 9pt;
            font-weight: 600;
        }
        QFrame#AdvancedDetails {
            background: transparent;
            border: 0;
        }
        QPushButton#AdvancedDetailsToggle {
            min-height: 30px;
            padding: 4px 10px;
            background: #f8fafc;
            color: #475569;
            border: 1px solid #d7e1ed;
            border-radius: 8px;
            font-weight: 700;
            text-align: left;
        }
        QPushButton#AdvancedDetailsToggle:checked {
            background: #eef6ff;
            color: #255985;
            border-color: #aacbea;
        }
        QLabel#AdvancedDetailsContent {
            background: #f8fafc;
            color: #475569;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 10px 12px;
            font-size: 9pt;
        }
        QFrame#AlertBanner {
            background: #fff8ed;
            border: 1px solid #f3d6ad;
            border-radius: 8px;
        }
        QFrame#AlertBanner[tone="danger"] {
            background: #fff1f2;
            border-color: #efc0c6;
        }
        QFrame#AlertBanner[tone="success"] {
            background: #effaf3;
            border-color: #bfebcf;
        }
        QLabel#AlertBannerIcon {
            min-width: 22px;
            max-width: 22px;
            min-height: 22px;
            max-height: 22px;
            border-radius: 11px;
            background: #fff0d4;
            color: #8b4513;
            font-size: 11pt;
            font-weight: 900;
            qproperty-alignment: AlignCenter;
        }
        QFrame#AlertBanner[tone="danger"] QLabel#AlertBannerIcon {
            background: #ffe4e6;
            color: #9f2d2d;
        }
        QFrame#AlertBanner[tone="success"] QLabel#AlertBannerIcon {
            background: #dff6e7;
            color: #17643a;
        }
        QLabel#AlertBannerTitle {
            color: #10233f;
            font-size: 10pt;
            font-weight: 800;
        }
        QLabel#AlertBannerDetail {
            color: #52677e;
            font-size: 9pt;
        }
        QFrame#TaskToast {
            background: #f8fafc;
            border: 1px solid #d7e1ed;
            border-radius: 8px;
        }
        QFrame#TaskToast[tone="running"] {
            background: #eef6ff;
            border-color: #b9d7f4;
        }
        QFrame#TaskToast[tone="success"] {
            background: #effaf3;
            border-color: #bfebcf;
        }
        QFrame#TaskToast[tone="warning"] {
            background: #fff8ed;
            border-color: #f3d6ad;
        }
        QFrame#TaskToast[tone="danger"] {
            background: #fff1f2;
            border-color: #efc0c6;
        }
        QLabel#TaskToastIcon {
            min-width: 26px;
            max-width: 26px;
            min-height: 26px;
            max-height: 26px;
            border-radius: 13px;
            background: #dcecff;
            color: #174f87;
            font-size: 12pt;
            font-weight: 900;
            qproperty-alignment: AlignCenter;
        }
        QLabel#TaskToastIcon[tone="success"] {
            background: #dff6e7;
            color: #17643a;
        }
        QLabel#TaskToastIcon[tone="warning"] {
            background: #fff0d4;
            color: #8b4513;
        }
        QLabel#TaskToastIcon[tone="danger"] {
            background: #ffe4e6;
            color: #9f2d2d;
        }
        QLabel#TaskToastTitle {
            color: #10233f;
            font-size: 11pt;
            font-weight: 800;
        }
        QLabel#TaskToastDetail {
            color: #52677e;
            font-size: 9pt;
            font-weight: 600;
        }
"""
