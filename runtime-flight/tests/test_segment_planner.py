"""Task 6: Segment Planner and shared text client. Fake HTTP only."""

from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from runtime_flight.baseline import BaselineContext, CharacterPackTruth, ScenePackTruth
from runtime_flight.models import (
    MAX_FRAMING_CHARS,
    Fact,
    SegmentPackage,
    Tweet,
    TweetCard,
)
from runtime_flight.segment_planner import SegmentPlanner, SegmentPlannerError
from runtime_flight.source import (
    EXPECTED_AUTHOR,
    EXPECTED_LINKED_URL,
    EXPECTED_TWEET_ID,
    EXPECTED_TWEET_URL,
)
from runtime_flight.text_client import TextAttemptLimiter, TextClient, TextClientError

FORBIDDEN_ROOT_MODULES = {
    "writer",
    "post",
    "spend",
    "generator",
    "playhead",
    "run_live",
    "studio",
}

TWEET_TEXT = "Hello café\nworld"
EXCERPT_TEXT = "Reviewed excerpt body.\n"
SECRET_API_KEY = "sk-test-text-api-key-abcdef0123456789"
SECRET_BASE_URL = "https://text.example.invalid/v1"
SECRET_MODEL = "test-model"
FAL_URL = "https://queue.fal.run/minimax/h3-max/image-to-video"
HERO_PATH = "/secret/local/hero.png"


def _source_packet():
    from runtime_flight.models import LinkedSource, SourcePacket

    excerpt_sha = "e" * 64
    return SourcePacket(
        tweet=Tweet(
            id=EXPECTED_TWEET_ID,
            author=EXPECTED_AUTHOR,
            text=TWEET_TEXT,
            url=EXPECTED_TWEET_URL,
        ),
        linked_source=LinkedSource(
            title="The Rise and Fall of Agent Civilizations",
            subtitle="The whole OpenAI/Hugging Face story in plain English",
            url=EXPECTED_LINKED_URL,
            excerpt=EXCERPT_TEXT,
            excerpt_sha256=excerpt_sha,
        ),
        packet_sha256="p" * 64,
        reviewed_at="2026-08-31T00:00:00+00:00",
    )


def _baseline() -> BaselineContext:
    bot1 = CharacterPackTruth(
        slot="BOT1",
        pack_id="char-1",
        version=1,
        display_name="BOT1",
        manifest={"voice_direction": "low"},
    )
    bot2 = CharacterPackTruth(
        slot="BOT2",
        pack_id="char-2",
        version=1,
        display_name="BOT2",
        manifest={"voice_direction": "bright"},
    )
    return BaselineContext(
        baseline_id="baseline-secret-id",
        hero_path=Path(HERO_PATH),
        hero_sha256="h" * 64,
        host_map={"BOT1": "host_a", "BOT2": "host_b"},
        display_names={"BOT1": "BOT1", "BOT2": "BOT2"},
        reanchor_every=60,
        frame={"w": 1920, "h": 1080, "fps": 30},
        characters=(bot1, bot2),
        scene=ScenePackTruth(
            pack_id="scene-1",
            version=1,
            manifest={"set": "Warm studio"},
        ),
    )


def _valid_plan_payload(**overrides) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "item_id": EXPECTED_TWEET_ID,
        "question": "What happened to the secret AI civilizations?",
        "framing": "A reviewed account of three wiped-out agent societies.",
        "angles": ["scope", "takeover"],
        "facts": [
            {
                "id": "f1",
                "text": "Three secret AI civilizations started and were wiped out.",
                "source_url": EXPECTED_TWEET_URL,
            },
            {
                "id": "f2",
                "text": "The article retells the OpenAI and Hugging Face story.",
                "source_url": EXPECTED_LINKED_URL,
            },
        ],
        "chyron": "Secret AI civilizations",
        "chyron_fact_ids": ["f1"],
        "center": {
            "author": "injected-author",
            "text": "injected card text",
            "url": "https://evil.example/card",
        },
    }
    payload.update(overrides)
    return payload


class FakeResponse:
    def __init__(self, status_code: int, body: Any) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> Any:
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


def _json_body(plan: dict[str, Any], *, usage: Any = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "choices": [{"message": {"content": json.dumps(plan, separators=(",", ":"))}}],
    }
    if usage is not None:
        body["usage"] = usage
    return body


