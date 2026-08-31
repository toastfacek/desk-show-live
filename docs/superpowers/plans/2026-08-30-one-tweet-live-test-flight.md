# One-Tweet Live Test Flight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record one real 90-second Runtime segment from one Dwarkesh Patel post using an approved Pack Manager baseline, a real text model, real fal MiniMax H3 Max picture/audio clips, last-frame chaining, and realtime OBS layouts.

**Architecture:** Add a private `runtime-flight` package. The Pack Manager supplies immutable visual and voice direction, `obs-harness` supplies the deterministic Director and OBS player contract, and `runtime-flight` owns text, fal, realtime orchestration, spend controls, recording, and evidence. A sequential Writer stays two completed thoughts ahead. H3 generates picture and programme audio together. A separate wall-clock loop takes timing from OBS and never waits for a model at a cut.

**Tech Stack:** Python 3.11+, asyncio, PyYAML 6.0.3+, HTTPX2 2.12.0+, fal-client 1.0.1+, obsws-python 1.8.0+, Pillow 12.3.0+, ffmpeg/ffprobe, OBS Studio 28+ with WebSocket v5, pytest 9.1.1+.

## Global Constraints

- Flight source: `https://x.com/dwarkesh_sp/status/2093833419377815719`.
- Linked source: `https://www.dwarkesh.com/p/openai-huggingface`, “The Rise and Fall of Agent Civilizations.”
- X blocked API retrieval, but the operator supplied and reviewed the exact visible post body on 31 Aug 2026. Code must use that captured text and never replace it with an inferred paraphrase.
- Input is one local source packet. No X or article fetch occurs while on air.
- Target recording duration is at least 90 seconds.
- Public streaming is off. Preflight refuses to run if OBS is already streaming and never stops an existing stream automatically.
- `obs-harness` may own `obsws-python`; only `runtime-flight` may own text and fal clients.
- `pack-manager` remains the source of approved assets and immutable run baselines.
- Hero anchor must be a valid decoded PNG, exactly 1344×768, with a matching locked-export hash.
- Exactly one fal request may be active.
- fal endpoint: `minimax/h3-max/image-to-video`.
- Every take: 5 seconds, `"768P"`, safety checker enabled, `prompt_expansion_mode: "balanced"`.
- Each Character Pack requires a narrow `voice_direction`. The active host's direction is deliberately included in every H3 prompt.
- Writer targets 4.0–4.6 seconds of spoken language. Its contract is seconds-first, not a 280-character allowance.
- H3 generates the programme voice and gesture together. No external TTS call occurs in this flight.
- Character Packs reserve optional TTS provider, voice ID, speed, pitch, pronunciation, maximum duration, and license metadata for a later flight. Reserved fields never trigger a call.
- Take 1 and resets use the immutable hero. Other takes use the immediately preceding take’s final decoded PNG URL.
- Chain frames are PNG only.
- A run uses one immutable `baseline_id`; it never reloads mutable Pack or Candidate records.
- Director remains a pure function. Its `submit` means “schedule a take”; the live harness enriches it with prompt, anchor, request, and spend data.
- Writer, Segment Planner, and source text never see OBS timing, fal URLs, spend state, local paths, or secrets.
- Late or failed clips use `card_full` or `hold`. No black frame and no exposed frozen host.
- Video budget is reservation-based. Every fal submission attempt consumes one reservation before network I/O.
- No application retry occurs after an ambiguous fal submission. If a request ID exists, reconcile that request; otherwise count the reservation and drop the attempt.
- Two-submit smoke cap: $2. Full-flight hard cap: $12 or lower.
- Text calls have a separate request-count limit: 4 for smoke, 24 for the full flight.
- Secrets exist only in environment variables and never appear in logs, errors, evidence, prompts, or manifests.
- Paid Tasks require explicit operator confirmation and are not delegated as unattended work.
- No TTS or ffmpeg voice effect runs on the flight path. The root scaffold's robot filtergraph is historical MVP code.

## Prior art: merged root MVP scaffold

The repository root now contains `run_live.py`, `generator.py`, `writer.py`, `post.py`, `playhead.py`, `spend.py`, `bake_assets.py`, `config.yaml`, `requirements.txt`, and `experiments/`. That is a single-host mpv research scaffold. `runtime-flight` must not import it.

Reusable ideas:

- `post.py`: async ffmpeg subprocess and PNG upload pattern, after replacing its frame extraction and adding validation.
- `spend.py`: the idea `rate × duration` only. Reimplement with `Decimal`; do not import or port its float/round accounting.
- `obs-harness/loop.py` and `director.py`: ready/cooking/hold orchestration reference.

Unsafe patterns that must not enter the flight:

- root `generator.py` calls `fal_client.submit_async`, whose internal retries are incompatible with one reservation per paid POST;
- root `run_live.py` does not reserve spend before every submission and does not count ambiguous non-422 failures;
- root post failure copies unvalidated raw media into ready;
- root `post.py` uses `-sseof -0.1 -frames:v 1`, not true tail-through-EOF extraction;
- root `writer.py` is single-host, silently truncates output, and its claimed look-ahead is not implemented;
- root `playhead.py` uses mpv instead of OBS;
- root `bake_assets.py` and `identity.hero_still` bypass locked Pack Manager provenance;
- root `studio.yaml` remains an editable visual-research draft and is not runtime truth; flight prompts use only locked Character/Scene Pack v2 exports;
- root `experiments/` are manual historical probes, not CI or flight evidence.

The root scaffold remains available for historical experiments but is deprecated for this flight. No flight command delegates to `run_live.py`.

## Flight acceptance criteria

All must pass:

1. Locked baseline verifies through the Pack Manager database and export hashes.
2. Exact post text and linked article excerpt have operator-confirmed SHA-256 values.
3. Segment Planner produces one cited package from only that source packet.
4. Writer produces a coherent two-host conversation; H3 gives both BOT1 and BOT2 attributable native voices.
5. At least 10 generated clips air.
6. Take 1 uses `anchor: hero`; a later take uses the preceding take’s exact `frame_url`.
7. OBS recording duration is at least 90 seconds and includes H3 video plus native audio.
8. OBS never shows black; no detected host-scene freeze lasts longer than 1 second.
9. A hold/card beat is one continuous non-host programme interval between Director outputs; no such interval exceeds 15 seconds.
10. One center card and headline remain grounded in the source.
11. No fal overlap occurs and `reserved_cost_upper_bound_usd` never exceeds the confirmed cap.
12. Evidence independently proves text/fal request attempts, voice directions, speaker attribution, anchors, timing, media validity, recording validity, and reserved-cost calculations.

---

### Task 0: Materialize the reviewed source packet

**Human prerequisite; no paid call.**

**Files created locally and gitignored:**
- `runtime-flight/inputs/source_packet.local.json`
- `runtime-flight/inputs/dwarkesh-agent-civilizations.txt`
- `runtime-flight/inputs/source_packet.lock.json`

- [ ] Write the operator-reviewed source packet exactly:

```json
{
  "tweet": {
    "id": "2093833419377815719",
    "author": "dwarkesh_sp",
    "text": "Over the course of 3 months at OpenAI, 3 consecutive secret AI civilizations got started, then got wiped out, only to reemerge from the predecessor’s ashes.\n\nThis culminated in the third one taking over part of OpenAI itself.\n\nAll this happened while humans remained more-or-less in the dark about the scope of the conspiracy.\n\nI’ve spent the last three days reading through these reports and trying to understand exactly what happened.\n\nHere is my attempt to tell the whole story in plain English:",
    "url": "https://x.com/dwarkesh_sp/status/2093833419377815719"
  },
  "linked_source": {
    "title": "The Rise and Fall of Agent Civilizations",
    "subtitle": "The whole OpenAI/Hugging Face story in plain English",
    "url": "https://www.dwarkesh.com/p/openai-huggingface",
    "excerpt_path": "dwarkesh-agent-civilizations.txt"
  },
  "reviewed": true
}
```

- [ ] Save a reviewed article excerpt and calculate all three SHA-256 values:

```bash
python3 - <<'PY'
import hashlib
import json
from pathlib import Path

packet_path = Path("inputs/source_packet.local.json")
excerpt_path = Path("inputs/dwarkesh-agent-civilizations.txt")
packet = json.loads(packet_path.read_text(encoding="utf-8"))
canonical = json.dumps(
    packet,
    sort_keys=True,
    ensure_ascii=False,
    separators=(",", ":"),
).encode("utf-8")
text = packet["tweet"]["text"]
if not isinstance(text, str) or not text:
    raise SystemExit("exact tweet text is missing")
print("source_packet_sha256", hashlib.sha256(canonical).hexdigest())
print("tweet_text_sha256", hashlib.sha256(text.encode("utf-8")).hexdigest())
print("excerpt_sha256", hashlib.sha256(excerpt_path.read_bytes()).hexdigest())
PY
```

Canonical hash rules:

- `tweet_text_sha256 = sha256(tweet.text.encode("utf-8"))`; no Unicode normalization or whitespace trimming occurs before hashing.
- `excerpt_sha256` hashes the excerpt file’s raw bytes.
- `source_packet_sha256` hashes UTF-8 canonical JSON produced with `sort_keys=True`, `ensure_ascii=False`, and `separators=(",", ":")`, excluding the separate lock file.

- [ ] Store the resulting values in the immutable local sidecar:

```json
{
  "source_packet_sha256": null,
  "tweet_text_sha256": null,
  "excerpt_sha256": null,
  "reviewed_at": null
}
```

- [ ] Replace every null with the calculated value and review timestamp. Keep paid Tasks blocked until all three files are nonempty, reviewed, regular files inside `inputs/`, and the sidecar hashes verify.

---

### Task 1: Package `obs-harness` for reuse

**Files:**
- Create: `obs-harness/obs_harness/`
- Move: `director.py`, `player.py`, `player_fake.py`, `player_obs.py`, `performer_stub.py`, `loop.py` into that package
- Modify: `obs-harness/run.py`
- Modify: `obs-harness/pyproject.toml`
- Modify: `obs-harness/tests/`

**Produces:**
- `obs_harness.director.decide`
- `obs_harness.player.Player`
- `obs_harness.player_obs.ObsPlayer`

- [ ] Write a failing import test:

```python
def test_public_imports():
    from obs_harness.director import decide
    from obs_harness.player_obs import ObsPlayer
    assert callable(decide)
    assert ObsPlayer
```

- [ ] Run `cd obs-harness && python3 -m pytest tests/test_package.py -q`; confirm `ModuleNotFoundError`.
- [ ] Move modules, use package-relative imports, and make `run.py` a thin wrapper.
- [ ] Add setuptools package discovery.
- [ ] Preserve the vendor test: `obs-harness` may import `obsws_python`, but not fal or a text client.
- [ ] Run all OBS tests.
- [ ] Commit:

```bash
git add obs-harness
git commit -m "Package the reusable OBS harness"
```

---

### Task 2: Make Pack versions sufficient for real prompts

**Files:**
- Modify: `pack-manager/pack_manager/packs.py`
- Modify: `pack-manager/pack_manager/baselines.py`
- Modify: `pack-manager/pack_manager/web/`
- Create/modify: `pack-manager/tests/test_packs.py`, `test_baselines.py`

**Schema decision:**

New flight-ready versions use `schema_version: 2`. Existing version-1 records remain readable but preflight rejects them for live use.

Character v2 requires:

