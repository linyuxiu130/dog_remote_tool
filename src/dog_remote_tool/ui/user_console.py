from __future__ import annotations

from dataclasses import dataclass

from PyQt5.QtCore import QTimer, Qt, pyqtSignal
from PyQt5.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget


@dataclass(frozen=True)
class StatusTone:
    key: str
    title: str
    next_step: str


STATUS_TONES: dict[str, StatusTone] = {
    "ready": StatusTone("success", "已就绪", "可以开始建图。"),
    "mapping": StatusTone("running", "建图中", "请遥控设备移动，完成后点击结束保存。"),
    "starting": StatusTone("warning", "启动中", "正在等待远端进入建图状态。"),
    "saving": StatusTone("warning", "保存中", "正在确认地图保存结果。"),
    "success": StatusTone("success", "保存完成", "地图已保存，可继续编辑路网或进入导航。"),
    "stopped": StatusTone("neutral", "未开始", "可以开始建图。"),
    "error": StatusTone("danger", "失败", "请查看提示并重试。"),
    "unknown": StatusTone("danger", "状态未知", "请刷新状态或检查设备连接。"),
}

OPERATION_TONES: dict[str, str] = {
    "idle": "neutral",
    "running": "running",
    "saving": "warning",
    "done": "success",
    "blocked": "danger",
}

def status_tone_for_mapping_state(state: str) -> StatusTone:
    return STATUS_TONES.get(state, STATUS_TONES["unknown"])


def compact_map_name(remote_map: str) -> str:
    if not remote_map:
        return "--"
    path = remote_map.rsplit("/", 1)[-1]
    if path == "map.pgm":
        parent = remote_map.rsplit("/", 2)[-2] if "/" in remote_map else ""
        return parent or path
    return path


