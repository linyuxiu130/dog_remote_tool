from __future__ import annotations


BAG_STYLESHEET = """
        QFrame#BagStatusBar, QFrame#BagMainPanel {
            background: #ffffff;
            border: 1px solid #e3eaf3;
            border-radius: 10px;
        }
        QFrame#BagStatusBar {
            background: #fbfdff;
        }
        QFrame#BagEditorPanel {
            background: #ffffff;
            border: 1px solid #edf2f7;
            border-radius: 8px;
        }
        QFrame#BagStatusInfo {
            background: #ffffff;
            border: 1px solid #dbe8f5;
            border-radius: 8px;
        }
        QLabel#BagStatusOk {
            background: #dcfce7;
            color: #166534;
            border: 1px solid #86efac;
            border-radius: 6px;
            padding: 4px 8px;
            font-weight: 700;
        }
        QLabel#BagStatusWarn {
            background: #fef3c7;
            color: #92400e;
            border: 1px solid #fcd34d;
            border-radius: 6px;
            padding: 4px 8px;
            font-weight: 700;
        }
        QLabel#BagStatusBad {
            background: #f9e5df;
            color: #8f3128;
            border: 1px solid #e9aea2;
            border-radius: 6px;
            padding: 4px 8px;
            font-weight: 700;
        }
        QProgressBar#BagTransferProgress {
            background: #e7eef7;
            border: 1px solid #c8d8ea;
            border-radius: 9px;
            min-height: 18px;
            max-height: 18px;
            text-align: center;
        }
        QProgressBar#BagTransferProgress::chunk {
            background: #2f6fa8;
            border-radius: 8px;
            margin: 1px;
        }
        QLabel#BagTransferPercent {
            color: #10233f;
            font-size: 12pt;
            font-weight: 800;
            min-width: 46px;
        }
        QLabel#BagTransferSpeed {
            background: #eef6f5;
            color: #0f5f5a;
            border: 1px solid #bfdedb;
            border-radius: 6px;
            padding: 3px 8px;
            font-weight: 700;
        }
        QLabel#BagTransferEta {
            background: #eef6f5;
            color: #0f5f5a;
            border: 1px solid #bfdedb;
            border-radius: 6px;
            padding: 3px 8px;
            font-weight: 700;
        }
"""
