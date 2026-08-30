# Desk Show — Conductor Layer Brief

**Status:** Requirements only, for decision · **Date:** 30 Aug 2026 · **Owner:** Jesse · **Author:** Chunq

**Parent docs (unchanged, still the contract):** "Desk Show — H3 Max Spec + Review + Drift Plan" and "Desk Show MVP — TDD (H3 Max, one robot host)". This document adds a layer on top of them. It does not replace them. Where I think one of them is wrong, I say so out loud in §3 and §12 and leave the original text alone.

**This is not a build plan.** No code, no schemas to implement, no milestones. It is the set of requirements and decisions the conductor layer has to satisfy, written so Jesse can read it and either approve, argue, or send it back.

---

## 1. Terms, defined once

Five words earn their keep in this document. Each is defined here and then used plainly.

- **Conductor** — the piece of software that decides, at each cut point, what the viewer sees next and how long they see it. It is a director sitting in front of a switcher. It never writes dialogue.
- **Switcher** — in a real broadcast truck, the box that chooses which camera goes to air. Here it is a software equivalent: it picks between the generated host window, a graphic, a pre-made clip, or a freeze.
- **Playhead** — the thing actually playing video right now, and the only source of truth about wall-clock time. It knows what is on air and when that clip ends.
- **Last-frame chain** — the trick that keeps the host looking like the same character: the final still frame of clip N is fed in as the first frame of clip N+1.
- **Beat** — one decision by the conductor: one layout, one source, one duration. A show is a sequence of beats. Most beats are a host clip; some are a graphic.

One more, borrowed from broadcast because there is no plainer word: a **rundown** is the ordered list of segments an episode is planned to contain, with time allotted to each.

---

## 2. The one-paragraph version

H3 Max is one camera, and it is a slow camera. It cannot be a show on its own, because the time it takes to make five seconds of host is roughly the same as the five seconds of host it makes — so a one-camera show has no slack and stalls the first time anything hiccups. The conductor is the fix, and the fix is not creative garnish: **the conductor's real job is to turn generation delay into deliberate pacing.** Three seconds of freeze looks broken. The same three seconds sitting on a tweet card with the music bed up looks like a show taking a beat. Everything else in this document follows from that one substitution.

---

## 3. A correction to the existing contract (please read this part)

The TDD, §4, says:

> "Generation of N+1 starts when N is **submitted**, not when it starts playing."

That is not achievable while the last-frame chain is in use, and the same claim appears in the spec's architecture section. Clip N+1's first frame *is* clip N's last frame. That frame does not exist until clip N has finished rendering, been downloaded, had its final frame extracted, and had that PNG uploaded somewhere H3 can fetch it. So the real sequence is strictly serial: submit N → N renders → N downloads → frame extracted and uploaded → *only now* may N+1 be submitted.

The overlap we actually get is the one Jesse stated: **play N while N+1 cooks.** Nothing earlier.

This matters because it changes the arithmetic, and the arithmetic is unfriendly. Call the time from submitting a take to having its last frame uploaded the **turnaround**. The TDD's own estimate of that path is 4.0–6.0 seconds (queue 0.5–1.0, render 2.5–3.0, download 0.5–1.0, extract-and-upload 0.5–1.0). The playback window is 5.0 seconds. Turnaround and window are the same size, which means the one-host chained loop runs at roughly 100% duty cycle with no room for a bad minute:

| Turnaround | Non-host seconds needed per cycle | Share of show that must be graphics | Cost per show-minute at promo 768p |
| :--- | :--- | :--- | :--- |
| 4.5s | 0 | 0% | $2.40 |
| 5.0s | 0 | 0% | $2.40 |
| 5.5s | 0.5s | 9% | $2.18 |
| 6.0s | 1.0s | 17% | $2.00 |
| 7.0s | 2.0s | 29% | $1.71 |

Two conclusions, both load-bearing:

**(a) Graphics beats are mandatory, not optional.** If measured turnaround lands above about 4.5s — and the TDD expects it to — then a one-host chained show *cannot* be gapless without non-host material in the mix. The conductor is not a v2 nicety. It is the thing that lets the 60-second test pass for a good reason rather than by luck.

