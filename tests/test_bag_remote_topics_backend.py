import pytest

from dog_remote_tool.modules.bag import remote_topics as bag_remote_topics


def test_clamp_inspect_options_limits_sample_seconds_and_workers():
    assert bag_remote_topics.clamp_inspect_options(0.1, 1) == (0.5, 4)
    assert bag_remote_topics.clamp_inspect_options(20, 99) == (10.0, 32)
    assert bag_remote_topics.clamp_inspect_options(1.5, 16) == (1.5, 16)


def test_list_remote_topics_script_wraps_env_and_probe():
    script = bag_remote_topics.list_remote_topics_script(["source /opt/ros/humble/setup.bash"])

    assert script.startswith("source /opt/ros/humble/setup.bash\npython3 - <<'PY'\n")
    assert "dog_remote_topic_list_probe" in script
    assert script.endswith("\nPY\n")


def test_inspect_remote_topics_script_replaces_sampling_placeholders():
    script, sample_seconds, batch_size = bag_remote_topics.inspect_remote_topics_script([], 20, 99)

    assert sample_seconds == 10.0
    assert batch_size == 32
    assert "SAMPLE_SECONDS = 10.0" in script
    assert "BATCH_SIZE = 32" in script
    assert "__SAMPLE_SECONDS__" not in script
    assert "__BATCH_SIZE__" not in script


def test_parse_remote_topics_output_uses_last_json_payload():
    rows = bag_remote_topics.parse_remote_topics_output(
        "log line\n{\"ok\": false, \"error\": \"old\"}\n{\"ok\": true, \"topics\": [{\"topic\": \"/cmd_vel\"}]}\n",
        "",
        empty_message="empty",
        failure_message="failed",
    )

    assert rows == [{"topic": "/cmd_vel"}]


def test_parse_remote_topics_output_reports_empty_and_failed_payloads():
    with pytest.raises(RuntimeError, match="empty"):
        bag_remote_topics.parse_remote_topics_output("", "", empty_message="empty", failure_message="failed")

    with pytest.raises(RuntimeError, match="boom"):
        bag_remote_topics.parse_remote_topics_output(
            "{\"ok\": false, \"error\": \"boom\"}\n",
            "",
            empty_message="empty",
            failure_message="failed",
        )
