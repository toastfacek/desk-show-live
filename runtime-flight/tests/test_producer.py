"""Visual producer board: projection, loopback server, demo clock, operator actions."""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from decimal import Decimal
from pathlib import Path

import pytest

from runtime_flight.models import CoverageState, SegmentPackage
from runtime_flight.producer import (
    DemoShow,
    ProducerBoard,
    ProducerServer,
    apply_operator,
    derive_phase,
    demo_package,
    empty_producer_state,
    format_clock,
    project_from_harness,
    project_producer_state,
    run_demo_board,
)
from runtime_flight.__main__ import main

PRODUCER_DIR = Path(__file__).resolve().parent.parent / "producer"
APP_JS = PRODUCER_DIR / "app.js"


def _fetch(url: str, data: bytes | None = None) -> urllib.request.addinfourl:
    request = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    return urllib.request.urlopen(request, timeout=2)


def _json(url: str, data: bytes | None = None) -> tuple[dict, dict[str, str]]:
    with _fetch(url, data=data) as response:
        headers = dict(response.headers.items())
        payload = json.loads(response.read().decode("utf-8"))
    return payload, headers


def _package() -> SegmentPackage:
    return demo_package()


def _base_kwargs(**overrides):
    payload = {
        "elapsed_s": 12.0,
        "target_s": 90.0,
        "package": _package(),
        "on_air": {
            "kind": "host",
            "take": 2,
            "speaker": "BOT1",
            "line": "Three civilizations rose in ninety days.",
            "ends_at": 15.0,
            "layout": "split",
        },
        "ready": [],
        "cooking": {
            "take": 3,
            "submitted_at": 10.0,
            "speaker": "BOT2",
            "line": "What moved, and for whom?",
        },
        "next_line": {"speaker": "BOT2", "text": "What moved, and for whom?"},
        "flags": {"hold": False, "panic": False, "preview": False},
        "layout": "split",
        "spend_total": Decimal("0.80"),
        "spend_cap": Decimal("12.00"),
        "writer_phase": "develop",
        "coverage": CoverageState.initial(),
        "display_names": {"BOT1": "PHASEONE[lol]", "BOT2": "deb"},
        "aired_count": 2,
        "next_take": 3,
        "mode": "demo",
        "generate_elapsed_s": 2.0,
    }
    payload.update(overrides)
    return payload


def test_format_clock_and_phase():
    assert format_clock(0) == "00:00"
    assert format_clock(90) == "01:30"
    assert (
        derive_phase(
            flags={"panic": True},
            on_air={"kind": "host"},
            cooking=None,
            ready=[],
            next_line=None,
        )
        == "PANIC"
    )
    assert (
        derive_phase(
            flags={"hold": True},
            on_air={"kind": "hold"},
            cooking=None,
            ready=[],
            next_line=None,
        )
        == "HOLD"
    )
    assert (
        derive_phase(
            flags={},
            on_air={"kind": "host"},
            cooking={"take": 2},
            ready=[],
            next_line=None,
        )
        == "PLAY"
    )
    assert (
        derive_phase(
            flags={},
            on_air={"kind": "card"},
            cooking={"take": 1},
            ready=[],
            next_line={"speaker": "BOT1", "text": "x"},
        )
        == "GENERATE"
    )
    assert (
        derive_phase(
            flags={},
            on_air=None,
            cooking=None,
            ready=[{"take": 1}],
            next_line=None,
        )
        == "READY"
    )
    assert (
        derive_phase(
            flags={},
            on_air=None,
            cooking=None,
            ready=[],
            next_line={"speaker": "BOT1", "text": "x"},
        )
        == "WRITE"
    )


def test_project_maps_runtime_jobs_not_votes():
    state = project_producer_state(**_base_kwargs())
    assert state["phase"] == "PLAY"
    assert state["clock"] == "00:12"
    assert state["stats"]["speaker_name"] == "PHASEONE[lol]"
    assert state["stats"]["spend_usd"] == "0.80"
    assert state["lanes"]["on_air"]["status"] == "PLAYING"
    assert state["lanes"]["next"]["status"] == "GENERATING"
    assert "vote" not in json.dumps(state).lower()
    assert any(step["id"] == "generate" and step["state"] == "active" for step in state["pipeline"])
    assert state["story"]["chyron"]
    assert state["program"]["hosts"]["BOT1"]["on_air"] is True
    assert state["program"]["hosts"]["BOT2"]["on_air"] is False


