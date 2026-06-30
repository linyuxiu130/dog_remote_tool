from __future__ import annotations


ROUTE_STYLESHEET = """
        QFrame#RouteWorkbenchHeader, QFrame#RouteInspector {
            background: #ffffff;
            border: 1px solid #e3eaf3;
            border-radius: 10px;
        }
        QDialog#RouteEditorDialog {
            background: #eef4f9;
        }
        QFrame#RouteEditorHeader, QFrame#RouteEditorSidePanel {
            background: #ffffff;
            border: 1px solid #dbe6f2;
            border-radius: 10px;
        }
        QLabel#RouteEditorTitle {
            color: #10233f;
            font-size: 14pt;
            font-weight: 900;
            padding-right: 12px;
        }
        QCheckBox#RouteEditorCheck {
            color: #40536a;
            font-weight: 800;
            spacing: 6px;
            padding: 4px 6px;
        }
        QCheckBox#RouteEditorCheck::indicator {
            width: 16px;
            height: 16px;
            border: 1px solid #bfd0e2;
            border-radius: 4px;
            background: #ffffff;
        }
        QCheckBox#RouteEditorCheck::indicator:checked {
            background: #2f78bd;
            border-color: #2f78bd;
        }
        QFrame#RouteInfoStrip {
            background: #ffffff;
            border: 1px solid #e3eaf3;
            border-radius: 10px;
        }
        QFrame#NavActionSection {
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
        }
        QLabel#NavActionSectionTitle {
            color: #52677e;
            font-size: 9pt;
            font-weight: 800;
            padding: 0;
        }
        QLabel#RouteAnalysisSummary {
            background: #f8fbff;
            color: #334155;
            border: 1px solid #e4edf7;
            border-radius: 7px;
            padding: 8px 9px;
            font-size: 9pt;
            font-weight: 650;
        }
        QTableWidget {
            background: #ffffff;
            alternate-background-color: #f8fbff;
            border: 1px solid #e4edf7;
            border-radius: 7px;
            color: #27364a;
            gridline-color: #e7eef7;
        }
        QHeaderView::section {
            background: #eef6ff;
            color: #334155;
            border: 0;
            border-bottom: 1px solid #dbe8f5;
            padding: 5px 7px;
            font-weight: 800;
        }
        QLabel#RouteInfoText {
            background: #f8fbff;
            color: #40536a;
            border: 1px solid #e4edf7;
            border-radius: 7px;
            padding: 5px 9px;
            font-size: 9pt;
            font-weight: 700;
        }
        QLabel#RouteInfoBadge, QLabel#RouteInfoBadgeOk, QLabel#RouteInfoBadgeWarn {
            border-radius: 7px;
            padding: 5px 10px;
            font-size: 9pt;
            font-weight: 800;
        }
        QLabel#RouteInfoBadge {
            background: #eef7ff;
            color: #245b84;
            border: 1px solid #c7e2f8;
        }
        QLabel#RouteInfoBadgeOk {
            background: #edf8f0;
            color: #22623a;
            border: 1px solid #c9ead2;
        }
        QLabel#RouteInfoBadgeWarn {
            background: #fff8ed;
            color: #8b4513;
            border: 1px solid #f5dec0;
        }
        QFrame#RouteToolRail {
            background: #ffffff;
            border: 1px solid #e3eaf3;
            border-radius: 10px;
        }
        QPushButton#RouteToolButton {
            min-height: 34px;
            padding: 3px 4px;
            background: #f8fbff;
            color: #334155;
            border: 1px solid #dbe8f5;
            border-radius: 8px;
            font-weight: 700;
        }
        QPushButton#RouteToolButton:hover {
            background: #eef6ff;
            border-color: #bfdbfe;
            color: #0f4c8a;
        }
        QPushButton#RouteToolButton:checked {
            background: #174f87;
            border-color: #174f87;
            color: #ffffff;
        }
        QLabel#RouteStatusNeutral, QLabel#RouteStatusReady, QLabel#RouteStatusSuccess,
        QLabel#RouteStatusWarning, QLabel#RouteStatusError {
            border-radius: 8px;
            padding: 7px 10px;
            font-weight: 800;
        }
        QLabel#RouteStatusNeutral {
            background: #ffffff;
            color: #46566b;
            border: 1px solid #e3eaf3;
        }
        QLabel#RouteStatusReady {
            background: #eef7ff;
            color: #245b84;
            border: 1px solid #c7e2f8;
        }
        QLabel#RouteStatusSuccess {
            background: #edf8f0;
            color: #22623a;
            border: 1px solid #c9ead2;
        }
        QLabel#RouteStatusWarning {
            background: #fff8ed;
            color: #8b4513;
            border: 1px solid #f5dec0;
        }
        QLabel#RouteStatusError {
            background: #fff2ee;
            color: #8f3128;
            border: 1px solid #e8bdb4;
        }
        QLabel#RouteInspectorTitle {
            color: #17324d;
            font-size: 11pt;
            font-weight: 800;
        }
        QTabWidget#RouteInspectorTabs::pane {
            background: #ffffff;
            border: 1px solid #dbe8f5;
            border-radius: 8px;
            top: -1px;
        }
        QTabWidget#RouteInspectorTabs QTabBar::tab {
            background: #f8fbff;
            color: #52677e;
            border: 1px solid #dbe8f5;
            border-bottom: none;
            border-top-left-radius: 7px;
            border-top-right-radius: 7px;
            padding: 7px 9px;
            font-weight: 700;
            min-width: 36px;
        }
        QTabWidget#RouteInspectorTabs QTabBar::tab:selected {
            background: #ffffff;
            color: #17324d;
            border-color: #cbd7e6;
        }
        QTabWidget#RouteInspectorTabs QTabBar::tab:hover {
            background: #eef6ff;
            color: #0f4c8a;
        }
        QFrame#LogPanelFrame {
            background: #f8fbff;
            border: 1px solid #d6e3f0;
            border-radius: 10px;
        }
"""