**(b) With one window on air, the bill has a ceiling.** Only one generated clip is ever visible, so you can never bill more than 60 generated seconds per show-minute: $2.40/min at the promo rate, $4.80/min at list. That is a cap, not a target, and every graphics beat is a direct discount off it. Waste (dropped and unused takes) is the only thing that can push past it.

**Requirement:** the first live run must log, per take, the timestamp at which the next take's anchor frame became available — not just when the take was submitted. That single number decides whether the show needs 9% graphics or 30% graphics, and nothing else in this document can be sized without it.

---

## 4. Roles: who is allowed to do what

The whole design rests on one boundary: **the writer decides what is said. The conductor decides what is seen, and when.** Neither crosses. If that line blurs, the conductor starts rewriting the show and the show stops being writable.

| Role | May do | May **not** do |
| :--- | :--- | :--- |
| **Ingest** | Fetch posts. Timestamp them. Flag which have images or links. | Judge, rank, rewrite, or decide order. |
| **Segmenter** | Choose what is worth talking about and in what order. Merge related posts. Drop junk. Hand forward a short brief: this item, this angle, roughly this many beats. Emit clearly-labelled filler when the feed is dry. | Write any spoken word. Choose a layout. |
| **Writer** | Turn a brief into spoken lines. Own persona and voice. Decide **which host says it**. Own the performance direction that rides along inside the prompt. Run two or more beats ahead. | Decide when a line airs. Choose a layout. Call the video API. Fetch posts. |
| **Performer (H3 Max)** | Perform one given line as one atomic clip, picture and sound welded together. | Anything else. It returns no transcript, is assumed to improvise nothing, and knows nothing about the show. |
| **Compositor** | Given a beat instruction, render the frame: host window placed, set behind, card overlaid, lower third, audio bed. Deterministic. | Decide anything. It is a renderer with no opinions. |
| **Playhead** | Own wall-clock truth. Play what it is handed. Announce "current clip ends in X". Freeze when it runs dry. | Choose what plays next. |
| **Conductor** | At each boundary: pick the layout, pick the source, set the duration. Decide **when** to submit the next take, at what resolution, and whether it chains off the previous frame or re-anchors to the hero still. Keep the drift counter. Keep the hold budget. Apply Jesse's overrides. Shift the layout mix when money runs low. | Write or alter a single word. Change who is speaking. Touch prompt content beyond anchor, resolution, and duration. |
| **Operator (Jesse)** | Override anything, at the next clip boundary. | Override mid-clip — clips are atomic (§7). |
| **Spend meter** | Refuse any submission. Final authority, overrides the conductor. | Nothing else; it is a brake, not a driver. |

Two consequences worth naming:

- Because the writer picks the speaker, and because a chained take needs *that host's* previous last frame, the writer must publish speaker assignments at least two beats ahead so anchors can be prepared. This is a small contract addition to the writer, not a change to what it writes.
- The conductor may set resolution and duration, which are cost and timing levers, but not framing language ("close-up", "wide"). The moment the conductor writes prompt text it is co-authoring, and it also fights the last-frame chain, which pins framing by definition.

---

## 5. The source board

A source is anything that can be on screen. The useful way to sort them is not "camera vs graphic" but **how they bill**.

**Metered** — billed per second of finished video, every time. Only one thing is in this tier: the H3 window. $0.04/s at 768p promo, $0.08/s at list; $0.025/s and $0.05/s at 480p.

**Bake once** — generated slowly and offline, then reused forever. Amortises to roughly nothing. The set plate, the hero still, the idle/listening loop, transition stings, the outro.

**Free forever** — no generation at all. The tweet card, lower thirds, the clock and bug, the music bed and room tone, the freeze-frame hold, layout itself.

### Day one

| Source | Tier | Notes |
| :--- | :--- | :--- |
| Host clip, currently playing | Metered | The show's only real camera. |
| Host clip, currently cooking | — | Not showable, but its expected-ready time is the conductor's most important input. |
| Freeze on the last real frame | Free | The emergency brake. Counted as a defect, not a shot (§7). |
| Pre-baked idle / listening loop | Bake once | Host on screen, not speaking. The good way to buy 5 seconds. |
| Tweet card overlay | Free | Rendered from the real post text. Never a screenshot pushed through H3. |
| Static set plate | Bake once | One image. |
| Lower third, clock, bug | Free | |
| Music bed / room tone | Free | Underlies everything; makes silence read as intentional. |
| Pre-baked sting (~1s) | Bake once | One transition, used sparingly. |

