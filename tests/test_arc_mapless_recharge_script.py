from __future__ import annotations

import importlib.util
import sys
from types import SimpleNamespace
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "arc_mapless_recharge_test.py"
MAPPED_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "arc_mapped_recharge_test.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("arc_mapless_recharge_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_mapped_script_module():
    spec = importlib.util.spec_from_file_location("arc_mapped_recharge_test", MAPPED_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_format_duration_uses_hh_mm_ss():
    module = load_script_module()
    assert module.format_duration(0) == "00:00:00"
    assert module.format_duration(3661) == "01:01:01"


def test_success_rate_uses_completed_rounds():
    module = load_script_module()
    assert module.success_rate(0, 0) == 0.0
    assert module.success_rate(3, 4) == 75.0


def test_is_charging_accepts_arc_topic_and_app_status():
    module = load_script_module()
    assert module.is_charging({"ARC_DOCK_STATE": "2"})
    assert module.is_charging({"ARC_STATE": "7"})
    assert module.is_charging({"ARC_APP_ALG_STATUS": "Charging"})
    assert module.is_charging({"DOG_REMOTE_CHARGING": "1"})
    assert not module.is_charging({"ARC_DOCK_STATE": "5", "ARC_APP_DOCK_STATUS": "StandBy"})


def test_has_arc_charge_state_ignores_missing_topic_values():
    module = load_script_module()

    assert module.has_arc_charge_state({"ARC_DOCK_TEXT": "无数据", "ARC_TEXT": "未知"}) is False
    assert module.has_arc_charge_state({"ARC_STATE": "0", "ARC_TEXT": "待机"}) is True


def test_charging_evidence_lists_arc_app_and_battery_sources():
    module = load_script_module()
    evidence = module.charging_evidence(
        {
            "ARC_DOCK_STATE": "2",
            "ARC_DOCK_TEXT": "充电中",
            "ARC_APP_DOCK_STATUS": "Charging",
            "DOG_REMOTE_CHARGING": "1",
            "DOG_REMOTE_BATTERY": "64",
        }
    )
    assert "/arc/dock_state=2(充电中)" in evidence
    assert "get_arc_dock_status=Charging" in evidence
    assert "DOG_REMOTE_CHARGING=1, battery=64%" in evidence


def test_read_charging_evidence_skips_battery_when_arc_state_is_decisive(monkeypatch):
    module = load_script_module()
    profile = module.get_product("zg_lidar_nx")
    calls = []

    monkeypatch.setattr(module, "read_arc_status", lambda _profile: {"ARC_APP_DOCK_STATUS": "Charging"})
    monkeypatch.setattr(module, "read_battery_status", lambda _profile: calls.append(_profile) or {"DOG_REMOTE_CHARGING": "1"})

    assert module.read_charging_evidence(profile) == {"ARC_APP_DOCK_STATUS": "Charging"}
    assert calls == []


def test_read_charging_evidence_reads_battery_when_arc_state_is_missing(monkeypatch):
    module = load_script_module()
    profile = module.get_product("zg_lidar_nx")

    monkeypatch.setattr(module, "read_arc_status", lambda _profile: {"ARC_DOCK_TEXT": "无数据"})
    monkeypatch.setattr(module, "read_battery_status", lambda _profile: {"DOG_REMOTE_CHARGING": "1", "DOG_REMOTE_BATTERY": "64"})

    assert module.read_charging_evidence(profile) == {
        "ARC_DOCK_TEXT": "无数据",
        "DOG_REMOTE_CHARGING": "1",
        "DOG_REMOTE_BATTERY": "64",
    }


def test_undock_reset_verified_uses_actual_charging_state():
    module = load_script_module()

    assert module.undock_reset_verified({"ARC_APP_ALG_STATUS": "StandBy", "ARC_APP_DOCK_STATUS": "StandBy", "DOG_REMOTE_CHARGING": "0"})
    assert module.undock_reset_verified({"ARC_APP_ALG_STATUS": "StandBy", "ARC_APP_DOCK_STATUS": "StandBy", "DOG_REMOTE_CHARGING": "1"})
    assert module.undock_reset_verified({"ARC_STATE": "0", "ARC_DOCK_STATE": "0"})
    assert not module.undock_reset_verified({"ARC_APP_ALG_STATUS": "Charging", "ARC_APP_DOCK_STATUS": "Charging"})
    assert not module.undock_reset_verified({"ARC_DOCK_STATE": "2", "DOG_REMOTE_CHARGING": "1"})


def test_parse_args_defaults_to_120_second_undock_and_one_retry():
    module = load_script_module()

    args = module.parse_args([])

    assert args.count == 50
    assert args.count_was_provided is False
    assert args.undock_timeout == 120
    assert args.undock_retries == 1
    assert args.settle_seconds == 2.0


def test_parse_args_tracks_explicit_count():
    module = load_script_module()

    args = module.parse_args(["--count", "3"])

    assert args.count == 3
    assert args.count_was_provided is True


def test_prompt_count_if_needed_accepts_interactive_count(monkeypatch):
    module = load_script_module()
    args = module.parse_args([])

    monkeypatch.setattr(module.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _prompt: "4")

    module.prompt_count_if_needed(args, test_title="有图回充测试")

    assert args.count == 4


def test_confirm_start_prints_recharge_test_count(capsys):
    module = load_script_module()
    profile = module.get_product("zg_lidar_nx")
    args = module.parse_args(["--count", "3", "--yes"])

    module.confirm_start(profile, args)

    assert "无图回充测试次数：3" in capsys.readouterr().out


def test_mapped_script_requires_map_pcd():
    module = load_mapped_script_module()

    args = module.base.parse_args(["--count", "2", "--yes"], configure_parser=module.configure_parser)

    module.validate_args(args)

    assert args.map_pcd == ""


def test_mapped_script_accepts_positional_map_pcd():
    module = load_mapped_script_module()

    args = module.base.parse_args(
        ["/ota/alg_data/map/history_map/a/map.pcd", "--count", "2", "--yes"],
        configure_parser=module.configure_parser,
    )
    module.validate_args(args)

    assert args.map_pcd == "/ota/alg_data/map/history_map/a/map.pcd"


def test_mapped_dock_action_uses_start_arc_with_map(monkeypatch):
    module = load_script_module()
    profile = module.get_product("zg_lidar_nx")
    progress = module.Progress(total=1, started_at=0)
    args = SimpleNamespace(map_pcd="/ota/alg_data/map/history_map/a/map.pcd", dock_timeout=90)
    calls = []

    monkeypatch.setattr(
        module.navigation,
        "start_arc_with_map_command",
        lambda _profile, _map, monitor_seconds: calls.append((_profile, _map, monitor_seconds))
        or SimpleNamespace(command="mapped-dock"),
    )
    monkeypatch.setattr(module, "run_command_streaming", lambda command, _progress: module.CommandResult(0, command, 1.0))

    result = module.run_mapped_dock_action(profile, args, progress)

    assert result.output == "mapped-dock"
    assert calls == [(profile, "/ota/alg_data/map/history_map/a/map.pcd", 90)]


def test_mapped_script_scan_command_finds_arc_marked_yaml():
    module = load_mapped_script_module()
    profile = module.base.get_product("zg_lidar_nx")

    command = module.arc_marked_map_list_command(profile, "/ota/alg_data/map")

    assert "arc_position_flag" in command
    assert "/ota/alg_data/map/history_map" in command
    assert "map.pcd" in command


def test_mapped_script_auto_selects_single_arc_marked_map(monkeypatch):
    module = load_mapped_script_module()
    profile = module.base.get_product("zg_lidar_nx")
    args = module.base.parse_args(["--count", "2", "--yes"], configure_parser=module.configure_parser)
    module.validate_args(args)

    monkeypatch.setattr(module, "list_arc_marked_maps", lambda _profile, _root: [("a", "/ota/alg_data/map/history_map/a/map.pcd")])

    module.prepare_args(profile, args)

    assert args.map_pcd == "/ota/alg_data/map/history_map/a/map.pcd"


def test_mapped_script_noninteractive_multiple_maps_require_explicit_choice(monkeypatch, capsys):
    module = load_mapped_script_module()
    monkeypatch.setattr(module.sys.stdin, "isatty", lambda: False)

    try:
        module.choose_map_pcd([("a", "/a/map.pcd"), ("b", "/b/map.pcd")])
    except SystemExit as exc:
        assert "非交互模式" in str(exc)
    else:
        raise AssertionError("choose_map_pcd should fail for multiple maps without tty")

    assert "--map-pcd" in capsys.readouterr().out


def test_mapped_script_interactive_single_map_still_prompts(monkeypatch, capsys):
    module = load_mapped_script_module()

    monkeypatch.setattr(module.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _prompt: "")

    assert module.choose_map_pcd([("a", "/a/map.pcd")]) == "/a/map.pcd"
    assert "请选择已标记充电桩地图" in capsys.readouterr().out


def test_undock_reset_retries_when_still_charging(monkeypatch):
    module = load_script_module()
    profile = module.get_product("zg_lidar_nx")
    progress = module.Progress(total=1, started_at=0)
    args = SimpleNamespace(count=1, undock_timeout=120, reset_evidence_timeout=1, undock_retries=1)
    calls = []

    def fake_run_arc_action(_profile, action, timeout_seconds, _progress):
        calls.append((action, timeout_seconds))
        return module.CommandResult(8, "[ERROR] ARC 动作等待超时。", 1.0)

    monkeypatch.setattr(module, "run_arc_action", fake_run_arc_action)
    monkeypatch.setattr(module, "release_arc_control", lambda *_args: module.CommandResult(0, "[INFO] released", 0.1))
    monkeypatch.setattr(module, "wait_for_undock_reset", lambda *_args: {"ARC_APP_DOCK_STATUS": "Charging"})
    monkeypatch.setattr(module, "clear_status_line", lambda *_args: None)
    monkeypatch.setattr(module, "print_status_line", lambda *_args, **_kwargs: None)

    ok, result, values = module.run_undock_reset_with_retries(profile, args, progress, 1)

    assert ok is False
    assert result.elapsed == 2.0
    assert values == {"ARC_APP_DOCK_STATUS": "Charging"}
    assert calls == [("undock", 120), ("undock", 120)]


def test_stop_cleanup_skips_undock_when_already_non_charging(monkeypatch):
    module = load_script_module()
    profile = module.get_product("zg_lidar_nx")
    progress = module.Progress(total=1, started_at=0)
    args = SimpleNamespace(undock_timeout=120)
    calls = []
    release_calls = []

    monkeypatch.setattr(module, "read_charging_evidence", lambda _profile: {"ARC_APP_DOCK_STATUS": "StandBy"})
    monkeypatch.setattr(module, "run_arc_action", lambda *_args: calls.append(_args))
    monkeypatch.setattr(
        module,
        "release_arc_control",
        lambda *_args: release_calls.append(_args) or module.CommandResult(0, "[INFO] released", 0.1),
    )
    monkeypatch.setattr(module, "clear_status_line", lambda *_args: None)
    monkeypatch.setattr(module, "print_status_line", lambda *_args, **_kwargs: None)

    assert module.stop_cleanup(profile, args, progress, "测试") is True
    assert calls == []
    assert release_calls == [(profile, progress)]


def test_stop_cleanup_uses_shared_arc_undock_action(monkeypatch):
    module = load_script_module()
    profile = module.get_product("zg_lidar_nx")
    progress = module.Progress(total=1, started_at=0)
    args = SimpleNamespace(undock_timeout=120)
    calls = []
    snapshots = [
        {"ARC_APP_DOCK_STATUS": "Charging"},
        {"ARC_APP_DOCK_STATUS": "StandBy"},
    ]

    def fake_run_arc_action(_profile, action, timeout_seconds, _progress):
        calls.append((action, timeout_seconds))
        return module.CommandResult(0, "[INFO] 出桩成功", 1.0)

    monkeypatch.setattr(module, "read_charging_evidence", lambda _profile: snapshots.pop(0))
    monkeypatch.setattr(module, "run_arc_action", fake_run_arc_action)
    monkeypatch.setattr(module, "release_arc_control", lambda *_args: module.CommandResult(0, "[INFO] released", 0.1))
    monkeypatch.setattr(module, "clear_status_line", lambda *_args: None)
    monkeypatch.setattr(module, "print_status_line", lambda *_args, **_kwargs: None)

    assert module.stop_cleanup(profile, args, progress, "测试") is True
    assert calls == [("undock", 120)]
