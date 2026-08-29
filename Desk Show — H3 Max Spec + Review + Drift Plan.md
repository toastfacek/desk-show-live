# Live Original-Character Desk Show — Spec \+ Review

**Stack:** fal MiniMax H3 Max · **Date:** 29 Aug 2026 · **Spec:** Forge/Notion · **Review \+ drift plan:** Claude

---

## Part 1 — Build spec (from Notion, 29 Aug 2026\)

### Objective

A live desk show: two original animated hosts, each a short talking-head clip, composited over a static set with a tweet ticker. A text model writes the lines a beat ahead. fal MiniMax H3 Max performs them. No cloned IP.

### Context

- Spark: Rehan Sheikh's infinite-cable stream (Minimax hooked to Twitch, then banned on Twitch and Kick for DMCA / Rick and Morty)  
- Product: fal MiniMax H3 Max (fal's faster cut of open-weight MiniMax H3, not MiniMax's own H3 endpoint)  
- Text-to-video API: `minimax/h3-max/text-to-video`  
- Image-to-video API (first frame \+ optional last frame): `minimax/h3-max/image-to-video`  
- Official MiniMax H3 (slower, has character reference) is not the live path  
- Conversation with Jesse, 29 Aug 2026: original characters, green-screen hosts on a static background, tweets as a ticker, each turn is its own 5s clip, text chat runs a line or two ahead of video

### Acceptance criteria

- Product split written: what H3 Max can do vs official H3 vs what we build  
- Cost model for 1 hour of continuous 768p (and 480p) at promo and list rates  
- Engineering architecture written, with a first-build slice Forge can ship ✔  
- Out of scope explicit (no IP clones, no true real-time overlapping conversation, no 30s single clips)  
- Jesse can read this page and know whether a weekend prototype is worth it

### Out of scope

Cloning Rick and Morty, TBPN hosts, or anyone else's likeness. Independent characters that actually hear each other inside the video model. 30-second single generations (H3 Max maxes at 15s). Official MiniMax H3 as the live path (too slow). Ads / monetization (later).

### What we are building (product)

A desk show, not a generated world. Static background. Tweet feed is an overlay (HTML or OBS). Two original hosts as separate talking-head clips laid on top. One text model writes the conversation. H3 Max only performs a line it is given. Hosts take turns. While clip A plays, we write and generate B.

True real-time reaction is not feasible on this stack. Feasible version: about a 5–10 second lag, one camera, turn-taking.

### fal H3 Max facts (as of 29 Aug 2026\)

- H3 Max is fal's post-train of open MiniMax H3 (Artificial Analysis lists it as MiniMax H3 Turbo, 768p)  
- Two endpoints at launch: text-to-video, and image-to-video with optional `image_url` (first frame) and `end_image_url` (last frame) — the persist trick: last frame of clip N becomes first frame of clip N+1  
- Reference-to-video (pin a character still / voice) NOT at launch; fal said "later this week" as of 25 Aug 2026\. Until then, faces drift clip to clip. Official H3 has reference-to-video (up to 9 images, 3 videos, 3 audio) but is \~35× slower  
- Duration 5–15s (default 5). Resolution 480p or 768p (16:9 768p \= 1344×768, 24 fps). No 2K  
- Sound generated in the same pass (lip sync included); cuts at clip boundaries  
- Full-clip generation, not streamed frames. 5s @ 768p renders in \~2.5–3s (`timings.inference`). 15s clip takes \~15s — no buffer  
- `prompt_expansion_mode`: use `balanced` (\~1s). `quality` can spend \~30s and stalls a live show  
- `fal.subscribe(...)` with `Authorization: Key $FAL_KEY`. Queue \+ download \+ mux on top of denoise. Safety checker on by default  
- fal says API output usable commercially (check terms). Safety checker and MiniMax policy still block IP / sensitive content

### Cost (H3 Max, published on fal 26–29 Aug 2026\)

Billed per second of output video. Promo (50% off, ends 1 Sep 2026): 480p $0.025/s, 768p $0.04/s. List: 480p $0.05/s, 768p $0.08/s.

One host talking at a time (60s of generated video per minute of show):

| Tier | Per 5s take | Per minute | Per hour |
| :---- | :---- | :---- | :---- |
| 768p promo | $0.20 | $2.40 | $144 |
| 768p list | $0.40 | $4.80 | $288 |
| 480p promo | $0.125 | $1.50 | $90 |
| 480p list | $0.25 | $3.00 | $180 |

15s 768p clip: $0.60 promo / $1.20 list. Both hosts generating at once: double it. Budget 1.5–2× for a messy live run (retries, failed takes). Text-model cost is noise next to this. Five free 5s 768p gens/day unsigned — not enough to run a show. Official H3 is a different bill; don't mix its numbers into the live-show hour.