That is nine sources, one of which costs money. A real truck's advantage was never the number of cameras; it was having something to cut to. This board already provides that.

### Next, in the order I would add them

1. **Second host.** Discussed in §12 — I think this is a *timing* feature more than a creative one, and cheaper than it looks.
2. **B-roll library.** Bake once, reuse many times. Ten generic desk-show cutaways bought once, at maybe $2 total, that can cover a beat any time forever.
3. **Screen capture of the actual feed.** Free, and honest — it is the real thing rather than a recreation of it.

### Later, and only with a reason

- **Generated cutaways** (a second live H3 stream for reaction shots). Metered, no reuse, and it makes the stall problem worse, not just the bill (§12).
- **A real camera** (Jesse at the desk). Free per second, but it turns a program into a scheduled appearance, which is a business decision rather than a technical one.

---

## 6. Shot grammar: what the conductor may call

All day-one layouts are **rectangles arranged on a set**. There is no cutout in v1, so the host clip arrives as a full frame with its own background, and every layout has to accept it as a rectangle. This is fine, and there is a free win in it: if the set is *a video wall behind a desk*, a rectangular host window stops being a compromise and becomes the look. Recommending that as a **default** — it makes "no cutout" a style rather than a limitation, and it survives contact with a second host later.

Six layouts. That is the whole vocabulary for the first conductor.

| # | Layout | What is on screen | Cost | When the conductor calls it |
| :--- | :--- | :--- | :--- | :--- |
| 1 | **Host full** | Host window large on the set | Metered | The default. Any ordinary spoken line. |
| 2 | **Host + card** | Host window smaller, tweet card beside it | Metered, and eligible for 480p | The line is about a specific post and the audience needs to see it. |
| 3 | **Card full, voice over** | Card fills the frame; the host's audio keeps playing underneath | Metered — see the trap below | A long quote, or a take that came back visually ugly but sounds fine. |
| 4 | **Card beat** | Card fills the frame; no new speech, bed only | **Free** | Let a line land. Buy 2–4 seconds. The workhorse. |
| 5 | **Idle** | Pre-baked host loop, listening or nodding | Bake once | Buy ~5 seconds with the host still on screen. |
| 6 | **Hold** | Freeze on the last real frame, bed continues | Free | Last resort. Budgeted and counted (§7, §9). |

**The trap inside layout 3.** H3 generates picture and sound in a single pass — you cannot buy the audio alone. So "host talking over a graphic" costs exactly as much as "host on screen", because you are paying for pixels you then cover up. The genuinely free beat is the *silent* one, layout 4. This is worth saying clearly because the tempting mental model — "graphics are cheap, so host-over-graphics is cheap" — is wrong on this stack. The only thing that would make it true is separating audio from video, which is exactly the TDD's TTS-first fallback. See §12.

Later additions, with a slot reserved in the grammar now so nothing has to be rebuilt: **two-box** (both hosts visible, one speaking), **over-the-shoulder** (host small, big graphic behind), **full-screen B-roll**, **live camera**.

**Resolution follows shot size.** When the host occupies roughly a third of the frame or less, 768p is being thrown away — 480p promo is $0.025/s against $0.04/s, about 37% cheaper, and invisible at that size. **Requirement:** each layout carries a minimum resolution, and the generator always requests the cheapest resolution that satisfies the layout it was requested for. This is the one cost lever only the conductor can pull, because only the conductor knows how big the host will be.

---

## 7. Timing rules the conductor must obey

Five rules. The first two are hard constraints from the platform; the rest are policy.

**Rule 1 — Clips are atomic. Cut only at boundaries.** Picture and sound arrive welded, so cutting away mid-clip cuts the sentence in half. Every conductor decision, and every one of Jesse's overrides, takes effect at the next clip boundary. The single exception is layout 3, where the audio deliberately continues under a graphic.

**Rule 2 — The last-frame lock.** A chained take may not be submitted until the previous take's anchor frame is uploaded and confirmed. The conductor therefore submits in one of two modes:

- **Chained** — first frame is the previous take's last frame. Preserves continuity. Strictly serial: one at a time, forever.
- **Anchored** — first frame is the hero still (or a pinned reference image). Independent of any other take, so several can cook at once.

