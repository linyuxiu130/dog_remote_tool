from PyQt5.QtWidgets import QApplication

from dog_remote_tool.ui.user_console import (
    ActionCard,
    AlertBanner,
    ConsoleStatusCard,
    StatusBadge,
    TaskToast,
    compact_map_name,
    status_tone_for_mapping_state,
)


def test_status_tone_for_mapping_state_uses_user_facing_labels():
    tone = status_tone_for_mapping_state("mapping")

    assert tone.key == "running"
    assert tone.title == "建图中"
    assert "结束保存" in tone.next_step


def test_status_tone_unknown_falls_back_to_actionable_message():
    tone = status_tone_for_mapping_state("not-a-state")

    assert tone.key == "danger"
    assert tone.title == "状态未知"
    assert "刷新状态" in tone.next_step


def test_compact_map_name_prefers_history_directory_for_map_pgm():
    assert (
        compact_map_name("/ota/alg_data/map/history_map/2026_06_15_22_03_32/map.pgm")
        == "2026_06_15_22_03_32"
    )


def test_compact_map_name_keeps_non_standard_file_name():
    assert compact_map_name("/tmp/custom_map.png") == "custom_map.png"


def test_alert_banner_starts_hidden_and_updates_text():
    _ = QApplication.instance() or QApplication([])
    banner = AlertBanner()

    assert banner.isHidden()

    banner.show_message("系统忙", "请稍后重试", "warning")

    assert banner.isVisible()
    assert banner.title.text() == "系统忙"
    assert banner.detail.text() == "请稍后重试"
    assert banner.property("tone") == "warning"

    banner.clear_message()

    assert banner.isHidden()


def test_console_status_card_skips_duplicate_status_polish(monkeypatch):
    _ = QApplication.instance() or QApplication([])
    card = ConsoleStatusCard("当前状态", "读取中", "正在读取远端状态。")
    calls = []
    original_set_tone = StatusBadge.set_tone

    def spy_set_tone(self, tone):
        calls.append(tone)
        return original_set_tone(self, tone)

    monkeypatch.setattr(StatusBadge, "set_tone", spy_set_tone)

    card.set_status("读取中", "正在读取远端状态。", "neutral")

    assert calls == []

    card.set_status("建图中", "请继续移动。", "running")

    assert calls == ["running"]


def test_action_card_exposes_user_facing_action():
    _ = QApplication.instance() or QApplication([])
    card = ActionCard("进入导航", "使用当前地图开始初始化定位和导航。", "进入导航", tone="primary")
    clicked = []
    card.clicked.connect(lambda: clicked.append(True))

    card.button.click()

    assert clicked == [True]
    assert card.title.text() == "进入导航"
    assert "初始化定位" in card.detail.text()
    assert card.property("tone") == "primary"
    assert card.button.objectName() == "Primary"


def test_task_toast_updates_user_facing_status():
    _ = QApplication.instance() or QApplication([])
    toast = TaskToast()

    toast.show_message("任务已完成", "开始建图", "success", duration_ms=1200)

    assert toast.isVisible()
    assert toast.title.text() == "任务已完成"
    assert toast.detail.text() == "开始建图"
    assert toast.property("tone") == "success"
    assert toast.icon.property("tone") == "success"