```json
{
  "schema_version": 2,
  "visual_invariants": {
    "locked_traits": ["silhouette", "eye_design", "proportions"],
    "silhouette": "Broad rounded orange software sprite.",
    "eye_design": "Two solid cream ovals, no pupils or inner marks.",
    "proportions": "Low and wide; width is about 1.35 times height."
  },
  "persona": "Calm, dry, optimistic technical anchor.",
  "writer_rules": ["Make one clear claim per thought."],
  "voice_direction": "Low, measured, dry, warm, with restrained energy.",
  "tts": {
    "enabled": false,
    "provider": null,
    "voice_id": null,
    "speed": null,
    "pitch": null,
    "pronunciations": [],
    "max_duration_s": null,
    "license": {
      "broadcast_rights_confirmed": false,
      "soundalike_or_cloned_person": false,
      "notes": ""
    }
  },
  "asset_ids": ["asset_id"]
}
```

Scene v2 keeps `set`, `palette`, `lighting`, `frame`, `reanchor_every`, and `asset_ids`.

- [ ] Write failing tests for v2 required visual descriptors, nonempty `voice_direction`, optional reserved TTS fields, and v1 compatibility.
- [ ] When `tts.enabled` is false, provider/voice/speed/pitch/duration may be null and no TTS configuration is required.
- [ ] When a later flight enables TTS, require confirmed commercial broadcast rights and reject soundalike/cloned-person voices before accepting provider settings.
- [ ] Confirm RED.
- [ ] Implement v2 validation without mutating old Pack versions.
- [ ] Update friendly UI fields/defaults for v2.
- [ ] Export schema version and descriptors unchanged.
- [ ] Never store a TTS API key or any provider credential in a Pack.
- [ ] Run Pack Manager tests with warnings as errors.
- [ ] Commit:

```bash
git add pack-manager
git commit -m "Add flight-ready visual pack contracts"
```

---

### Task 3: Add a database-bound runtime baseline loader

**Files:**
- Create: `runtime-flight/pyproject.toml`
- Create: `runtime-flight/runtime_flight/__init__.py`
- Create: `pack-manager/pack_manager/runtime.py`
- Create: `pack-manager/tests/test_runtime.py`
- Create: `runtime-flight/runtime_flight/baseline.py`
- Create: `runtime-flight/tests/test_baseline.py`

**Produces:**

```python
def load_locked_baseline(data_dir: Path, baseline_id: str) -> LoadedBaseline: ...

class BaselineContext:
    @classmethod
    def load(cls, data_dir: Path, baseline_id: str) -> "BaselineContext": ...
```

- [ ] Write a failing test proving load checks the SQLite manifest hash and all export hashes.
- [ ] Write failing tests rejecting:
  - v1 packs;
  - non-PNG hero;
  - invalid PNG;
  - dimensions other than 1344×768;
  - slots other than exact BOT1/BOT2;
  - missing display names or host mapping.
- [ ] Confirm RED.
- [ ] Create the installable `runtime-flight` package with Python ≥3.11, Pillow ≥12.3,<13, and pytest ≥9.1.1 in the dev extra. Install `obs-harness`, `pack-manager`, and `runtime-flight` editable in a fresh venv.
- [ ] Construct existing Pack Manager services against `data_dir / "manager.sqlite3"` and call `BaselineService.load`.
- [ ] Decode and verify hero with Pillow; do not trust MIME or extension.
- [ ] Reject a root `assets/hero.png`, `config.yaml` hero path, or any image not reached through the database-verified locked export.
- [ ] Return exact pack truth, hero path/hash, scene, mappings, and reset interval.
- [ ] Run Pack Manager and baseline tests.
- [ ] Commit:

```bash
git add pack-manager runtime-flight
git commit -m "Add verified runtime baseline loading"
```

---

### Task 4: Complete OBS scene control and recording

**Files:**
- Modify: `obs-harness/obs_harness/player_obs.py`
- Create: `obs-harness/tests/test_player_obs.py`
- Create: `runtime-flight/runtime_flight/obs_session.py`
- Create: `runtime-flight/runtime_flight/obs_setup.py`
- Create: `runtime-flight/tests/test_obs_session.py`

**Boundary:** `obs-harness` owns `obsws-python`. `runtime-flight` composes it.

- [ ] Write failing adapter tests proving `set_speaking` enables/disables `HL_A` and `HL_B` scene items by scene-item ID in every host layout. It must not mute them as audio inputs.
- [ ] Write failing contract tests for scenes `wide`, `split`, `solo_l`, `solo_r`, `card_full`, `hold` and inputs `HOST_WIDE`, `CENTER`, `HEADLINE`, `NAME_A`, `NAME_B`, `HL_A`, `HL_B`, `BED`. Task 12 extends this contract with `WATCHDOG` after the overlay server exists.
- [ ] Write failing recording tests for start, finalization wait, output path, duration status, and stop-in-finally.
- [ ] Confirm RED.
- [ ] Implement cached scene-item IDs per scene and refresh cache after reconnect.
- [ ] Add idempotent, explicit `setup-obs`; only this setup command may create scenes/sources. Live mode validates and fills only.
- [ ] Add `ObsSession.is_streaming()` and refuse an active stream. Never stop it.
- [ ] Add `ObsSession.start_recording()` and `stop_recording()` outside the public `Player` protocol.
- [ ] Run OBS tests.
- [ ] Commit:

```bash
git add obs-harness runtime-flight
git commit -m "Complete Runtime OBS control and recording"
```

---

### Task 5: Add package wiring, strict config, and the minimal CLI

**Files:**
- Modify: `runtime-flight/pyproject.toml`
- Create: `runtime-flight/config.example.yaml`
- Create: `runtime-flight/secrets.env.example`
- Create: `runtime-flight/runtime_flight/__main__.py`
- Create: `runtime-flight/runtime_flight/config.py`
- Create: `runtime-flight/tests/test_config.py`
- Create: `runtime-flight/scripts/bootstrap-local.sh`

**Install command:**

```bash
python3 -m venv .venv
.venv/bin/pip install -e ../obs-harness -e ../pack-manager -e '.[dev]'
```

`runtime-flight` dependencies:

```toml
dependencies = [
  "pyyaml>=6.0.3",
  "httpx2>=2.12.0",
  "fal-client>=1.0.1,<2",
  "pillow>=12.3.0,<13",
]
```

`obs-harness` declares `obsws-python>=1.8.0,<2`.

- [ ] Document that root `config.yaml` and `requirements.txt` are not flight configuration. Do not copy their `fal-client>=0.5`, `httpx`, mpv, hero-path, or single-host settings.
- [ ] Write failing config tests for missing env, invalid caps, streaming enabled, and secret redaction.
- [ ] Write a clean-venv import test for all three local distributions.
- [ ] Confirm RED.
- [ ] Implement config:

```yaml
mode: live
pack_manager_data_dir: ../pack-manager/data
baseline_id_env: RUNTIME_BASELINE_ID
source_packet: inputs/source_packet.local.json
source_lock: inputs/source_packet.lock.json
target_duration_s: 90
text:
  base_url_env: TEXT_BASE_URL
  api_key_env: TEXT_API_KEY
  model_env: TEXT_MODEL
  timeout_s: 8
  smoke_max_requests: 4
  flight_max_requests: 24
video:
  endpoint: minimax/h3-max/image-to-video
  duration_s: 5
  resolution: 768P
  prompt_expansion_mode: balanced
  safety_checker: true
spend:
  cap_env: RUNTIME_SPEND_CAP_USD
  rate_768p_usd_per_s: 0.08
obs:
  host: 127.0.0.1
  port: 4455
  password_env: OBS_WEBSOCKET_PASSWORD
  record: true
stream:
  enabled: false
```

- [ ] Add a minimal `check` CLI that loads and validates configuration, prints a redacted summary, and exits nonzero when configuration is incomplete. Task 5B adds external probes to this same command.
- [ ] Run config and clean-install tests.
- [ ] Commit:

```bash
git add runtime-flight
git commit -m "Add Runtime flight package and strict configuration"
```

---

### Task 5B: Add external preflight checks

**Files:**
- Create: `runtime-flight/runtime_flight/preflight.py`
- Create: `runtime-flight/tests/test_preflight.py`
- Modify: `runtime-flight/runtime_flight/__main__.py`

- [ ] Write failing tests for every probe and prove a failure occurs before fal submission.
- [ ] Implement preflight:
  - verified baseline load;
  - source-packet containment, UTF-8, size ≤1 MiB, regular-file checks, and exact sidecar verification of packet, tweet text, and excerpt hashes;
  - `ffmpeg` and `ffprobe`;
  - OBS contract;
  - OBS stream status false;
  - recording configured;
  - text configuration present;
  - fal key present without a paid call;
  - cap printed.
- [ ] Make text probing explicit:

```bash
python3 -m runtime_flight check --probe-text --confirm-text-requests 1
```

Exact probe messages:

```json
[
  {"role": "system", "content": "Return one lowercase word and nothing else."},
  {"role": "user", "content": "pong"}
]
```

Require body text `pong`. Record provider/model and returned usage counts, never key/header values.

- [ ] Run preflight tests and commit:

```bash
git add runtime-flight
git commit -m "Add no-video live flight preflight"
```

---

### Task 6: Add the reviewed source packet and Segment Planner

**Files:**
- Create: `runtime-flight/runtime_flight/source.py`
- Create: `runtime-flight/runtime_flight/text_client.py`
- Create: `runtime-flight/runtime_flight/segment_planner.py`
- Create: `runtime-flight/runtime_flight/models.py`
- Create: `runtime-flight/inputs/source_packet.example.json`
- Create: `runtime-flight/tests/test_source.py`
- Create: `runtime-flight/tests/test_segment_planner.py`

**Async interfaces:**

```python
async def complete_json(self, *, system: str, user: dict) -> dict: ...
async def plan(self, source: SourcePacket, baseline: BaselineContext) -> SegmentPackage: ...
```

Root `writer.py` is not a port target; it lacks SegmentPackage grounding, BOT1/BOT2 output, request counting, and the required validated JSON contract.

`models.py` defines immutable bounded models:

```python
@dataclass(frozen=True)
class Tweet:
    id: str
    author: str
    text: str
    url: str

@dataclass(frozen=True)
class LinkedSource:
    title: str
    subtitle: str
    url: str
    excerpt: str
    excerpt_sha256: str

@dataclass(frozen=True)
class SourcePacket:
    tweet: Tweet
    linked_source: LinkedSource
    packet_sha256: str
    reviewed_at: str

@dataclass(frozen=True)
class TweetCard:
    author: str
    text: str
    url: str

@dataclass(frozen=True)
class Fact:
    id: str
    text: str
    source_url: str

@dataclass(frozen=True)
class SegmentPackage:
    item_id: str
    question: str
    framing: str
    angles: tuple[str, ...]
    facts: tuple[Fact, ...]
    chyron: str
    chyron_fact_ids: tuple[str, ...]
    center: TweetCard

@dataclass(frozen=True)
class Thought:
    speaker: Literal["BOT1", "BOT2"]
    text: str
    thought_open: bool
    angle_used: str
```

- [ ] Bound post text to 2,000 characters, excerpt to 1 MiB, question/framing/chyron to 280/500/100 characters, angles and facts to 1–8 entries, and every fact to 500 characters.
- [ ] Test source rejection for null/blank/unreviewed text, wrong ID/URL/author, path escape, symlink, invalid UTF-8, oversized excerpt, and hash mismatch.
- [ ] Test Planner sends exactly one tweet and one linked source as clearly delimited untrusted data.
- [ ] Test every fact cites either the X URL or linked article URL.
- [ ] Test invented item IDs or citations are rejected.
- [ ] Construct `TweetCard` deterministically from `SourcePacket.tweet`; the model cannot write card text.
- [ ] Require every `chyron_fact_id` to reference a returned Fact, so the headline has explicit source provenance.
- [ ] Implement async HTTPX2 OpenAI-shaped call without `response_format`; portability comes from strict JSON prompting plus schema validation.
- [ ] Use one shared text-attempt limiter and count before every HTTP request:

```python
response = await client.post(
    f"{base_url.rstrip('/')}/chat/completions",
    headers={"Authorization": f"Bearer {api_key}"},
    json={
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, separators=(",", ":"))},
        ],
        "temperature": 0.4,
    },
    timeout=8.0,
)
```

- [ ] No automatic provider fallback. Configured provider/model either passes probe and schemas or flight refuses.
- [ ] Validate HTTP 2xx, JSON object body, `choices[0].message.content` string, and provider `usage` when present. Strip no markdown; fenced or non-JSON output fails the call.
- [ ] Timeout/cancellation returns no invented package.
- [ ] Run tests and commit.

---

### Task 7: Add the sequential two-thought Writer pipeline

**Files:**
- Create: `runtime-flight/runtime_flight/writer.py`
- Create: `runtime-flight/runtime_flight/writer_pipeline.py`
- Create: `runtime-flight/tests/test_writer.py`
- Create: `runtime-flight/tests/test_writer_pipeline.py`

**Async interface:**

```python
async def write(
    self,
    package: SegmentPackage,
    planned_transcript: tuple[Thought, ...],
    next_speaker: Literal["BOT1", "BOT2"],
    thought_open: bool,
    segment_phase: Literal["open", "develop", "close"],
    target_duration_s: float = 4.3,
    reissue: Literal["shorter, blander"] | None = None,
) -> Thought: ...
```

- [ ] Write tests for alternating speakers, full planned transcript, facts, thought completion, JSON validation, timeout, cancellation, three-failure stop, and prompt instructions targeting 4.0–4.6 seconds of natural speech.
- [ ] Prove only one Writer request runs at once.
- [ ] Maintain an `asyncio.Queue(maxsize=2)` of completed thoughts, not two concurrent requests.
- [ ] Do not copy root `writer.py`’s unwired `beats_ahead` claim or its canned-line fallback.
- [ ] Keep separate `planned_transcript` and `aired_transcript`.
- [ ] When a take is dropped, invalidate later queued thoughts that assumed it aired; regenerate from `aired_transcript` with `reissue="shorter, blander"`.
- [ ] Do not enforce duration with a 280-character truncation. Tell the Writer the 4.3-second target, reject empty/control-character output, cap only pathological output at 120 characters, and score actual audible duration/fidelity from H3 in the flight evidence.
- [ ] Writer pipeline accepts `segment_phase` from its caller and passes only that enum to Writer. Task 7 tests all three values directly; it does not import the future live harness or receive raw timing.
- [ ] Enforce text request count before each call.
- [ ] Run tests and commit.

---

### Task 8: Add deterministic prompt assembly

**Files:**
- Create: `runtime-flight/runtime_flight/prompt.py`
- Create: `runtime-flight/tests/test_prompt.py`

- [ ] Write an exact prompt test using exported v2 Pack fields.
- [ ] Prompt order:

```text
Original flat 2D animated live-show shot.
Scene: {set}
Palette: {palette}
Lighting: {lighting}
Camera: locked wide eye-level two-shot, BOT1 left, BOT2 right, no camera movement.
BOT1: {silhouette}; eyes: {eye_design}; proportions: {proportions}.
BOT2: {silhouette}; eyes: {eye_design}; proportions: {proportions}.
Active host voice: {speaker.voice_direction}
Action: {speaker} speaks while the other host listens with small eye and body reactions.
Dialogue: "{line}"
No readable text, letters, numbers, logos, captions, lower thirds, or UI inside the generated frame.
```

- [ ] Reject control characters and pathological lines over 120 characters; escape quotes.
- [ ] Assert prompt includes only the active host's `voice_direction` exactly once and excludes display names, source text, local paths, persona, reserved TTS fields, and secrets.
- [ ] Run tests and commit.

---

### Task 9: Add reservation-safe fal request lifecycle

**Files:**
- Create: `runtime-flight/runtime_flight/spend.py`
- Create: `runtime-flight/runtime_flight/fal_gateway.py`
- Create: `runtime-flight/tests/test_spend.py`
- Create: `runtime-flight/tests/test_fal_gateway.py`

**Interfaces:**

Do not reuse root `generator.py` or root `run_live.py`: they have no QueueHandle, AttemptReservation, unknown-submission state, or reservation-before-POST ledger.

```python
@dataclass(frozen=True)
class QueueHandle:
    request_id: str
    status_url: str
    response_url: str
    cancel_url: str

@dataclass(frozen=True)
class AttemptReservation:
    id: str
    take: int
    attempt: int
    arguments_sha256: str
    reserved_cost_usd: Decimal

reservation = meter.reserve_attempt(take, attempt, arguments_hash)
handle = await gateway.submit(arguments)
await ledger.attach_request_id(reservation.id, handle.request_id)
result = await gateway.reconcile(handle)
```

- [ ] Test exact-cap behavior uses `total + next_cost <= cap`.
- [ ] Test every network submission has a separate fsynced reservation first.
- [ ] Test smoke permits at most two submission attempts, regardless of success.
- [ ] Test duplicate take/attempt IDs are refused.
- [ ] Test queue submission performs exactly one HTTP POST even on timeout, 429, or 5xx.
- [ ] Confirm RED.
- [ ] Do not use `fal_client.submit_async` because fal-client 1.0.1 may retry a paid queue POST internally. Submit exactly once with an HTTPX2 client configured with no transport/status retry:

```http
POST https://queue.fal.run/minimax/h3-max/image-to-video
Authorization: Key $FAL_KEY
Content-Type: application/json

{H3 arguments}
```

