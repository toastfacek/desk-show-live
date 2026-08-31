# Agentic Live Streaming Harness — Plan

**Status:** Plan for review · **Date:** 30 Aug 2026 · **Owner:** Jesse

This is a plan, not a build. No code. It does not replace the two-host architecture. It answers one question that doc left open: **if the live show is run by software agents instead of a room of people, who is in charge, which jobs still exist, and which jobs were only there because humans are scarce?**

Read this first if you have not read the other files. The other files assume you already know the show. This one does not.

**Parent docs**

- `Desk Show — Two-Host Architecture & Harness.md` — current show design. Still in force. This plan sits on top of it.
- `Desk Show — Conductor Layer Brief.md` — who is allowed to know what. The permission rules here are the same idea, with fewer job titles.
- `Desk Show — Character & Set Bible.md` and `studio.yaml` — what the hosts and set look like. Not needed to review this plan.
- `OBS Harness — TDD.md` — public v1: clock + OBS + stub clips. Ships alone.
- `Live Sockets — TDD (text API + fal H3).md` — later package: their text key + their fal key. Depends on the OBS harness. Not in the public v1 cut.
- `Desk Show MVP — TDD` and `Desk Show — H3 Max Spec` — older. Useful for cost and the first video test. Do not treat them as the live-show design.

---

## 1. What we are proposing

We want a **program that can run a live stream** the way a small TV control room does: pick the next topic, write the next line, put a picture on screen, play a clip, draw the headlines, and recover when the next clip is late.

The show itself (two cartoon hosts talking about a feed) can stay private. The **runner** — the part that talks to the video switcher, plays clips, and lets agents do jobs — is the piece we may later make public.

This plan names that runner the **harness**. It names the agent in charge of the other agents the **producer**. Those are the only two “boss” roles. Everything else is either a specialist agent or a plain function.

**The decision we want from review:** is this the right split (producer in charge of jobs, harness in charge of time), and is the condensed job list right?

---

## 2. Context a new reviewer needs

### 2.1 The show

Working name: **Runtime**. A fake live desk show, aimed at Twitch.

Two original cartoon hosts sit at a desk and talk about posts from a feed (Twitter/X in the long run; a hand-pasted file of posts for the first version). A text model writes what they say. A video model acts it out as a short clip. We layer that clip over a real-looking TV frame: names, a headline, tickers, a clock, a LIVE badge, a card in the middle with the post.

We do not clone anyone’s face or voice. We do not name other shows, studios, or characters in any video prompt. That is both a legal line and a safety-filter line.

### 2.2 Why we do not generate the whole frame

The video model we buy clips from is **fal MiniMax H3 Max**. You send a prompt (and usually a still image). You wait. You get back a short video file with picture and sound already joined. Typical live take: **5 seconds** long, **768p**, about as long to make as it is to watch. You pay per second of finished video.

Rough cost for wall-to-wall talking, one picture on screen:

| Rate | Per 5s clip | Per minute of host talk | Per hour |
| :---- | :---- | :---- | :---- |
| 768p promo (through 1 Sep 2026) | $0.20 | $2.40 | $144 |
| 768p list (from 2 Sep 2026) | $0.40 | $4.80 | $288 |

If the model drew the headlines, the tickers, and the post card as well, three bad things happen: the type flickers (video models garble text), every extra “camera” is another bill, and a late clip freezes a face on screen.

So we generate **one thing only**: a wide shot of both hosts at the desk. Everything else is drawn by ordinary software, at full HD, for free, with no wait. That is the whole economic trick.

The two hosts are in **one** clip, side by side. The second host does not double the bill.

### 2.3 The video model is a clip, not a camera

This is the fact the whole machine is built around.

A real camera is live. You cut to it and it is there. H3 Max is a **file**. The next clip cannot start from the last frame of the current clip until that clip has finished, downloaded, and we have pulled the last picture out as a PNG. So we play clip N while clip N+1 is cooking. If N+1 is late, we must show something else that still looks like a show (a card, a bumper, a hold), not a frozen face.

We call that “something else” a **hold**. It is a planned beat, not a crash.

Until a later “pin this face” feature is proven, we keep identity by feeding each new clip the last frame of the last clip. That makes the video path **one-at-a-time**. Extra agents cannot cook the next clip sooner. Only a change in the video model can.

### 2.4 OBS