**Rule 3 — A cut buys a free re-anchor, and a free head start.** If the beat immediately before a host beat contains no host video — a card beat, a sting, a full-screen graphic — then the seam is invisible, and that host take may be submitted in *anchored* mode. This is how real editing has always hidden discontinuity, and the review notes already identified it as the drift fix. What the review did not say is that it is also the *parallelism* fix: anchored takes have no dependency on each other, so around every graphic beat the conductor can put two or three takes in the oven simultaneously and actually build a buffer. Serial chaining can never build a buffer, because it produces at the same rate it consumes.

That reframes the conductor entirely. It is not decorating the gap. It is using the gap to escape the constraint that created the gap.

**Rule 4 — Spend latency as pacing, in a fixed ladder.** At each boundary, if nothing is ready to air:

1. Cooking take expected within ~1.5s → **card beat** (2s), or **idle** if no card is available.
2. Expected within ~5s → **idle** (5s).
3. Expected later, or unknown → **card beat then idle**, and if still nothing, **hold**.
4. Hold entered → log it as a defect and raise a visible health warning.

The distinction between step 3 and step 4 is the whole point. Steps 1–3 are a show. Step 4 is a bug wearing a show's clothes.

**Rule 5 — Holds are defects.** Track holds per minute as a health number, not as a shot type. **Default:** more than one hold per 60 seconds means the run is limping and the conductor should immediately raise the graphics share — call more card beats, insert idles between host beats — buying turnaround headroom by lowering the duty cycle. It should not wait for a human to notice.

---

## 8. Control surface

The first version is a log and a keyboard. No wall of screens. A video-wall interface is a real product later; it is not what is missing now. **What is missing now is the ability to tune the rules without paying $2.40 a minute to watch them run** — see the rehearsal requirement at the end of this section, which I would rank above every UI item in this document.

### State that must be visible, continuously

- **On air** — which take, which layout, which post it belongs to, when it ends.
- **Queue** — how many clips are ready; for each, whether it was chained or anchored.
- **Cooking** — what is in flight, submitted when, expected ready when, and how that estimate compares to recent reality.
- **Anchor** — is a fresh chain frame available; how many consecutive chained takes this host has run.
- **Feed** — how many items the segmenter is holding, how old the oldest is, and whether we are on filler.
- **Money** — spent, cap, current burn per minute, and minutes remaining at this burn.
- **Health** — holds in the last 60s, safety rejections, retries, share of the last 60s that was graphics.

Roughly:

```
T+42.0  ON AIR   take 009  HOST+CARD  post #7   ends T+47.0
        QUEUE    1 ready (010, anchored) | cooking 011 (chained, sent T+40.1, eta T+45.4)
        ANCHOR   chain frame 009 ready · consecutive chained 3/5
        FEED     3 items queued · oldest 22s · live
        MONEY    $4.36 / $20.00 · $2.18/min · ~7 min to cap
        HEALTH   holds 0/60s · rejected 1 · retries 2 · graphics share 11%
```

Everything on that screen is already implied by the TDD's manifest, with two fields added (§11). It is a view, not a new system.

### What Jesse can override

Single keys, each taking effect at the next boundary, each written into the log so the run stays measurable:

| Override | Effect |
| :--- | :--- |
| **Card** | Go to card full at the next boundary and stay until released. |
| **Kill** | Discard the cooking take unheard and unseen. For a bad gen. |
| **Skip** | Drop the current post, move to the next brief. |
| **Re-anchor** | Force the next take back to the hero still. |
| **Pause** | Stop submitting. Stay alive on graphics and idles indefinitely, spending nothing. |
| **Resume** | Start submitting again. |
| **Wrap** | Run out the ready queue, play the pre-baked outro, stop cleanly. |

Note what is absent: there is no "make it look better" and no "say something else". Those belong to the writer and the persona, and giving the conductor a knob for them would break §4.

### Rehearsal mode — the actual first requirement

The conductor is a rule set, and rule sets need dozens of runs to get right. At live prices, thirty minutes of tuning costs about $72 at promo rates and $144 at list, and most of those runs will be wrong on purpose.

