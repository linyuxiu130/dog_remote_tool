from __future__ import annotations

from importlib import import_module
from pathlib import Path


def _remote_access_page_module():
    return import_module("dog_remote_tool.ui.pages.remote_access.page")


class RemoteAccessDialogMixin:
    def choose_zip(self) -> bool:
        start_dir = str(Path(self.zip_path.text()).expanduser().parent)
        if not Path(start_dir).is_dir():
            start_dir = str(Path.home() / "Downloads")
        path, _ = _remote_access_page_module().QFileDialog.getOpenFileName(
            self,
            "选择 FRP 包",
            start_dir,
            "Zip (*.zip)",
        )
        if path:
            self.zip_path.setText(path)
            return True
        return False

    def choose_community_deb(self) -> bool:
        start_dir = str(Path(self.community_deb_path.text()).expanduser().parent)
        if not Path(start_dir).is_dir():
            start_dir = str(Path.home() / "Downloads")
        path, _ = _remote_access_page_module().QFileDialog.getOpenFileName(
            self,
            "选择 community-node deb",
            start_dir,
            "Deb (*.deb);;All (*)",
        )
        if path:
            self.community_deb_path.setText(path)
            return True
        return False
