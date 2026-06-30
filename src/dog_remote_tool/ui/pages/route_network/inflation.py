from __future__ import annotations

from dog_remote_tool.modules.navigation.route_network import MapMetadata
from dog_remote_tool.ui.route_inflation_overlay import DEFAULT_ROUTE_INFLATION_RADIUS_M


def _route_network_page_module():
    from dog_remote_tool.ui.pages.route_network import page as route_network_page

    return route_network_page


class RouteNetworkInflationMixin:
    def effective_inflation_radius_m(self) -> float | None:
        radius = getattr(self, "inflation_radius_m", None)
        return radius if radius is not None and radius > 0 else DEFAULT_ROUTE_INFLATION_RADIUS_M

    def create_current_inflation_overlay(self, metadata: MapMetadata):
        radius_m = self.effective_inflation_radius_m()
        if radius_m is None:
            return None
        return _route_network_page_module().create_inflation_overlay(metadata, radius_m=radius_m)

    def refresh_inflation_overlay(self) -> bool:
        metadata = getattr(self, "map_metadata", None)
        if metadata is None:
            return False
        overlay = self.create_current_inflation_overlay(metadata)
        if overlay is not None:
            self.canvas.set_inflation_overlay(overlay.pixmap, overlay.label)
        else:
            self.canvas.set_inflation_overlay(None, "")
        dialog = getattr(self, "active_editor_dialog", None)
        if dialog is not None and getattr(dialog, "canvas", None) is not None:
            dialog.canvas.set_inflation_overlay(self.canvas.inflation_overlay, self.canvas.inflation_overlay_label)
            if callable(getattr(dialog, "refresh_inflation_label", None)):
                dialog.refresh_inflation_label()
        self.update_inflation_info()
        return True

    def set_inflation_radius_m(self, radius_m: float | None) -> bool:
        self.inflation_radius_m = radius_m if radius_m is not None and radius_m > 0 else None
        return self.refresh_inflation_overlay()

    def update_inflation_info(self) -> None:
        label = getattr(self, "inflation_state_label", None)
        if label is None:
            return
        text = getattr(self.canvas, "inflation_overlay_label", "") or "膨胀：未读取"
        label.setText(text)
        label.setToolTip(
            "路网编辑障碍显示使用默认障碍膨胀半径。"
            if text != "膨胀：未读取"
            else "底图尚未加载，暂未生成障碍膨胀显示。"
        )
