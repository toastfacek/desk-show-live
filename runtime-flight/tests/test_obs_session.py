"""Task 4: OBS contract validation, setup-obs, and recording lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from runtime_flight.obs_setup import (
    REQUIRED_INPUTS,
    REQUIRED_SCENES,
    SCENE_EXTRA_SCENE_ITEMS,
    SCENE_REQUIRED_SOURCES,
    setup_obs,
    validate_contract,
)
from runtime_flight.obs_session import ObsSession


@dataclass
class FakeObsClient:
    scenes: set[str] = field(default_factory=set)
    inputs: set[str] = field(default_factory=set)
    scene_items: dict[str, set[str]] = field(default_factory=dict)
    calls: list[tuple] = field(default_factory=list)
    streaming: bool = False
    recording: bool = False
    record_duration_ms: int = 0
    output_path: str = "/tmp/recording.mkv"

    def get_scene_list(self):
        return type(
            "SceneList",
            (),
            {"scenes": [{"sceneName": name} for name in sorted(self.scenes)]},
        )()

    def get_input_list(self, kind=None):
        return type(
            "InputList",
            (),
            {"inputs": [{"inputName": name} for name in sorted(self.inputs)]},
        )()

    def get_scene_item_list(self, name: str):
        sources = sorted(self.scene_items.get(name, set()))
        return type(
            "SceneItemList",
            (),
            {
                "scene_items": [
                    {"sourceName": source_name, "sceneItemId": index + 1}
                    for index, source_name in enumerate(sources)
                ]
            },
        )()

    def create_scene(self, name: str):
        self.calls.append(("create_scene", name))
        self.scenes.add(name)
        self.scene_items.setdefault(name, set())

    def create_input(
        self,
        sceneName,
        inputName,
        inputKind,
        inputSettings,
        sceneItemEnabled,
    ):
        self.calls.append(
            (
                "create_input",
                sceneName,
                inputName,
                inputKind,
                inputSettings,
                sceneItemEnabled,
            )
        )
        self.inputs.add(inputName)
        self.scene_items.setdefault(sceneName, set()).add(inputName)

    def create_scene_item(self, sceneName: str, sourceName: str, enabled: bool):
        self.calls.append(("create_scene_item", sceneName, sourceName, enabled))
        self.scene_items.setdefault(sceneName, set()).add(sourceName)

    def get_stream_status(self):
        return type("StreamStatus", (), {"output_active": self.streaming})()

    def get_record_status(self):
        return type(
            "RecordStatus",
            (),
            {
                "output_active": self.recording,
                "output_duration": self.record_duration_ms,
            },
        )()

    def start_record(self):
        self.calls.append(("start_record",))
        self.recording = True

    def stop_record(self):
        self.calls.append(("stop_record",))
        self.recording = False
        return type("StopRecord", (), {"output_path": self.output_path})()


def _scene_items_for_contract() -> dict[str, set[str]]:
    items: dict[str, set[str]] = {}
    for scene, sources in SCENE_REQUIRED_SOURCES.items():
        items[scene] = set(sources)
    for scene, extras in SCENE_EXTRA_SCENE_ITEMS.items():
        items.setdefault(scene, set()).update(extras)
    return items


def _complete_client() -> FakeObsClient:
    return FakeObsClient(
        scenes=set(REQUIRED_SCENES),
        inputs=set(REQUIRED_INPUTS),
        scene_items=_scene_items_for_contract(),
    )


def test_validate_contract_accepts_complete_obs():
    errors = validate_contract(_complete_client())
    assert errors == []


@pytest.mark.parametrize("missing_scene", REQUIRED_SCENES)
def test_validate_contract_rejects_missing_scene(missing_scene):
    client = _complete_client()
    client.scenes.remove(missing_scene)
    errors = validate_contract(client)
    assert any(missing_scene in error for error in errors)


@pytest.mark.parametrize("missing_input", REQUIRED_INPUTS)
def test_validate_contract_rejects_missing_input(missing_input):
    client = _complete_client()
    client.inputs.remove(missing_input)
    errors = validate_contract(client)
    assert any(missing_input in error for error in errors)


def test_validate_contract_excludes_watchdog_until_task_12():
    client = _complete_client()
    errors = validate_contract(client)
    assert errors == []
    assert "WATCHDOG" not in REQUIRED_INPUTS


def test_setup_obs_creates_missing_scenes_and_inputs():
    client = FakeObsClient()
    summary = setup_obs(client)
    assert client.scenes == set(REQUIRED_SCENES)
    assert client.inputs == set(REQUIRED_INPUTS)
    assert summary["created_scenes"]
    assert summary["created_inputs"]


def test_setup_obs_is_idempotent():
    client = FakeObsClient()
    first = setup_obs(client)
    call_count_after_first = len(client.calls)
    second = setup_obs(client)
    assert first["created_scenes"]
    assert first["created_inputs"]
    assert second["created_scenes"] == []
    assert second["created_inputs"] == []
    assert len(client.calls) == call_count_after_first


def test_live_mode_validate_only_never_creates():
    client = FakeObsClient()
    session = ObsSession(client=client, live_mode=True)
    with pytest.raises(RuntimeError, match="missing scene"):
        session.ensure_contract()


def test_is_streaming_reports_active_stream():
    client = _complete_client()
    client.streaming = True
    session = ObsSession(client=client)
    assert session.is_streaming() is True


def test_refuse_streaming_never_stops_existing_stream():
    client = _complete_client()
    client.streaming = True
    session = ObsSession(client=client)
    with pytest.raises(RuntimeError, match="streaming"):
        session.refuse_streaming()
    assert client.streaming is True
    stop_calls = [call for call in client.calls if call[0] == "stop_stream"]
    assert stop_calls == []


def test_start_recording_waits_until_active_and_refuses_streaming():
    client = _complete_client()
    client.streaming = True
    session = ObsSession(client=client)
    with pytest.raises(RuntimeError, match="streaming"):
        session.start_recording()

    client.streaming = False
    session.start_recording()
    assert ("start_record",) in client.calls
    assert client.recording is True


def test_stop_recording_returns_output_path_and_waits_for_finalize():
    client = _complete_client()
    session = ObsSession(client=client)
    client.recording = True
    path = session.stop_recording()
    assert path == client.output_path
    assert client.recording is False
    assert ("stop_record",) in client.calls


def test_recording_duration_reports_seconds():
    client = _complete_client()
    client.record_duration_ms = 91_500
    session = ObsSession(client=client)
    assert session.recording_duration_s() == pytest.approx(91.5)


def test_stop_recording_runs_in_finally():
    client = _complete_client()
    session = ObsSession(client=client)
    client.recording = True

    class Boom(Exception):
        pass

    with pytest.raises(Boom):
        with session.recording_session():
            raise Boom()

    assert client.recording is False
    assert ("stop_record",) in client.calls
