# Desk Show — Embodied Agent Podcast

**Status:** Plan for review · **Date:** 2 Sep 2026 · **Owner:** Jesse  
**Trigger:** fal as live performer looks like a dead end; simulate the hosts as chat agents and put them on a livestream instead.

This is a plan, not a build. It does not delete the H3 flight code. It answers: **is the live show two agents with faces, or a video model acting out a script?**

Parent docs this sits on:

- `Agentic Live Streaming Harness — Plan.md` — two bosses (producer owns jobs, harness owns time). Still in force.
- `Desk Show — Two-Host Architecture & Harness.md` — wells, layouts, 1080 furniture. The *frame* stays. The *host source kind* changes.
- `runtime-flight/runtime_flight/discuss.py` — two HostMinds, last-line only, already “no script, no fal.”
- `research/findings/dialogue-and-character.md` — why last-line + job beats a scripted pair.

Repo review source: [ChatGPT share 6a98817d](https://chatgpt.com/share/6a98817d-a834-83ea-b340-dcfce9cb3ae5) (embodied realtime agents: Open-LLM-VTuber, Spline, TalkingHead, Tavus / Anam / HeyGen / D-ID).

---

## 1. Verdict

**Yes. Kill fal on the live path.** Keep it as an offline art tool if we want hero stills or bumpers later. Do not keep it as the camera.

The show we actually want is already half-built:

1. Two HostMinds talk to each other about a card (`discuss.py`).
2. A producer maps the room. A harness owns the clock.
3. OBS + HTML furniture make it look like television.
4. The missing piece is a **face** — a live UI that performs thinking, tool use, listening, and speech — plus a **voice** that is not welded to a 5-second mp4.

That is more durable than “generate a video of an agent convo” for one structural reason: **the conversation is real. The picture is an expression of it.** We can change the face, the voice, the tools, the memory, the well layout, without re-rolling identity through a last-frame chain.

“Podcast” here means the **conversational form**: two agents, live, with tools, talking to each other. It does **not** mean we abandon the desk and ship a Zoom grid. The frame stays a desk show. A language model that treats 90 seconds as a magazine essay already sounds like a podcast someone forgot to stop (`research/findings/talk-show-segment-lifecycle.md`). HostMind’s last-line / job / 220-character contract is the vaccine. Do not throw it away when we add tools.

---

## 2. Why fal is a dead end for *this* show

H3 Max is a clip, not a camera. The whole live machine was built around that fact (`Agentic Live Streaming Harness` §2.3). That fact does not get nicer with more prompt engineering.

| Constraint | What it does to the show |
| :---- | :---- |
| Picture + speech welded in one file | Cannot talk over a card without paying for hidden pixels. Cannot cut mid-thought. TTS was already the reserved escape (`Two-Host` §1). |
| Last-frame chain | Take N+1 cannot start until N finishes, downloads, and yields a PNG. Extra agents cannot cook faster. Identity is a serial file path. |
| 5-second clip as the unit of time | The camera writes the script. HostMind was invented specifically so a thought is not “fill five seconds.” |
| $2.40–$4.80 / min of host talk | Every graphics beat is a discount. Waste (cooked, never aired) is the only way past the ceiling. |
| Safety 422 | Same prompt cannot retry. Writer must reissue shorter and blander. The show gets timid when the model gets scared. |
| Drift | Faces and voices walk. Critics exist because the performer forgets who it is. |

The first paid OBS flight (`runtime-flight/LIVE_FLIGHT_CHECK.md`) already spent most of its learning on **decode, remux, crop, and silence** — not on whether the hosts were good. Ten submissions, $4 reserved, two fal failures, Writer stuck on BOT1. That is a lot of machine for eight takes of one voice.

The product we said we sell (`Harness` §17.1) is: live input mutates the **rundown**. Infinite TV / fal’s own live bot mutates **pixels**. Using H3 as the hosts trains us toward the product we said we would not sell. Hosts that melt are a branding problem, not a feature.

---

## 3. The machine: brain ≠ voice ≠ body

This is the architecture in the ChatGPT share, restated in Desk Show nouns.

```
          PRODUCER  (slow loop: topic, pace, package)
                │
                ▼
     ┌──── HOSTMIND A ────┐         ┌──── HOSTMIND B ────┐
     │ soul, job, memory  │◄─line──►│ soul, job, memory  │
     │ tools, coverage    │         │ tools, coverage    │
     └─────────┬──────────┘         └─────────┬──────────┘
               │                              │
     speech / emotion / action / tool-state   │
               │                              │
               ▼                              ▼
            TTS A                          TTS B
               │                              │
               ▼                              ▼
         FACE A (well)                   FACE B (well)
               │                              │
               └──────────┬───────────────────┘
                          ▼
              HARNESS + OBS + 1080 FURNITURE
                    (clock, layouts, card, chyron)
```

Three channels, never merged:

| Channel | Who owns it | What it is | What it is not |
| :---- | :---- | :---- | :---- |
| **Brain** | HostMind (+ producer / topic map) | Next move, tools, memory, `reply_to` | Frames, phonemes, layouts |
| **Voice** | TTS / realtime audio | Speech, amplitude, optional visemes | Identity pictures |
| **Body** | Face runtime in the host well | Emotion, gaze, idle, thinking, tool chrome | A second LLM |

The LLM **does not animate frames**. It emits a line plus a small performance object. Audio independently drives the mouth (or a waveform, or a CRT glow). The face can react *before* the sentence finishes: thinking starts when the tool is called, not when TTS starts.

That is the long-term control we do not have with H3. A new emote, a new tool, a new well layout is a renderer change. It is not a new last-frame chain.

---

## 4. What we already have (do not rebuild)

`discuss.py` line 1 is the tell: **“Two host minds. Each turn answers the last line. No script, no fal.”**

HostMind already is the chat agent, with the constraints that make two-host talk feel like a desk instead of a meeting:

- Last-line obligation (`reply_to`)
- Named moves (`frame / poke / number / reframe / callback / question / broaden / land`)
- Complementary jobs (BOT1 = thesis/weather, BOT2 = number/stake)
- Coverage that refuses to close after one bounce
- Soul / stance / opinions on the voice, planner (topic map) ≠ speaker
- 220-character spoken line

The overlay, wells, layouts, and producer package already assume **hosts are one layer and CG is another computer**. Fal was occupying the host wells because it was the only picture we knew how to buy. The wells do not care. A browser source with a face is a **live / graphic** source in the §17.4 taxonomy. Hold becomes “the other host is thinking,” not “the clip is late.”

Character Packs stay. They stop being fal prompt sheets and become:

- standing visual identity for the face runtime
- TTS voice IDs / direction
- soul text HostMind already loads

---

## 5. Performance contract

Add this next to the spoken line. Do not let it become a second script.

```json
{
  "speaker": "BOT1",
  "text": "Fear has a ticker now, and it shrugs.",
  "move": "frame",
  "reply_to": null,
  "performance": {
    "emotion": "skeptical",
    "energy": 0.6,
    "gaze": "other_host",
    "gesture": "shrug",
    "thinking": false
  },
  "tool": null
}
```

While a tool is running, the host does not have to speak. The face does:

```json
{
  "speaker": "BOT2",
  "text": null,
  "performance": {
    "emotion": "focused",
    "energy": 0.4,
    "gaze": "card",
    "thinking": true
  },
  "tool": {
    "name": "search_memory",
    "label": "checking the last print"
  }
}
```

Rules:

1. `performance` is a closed enum. The model picks among faces we actually built. No free-text stage directions.
2. Mouth / glow / waveform follows **audio**, not the model.
3. Tool chrome is deterministic. The agent names the tool; the face draws the state we already designed.
4. The listening host still performs. Idle is a state, not a freeze.
5. The director / harness still picks the layout. A shrug is not a cut.

This is the same permission wall as the conductor brief: the speaker does not pick the shot. The face does not write the line.

---

## 6. Tools, memory, “real agents”

Yes — this is the product upgrade, not a garnish.

A HostMind that can only recite the card is a writer with extra steps. A HostMind that can search, fetch a number, open a memory, or refuse a fact it does not have is a **guest who works here**.

Keep the planner ≠ speaker split. Tools are how the speaker *grounds*. They are not how the speaker becomes the producer.

v1 tool set (small on purpose):

| Tool | Who | Why it is on air |
| :---- | :---- | :---- |
| `lookup_fact` | Either host | Number/stake without inventing |
| `search_memory` | Either host | Callbacks that are true |
| `read_card_media` | Either host | Image / chart on the centre well |
| `pass` | Listening host | “I have nothing grounded” — face stays idle |

Do not give either host `set_headline`, `set_layout`, or `skip_segment`. Those stay producer / harness. An agent that can cut the show will cut the show.

Thinking time is now a **beat we can show**, not a stall we have to hide. That is the visual we could never buy from H3: the host looks up, the well shows a search, the other host waits, then the number lands.

---

## 7. Repo / product review (from the share)

Study these. Do not adopt a second brain.

### Steal the contract

**[Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber)** (~13.6k stars). Closest conceptual match: continuous voice, interruption, expressions the agent chooses, tool calling (they even ship `mcp_servers.json`), persistent chat, Live2D as a face over a real LLM. The steal is **agent state → `{speech, emotion, action}` → renderer**. The risk is the rest of the product: it is a companion / VTuber desktop, Live2D-licensed, one character talking to a user. We are two hosts talking to each other on a desk. Do not import the app. Import the performance bus.

**[met4citizen/TalkingHead](https://github.com/met4citizen/TalkingHead)**. Browser Three.js / VRM kit: lipsync from a `MediaStream`, expressions, gestures, OpenAI Realtime examples. Useful if we ever want a 3D body. For v1 it is heavier than a well that only needs eyes, mouth, and a thinking state. Audio-driven mouth + semantic face is the clean split.

**Spline Voice Assistant.** Beautiful body. Dangerous brain. Spline’s assistant is its own Realtime session, own instructions, own tools. Two brains drift. Use Spline (or Rive) as a **scene we drive with variables** (`speaking`, `emotion`, `thinking`, `voiceLevel`). Do not let Spline own HostMind. Fine as a one-evening prototype of “does this character feel alive,” then rip the brain out.

### Plumbing, not taste

The share cites **hikaneko/ai-avatar** as mic → LiveKit → VAD → Whisper → LLM → TTS → TalkingHead → canvas capture. I could not find that exact repo. The pattern is still right: someone has to own WebRTC / VAD / barge-in. We do not need that for two agents talking to *each other* in v1. There is no guest mic until we invite a human. Skip LiveKit until a live well is a person.

### Do not use as the Desk Show face

**Tavus, Anam, HeyGen LiveAvatar, D-ID, Beyond Presence.** These are “FaceTime with a synthetic employee.” Avatar-only modes (your agent, your TTS, their renderer) are architecturally clean and still the wrong aesthetic. Photoreal / anime receptionists push us toward Infinite TV with a different invoice. Anam’s stylization is the least-wrong of the set and still a vendor face we do not control.

**HeyGen / fal H3 as “just the mouth.”** That is the current dead end with a new sticker.

---

## 8. Visual direction

Three bodies, one brain. Ranked for *this* show:

| | Direction | When |
| :---- | :---- | :---- |
| **C. Living UI (ship this)** | Broderick / ROAM geometry: primitive body, two pill eyes, **no mouth**. Talk is squash-stretch + eye pulse. Rive / SVG / CSS. | First face. Cute, fast, no visemes. Mock: `research/mocks/grokbots.html`. |
| **A. Live2D** | Illustrated host, Open-LLM-VTuber-style expression API. | If C feels too abstract and we have art. License is a real cost (`LICENSE-Live2D.md` on that repo). |
| **B. Stylized 3D / VRM** | TalkingHead, body language, props. | Later, if a well needs shoulders. Not the first proof. |

C is now locked to a specific steal, not a vibe board.

**Reference:** [Jeff Broderick, 1 Sep 2026](https://x.com/brdrck/status/2094896591144403001) — “cute little animated vector characters,” Opacity → Zoah. The tape is a vector editor constructing **ROAM** as four mouthless creatures. The one we want is the **O**: a sphere with two vertical pill eyes. The M is twin capsules. Construction lines and anchors are part of the charm. There is no official SDK. Do not ship their wordmark or their files.

**Talk without a mouth:** squash the whole body at speech rate, pulse the pills, blink, tilt. Amplitude can drive squash depth. No jaw, no visemes, no waveform teeth. That is faster than lip sync and reads as cartoon, not broken anatomy.

**Closest reusable code, ranked:**

| Thing | Use |
| :---- | :---- |
| `research/mocks/grokbots.html` | Ours. Two hosts, `talking` / `listening` / `thinking` / `laugh`, click-to-talk. |
| [FluxGarage/RoboEyes](https://github.com/FluxGarage/RoboEyes) | Steal the **eye-mood API** (blink, idle look, laugh-shake, curious). Arduino/OLED, not a renderer we embed. |
| [tanmaywankar/Grobot_Animations](https://github.com/tanmaywankar/Grobot_Animations) | Same idea, plus a web mood tinkerer. |
| [Eyuvaraj/Interactive-Avatar-Rive](https://github.com/Eyuvaraj/Interactive-Avatar-Rive) | The `isTalking` boolean → Rive input. Drop their lip-sync art; keep the wiring. |
| [metafizzy/zdog](https://github.com/metafizzy/zdog) | If the sphere needs a real equator / 3D turn. Cute, designer-friendly, still no mouth. |
| Rive community mascots | Production path once a designer rigs PHASEONE + deb to the same inputs. |

The locked hosts stay PHASEONE[lol] (amber pills on a charcoal sphere, left) and deb (teal pills on a cream capsule, right). Furniture still draws names, chyron, card, LIVE, clock. The face plate has no type.

---

## 9. Keep / kill / add

### Keep

- Harness owns time. Producer owns jobs.
- OBS (or a later `Player`) as switcher. Customer still does not operate it.
- 1080 furniture, overlay schema, `split` / `wide` / `solo_*` / `card_full`.
- HostMind last-line contract, moves, complementary jobs, coverage.
- Topic map as planner. Speaker does not rewrite the plan.
- Character Packs as identity (visual + voice + soul), not as H3 prompt bags.
- Source / well / layout / hold types (`Harness` §17.4). Hosts become live/graphic wells. Hold remains for “brain late,” not “clip late.”
- Rehearse / live / replay. Rehearse is now fake TTS + fake tools, $0.

### Kill (live path)

- fal / H3 as the host performer.
- Last-frame chain as identity.
- 5-second clip as the unit of talk.
- H3-welded programme audio.
- Cook/play overlap as the main timing trick.
- Spend cap as the thing that decides whether a host may speak. (TTS spend is real; it is not $4.80/min.)
- One writer scripting both hosts *on air*. HostMind already replaced that. Do not bring the script back to “help” the agents.

### Add

- `performance` object on each turn (closed enum).
- Face runtime: one browser source per host well, or one page with two faces.
- TTS adapter (provider-agnostic; Character Pack holds voice IDs).
- Tiny tool set (§6) with on-air chrome.
- A listening state that is acted, not frozen.

### Leave on the shelf

- Human guest mic / LiveKit / NDI. Same rule as before: add when a well is a person.
- Chat writes the rundown. Showing chat is cheap. Letting it write is still adversarial.
- Photoreal avatars.
- A second HostMind brain inside Spline / Live2D / any renderer.

---

## 10. What “podcast” must not break

The research already named the failure mode. Two unconstrained chat agents become a meeting: recap, fold, empty the well on turn two, agree because RLHF likes agree.

So the livestream is a podcast **only** in this sense: the hosts are live agents, they can think, they can use tools, the audience can watch that. It is still a **desk**:

- One shared object (the card).
- Two jobs that cannot be satisfied by the same sentence.
- Short turns. Last line is the allocation. No third host.
- Producer still ends the room. Agents do not filibuster because they have memory now.
- Thinking is visible and **bounded**. A tool that takes more than a breath becomes a card / hold, not dead air with a spinner we forgot to design.

If we let the agents free-chat “like a podcast,” we will have thrown away the only part of this repo that already works.

---

## 11. First proof (still no fal)

Prove aliveness before we decorate.

**P0 — ears.** Run `discuss` into a speaker: HostMind → TTS → two voices, no picture. If the tape is not a show, no face will save it.

**P1 — face in a well.** One living-UI host in the existing left well. Audio-reactive mouth. `thinking` / `speaking` / `idle`. Hard-code the performance enum from a fixture transcript. $0.

**P2 — two faces, one card.** Both wells. HostMind live. TTS live. Overlay furniture unchanged. Tools stubbed (`lookup_fact` returns package facts only). Record 90s. No OBS required if a browser compositor is faster; OBS is fine if the wells already exist.

**P3 — one real tool on air.** `search_memory` or `lookup_fact` against something not on the card. The well must show the search. The other host must listen. Then the number lands.

Stop if P0 is boring. Do not spend art on P2 until P0 holds. That is the same discipline as “rehearse before live,” with text+TTS instead of stub clips.

---

## 12. How this lands on the existing build

| Existing piece | After this plan |
| :---- | :---- |
| M0–M2 H3 picture tests | Historical. Useful as “we measured the clip path.” Not a gate for P0. |
| OBS harness / overlay / layouts | Keep. Host wells switch source kind. |
| Live Sockets (their text key + their fal key) | Text key stays. Fal key becomes optional / offline. A later socket is **their TTS key**. |
| Pack Manager | Packs gain `face` + `tts` and stop requiring a hero chain for live. |
| Paid H3 flight | Do not run another one to “see if identity holds.” That question is retired for the live path. |

The public-harness story gets cleaner: the runner still talks to a switcher, fills furniture, keeps a clock. The paid camera was the awkward part of the rental. A face runtime is just another source.

---

## 13. Open questions for review

Mark each agree / change / defer.

1. **Fal is off the live path.** Offline art only, if at all. Agree?
2. **HostMind stays the brain.** We add `performance` + a tiny tool set. We do not replace it with Open-LLM-VTuber or Spline’s assistant. Agree?
3. **Living UI is the first face** (direction C). Live2D / VRM later. Agree?
4. **“Podcast” is the agent form, not the visual form.** Desk frame stays. Agree?
5. **P0 is TTS-only tape** before any face art. Agree?
6. **No guest mic / LiveKit in the first proof.** Two agents only. Agree?
7. **Renderer has no LLM.** If we prototype in Spline Voice Assistant, we throw the brain away before it ships. Agree?

---

## 14. What “done” means for this plan

This plan is accepted when the answers to §13 are written down, and nobody is still treating H3 as the thing we have to make work before the hosts can talk.

It is **not** done when a Rive file exists. The next writing, if this is accepted, is a short TDD for P0 (HostMind → TTS → two-track tape) and a face-state schema the overlay can already consume.

The surprise, for us: we do not need a new show. We need to stop asking a video model to pretend to be the show we already wrote.