**Requirement:** the conductor must be runnable against a stub performer that returns pre-existing clips after a configurable, randomly jittered delay, with the video API switched off entirely and the spend meter reading zero. Feed it a folder of takes already generated for the TDD's experiments, tell it that turnaround is sometimes 4 seconds and sometimes 11, and watch the ladder in §7 behave. Ten takes bought once fund unlimited rehearsal.

I would build this before the conductor makes a single real API call. It is also the only honest way to test the failure modes in §9, since most of them are hard to cause deliberately when you are paying for them.

---

## 9. Failure modes

| Failure | What the conductor does | What is required to make that possible |
| :--- | :--- | :--- |
| **Gen late** | The §7 Rule 4 ladder: card beat → idle → hold. Raise graphics share if it keeps happening. | An expected-ready estimate that learns from the last several takes, not a fixed constant. |
| **Gen ugly** — drift, wrong framing, garbled line | Honest answer: at queue depth 1 there is **no review window**. The clip is airing seconds after it exists. | Cheap automatic rejects that need no judgment: duration matches what was asked, audio is not silent, last frame is not black, file size is sane. Reject and reissue on those. Optionally, a configurable *review delay* that runs the queue one clip deeper, giving a ~5s human veto at the cost of ~5s more lag. **Default:** off on day one; the lag is not worth it until someone is reliably watching. |
| **Identity drift** | Conductor holds the consecutive-chained counter and forces an anchored take at the next available cut. | The counter, and the §7 Rule 3 rule that cuts license re-anchoring. Cap **default** 5, matching the TDD. |
| **Empty feed** | Never stop. Ladder: evergreen segment from a config list → callback to an earlier post → station-ident card beat plus idle. | The segmenter must always hold at least two briefs, and must mark filler as filler so the conductor can prefer cheap layouts while on it. |
| **Budget** | Two lines, not one. At the **soft** line (**default** 75% of cap) shift the mix toward graphics and drop to 480p where layout allows. At the **hard** line, stop submitting, run out the queue, play the outro. | The soft line is the conductor's to own, because only it controls the layout mix. The hard line stays with the spend meter, above the conductor. |
| **Playhead dies** | Restart it and resume from the queue. Log the gap. | Nothing new; the playhead is already a separate process. |
| **Hostile post text on screen** | The card is an on-air text surface displaying text we did not write. The safety checker inspects what goes *into* H3 — it never sees the card. So a post can be clean enough to talk about and still be something you would not want rendered at full width. | Card renderer executes nothing and truncates hard. Images stripped by default. A blocklist plus the manual **Skip**. And the first-build slice's "no tweets" stance should hold until this policy exists — see §13, question 3. |

---

## 10. Explicitly out of scope for the first conductor

Named so nobody sneaks a twenty-camera truck in through the side door.

- **More than one generated video window on screen at once.** Not now, arguably not ever. §12 explains why this is worse than double the money.
- **Generated cutaways** — a second live H3 stream for reactions or B-roll. Agreed with the working hypothesis: this is the bill multiplier, and it is also a stall multiplier.
- **A video-wall / multiview interface.** Rehearsal mode first (§8).
- **A second host in the *first* conductor.** The grammar reserves a slot; the first build stays one host. But see §12 — I would move this up the queue sooner than the existing docs imply.
- **Conductor-authored framing.** No "call a close-up". Layout, duration, resolution, anchor mode. That is the list.
- **Transitions** beyond a hard cut and one baked sting. No wipes, no crossfades, no motion graphics package.
- **Automatic quality judgment.** The cheap mechanical checks in §9, nothing that has an opinion.
- **Learned or self-tuning rules.** Hand-written rules only, in a config file a human can read and diff.
- **Streaming out** — RTMP, Twitch, anything. The stated position stands: revisit a playhead-to-stream layer only after 60 seconds holds locally.
- **Cutout / chroma-key.** Unchanged from the existing docs, and §6 makes it unnecessary for every day-one layout.

---

## 11. How this sits beside the TDD's first-build slice

**The first-build slice does not change.** One host, 5s, 768p, last-frame chain, static JPEG, no tweets, no cutout. Done when 60s plays without a stall, the hold fires on purpose, the chain is visible across 8+ takes, and real dollars-per-minute is known including retries.

