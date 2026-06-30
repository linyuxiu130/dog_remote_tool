from __future__ import annotations

from dataclasses import dataclass

from .profiles import ProductProfile
from .quoting import quote

ROUTE_REPAIR_COOLDOWN_SECONDS = 60


@dataclass(frozen=True)
class RouteRepairRule:
    target_host: str
    subnet: str
    gateway: str = ""
    source_prefix: str = ""


def route_repair_rule(profile: ProductProfile) -> RouteRepairRule | None:
    host = _profile_host(profile)
    jump_host = getattr(profile, "jump_host", "")
    if host.startswith("192.168.168.") and jump_host:
        return RouteRepairRule(
            target_host=host,
            subnet="192.168.168.0/24",
            gateway=jump_host,
            source_prefix="192.168.168.",
        )
    if host.startswith("192.168.234."):
        return RouteRepairRule(
            target_host=host,
            subnet="192.168.234.0/24",
            source_prefix="192.168.234.",
        )
    return None


def _profile_host(profile: ProductProfile) -> str:
    host = getattr(profile, "host", "")
    if host:
        return host
    target = getattr(profile, "target", "")
    return target.rsplit("@", 1)[-1]


def route_repair_command(profile: ProductProfile) -> str:
    rule = route_repair_rule(profile)
    if rule is None:
        return ""
    if rule.gateway:
        return _gateway_route_command(rule)
    return _direct_route_command(rule)


def with_route_repair(profile: ProductProfile, command: str) -> str:
    if getattr(profile, "jump_host", ""):
        return command
    route_prefix = route_repair_command(profile)
    if route_prefix:
        return f"{route_prefix}; {command}"
    return command


def _gateway_route_command(rule: RouteRepairRule) -> str:
    target = quote(rule.target_host)
    subnet = quote(rule.subnet)
    gateway = quote(rule.gateway)
    expected_route = '*" via $DOG_ROUTE_GATEWAY "*'
    repair = _privileged_route_replace(
        '"$DOG_ROUTE_SUBNET" via "$DOG_ROUTE_GATEWAY" dev "$DOG_ROUTE_DEV" src "$DOG_ROUTE_SRC" metric 50',
        '"[route] failed to repair $DOG_ROUTE_SUBNET via $DOG_ROUTE_GATEWAY dev $DOG_ROUTE_DEV"',
        '"[route] need sudo permission to repair $DOG_ROUTE_SUBNET via $DOG_ROUTE_GATEWAY"',
    )
    return (
        "{ "
        f"DOG_ROUTE_HOST={target}; "
        f"DOG_ROUTE_SUBNET={subnet}; "
        f"DOG_ROUTE_GATEWAY={gateway}; "
        "DOG_ROUTE_LINE=$(ip route get \"$DOG_ROUTE_HOST\" 2>/dev/null || true); "
        "case \"$DOG_ROUTE_LINE\" in "
        "*\" via $DOG_ROUTE_GATEWAY \"*) ;; "
        "*) "
        "DOG_GATEWAY_INFO=$(ip -o -4 addr show scope global 2>/dev/null | awk '$4 ~ /^192[.]168[.]234[.]/ {split($4,a,\"/\"); print $2\" \"a[1]; exit}'); "
        "if [ -n \"$DOG_GATEWAY_INFO\" ]; then "
        "DOG_ROUTE_DEV=${DOG_GATEWAY_INFO%% *}; "
        "DOG_ROUTE_SRC=${DOG_GATEWAY_INFO#* }; "
        f"{_cooldown_guarded_repair(repair)}"
        "else "
        "printf '%s\\n' \"[route] no 192.168.234.x interface for $DOG_ROUTE_HOST\" >&2; "
        "fi; "
        ";; "
        "esac; "
        f"{_verify_route_after(expected_route)}"
        "} >/dev/null"
    )