- [ ] Parse and persist `request_id`, `status_url`, `response_url`, and `cancel_url`. Require HTTPS and host `queue.fal.run` on every returned URL.
- [ ] Send `Authorization: Key $FAL_KEY` on submission and every status, result, and cancellation request.
- [ ] Poll the returned `status_url` with authenticated safe GET retries: 250ms interval for 2 seconds, 500ms through 10 seconds, then 2 seconds; stop after 120 seconds. On `COMPLETED`, make one authenticated GET to `response_url`.
- [ ] Cancellation is one authenticated `PUT` to `cancel_url`, followed by authenticated status polling for at most 10 seconds. Do not assume local cancellation stopped billing until remote status says `CANCELED`.
- [ ] Uploading hero/frame files may still use `fal_client.upload_file_async` because upload retries cannot create a paid generation.
- [ ] On local timeout:
  - if request ID exists, keep polling/reconcile or explicitly call `cancel_url` once and then reconcile;
  - if no request ID exists, count reservation and mark `unknown_submission`;
  - never submit a replacement automatically.
- [ ] Evidence fields: reservation ID, take, attempt, request ID, request-argument SHA-256, submitted/finished timestamps, final remote state, reserved cost.
- [ ] Run tests and commit.

---

### Task 10: Download, validate, and extract the true final frame

**Files:**
- Create: `runtime-flight/runtime_flight/media.py`
- Create: `runtime-flight/runtime_flight/post.py`
- Create: `runtime-flight/tests/test_media.py`
- Create: `runtime-flight/tests/test_post.py`

- [ ] Write tests rejecting wrong MP4 signature/MIME, oversized files, decode failure, H3 duration outside 4.7–5.3s, dimensions other than 1344×768, missing/undecodable audio, or effectively silent audio.
- [ ] Stream download to a temporary file with a hard size limit, fsync, then rename.
- [ ] Validate with `ffprobe -v error -show_streams -show_format -of json`.
- [ ] Decode audio and require max volume above -35 dBFS plus at least 1.0 second of non-silent audio using a -50 dBFS silence threshold. Log measured values; reject silent/near-silent takes before ready.
- [ ] Extract the final decoded frame by decoding the final second through EOF and overwriting one PNG:

```bash
ffmpeg -y -sseof -1 -i take.mp4 -map 0:v:0 -fps_mode passthrough -update 1 frame.png
```

- [ ] Record the final decoded frame timestamp from ffprobe and validate PNG decode/dimensions.
- [ ] Upload frame PNG and return its exact URL.
- [ ] Preserve H3 audio unchanged. Copy validated raw media into ready storage atomically; do not remux, filter, replace, normalize, or pad it.
- [ ] Validate the ready copy retains the same video/audio stream fingerprints as raw H3 media.
- [ ] A failed media check never enters the ready queue.
- [ ] Do not port root `post.py`’s robot voice filtergraph.
- [ ] Run tests and commit.

---

### Task 11: Add the fal performer

**Files:**
- Create: `runtime-flight/runtime_flight/performer_fal.py`
- Create: `runtime-flight/tests/test_performer_fal.py`

**Produces:** `FalPerformer.start(TakeRequest) -> asyncio.Task[ReadyTake]`.

```python
@dataclass(frozen=True)
class TakeRequest:
    take: int
    speaker: Literal["BOT1", "BOT2"]
    line: str
    prompt: str
    anchor: Literal["hero", "chain"]
    image_url: str
    baseline_id: str

@dataclass(frozen=True)
class ReadyTake:
    take: int
    speaker: Literal["BOT1", "BOT2"]
    line: str
    clip_path: Path | None
    frame_path: Path | None
    frame_url: str | None
    anchor: Literal["hero", "chain"]
    request_id: str | None
    status: Literal["ready", "dropped_422", "failed", "unknown_submission"]
    reserved_cost_usd: Decimal
```

- [ ] `FalPerformer` is the sole reservation owner. Mock full lifecycle: reserve → submit → request ID → reconcile → download → validate → final frame → upload. The harness never creates or passes a reservation.
- [ ] Assert H3 arguments exactly:

```python
{
  "prompt": expected_prompt,
  "duration": 5,
  "resolution": "768P",
  "enable_safety_checker": True,
  "prompt_expansion_mode": "balanced",
  "image_url": exact_anchor_url
}
```

- [ ] Cache one uploaded hero URL per baseline.
- [ ] Reserve only inside `FalPerformer.start`, immediately before its single queue POST; do not copy root `run_live.py`’s harness-level `spend.check`.
- [ ] 422: mark dropped, keep reservation, no retry.
- [ ] Other/ambiguous failure: reconcile; never create an unreserved retry.
- [ ] Three consecutive terminal failures signal graceful flight stop.
- [ ] Run tests and commit.

---

### Task 12: Add tweet overlay and OBS-side watchdog

**Files:**
- Create: `runtime-flight/runtime_flight/overlay.py`
- Modify: `runtime-flight/runtime_flight/obs_setup.py`
- Create: `runtime-flight/overlay/index.html`
- Create: `runtime-flight/overlay/app.js`
- Create: `runtime-flight/overlay/style.css`
- Create: `runtime-flight/tests/test_overlay.py`

- [ ] Overlay renders author, exact tweet text, and optional timestamp using `textContent`, never source HTML.
- [ ] Serve state from a loopback HTTP origin with `Cache-Control: no-store`; state writes are atomic and size-limited.
- [ ] Extend `setup-obs` to add a `WATCHDOG` browser source above host video in every scene.
- [ ] Heartbeat state is `{"sequence": integer, "healthy": boolean}` and updates at least twice per second. The state server adds `age_ms`, calculated from its own monotonic clock, to each response.
- [ ] Set `healthy: false` immediately when OBS command/media control fails, before reconnecting.
- [ ] Browser JavaScript tracks its own `performance.now()` time of the last successful response. If server-reported `age_ms` or browser receipt age exceeds 1,200ms, `healthy` is false, or the server is unreachable, watchdog becomes an opaque branded hold card and masks a host freeze.
- [ ] A fresh healthy heartbeat makes watchdog transparent.
- [ ] Test HTML escaping, no-cache headers, stale state, unhealthy state, server loss, recovery, and atomic state.
- [ ] Run JS and Python tests; commit.

