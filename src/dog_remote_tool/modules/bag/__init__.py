from __future__ import annotations

from pathlib import Path

import dog_remote_tool.modules.bag.backend as _bag_backend
import dog_remote_tool.modules.bag.calibration as _bag_calibration
import dog_remote_tool.modules.bag.local as _bag_local
import dog_remote_tool.modules.bag.logs as _bag_logs
import dog_remote_tool.modules.bag.names as _bag_names
import dog_remote_tool.modules.bag.recording_plan as _bag_recording_plan
import dog_remote_tool.modules.bag.topic_check as _bag_topic_check
import dog_remote_tool.modules.bag.topics as _bag_topics
import dog_remote_tool.modules.bag.transfer as _bag_transfer


REMOTE_CALIBRATION_FILES = _bag_calibration.REMOTE_CALIBRATION_FILES
TOPIC_CHECK_ALTERNATIVE_GROUPS = _bag_topic_check.TOPIC_CHECK_ALTERNATIVE_GROUPS
DEFAULT_LOCAL_DATA_ROOT = Path.home() / "data"
DEFAULT_LOCAL_BAG_DIR = str(DEFAULT_LOCAL_DATA_ROOT / "bags")
DEFAULT_LOCAL_LOG_DIR = str(DEFAULT_LOCAL_DATA_ROOT / "logs")
TRANSFER_COMPLETE_MARKER = _bag_transfer.TRANSFER_COMPLETE_MARKER
TRANSFER_INCOMPLETE_MARKER = _bag_transfer.TRANSFER_INCOMPLETE_MARKER

PRODUCT_RECORD_ENV = _bag_recording_plan.PRODUCT_RECORD_ENV
PRODUCT_STORAGE_OVERRIDES = _bag_recording_plan.PRODUCT_STORAGE_OVERRIDES
PROFILE_STORAGE_OVERRIDES = _bag_recording_plan.PROFILE_STORAGE_OVERRIDES

LOG_PATHS = _bag_logs.LOG_PATHS
TOPIC_CHECK_PROFILES = _bag_topic_check.TOPIC_CHECK_PROFILES

BagBackend = _bag_backend.BagBackend
normalize_topic = _bag_names.normalize_topic
safe_filename_component = _bag_names.safe_filename_component
data_package_prefix = _bag_names.data_package_prefix
standard_remote_bag_name = _bag_names.standard_remote_bag_name
standard_dataset_name = _bag_names.standard_dataset_name
dataset_name_from_remote_bags = _bag_names.dataset_name_from_remote_bags
local_bag_name_from_remote = _bag_names.local_bag_name_from_remote
profile_product_key = _bag_names.profile_product_key
format_size = _bag_names.format_size
format_rsync_speed = _bag_names.format_rsync_speed
load_bag_metadata = _bag_local.load_bag_metadata

CUSTOM_PRESET_PREFIX = _bag_topics.CUSTOM_PRESET_PREFIX
TOPIC_CONFIG_MAP = _bag_topics.TOPIC_CONFIG_MAP
DEFAULT_TOPICS = _bag_topics.DEFAULT_TOPICS
TopicPlan = _bag_topics.TopicPlan
resources_dir = _bag_topics.resources_dir
load_record_topics = _bag_topics.load_record_topics
custom_preset_key = _bag_topics.custom_preset_key
custom_preset_name_from_key = _bag_topics.custom_preset_name_from_key
is_custom_preset_key = _bag_topics.is_custom_preset_key
config_dir = _bag_topics.config_dir
load_custom_presets = _bag_topics.load_custom_presets
save_custom_presets = _bag_topics.save_custom_presets
load_topic_overrides = _bag_topics.load_topic_overrides
save_topic_overrides = _bag_topics.save_topic_overrides
apply_topic_overrides = _bag_topics.apply_topic_overrides
apply_custom_presets = _bag_topics.apply_custom_presets
selected_topic_plan = _bag_topics.selected_topic_plan
suggest_similar_topics = _bag_topics.suggest_similar_topics
add_topic_suggestions = _bag_topics.add_topic_suggestions

RecordPlan = _bag_recording_plan.RecordPlan
recording_storage_for_profile = _bag_recording_plan.recording_storage_for_profile