**OBS Studio** is free, open-source software (GPL v2 or later) that people use to record and live-stream. It layers cameras, video files, text, and web pages onto one output and can send that output to Twitch.

We use OBS as the **switcher and the player**. We do not write our own compositor. We talk to OBS over its built-in remote-control port (the WebSocket server, on since OBS 28). Our code is a client. That matters for licensing: talking to OBS over the network does not force our code to be GPL. Shipping a plugin that is compiled into OBS would.

OBS is not what a Super Bowl truck runs. It is what a lean studio runs when one box has to be the switcher, the graphics machine, and the stream encoder. That is enough for this show. Twitch out is an OBS checkbox.

The remote-control commands we care about are small and named. We build the scenes in OBS by hand, once. The program is allowed to **switch** scenes and **change** what a source is showing. It is not allowed to create or delete scenes while the show is on. A bad call at 2am must not take the studio apart.

### 2.5 How a real live room works (and what we copied)

A real news or talk-show control room is a small factory:

- A **producer** owns the list of segments and the pace. “We are long. Go to a break.”
- A **director** calls the shot. “Wide. Split. Card. Hold.”
- A **switcher operator** hits the buttons. They do not invent the show.
- A **graphics operator** puts up headlines and names.
- A **playback operator** cues the next tape and knows how much time is left.
- An **audio operator** ducks the music when someone talks.
- **Cameras and talent** are live.

In a modern newsroom, a list of stories in the news computer fires those machines in order. A human can still throw the list away.

We copied the **jobs**, not the hardware.

| Real room | This plan |
| :---- | :---- |
| Producer | Producer agent |
| Director | Director (rules first; an agent only later, and only if rules fail) |
| Switcher + graphics + playback + audio | OBS, driven by a small command list |
| Cameras | One paid video clip at a time |
| “Tape is late, go to the graphic” | Hold |
| “Audio keeps going under a cover shot” | Card full-screen, host sound still in the mixer |
| List of stories | The show list (segments) |
| Take next | The short loop, every clip boundary |

What is **not** like real TV: the “camera” is a 5-second file that costs money and arrives late. We cannot cut between live angles. We change **layouts** of the same clip (wide, split, one host bigger). That is a cost move dressed as a camera move.

### 2.6 Does this already exist?

Pieces exist. The product does not.

- **OBS + an assistant that clicks buttons.** Several small open projects let a chat agent switch scenes or mute a mic. They do not run a show. They do not buy video. They do not keep a clock.
- **fal’s own live demo** (Rehan Sheikh, late Aug 2026). Full-frame generated video, chat drives the next clip, sent to Twitch, then Kick, then Rumble after bans. That is “generate the whole world.” We are making a desk show. Same video API. Different machine. We are not plugging into that bot.
- **Offline film tools that call fal.** Fine for editing. Not live.
- **Streamer.bot and the like.** Event toys for human streamers (a follow plays a sound). Not a control room.

The gap: a runner that treats OBS as the player, a clip model as a paid camera, and everything else as free drawings — and that can be driven by agents without a person in each chair.

---

## 3. Two products, one machine

Keep these apart in your head. Reviewers who mix them will ask the wrong questions.

**The harness (candidate to be public later)**  
A runner that:

- talks to OBS
- plays a ready video file
- switches named layouts
- fills text and picture slots (headline, names, center card, tickers)
- keeps a clock of what is on air
- calls a video backend through a thin adapter (fal first)
- enforces a spend cap
- can run in three modes with the same code: **rehearse** (fake clips, $0), **live** (real fal), **replay** (read an old log)

**The show (stays ours)**  
The writer’s voice, the host sheets, the set, the feed, the list of segments, the rules for when to spend a clip. That is Runtime.

The harness is a switcher you can rent. The show is one production that rents it.

This plan specifies the **harness plus the agent org that sits on it**. It does not redesign the hosts or the look.

---

## 4. The two bosses

There are two different kinds of “in charge.” Mixing them is how the show freezes.

### 4.1 The harness owns time

The harness is **not an agent**. It is a clock.

Every few seconds, at a clip boundary, it:

1. Asks OBS what is on air and how much time is left.
2. Hands that snapshot to the Director.
3. Gets back **one** instruction (a “beat”).
4. Does that instruction: switch layout, play a file, maybe start the next video job.
5. Does not wait for a text model. The only wait it will accept is the video API.

If every agent is late, the harness still cuts. It goes to hold. The show continues.

