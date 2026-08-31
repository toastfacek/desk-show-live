"""Task 4: OBS contract validation, setup-obs, and recording lifecycle."""

from __future__ import annotations

import pytest

from runtime_flight.obs_setup import (
    REQUIRED_INPUTS,
    REQUIRED_SCENES,
    setup_obs,
    validate_contract,
)
from runtime_flight.obs_session import ObsSession
from conftest_obs import FakeObsClient, FakeSceneItem, complete_obs_client


def test_validate_contract_accepts_complete_obs():
    errors = validate_contract(complete_obs_client())
    assert errors == []


@pytest.mark.parametrize("missing_scene", REQUIRED_SCENES)
def test_validate_contract_rejects_missing_scene(missing_scene):
    client = complete_obs_client()
    client.scenes.remove(missing_scene)
    errors = validate_contract(client)
    assert any(missing_scene in error for error in errors)


@pytest.mark.parametrize("missing_input", REQUIRED_INPUTS)
def test_validate_contract_rejects_missing_input(missing_input):
    client = complete_obs_client()
    del client.inputs[missing_input]
    errors = validate_contract(client)
    assert any(missing_input in error for error in errors)


def test_validate_contract_rejects_missing_scene_item():
    client = complete_obs_client()
    client.scene_items["wide"] = [
        item for item in client.scene_items["wide"] if item.source_name != "HEADLINE"
    ]
    errors = validate_contract(client)
    assert any("HEADLINE" in error and "wide" in error for error in errors)


def test_validate_contract_rejects_split_with_one_host_wide():
    client = complete_obs_client()
    client.scene_items["split"] = [
        item for item in client.scene_items["split"] if item.source_name != "HOST_WIDE"
    ]
    client.scene_items["split"].append(FakeSceneItem("HOST_WIDE", 501))
    errors = validate_contract(client)
    assert any("HOST_WIDE" in error and "split" in error for error in errors)


def test_validate_contract_rejects_split_with_duplicate_host_wide_ids():
    client = complete_obs_client()
    client.scene_items["split"] = [
        item for item in client.scene_items["split"] if item.source_name != "HOST_WIDE"
    ]
    client.scene_items["split"].extend(
        [FakeSceneItem("HOST_WIDE", 88), FakeSceneItem("HOST_WIDE", 88)]
    )
    errors = validate_contract(client)
    assert any("distinct" in error.lower() for error in errors)


def test_validate_contract_excludes_watchdog_until_task_12():
    client = complete_obs_client()
    errors = validate_contract(client)
    assert errors == []
    assert "WATCHDOG" not in REQUIRED_INPUTS


def test_validate_contract_rejects_incompatible_existing_input_kind():
    client = complete_obs_client()
    client.inputs["HEADLINE"] = "browser_source"
    errors = validate_contract(client)
    assert any("HEADLINE" in error and "incompatible" in error for error in errors)


def test_setup_obs_creates_missing_scenes_and_inputs():
    client = FakeObsClient()
    summary = setup_obs(client)
    assert client.scenes == set(REQUIRED_SCENES)
    assert set(client.inputs) == set(REQUIRED_INPUTS)
    assert summary["created_scenes"]
    assert summary["created_inputs"]


def test_setup_obs_adds_second_host_wide_scene_item_for_split():
    client = complete_obs_client()
    client.scene_items["split"] = [
        item for item in client.scene_items["split"] if item.source_name != "HOST_WIDE"
    ]
    client.scene_items["split"].append(FakeSceneItem("HOST_WIDE", 700))
    setup_obs(client)
    host_wide_ids = [
        item.scene_item_id
        for item in client.scene_items["split"]
        if item.source_name == "HOST_WIDE"
    ]
    assert len(host_wide_ids) == 2
    assert len(set(host_wide_ids)) == 2


def _create_calls(calls: list[tuple]) -> list[tuple]:
    return [
        call
        for call in calls
        if call[0] in {"create_scene", "create_input", "create_scene_item"}
    ]


