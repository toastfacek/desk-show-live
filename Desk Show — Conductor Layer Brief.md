# Conductor layer

This is a requirements brief, not a build. No code. Nothing here calls fal (the video API we buy clips from).

## What this project is

`desk-show-live` is the spec for a fake live desk show. An original cartoon host sits at a desk and comments on a feed (Twitter/X). We do not generate a whole new world each time. We buy short talking-head clips from MiniMax H3 Max on fal, play them in a row, and composite the host over a static set plus a real tweet card.

H3 Max is a clip model, not a livestream. You send a prompt (and usually a first-frame image), wait, and get back a 5-second mp4 with picture and sound welded together. A 5-second clip at 768p costs $0.04/s on the promo rate through 1 Sep 2026, then $0.08/s. It takes about as long to render as it lasts.

To keep the host looking like the same person, each new clip starts on the last frame of the last clip. That is the last-frame chain. The last frame does not exist until the clip finishes, downloads, and we extract the PNG. So we cannot start take N+1 when N is submitted. We play N while N+1 cooks. That is the only overlap.

The rest of this repo has the older TDD and H3 Max spec. Those stay. This page adds the layer around the clips.

## What the conductor is

The conductor is the piece that decides, at each cut, what is on screen and for how long. It is a director sitting in front of a switcher. It never writes dialogue.

H3 Max is one camera, and it is a slow camera. If that camera is the only thing on screen, the show freezes the first time a take is late. Three seconds of a frozen face looks broken. The same three seconds on a tweet card, with the music bed still up, looks like a show taking a beat. The conductor's job is to turn generation delay into that beat.

## Who does what

- **Ingest** pulls posts. It does not rank or write.
- **Segmenter** turns the pile into a short "talk about this next" queue.
- **Writer** writes the spoken line from that brief. It can run a line or two ahead. It never picks a layout.
- **H3 Max** only performs a line it is already given. It returns no transcript.
- **Compositor** lays the host clip over the set and the tweet card. Deterministic. No opinions.
- **Playhead** is what is actually playing right now. Wall-clock truth.
- **Conductor** picks layout, source, and duration. It may set resolution and whether the next take chains off the last frame or re-anchors to the hero still. It does not touch prompt text.
- **Operator (Jesse)** can override at the next clip boundary. Clips are atomic: picture and sound are welded, so no mid-clip cut.
- **Spend meter** can refuse a submission. It is a brake.

## What can be on screen

Sort sources by how they bill, not by "camera vs graphic."

**Metered:** the H3 Max host window. This is the only thing that costs money every time.

**Bake once:** the set plate, the hero still, an idle/listening loop, a short sting, the outro. Made offline, reused forever.

**Free:** the tweet card (real post text, never baked into H3), lower thirds, clock, music bed, a freeze on the last frame.

Day one is one metered window plus those graphics. Do not generate eight extra angles. That is eight bills. Two generated windows on screen at once is worse than 2x cost: both have to be ready at the same instant, so stall risk goes up faster than the bill.

## Timing

The TDD said generation of N+1 starts when N is submitted. That is not possible while the last-frame chain is in use. Play N while N+1 cooks.

Turnaround (submit to next-frame-ready) is about 4–6 seconds. Playback is 5 seconds. The one-host chained loop sits at roughly 100% duty cycle: no slack. If turnaround lands above ~4.5s, some of the show *must* be non-host material. Graphics beats are how the 60-second test passes on purpose, not by luck.

With one window on air, you never bill more than 60 generated seconds per show-minute: $2.40/min promo, $4.80/min list. Every graphics beat is a discount. Waste (takes you generate and never air) is the only way past that ceiling.

Log `chain_ready_at` per take: the timestamp the next take's anchor frame became usable. That number sizes the graphics share. Guessing it is how this whole page stays fiction.

## Lock these

1. One generated video window on screen, ever, in v1. Graphics and bake-once assets are the other cameras.
2. Writer decides what is said. Conductor decides what is seen and when. The conductor never writes prompt text.
3. Rehearsal mode first: a stub performer that returns existing clips after a jittered delay, fal off, spend at zero. Tune the rules there. Live conductor time is ~$2.40/min promo.

On day one the conductor can just return "host full screen" every time, and "hold" when the queue is dry. Same behavior as the TDD. The point is the seam exists.

## Jesse still has to pick

1. **Audio:** keep H3's welded audio, or move voice to TTS? Host-talking-over-a-graphic costs full price today, because you pay for pixels you cover up. TTS makes that beat free and makes clip length predictable. The trade is lip sync. Wait for the TDD's E1/E2 results. No default.
2. **Clock or open-ended?** A 12-minute episode with a rundown is a different machine from a block that just has to stay alive. No default.
3. **Attended or unattended?** If someone is at the desk, a ~5s review delay buys a veto on ugly takes. If not, the layout mix has to be more conservative on its own.

Also still open, with defaults: cards are text-only, truncated, images stripped, until a safety pass exists. Whose feed is still unset.

## The surprise

A second host is a timing fix, and it is close to free.

The older spec said two hosts double the bill. True only if both are on screen at once. If they alternate (the locked design), only one window airs, so cost per show-minute does not change.

The last-frame chain is per host. Sequence A1, B1, A2, B2: A2 needs A1's last frame, which was ready long before B1 finished airing. Each host's chain gets two playback windows of slack instead of one. A loop at ~110% duty cycle with one host runs at ~55% with two. Same bill. Continuity holds. The new risk is waste: generating ahead means sometimes paying for a take you never air.

That is a stronger argument for the second host than banter. Do it after the one-host 60s loop holds.

## Out of scope for now

No livestream / RTMP.
No video-wall UI.
No second generated window at the same time.
No generated cutaways.
No plugging into fal's own H3 Max Live Twitch bot. Same clip API. We can steal a playhead-to-stream layer later.

First build is unchanged: one host, 5s, 768p, last-frame chain, static JPEG, no tweets, no cutout. Done when 60s does not stall, hold fires on purpose, the chain is visible across 8+ takes, and we have a real $/min including retries.

## Two cheap measurements

8s and 10s takes once (~$1.20 promo). A chunk of turnaround is fixed per take (queue, download, extract, upload). Longer clips may give slack for the same money per show-minute. Render time may also grow worse than linear. Nobody knows until we measure.

`minimax/h3-max/reference-to-video` shipped 29 Aug. Ten takes (~$2 promo). If a pinned host still holds identity without the previous last frame, the serial chain this page is designed around goes away, and takes can cook in parallel. Measure before we commit to conductor rules that only exist to work around that chain.
