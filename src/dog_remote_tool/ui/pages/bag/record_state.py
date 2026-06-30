from __future__ import annotations

from PyQt5.QtCore import QAbstractAnimation

from dog_remote_tool.ui.pages.bag.helpers import current_bag_label_state
from dog_remote_tool.ui.widget_roles import set_widget_text_tooltip, widget_text, widget_tooltip, widget_visible


class BagRecordStateMixin:
    def _set_current_bag_paths(self, paths: list[str]) -> bool:
        text, tooltip, visible = current_bag_label_state(paths)
        current_text = widget_text(self.current_bag_label)
        current_tooltip = widget_tooltip(self.current_bag_label)
        current_visible = (
            widget_visible(self.record_detail_widget, getattr(self, "record_detail_visible", visible))
            if hasattr(self, "record_detail_widget")
            else getattr(self, "record_detail_visible", visible)
        )
        current_size = widget_text(self.current_bag_size_label)
        changed = current_text != text or current_tooltip != tooltip or current_visible != visible or (not visible and current_size != "--")
        set_widget_text_tooltip(self.current_bag_label, text, tooltip)
        self._set_record_detail_visible(visible)
        if not visible:
            self.current_bag_size_label.setText("--")
        return changed

    def _apply_record_context(self, context: dict) -> bool:
        changed = (
            self.is_reading_bag_size
            or self.current_bag_paths != context["paths"]
            or self.current_record_profile != context.get("profile")
            or self.current_record_topics != context["topics"]
            or self.current_record_product != context["product"]
            or self.current_record_themes != context["themes"]
            or self.current_record_started_at != context["started_at"]
            or self.current_record_finished_at != context["finished_at"]
            or self.current_record_duration_seconds != context["duration_seconds"]
            or self.current_record_storage != context["storage"]
            or self.current_record_cache_gb != context["cache_gb"]
        )
        self.bag_size_request_id += 1
        self.is_reading_bag_size = False
        self.current_bag_paths = context["paths"]
        self.current_record_profile = context.get("profile")
        self.current_record_topics = context["topics"]
        self.current_record_product = context["product"]
        self.current_record_themes = context["themes"]
        self.current_record_started_at = context["started_at"]
        self.current_record_finished_at = context["finished_at"]
        self.current_record_duration_seconds = context["duration_seconds"]
        self.current_record_storage = context["storage"]
        self.current_record_cache_gb = context["cache_gb"]
        return changed

    def _set_record_detail_visible(self, visible: bool) -> bool:
        current = widget_visible(self.record_detail_widget, visible)
        changed = current != visible
        self.record_detail_widget.setVisible(visible)
        return changed

    def _set_pull_progress_visible(self, visible: bool) -> bool:
        widgets = (
            self.progress_bar,
            self.transfer_percent_label,
            self.transfer_speed_label,
            self.transfer_eta_label,
        )
        changed = any(widget_visible(widget, visible) != visible for widget in widgets)
        for widget in widgets:
            widget.setVisible(visible)
        return changed

    def _set_pull_progress_value(self, value: int, animated: bool = True) -> bool:
        value = max(0, min(100, int(value)))
        current = (
            self.progress_bar.value()
            if callable(getattr(self.progress_bar, "value", None))
            else getattr(self.progress_bar, "current_value", 0)
        )
        running = self.progress_animation.state() == QAbstractAnimation.Running
        changed = current != value or running
        if not changed:
            return False
        if not animated:
            self.progress_animation.stop()
            self.progress_bar.setValue(value)
            return True
        if running:
            self.progress_animation.stop()
        self.progress_animation.setStartValue(current)
        self.progress_animation.setEndValue(value)
        self.progress_animation.start()
        return True