An agent must never be the thing that decides “has the file landed?” The file has landed when OBS (or the download step) says so.

### 4.2 The producer owns jobs

The **producer** is the only agent that other agents report to.

It runs on the **slow loop**: about once per segment (roughly 90 seconds), and whenever spend or pace looks wrong. It does not emit a beat. It does not write a spoken line. It does not call fal.

It decides:

- what the next segment is about
- whether to skip a post
- the headline and what sits in the center
- a layout *plan* for the segment (a list of preferred shots, not the live cut)
- “we are long, go to a bumper”
- “spend is hot, stop buying clips”
- whether to take a note from a critic after a clip has already aired

Writer, Director, and any critics do **not** talk to each other. They write into slots the producer or the harness already owns.

```
Producer (agent)                 ← boss of jobs
  ├─ Fetch posts (function)
  ├─ Writer (agent)
  ├─ Graphics fill (function; agent may draft copy off the clock)
  ├─ Critics (agents, after a clip, never blocking)
  └─ Director (function now; agent only later)
        └─ one beat, handed to the harness

Harness (program)                ← boss of time
  ├─ OBS commands
  ├─ Video submit / download / last-frame extract
  ├─ Spend cap
  └─ What is on air
```

**Why the producer, not the director, is the orchestrator.**  
The director’s job is one cut. If the director also hires the writer and picks the topic, the org chart sits on a 5-second timer. That is how you miss the cut. The producer already exists in the two-host doc as “build later.” This plan promotes it to “the agent in charge,” and keeps it off the short loop.

**Why the harness, not the producer, is the clock.**  
Live video does not care who is clever. It cares what is on screen *now*. A language model is a bad clock.

---

## 5. The condensed job list

The two-host doc listed seven roles and then a human operator. Several of those exist because a TV truck needs a body in a chair. Software does not.

### 5.1 Live org (what we keep)

Four brains and a clock.

| Name | Kind | Clock | Job |
| :---- | :---- | :---- | :---- |
| **Producer** | Agent | Slow (per segment) | Topic, pace, headline, center, layout plan, “stop spending” |
| **Writer** | Agent | Ahead of video (always 2 thoughts ready) | The next spoken thought, for whoever is speaking. One writer for both hosts. |
| **Director** | Function first | Short (every clip edge) | One beat: layout, what plays, whether to buy the next clip |
| **Critics** | Agents, optional | After the cut | Did the intended sprite carry the voice and motion? Was the native line clear? Did the shapes or voices drift? Tell the producer, not the clock. |
| **Harness** | Program | Always | Time, OBS, files, money brake |

### 5.2 Demote to functions (never make these agents)

| Old job | Why it is not an agent |
| :---- | :---- |
| Fetch posts | Get data. No opinions. First version reads a local JSON file. |
| Build the video prompt and call fal | Fill a template, send a request, respect the cap. |
| Download, cut out the last frame, write the log row | File work. |
| Switcher / playback / duck music / put up a headline | Button presses. The OBS command list. |
| Spend cap | A brake. If an agent owns the brake, it will spend. |

### 5.3 Merge (these were staffing)

| Old jobs | Now |
| :---- | :---- |
| Segmenter + “which post” + headline taste | **One producer package** per segment. The segmenter as its own agent was a human-sized role. Keep the *output shape*. Drop the extra title. |
| Graphics operator + name bars + ticker clerk | **Fill a template.** An agent may draft copy on the slow loop. On the short loop it is “set headline to this string.” |
| Human operator (kill, hold, panic, preview) | **Rules plus a critic.** Preview is free — the next file already exists. Kill and hold are the same path as a rejected video. A small panel can stay for debug. It is not a job the show needs in order to exist. |
| Audio operator | H3's native audio stays attached to the clip; someone speaking → drop the music bed by a set amount, segment change → play a sting. |

### 5.4 Do not add

| Tempting extra | Why not |
| :---- | :---- |
| One writer per host | Two voices start a meeting. One writer scripts both. |
| A director vote among many agents | The short loop needs one beat, not a committee. |
| Extra video agents cooking spare clips | Waste is the only way past the cost ceiling. We generate when the director says submit, depth one. |
| A second paid picture on screen | Both pictures must be ready at the same cut. Cost and stall risk rise faster than 2×. |

---

## 6. What each job may see, and what it may emit

