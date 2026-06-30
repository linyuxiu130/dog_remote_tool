from __future__ import annotations


STATUS_PANEL_STYLESHEET = """
        QFrame#StatusCard {
            background: #ffffff;
            border: 1px solid #e3eaf3;
            border-radius: 10px;
        }
        QFrame#PerfMetricCard {
            background: #ffffff;
            border: 1px solid #e3eaf3;
            border-radius: 10px;
        }
        QFrame#TopCpuCard {
            background: #ffffff;
            border: 1px solid #e3eaf3;
            border-radius: 10px;
        }
        QFrame#JointTempCard {
            background: #ffffff;
            border: 1px solid #e3eaf3;
            border-radius: 10px;
        }
        QFrame#TopCpuRow {
            background: #f8fafc;
            border: 1px solid #edf2f7;
            border-radius: 8px;
        }
        QLabel#TopCpuHeader {
            color: #64748b;
            font-size: 8pt;
            font-weight: 700;
        }
        QLabel#TopCpuName {
            color: #10233f;
            font-size: 9pt;
            font-weight: 700;
        }
        QLabel#TopCpuValue {
            color: #0f766e;
            font-size: 10pt;
            font-weight: 800;
        }
        QLabel#TopCpuTotalValue {
            color: #334155;
            font-size: 10pt;
            font-weight: 800;
        }
        QLabel#JointTempValue {
            color: #17324d;
            font-size: 10pt;
            font-weight: 800;
            background: #f8fafc;
            border: 1px solid #edf2f7;
            border-radius: 8px;
            padding: 4px 6px;
        }
        QLabel#PerfMetricTitle {
            color: #52677e;
            font-size: 9pt;
            font-weight: 700;
        }
        QLabel#PerfMetricValue {
            color: #17324d;
            font-size: 17pt;
            font-weight: 800;
        }
        QLabel#PerfMetricDetail {
            color: #64748b;
            font-size: 9pt;
        }
        QLabel#DiagSectionTitle {
            color: #17324d;
            font-size: 12pt;
            font-weight: 800;
        }
        QLabel#DiagTargetLabel {
            color: #64748b;
            font-size: 9pt;
        }
        QLabel#MetricValue {
            color: #10233f;
            font-size: 10pt;
            font-weight: 700;
        }
        QLabel#EndpointValue {
            color: #10233f;
            font-size: 10pt;
            font-weight: 700;
        }
        QLabel#StatusText {
            color: #10233f;
            font-size: 10pt;
        }
        QLabel#StatusStrong {
            color: #10233f;
            font-size: 10pt;
            font-weight: 700;
        }
        QLabel#LaunchNote {
            background: #eef6f5;
            color: #0f5f5a;
            border: 1px solid #bfdedb;
            border-radius: 5px;
            padding: 2px 6px;
            font-size: 9pt;
            font-weight: 700;
        }
"""
