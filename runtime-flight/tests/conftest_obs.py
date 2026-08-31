"""Shared OBS test fakes for runtime-flight Task 4 tests."""

from __future__ import annotations

from dataclasses import dataclass, field

from runtime_flight.obs_setup import REQUIRED_SCENES, SCENE_ITEM_REQUIREMENTS

SUPPORTED_KINDS = (
    "ffmpeg_source",
    "image_source",
    "text_ft2_source",
    "text_gdiplus",
    "color_source",
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
    stream_sequence: list[bool] | None = None
    stream_polls: int = 0
    recording: bool = False
    record_duration_ms: int = 0
    output_path: str = "/tmp/recording.mkv"
    polls_until_record_active: int = 0
    polls_until_record_inactive: int = 0
    record_never_active: bool = False
    start_record_seen: bool = False
    post_start_polls: int = 0
    raises_on_post_start_poll: int | None = None
    stop_pending: bool = False
    post_stop_polls: int = 0
    stop_never_finalizes: bool = False
    stop_record_raises: Exception | None = None
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
        assert unversioned is True
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
        self.calls.append(("get_stream_status",))
        if self.stream_sequence:
            index = min(self.stream_polls, len(self.stream_sequence) - 1)
            active = self.stream_sequence[index]
            self.stream_polls += 1
            return type("StreamStatus", (), {"output_active": active})()
        return type("StreamStatus", (), {"output_active": self.streaming})()

    def get_record_status(self):
        if self.stop_pending:
            self.post_stop_polls += 1
            if self.stop_never_finalizes:
                active = True
            else:
                active = self.post_stop_polls < self.polls_until_record_inactive
            if not active:
                self.recording = False
                self.stop_pending = False
            return type(
                "RecordStatus",
                (),
                {
                    "output_active": active,
                    "output_duration": self.record_duration_ms,
                },
            )()

        if self.start_record_seen and self.raises_on_post_start_poll is not None:
            self.post_start_polls += 1
            if self.post_start_polls >= self.raises_on_post_start_poll:
                raise RuntimeError("websocket dropped")

        if self.recording:
            active = True
        elif self.start_record_seen and self.polls_until_record_active:
            self.post_start_polls += 1
            active = self.post_start_polls >= self.polls_until_record_active
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
        self.start_record_seen = True
        if self.polls_until_record_active == 0 and not self.record_never_active:
            self.recording = True

    def stop_record(self):
        self.calls.append(("stop_record",))
        if self.stop_record_raises is not None:
            raise self.stop_record_raises
        self.stop_pending = True
        self.post_stop_polls = 0
        return type("StopRecord", (), {"output_path": self.output_path})()


def scene_items_for_contract() -> dict[str, list[FakeSceneItem]]:
    items: dict[str, list[FakeSceneItem]] = {}
    item_id = 1
    for scene, requirements in SCENE_ITEM_REQUIREMENTS.items():
        scene_items: list[FakeSceneItem] = []
        for requirement in requirements:
            count = (
                requirement.maximum
                if requirement.maximum is not None
                else requirement.minimum
            )
            for _ in range(count):
                scene_items.append(FakeSceneItem(requirement.source, item_id))
                item_id += 1
        items[scene] = scene_items
    return items


def complete_obs_client() -> FakeObsClient:
    return FakeObsClient(
        scenes=set(REQUIRED_SCENES),
        inputs={
            "HOST_WIDE": "ffmpeg_source",
            "CENTER": "image_source",
            "HEADLINE": "text_ft2_source",
            "NAME_A": "text_ft2_source",
            "NAME_B": "text_ft2_source",
            "HL_A": "color_source",
            "HL_B": "color_source",
            "BED": "ffmpeg_source",
            "WATCHDOG": "browser_source",
        },
        scene_items=scene_items_for_contract(),
    )