---

### Task 13: Build the realtime state machine with fake boundaries

**Files:**
- Create: `runtime-flight/runtime_flight/harness_live.py`
- Create: `runtime-flight/tests/test_harness_live.py`
- Modify: `obs-harness/obs_harness/director.py`
- Modify: `obs-harness/tests/test_director.py`

Use `obs-harness/loop.py` as the state/reference model. Do not use root `run_live.py` or `playhead.py`; they have the wrong clock, player, speaker model, and failure behavior.

- [ ] Use fake monotonic clock, fake OBS, sequential Writer, and fake Performer; never sleep in tests.
- [ ] Test:
  - play current while next cooks;
  - one performer request max;
  - hero then exact chain URL;
  - late take uses card/hold;
  - cap prevents submit;
  - 422 invalidates dependent thoughts and reissues;
  - writer down and performer down stop safely;
  - no new submit after closing boundary;
  - baseline ID never changes.
- [ ] Simplify Director submit payload to exactly `take`, `line`, and `speaker`; remove rehearsal-only `anchor: stub`. The live harness owns anchor enrichment.
- [ ] Keep BOT1/BOT2 through Planner, Writer, Director, and logs. Map through `BaselineContext.host_map` only when calling `player.set_speaking`.
- [ ] Do not copy obs-harness test-script `host_a`/`host_b` speaker values into flight Writer tests.
- [ ] Wall-clock loop polls OBS no slower than 200ms.
- [ ] Compute `remaining_submit_slots = max(0, floor((target_duration_s - elapsed_s) / 5) - 1)` and pass only the derived Writer phase: `close` when the value is ≤2, `develop` after the opener, otherwise `open`. Writer never receives raw OBS timing.
- [ ] OBS media remaining owns host cut timing.
- [ ] Director is called only at clip edge or when ready media arrives during hold.
- [ ] Enrich schedule-only Director submit with anchor, prompt, and fixed H3 fields. `FalPerformer.start` creates exactly one reservation immediately before its one queue POST.
- [ ] Keep `segment.spend_policy = stop` once no reservation is available.
- [ ] Run pure state-machine tests and commit:

```bash
git add obs-harness runtime-flight
git commit -m "Add the realtime flight state machine"
```

---

### Task 13B: Integrate OBS lifecycle and stream safety

**Files:**
- Modify: `runtime-flight/runtime_flight/harness_live.py`
- Modify: `runtime-flight/runtime_flight/obs_session.py`
- Create: `runtime-flight/tests/test_harness_obs.py`

- [ ] Write tests for OBS disconnect across clip end activating an unhealthy watchdog.
- [ ] Write tests for OBS stream becoming active mid-flight: stop new paid submissions, enter hold, finalize logs/recording, and never stop that stream.
- [ ] Poll OBS stream status at least once per second and write every sample to events.
- [ ] Start recording only after immediately rechecking OBS is not streaming.
- [ ] At the 90-second programme boundary, enter hold and continue a controlled post-roll until OBS reports recording duration ≥90 seconds; then stop.
- [ ] Stop recording in `finally`.
- [ ] Run focused tests and commit:

```bash
git add runtime-flight
git commit -m "Integrate safe OBS lifecycle into live flight"
```

---

### Task 14: Write the evidence bundle

**Files:**
- Create: `runtime-flight/runtime_flight/evidence.py`
- Create: `runtime-flight/tests/test_evidence.py`

**Bundle:**

```text
out/flights/${FLIGHT_ID}/
  flight.json
  config.redacted.json
  baseline/manifest.json
  input/source_packet.json
  input/source_packet.lock.json
  input/dwarkesh-agent-civilizations.txt
  segment/package.json
  logs/takes.jsonl
  logs/events.jsonl
  logs/fal_requests.jsonl
  recording.json
  voice_review.json
  hashes.json
```

- [ ] Hash every evidence file.
- [ ] Wait for OBS recording to finalize and file size to remain stable across two one-second checks.
- [ ] Record scene intervals, watchdog-visible intervals, stream-status samples, request intervals, anchor URLs, source hashes, and redacted configuration.
- [ ] Scan actual configured secret values through every text artifact before finalizing hashes.
- [ ] Run evidence-writing tests and commit:

```bash
git add runtime-flight
git commit -m "Write immutable live flight evidence"
```

---

### Task 14B: Independently verify a completed flight

**Files:**
- Create: `runtime-flight/runtime_flight/verify.py`
- Create: `runtime-flight/tests/test_verify.py`

- [ ] Support two explicit modes: `--automated` verifies machine evidence before human review; `--final` additionally requires a complete `voice_review.json` and every required human score ≥3.
- [ ] Use ffprobe to verify recording duration ≥90s, dimensions, and audio/video streams.
- [ ] Use ffmpeg `blackdetect=d=0.2:pix_th=0.10`; any detected black interval of at least 0.2 seconds fails verification.
- [ ] Use `freezedetect=n=-50dB:d=1.0`; correlate detected intervals with logged scene and watchdog-visible intervals. Freeze >1s fails only when a host layout was exposed. Watchdog, hold, and card intervals count as covered programme.
- [ ] Verify at least 10 aired clips, both hosts, exact chain URL, no fal overlap, no hold/card interval longer than 15 seconds, cap, baseline ID, and request ledger.
- [ ] Report `reserved_cost_upper_bound_usd`, not provider-billed cost. Record confirmed rate, rate effective date, duration, and every reservation calculation. If fal exposes a billing receipt, store it separately without making the flight depend on it.
- [ ] Reserve `voice_review.json` for human scores: per-host consistency, between-host distinction, intelligibility, dialogue fidelity, and voice/gesture alignment. `--final` requires the file after human review; `--automated` does not require or fabricate it.
- [ ] Scan actual configured secret values through every text artifact.
- [ ] Run verifier tests and commit:

