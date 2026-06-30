from __future__ import annotations

from dog_remote_tool.modules import navigation
from dog_remote_tool.ui.pages.navigation import status_helpers as _status_helpers
from dog_remote_tool.ui.widget_roles import set_widget_role, set_widget_text_style_tooltip


def _navigation_page_class():
    from dog_remote_tool.ui.pages.navigation.page import NavigationPage

    return NavigationPage


def _stop_navigation_task_in_flight(page) -> bool:
    tasks = getattr(getattr(page, "runner", None), "tasks", None)
    if not isinstance(tasks, dict):
        return False
    return any(getattr(task, "title", "") == "执行：停止导航" for task in tasks.values())


class NavigationActionButtonsMixin:
    def update_navigation_action_buttons(self, values: dict[str, str] | None = None) -> bool:
        page = _navigation_page_class()
        values = values if values is not None else getattr(self, "last_status_values", {})
        ready, reason = page.navigation_action_ready_reason(self, values or {})
        running = page.remote_navigation_running(self, values or {})
        stop_in_flight = _stop_navigation_task_in_flight(self)
        stop_waiting = bool(getattr(self, "stop_navigation_waiting_remote_confirm", False) or stop_in_flight)
        waiting_started_at = float(getattr(self, "stop_navigation_waiting_started_at", 0.0) or 0.0)
        has_fresh_remote_status = float(getattr(self, "last_status_at", 0.0) or 0.0) > waiting_started_at
        if getattr(self, "stop_navigation_waiting_remote_confirm", False) and not stop_in_flight and has_fresh_remote_status:
            self.stop_navigation_waiting_remote_confirm = False
            stop_waiting = False
        arc_ready, arc_reason = page.arc_calibration_ready_reason(self, values or {})
        arc_mark_ready, arc_mark_reason = page.arc_mark_ready_reason(self, values or {})
        recharge_action, recharge_label, recharge_ready, recharge_reason = page.mapped_recharge_action_state(self, values or {})
        route_ready, route_reason = page.route_navigation_ready_reason(self)
        loop_enabled = bool(getattr(self, "navigation_loop_enabled", False))
        selected_route = page.local_route_geojson_path(self)
        selected_map_pgm = self.selected_map_pgm()
        has_selected_map = bool(self.selected_map_pgm())
        has_local_route = bool(selected_route and selected_route.exists())
        route_mode_loaded = (
            bool(getattr(self, "route_target_mode", False))
            and getattr(self, "route_graph", None) is not None
            and getattr(self, "route_graph_remote_pgm", "") == selected_map_pgm
        )
        route_has_targets = route_mode_loaded and bool(page.visible_navigation_points(self))
        route_state_unknown = has_selected_map and self.route_file_states.get(selected_map_pgm) is None
        route_load_ready = ready and has_selected_map and (route_ready or has_local_route or route_state_unknown)
        route_action_ready = ready and route_has_targets
        route_file_action_ready = getattr(self, "page_active", False) and page.navigation_supported(self) and has_selected_map
        if ready:
            if route_mode_loaded:
                action_text = "路网导航模式：点位导航已暂停，可选择路网目标"
            else:
                action_text = "导航可用：可发送点位/路网任务" if route_ready else "导航可用：可发送点位任务"
        else:
            action_text = f"导航阻塞：{reason}"
        action_tooltip = navigation.navigation_user_status_summary(values or {})
        if action_tooltip == "导航状态：等待刷新":
            action_tooltip = reason
        start_tooltips = {
            "point_nav_button": "使用当前点位开始导航；多个点按多点导航",
            "loop_button": "打开或关闭循环模式；开启后再点击点位/路网开始按钮才会按循环方式下发",
            "relocalize_button": "重新加载当前地图定位",
            "route_mode_button": "进入后地图点击将选择路网目标；退出后恢复点位导航",
            "route_goal_button": "按已选择的路网目标节点发送路网导航",
        }
        file_tooltips = {
            "choose_route_file_button": "打开当前历史图的路网编辑器；保存后默认同步到机器人当前历史图目录",
            "history_route_editor_button": "打开当前历史图的路网编辑器；保存后默认同步到机器人当前历史图目录",
            "upload_route_file_button": "选择本地 GeoJSON 并上传到机器人当前历史图目录",
            "history_upload_route_button": "选择本地 GeoJSON 并上传到机器人当前历史图目录",
            "export_route_file_button": "把当前历史图的本地 map.geojson 导出到指定位置",
        }
        targets = [self]
        dialog = getattr(self, "workspace_dialog", None)
        if dialog is not None:
            targets.append(dialog)
        for target in targets:
            for attr, tooltip in start_tooltips.items():
                button = getattr(target, attr, None)
                if button is None:
                    continue
                if attr == "route_mode_button":
                    button.setText("退出路网导航" if route_mode_loaded else "进入路网导航")
                    button.setEnabled(route_mode_loaded or route_load_ready)
                    if route_mode_loaded:
                        button.setToolTip("退出路网导航模式，清空路网目标并恢复点位导航")
                    elif not ready:
                        button.setToolTip(reason)
                    elif has_local_route and not route_ready:
                        button.setToolTip("可加载本地路网预览；启动路网导航前需要上传到机器人")
                    elif route_ready or route_state_unknown:
                        button.setToolTip("加载 map.geojson 路网叠加并进入路网目标选择模式")
                    else:
                        button.setToolTip(route_reason)
                elif attr == "route_goal_button":
                    button.setText("开始路网导航")
                    button.setEnabled(route_action_ready)
                    if not ready:
                        button.setToolTip(reason)
                    elif route_has_targets:
                        button.setToolTip(
                            "循环模式已开启，点击后按路网循环方式下发"
                            if loop_enabled
                            else (
                                "按已选择的路网目标节点发送路网导航"
                                if route_ready
                                else f"将先在下发时检查远端路网：{route_reason}"
                            )
                        )
                    elif route_mode_loaded:
                        button.setToolTip("请先点击路网节点附近设定目标")
                    elif route_ready or has_local_route or route_state_unknown:
                        button.setToolTip("请先点击“进入路网导航”")
                    else:
                        button.setToolTip(route_reason)
                elif attr == "point_nav_button" and route_mode_loaded:
                    button.setText("点位导航")
                    button.setEnabled(False)
                    button.setToolTip("当前处于路网导航模式，请退出后使用点位导航")
                elif attr == "loop_button":
                    button.setText("循环 ON" if loop_enabled else "循环 OFF")
                    button.setEnabled(getattr(self, "page_active", False) and page.navigation_supported(self))
                    button.setToolTip(
                        "循环模式已开启；再次点击关闭"
                        if loop_enabled
                        else "循环模式已关闭；点击后，后续点位/路网开始按钮将按循环方式下发"
                    )
                    if callable(getattr(button, "setChecked", None)):
                        button.setChecked(loop_enabled)
                    set_widget_role(button, "LoopSwitchOn" if loop_enabled else "LoopSwitchOff")
                elif attr == "relocalize_button":
                    button.setText("重新定位")
                    relocalize_ready = (
                        getattr(self, "page_active", False)
                        and page.navigation_supported(self)
                        and has_selected_map
                        and not running
                    )
                    button.setEnabled(relocalize_ready)
                    if running:
                        button.setToolTip("当前正在导航，请先停止后再重新定位")
                    elif not has_selected_map:
                        button.setToolTip("请先选择历史图")
                    elif not page.navigation_supported(self):
                        button.setToolTip("当前设备不支持导航")
                    else:
                        button.setToolTip("重新加载当前地图定位")
                else:
                    if attr == "point_nav_button":
                        button.setText("点位导航")
                    button.setEnabled(ready)
                    if ready and loop_enabled and attr == "point_nav_button":
                        button.setToolTip("循环模式已开启，点击后按循环方式下发")
                    else:
                        button.setToolTip(tooltip if ready else reason)
            for attr, tooltip in file_tooltips.items():
                button = getattr(target, attr, None)
                if button is None:
                    continue
                if attr in {"choose_route_file_button", "history_route_editor_button"}:
                    local_edit_ready = getattr(self, "page_active", False) and page.navigation_supported(self)
                    button.setEnabled(local_edit_ready)
                    if route_file_action_ready:
                        button.setToolTip(tooltip)
                    elif local_edit_ready:
                        button.setToolTip("可打开本地 map.yaml 编辑路网；选择远端历史图后保存会默认同步到远端")
                    else:
                        button.setToolTip("当前设备不支持导航")
                else:
                    button.setEnabled(route_file_action_ready and has_local_route)
                    if not route_file_action_ready:
                        button.setToolTip("请先选择历史图")
                    elif not has_local_route:
                        button.setToolTip("请先点击“编辑路网”并保存 map.geojson")
                    else:
                        button.setToolTip(tooltip)
            status_label = getattr(target, "nav_action_status", None) or getattr(target, "action_status_label", None)
            if status_label is not None:
                set_widget_text_style_tooltip(
                    status_label,
                    action_text,
                    _status_helpers.NAV_ACTION_READY_STYLE if ready else _status_helpers.NAV_ACTION_BLOCKED_STYLE,
                    action_tooltip,
                )
            stop_button = getattr(target, "stop_button", None)
            if stop_button is not None:
                stop_button.setText("停止中" if stop_waiting else "停止")
                stop_enabled = (
                    getattr(self, "page_active", False)
                    and page.navigation_supported(self)
                    and not stop_waiting
                )
                stop_button.setEnabled(stop_enabled)
                if stop_waiting:
                    stop_button.setToolTip("停止命令已发送，正在等待远端确认")
                elif stop_enabled:
                    stop_button.setToolTip("停止当前远端导航任务并释放导航控制权" if running else "发送停止命令并释放导航控制权")
                elif not page.navigation_supported(self):
                    stop_button.setToolTip("当前设备不支持导航")
                else:
                    stop_button.setToolTip("停止暂不可用")
            pause_button = getattr(target, "pause_resume_button", None)
            if pause_button is not None:
                paused = page.remote_navigation_paused(self, values or {})
                pause_enabled = (
                    getattr(self, "page_active", False)
                    and page.navigation_supported(self)
                    and page.remote_navigation_running(self, values or {})
                )
                pause_button.setText("继续" if paused else "暂停")
                pause_button.setEnabled(pause_enabled)
                pause_button.setToolTip(
                    "继续当前远端导航任务，机器人可能恢复移动"
                    if paused
                    else "暂停当前远端导航任务"
                    if pause_enabled
                    else "当前没有可暂停或继续的导航任务"
                )
                set_widget_role(pause_button, "Primary" if paused else "SoftPrimary")
            arc_button = getattr(target, "arc_calibration_button", None)
            if arc_button is not None:
                arc_button.setEnabled(arc_ready)
                arc_button.setToolTip("发送 ARC 充电桩标定请求" if arc_ready else arc_reason)
            arc_mark_button = getattr(target, "arc_mark_button", None)
            if arc_mark_button is not None:
                arc_mark_button.setEnabled(arc_mark_ready)
                arc_mark_button.setToolTip("机器狗正对充电桩且稳定识别后，将桩位写入当前地图" if arc_mark_ready else arc_mark_reason)
            recharge_button = getattr(target, "mapped_recharge_button", None)
            if recharge_button is not None:
                recharge_button.setText(recharge_label)
                recharge_button.setEnabled(recharge_ready)
                recharge_button.setVisible(
                    page.arc_charging_detected(self, values or {}) or bool(getattr(self, "charging_docks", []))
                )
                recharge_button.setToolTip(recharge_reason)
                set_widget_role(recharge_button, "Danger" if recharge_action == "undock" else "Primary")
        if not ready and getattr(self, "page_active", False) and reason:
            self.last_navigation_action_reason = reason
        elif ready:
            self.last_navigation_action_reason = ""
        return ready