This is the safety rail. It is copied from the conductor brief and tightened. If two jobs share a brain, these walls disappear and the show starts writing to the clock.

### 6.1 Fetch posts

**Sees:** the feed (or the local file), a cursor. Nothing about the show.

**Emits:** a list of posts (id, time, author, text, url, media).

**Must not:** write lines, pick the topic, call the video API.

### 6.2 Producer

**Sees:** new posts, recent packages, the show list, spend so far vs cap, how many holds in the last few minutes, notes from critics. Does not see last-frame image URLs. Does not see the live play time as something to write to.

**Emits:** one **segment package** (and, when needed, a pace order). The package includes a **topic map**: ordered beats, each with a complementary job for BOT1 and BOT2. The Producer maps the topic. It does not write the lines, and it does not fill a take count.

`time_budget_s` is how much show time this map may fill. It is a budget, not a script length. For a 90 second budget, prefer one beat that can be explored in depth. For a longer budget, add a beat only when the source opens a new question. An hour uses the same machinery with more beats.

A beat is done when both hosts have landed their job and both have nothing grounded left to add. The segment ends when the map is exhausted, or when the harness clock / spend cap says stop. The clock does not invent extra recap takes.

```json
{
  "item_id": "1950123999999999999",
  "question": "If you have no thesis, is the move even information?",
  "framing": "The poster is narrating a VIX spike as weather. Treat fear as a product with no salesperson.",
  "angles": [
    "a ticker that shrugs is still a ticker",
    "one host wants the number; the other wants the reason"
  ],
  "topic_map": {
    "throughline": "A fear ticker with no thesis.",
    "fight": "Is the move information, or weather with a chart?",
    "done_when": "Both the thesis and the number have been landed.",
    "beats": [
      {
        "id": "b1",
        "question": "If you have no thesis, is the move even information?",
        "tension": "Weather versus a counted move.",
        "bot1_job": "Land that a move without a thesis is weather.",
        "bot2_job": "Land what moved, by how much, for whom.",
        "fact_ids": ["f1"],
        "done_when": "Both jobs landed and neither host has more grounded to add."
      }
    ]
  },
  "chyron": "A MOVE WITHOUT A THESIS",
  "center": {"kind": "tweet_card", "post_id": "1950123999999999999"},
  "layout_plan": ["wide", "split", "split", "wide", "split"],
  "spend_policy": "normal",
  "skip": false
}
```

`spend_policy` is one of: `normal` | `cheap` (prefer cards and bumpers) | `stop` (no new video buys; finish what is cooking).

A pace order is a separate, rare object: `hold` | `next_segment` | `bumper` | `end_show`. The harness executes it at the next clip edge, not mid-clip. Picture and sound in a clip are joined; we do not cut a clip in half.

**Must not:** emit a spoken line. Emit a live beat. Call fal.

### 6.3 Writer

**Sees:** both host personas and writer rules, the full script so far, the current package, the current beat, coverage (what has landed, what is still open), who speaks next, whether the last thought is still open. If a clip was rejected, it also sees `reissue: shorter, blander`. It does not see the failed video. It does not see the live clock or the take index.

**Emits:**

```json
{
  "speaker": "BOT1",
  "text": "Fear has a ticker now, and it shrugs.",
  "thought_open": false,
  "angle_used": "a ticker that shrugs is still a ticker",
  "beat_id": "b1",
  "landed_own_job": true,
  "beat_exhausted": false
}
```

A **point** is the claim this host wants to make. A **chunk** is one 5-second file. The Writer may batch a point into 1–4 chunks in one call. Earlier chunks keep `thought_open` true so the same host keeps talking. The last chunk may close the point or leave it open if the rant is not done. The clip length must not write the script.

The Writer stays on the current beat until both host jobs have landed and both hosts have nothing grounded left to add. Landing a job is not the same as exhausting the beat. Do not restate the card. React to the previous line. Cover the beat from this host’s perspective, then the other host’s, in depth.

This is the complementary-questions contract from `research/findings/talk-show-segment-lifecycle.md` (thesis/weather vs number/stake). The end condition is topic-complete, not “empty the well on a 90s clock.” The 90s number is the Producer’s budget when it maps the room. A 90s discussion of one beat is expected. An hour is the same map with more beats or a longer budget.

The line sits in a **written-ahead** slot (target depth: 2) until the director spends it. The next writer call gets this line on the script even if the video has not performed it yet. Writer ahead, video behind.