def test_setup_obs_is_idempotent():
    client = FakeObsClient()
    first = setup_obs(client)
    create_calls_after_first = _create_calls(client.calls)
    second = setup_obs(client)
    assert first["created_scenes"]
    assert first["created_inputs"]
    assert second["created_scenes"] == []
    assert second["created_inputs"] == []
    assert second["created_scene_items"] == []
    assert _create_calls(client.calls) == create_calls_after_first


def test_ensure_contract_is_validate_only_and_never_creates():
    client = FakeObsClient()
    session = ObsSession(client=client)
    with pytest.raises(RuntimeError, match="missing scene"):
        session.ensure_contract()
    create_calls = [
        call
        for call in client.calls
        if call[0] in {"create_scene", "create_input", "create_scene_item"}
    ]
    assert create_calls == []


def test_is_streaming_reports_active_stream():
    client = complete_obs_client()
    client.streaming = True
    session = ObsSession(client=client)
    assert session.is_streaming() is True


def test_refuse_streaming_never_stops_existing_stream():
    client = complete_obs_client()
    client.streaming = True
    session = ObsSession(client=client)
    with pytest.raises(RuntimeError, match="streaming"):
        session.refuse_streaming()
    assert client.streaming is True
    stop_calls = [call for call in client.calls if call[0] == "stop_stream"]
    assert stop_calls == []


def test_start_recording_refuses_existing_recording():
    client = complete_obs_client()
    client.recording = True
    session = ObsSession(client=client)
    with pytest.raises(RuntimeError, match="recording"):
        session.start_recording()
    assert ("start_record",) not in client.calls


def test_start_recording_waits_for_delayed_active_and_refuses_streaming():
    client = complete_obs_client()
    client.streaming = True
    session = ObsSession(client=client)
    with pytest.raises(RuntimeError, match="streaming"):
        session.start_recording()

    client.streaming = False
    client.polls_until_record_active = 3
    session = ObsSession(client=client, poll_interval_s=0.0)
    session.start_recording()
    assert ("start_record",) in client.calls
    assert client.post_start_polls >= 3
    assert client.recording is True
    assert session.owns_recording is True


def test_start_recording_poll_exception_after_start_before_active():
    client = complete_obs_client()
    client.polls_until_record_active = 3
    client.raises_on_post_start_poll = 1
    session = ObsSession(client=client, poll_interval_s=0.0, finalize_timeout_s=1.0)
    with pytest.raises(RuntimeError, match="websocket dropped"):
        session.start_recording()
    assert ("start_record",) in client.calls
    assert client.post_start_polls >= 1
    assert client.recording is False
    assert ("stop_record",) in client.calls
    assert session.owns_recording is False


def test_start_recording_timeout_preserves_ownership_when_finalize_times_out():
    client = complete_obs_client()
    client.record_never_active = True
    client.stop_never_finalizes = True
    session = ObsSession(
        client=client,
        finalize_timeout_s=0.01,
        poll_interval_s=0.0,
    )
    with pytest.raises(RuntimeError, match="did not become active"):
        session.start_recording()
    assert ("start_record",) in client.calls
    assert ("stop_record",) in client.calls
    assert client.post_stop_polls >= 1
    assert session.owns_recording is True


def test_stop_recording_waits_through_delayed_finalization_polls():
    client = complete_obs_client()
    client.recording = True
    client.polls_until_record_inactive = 3
    session = ObsSession(client=client, poll_interval_s=0.0)
    session._owns_recording = True
    path = session.stop_recording()
    assert path == client.output_path
    assert client.post_stop_polls >= 3
    assert client.recording is False
    assert session.owns_recording is False


def test_stop_recording_timeout_preserves_ownership_for_retry():
    client = complete_obs_client()
    client.recording = True
    client.stop_never_finalizes = True
    session = ObsSession(
        client=client,
        poll_interval_s=0.0,
        finalize_timeout_s=0.01,
    )
    session._owns_recording = True
    with pytest.raises(RuntimeError, match="did not finalize"):
        session.stop_recording()
    assert ("stop_record",) in client.calls
    assert client.post_stop_polls >= 1
    assert session.owns_recording is True


