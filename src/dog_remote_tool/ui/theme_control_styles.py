from __future__ import annotations


CONTROL_STYLESHEET = """
        QFrame#ControlHero {
            background: #ffffff;
            border: 1px solid #e3eaf3;
            border-radius: 10px;
        }
        QFrame#ControlSubPanel {
            background: #ffffff;
            border: 1px solid #edf2f7;
            border-radius: 8px;
        }
        QFrame#ControlInlineGroup {
            background: transparent;
            border: none;
        }
        QFrame#ControlVideoPanel {
            background: #0d1420;
            border: 1px solid #162338;
            border-radius: 8px;
        }
        QLabel#ControlVideoViewport {
            background: #0d1420;
            color: #d7e2ef;
            border: none;
            border-radius: 8px;
            padding: 0;
            font-weight: 700;
            line-height: 150%;
        }
        QLabel#ControlVideoPipViewport {
            background: rgba(7, 16, 29, 190);
            color: #e8f0f8;
            border: 1px solid rgba(255, 255, 255, 95);
            border-radius: 8px;
            padding: 0;
            font-weight: 800;
            line-height: 145%;
        }
        QLabel#ControlVideoSpeedBadge {
            background: #eef6ff;
            color: #17496e;
            border: 1px solid #c7ddf4;
            border-radius: 8px;
            padding: 6px 12px;
            font-weight: 800;
        }
        QLabel#ControlHeroTitle {
            color: #17324d;
            font-size: 13pt;
            font-weight: 800;
        }
        QLabel#ControlBadge {
            background: #eef6ff;
            color: #255985;
            border: 1px solid #d6e7fb;
            border-radius: 8px;
            padding: 5px 9px;
            font-weight: 700;
        }
        QLabel#ControlBadgeWarn {
            background: #fff8ed;
            color: #8b4513;
            border: 1px solid #f5dec0;
            border-radius: 8px;
            padding: 5px 9px;
            font-weight: 700;
        }
        QLabel#ControlSpeedValue {
            background: #edf8f0;
            color: #22623a;
            border: 1px solid #c9ead2;
            border-radius: 8px;
            padding: 5px 10px;
            min-width: 86px;
            font-weight: 800;
        }
"""
