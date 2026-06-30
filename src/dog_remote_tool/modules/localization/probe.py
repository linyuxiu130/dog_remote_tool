from __future__ import annotations

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.core.shell import CommandSpec, remote_env, ssh_command
import dog_remote_tool.modules.localization.alg as _localization_alg


def status_command(profile: ProductProfile) -> CommandSpec:
    inner = (
        f"{remote_env(profile)}; "
        "source /opt/runtime/env.bash >/dev/null 2>&1 || true; "
        "echo '--- alg loc status ---'; "
        f"{_localization_alg.alg_loc_status_inner()} || exit $?; "
        "echo '--- status code note ---'; "
        "echo 'alg get_loc_status: ContinuousLoc/LocOk 表示定位正常，Error/Fail 表示失败。'"
    )
    return CommandSpec("查看定位状态", ssh_command(profile, inner), concurrency="parallel")


def probe_status_command(profile: ProductProfile) -> str:
    loc_status_capture = (
        f"ALG_LOC_OUTPUT=$({_localization_alg.alg_loc_status_inner()} || exit $?); "
        "printf '%s\\n' \"$ALG_LOC_OUTPUT\"; "
        "ALG_LOC_VALUE=$(printf '%s\\n' \"$ALG_LOC_OUTPUT\" | awk -F= '/^ALG_LOC_STATUS=/ {value=$2} END {print value}'); "
    )
    inner = (
        f"{remote_env(profile)}; "
        "source /opt/runtime/env.bash >/dev/null 2>&1 || true; "
        f"{loc_status_capture}"
        "case \"$ALG_LOC_VALUE\" in ContinuousLoc|continuousloc|LocOk|InitLocOk) echo STATUS=success; echo TEXT=连续定位正常; echo ALG_LOC_STATUS=$ALG_LOC_VALUE; exit 0 ;; esac; "
        "case \"$ALG_LOC_VALUE\" in Error|Fail|Failed|LocError|LocLoss|LocTimeout) echo STATUS=error; echo TEXT=定位失败; echo ALG_LOC_STATUS=$ALG_LOC_VALUE; exit 0 ;; esac; "
        "case \"$ALG_LOC_VALUE\" in Init|InitLocing|Relocating|Locating) echo STATUS=locating; echo TEXT=定位中; echo ALG_LOC_STATUS=$ALG_LOC_VALUE; exit 0 ;; esac; "
        "case \"$ALG_LOC_VALUE\" in Ready|ready|StandBy|Standby) echo STATUS=ready; echo TEXT=定位待加载; echo ALG_LOC_STATUS=$ALG_LOC_VALUE; exit 0 ;; esac; "
        "echo STATUS=unknown; echo TEXT=未知定位状态; echo ALG_LOC_STATUS=$ALG_LOC_VALUE"
    )
    return ssh_command(profile, inner)