def test_hold_and_panic_projection():
    hold = project_producer_state(**_base_kwargs(flags={"hold": True}, on_air={"kind": "hold"}))
    assert hold["phase"] == "HOLD"
    assert hold["program"]["hold"] is True
    assert hold["controls"]["resume"] is True
    panic = project_producer_state(**_base_kwargs(flags={"panic": True, "hold": True}))
    assert panic["phase"] == "PANIC"
    assert "Panic" in panic["live_state"]


def test_demo_show_advances_and_holds():
    show = DemoShow()
    cold = show.view()
    assert cold["phase"] == "WRITE"
    assert cold["program"]["layout"] == "card_full"
    later = show.tick(8.0)
    assert later["elapsed_s"] == 8.0
    assert later["phase"] in {"PLAY", "GENERATE"}
    assert later["lanes"]["next"]["status"] in {"GENERATING", "WRITING", "READY"}
    show.control("hold")
    held = show.view()
    assert held["phase"] == "HOLD"
    show.control("resume")
    show.tick(1.0)
    assert show.flags["hold"] is False
    show.control("panic")
    assert show.view()["phase"] == "PANIC"
    show.control("next_segment")
    assert show.elapsed_s == 0.0
    assert show.view()["phase"] == "WRITE"


def test_producer_server_loopback_and_control(tmp_path: Path):
    with pytest.raises(ValueError, match="loopback"):
        ProducerServer(host="0.0.0.0")

    board = ProducerBoard()
    board.publish(project_producer_state(**_base_kwargs()))
    with ProducerServer(board=board, producer_dir=PRODUCER_DIR) as server:
        assert server.host == "127.0.0.1"
        state, headers = _json(server.url + "state.json")
        assert headers.get("Cache-Control") == "no-store"
        assert state["phase"] == "PLAY"
        assert "PHASEONE[lol]" in json.dumps(state)

        with _fetch(server.url) as response:
            html = response.read().decode("utf-8")
        assert 'id="live-state"' in html
        assert "innerHTML" not in html
        assert "Showrunner" not in html

        result, _ = _json(
            server.url + "control",
            data=json.dumps({"action": "hold"}).encode("utf-8"),
        )
        assert result["ok"] is True
        assert board.drain_commands() == ["hold"]
        assert board.snapshot()["flags"]["hold"] is True

        with pytest.raises(urllib.error.HTTPError) as raised:
            _json(
                server.url + "control",
                data=json.dumps({"action": "explode"}).encode("utf-8"),
            )
        assert raised.value.code == 400


def test_demo_board_serves_moving_state():
    import threading
    import time

    stop = threading.Event()
    url = run_demo_board(port=0, serve_forever=False, stop=stop, hz=20.0)
    try:
        first, _ = _json(url + "state.json")
        assert first["mode"] == "demo"
        time.sleep(0.35)
        later, _ = _json(url + "state.json")
        assert later["sequence"] >= first["sequence"]
        assert later["elapsed_s"] >= first["elapsed_s"]
    finally:
        stop.set()


def test_apply_operator_sets_harness_flags():
    class Fake:
        flags = {"hold": False, "panic": False, "preview": False}
        ready = []
        events = []
        t = 1.0
        _stop_submits = False
        spend_policy = "normal"

    apply_operator(Fake, "hold")
    assert Fake.flags["hold"] is True
    apply_operator(Fake, "panic")
    assert Fake.flags["panic"] is True
    assert Fake._stop_submits is True
    apply_operator(Fake, "resume")
    assert Fake.flags["hold"] is False
    assert Fake.flags["panic"] is False
    with pytest.raises(ValueError):
        apply_operator(Fake, "explode")