**Must not:** pick a layout. Call fal. Fetch posts. See the spend number or the live clock. Rewrite earlier lines.

### 6.4 Director

**Sees:** a snapshot of time and money, plus the next written line as opaque text. It does not get the pile of posts. It does not rewrite the line.

**Snapshot in:**

```json
{
  "t": 12.4,
  "on_air": {
    "layout": "split",
    "take": 2,
    "duration_s": 5,
    "ends_at": 15.0,
    "speaker": "BOT2"
  },
  "ready": [],
  "cooking": {"take": 3, "submitted_at": 10.1},
  "chain_ready": false,
  "next_line": {
    "speaker": "BOT1",
    "text": "Fear has a ticker now, and it shrugs."
  },
  "spend_usd": 0.60,
  "spend_cap_usd": 20.00,
  "holds_recent": 0,
  "anchor_reset_due": false,
  "segment": {
    "layout_plan": ["wide", "split", "split"],
    "center": {"kind": "tweet_card", "post_id": "1950123999999999999"},
    "chyron": "A MOVE WITHOUT A THESIS",
    "spend_policy": "normal"
  }
}
```

**Beat out** (one cut):

```json
{
  "at": 15.0,
  "layout": "card_full",
  "host_source": null,
  "speaking": null,
  "center": {"kind": "tweet_card", "post_id": "1950123999999999999"},
  "chyron": "A MOVE WITHOUT A THESIS",
  "submit": null,
  "why": "take 3 is still cooking; the next last-frame does not exist; put the post up"
}
```

When the cooked clip lands and the chain is ready, `submit` may be filled. The director still does not write `text`. It only carries the writer’s line through.

**v1 is a function.** Same snapshot in, one beat out. Do not put a model here until that function is wrong in a way rules cannot fix. If we ever do, the prompt is: “return one beat, never a line of dialogue,” and the model must finish during the *current* clip, not at the edge.

**Must not:** write dialogue. Fetch posts. Bypass the spend cap.

### 6.5 Video submit and file work

**Sees:** the line, the host sheets and set text from `studio.yaml`, the current still image URL, duration, resolution, the remaining budget.

**Does:** assemble a fixed prompt (style + set + both hosts + who is speaking + the line in quotes). Call fal. Refuse if the cap would be crossed. Download the file. Extract the last frame as PNG (never JPEG). Upload that PNG. Append one log row.

**Must not:** change the line. Pick a layout.

### 6.6 Critics (optional, after the cut)

**See:** the clip that just played (or a still from it), the line it was supposed to say, which host was meant to speak.

**Emit:** notes to the producer (`reanchor`, `reissue`, `ok`). They do not change what is on air. The next short loop has already moved on.

### 6.7 Permission table

| | Posts | Script | Clock / money | Last-frame URL | Spoken line | Live beat |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| Fetch | in | no | no | no | no | no |
| Producer | in | glance (pace only) | trend, not the cut | no | no | no |
| Writer | no (only the chosen post inside the package) | in / out | no | no | **out** | no |
| Director | no | next line as text | **in** | yes, to pass through | carry only | **out** |
| Video submit | no | no | cap only | in / out | in, frozen | no |
| Critics | no | the line just aired | no | no | no | no |
| Harness | no | no | source of truth | files | no | executes |

---

## 7. The two loops

Same idea as the two-host doc. The producer now sits at the top of the slow loop. The director stays a function on the short loop.

### 7.1 Slow loop — about every 90 seconds, never on the critical path

```
show list advances
  → fetch posts
  → producer emits one package (or skip, or bumper)
  → writer starts filling the written-ahead slot (depth 2)
  → harness loads the package’s headline, center, and layout plan
```

### 7.2 Short loop — every clip edge, about every 5 seconds

```
OBS says what is on air
  → director gets the snapshot
  → director emits one beat
  → harness does the beat
  → if submit is set: build prompt, call fal, download, last frame, log row, put the file where OBS can see it
```

Nothing in the short loop waits on a text model. All of its delay is the video API.

### 7.3 Three modes, one path

| Mode | What plays | Spend | Use |
| :---- | :---- | :---- | :---- |
| `rehearse` | Old clips, returned after a jittered delay | $0 | Tune producer packages and director rules. Most work happens here. |
| `live` | fal | Real | The show. |
| `replay` | An old log file | $0 | Recreate a run. Debug one failure. |

