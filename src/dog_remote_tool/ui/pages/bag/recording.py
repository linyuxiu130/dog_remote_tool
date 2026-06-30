from __future__ import annotations

from dog_remote_tool.ui.pages.bag.recording_lifecycle import BagRecordingLifecycleMixin
from dog_remote_tool.ui.pages.bag.recording_remote import BagRecordingRemoteMixin
from dog_remote_tool.ui.pages.bag.recording_session import BagRecordingSessionMixin
from dog_remote_tool.ui.pages.bag.recording_size import BagRecordingSizeMixin


class BagRecordingMixin(
    BagRecordingLifecycleMixin,
    BagRecordingSizeMixin,
    BagRecordingSessionMixin,
    BagRecordingRemoteMixin,
):
    pass
