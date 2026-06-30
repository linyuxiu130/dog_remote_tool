from __future__ import annotations

from dog_remote_tool.modules.navigation import route_network
from dog_remote_tool.ui.widget_roles import set_widget_role


class RouteNetworkScaleStatusMixin:
    def update_scale_info(self) -> None:
        graph = self.canvas.graph
        self.graph_summary_label.setText(f"路网：{len(graph.nodes)} 点 / {len(graph.edges)} 边")
        if not self.canvas.pixmap or self.canvas.pixmap.isNull() or not self.map_metadata:
            self.map_scale_label.setText("底图：未加载")
            self.scale_state_label.setText("比例：等待底图")
            self.update_inflation_info()
            set_widget_role(self.scale_state_label, "RouteInfoBadgeWarn")
            return
        image_size = (self.canvas.pixmap.width(), self.canvas.pixmap.height())
        area = route_network.map_bounds(self.map_metadata, image_size)
        self.map_scale_label.setText(
            f"底图：{self.map_metadata.resolution:.3f} m/px · {area.width:.1f} x {area.height:.1f} m"
        )
        self.map_scale_label.setToolTip(
            f"x: {area.min_x:.3f} ~ {area.max_x:.3f} m\ny: {area.min_y:.3f} ~ {area.max_y:.3f} m\n"
            "路网坐标使用 map.yaml 的 origin 和 resolution 映射到底图像素。"
        )
        bounds = route_network.graph_bounds(graph)
        if bounds is None:
            self.scale_state_label.setText("比例：底图已就绪")
            scale_role = "RouteInfoBadge"
            self.scale_state_label.setToolTip("底图已加载，等待创建或打开路网。")
        elif area.contains_bounds(bounds, tolerance=0.02):
            self.scale_state_label.setText("比例：坐标已对齐")
            scale_role = "RouteInfoBadgeOk"
            self.scale_state_label.setToolTip(
                f"路网范围 x: {bounds.min_x:.3f} ~ {bounds.max_x:.3f} m，"
                f"y: {bounds.min_y:.3f} ~ {bounds.max_y:.3f} m，位于底图范围内。"
            )
        else:
            self.scale_state_label.setText("比例：路网超出底图")
            scale_role = "RouteInfoBadgeWarn"
            self.scale_state_label.setToolTip(
                f"路网范围 x: {bounds.min_x:.3f} ~ {bounds.max_x:.3f} m，"
                f"y: {bounds.min_y:.3f} ~ {bounds.max_y:.3f} m，已超出底图范围。"
            )
        set_widget_role(self.scale_state_label, scale_role)
        self.update_inflation_info()

    def fit_canvas(self) -> None:
        self.canvas.reset_view()
        self.set_status("已适配画布", "ready")

    def clear_path_preview(self) -> None:
        self.canvas.set_path_edges([])
        self.preview_result.setText("路径高亮已清除")
        self.set_status("路径已清除", "ready")

    def set_status(self, text: str, state: str) -> None:
        self.status_label.setText(text)
        set_widget_role(
            self.status_label,
            {
                "success": "RouteStatusSuccess",
                "ready": "RouteStatusReady",
                "warning": "RouteStatusWarning",
                "error": "RouteStatusError",
            }.get(state, "RouteStatusNeutral"),
        )