Rehearse is not a nice-to-have. Live video is a few dollars a minute. Every rule you can prove with fake clips, you prove with fake clips.

This is also where extra agents are worth it: run the same show list fifty times with different director rules, keep the set that holds. Do that **off air**.

---

## 8. What the harness can ask OBS to do

A small command list. Same list for the harness, a human at a debug panel, and an agent trying to set the room up.

```
get_program_state()     → what is on air, time left in the clip, is the source healthy
set_layout(name)        → wide | split | solo_l | solo_r | card_full | hold
play_clip(path)         → point the one host video source at a new file
set_speaking(host)      → draw the “this person is talking” highlight
set_center(kind, data)  → post card | chart | image | guest | none
set_headline(text)
set_name_bar(host, name, handle)
set_ticker(track, items)
play_sting(name)
duck_music(db)
set_crop(item, rect)    → live tune of the split (setup, not every cut)
```

**Layouts** are OBS scenes, built by hand:

| Layout | On screen |
| :---- | :---- |
| `wide` | The generated two-shot, full width |
| `split` | Left half and right half of the **same** file, placed on either side, card covering the join |
| `solo_l` / `solo_r` | One half, larger |
| `card_full` | Center content full frame; host audio can still play |
| `hold` | Card or bumper, tickers moving, music up. The late-clip layout. |

`split` uses one media source added to the scene twice, so both halves share the same play time. Verify that before anything else is built on it. That check is already milestone M0 in the two-host doc.

The harness does not create or destroy scenes.

---

## 9. When something goes wrong

| Failure | Response |
| :---- | :---- |
| Next clip is late | `card_full` or `hold`. Headline stays. Music stays. Reads as a pause, not a crash. |
| Video safety reject | Drop the take. Cost still counts. Writer reissues shorter and blander. Hold. Never retry the same prompt. |
| Cannot extract or upload the last frame | Fall back to the locked hero still. Keep going. |
| Faces drifted out of their halves | Force a return to the hero still, hidden behind a layout change (those are free). |
| OBS remote-control drops | Reconnect. OBS keeps playing what is already on air. A stale layout is survivable. A dead player is not. |
| 3 video failures in a row | Finish what is ready, go to a bumper, stop. Keep the log. |
| Spend cap | Refuse the next submit. Clean stop. |
| Producer is late | Keep the current package. Writer can still work. The short loop does not wait. |
| Writer is late | Do not stall video. Hold, or play a bumper. Depth 2 is there so this is rare. |
| Producer and director disagree | Director wins the cut (it has the clock). Producer wins the next segment. |

Picture and sound are joined inside a clip. We never cut a clip in the middle.

---

## 10. What changes if there is no human in each chair

These assumptions were true because people are scarce or slow. They can go.

1. **One person per job.** We do not need a graphics operator, a switcher, and a playback operator. We need a short command list.

2. **A human at the desk makes the show possible.** No. Conservative director rules make unattended possible. A critic plus the producer make it better. A small panel is for debug, not survival.

3. **The director must be a function forever.** The reason was delay and too many cooks, not a law of nature. A director *agent* may decide during the current clip and park a beat for the edge. It still must not write lines. Promote it only after the function is wrong in a way rules cannot fix.

4. **“Pick the topic” needs its own agent.** That was so a human-shaped writer would not also pick the story. A producer agent can emit the whole package. Keep the schema. Drop the extra role.

5. **Rehearsal is for a person to tune by hand.** Rehearsal becomes a search: same harness, fake clips, many rule sets, keep the winner.

6. **Wait to build a producer until the director is wrong.** That was a cost-of-complexity argument for a human team. A producer that runs once per segment is cheap. What we still will not do is put producer taste on every 5-second cut.

---

## 11. What does not change (more agents do not help)

These are physics, money, or taste. Headcount does not move them.

1. **What is on air is a fact.** A hundred agents agreeing the next file is ready does not make the file exist.

2. **The last-frame path is one-at-a-time.** Until a pinned-face feature is proven, clip N+1 needs clip N’s last picture. Extra video agents just spend money.

3. **One paid picture.** Two paid pictures at once is worse than twice the cost.

4. **The writer must not see the clock.** If it does, every line becomes “fill five seconds.”

5. **The director must not write.** If the same brain picks the shot and the line, the host talks like a switcher.

