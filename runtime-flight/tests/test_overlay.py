"""Task 12: tweet overlay, loopback watchdog, and atomic heartbeat state."""

from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest

from runtime_flight.overlay import (
    STALE_MS,
    OverlayServer,
    atomic_write_bytes,
)

OVERLAY_DIR = Path(__file__).resolve().parent.parent / "overlay"
APP_JS = OVERLAY_DIR / "app.js"


def _fetch(url: str) -> urllib.request.addinfourl:
    request = urllib.request.Request(url, method="GET")
    return urllib.request.urlopen(request, timeout=2)


def _json(url: str) -> tuple[dict, dict[str, str]]:
    with _fetch(url) as response:
        headers = dict(response.headers.items())
        payload = json.loads(response.read().decode("utf-8"))
    return payload, headers


def test_app_js_syntax():
    completed = subprocess.run(
        ["node", "--check", str(APP_JS)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_overlay_js_hold_and_html_escaping(tmp_path: Path):
    script = tmp_path / "overlay_js_cases.js"
    script.write_text(
        f"""
const assert = require("assert");
const {{ STALE_MS, shouldShowHold, applyCard }} = require({json.dumps(str(APP_JS))});

assert.strictEqual(STALE_MS, 1200);
assert.strictEqual(shouldShowHold({{ unreachable: true, healthy: true, age_ms: 0, receiptAgeMs: 0 }}), true);
assert.strictEqual(shouldShowHold({{ unreachable: false, healthy: false, age_ms: 0, receiptAgeMs: 0 }}), true);
assert.strictEqual(shouldShowHold({{ unreachable: false, healthy: true, age_ms: 1201, receiptAgeMs: 0 }}), true);
assert.strictEqual(shouldShowHold({{ unreachable: false, healthy: true, age_ms: 0, receiptAgeMs: 1201 }}), true);
assert.strictEqual(shouldShowHold({{ unreachable: false, healthy: true, age_ms: 1200, receiptAgeMs: 1200 }}), false);

const nodes = {{ author: {{ textContent: "" }}, tweet: {{ textContent: "" }}, timestamp: {{ textContent: "" }} }};
const xss = "<img src=x onerror=alert(1)><script>alert(1)</script>";
applyCard({{ author: "<b>dwarkesh_sp</b>", text: xss, timestamp: "<i>now</i>" }}, nodes);
assert.strictEqual(nodes.author.textContent, "<b>dwarkesh_sp</b>");
assert.strictEqual(nodes.tweet.textContent, xss);
assert.strictEqual(nodes.timestamp.textContent, "<i>now</i>");
assert.strictEqual(nodes.author.innerHTML, undefined);
console.log("ok");
""",
        encoding="utf-8",
    )
    completed = subprocess.run(
        ["node", str(script)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_atomic_write_rejects_oversize_and_keeps_previous(tmp_path: Path):
    path = tmp_path / "card.json"
    atomic_write_bytes(path, b'{"ok":true}', max_bytes=32)
    with pytest.raises(ValueError, match="size limit"):
        atomic_write_bytes(path, b"x" * 33, max_bytes=32)
    assert path.read_bytes() == b'{"ok":true}'
    assert not (tmp_path / "card.json.tmp").exists()


def test_overlay_binds_loopback_only():
    with pytest.raises(ValueError, match="loopback"):
        OverlayServer(host="0.0.0.0")


def test_overlay_headers_card_unhealthy_stale_and_recovery(tmp_path: Path):
    with OverlayServer(state_dir=tmp_path, heartbeat_interval_s=0.05) as server:
        assert server.host == "127.0.0.1"
        heartbeat, headers = _json(server.url + "heartbeat.json")
        assert headers.get("Cache-Control") == "no-store"
        assert "sequence" in heartbeat
        assert heartbeat["healthy"] is True
        assert isinstance(heartbeat["age_ms"], int)
        assert heartbeat["age_ms"] < STALE_MS

        with _fetch(server.url) as response:
            index_headers = dict(response.headers.items())
            html = response.read().decode("utf-8")
        assert index_headers.get("Cache-Control") == "no-store"
        assert 'id="tweet"' in html
        assert "innerHTML" not in html

        server.set_card(
            author="<b>dwarkesh_sp</b>",
            text="<script>alert(1)</script>",
            timestamp="<i>now</i>",
        )
        card, card_headers = _json(server.url + "card.json")
        assert card_headers.get("Cache-Control") == "no-store"
        assert card["author"] == "<b>dwarkesh_sp</b>"
        assert card["text"] == "<script>alert(1)</script>"
        assert card["timestamp"] == "<i>now</i>"
        assert card["layout"] == "split"
        assert server.set_layout("card") == "card_full"
        card, _ = _json(server.url + "card.json")
        assert card["layout"] == "card_full"
        server.set_card(author="keep", text="keep", timestamp="now")
        card, _ = _json(server.url + "card.json")
        assert card["layout"] == "card_full"

        first_sequence = heartbeat["sequence"]
        time.sleep(0.2)
        later, _ = _json(server.url + "heartbeat.json")
        assert later["sequence"] > first_sequence

        server.mark_unhealthy()
        unhealthy, _ = _json(server.url + "heartbeat.json")
        assert unhealthy["healthy"] is False
        assert unhealthy["age_ms"] < STALE_MS

        server.pause_heartbeat_writer()
        with server._lock:
            server._heartbeat_written_at = time.monotonic() - 1.5
        stale, _ = _json(server.url + "heartbeat.json")
        assert stale["healthy"] is False
        assert stale["age_ms"] > STALE_MS

        server.set_healthy(True)
        recovered, _ = _json(server.url + "heartbeat.json")
        assert recovered["healthy"] is True
        assert recovered["age_ms"] < STALE_MS
        assert recovered["sequence"] > unhealthy["sequence"]


def test_overlay_server_serves_cropped_tweet_shots(tmp_path: Path) -> None:
    from PIL import Image

    from runtime_flight.tweet_shot import write_shot_set

    write_shot_set(Image.new("RGB", (584, 628), (30, 40, 50)), tmp_path)
    with OverlayServer(state_dir=tmp_path, heartbeat_interval_s=0.05) as server:
        urls = server.set_shots(tmp_path, card_mode="shot")
        assert urls["shot_solo_url"] == "/tweet-shot-solo.png"
        card, _ = _json(server.url + "card.json")
        assert card["has_shot"] is True
        assert card["card_mode"] == "shot"
        with _fetch(server.url + "tweet-shot-solo.png") as response:
            assert response.headers.get("Content-Type") == "image/png"
            assert response.read()[:8] == b"\x89PNG\r\n\x1a\n"
