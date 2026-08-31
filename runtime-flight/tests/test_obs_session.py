"""Task 4: OBS contract validation, setup-obs, and recording lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from runtime_flight.obs_setup import (
    REQUIRED_INPUTS,
    REQUIRED_SCENES,
    SCENE_ITEM_REQUIREMENTS,
    SceneItemRequirement,
    resolve_role_kinds,
    setup_obs,
    validate_contract,
)
from runtime_flight.obs_session import ObsSession


SUPPORTED_KINDS = (
    "ffmpeg_source",
    "image_source",
    "text_ft2_source",
    "color_source_v3",
    "browser_source",
)


@dataclass
class FakeSceneItem:
    source_name: str
    scene_item_id: int


@dataclass
class FakeObsClient:
    scenes: set[str] = field(default_factory=set)
    inputs: dict[str, str] = field(default_factory=dict)
    scene_items: dict[str, list[FakeSceneItem]] = field(default_factory=dict)
    supported_kinds: tuple[str, ...] = SUPPORTED_KINDS
    calls: list[tuple] = field(default_factory=list)
    streaming: bool = False
    recording: bool = False
    record_duration_ms: int = 0
    output_path: str = "/tmp/recording.mkv"
    polls_until_record_active: int = 0
    polls_until_record_inactive: int = 0
    record_poll_count: int = 0
    record_never_active: bool = False
    record_status_raises: Exception | None = None
    record_status_raises_after: int = 0
    next_scene_item_id: int = 1

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
            {
                "inputs": [
                    {
                        "inputName": name,
                        "unversionedInputKind": input_kind,
                    }
                    for name, input_kind in sorted(self.inputs.items())
                ]
            },
        )()

    def get_input_kind_list(self, unversioned: bool):
        self.calls.append(("get_input_kind_list", unversioned))
        return type(
            "InputKindList",
            (),
            {"input_kinds": list(self.supported_kinds)},
        )()

    def get_scene_item_list(self, name: str):
        items = self.scene_items.get(name, [])
        return type(
            "SceneItemList",
            (),
            {
                "scene_items": [
                    {
                        "sourceName": item.source_name,
                        "sceneItemId": item.scene_item_id,
                    }
                    for item in items
                ]
            },
        )()

    def create_scene(self, name: str):
        self.calls.append(("create_scene", name))
        self.scenes.add(name)
        self.scene_items.setdefault(name, [])

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
        self.inputs[inputName] = inputKind
        self.scene_items.setdefault(sceneName, []).append(
            FakeSceneItem(inputName, self._next_scene_item_id())
        )

    def create_scene_item(self, sceneName: str, sourceName: str, enabled: bool):
        self.calls.append(("create_scene_item", sceneName, sourceName, enabled))
        self.scene_items.setdefault(sceneName, []).append(
            FakeSceneItem(sourceName, self._next_scene_item_id())
        )

    def _next_scene_item_id(self) -> int:
        item_id = self.next_scene_item_id
        self.next_scene_item_id += 1
        return item_id

    def get_stream_status(self):
        return type("StreamStatus", (), {"output_active": self.streaming})()

    def get_record_status(self):
        if (
            self.record_status_raises is not None
            and self.record_poll_count >= self.record_status_raises_after
        ):
            raise self.record_status_raises
        self.record_poll_count += 1
        if self.recording:
            if (
                self.polls_until_record_inactive
                and self.record_poll_count >= self.polls_until_record_inactive
            ):
                self.recording = False
            active = True
        elif self.polls_until_record_active:
            active = self.record_poll_count >= self.polls_until_record_active
            if active:
                self.recording = True
        elif self.record_never_active:
            active = False
        else:
            active = self.recording
        return type(
            "RecordStatus",
            (),
            {
                "output_active": active,
                "output_duration": self.record_duration_ms,
            },
        )()

    def start_record(self):
        self.calls.append(("start_record",))
        if self.polls_until_record_active == 0 and not self.record_never_active:
            self.recording = True

    def stop_record(self):
        self.calls.append(("stop_record",))
        self.recording = False
        return type("StopRecord", (), {"output_path": self.output_path})()


def _scene_items_for_contract() -> dict[str, list[FakeSceneItem]]:
    items: dict[str, list[FakeSceneItem]] = {}
    item_id = 1
    for scene, requirements in SCENE_ITEM_REQUIREMENTS.items():
        scene_items: list[FakeSceneItem] = []
        for requirement in requirements:
            count = requirement.maximum if requirement.maximum is not None else requirement.minimum
            for _ in range(count):
                scene_items.append(FakeSceneItem(requirement.source, item_id))
                item_id += 1
        items[scene] = scene_items
    return items


def _complete_client() -> FakeObsClient:
    return FakeObsClient(
        scenes=set(REQUIRED_SCENES),
        inputs={
            "HOST_WIDE": "ffmpeg_source",
            "CENTER": "image_source",
            "HEADLINE": "text_ft2_source",
            "NAME_A": "text_ft2_source",
            "NAME_B": "text_ft2_source",
            "HL_A": "color_source_v3",
            "HL_B": "color_source_v3",
            "BED": "ffmpeg_source",
        },
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
    del client.inputs[missing_input]
    errors = validate_contract(client)
    assert any(missing_input in error for error in errors)


def test_validate_contract_rejects_missing_scene_item():
    client = _complete_client()
    client.scene_items["wide"] = [
        item for item in client.scene_items["wide"] if item.source_name != "HEADLINE"
    ]
    errors = validate_contract(client)
    assert any("HEADLINE" in error and "wide" in error for error in errors)


def test_validate_contract_rejects_split_with_one_host_wide():
    client = _complete_client()
    client.scene_items["split"] = [
        item for item in client.scene_items["split"] if item.source_name != "HOST_WIDE"
    ]
    client.scene_items["split"].append(FakeSceneItem("HOST_WIDE", 501))
    errors = validate_contract(client)
    assert any("HOST_WIDE" in error and "split" in error for error in errors)


def test_validate_contract_rejects_split_with_duplicate_host_wide_ids():
    client = _complete_client()
    client.scene_items["split"] = [
        item for item in client.scene_items["split"] if item.source_name != "HOST_WIDE"
    ]
    client.scene_items["split"].extend(
        [FakeSceneItem("HOST_WIDE", 88), FakeSceneItem("HOST_WIDE", 88)]
    )
    errors = validate_contract(client)
    assert any("distinct" in error.lower() for error in errors)


def test_validate_contract_excludes_watchdog_until_task_12():
    client = _complete_client()
    errors = validate_contract(client)
    assert errors == []
    assert "WATCHDOG" not in REQUIRED_INPUTS


def test_resolve_role_kinds_prefers_cross_platform_candidates():
    kinds = resolve_role_kinds(
        {"ffmpeg_source", "text_ft2_source", "color_source_v3", "image_source"}
    )
    assert kinds["media"] == "ffmpeg_source"
    assert kinds["text"] == "text_ft2_source"
    assert kinds["color"] == "color_source_v3"
    assert kinds["image"] == "image_source"


def test_resolve_role_kinds_fails_once_when_roles_unsupported():
    with pytest.raises(RuntimeError, match="roles:") as excinfo:
        resolve_role_kinds({"browser_source"})
    message = str(excinfo.value)
    assert "media" in message
    assert "text" in message
    assert "color" in message


def test_validate_contract_rejects_incompatible_existing_input_kind():
    client = _complete_client()
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
    client = _complete_client()
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


def test_start_recording_refuses_existing_recording():
    client = _complete_client()
    client.recording = True
    session = ObsSession(client=client)
    with pytest.raises(RuntimeError, match="recording"):
        session.start_recording()
    assert ("start_record",) not in client.calls


def test_start_recording_waits_for_delayed_active_and_refuses_streaming():
    client = _complete_client()
    client.streaming = True
    session = ObsSession(client=client)
    with pytest.raises(RuntimeError, match="streaming"):
        session.start_recording()

    client.streaming = False
    client.polls_until_record_active = 3
    session = ObsSession(client=client, poll_interval_s=0.0)
    session.start_recording()
    assert ("start_record",) in client.calls
    assert client.recording is True
    assert session.owns_recording is True


def test_start_recording_timeout_stops_only_owned_recording():
    client = _complete_client()
    client.record_never_active = True
    session = ObsSession(
        client=client,
        finalize_timeout_s=0.01,
        poll_interval_s=0.0,
    )
    with pytest.raises(RuntimeError, match="did not become active"):
        session.start_recording()
    assert ("stop_record",) in client.calls
    assert session.owns_recording is False


def test_start_recording_poll_exception_stops_only_owned_recording():
    client = _complete_client()
    client.record_status_raises = RuntimeError("websocket dropped")
    client.record_status_raises_after = 2
    session = ObsSession(client=client, poll_interval_s=0.0)
    with pytest.raises(RuntimeError, match="websocket dropped"):
        session.start_recording()
    assert ("start_record",) in client.calls
    assert ("stop_record",) in client.calls
    assert session.owns_recording is False


def test_stop_recording_returns_output_path_and_waits_for_finalize():
    client = _complete_client()
    session = ObsSession(client=client, poll_interval_s=0.0)
    client.recording = True
    session._owns_recording = True
    client.polls_until_record_inactive = 2
    path = session.stop_recording()
    assert path == client.output_path
    assert client.recording is False
    assert ("stop_record",) in client.calls
    assert session.owns_recording is False


def test_stop_recording_does_not_stop_preexisting_recording():
    client = _complete_client()
    client.recording = True
    session = ObsSession(client=client)
    assert session.stop_recording() is None
    assert ("stop_record",) not in client.calls
    assert client.recording is True


def test_recording_duration_reports_seconds():
    client = _complete_client()
    client.record_duration_ms = 91_500
    session = ObsSession(client=client)
    assert session.recording_duration_s() == pytest.approx(91.5)


def test_stop_recording_runs_in_finally():
    client = _complete_client()
    session = ObsSession(client=client, poll_interval_s=0.0)

    class Boom(Exception):
        pass

    with pytest.raises(Boom):
        with session.recording_session():
            assert session.owns_recording is True
            raise Boom()

    assert client.recording is False
    assert ("stop_record",) in client.calls