6. **The spend cap is a hard stop.** Extra agents will happily buy spare clips. Waste is the only way past the per-minute ceiling.

7. **One writer, both hosts.** Voice is a consistency problem.

8. **Safety filters and platform rules still exist.** More agents make a bigger prompt surface. They do not reduce bans. Reissue stays shorter and blander.

---

## 12. What we will not do in this plan

- Generate the whole frame.
- Plug into fal’s own live bot.
- Cut a clip in the middle.
- Let any agent create or delete OBS scenes on air.
- Let any agent own the spend cap.
- Put a language model on the short loop in v1.
- Build a second paid camera.
- Let chat change the show in v1 (showing chat later is cheap; letting it write is a safety problem).
- Name other people’s shows, faces, or characters in a video prompt.
- Treat this plan as permission to write code before the two-host M0/M1 video tests. Those tests can still kill the look. This plan is the org chart, not a skip-ahead.

---

## 13. How this lands on the existing build order

The two-host milestones stay. This plan does not insert a new first step in front of “does the split hold?”

| Existing step | What this plan adds |
| :---- | :---- |
| M0 — bible, hero still, OBS scenes, prove the split shares one play time | Unchanged. Still first. |
| M1 — one clip: prompt → fal → file → last frame → log | Unchanged. |
| M2 — composition and “who is speaking” tests | Unchanged. Stop if the split fails. |
| M3 — OBS command list, drivable by hand | See `OBS Harness — TDD` (H3). |
| M4 — harness in `rehearse`, stub clips, $0 | Public OBS harness done at H4. |
| M5 — live writer + video + spend cap | See `Live Sockets — TDD`. Their text key + their fal key. Producer still a file. |
| M6 — Twitch out | Unchanged. |

**Do not build the producer as a model before M4 holds.** M4 is where we learn whether the clock works. A clever agent on a broken clock is noise.

**Public / open-source cut:** `OBS Harness — TDD.md` at H4. Clock, OBS backend, stub clips, demo pack. No writer model, no fal, no host sheets, no feed. Text + fal sockets are a later package.

---

## 14. Open questions for review

Please mark each as agree / change / defer.

1. **Producer is the agent in charge of jobs. The harness is in charge of time.** Is that the split you want?

2. **Director stays a function in v1.** Agree?

3. **Segmenter is not its own agent.** The producer emits that package. Agree?

4. **Human operator is not required for the show to exist.** A debug panel is fine. Agree?

5. **Critics are optional and after the fact.** Do not block the next cut. Agree?

6. **One writer for both hosts, forever on air.** Extra writers only in rehearsal, if at all. Agree?

7. **The public cut is `OBS Harness — TDD.md` only** (clock + OBS + stub). Text and fal stay in a later package. Right line?

8. **License for a later public repo.** Talking to OBS over the network can be MIT or Apache. Confirm a preference when we split the repo. Not a blocker for this plan.

9. **Reference-to-video.** If pinning a face removes the last-frame chain, most of §11.2 goes away and clips can cook in parallel. That is a measurement (already listed in the two-host doc). This plan does not depend on it.

---

## 15. What “done” means for this plan

This plan is accepted when the answers to §14 are written down (even as “defer”), and nobody is still treating the director as the orchestrator or an agent as the clock.

It is **not** done when code exists. The next writing, if this is accepted, is a short addition to the two-host doc: rename conductor/segmenter in the role table, add the producer package, point here.

---

## 16. A worked minute (so the loops are concrete)

Clock starts at 00:12.4. Take 2 is on air (split, BOT2 speaking), ends at 00:15.0. Take 3 is cooking. The chain for take 4 is not ready. The writer already has thought 4 in the written-ahead slot. Spend is $0.60 of $20.

**00:15.0 — short loop.** Director sees “cooking, no ready file,” emits `card_full`, `submit: null`. Harness puts the post up. Music stays. This is a hold that looks like a beat.

**00:15.4 — take 3 lands.** Chain is ready. Director emits `split`, play take 3, `submit` take 4 with the writer’s line and the new last-frame URL. Harness starts the video job. Writer is already free to write thought 5. Producer is asleep until the segment clock says so.

**~00:90 — slow loop.** Producer looks at new posts, spend trend, holds. Emits the next package or a bumper. Writer switches questions when the current thought closes. The short loop never waited for that.

If at 00:15.0 the producer had been “thinking,” nothing changes. The card still goes up. That is the whole point of two bosses.
