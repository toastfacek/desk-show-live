"""OBS scene/input contract validation and idempotent setup-obs."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
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

ROLE_KIND_CANDIDATES: dict[str, tuple[str, ...]] = {
    "media": ("ffmpeg_source", "vlc_source"),
    "text": ("text_ft2_source", "text_gdiplus_v2", "text_gdiplus_source"),
    "color": ("color_source_v3", "color_source"),
    "image": ("image_source",),
    "browser": ("browser_source",),
}

INPUT_ROLE: dict[str, str] = {
    "HOST_WIDE": "media",
    "BED": "media",
    "HEADLINE": "text",
    "NAME_A": "text",
    "NAME_B": "text",
    "HL_A": "color",
    "HL_B": "color",
    "CENTER": "image",
}


@dataclass(frozen=True)
class SceneItemRequirement:
    source: str
    minimum: int = 1
    maximum: int | None = None
    distinct_ids: bool = False


SCENE_ITEM_REQUIREMENTS: dict[str, tuple[SceneItemRequirement, ...]] = {
    "wide": (
        SceneItemRequirement("HOST_WIDE"),
        SceneItemRequirement("HEADLINE"),
        SceneItemRequirement("NAME_A"),
        SceneItemRequirement("NAME_B"),
        SceneItemRequirement("HL_A"),
        SceneItemRequirement("HL_B"),
    ),
    "split": (
        SceneItemRequirement("HOST_WIDE", minimum=2, maximum=2, distinct_ids=True),
        SceneItemRequirement("CENTER"),
        SceneItemRequirement("HEADLINE"),
        SceneItemRequirement("NAME_A"),
        SceneItemRequirement("NAME_B"),
        SceneItemRequirement("HL_A"),
        SceneItemRequirement("HL_B"),
    ),
    "solo_l": (
        SceneItemRequirement("HOST_WIDE"),
        SceneItemRequirement("HEADLINE"),
        SceneItemRequirement("NAME_A"),
        SceneItemRequirement("NAME_B"),
        SceneItemRequirement("HL_A"),
        SceneItemRequirement("HL_B"),
    ),
    "solo_r": (
        SceneItemRequirement("HOST_WIDE"),
        SceneItemRequirement("HEADLINE"),
        SceneItemRequirement("NAME_A"),
        SceneItemRequirement("NAME_B"),
        SceneItemRequirement("HL_A"),
        SceneItemRequirement("HL_B"),
    ),
    "card_full": (SceneItemRequirement("CENTER"),),
    "hold": (SceneItemRequirement("CENTER"), SceneItemRequirement("BED")),
}


class ObsSetupClient(Protocol):
    def get_scene_list(self) -> Any: ...

    def get_input_list(self, kind: str | None = None) -> Any: ...

    def get_input_kind_list(self, unversioned: bool) -> Any: ...

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


def _input_kinds(client: ObsSetupClient) -> dict[str, str]:
    response = client.get_input_list()
    inputs = getattr(response, "inputs", None) or []
    kinds: dict[str, str] = {}
    for item in inputs:
        if isinstance(item, dict):
            name = item["inputName"]
            kind = item.get("unversionedInputKind") or item.get("inputKind")
        else:
            name = item.input_name
            kind = getattr(item, "unversioned_input_kind", None) or getattr(
                item, "input_kind", None
            )
        if kind:
            kinds[name] = str(kind)
    return kinds


def _supported_input_kinds(client: ObsSetupClient) -> set[str]:
    response = client.get_input_kind_list(True)
    kinds = getattr(response, "input_kinds", None)
    if kinds is None:
        kinds = getattr(response, "inputKinds", None) or []
    return {str(kind) for kind in kinds}


def _scene_items(client: ObsSetupClient, scene_name: str) -> list[tuple[str, int]]:
    response = client.get_scene_item_list(scene_name)
    items = getattr(response, "scene_items", None) or []
    parsed: list[tuple[str, int]] = []
    for item in items:
        if isinstance(item, dict):
            parsed.append((str(item["sourceName"]), int(item["sceneItemId"])))
        else:
            parsed.append((str(item.source_name), int(item.scene_item_id)))
    return parsed


def scene_item_multiset_errors(
    scene_name: str,
    scene_items: list[tuple[str, int]],
    requirements: tuple[SceneItemRequirement, ...],
) -> list[str]:
    errors: list[str] = []
    counts = Counter(source for source, _ in scene_items)
    ids_by_source: dict[str, list[int]] = {}
    for source, item_id in scene_items:
        ids_by_source.setdefault(source, []).append(item_id)

    for requirement in requirements:
        count = counts.get(requirement.source, 0)
        if count < requirement.minimum:
            errors.append(
                f"missing scene item {requirement.source} in {scene_name}: "
                f"need at least {requirement.minimum}, found {count}"
            )
            continue
        maximum = requirement.maximum
        if maximum is not None and count != maximum:
            errors.append(
                f"scene item {requirement.source} in {scene_name}: "
                f"need exactly {maximum}, found {count}"
            )
        if requirement.distinct_ids:
            distinct = len(set(ids_by_source.get(requirement.source, [])))
            if distinct != count:
                errors.append(
                    f"scene item {requirement.source} in {scene_name}: "
                    f"need {count} distinct scene-item IDs, found {distinct}"
                )
    return errors


def _required_roles() -> set[str]:
    return {INPUT_ROLE[input_name] for input_name in REQUIRED_INPUTS}


def resolve_role_kinds(supported_kinds: set[str]) -> dict[str, str]:
    resolved: dict[str, str] = {}
    missing_roles: list[str] = []
    for role in sorted(_required_roles()):
        candidates = ROLE_KIND_CANDIDATES[role]
        chosen = next((kind for kind in candidates if kind in supported_kinds), None)
        if chosen is None:
            missing_roles.append(role)
        else:
            resolved[role] = chosen
    if missing_roles:
        raise RuntimeError(
            "OBS lacks supported input kinds for roles: "
            + ", ".join(sorted(missing_roles))
        )
    return resolved


def _resolved_input_kinds(client: ObsSetupClient) -> dict[str, str]:
    role_kinds = resolve_role_kinds(_supported_input_kinds(client))
    return {
        input_name: role_kinds[INPUT_ROLE[input_name]] for input_name in REQUIRED_INPUTS
    }


def _input_kind_errors(client: ObsSetupClient) -> list[str]:
    errors: list[str] = []
    try:
        resolved = _resolved_input_kinds(client)
    except RuntimeError as exc:
        return [str(exc)]
    existing = _input_kinds(client)
    for input_name, expected_kind in resolved.items():
        actual = existing.get(input_name)
        if actual is None:
            continue
        role = INPUT_ROLE[input_name]
        if actual not in ROLE_KIND_CANDIDATES[role]:
            errors.append(
                f"input {input_name} has incompatible kind {actual} for role {role}"
            )
    return errors


def validate_contract(client: ObsSetupClient) -> list[str]:
    errors: list[str] = []
    scenes = _scene_names(client)
    inputs = _input_kinds(client)

    for scene in REQUIRED_SCENES:
        if scene not in scenes:
            errors.append(f"missing scene: {scene}")

    for input_name in REQUIRED_INPUTS:
        if input_name not in inputs:
            errors.append(f"missing input: {input_name}")

    errors.extend(_input_kind_errors(client))

    for scene in REQUIRED_SCENES:
        if scene not in scenes:
            continue
        errors.extend(
            scene_item_multiset_errors(
                scene,
                _scene_items(client, scene),
                SCENE_ITEM_REQUIREMENTS[scene],
            )
        )

    return errors


def _missing_scene_item_counts(
    scene_name: str, scene_items: list[tuple[str, int]]
) -> dict[str, int]:
    counts = Counter(source for source, _ in scene_items)
    missing: dict[str, int] = {}
    for requirement in SCENE_ITEM_REQUIREMENTS[scene_name]:
        current = counts.get(requirement.source, 0)
        target = requirement.maximum if requirement.maximum is not None else requirement.minimum
        if current < target:
            missing[requirement.source] = target - current
    return missing


def setup_obs(client: ObsSetupClient) -> dict[str, list[str]]:
    created_scenes: list[str] = []
    created_inputs: list[str] = []
    created_scene_items: list[str] = []
    scenes = _scene_names(client)
    inputs = _input_kinds(client)
    input_kinds = _resolved_input_kinds(client)

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
                input_kinds[input_name],
                {},
                True,
            )
            created_inputs.append(input_name)
            inputs[input_name] = input_kinds[input_name]

    for scene in REQUIRED_SCENES:
        items = _scene_items(client, scene)
        for source_name, count in _missing_scene_item_counts(scene, items).items():
            for _ in range(count):
                client.create_scene_item(scene, source_name, True)
                created_scene_items.append(f"{scene}:{source_name}")
                items.append((source_name, -1))

    return {
        "created_scenes": created_scenes,
        "created_inputs": created_inputs,
        "created_scene_items": created_scene_items,
    }


def ensure_contract(client: ObsSetupClient) -> None:
    errors = validate_contract(client)
    if errors:
        raise RuntimeError(errors[0])
