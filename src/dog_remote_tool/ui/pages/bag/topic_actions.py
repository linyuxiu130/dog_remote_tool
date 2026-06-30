from __future__ import annotations

from PyQt5.QtWidgets import QInputDialog, QMessageBox, QTableWidgetItem

from dog_remote_tool.modules import bag
from dog_remote_tool.ui.pages.bag.topic_editor import selected_topic_table_values
from dog_remote_tool.ui.pages.bag.topic_helpers import set_config_topics


class BagTopicActionsMixin:
    def _topic_table_changed(self, _item: QTableWidgetItem) -> bool:
        if self._updating_topic_table:
            return False
        key = self._active_topic_key()
        if not key:
            return False
        return self._apply_topic_table_to_theme(key)

    def _apply_topic_table_to_theme(self, key: str) -> bool:
        topics = self._parse_topic_table()
        config = self.record_topics.setdefault(key, {"name": key, "topics": []})
        changed = config.get("topics", []) != topics
        set_config_topics(config, topics)
        self._persist_topic_config(key)
        self._topic_selection_changed()
        return changed

    def _persist_topic_config(self, key: str) -> bool:
        config = self.record_topics.get(key, {})
        topics = list(dict.fromkeys(config.get("topics", [])))
        if bag.is_custom_preset_key(key):
            self.custom_presets[bag.custom_preset_name_from_key(key)] = topics
            bag.save_custom_presets(self.custom_presets)
            return True
        if key == "custom":
            return False
        entry = self.topic_overrides.setdefault(self.product, {}).setdefault(key, {})
        if config.get("name"):
            entry["name"] = config.get("name", key)
        entry["topics"] = topics
        entry["zstd_topics"] = []
        entry["lz4_topics"] = []
        entry.pop("added", None)
        entry.pop("removed", None)
        bag.save_topic_overrides(self.topic_overrides)
        return True

    def save_active_topic_name(self) -> bool:
        key = self._active_topic_key()
        name = self.topic_name_entry.text().strip()
        if not key or not name:
            QMessageBox.information(self, "提示", "请选择主题并输入名称")
            return False
        if self._topic_name_exists(name, key):
            QMessageBox.warning(self, "名称重复", f"主题已存在: {name}")
            return False
        if bag.is_custom_preset_key(key):
            old_name = bag.custom_preset_name_from_key(key)
            if name == old_name:
                return False
            self.custom_presets[name] = self.custom_presets.pop(old_name, [])
            bag.save_custom_presets(self.custom_presets)
            self.record_topics = bag.apply_custom_presets(
                bag.apply_topic_overrides(bag.load_record_topics(self.product), self.product, self.topic_overrides),
                self.custom_presets,
            )
            keep = [bag.custom_preset_key(name)]
            self._log(f"[自定义Topic] 已重命名主题: {old_name} -> {name}")
        else:
            config = self.record_topics.setdefault(key, {"name": key, "topics": []})
            config["name"] = name
            entry = self.topic_overrides.setdefault(self.product, {}).setdefault(key, {})
            entry["name"] = name
            bag.save_topic_overrides(self.topic_overrides)
            keep = [key]
            self._log(f"[主题Topic] 已更新主题名称: {key} -> {name}")
        self._refresh_topic_list(keep)
        self._topic_selection_changed()
        return True

    def select_all_topics(self) -> bool:
        changed = len(self.topic_list.selectedItems()) < self.topic_list.count()
        self.topic_list.selectAll()
        self._topic_selection_changed()
        return changed

    def deselect_all_topics(self) -> bool:
        changed = bool(self.topic_list.selectedItems())
        self.topic_list.clearSelection()
        self._topic_selection_changed()
        return changed

    def create_custom_theme(self) -> bool:
        name, ok = QInputDialog.getText(self, "新增主题", "主题名称")
        if not ok:
            return False
        name = name.strip()
        if not name:
            QMessageBox.information(self, "提示", "请输入主题名称")
            return False
        if name in self.custom_presets or self._topic_name_exists(name):
            QMessageBox.warning(self, "名称重复", f"主题已存在: {name}")
            return False
        self.custom_presets[name] = []
        bag.save_custom_presets(self.custom_presets)
        self.record_topics = bag.apply_custom_presets(
            bag.apply_topic_overrides(bag.load_record_topics(self.product), self.product, self.topic_overrides),
            self.custom_presets,
        )
        key = bag.custom_preset_key(name)
        self._refresh_topic_list([key])
        self._topic_selection_changed()
        self._log(f"[主题] 已新增: {name}")
        return True

    def delete_active_theme(self) -> bool:
        key = self._active_topic_key()
        if not key:
            QMessageBox.information(self, "提示", "请选择要删除的主题")
            return False
        if not bag.is_custom_preset_key(key):
            QMessageBox.information(self, "提示", "内置主题不能删除；可修改名称或 Topic")
            return False
        name = bag.custom_preset_name_from_key(key)
        reply = QMessageBox.question(self, "删除主题", f"删除主题“{name}”？", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return False
        self.custom_presets.pop(name, None)
        bag.save_custom_presets(self.custom_presets)
        self.record_topics = bag.apply_custom_presets(
            bag.apply_topic_overrides(bag.load_record_topics(self.product), self.product, self.topic_overrides),
            self.custom_presets,
        )
        self._refresh_topic_list([])
        self._topic_selection_changed()
        self._log(f"[主题] 已删除: {name}")
        return True

    def add_topic_to_active_theme(self) -> bool:
        key = self._active_topic_key()
        topic = bag.normalize_topic(self.topic_entry.text())
        if not key or not topic:
            return False
        topics = self._parse_topic_table()
        if topic in topics:
            return False
        topics.append(topic)
        config = self.record_topics.setdefault(key, {"name": key, "topics": []})
        set_config_topics(config, topics)
        if key != "custom":
            self._persist_topic_config(key)
        self.topic_entry.clear()
        self._log(f"[主题Topic] 已添加: {key} -> {topic}")
        self._topic_selection_changed()
        return True

    def remove_selected_topics_from_active_theme(self) -> bool:
        key = self._active_topic_key()
        if not key:
            return False
        selected_rows, selected = selected_topic_table_values(self.topic_table)
        if not selected:
            QMessageBox.information(self, "提示", "请先在 Topic 表格中选择要删除的行")
            return False
        for row in selected_rows:
            self.topic_table.removeRow(row)
        topics = self._parse_topic_table()
        config = self.record_topics.setdefault(key, {"name": key, "topics": []})
        set_config_topics(config, topics)
        if key != "custom":
            self._persist_topic_config(key)
        self._log(f"[主题Topic] 已从 {key} 删除: {', '.join(dict.fromkeys(selected))}")
        self._topic_selection_changed()
        return True