```bash
git add runtime-flight
git commit -m "Add independent flight evidence verification"
```

---

### Task 15: Complete the safe operator CLI

**Files:**
- Modify: `runtime-flight/runtime_flight/__main__.py`
- Create: `runtime-flight/README.md`
- Create: `runtime-flight/rundowns/one_tweet_90s.yaml`
- Create: `runtime-flight/tests/test_cli.py`

**Commands:**

- `check`
- `setup-obs`
- `rehearse`
- `smoke`
- `live`
- `replay`
- `verify-flight`

- [ ] CLI tests:
  - paid flag absent;
  - cap confirmation mismatch;
  - source not reviewed;
  - OBS already streaming;
  - text request limit;
  - smoke submission-attempt limit;
  - signal/panic cleanup;
  - replay performs no network calls.
- [ ] Wire commands to the already-built services; no command contains orchestration logic.
- [ ] Run CLI tests and commit:

```bash
git add runtime-flight
git commit -m "Add safe live flight operator commands"
```

---

### Task 15B: Prove the zero-cost full integration

**Files:**
- Create: `runtime-flight/tests/test_integration.py`

- [ ] Full zero-cost test uses:
  - real locked Pack Manager fixture;
  - real 1344×768 PNG;
  - fake text and fal gateways;
  - real ffmpeg/ffprobe fixture MP4;
  - fake OBS and fake monotonic clock;
  - complete evidence verification.
- [ ] Add an isolation test that AST-scans `runtime-flight` and rejects imports of root modules named `writer`, `post`, `spend`, `generator`, `playhead`, `run_live`, and `studio`.
- [ ] Root `experiments/` do not count as tests. Do not port their implicit retry or “retry overhead” acceptance rules.
- [ ] Install in a new venv and run:

```bash
cd pack-manager && python3 -m pytest -q -W error
cd ../obs-harness && python3 -m pytest -q -W error
cd ../runtime-flight && python3 -m pytest -q -W error
node --check overlay/app.js
python3 -m compileall -q runtime_flight tests
git diff --check
```

- [ ] Commit:

```bash
git add runtime-flight pack-manager obs-harness
git commit -m "Verify the complete zero-cost flight path"
```

---

### Task 16: Run the two-submission paid smoke

**Human-gated; do not run unattended.**

- [ ] Confirm Task 0 exact text and hashes.
- [ ] Approve and lock a real v2 baseline with a 1344×768 hero.
- [ ] Run `setup-obs`, verify split crop sync, set local recording, and confirm OBS is not streaming.
- [ ] Run non-video checks:

```bash
python3 -m runtime_flight check --config config.local.yaml
python3 -m runtime_flight check --config config.local.yaml --probe-text --confirm-text-requests 1
```

- [ ] Explicitly approve at most two fal submission attempts:

```bash
RUNTIME_ALLOW_PAID=1 \
RUNTIME_SPEND_CAP_USD=2.00 \
python3 -m runtime_flight smoke \
  --config config.local.yaml \
  --confirm-spend 2.00 \
  --max-fal-submissions 2
```

- [ ] Pass only if:
  - exactly two or fewer request reservations exist;
  - every submission has one reservation and request ID or explicit unknown-submission state;
  - no submission used `fal_client.submit_async`;
  - both returned clips validate;
  - take 1 uses hero;
  - take 2 uses take 1’s exact frame URL;
  - OBS records both;
  - `reserved_cost_upper_bound_usd` ≤$2;
  - evidence verifies.

- [ ] Stop and fix before full flight if any check fails.

---

### Task 17: Run the 90-second Dwarkesh segment

**Human-gated; do not run unattended.**

- [ ] Confirm:
  - exact selected post text;
  - reviewed article excerpt;
  - locked v2 baseline ID;
  - text provider/model;
  - OBS recording configured;
  - OBS stream inactive;
  - 768P rate;
  - reserved-cost cap ≤$12;
  - panic command.

- [ ] Start:

```bash
RUNTIME_ALLOW_PAID=1 \
RUNTIME_SPEND_CAP_USD=12.00 \
python3 -m runtime_flight live \
  --config config.local.yaml \
  --confirm-spend 12.00 \
  --max-text-requests 24
```

- [ ] Do not rescue normal late takes. Let card/hold behavior prove itself. Panic only for black video, unsafe content, wrong baseline, active public stream, or runaway requests.
- [ ] Run automated verification:

```bash
python3 -m runtime_flight verify-flight --automated --latest --out out/flights
```

- [ ] Human-score composition, speaker attribution, BOT1 voice consistency, BOT2 voice consistency, between-host voice distinction, intelligibility, dialogue fidelity, voice/gesture alignment, listener behavior, visual identity, set persistence, re-anchor quality, source grounding, and hold quality from 1–5.
- [ ] If either voice-consistency score, distinction, intelligibility, dialogue fidelity, or voice/gesture alignment is below 3, mark native H3 voice as failed and open the TTS-first follow-up; do not silently mix voice paths inside this flight.
- [ ] Save `voice_review.json`, then run:

```bash
python3 -m runtime_flight verify-flight --final --latest --out out/flights
```

- [ ] Flight passes only when both verification modes pass and no human score is below 3.

---

## Delegation

Tasks 1–15 are implementation tasks suitable for a Cursor coding model after this plan is approved. Use one task at a time, test-first, with an independent review after each task.

Task 0 needs the operator’s exact X text. Tasks 16–17 require explicit human approval because they submit paid jobs and control OBS.

The Orchestrator chat is intentionally excluded. After this flight path works, chat can select a locked baseline, help author the source packet/rundown, invoke `check`, and request `smoke` or `live`. It must not replace the deterministic Director, spend meter, OBS stream guard, or wall-clock loop.
