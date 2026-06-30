from __future__ import annotations


OTA_STYLESHEET = """
        QFrame#OtaWorkbench {
            background: transparent;
            border: none;
        }
        QFrame#OtaTargetPanel {
            background: #10233f;
            border: 1px solid #10233f;
            border-radius: 10px;
        }
        QFrame#OtaTargetPanel QLabel#FieldLabel {
            color: #9fb4cc;
            font-weight: 800;
        }
        QLabel#OtaTargetTitle {
            color: #ffffff;
            font-size: 13pt;
            font-weight: 800;
        }
        QFrame#OtaTargetPanel QLabel#Muted {
            color: #c8d6e6;
            font-size: 9pt;
        }
        QFrame#OtaPackagePanel, QFrame#OtaActionPanel, QFrame#OtaDevicePanel {
            background: #ffffff;
            border: 1px solid #dbe6f2;
            border-radius: 10px;
        }
        QFrame#OtaPackagePanel QLineEdit {
            min-height: 34px;
            font-weight: 700;
            color: #10233f;
        }
        QFrame#OtaDevicePanel {
            background: #fbfdff;
        }
        QFrame#OtaSectionPanel {
            background: #ffffff;
            border: 1px solid #e2ebf5;
            border-radius: 8px;
        }
        QFrame#OtaInfoRow {
            background: #f6f9fd;
            border: 1px solid #e5edf6;
            border-radius: 6px;
        }
        QLabel#OtaInfoKey {
            color: #5c6f85;
            font-size: 8pt;
            font-weight: 800;
        }
        QLabel#OtaInfoValue {
            color: #10233f;
            font-size: 10pt;
            font-weight: 800;
        }
        QLabel#OtaMcuModuleLabel {
            color: #10233f;
            font-size: 10pt;
            font-weight: 800;
            padding: 8px 6px;
        }
        QLabel#OtaActionTitle {
            color: #10233f;
            font-size: 11pt;
            font-weight: 800;
        }
        QLabel#OtaProgressPercent {
            color: #2f6fa8;
            font-size: 13pt;
            font-weight: 800;
            min-width: 72px;
        }
        QLabel#OtaProgressState {
            background: #dcecff;
            color: #2f6fa8;
            border: 1px solid #aacbea;
            border-radius: 7px;
            padding: 5px 10px;
            font-weight: 800;
        }
        QFrame#OtaMetricCard {
            background: #f8fafc;
            border: 1px solid #edf2f7;
            border-radius: 8px;
        }
        QFrame#OtaMcuPanel {
            background: #fbfdff;
            border: 1px solid #dbe8f5;
            border-radius: 8px;
        }
        QLabel#OtaMetricValue {
            color: #10233f;
            font-size: 10pt;
            font-weight: 800;
        }
        QLabel#OtaStatusPill {
            background: #fef3c7;
            color: #92400e;
            border: 1px solid #fcd34d;
            border-radius: 6px;
            padding: 4px 8px;
            font-weight: 700;
        }
        QLabel#OtaStatusPillOk {
            background: #dcfce7;
            color: #166534;
            border: 1px solid #86efac;
            border-radius: 6px;
            padding: 4px 8px;
            font-weight: 700;
        }
        QLabel#OtaStatusPillBad {
            background: #f9e5df;
            color: #8f3128;
            border: 1px solid #e9aea2;
            border-radius: 6px;
            padding: 4px 8px;
            font-weight: 700;
        }
"""