def test_project_from_harness_uses_snapshot():
    class Meter:
        total = Decimal("1.20")
        cap_usd = Decimal("12.00")

    class Pipeline:
        coverage = CoverageState.initial()

        def peek_ready(self):
            return None

    class Harness:
        package = _package()
        meter = Meter()
        pipeline = Pipeline()
        baseline = type("B", (), {"display_names": {"BOT1": "PHASEONE[lol]", "BOT2": "deb"}})()
        target_duration_s = 90.0
        aired_count = 1
        log = []
        _thought_by_take = {}

        def snapshot(self):
            return {
                "t": 20.0,
                "on_air": {"kind": "host", "take": 1, "speaker": "BOT2", "layout": "wide", "line": "hi"},
                "ready": [],
                "cooking": None,
                "next_line": None,
                "flags": {"hold": False, "panic": False},
                "next_take": 2,
                "layout_i": 0,
                "segment": {"layout_plan": ["wide", "split"]},
            }

        def current_writer_phase(self):
            return "develop"

    state = project_from_harness(Harness(), mode="live")
    assert state["mode"] == "live"
    assert state["phase"] == "PLAY"
    assert state["stats"]["speaker"] == "BOT2"
    assert state["stats"]["spend_usd"] == "1.20"


def test_app_js_syntax_and_no_inner_html():
    completed = subprocess.run(
        ["node", "--check", str(APP_JS)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    source = APP_JS.read_text(encoding="utf-8")
    assert "textContent" in source
    assert "innerHTML" not in source
    assert "insertAdjacentHTML" not in source
    assert "document.write" not in source


def test_app_js_apply_state_uses_text_content(tmp_path: Path):
    script = tmp_path / "producer_js_cases.js"
    script.write_text(
        f"""
const assert = require("assert");
const {{ formatClock, percent, applyState, applyLane, applyPipeline }} = require({json.dumps(str(APP_JS))});
global.document = {{
  createElement(tag) {{
    return {{
      tagName: tag,
      className: "",
      classList: {{ add() {{}}, toggle() {{}} }},
      children: [],
      textContent: "",
      style: {{}},
      appendChild(child) {{ this.children.push(child); return child; }},
    }};
  }},
}};

assert.strictEqual(formatClock(90), "01:30");
assert.strictEqual(percent(0.5), "50%");

const lane = {{
  querySelector(sel) {{
    this._nodes = this._nodes || {{}};
    if (!this._nodes[sel]) this._nodes[sel] = {{ textContent: "", style: {{ width: "" }} }};
    return this._nodes[sel];
  }}
}};
applyLane(lane, {{ label: "ON AIR", status: "PLAYING", name: "deb", progress: 0.4, line: "<b>x</b>" }});
assert.strictEqual(lane.querySelector("[data-name]").textContent, "deb");
assert.strictEqual(lane.querySelector("[data-line]").textContent, "<b>x</b>");
assert.strictEqual(lane.querySelector("[data-bar]").style.width, "40%");

const pipe = {{ children: [], childNodes: {{ length: 0 }}, removeChild() {{}}, appendChild(node) {{ this.children.push(node); this.childNodes.length = this.children.length; }} }};
applyPipeline(pipe, [{{ id: "write", label: "WRITE", detail: "1.1s", state: "active" }}]);
assert.strictEqual(pipe.children[0].children[0].textContent, "WRITE");
assert.ok(pipe.children[0].className.includes("is-active"));

const nodes = {{
  eyebrow: {{ textContent: "" }},
  modePill: {{ textContent: "" }},
  liveState: {{ textContent: "" }},
  meta: {{ textContent: "" }},
  note: {{ textContent: "" }},
  statLayout: {{ textContent: "" }},
  statSpeaker: {{ textContent: "" }},
  statSpend: {{ textContent: "" }},
  statSeconds: {{ textContent: "" }},
  rehearsalCopy: {{ textContent: "" }},
  program: {{ classList: {{ toggle() {{}} }} }},
  pgClock: {{ textContent: "" }},
  pgLive: {{ style: {{ opacity: "" }} }},
  cardAuthor: {{ textContent: "" }},
  cardBody: {{ textContent: "" }},
  pgLine: {{ textContent: "" }},
  chyronKicker: {{ textContent: "" }},
  chyronHead: {{ textContent: "" }},
  hostLName: {{ textContent: "" }},
  hostRName: {{ textContent: "" }},
  wellL: {{ classList: {{ toggle() {{}} }} }},
  wellR: {{ classList: {{ toggle() {{}} }} }},
  pgHoldLabel: {{ textContent: "" }},
  dotClock: {{ classList: {{ toggle() {{}} }} }},
  dotVideo: {{ classList: {{ toggle() {{}} }} }},
  dotSpend: {{ classList: {{ toggle() {{}} }} }},
  laneOnAir: null,
  laneNext: null,
  pipe: {{ children: [], childNodes: {{ length: 0 }}, removeChild() {{}}, appendChild() {{}} }},
  btnPreview: {{ disabled: false, classList: {{ toggle() {{}} }} }},
  btnHold: {{ disabled: false, classList: {{ toggle() {{}} }} }},
  btnResume: {{ disabled: false, classList: {{ toggle() {{}} }} }},
  btnKill: {{ disabled: false, classList: {{ toggle() {{}} }} }},
  btnNext: {{ disabled: false, classList: {{ toggle() {{}} }} }},
  btnPanic: {{ disabled: false, classList: {{ toggle() {{}} }} }},
  writerPhase: {{ textContent: "" }},
  writerBeat: {{ textContent: "" }},
  writerMeta: {{ textContent: "" }},
  writerReady: {{ children: [], childNodes: {{ length: 0 }}, removeChild() {{}}, appendChild(n) {{ this.children.push(n); this.childNodes.length = this.children.length; }} }},
  storyId: {{ textContent: "" }},
  storyQuestion: {{ textContent: "" }},
  storyFraming: {{ textContent: "" }},
  storyFight: {{ textContent: "" }},
  storyBeats: {{ children: [], childNodes: {{ length: 0 }}, removeChild() {{}}, appendChild(n) {{ this.children.push(n); this.childNodes.length = this.children.length; }} }},
  queueNow: {{ children: [], childNodes: {{ length: 0 }}, removeChild() {{}}, appendChild(n) {{ this.children.push(n); this.childNodes.length = this.children.length; }} }},
  queueLog: {{ children: [], childNodes: {{ length: 0 }}, removeChild() {{}}, appendChild(n) {{ this.children.push(n); this.childNodes.length = this.children.length; }} }},
}};
const xss = "<img src=x onerror=alert(1)>";
applyState({{
  show: "RUNTIME",
  system: "LIVE SYSTEM",
  mode: "demo",
  phase: "PLAY",
  elapsed_s: 12,
  clock: "00:12",
  live_state: xss,
  meta: "segment x",
  note: "play while generating",
  stats: {{ layout: "split", speaker: "BOT1", speaker_name: "PHASEONE[lol]", spend_usd: "0.40", spend_cap: "12.00" }},
  program: {{
    layout: "split", live: true, hold: false, preview: false, speaker: "BOT1",
    hosts: {{ BOT1: {{ name: "PHASEONE[lol]", on_air: true }}, BOT2: {{ name: "deb", on_air: false }} }},
    card: {{ author: "<b>dwarkesh_sp</b>", body: xss }},
    chyron: {{ kicker: "DESK", headline: xss }},
    line: xss, clock: "00:12"
  }},
  lanes: {{}},
  pipeline: [],
  flags: {{}},
  controls: {{ preview_next: true, hold: true, resume: false, kill_take: false, next_segment: true, panic: true }},
  writer: {{ phase: "develop", ready: [{{ speaker: "BOT2", text: xss }}], coverage: {{ beat_id: "b1", exchanges: 1, map_complete: false, question: xss }} }},
  story: {{ item_id: "one", question: xss, framing: "frame", chyron: "c", beats: [], throughline: "", fight: "" }},
  queue: {{ cooking: null, ready: [], log: [] }}
}}, nodes);
assert.strictEqual(nodes.liveState.textContent, xss);
assert.strictEqual(nodes.cardBody.textContent, xss);
assert.strictEqual(nodes.cardAuthor.textContent, "<b>dwarkesh_sp</b>");
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


def test_board_cli_refuses_non_loopback(capsys: pytest.CaptureFixture[str]):
    code = main(["board", "--host", "0.0.0.0", "--port", "8766"])
    captured = capsys.readouterr()
    assert code == 1
    assert "loopback" in captured.err


def test_empty_state_is_hold():
    state = empty_producer_state()
    assert state["phase"] == "HOLD"
    assert state["program"]["hold"] is True
