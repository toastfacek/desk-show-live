"""Tweet URL → image + producer card + writer preview. No live tweet HTTP."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from runtime_flight.__main__ import main
from runtime_flight.ingest import ingest_tweet
from runtime_flight.overlay import OverlayServer
from runtime_flight.source import load_source_packet
from runtime_flight.stage import expected_text_requests, run_stage
from runtime_flight.tweet_fetch import TweetFetchError, fetch_tweet
from runtime_flight.tweet_image import CARD_H, CARD_W, render_tweet_card
from runtime_flight.tweet_embed import TweetEmbedError, official_embed_url
from runtime_flight.tweet_url import TweetUrlError, parse_tweet_url
from test_preflight import _complete_env, _make_flight_setup, _write_flight_config

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "tweet_fixture.json"
OVERLAY_JS = (
    Path(__file__).resolve().parents[2] / "scripts" / "design-preview" / "overlay-live.js"
)
OVERLAY_HTML = (
    Path(__file__).resolve().parents[2] / "scripts" / "design-preview" / "overlay-live.html"
)


def _fixture() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _http_get_factory(fixture: dict[str, Any]):
    def http_get(url: str, **_kwargs):
        if "api.fxtwitter.com" in url:
            body = json.dumps(
                {
                    "tweet": {
                        "id": fixture["id"],
                        "text": fixture["text"] + " https://example.com/workflow-note",
                        "author": {
                            "screen_name": fixture["author"],
                            "name": fixture["author_name"],
                        },
                        "media": {"photos": []},
                    }
                }
            ).encode("utf-8")
            return 200, body, "application/json"
        raise TweetFetchError(f"unexpected url {url}")

    return http_get


async def _stage_text_post(url: str, *, headers: dict, json: dict, timeout: float):
    del url, headers, timeout
    codec = __import__("json")
    payload = codec.loads(json["messages"][1]["content"])
    if "untrusted_data" in payload:
        tweet = payload["untrusted_data"]["tweet"]
        content = {
            "item_id": tweet["id"],
            "question": "What does this workflow unlock?",
            "framing": "A public note about shipping a workflow without a human in the loop.",
            "angles": ["unlock", "catch"],
            "facts": [
                {
                    "id": "f1",
                    "text": tweet["text"][:200],
                    "source_url": tweet["url"],
                }
            ],
            "chyron": "Ship the workflow, then name the catch",
            "chyron_fact_ids": ["f1"],
        }
    else:
        package = payload["package"]
        speaker = payload["next_speaker"]
        content = {
            "speaker": speaker,
            "text": f"{speaker} names the workflow on the card.",
            "thought_open": False,
            "angle_used": package["angles"][0],
        }

    class Response:
        status_code = 200

        def json(self) -> dict[str, Any]:
            return {
                "choices": [{"message": {"content": codec.dumps(content)}}],
                "usage": {},
            }

    return Response()


def test_official_embed_url_is_digits_only() -> None:
    assert official_embed_url("2094640985116737882") == (
        "https://platform.twitter.com/embed/Tweet.html"
        "?dnt=true&hide_thread=true&theme=dark&id=2094640985116737882"
    )
    with pytest.raises(TweetEmbedError):
        official_embed_url("https://evil.example")


def test_parse_tweet_url_accepts_x_and_twitter() -> None:
    parsed = parse_tweet_url(
        "https://x.com/example_user/status/1234567890123456789?s=20"
    )
    assert parsed.id == "1234567890123456789"
    assert parsed.author == "example_user"
    assert parsed.url == "https://x.com/example_user/status/1234567890123456789"
    assert parse_tweet_url(
        "https://twitter.com/example_user/status/1234567890123456789"
    ).id == parsed.id
    with pytest.raises(TweetUrlError):
        parse_tweet_url("https://example.com/not-a-tweet")


def test_fetch_tweet_uses_injected_http() -> None:
    fixture = _fixture()
    fetched = fetch_tweet(fixture["url"], http_get=_http_get_factory(fixture))
    assert fetched.id == fixture["id"]
    assert fetched.author == fixture["author"]
    assert fixture["text"] in fetched.text
    assert fetched.linked_urls == ("https://example.com/workflow-note",)


def test_render_tweet_card_is_center_well_png() -> None:
    png = render_tweet_card(
        author="example_user",
        text="A public note about a new workflow.",
    )
    image = Image.open(BytesIO(png))
    assert image.size == (CARD_W, CARD_H)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_tweet_card_keeps_cjk_glyphs() -> None:
    png = render_tweet_card(
        author="HoodyLiu",
        text="从弹幕遥控 AI，变成投票导演 AI",
    )
    image = Image.open(BytesIO(png)).convert("L")
    assert image.size == (CARD_W, CARD_H)
    # CJK must paint more than the empty panel. Tofu-only fallback is a few dots.
    pixels = image.get_flattened_data() if hasattr(image, "get_flattened_data") else image.getdata()
    ink = sum(1 for pixel in pixels if pixel < 200)
    assert ink > 4000


def test_ingest_writes_reviewed_packet_lock_and_image(tmp_path: Path) -> None:
    fixture = _fixture()
    result = ingest_tweet(
        fixture["url"],
        tmp_path / "staged",
        fixture=fixture,
    )
    source = load_source_packet(result["packet_path"], result["lock_path"])
    assert source.tweet.author == "example_user"
    assert result["image_path"].is_file()
    assert result["image_path"].stat().st_size > 100
    card = json.loads((tmp_path / "staged" / "card.json").read_text(encoding="utf-8"))
    assert card["author"] == "example_user"
    assert card["image_url"] == "/tweet.png"
    assert card["tweet_id"] == "1234567890123456789"
    assert card["text"].startswith("A public note")


def test_overlay_serves_dynamic_card_and_tweet_image(tmp_path: Path) -> None:
    png = render_tweet_card(author="example_user", text="Card body")
    with OverlayServer(state_dir=tmp_path, heartbeat_interval_s=0.05) as server:
        server.set_card(
            author="example_user",
            text="Card body",
            chyron="Desk line from the planner",
            ticker=["unlock", "catch"],
            tweet_id="1234567890123456789",
            image_bytes=png,
        )
        import urllib.request

        with urllib.request.urlopen(server.url + "card.json", timeout=2) as response:
            card = json.loads(response.read().decode("utf-8"))
        assert card["author"] == "example_user"
        assert card["chyron"] == "Desk line from the planner"
        assert card["ticker"] == ["unlock", "catch"]
        assert card["tweet_id"] == "1234567890123456789"
        with urllib.request.urlopen(server.url + "tweet.png", timeout=2) as response:
            image = response.read()
        assert image[:8] == b"\x89PNG\r\n\x1a\n"
        with urllib.request.urlopen(server.live_url, timeout=2) as response:
            html = response.read().decode("utf-8")
        assert "overlay-live.js" in html
        assert 'id="card-body"' in html
        assert 'id="card-image"' in html
        assert 'id="tweet-embed"' in html
        with urllib.request.urlopen(server.url + "tweet-embed.html?id=1234567890123456789", timeout=2) as response:
            embed = response.read().decode("utf-8")
        assert "platform.twitter.com/widgets.js" in embed
        assert "twitter.com/i/status/" in embed
        assert "overflow:hidden" in embed
        assert "fitTweet" not in embed
        assert "innerHTML" not in embed


def test_overlay_live_js_uses_text_content_and_rejects_remote_images() -> None:
    source = OVERLAY_JS.read_text(encoding="utf-8")
    assert "textContent" in source
    assert "innerHTML" not in source
    html = OVERLAY_HTML.read_text(encoding="utf-8")
    assert "innerHTML" not in html
    completed = __import__("subprocess").run(
        [
            "node",
            "-e",
            f"""
