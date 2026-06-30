from __future__ import annotations

from dog_remote_tool.core.profiles import ProductProfile
from dog_remote_tool.modules.mapping import alg as _mapping_alg


def is_mapping_alg_status(profile: ProductProfile, alg_status: str) -> bool:
    del profile
    return _mapping_alg.is_alg_mapping_active(alg_status)


is_mapping_active_alg_status = is_mapping_alg_status


def alg_active_states(profile: ProductProfile) -> str:
    del profile
    return " ".join(sorted(_mapping_alg.ALG_MAPPING_STATUSES))


def mapping_status_from_alg_status(
    profile: ProductProfile,
    alg_status: str,
    error_code: str = "",
    error_msg: str = "",
) -> tuple[str, str] | None:
    del profile
    data = alg_status.strip()
    code = error_code.strip()
    status = _mapping_alg.alg_mapping_status(data, code, error_msg)
    if status is not None:
        return status
    return None

