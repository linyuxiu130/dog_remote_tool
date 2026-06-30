from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QListWidgetItem

from dog_remote_tool.modules import bag
from dog_remote_tool.ui.pages.bag.helpers import default_remote_bag_path
from dog_remote_tool.ui.pages.bag.topic_actions import BagTopicActionsMixin
from dog_remote_tool.ui.pages.bag.topic_helpers import (
    editable_topic_list,
    topic_display_name,
    topic_name_exists,
    topic_tooltip,
)
from dog_remote_tool.ui.pages.bag.topic_editor import (
    active_topic_key,
    selected_topic_keys,
    set_topic_table_rows,
    topic_table_values,
)
from dog_remote_tool.ui.widget_roles import (
    set_widget_text_tooltip,
    widget_enabled,
    widget_text,
    widget_tooltip,
)


class BagTopicConfigMixin(BagTopicActionsMixin):
    def reload_topic_config(self) -> bool:
        profile = self.profile()
        product = bag.profile_product_key(profile)
        base = bag.load_record_topics(product)
        base = bag.apply_topic_overrides(base, product, self.topic_overrides)
        record_topics = bag.apply_custom_presets(base, self.custom_presets)
        remote_path = default_remote_bag_path(product, profile.home)
        storage = bag.recording_storage_for_profile(profile, product)
        current_remote_path = widget_text(self.remote_path)
        current_storage = self.storage_combo.currentText() if callable(getattr(self.storage_combo, "currentText", None)) else ""
        changed = (
            self.product != product
            or self.record_topics != record_topics
            or current_remote_path != remote_path
            or current_storage != storage
        )
        self.product = product
        self.record_topics = record_topics
        self.remote_path.setText(remote_path)
        self.storage_combo.setCurrentText(storage)
        self._refresh_topic_list()
        self._topic_selection_changed()
        return changed

    def default_remote_bag_path(self) -> str:
        return default_remote_bag_path(self.product, self.profile().home)

    def _refresh_topic_list(self, keep: list[str] | None = None) -> bool:
        keep = keep if keep is not None else self.selected_keys()
        current_rows = []
        if callable(getattr(self.topic_list, "count", None)) and callable(getattr(self.topic_list, "item", None)):
            for row in range(self.topic_list.count()):
                item = self.topic_list.item(row)
                if item is None:
                    continue
                current_rows.append((item.text(), item.data(Qt.UserRole), item.toolTip(), item.isSelected()))
        expected_rows = []
        keep_set = set(keep)
        for key, config in self.record_topics.items():
            expected_rows.append((self._topic_display_name(key, config), key, self._topic_tooltip(key, config), key in keep_set))
        changed = current_rows != expected_rows
        self.topic_list.blockSignals(True)
        self.topic_list.clear()
        for key, config in self.record_topics.items():
            label = self._topic_display_name(key, config)
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, key)
            item.setToolTip(self._topic_tooltip(key, config))
            self.topic_list.addItem(item)
            item.setSelected(key in keep)
        self.topic_list.blockSignals(False)
        return changed

    def _topic_display_name(self, key: str, config: dict | None = None) -> str:
        return topic_display_name(self.record_topics, key, config)

    def _topic_tooltip(self, key: str, config: dict | None = None) -> str:
        return topic_tooltip(self.record_topics, key, config)

    def _topic_name_exists(self, name: str, current_key: str = "") -> bool:
        return topic_name_exists(self.record_topics, name, current_key)

    def selected_keys(self) -> list[str]:
        return selected_topic_keys(self.topic_list)

    def topic_plan(self) -> bag.TopicPlan:
        return bag.selected_topic_plan(self.record_topics, self.selected_keys())

    def _topic_selection_changed(self) -> bool:
        keys = self.selected_keys()
        plan = self.topic_plan()
        selected_text = f"已选择: {len(keys)} 个主题"
        count = f"当前录制Topic: {len(plan.all_topics)} 个"
        enabled = bool(plan.all_topics) and not self.is_checking_topics
        selected_current = widget_text(self.selected_count_label)
        preview_current = widget_text(self.preview_count_label)
        button_current = widget_enabled(self.topic_check_btn)
        changed = selected_current != selected_text or preview_current != count or button_current != enabled
        self.selected_count_label.setText(selected_text)
        self.preview_count_label.setText(count)
        self.topic_check_btn.setEnabled(enabled)
        self._refresh_active_topic_label()
        return changed

    def _active_topic_key(self) -> str:
        return active_topic_key(self.topic_list)

    def _refresh_active_topic_label(self) -> bool:
        key = self._active_topic_key()
        label_text = widget_text(self.active_topic_label)
        label_tooltip = widget_tooltip(self.active_topic_label)
        entry_text = widget_text(self.topic_name_entry)
        entry_enabled = widget_enabled(self.topic_name_entry, True)
        table_enabled = widget_enabled(self.topic_table, True)
        if not key:
            changed = (
                label_text != "当前主题: -"
                or bool(label_tooltip)
                or bool(entry_text)
                or entry_enabled
                or self.topic_table.rowCount() != 0
                or table_enabled
            )
            set_widget_text_tooltip(self.active_topic_label, "当前主题: -", "")
            self.topic_name_entry.setText("")
            self.topic_name_entry.setEnabled(False)
            self.topic_table.setRowCount(0)
            self.topic_table.setEnabled(False)
            return changed
        name = self._topic_display_name(key)
        config = self.record_topics.get(key, {})
        topics = editable_topic_list(config)
        changed = (
            label_text != f"当前主题: {name}"
            or label_tooltip != name
            or entry_text != name
            or not entry_enabled
            or not table_enabled
            or topic_table_values(self.topic_table) != topics
        )
        set_widget_text_tooltip(self.active_topic_label, f"当前主题: {name}", name)
        self.topic_name_entry.setEnabled(True)
        self.topic_name_entry.setText(name)
        self.topic_table.setEnabled(True)
        self._set_topic_table_from_config(config)
        return changed

    def _set_topic_table_from_config(self, config: dict) -> bool:
        topics = editable_topic_list(config)
        changed = topic_table_values(self.topic_table) != topics
        self._updating_topic_table = True
        set_topic_table_rows(self.topic_table, topics)
        self._updating_topic_table = False
        return changed

    def _parse_topic_table(self) -> list[str]:
        return topic_table_values(self.topic_table)