const assert = require("assert");
const {{ applyProducerCard, applyOverlayLayout, normalizeLayout, safeImageUrl, cardOriginFromSearch, officialEmbedPath, formatEasternClock, shouldUseShot, shotFallbackPath }} = require({json.dumps(str(OVERLAY_JS))});
assert.strictEqual(shouldUseShot({{ has_shot: true }}, "solo_l", ""), true);
assert.strictEqual(shouldUseShot({{ has_shot: true }}, "split", ""), false);
assert.strictEqual(shouldUseShot({{ has_shot: true }}, "split", "shot"), true);
assert.strictEqual(shouldUseShot({{ has_shot: true }}, "solo_l", "embed"), false);
assert.strictEqual(shotFallbackPath("solo_r"), "/tweet-shot-solo.png");
assert.strictEqual(shotFallbackPath("card_full"), "/tweet-shot-card.png");
assert.strictEqual(normalizeLayout("card"), "card_full");
assert.strictEqual(normalizeLayout("nope"), "split");
const hidA = {{ hidden: false, className: "hid live" }};
const hidB = {{ hidden: false, className: "hid idle" }};
const root = {{ classList: {{ items: new Set(["layout-split"]), add(name) {{ this.items.add(name); }}, remove(name) {{ this.items.delete(name); }} }} }};
assert.strictEqual(applyOverlayLayout("card_full", {{ hidA, hidB, root, speaker: "a" }}), "card_full");
assert.strictEqual(hidA.hidden, true);
assert.strictEqual(hidB.hidden, true);
assert.ok(root.classList.items.has("layout-card_full"));
applyOverlayLayout("solo_l", {{ hidA, hidB, root, speaker: "a" }});
assert.strictEqual(hidA.hidden, false);
assert.strictEqual(hidB.hidden, true);
assert.strictEqual(hidA.className, "hid live");
applyOverlayLayout("solo_r", {{ hidA, hidB, root, speaker: "b" }});
assert.strictEqual(hidA.hidden, true);
assert.strictEqual(hidB.hidden, false);
assert.strictEqual(hidB.className, "hid live");
assert.strictEqual(formatEasternClock(new Date("2026-09-01T21:17:59Z")), "17:17:59");
assert.strictEqual(formatEasternClock(new Date("2026-01-15T21:17:59Z")), "16:17:59");
assert.strictEqual(safeImageUrl("/tweet.png", "http://127.0.0.1:8765"), "http://127.0.0.1:8765/tweet.png");
assert.strictEqual(safeImageUrl("https://evil.example/x.png", "http://127.0.0.1:8765"), "");
assert.strictEqual(officialEmbedPath("2094640985116737882", "http://127.0.0.1:8765"), "http://127.0.0.1:8765/tweet-embed.html?id=2094640985116737882&theme=dark");
assert.strictEqual(officialEmbedPath("https://evil.example", "http://127.0.0.1:8765"), "");
assert.strictEqual(cardOriginFromSearch("?card_origin=http://127.0.0.1:8765", "http://127.0.0.1:8766"), "http://127.0.0.1:8765");
assert.strictEqual(cardOriginFromSearch("?card_origin=https://evil.example", "http://127.0.0.1:8766"), "http://127.0.0.1:8766");
const nodes = {{
  author: {{ textContent: "" }},
  body: {{ textContent: "" }},
  chyron: {{ textContent: "old" }},
  image: {{ src: "", hidden: true }},
  embed: {{ src: "", hidden: true }},
  shot: {{ src: "", hidden: true }},
  well: {{ classList: {{ added: null, add(name) {{ this.added = name; }}, remove(name) {{ if (this.added === name) this.added = null; }} }} }},
  ticker: {{ textContent: "" }},
  panel: {{ classList: {{ added: null, add(name) {{ this.added = name; }} }} }},
  cardOrigin: "http://127.0.0.1:8765",
  embedOrigin: "http://127.0.0.1:8766",
}};
applyProducerCard({{
  author: "example_user",
  text: "<script>alert(1)</script>",
  chyron: "Ship the workflow",
  ticker: ["unlock", "catch"],
  photo_url: "/media.jpg",
  tweet_id: "2094640985116737882",
}}, nodes);
assert.strictEqual(nodes.author.textContent, "@example_user");
assert.strictEqual(nodes.body.textContent, "<script>alert(1)</script>");
assert.strictEqual(nodes.chyron.textContent, "Ship the workflow");
assert.strictEqual(nodes.image.src, "http://127.0.0.1:8765/media.jpg");
assert.strictEqual(nodes.ticker.textContent, "unlock  ·  catch");
assert.strictEqual(nodes.embed.src, "http://127.0.0.1:8766/tweet-embed.html?id=2094640985116737882&theme=dark");
assert.strictEqual(nodes.well.classList.added, "has-embed");
console.log("ok");
""",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_expected_text_requests() -> None:
    assert expected_text_requests(plan=False, write=False) == 0
    assert expected_text_requests(plan=True, write=False) == 1
    assert expected_text_requests(plan=True, write=True) == 3


def test_stage_fixture_writes_card_package_and_writer_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup = _make_flight_setup(tmp_path / "pack-root")
    _complete_env(monkeypatch, setup)
    config_path = _write_flight_config(tmp_path, setup)
    from runtime_flight.config import load_config, validate_config

    config = load_config(config_path)
    validate_config(config, require_obs=False)
    overlay = OverlayServer(state_dir=tmp_path / "overlay", heartbeat_interval_s=0.05)
    overlay.start()
    try:
        summary = run_stage(
            tweet_url=_fixture()["url"],
            config=config,
            out_dir=tmp_path / "staged",
            confirm_text_requests=3,
            fixture=_fixture(),
            http_post=_stage_text_post,
            overlay=overlay,
        )
        assert summary["author"] == "example_user"
        assert summary["chyron"] == "Ship the workflow, then name the catch"
        assert len(summary["writer_lines"]) == 2
        assert summary["writer_lines"][0]["speaker"] == "BOT1"
        source_dir = Path(summary["source_dir"])
        assert (source_dir / "tweet.png").is_file()
        assert (source_dir / "package.json").is_file()
        assert (source_dir / "writer-preview.json").is_file()
        source = load_source_packet(
            source_dir / "source_packet.local.json",
            source_dir / "source_packet.lock.json",
        )
        assert source.tweet.id == "1234567890123456789"
        import urllib.request

        with urllib.request.urlopen(summary["card_url"], timeout=2) as response:
            card = json.loads(response.read().decode("utf-8"))
        assert card["chyron"] == "Ship the workflow, then name the catch"
        assert card["author"] == "example_user"
        assert card["tweet_id"] == "1234567890123456789"
    finally:
        overlay.stop()


def test_stage_cli_ingest_only_and_writer_confirm_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    setup = _make_flight_setup(tmp_path / "pack-root")
    _complete_env(monkeypatch, setup)
    config_path = _write_flight_config(tmp_path, setup)
    overlay = OverlayServer(state_dir=tmp_path / "overlay", heartbeat_interval_s=0.05)
    overlay.start()
    try:
        from runtime_flight.config import load_config

        summary = run_stage(
            tweet_url=_fixture()["url"],
            config=load_config(config_path),
            out_dir=tmp_path / "staged-cli",
            confirm_text_requests=0,
            plan=False,
            write=False,
            fixture=_fixture(),
            overlay=overlay,
        )
        assert summary["package_path"] is None
        assert summary["writer_lines"] == []
        assert Path(summary["image_path"]).is_file()

        recorded: dict[str, Any] = {}

        def _runner(**kwargs):
            recorded.update(kwargs)
            return {"ok": True}

        held: list[bool] = []
        monkeypatch.setattr("runtime_flight.__main__._hold_overlay", lambda: held.append(True))
        keep_code = main(
            [
                "stage",
                "--config",
                str(config_path),
                "--tweet-url",
                _fixture()["url"],
                "--fixture",
                str(FIXTURE),
                "--out",
                str(tmp_path / "staged-hold"),
                "--ingest-only",
                "--keep-overlay",
            ],
            stage_runner=lambda *args, **kwargs: {"ok": True},
        )
        assert keep_code == 0
        assert held == [True]

        code = main(
            [
                "stage",
                "--config",
                str(config_path),
                "--tweet-url",
                _fixture()["url"],
                "--fixture",
                str(FIXTURE),
                "--out",
                str(tmp_path / "staged"),
                "--confirm-text-requests",
                "1",
            ],
            stage_runner=lambda *args, **kwargs: _runner(**kwargs),
        )
        captured = capsys.readouterr()
        assert code == 1
        assert "confirm-text-requests must be 3" in captured.err
        del recorded
    finally:
        overlay.stop()
