from __future__ import annotations

from pathlib import Path

from PyQt5.QtWidgets import QWidget

from .map_history_card import RouteMapHistoryCard


class RouteNetworkMapHistoryCardsMixin:
    def clear_history_map_cards(self) -> None:
        layout = getattr(self, "history_map_cards_layout", None)
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.history_map_cards = {}
        self.history_map_cards_panel.hide()
        self.history_map_cards_empty.show()

    def update_history_map_cards(self, entries: list[tuple[str, str, str]]) -> None:
        self.clear_history_map_cards()
        visible_entries = entries[:5]
        if not visible_entries:
            self.history_map_cards_empty.setText("暂无历史图")
            return
        self.history_map_cards_empty.hide()
        self.history_map_cards_panel.show()
        card_count = max(3, len(visible_entries))
        for label, remote_pgm, detail in visible_entries:
            card = RouteMapHistoryCard(label, remote_pgm, detail, self.select_history_map)
            self.history_map_cards[remote_pgm] = card
            self.history_map_cards_layout.addWidget(card, 1)
            self.update_history_map_card_thumbnail(remote_pgm)
        for _index in range(card_count - len(visible_entries)):
            spacer = QWidget()
            spacer.setMaximumWidth(420)
            self.history_map_cards_layout.addWidget(spacer, 1)
        self.update_history_map_card_selection()
        self.preload_history_map_card_thumbnails(visible_entries)

    def update_history_map_card_selection(self) -> None:
        selected = self.selected_history_map_pgm()
        for remote_pgm, card in getattr(self, "history_map_cards", {}).items():
            card.set_selected(remote_pgm == selected)

    def update_history_map_card_thumbnail(self, remote_pgm: str, local_dir: Path | None = None) -> bool:
        card = getattr(self, "history_map_cards", {}).get(remote_pgm)
        if card is None:
            return False
        local_dir = local_dir or self.local_paths_for_history(remote_pgm)[0].parent
        return card.set_thumbnail_from_file(local_dir / "map.pgm")
