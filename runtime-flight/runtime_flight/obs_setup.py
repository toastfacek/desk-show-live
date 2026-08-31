"""OBS scene/input contract validation and idempotent setup-obs."""

from __future__ import annotations

from typing import Any, Protocol

REQUIRED_SCENES = ("wide", "split", "solo_l", "solo_r", "card_full", "hold")
REQUIRED_INPUTS = (
    "HOST_WIDE",
    "CENTER",
    "HEADLINE",
    "NAME_A",
    "NAME_B",
    "HL_A",
    "HL_B",
    "BED",
)
HOST_LAYOUTS = ("wide", "split", "solo_l", "solo_r")

INPUT_KINDS: dict[str, str] = {
    "HOST_WIDE": "ffmpeg_source",
    "CENTER": "image_source",
    "HEADLINE": "text_gdiplus_v2",
    "NAME_A": "text_gdiplus_v2",
    "NAME_B": "text_gdiplus_v2",
    "HL_A": "color_source",
    "HL_B": "color_source",
    "BED": "ffmpeg_source",
}

SCENE_REQUIRED_SOURCES: dict[str, tuple[str, ...]] = {
    "wide": ("HOST_WIDE", "HEADLINE", "NAME_A", "NAME_B", "HL_A", "HL_B"),
    "split": ("HOST_WIDE", "CENTER", "HEADLINE", "NAME_A", "NAME_B", "HL_A", "HL_B"),
    "solo_l": ("HOST_WIDE", "HEADLINE", "NAME_A", "NAME_B", "HL_A", "HL_B"),
    "solo_r": ("HOST_WIDE", "HEADLINE", "NAME_A", "NAME_B", "HL_A", "HL_B"),
    "card_full": ("CENTER",),
    "hold": ("CENTER", "BED"),
}

SCENE_EXTRA_SCENE_ITEMS: dict[str, tuple[str, ...]] = {
    "split": ("HOST_WIDE",),
}


class ObsSetupClient(Protocol):
    def get_scene_list(self) -> Any: ...

    def get_input_list(self, kind: str | None = None) -> Any: ...

    def create_scene(self, name: str) -> Any: ...

    def create_input(
        self,
        sceneName: str,
        inputName: str,
        inputKind: str,
        inputSettings: dict,
        sceneItemEnabled: bool,
    ) -> Any: ...

    def get_scene_item_list(self, name: str) -> Any: ...

    def create_scene_item(self, sceneName: str, sourceName: str, enabled: bool) -> Any: ...


def _scene_names(client: ObsSetupClient) -> set[str]:
    response = client.get_scene_list()
    scenes = getattr(response, "scenes", None) or []
    names: set[str] = set()
    for scene in scenes:
        if isinstance(scene, dict):
            names.add(scene["sceneName"])
        else:
            names.add(scene.scene_name)
    return names


def _input_names(client: ObsSetupClient) -> set[str]:
    response = client.get_input_list()
    inputs = getattr(response, "inputs", None) or []
    names: set[str] = set()
    for item in inputs:
        if isinstance(item, dict):
            names.add(item["inputName"])
        else:
            names.add(item.input_name)
    return names


def _scene_source_names(client: ObsSetupClient, scene_name: str) -> set[str]:
    response = client.get_scene_item_list(scene_name)
    items = getattr(response, "scene_items", None) or []
    names: set[str] = set()
    for item in items:
        if isinstance(item, dict):
            names.add(item["sourceName"])
        else:
            names.add(item.source_name)
    return names


def validate_contract(client: ObsSetupClient) -> list[str]:
    errors: list[str] = []
    scenes = _scene_names(client)
    inputs = _input_names(client)

    for scene in REQUIRED_SCENES:
        if scene not in scenes:
            errors.append(f"missing scene: {scene}")

    for input_name in REQUIRED_INPUTS:
        if input_name not in inputs:
            errors.append(f"missing input: {input_name}")

    for scene in REQUIRED_SCENES:
        if scene not in scenes:
            continue
        present = _scene_source_names(client, scene)
        required = list(SCENE_REQUIRED_SOURCES[scene])
        required.extend(SCENE_EXTRA_SCENE_ITEMS.get(scene, ()))
        for source_name in required:
            if source_name not in present:
                errors.append(f"missing scene item {source_name} in {scene}")

    return errors


def setup_obs(client: ObsSetupClient) -> dict[str, list[str]]:
    created_scenes: list[str] = []
    created_inputs: list[str] = []
    scenes = _scene_names(client)
    inputs = _input_names(client)

    for scene in REQUIRED_SCENES:
        if scene not in scenes:
            client.create_scene(scene)
            created_scenes.append(scene)
            scenes.add(scene)

    anchor_scene = "wide"
    for input_name in REQUIRED_INPUTS:
        if input_name not in inputs:
            client.create_input(
                anchor_scene,
                input_name,
                INPUT_KINDS[input_name],
                {},
                True,
            )
            created_inputs.append(input_name)
            inputs.add(input_name)

    for scene in REQUIRED_SCENES:
        present = _scene_source_names(client, scene)
        required = list(SCENE_REQUIRED_SOURCES[scene])
        required.extend(SCENE_EXTRA_SCENE_ITEMS.get(scene, ()))
        for source_name in required:
            if source_name not in present:
                client.create_scene_item(scene, source_name, True)
                present.add(source_name)

    return {"created_scenes": created_scenes, "created_inputs": created_inputs}


def ensure_contract(client: ObsSetupClient, *, create: bool) -> dict[str, list[str]] | None:
    if create:
        return setup_obs(client)
    errors = validate_contract(client)
    if errors:
        raise RuntimeError(errors[0])
    return None