def _client(http_post, *, max_requests: int = 4) -> TextClient:
    return TextClient(
        base_url=SECRET_BASE_URL,
        api_key=SECRET_API_KEY,
        model=SECRET_MODEL,
        limiter=TextAttemptLimiter(max_requests),
        http_post=http_post,
    )


def _run(coro):
    return asyncio.run(coro)


def test_planner_sends_one_tweet_and_one_linked_source_as_untrusted_data():
    captured: dict[str, Any] = {}

    async def http_post(url, *, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse(200, _json_body(_valid_plan_payload()))

    async def run():
        planner = SegmentPlanner(_client(http_post))
        return await planner.plan(_source_packet(), _baseline())

    package = _run(run())
    request = captured["json"]
    assert request["model"] == SECRET_MODEL
    assert request["temperature"] == 0.4
    assert captured["timeout"] == 8.0
    assert captured["url"] == f"{SECRET_BASE_URL.rstrip('/')}/chat/completions"
    assert captured["headers"]["Authorization"] == f"Bearer {SECRET_API_KEY}"
    messages = request["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    user = json.loads(messages[1]["content"])
    assert set(user) == {"untrusted_data", "hosts", "time_budget_s"}
    untrusted = user["untrusted_data"]
    assert set(untrusted) == {"tweet", "linked_source"}
    assert untrusted["tweet"] == {
        "id": EXPECTED_TWEET_ID,
        "author": EXPECTED_AUTHOR,
        "text": TWEET_TEXT,
        "url": EXPECTED_TWEET_URL,
    }
    assert untrusted["linked_source"] == {
        "title": "The Rise and Fall of Agent Civilizations",
        "subtitle": "The whole OpenAI/Hugging Face story in plain English",
        "url": EXPECTED_LINKED_URL,
        "excerpt": EXCERPT_TEXT,
    }
    serialized = json.dumps(user)
    for leaked in (HERO_PATH, FAL_URL, SECRET_API_KEY, "OBS", "spend", "fal"):
        assert leaked not in serialized
    for leaked in (HERO_PATH, FAL_URL, SECRET_API_KEY):
        assert leaked not in messages[0]["content"]
    assert isinstance(package, SegmentPackage)
    assert package.item_id == EXPECTED_TWEET_ID
    assert package.facts[0].source_url in {EXPECTED_TWEET_URL, EXPECTED_LINKED_URL}
    assert package.topic_map is not None
    assert len(package.topic_map.beats) == 1
    assert user["hosts"]["BOT1"]["persona"]
    assert user["hosts"]["BOT2"]["writer_rules"]
    assert "voice_direction" not in json.dumps(user["hosts"])
    assert "host_a" not in json.dumps(user["hosts"])
    assert "host_b" not in json.dumps(user["hosts"])
    assert user["time_budget_s"] is None


def test_every_fact_must_cite_tweet_or_linked_url():
    payload = _valid_plan_payload()
    payload["facts"][1]["source_url"] = "https://en.wikipedia.org/wiki/OpenAI"

    async def http_post(url, *, headers, json, timeout):
        return FakeResponse(200, _json_body(payload))

    async def run():
        planner = SegmentPlanner(_client(http_post))
        return await planner.plan(_source_packet(), _baseline())

    with pytest.raises(SegmentPlannerError, match="source_url|citation"):
        _run(run())


def test_invented_item_id_is_rejected():
    payload = _valid_plan_payload(item_id="9999999999999999999")

    async def http_post(url, *, headers, json, timeout):
        return FakeResponse(200, _json_body(payload))

    async def run():
        planner = SegmentPlanner(_client(http_post))
        return await planner.plan(_source_packet(), _baseline())

    with pytest.raises(SegmentPlannerError, match="item_id"):
        _run(run())


def test_invented_chyron_fact_id_is_rejected():
    payload = _valid_plan_payload(chyron_fact_ids=["f1", "invented"])

    async def http_post(url, *, headers, json, timeout):
        return FakeResponse(200, _json_body(payload))

    async def run():
        planner = SegmentPlanner(_client(http_post))
        return await planner.plan(_source_packet(), _baseline())

    with pytest.raises(SegmentPlannerError, match="chyron_fact"):
        _run(run())


def test_tweet_card_is_built_from_source_packet_not_model():
    async def http_post(url, *, headers, json, timeout):
        return FakeResponse(200, _json_body(_valid_plan_payload()))

    async def run():
        planner = SegmentPlanner(_client(http_post))
        return await planner.plan(_source_packet(), _baseline())

    package = _run(run())
    assert package.center == TweetCard(
        author=EXPECTED_AUTHOR,
        text=TWEET_TEXT,
        url=EXPECTED_TWEET_URL,
    )
    assert package.center.text != "injected card text"


def test_timeout_returns_no_invented_package():
    async def http_post(url, *, headers, json, timeout):
        raise TimeoutError("request timed out")

    async def run():
        planner = SegmentPlanner(_client(http_post))
        return await planner.plan(_source_packet(), _baseline())

    with pytest.raises((TextClientError, TimeoutError)):
        _run(run())


def test_cancellation_returns_no_invented_package():
    started = asyncio.Event()

    async def http_post(url, *, headers, json, timeout):
        started.set()
        await asyncio.sleep(60)
        raise AssertionError("should have been cancelled")

    async def run():
        planner = SegmentPlanner(_client(http_post))
        task = asyncio.create_task(planner.plan(_source_packet(), _baseline()))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert task.cancelled() or task.exception() is not None

    _run(run())


def test_fenced_markdown_json_is_accepted():
    payload = _valid_plan_payload()
    fenced = "```json\n" + json.dumps(payload) + "\n```"

    async def http_post(url, *, headers, json, timeout):
        return FakeResponse(
            200,
            {"choices": [{"message": {"content": fenced}}]},
        )

    async def run():
        client = _client(http_post)
        return await client.complete_json(system="sys", user={"k": "v"})

    assert _run(run()) == payload


def test_json_object_extracted_from_leading_prose():
    payload = {"ok": True, "speaker": "BOT1"}

    async def http_post(url, *, headers, json, timeout):
        return FakeResponse(
            200,
            {
                "choices": [
                    {
                        "message": {
                            "content": 'Sure.\n{"ok": true, "speaker": "BOT1"}'
                        }
                    }
                ]
            },
        )

    async def run():
        return await _client(http_post).complete_json(system="sys", user={"k": "v"})

    assert _run(run()) == payload


def test_unfenced_non_json_content_still_fails():
    async def http_post(url, *, headers, json, timeout):
        return FakeResponse(
            200,
            {"choices": [{"message": {"content": "not json"}}]},
        )

    async def run():
        client = _client(http_post)
        return await client.complete_json(system="sys", user={"k": "v"})

    with pytest.raises(TextClientError, match="JSON"):
        _run(run())


def test_limiter_counts_before_every_http_request():
    seen: list[int] = []
    limiter = TextAttemptLimiter(2)

    async def http_post(url, *, headers, json, timeout):
        seen.append(limiter.attempts)
        return FakeResponse(
            200,
            {"choices": [{"message": {"content": '{"ok":true}'}}]},
        )

    async def run():
        client = TextClient(
            base_url=SECRET_BASE_URL,
            api_key=SECRET_API_KEY,
            model=SECRET_MODEL,
            limiter=limiter,
            http_post=http_post,
        )
        first = await client.complete_json(system="sys", user={"n": 1})
        second = await client.complete_json(system="sys", user={"n": 2})
        with pytest.raises(TextClientError, match="budget|limit"):
            await client.complete_json(system="sys", user={"n": 3})
        return first, second

    first, second = _run(run())
    assert first == {"ok": True}
    assert second == {"ok": True}
    assert seen == [1, 2]
    assert limiter.attempts == 2


def test_non_2xx_response_fails():
    async def http_post(url, *, headers, json, timeout):
        return FakeResponse(500, {"error": "nope"})

    async def run():
        client = _client(http_post)
        return await client.complete_json(system="sys", user={"k": "v"})

    with pytest.raises(TextClientError, match="2xx|HTTP|status"):
        _run(run())


def test_invalid_usage_object_is_rejected():
    async def http_post(url, *, headers, json, timeout):
        return FakeResponse(
            200,
            {
                "choices": [{"message": {"content": '{"ok":true}'}}],
                "usage": "tokens=9",
            },
        )

    async def run():
        client = _client(http_post)
        return await client.complete_json(system="sys", user={"k": "v"})

    with pytest.raises(TextClientError, match="usage"):
        _run(run())


def test_text_client_does_not_log_authorization(capsys: pytest.CaptureFixture[str]):
    client = _client(
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no http"))
    )
    rendered = repr(client) + str(client)
    assert SECRET_API_KEY not in rendered
    assert "Authorization" not in rendered
    captured = capsys.readouterr()
    assert SECRET_API_KEY not in captured.out
    assert SECRET_API_KEY not in captured.err


def test_planner_bounds_question_framing_chyron_angles_and_facts():
    too_long = _valid_plan_payload(question="q" * 281)

    async def http_post(url, *, headers, json, timeout):
        return FakeResponse(200, _json_body(too_long))

    async def run():
        planner = SegmentPlanner(_client(http_post))
        return await planner.plan(_source_packet(), _baseline())

    with pytest.raises((SegmentPlannerError, ValueError), match="280|question"):
        _run(run())


def _package_with_framing(framing: str) -> SegmentPackage:
    return SegmentPackage(
        item_id=EXPECTED_TWEET_ID,
        question="What happened?",
        framing=framing,
        angles=("scope",),
        facts=(
            Fact(id="f1", text="A cited claim.", source_url=EXPECTED_TWEET_URL),
        ),
        chyron="Headline",
        chyron_fact_ids=("f1",),
        center=TweetCard(
            author=EXPECTED_AUTHOR,
            text=TWEET_TEXT,
            url=EXPECTED_TWEET_URL,
        ),
    )


def test_framing_accepts_1000_and_the_680_smoke_blurb():
    assert MAX_FRAMING_CHARS == 1000
    assert _package_with_framing("f" * 1000).framing == "f" * 1000
    assert len(_package_with_framing("x" * 680).framing) == 680


def test_framing_rejects_1001_characters():
    with pytest.raises(ValueError, match="framing exceeds 1000 characters"):
        _package_with_framing("f" * 1001)


def test_planner_accepts_1000_char_framing_and_clips_1001():
    accepted = _valid_plan_payload(framing="f" * 1000)
    overlong = _valid_plan_payload(framing=("Short clause. " + "f" * 1000))

    async def accept_post(url, *, headers, json, timeout):
        return FakeResponse(200, _json_body(accepted))

    async def clip_post(url, *, headers, json, timeout):
        return FakeResponse(200, _json_body(overlong))

    async def accept():
        return await SegmentPlanner(_client(accept_post)).plan(
            _source_packet(), _baseline()
        )

    async def clip():
        return await SegmentPlanner(_client(clip_post)).plan(
            _source_packet(), _baseline()
        )

    package = _run(accept())
    assert len(package.framing) == 1000
    clipped = _run(clip())
    assert clipped.framing == "Short clause."
    assert len(clipped.framing) <= MAX_FRAMING_CHARS


def _valid_topic_map() -> dict[str, Any]:
    return {
        "throughline": "Secret agent societies were wiped out.",
        "fight": "A missed civilization versus a counted wipeout.",
        "done_when": "Both hosts have landed and have nothing grounded left.",
        "beats": [
            {
                "id": "b1",
                "question": "Did monitoring miss a whole society?",
                "tension": "Thesis versus the count of wiped-out runs.",
                "bot1_job": "Land that monitoring missed a civilization.",
                "bot2_job": "Land how many runs died, and how fast.",
                "fact_ids": ["f1"],
                "done_when": "Both jobs landed and neither host has more to add.",
            }
        ],
    }


def test_planner_clips_overlong_beat_jobs():
    topic_map = _valid_topic_map()
    topic_map["beats"][0]["bot1_job"] = (
        "Unpack the capability the tweet shows and then sit with what it does "
        "to people when a cheap radio can hear a unique tire ID and an agent "
        "can turn that capture into a picture of who moved through the street "
        "last night without anyone agreeing to be seen, and whether that is "
        "already how agents start to see a neighborhood."
    )
    assert len(topic_map["beats"][0]["bot1_job"]) > 280
    payload = _valid_plan_payload(topic_map=topic_map)

    async def http_post(url, *, headers, json, timeout):
        return FakeResponse(200, _json_body(payload))

    package = _run(SegmentPlanner(_client(http_post)).plan(_source_packet(), _baseline()))
    assert package.topic_map is not None
    assert len(package.topic_map.beats[0].bot1_job) <= 280
    assert package.topic_map.beats[0].bot1_job.startswith("Unpack the capability")


def test_planner_keeps_a_real_topic_map_and_does_not_invent_a_card():
    payload = _valid_plan_payload(topic_map=_valid_topic_map())

    async def http_post(url, *, headers, json, timeout):
        return FakeResponse(200, _json_body(payload))

    package = _run(SegmentPlanner(_client(http_post)).plan(_source_packet(), _baseline()))
    assert package.topic_map is not None
    assert package.topic_map.throughline.startswith("Secret agent")
    assert package.topic_map.beats[0].bot1_job.startswith("Land that monitoring")
    assert package.topic_map.beats[0].bot2_job.startswith("Land how many")
    assert package.center.author == EXPECTED_AUTHOR


def test_planner_accepts_debate_alias_for_fight():
    topic_map = _valid_topic_map()
    topic_map["debate"] = topic_map.pop("fight")
    payload = _valid_plan_payload(topic_map=topic_map)

    async def http_post(url, *, headers, json, timeout):
        return FakeResponse(200, _json_body(payload))

    package = _run(SegmentPlanner(_client(http_post)).plan(_source_packet(), _baseline()))
    assert package.topic_map is not None
    assert package.topic_map.fight.startswith("A missed civilization")


def test_planner_rejects_beat_fact_id_that_is_not_a_returned_fact():
    topic_map = _valid_topic_map()
    topic_map["beats"][0]["fact_ids"] = ["invented"]
    payload = _valid_plan_payload(topic_map=topic_map)

    async def http_post(url, *, headers, json, timeout):
        return FakeResponse(200, _json_body(payload))

    with pytest.raises(SegmentPlannerError, match="beat fact_id"):
        _run(SegmentPlanner(_client(http_post)).plan(_source_packet(), _baseline()))


def test_planner_derives_angles_from_topic_map_when_angles_omitted():
    payload = _valid_plan_payload(topic_map=_valid_topic_map())
    del payload["angles"]

    async def http_post(url, *, headers, json, timeout):
        return FakeResponse(200, _json_body(payload))

    package = _run(SegmentPlanner(_client(http_post)).plan(_source_packet(), _baseline()))
    assert package.angles
    assert package.topic_map is not None
    assert package.topic_map.beats[0].tension in package.angles


def test_planner_system_maps_a_discussion_not_a_recap():
    captured: dict[str, Any] = {}

    async def http_post(url, *, headers, json, timeout):
        captured["system"] = json["messages"][0]["content"]
        return FakeResponse(200, _json_body(_valid_plan_payload()))

    _run(SegmentPlanner(_client(http_post)).plan(_source_packet(), _baseline()))
    system = captured["system"].lower()
    assert "topic_map" in system
    assert "recap" in system
    assert "bot1" in system
    assert "bot2" in system
    assert "spoken line" in system
    assert "human question" in system
    assert "tweet is the door" in system
    assert "not a beat" in system
    assert "whether the tweet" in system
    assert "throughline must not restate" in system
    assert "debate (not a fight)" in system
    assert "optimistic show" in system
    assert "ask x" in system


def test_facts_are_typed_and_bounded():
    package = SegmentPackage(
        item_id=EXPECTED_TWEET_ID,
        question="What happened?",
        framing="A short frame.",
        angles=("scope",),
        facts=(
            Fact(id="f1", text="A cited claim.", source_url=EXPECTED_TWEET_URL),
        ),
        chyron="Headline",
        chyron_fact_ids=("f1",),
        center=TweetCard(
            author=EXPECTED_AUTHOR,
            text=TWEET_TEXT,
            url=EXPECTED_TWEET_URL,
        ),
    )
    assert 1 <= len(package.angles) <= 8
    assert 1 <= len(package.facts) <= 8
    with pytest.raises(ValueError):
        Fact(id="f1", text="x" * 501, source_url=EXPECTED_TWEET_URL)


def test_no_provider_fallback_uses_configured_url_only():
    urls: list[str] = []

    async def http_post(url, *, headers, json, timeout):
        urls.append(url)
        return FakeResponse(503, {"error": "down"})

    async def run():
        client = _client(http_post)
        await client.complete_json(system="sys", user={"k": "v"})

    with pytest.raises(TextClientError):
        _run(run())
    assert urls == [f"{SECRET_BASE_URL.rstrip('/')}/chat/completions"]


def test_planner_modules_do_not_import_root_scaffold() -> None:
    root = Path(__file__).resolve().parents[1] / "runtime_flight"
    for name in ("text_client.py", "segment_planner.py", "topic_map.py"):
        path = root / name
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert imported.isdisjoint(FORBIDDEN_ROOT_MODULES)
        assert "fal_client" not in imported
        source = path.read_text(encoding="utf-8")
        assert "from writer" not in source
        assert "import writer" not in source