### Pipeline

1. Tweet (or a writer beat) lands  
2. Text model writes `Alex says: …`  
3. H3 Max image-to-video: prompt includes the line, `image_url` \= Alex's last frame or locked still, duration 5, 768p, `prompt_expansion_mode=balanced`  
4. Download mp4, cut host from background, lay over static set \+ ticker in OBS (or web compositor)  
5. While Alex plays (\~5s), write Jordan's reply and generate Jordan the same way  
6. Jordan ready before Alex ends → hard cut. If not → freeze last frame or blink loop

The line passes as **text** to the next turn, never the video (the model outputs no transcript).

### Engineering architecture (Forge, 29 Aug 2026\)

A **clip queue with a playhead**, not a stream. Only the line-as-text plus that host's last-frame JPEG carries forward.

**Loop (one host):** writer locks line N (N+1 already drafting) → submit image-to-video (5s, 768p, balanced, `image_url` \= host's last frame; hero still for clip 0\) → on success: download mp4 → ffmpeg last frame → push mp4 to ready queue (depth 1\) → playhead pops next clip; generation of the following clip started at submit time → queue empty at the cut \= hold (freeze frame \+ silence); writer never waits on video.

**Timing:** target 1 clip ready \+ 1 generating. Never 15s takes on the live path. Cold start: pre-bake one 5s idle take so the first wait is off-air.

**Last-frame chain:** ffmpeg last frame → public URL → `image_url` for N+1. Clip 0 \= locked still. Extract fail → hero still fallback (accept a jump), never stall.

**Cutout:** v1 none — full-frame talking head in a PiP window over a static set JPEG (desk-monitor look). v2 rank: (1) generate against a known solid backdrop and chroma-key, (2) rembg post (hair flicker), (3) wait for better mattes. Don't prompt "green screen" and hope.

**Audio seams:** v1 hard cut; lines end on a period; optional 100–200ms tail trim; no crossfade.

**Dead air / retries:** hold asset \= last-frame JPEG or one looping 5s "listening" take. Safety 422 → drop take, writer reissues shorter line, play hold. `FAL_KEY` on the box only.

**Compositor (first slice):** ffmpeg concat of ready folder, or OBS watching the folder \+ static JPEG set. No ticker, no second host. Box prototype, not a deployed product.

**Identity:** v1 accepts face drift (prompt \+ last-frame only) until fal ships reference-to-video.

### First-build slice (confirmed)

One host, 5s, 768p, last-frame chain, static JPEG, no tweets, no cutout. Full-frame talking head in a window. Prove play-while-generating and dollar-per-minute. Then second host \+ ticker.

**Done when:** 60s plays without a stall; hold-pattern fires at least once on purpose; last-frame chain visible across 8+ takes; real $/min known including retries.

### Open questions for Jesse

- Forge locked: one host, accept face-drift, box prototype. Override if wanted.  
- Whose Twitter feed is the prompt (Jesse's? a list? pasted?) — needed before a ticker, not in first slice.

---

## Part 2 — Review notes (Claude, 29 Aug 2026\)

**Verdict: the weekend prototype is worth it.** The first slice costs maybe $10–20 in generation and answers the questions that decide the project. The architecture is right — a clip queue with a playhead, not a stream — and the first slice is scoped with real done-criteria. But the spec watches the wrong risk.

**1\. Voice drift is the make-or-break, not face drift.** The last-frame chain anchors the picture, but audio is generated fresh every clip with no reference — the host's voice will shift timbre, accent, and energy take-to-take, and inconsistent voice is far more jarring than a slowly morphing face. Nothing in the stack fixes this until fal ships reference-to-video with audio refs. Add to done-criteria: **voice holds recognizably across 8+ takes.** If it fails, the show doesn't work on raw H3 Max audio, and that should be learned on day one. (See Part 3 for mitigations.)

**2\. Test verbatim line delivery on day one.** The whole design assumes H3 Max performs the exact dialogue it's given. Video models routinely paraphrase, garble, or drop scripted lines. If delivery is only approximate, the writer model is scripting a show the hosts aren't performing, and turn-taking coherence quietly falls apart.

**3\. Free face-drift fix the spec misses: re-anchor at cutaways.** Every cut to Jordan is a chance to reset Alex to the hero still — a jump in appearance across a cutaway is invisible (this is how real TV editing hides discontinuity). Drift then never compounds beyond one host's consecutive run. The alternative — chaining last frames for an hour, \~720 takes with a JPEG re-encode each cycle — will absolutely morph the character.

**4\. Timing margins are thinner than stated.** The real loop is queue \+ denoise \+ download \+ ffmpeg extract \+ upload frame to a public URL \+ resubmit; that round trip can eat most of a 5s window. A depth-1 ready queue means one slow generation triggers the hold pattern. Run the writer two beats ahead and accept a 10–15s tweet lag — nobody watching will notice.

**5\. Tweets are adversarial input.** Once tweets drive prompts, people will deliberately bait the safety checker (and attempt prompt injection through the ticker). Live-path 422 rates will be much higher than in testing; drop-and-reissue is the right design, but budget for it.

**6\. Cost honesty: prototype cheap, streaming not.** At list rates with the 1.5–2× retry multiplier, an hour of 768p runs $430–580; an infinite stream is a \~$10k/day habit. The eventual product is more likely scheduled episodes or short daily live blocks than 24/7 cable. The 50% promo ends 1 Sep — prototyping this weekend literally halves the bill.

Forge's locked defaults (one host, box prototype, accept drift in v1) are the right calls.

---

## Part 3 — Drift mitigation plan (Claude, 29 Aug 2026\)

### Voice drift — ranked mitigations

**V1 (ship this weekend): fixed audio effect chain — the "robot voice," done practically.** Pipe every take's audio through one unchanging ffmpeg filtergraph — pitch-lock plus a ring-modulator or vocoder flavor (the classic Dalek/computer treatment). The effect becomes the character's voice signature, and drift in the underlying generated timbre hides beneath it. Near-zero latency, one ffmpeg step you're already in for the last-frame extract. Pair it with prompting a narrow target ("flat robotic monotone, mid-pitch") — drift inside "robot monotone" is much less perceptible than drift inside "warm charismatic anchor." So yes to the prepackaged-computer-voice instinct — but as a post-processing signature on H3's own audio first, because it keeps lip sync free.

**Fallback (if H3 garbles lines or voice still wanders): TTS-first with an occluded mouth.** Discard H3's audio entirely. Generate the line with a deterministic TTS voice (a fixed stock voice — modern neural, or deliberately retro DECtalk/eSpeak if that's the bit), then generate the video to match. This buys two things at once: perfect voice consistency forever, and guaranteed verbatim delivery — the script risk in Part 2 disappears. The price is lip sync, so it only works if the character's design makes lip sync irrelevant: an LED-waveform mouth, a faceplate or visor, a helmeted host, a puppet-style rigid jaw. Bonus: TTS-first tells you the exact audio duration before you submit the video job, which tightens the clip-length math. Check the TTS license covers streaming/broadcast; avoid any voice marketed as a soundalike of a real person.

**V2: fal reference-to-video with audio refs**, the moment it ships. That's the real fix; everything above is bridge.

### Face drift — ranked mitigations

1. **Re-anchor at every cutaway** (Part 2, point 3). Cap any host's consecutive chained run at \~4–6 takes even in a one-host test, with a forced reset to the hero still.  
2. **Design for drift tolerance.** Photoreal human faces show drift worst — thousands of free parameters viewers are hardwired to track. A character with a strong silhouette and few facial degrees of freedom (chrome robot head, helmet \+ visor, cartoon mascot, heavy glasses) drifts far less visibly, and drift that does happen reads as animation style. This converges with the voice plan: **make at least one host a robot and both drift problems become canon-compatible.** A glitchy android host whose face subtly shifts is diegetic — a bit, not a bug.  
3. **PNG, not JPEG, in the last-frame chain** — recompression compounds across takes.  
4. **Bake anchors offline with official H3.** Slow is fine off-air: use official H3's character reference to generate the hero stills, idle loops, and hold assets so the fixed points the live chain keeps returning to are themselves consistent.

### Public-domain persona? Recommend against.

Tempting (instant recognizability, arguably legal), but it fails on four fronts. Platform risk: Twitch/Kick DMCA enforcement doesn't adjudicate public-domain nuance — the Rehan ban is the proof — and PD status is a landmine field anyway (Steamboat Willie Mickey is PD as a work while Disney's trademarks live on; same story with Popeye). Safety-checker risk: fal/MiniMax filters block by recognition, not legal analysis, so a recognizable persona raises live-path 422 rates — which is the dead-air budget. Voice risk: a PD text has no PD voice; the recognizable voices attached to these characters belong to actors and estates (personality rights). Brand: original characters are the moat — a PD skin makes the show a novelty about the reference. The safe middle path is **archetype, not persona**: an original noir detective, an original vampire-count-turned-pundit — archetypes are free, specific depictions aren't.

### Recommended v1 identity package

One original robot-designed host (drift-tolerant face, occluded or stylized mouth). H3 Max's own audio through a fixed ffmpeg effect chain as the voice signature. Hero still and hold assets baked offline with official H3 character reference. Re-anchor to the hero still at every reset, PNG chain, max 4–6 chained takes. Day-one tests: verbatim line delivery, and voice recognizability across 8+ takes. If verbatim delivery fails, switch to TTS-first with the waveform mouth. Reference-to-video adoption is v2 the week fal ships it.  
