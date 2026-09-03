import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import server as brain  # noqa: E402

def test_fit_line_caps_at_220() -> None:
    line = brain.fit_line("word " * 80)
    assert len(line) <= brain.MAX_LINE
    assert line


def test_stub_laugh_emotion() -> None:
    packet = brain.stub_reply("lol the privacy take is doing too much")
    assert packet["performance"]["emotion"] == "laugh"
    assert packet["performance"]["thinking"] is False
    assert packet["performance"]["energy"] > 0
    assert len(packet["text"]) <= 220


def test_stub_question_and_doubt() -> None:
    ask = brain.stub_reply("Who actually posted this, and is the number real?")
    assert ask["performance"]["emotion"] in brain.EMOTIONS
    doubt = brain.stub_reply("Nah I doubt the product even ships.")
    assert doubt["performance"]["emotion"] == "skeptical"


def test_normalize_rejects_unknown_emotion() -> None:
    packet = brain.normalize_packet(
        {"text": "Sit with the claim.", "performance": {"emotion": "enraged", "energy": 9}},
        "hello",
        source="live",
    )
    assert packet["performance"]["emotion"] in brain.EMOTIONS
    assert packet["performance"]["emotion"] != "enraged"
    assert 0 <= packet["performance"]["energy"] <= 1


def test_host_system_has_no_display_names() -> None:
    assert brain.isolation_violations(brain.HOST_SYSTEM) == []
    assert "writer" not in brain.HOST_SYSTEM.lower()


def test_index_is_solo_host() -> None:
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    assert "PHASEONE[lol]" in html
    assert "deb" not in html.lower()
    assert "zdog" in html.lower()
    assert 'data-mood="skeptical"' in html
    assert 'id="talk"' in html
    assert "Type or talk" in html
    footage = (ROOT / "footage.html").read_text(encoding="utf-8")
    assert "content view" in footage.lower()
    assert "deb" not in footage.lower()
    app = (ROOT / "js" / "footage-app.js").read_text(encoding="utf-8")
    assert "StreamerLoop.nextAction" in app
    assert "dt * speed" in app


def test_composer_never_disables_the_input() -> None:
    app = (ROOT / "js" / "app.js").read_text(encoding="utf-8")
    assert "input.disabled = false" in app
    assert "input.disabled = true" not in app
    assert "input.disabled = next" not in app
    assert "webkitSpeechRecognition" in app
    assert "finishTurn" in app
    assert "{ live: liveBrain }" in app


def test_brain_live_is_opt_in() -> None:
    source = (ROOT / "js" / "brain.js").read_text(encoding="utf-8")
    assert "location.protocol" not in source
    assert "Boolean(options && options.live)" in source


def test_voice_finish_is_idempotent() -> None:
    source = (ROOT / "js" / "voice.js").read_text(encoding="utf-8")
    assert "finished.has(mine)" in source
    assert "hardMs" in source or "2000" in source


def test_zdog_is_vendored() -> None:
    source = (ROOT / "vendor" / "zdog.dist.min.js").read_text(encoding="utf-8")
    assert "Zdog" in source
    assert "v1.1.3" in source


def test_renderer_has_no_llm() -> None:
    grokbot = (ROOT / "js" / "grokbot.js").read_text(encoding="utf-8")
    assert "openai" not in grokbot.lower()
    assert "TEXT_API" not in grokbot
    assert "Hemisphere" in grokbot
    assert "RoundedRect" in grokbot
    assert "equator" in grokbot


def test_log_message_does_not_recurse() -> None:
    source = Path(brain.__file__).read_text(encoding="utf-8")
    assert "self.log_error" not in source
    assert "sys.stderr.write" in source