def test_stop_recording_retry_after_finalize_timeout_succeeds():
    client = complete_obs_client()
    client.recording = True
    client.stop_never_finalizes = True
    client.polls_until_record_inactive = 2
    session = ObsSession(client=client, poll_interval_s=0.0, finalize_timeout_s=0.01)
    session._owns_recording = True
    with pytest.raises(RuntimeError, match="did not finalize"):
        session.stop_recording()
    assert session.owns_recording is True

    client.stop_never_finalizes = False
    client.stop_pending = False
    client.post_stop_polls = 0
    client.recording = True
    session = ObsSession(client=client, poll_interval_s=0.0, finalize_timeout_s=1.0)
    session._owns_recording = True
    path = session.stop_recording()
    assert path == client.output_path
    assert client.post_stop_polls >= 2
    assert session.owns_recording is False


def test_stop_recording_does_not_stop_preexisting_recording():
    client = complete_obs_client()
    client.recording = True
    session = ObsSession(client=client)
    assert session.stop_recording() is None
    assert ("stop_record",) not in client.calls
    assert client.recording is True


def test_recording_duration_reports_seconds():
    client = complete_obs_client()
    client.record_duration_ms = 91_500
    session = ObsSession(client=client)
    assert session.recording_duration_s() == pytest.approx(91.5)


def test_stop_recording_runs_in_finally_on_body_exception():
    client = complete_obs_client()
    client.polls_until_record_inactive = 2
    session = ObsSession(client=client, poll_interval_s=0.0)

    class Boom(Exception):
        pass

    with pytest.raises(Boom):
        with session.recording_session():
            assert session.owns_recording is True
            raise Boom()

    assert client.recording is False
    assert client.post_stop_polls >= 2
    assert ("stop_record",) in client.calls
    assert session.owns_recording is False


def test_recording_session_normal_exit_finalize_failure_propagates():
    client = complete_obs_client()
    client.stop_never_finalizes = True
    session = ObsSession(client=client, poll_interval_s=0.0, finalize_timeout_s=0.01)
    with pytest.raises(RuntimeError, match="did not finalize"):
        with session.recording_session():
            pass
    assert ("stop_record",) in client.calls
    assert client.post_stop_polls >= 1
    assert session.owns_recording is True


def test_recording_session_body_exception_preserves_original_on_stop_failure():
    client = complete_obs_client()
    client.stop_never_finalizes = True
    session = ObsSession(client=client, poll_interval_s=0.0, finalize_timeout_s=0.01)

    class Boom(Exception):
        pass

    with pytest.raises(Boom):
        with session.recording_session():
            raise Boom()
    assert ("stop_record",) in client.calls
    assert client.post_stop_polls >= 1
    assert session.owns_recording is True


class OBSSDKRequestError(Exception):
    """Fake vendor error not derived from RuntimeError."""


def test_recording_session_normal_exit_sdk_stop_error_propagates():
    client = complete_obs_client()
    client.stop_record_raises = OBSSDKRequestError("StopRecord rejected")
    session = ObsSession(client=client, poll_interval_s=0.0)
    with pytest.raises(OBSSDKRequestError, match="StopRecord rejected"):
        with session.recording_session():
            pass
    assert ("stop_record",) in client.calls
    assert session.owns_recording is True


def test_recording_session_body_exception_preserves_original_on_sdk_stop_error():
    client = complete_obs_client()
    client.stop_record_raises = OBSSDKRequestError("StopRecord rejected")
    session = ObsSession(client=client, poll_interval_s=0.0)

    class Boom(Exception):
        pass

    with pytest.raises(Boom):
        with session.recording_session():
            raise Boom()
    assert ("stop_record",) in client.calls
    assert session.owns_recording is True
