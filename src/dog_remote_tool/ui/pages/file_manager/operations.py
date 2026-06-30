from __future__ import annotations

from dog_remote_tool.ui.pages.file_manager.operation_edit import FileManagerEditMixin
from dog_remote_tool.ui.pages.file_manager.operation_navigation import FileManagerNavigationMixin
from dog_remote_tool.ui.pages.file_manager.operation_preview import FileManagerPreviewMixin
from dog_remote_tool.ui.pages.file_manager.operation_selection import FileManagerSelectionMixin
from dog_remote_tool.ui.pages.file_manager.operation_transfer import FileManagerTransferMixin


class FileManagerOperationsMixin(
    FileManagerNavigationMixin,
    FileManagerEditMixin,
    FileManagerTransferMixin,
    FileManagerSelectionMixin,
    FileManagerPreviewMixin,
):
    pass