def _direct_route_command(rule: RouteRepairRule) -> str:
    target = quote(rule.target_host)
    subnet = quote(rule.subnet)
    source_prefix = quote(rule.source_prefix)
    expected_route = '*" src $DOG_ROUTE_SOURCE_PREFIX"*'
    repair = _privileged_route_replace(
        '"$DOG_ROUTE_SUBNET" dev "$DOG_ROUTE_DEV" src "$DOG_ROUTE_SRC" metric 50',
        '"[route] failed to repair $DOG_ROUTE_SUBNET dev $DOG_ROUTE_DEV"',
        '"[route] need sudo permission to repair $DOG_ROUTE_SUBNET"',
    )
    return (
        "{ "
        f"DOG_ROUTE_HOST={target}; "
        f"DOG_ROUTE_SUBNET={subnet}; "
        f"DOG_ROUTE_SOURCE_PREFIX={source_prefix}; "
        "DOG_ROUTE_LINE=$(ip route get \"$DOG_ROUTE_HOST\" 2>/dev/null || true); "
        "case \"$DOG_ROUTE_LINE\" in "
        "*\" src $DOG_ROUTE_SOURCE_PREFIX\"*) ;; "
        "*) "
        "DOG_DIRECT_INFO=$(ip -o -4 addr show scope global 2>/dev/null | awk '$4 ~ /^192[.]168[.]234[.]/ {split($4,a,\"/\"); print $2\" \"a[1]; exit}'); "
        "if [ -n \"$DOG_DIRECT_INFO\" ]; then "
        "DOG_ROUTE_DEV=${DOG_DIRECT_INFO%% *}; "
        "DOG_ROUTE_SRC=${DOG_DIRECT_INFO#* }; "
        f"{_cooldown_guarded_repair(repair)}"
        "fi; "
        ";; "
        "esac; "
        f"{_verify_route_after(expected_route)}"
        "} >/dev/null"
    )


def _privileged_route_replace(route_args: str, failure_message: str, permission_message: str) -> str:
    return (
        "if sudo -n true >/dev/null 2>&1; then "
        f"sudo -n ip route replace {route_args} >/dev/null 2>&1 || "
        f"printf '%s\\n' {failure_message} >&2; "
        "elif command -v pkexec >/dev/null 2>&1 && [ -n \"${DISPLAY:-}${WAYLAND_DISPLAY:-}\" ]; then "
        f"pkexec ip route replace {route_args} >/dev/null 2>&1 || "
        f"printf '%s\\n' {failure_message} >&2; "
        "else "
        f"printf '%s\\n' {permission_message} >&2; "
        "fi; "
    )


def _cooldown_guarded_repair(repair_command: str) -> str:
    return (
        "DOG_ROUTE_STATE_DIR=\"${XDG_RUNTIME_DIR:-/tmp}/dog_remote_tool_routes\"; "
        "mkdir -p \"$DOG_ROUTE_STATE_DIR\" 2>/dev/null || DOG_ROUTE_STATE_DIR=\"${TMPDIR:-/tmp}\"; "
        "DOG_ROUTE_KEY=${DOG_ROUTE_HOST//[^A-Za-z0-9_.-]/_}; "
        "DOG_ROUTE_STAMP=\"$DOG_ROUTE_STATE_DIR/$DOG_ROUTE_KEY.stamp\"; "
        "DOG_ROUTE_NOW=$(date +%s 2>/dev/null || echo 0); "
        "DOG_ROUTE_LAST=0; "
        "if [ -r \"$DOG_ROUTE_STAMP\" ]; then DOG_ROUTE_LAST=$(cat \"$DOG_ROUTE_STAMP\" 2>/dev/null || echo 0); fi; "
        "case \"$DOG_ROUTE_NOW\" in ''|*[!0-9]*) DOG_ROUTE_NOW=0;; esac; "
        "case \"$DOG_ROUTE_LAST\" in ''|*[!0-9]*) DOG_ROUTE_LAST=0;; esac; "
        f"DOG_ROUTE_COOLDOWN_SECONDS={ROUTE_REPAIR_COOLDOWN_SECONDS}; "
        "if [ $((DOG_ROUTE_NOW - DOG_ROUTE_LAST)) -ge \"$DOG_ROUTE_COOLDOWN_SECONDS\" ]; then "
        "printf '%s\\n' \"$DOG_ROUTE_NOW\" > \"$DOG_ROUTE_STAMP\" 2>/dev/null || true; "
        f"{repair_command}"
        "else "
        "printf '%s\\n' \"[route] repair cooldown active for $DOG_ROUTE_HOST\" >&2; "
        "fi; "
    )


def _verify_route_after(success_pattern: str) -> str:
    return (
        "DOG_ROUTE_AFTER=$(ip route get \"$DOG_ROUTE_HOST\" 2>/dev/null || true); "
        "case \"$DOG_ROUTE_AFTER\" in "
        f"{success_pattern}) ;; "
        "*) printf '%s\\n' \"[route] unresolved $DOG_ROUTE_HOST route: ${DOG_ROUTE_AFTER:-no route}\" >&2; ;; "
        "esac; "
    )