**One thin interface change now.** Today the loop decides "play the next ready clip" implicitly, scattered across the loop body. Make that a single named decision point: it receives a snapshot of state and returns one beat — layout, source, duration, and the anchor mode for the next submission. On day one that decision function returns *host full* every time, and *hold* when the queue is dry. **Behaviour is byte-for-byte what the TDD already specifies.** The point is that the seam exists, so the conductor is a rule set dropped into a socket rather than a refactor of a working live loop.

**Two fields and one log, added now.** They are measurement, not features, and skipping them means re-running the expensive tests later:

- `anchor_mode` per take — chained or anchored. Needed to interpret drift results at all.
- `chain_ready_at` per take — when the next take's anchor became usable. **This is the number §3 hangs on.** Without it we cannot tell whether the show needs 9% graphics or 30%, and the whole conductor is sized on a guess.
- A **beat log** alongside the existing per-take manifest: what was on air, from when to when, under which layout. One row per beat. It is what makes a run reviewable after the fact.

**After 60s holds, in order:** rehearsal mode with the stub performer → the six layouts and the Rule 4 ladder → the card overlay → the second host (for timing, per §12) → the soft budget line → override keys. Streaming and any interface come after all of that.

---

## 12. Where I disagree with the working hypothesis

Mostly it holds. Four amendments, in descending order of how much they would change the build.

**1. A second host is a timing fix, and it is close to free. This is the biggest thing in this document after §3.** The existing spec says "both hosts generating at once: double it." True only if both are *on screen* at once. If they alternate — which is the locked design, hosts take turns — then only one window is ever airing, so generated seconds per show-minute are unchanged, and the bill per minute is unchanged.

But the timing changes completely, because **the last-frame chain is per host.** Take the sequence A1, B1, A2, B2. A2 needs A1's last frame, which was ready long before B1 finished airing. So A2 can cook during B1 without breaking anyone's chain. Each host's chain gets two playback windows of slack instead of one. A loop that runs at 110% duty cycle with one host runs at about 55% with two — from *cannot work* to *comfortable* — with no increase in cost per show-minute and no compromise on continuity.

That is a much stronger argument for the second host than banter, and it inverts the priority the existing docs assign it. It costs: a second anchor state, a per-host re-anchor policy, and the writer scripting both sides — all of which the contract already contains. The one new risk is waste: generating ahead means sometimes paying for a take you never air.

**2. "Angles" is the wrong word, and the wrong word will steer the build into the trap.** With one generated camera there are no angles. The conductor picks *frames and pacing*. Calling them angles invites "let's generate a second angle", which is precisely the eight-cameras-eight-bills mistake the hypothesis correctly warns about. I would strike angle and camera-number from the vocabulary and use **layout** and **beat**.

**3. "Day-one sources are cheap" is half true.** The free ones are free — card, set, freeze, layout, bed. But *host audio over a graphic* is full price, because H3 welds picture to sound (§6). So the conductor's genuinely-free vocabulary is one item: the silent beat. That is still enough to build the §7 ladder on, but it is thinner than the hypothesis assumes.

The interesting consequence: **the TDD's TTS-first fallback is not only a drift fallback, it is the conductor's cost lever.** If the voice comes from text-to-speech instead of from H3, then "host talks over a graphic" costs nothing, and the conductor can put the host's voice over a card for as long as it likes for free. That could plausibly halve the metered share of a show. It also makes clip length exactly predictable in advance, since you know the audio duration before you ask for video. The price is lip sync, which is why the existing docs' robot host with an occluded or waveform mouth was already the right design. I am not proposing we pick this — I am proposing that when E1 and E2 come back, this decision be weighed as a *production economics* question and not only as a drift question. It is Jesse's call and it is genuinely two-sided.

**4. Two generated windows at once is worse than 2× cost.** Worth stating as the reason the §10 ban is absolute rather than budgetary. Two windows on screen simultaneously must both be ready at the same instant. Each has its own independent chance of being late, so the probability that *something* stalls goes up faster than the bill does, and one late clip now ruins a composition rather than just a shot. The bill doubles; the reliability more than halves. Graphics do not have this property — they are always ready.

**Everything else in the hypothesis I would keep as written:** one generated window; the conductor decides layout and timing only and never writes; the eight-real-cameras framing is the trap; the first harness needs visible state and a small rule set rather than an interface; and fal's own Live product is a Twitch bot on the same clip API, so there is nothing to plug into — only a playhead-to-stream layer worth borrowing later.

