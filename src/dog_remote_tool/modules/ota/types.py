from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class OtaTarget:
    key: str
    label: str
    family: str
    host: str
    user: str
    password: str

    @property
    def remote(self) -> str:
        return f"{self.user}@{self.host}"


@dataclass(frozen=True)
class OtaFirmwareModule:
    name: str
    firmware: str
    tool: str = ""
    version: str = ""
    runnable: bool = False


@dataclass(frozen=True)
class OtaPackageManifest:
    package: str
    family: str
    system_image: str = ""
    system_size: int = 0
    modules: tuple[OtaFirmwareModule, ...] = field(default_factory=tuple)

    @property
    def runnable_module_count(self) -> int:
        return sum(1 for module in self.modules if module.runnable)


@dataclass(frozen=True)
class OtaFirmwareCoverage:
    supported: tuple[OtaFirmwareModule, ...] = field(default_factory=tuple)
    unsupported: tuple[OtaFirmwareModule, ...] = field(default_factory=tuple)
    note: str = ""
