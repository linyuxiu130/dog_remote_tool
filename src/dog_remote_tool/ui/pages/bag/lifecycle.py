from __future__ import annotations

from PyQt5.QtWidgets import QLabel

from dog_remote_tool.core.log_format import log_line
from dog_remote_tool.modules import bag
from dog_remote_tool.ui.label_status import label_status_object_name, repolish_label
from dog_remote_tool.ui.widget_roles import widget_object_name, widget_visible


class BagLifecycleMixin:
    def profile(self):
        return self.device_bar.current_profile()

    def backend(self) -> bag.BagBackend:
        return bag.BagBackend(self.profile(), self.product, self._log)

    def current_record_backend(self) -> bag.BagBackend:
        return bag.BagBackend(
            self.current_record_profile or self.profile(),
            self.current_record_product or self.product,
            self._log,
        )

    def _save_auto_pull_after_record(self, checked: bool) -> None:
        self.settings.setValue(self.AUTO_PULL_AFTER_RECORD_KEY, bool(checked))
        self._update_auto_pull_after_record_text(checked)

    def _update_auto_pull_after_record_text(self, checked: bool) -> None:
        button = getattr(self, "auto_pull_after_record", None)
        if button is not None:
            button.setText("自动回传开" if checked else "自动回传关")

    def auto_pull_after_record_enabled(self) -> bool:
        checkbox = getattr(self, "auto_pull_after_record", None)
        if checkbox is None:
            return False
        return bool(checkbox.isChecked())

    def _log(self, message: str) -> bool:
        self.log_signal.emit(log_line("info", message, scope="录包"))
        return True

    def _set_label_status(self, label: QLabel, state: str) -> bool:
        object_name = label_status_object_name(state)
        visible = bool(label.text().strip())
        current_object_name = widget_object_name(label)
        current_visible = widget_visible(label, visible)
        changed = current_object_name != object_name or current_visible != visible
        label.setObjectName(object_name)
        label.setVisible(visible)
        repolish_label(label)
        return changed
