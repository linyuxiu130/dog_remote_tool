from __future__ import annotations


BUTTON_STYLESHEET = """
        QPushButton {
            min-height: 34px;
            padding: 6px 14px 8px 14px;
            border: 1px solid #d7e1ed;
            border-radius: 8px;
            background: #ffffff;
            color: #243044;
        }
        QPushButton:hover {
            background: #eef6ff;
            border-color: #aacbea;
        }
        QPushButton:pressed {
            background: #dcecff;
        }
        QPushButton:checked {
            background: #eaf3fd;
            border-color: #aacbea;
            color: #17324d;
            font-weight: 700;
        }
        QPushButton#SegmentButton {
            min-height: 34px;
            padding: 6px 12px 8px 12px;
            background: #f8fafc;
            border-color: #d7e1ed;
            color: #334155;
            font-weight: 700;
        }
        QPushButton#SegmentButton:hover {
            background: #eef6ff;
            border-color: #7eb0e7;
        }
        QPushButton#SegmentButton:checked {
            background: #2f6fa8;
            border-color: #2f6fa8;
            color: #ffffff;
        }
        QPushButton#SegmentButton:disabled {
            background: #eef2f6;
            border-color: #d8e1ee;
            color: #94a3b8;
            font-weight: 600;
        }
        QPushButton#AutoTransferToggle {
            min-height: 34px;
            padding: 6px 12px 8px 12px;
            background: #f8fafc;
            border: 1px solid #cbd5e1;
            color: #475569;
            border-radius: 8px;
            font-weight: 700;
        }
        QPushButton#AutoTransferToggle:hover {
            background: #f1f5f9;
            border-color: #94a3b8;
            color: #334155;
        }
        QPushButton#AutoTransferToggle:checked {
            background: #eaf3fd;
            border-color: #aacbea;
            color: #255985;
            font-weight: 800;
        }
        QPushButton#AutoTransferToggle:checked:hover {
            background: #dcecff;
            border-color: #7eb0e7;
            color: #174f87;
        }
        QPushButton#AutoTransferToggle:disabled {
            background: #f1f5f9;
            border-color: #e2e8f0;
            color: #94a3b8;
            font-weight: 700;
        }
        QPushButton#Primary {
            background: #2f6fa8;
            color: #ffffff;
            border-color: #2f6fa8;
            font-weight: 700;
        }
        QPushButton#Primary:disabled {
            background: #edf2f7;
            color: #94a3b8;
            border-color: #d8e1ee;
            font-weight: 600;
        }
        QPushButton#SoftPrimary {
            background: #eef6ff;
            color: #255985;
            border-color: #d6e7fb;
            font-weight: 700;
        }
        QPushButton#SoftPrimary:hover {
            background: #dcecff;
            border-color: #aacbea;
        }
        QPushButton#SoftPrimary:disabled {
            background: #edf2f7;
            color: #94a3b8;
            border-color: #d8e1ee;
            font-weight: 600;
        }
        QPushButton#Danger {
            background: #b85b4d;
            color: #ffffff;
            border-color: #b85b4d;
            font-weight: 700;
        }
        QPushButton#DashboardPrimary, QPushButton#DashboardDanger, QPushButton#DashboardAction {
            min-width: 54px;
            max-width: 54px;
            min-height: 30px;
            max-height: 30px;
            padding: 0 4px;
            border-radius: 6px;
            font-size: 9pt;
            font-weight: 700;
        }
        QPushButton#DashboardPrimary {
            background: #2f6fa8;
            color: #ffffff;
            border-color: #2f6fa8;
        }
        QPushButton#DashboardDanger {
            background: #b85b4d;
            color: #ffffff;
            border-color: #b85b4d;
        }
        QPushButton#DashboardAction {
            background: #ffffff;
            color: #243044;
            border-color: #d7e1ed;
        }
        QPushButton#DashboardPrimary:disabled,
        QPushButton#DashboardDanger:disabled {
            background: #edf2f7;
            color: #94a3b8;
            border-color: #d8e1ee;
        }
        QPushButton#SoftDanger {
            background: #fff2ee;
            color: #9f3f2f;
            border-color: #efc3b8;
            font-weight: 700;
        }
        QPushButton#SoftDanger:hover {
            background: #fde8e1;
            border-color: #e9aea2;
        }
        QPushButton#SoftDanger:disabled {
            background: #edf2f7;
            color: #94a3b8;
            border-color: #d8e1ee;
            font-weight: 600;
        }
        QPushButton#LoopSwitchOn {
            background: #1f8a4c;
            color: #ffffff;
            border-color: #166534;
            font-weight: 800;
        }
        QPushButton#LoopSwitchOn:hover {
            background: #18733f;
            border-color: #14532d;
        }
        QPushButton#LoopSwitchOn:checked {
            background: #1f8a4c;
            color: #ffffff;
            border-color: #166534;
            font-weight: 800;
        }
        QPushButton#LoopSwitchOff {
            background: #f8fafc;
            color: #475569;
            border-color: #94a3b8;
            font-weight: 800;
        }
        QPushButton#LoopSwitchOff:hover {
            background: #eef2f6;
            border-color: #64748b;
            color: #334155;
        }
        QPushButton#LoopSwitchOn:disabled,
        QPushButton#LoopSwitchOff:disabled {
            background: #edf2f7;
            color: #94a3b8;
            border-color: #d8e1ee;
            font-weight: 700;
        }
        QPushButton#TinyButton {
            min-width: 30px;
            max-width: 30px;
            min-height: 32px;
            padding: 0;
            font-weight: 800;
            background: #ffffff;
        }
        QPushButton#DirectionButton {
            min-height: 40px;
            font-weight: 700;
            background: #ffffff;
        }
        QPushButton:disabled {
            background: #edf2f7;
            color: #94a3b8;
            border-color: #d8e1ee;
            font-weight: 600;
        }
        QPushButton#Danger:disabled {
            background: #edf2f7;
            color: #94a3b8;
            border-color: #d8e1ee;
        }
"""