class StatusBadge(QLabel):
    def __init__(self, text: str = "--", tone: str = "neutral", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("StatusBadge")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(26)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.set_tone(tone)

    def set_tone(self, tone: str) -> None:
        if self.property("tone") == tone:
            return
        self.setProperty("tone", tone)
        self.style().unpolish(self)
        self.style().polish(self)


class ConsoleStatusCard(QFrame):
    def __init__(self, eyebrow: str, title: str, detail: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ConsoleStatusCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)
        self.eyebrow = QLabel(eyebrow)
        self.eyebrow.setObjectName("ConsoleEyebrow")
        header = QGridLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setHorizontalSpacing(8)
        self.title = QLabel(title)
        self.title.setObjectName("ConsoleStatusTitle")
        self.title.setWordWrap(True)
        self.badge = StatusBadge(title)
        header.addWidget(self.title, 0, 0)
        header.addWidget(self.badge, 0, 1, Qt.AlignRight | Qt.AlignTop)
        header.setColumnStretch(0, 1)
        self.detail = QLabel(detail)
        self.detail.setObjectName("ConsoleHint")
        self.detail.setWordWrap(True)
        layout.addWidget(self.eyebrow)
        layout.addLayout(header)
        layout.addWidget(self.detail)
        self.set_status(title, detail, "neutral")

    def set_status(self, title: str, detail: str, tone: str) -> None:
        if (
            self.title.text() == title
            and self.detail.text() == detail
            and self.badge.text() == title
            and self.badge.property("tone") == tone
            and self.property("tone") == tone
        ):
            return
        if self.title.text() != title:
            self.title.setText(title)
        if self.detail.text() != detail:
            self.detail.setText(detail)
        if self.badge.text() != title:
            self.badge.setText(title)
        self.badge.set_tone(tone)
        if self.property("tone") == tone:
            return
        self.setProperty("tone", tone)
        self.style().unpolish(self)
        self.style().polish(self)


class InfoMetric(QFrame):
    def __init__(self, label: str, value: str = "--", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("InfoMetric")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        self.label = QLabel(label)
        self.label.setObjectName("InfoMetricLabel")
        self.value = QLabel(value)
        self.value.setObjectName("InfoMetricValue")
        self.value.setWordWrap(True)
        layout.addWidget(self.label)
        layout.addWidget(self.value)

    def set_value(self, value: str, tooltip: str = "") -> None:
        next_value = value or "--"
        if self.value.text() != next_value:
            self.value.setText(next_value)
        if self.toolTip() != tooltip:
            self.setToolTip(tooltip)
        if self.value.toolTip() != tooltip:
            self.value.setToolTip(tooltip)


class ActionCard(QFrame):
    clicked = pyqtSignal()

    def __init__(
        self,
        title: str,
        detail: str,
        action_text: str,
        *,
        tone: str = "neutral",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ActionCard")
        self.setProperty("tone", tone)
        self.title = QLabel(title)
        self.title.setObjectName("ActionCardTitle")
        self.title.setWordWrap(True)
        self.detail = QLabel(detail)
        self.detail.setObjectName("ActionCardDetail")
        self.detail.setWordWrap(True)
        self.button = QPushButton(action_text)
        self.button.setObjectName("Primary" if tone == "primary" else "SoftPrimary")
        self.button.setMinimumHeight(32)
        self.button.setMinimumWidth(120)
        self.button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.button.clicked.connect(self.clicked.emit)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(4)
        text_layout.addWidget(self.title)
        text_layout.addWidget(self.detail)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)
        layout.addLayout(text_layout, 1)
        layout.addWidget(self.button, 0, Qt.AlignVCenter)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_enabled(self, enabled: bool) -> None:
        self.setEnabled(enabled)
        self.button.setEnabled(enabled)


class AdvancedDetails(QFrame):
    def __init__(self, title: str = "详细信息", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.collapsed_title = title
        self.setObjectName("AdvancedDetails")
        self.toggle = QPushButton(title)
        self.toggle.setObjectName("AdvancedDetailsToggle")
        self.toggle.setCheckable(True)
        self.toggle.setChecked(False)
        self.toggle.clicked.connect(self._sync_visible)
        self.content = QLabel("")
        self.content.setObjectName("AdvancedDetailsContent")
        self.content.setWordWrap(True)
        self.content.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.toggle)
        layout.addWidget(self.content)
        self.content.hide()

    def set_details(self, text: str) -> None:
        self.content.setText(text or "暂无诊断详情")

    def _sync_visible(self) -> None:
        self.content.setVisible(self.toggle.isChecked())
        self.toggle.setText(f"收起{self.collapsed_title}" if self.toggle.isChecked() else self.collapsed_title)


class AlertBanner(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AlertBanner")
        self.icon = QLabel("!")
        self.icon.setObjectName("AlertBannerIcon")
        self.title = QLabel("")
        self.title.setObjectName("AlertBannerTitle")
        self.title.setWordWrap(True)
        self.detail = QLabel("")
        self.detail.setObjectName("AlertBannerDetail")
        self.detail.setWordWrap(True)
        text_box = QVBoxLayout()
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setSpacing(2)
        text_box.addWidget(self.title)
        text_box.addWidget(self.detail)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)
        layout.addWidget(self.icon, 0, Qt.AlignTop)
        layout.addLayout(text_box, 1)
        self.hide()

    def show_message(self, title: str, detail: str = "", tone: str = "warning") -> None:
        if self.title.text() != title:
            self.title.setText(title)
        if self.detail.text() != detail:
            self.detail.setText(detail)
        detail_visible = bool(detail)
        if self.detail.isVisible() != detail_visible:
            self.detail.setVisible(detail_visible)
        if self.property("tone") != tone:
            self.setProperty("tone", tone)
            self.style().unpolish(self)
            self.style().polish(self)
        self.show()

    def clear_message(self) -> None:
        self.hide()


class TaskToast(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("TaskToast")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumWidth(320)
        self.setMaximumWidth(480)
        self.icon = QLabel("")
        self.icon.setObjectName("TaskToastIcon")
        self.title = QLabel("")
        self.title.setObjectName("TaskToastTitle")
        self.title.setWordWrap(True)
        self.detail = QLabel("")
        self.detail.setObjectName("TaskToastDetail")
        self.detail.setWordWrap(True)
        text_box = QVBoxLayout()
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setSpacing(3)
        text_box.addWidget(self.title)
        text_box.addWidget(self.detail)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        layout.addWidget(self.icon, 0, Qt.AlignTop)
        layout.addLayout(text_box, 1)
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide)
        self.hide()

    def show_message(self, title: str, detail: str = "", tone: str = "running", duration_ms: int = 3600) -> None:
        self.title.setText(title)
        self.detail.setText(detail)
        self.detail.setVisible(bool(detail))
        self.icon.setText(self._icon_for_tone(tone))
        self.setProperty("tone", tone)
        self.icon.setProperty("tone", tone)
        for widget in (self, self.icon):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        self.adjustSize()
        if self.parentWidget() is not None:
            self.reposition()
        self.show()
        self.raise_()
        self.hide_timer.start(max(1200, duration_ms))

    def reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        width = min(480, max(320, int(parent.width() * 0.34)))
        width = min(width, max(280, parent.width() - 32))
        self.setFixedWidth(width)
        self.adjustSize()
        x = max(16, parent.width() - self.width() - 18)
        y = max(18, parent.height() - self.height() - 18)
        self.move(x, y)

    def _icon_for_tone(self, tone: str) -> str:
        if tone == "success":
            return "✓"
        if tone == "danger":
            return "!"
        if tone == "warning":
            return "…"
        return "•"
