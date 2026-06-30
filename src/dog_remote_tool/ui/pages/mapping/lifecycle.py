from __future__ import annotations


def _mapping_page_class():
    from dog_remote_tool.ui.pages.mapping.page import MappingPage

    return MappingPage


def _mapping_page_module():
    from dog_remote_tool.ui.pages.mapping import page as mapping_page

    return mapping_page


class MappingLifecycleMixin:
    def activate_page(self) -> None:
        if self.page_active:
            return
        mapping_page = _mapping_page_module()
        self.page_active = True
        mapping_page.QTimer.singleShot(200, self.refresh_mapping_page)

    def deactivate_page(self) -> None:
        self.page_active = False
        self._stop_refresh_processes(clear_maps=False)

    def _stop_refresh_processes(self, clear_maps: bool) -> None:
        mapping_page = _mapping_page_module()
        page = _mapping_page_class()
        self.status_slot.stop()
        self.map_list_slot.stop()
        self.map_fetch_slot.stop()
        self.map_thumbnail_slot.stop()
        if clear_maps:
            self.preview_autoload_enabled = False
            self.preview_remote_pgm = ""
            self.fetching_preview_remote_pgm = ""
            self.preview_file = ""
            self.preview_pixmap = None
            self.map_entry_details = {}
            self.map_entries_signature = ()
            self.map_thumbnail_queue = []
            with mapping_page.QSignalBlocker(self.map_selector):
                self.map_selector.clear()
            page.clear_map_cards(self)
            self.selected_map_detail.setText("远端目录：--")
            if hasattr(self, "edit_map_pgm_button"):
                self.edit_map_pgm_button.setEnabled(False)
            self.preview_status.setToolTip("")

    def shutdown_processes(self) -> None:
        self.page_active = False
        self._stop_refresh_processes(clear_maps=False)