---

## 13. Open questions Jesse has to lock

Listed plainly. Where I have a defensible default I have marked it; where I do not, I have not invented one.

**1. Does the show run to a clock, or open-ended?** A fixed twelve-minute episode with a rundown is a different machine from an open-ended block. With a clock, the conductor needs a time budget per segment and has to land the outro on the second — that is a real feature, not a tweak. Open-ended, it only has to stay alive. No default; this is a product decision.

**2. Audio path: keep H3's welded audio, or move to text-to-speech?** §12, point 3. This decides whether host-voice-over-graphics is free or full price, and therefore how much of the show the conductor can cover cheaply. The E1 and E2 results from the TDD are the input. No default — it trades lip sync against both cost and consistency, and that is a taste call.

**3. Whose feed, and does unmoderated post text ever go on screen?** The spec already flags the first half. The second half is new and it is a policy question, not an engineering one: the card displays text we did not write, and the safety checker never sees it. Recommended **default**: cards render text-only, hard-truncated, images stripped, with a blocklist and the manual Skip — and no live feed on air until that is in place.

**4. Is someone at the desk during a show?** If Jesse is watching with override keys, the review delay in §9 is worth its cost and the show can be braver. If unattended is a requirement, everything needs mechanical guards and the layout mix should be more conservative by default. This changes several §9 answers, so it needs an answer before they are settled.

**5. Is 5 seconds locked, or may we measure 8 and 10?** Roughly 2–2.5s of every take's turnaround is fixed overhead — queue, download, extract, upload — and it is paid once per take regardless of length. Spread across 10 seconds of playback instead of 5, it hurts half as much. Against that, the existing spec's datapoints (5s renders in ~3s, 15s renders in ~15s) suggest render time grows *worse* than linearly, which would cancel the gain. Those two numbers cannot both be extrapolated, so the honest position is that nobody knows. Cost is per output second, so the test is cost-neutral per show-minute: three takes at 5s, 8s and 10s, about $1.20 at promo, and the answer is either "5s is right" or "the duty-cycle problem in §3 largely disappears." I would spend the $1.20.

**6. Reference-to-video shipped on 29 Aug. Is it worth ten takes to measure now?** The TDD says do not chase it, and as scope discipline that is correct. But its relevance changed with §3: if a pinned host still holds identity without needing the previous take's last frame, then **every** take becomes anchored, the serial chain disappears, takes can cook in parallel, and a real buffer becomes possible. That is not a feature upgrade, it is the removal of the constraint this entire document is designed around. Unknown: whether its identity hold is good enough, and what it does to render time. Ten takes is roughly $2 at promo. I would argue for measuring it *before* committing to conductor rules that exist to work around a constraint that might not exist. Jesse's call on whether that violates the no-chasing rule.

---

## 14. Defaults picked in this document

Every low-stakes choice I made, in one place, so they are easy to overrule.

| Default | Where | Why |
| :--- | :--- | :--- |
| Set is a video wall behind a desk | §6 | Makes the rectangular host window the style instead of a compromise; kills the need for a cutout. |
| Six layouts, no more | §6 | Enough for the Rule 4 ladder; small enough to reason about. |
| Cheapest resolution that satisfies the layout | §6 | 480p is invisible in a small window and 37% cheaper. |
| Hold ladder: card beat → idle → hold | §7 | Two free-or-cheap steps before the one that looks broken. |
| More than 1 hold per 60s = raise graphics share | §7 | Self-correcting without waiting for a human. |
| Re-anchor cap: 5 consecutive chained takes | §9 | Matches the TDD; no reason to differ. |
| Review delay off on day one | §9 | Costs ~5s of lag to buy a veto nobody may be present to use. |
| Soft budget line at 75% of cap | §9 | Leaves room to glide to a clean sign-off instead of stopping mid-sentence. |
| Segmenter holds ≥2 briefs; filler is labelled | §9 | The show must never stop for lack of a topic. |
| Cards are text-only, truncated, images stripped | §13 | Smallest policy that makes an on-air text surface safe. |
| Rehearsal mode before any live conductor spend | §8 | Rules need dozens of runs; runs cost $2.40/min otherwise. |
