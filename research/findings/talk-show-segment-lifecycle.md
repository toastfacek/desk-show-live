# Talk-show cadence, segment lifecycle, and a two-host LLM contract

**Status:** Research brief for Runtime's Segmenter and Writer · **Date:** 31 Aug 2026

This is editorial research, not a visual lane. Named shows are cited here so a human can look at them. They must never enter a generation prompt. Describe the *move*, not the trademark.

Runtime already has the right skeleton: a Segmenter that opens one arguable question, a Writer that emits complete conversational thoughts, and an `open / develop / close` phase on each take. What was missing was the production grammar those pieces are supposed to be imitating.

---

## Executive summary

TBPN is not a late-night interview show and it is not a cable debate show. It is a daily three-hour live desk program that treats Silicon Valley the way SportsCenter treats a league: a ticker of personnel moves, fundraises, product launches, and "who ya got," delivered by two hosts who already share a group chat. The New York Times called it "SportsCenter for the LinkedIn crowd" and "two self-aware fellas who treat techno-capitalism like a Fantasy Football league." President Dylan Abruscato's rundown is three hours with three jobs: hour one is timeline react, hour two is one or two Tier-1 guests, hour three is a lightning round of fundraises, product news, and first-time founders.

The unit that matters for Runtime's 90-second MVP is not the three-hour block. It is the **headline beat**: a shared object on screen (a tweet, a clip, a stat), two hosts who ask *different questions of the same object*, a clock that kills the topic before it is exhausted, and a land that could be the chyron.

The archetypal dynamic to give a language model is **not** Crossfire / First Take manufactured opposition. It is **complementary obsessions on a shared stimulus**: one host wants the thesis, the other wants the number; they agree on the card; they disagree on what the card means; they close before they have said everything. That is already latent in the Conductor brief's UNIT / RIVET contract (reason vs number). PHASEONE[lol] and deb are the character-bible version of the same split.

Tried-and-true production, from PTI through morning-show rundowns, is mechanical: a rundown of timed topics, alternate who opens, graphics as evidence rather than narration, bumpers as free minutes, teases that sell the next block, and a ritual open/close so the show has a body even when the content is improvised.

---

## 1. How TBPN actually structures a day

### 1.1 The three-hour rundown

From the Television Academy interview with John Coogan and Dylan Abruscato (June 2026):

| Block | Clock (PT) | Job |
| :---- | :---- | :---- |
| Hour 1 | 11:00–12:00 | John and Jordi reacting to the news of the day and the timeline. "Very news-driven." |
| Hour 2 | 12:00–1:00 | One or two Tier-1 conversations. Guests are often news-driven too (the example given: Dylan Field and Brian Chesky the previous day). |
| Hour 3 | 1:00–2:00 | Lightning round: "quick-hitting fundraise announcements, product news and talks with up-and-coming early-stage founders." |

That maps onto three *kinds* of segment, not three lengths:

1. **Timeline react** — two hosts, a feed, short clocks, high topic count. This is Runtime's MVP (`timeline_react`, 90s).
2. **Guest two-way** — still two hosts, but the third voice is the story. Deferred.
3. **Lightning / Big Finish** — many objects, one or two lines each. The PTI analogue is the last 60 seconds of the show. Cheap, clippy, and a natural place to hide generation delay behind a card.

Hays has estimated they cover "somewhere between 50 and 100 topics" in a three-hour session. That is 2–4 minutes average if they were even; they are not. Hour one is faster. Hour two is slower. Hour three is faster again. Runtime should treat 90 seconds as a *headline*, not a deep dive.

### 1.2 What they say they are copying

They are explicit that they do not reverse-engineer ESPN shot-by-shot. Coogan: it is "more spiritual: What if we brought a lot of high energy and lightheartedness to the coverage of business?" The steal is the *attitude toward the ticker*, not the camera plot.

Concrete SportsCenter moves that show up anyway:

- Personnel moves as trades and poaches. NYT quotes on-air graphics of the form "Jian Zhang POACHED from Apple to go to Meta" and "BREAKING: Ilya Sutskever… has updated his profile pic." The joke is treating a LinkedIn change as a mid-season trade.
- High-energy stings as punctuation. Coogan mentions ringing a gong. Runtime already budgets bake-once stings and ad reads as free show-minutes.
- A show built for clips, not for sitting through. RockWater's post-acquisition writeup: the three-hour format exists to mint dozens of clippable moments for X. The land of a 90-second segment *is* the clip.

### 1.3 How the two hosts generate talk

Not by splitting "funny" and "serious." By splitting **what they obsess over**.

Jackson Dahl's Dialectic interview (Nov 2025) is the clearest primary on the partnership:

- **Complementary obsessions.** "John loves technology more. I love business more." John ran a YouTube channel and obsesses over production. Jordi ran a digital ad business and drives the commercial side. Dahl's phrase: "Complementary obsessions multiply."
- **Pre-game is the script.** They meet at 6:30am, before the 11am live show. Coogan on the daily newsletter: "I've never had writer's block because I'm just transcribing the discussion we already had." The live hour is a performance of a conversation that already happened. Runtime's Segmenter *is* that 6:30am. The Writer should not be discovering the question on take 1.
- **Golden retriever mode** (named by Coogan, used on guests). Show up happy, friendly, and — in Hays's word — dumb. Specifically not the interviewer signalling he is the smartest person in the room and intends to catch you. This is a guest tactic, not a two-host tactic. For BOT1/BOT2 riffing on a card, do not make both hosts golden retrievers or the segment has no teeth.
- **High production, low conversation.** Mahogany desk, suits, multi-cam *and* memes, live tweets, sarcastic quips. Dahl: "Formal enough to feel trustworthy while casual enough to be accessible." Runtime already split this in half: OBS furniture is the network, the generated two-shot is the group chat.
- **The chat as a third host.** Abruscato: you could move the desk, graphics, guests, and hosts onto a TV channel and it might look the same, "but without John and Jordi's relationship with the live chat, it wouldn't be the same show." Chat has broken news, corrected an OpenRouter chart live, and once forced them to scrap a booked AI-researcher lineup for breaking news. Runtime v1 cannot let chat *steer* (adversarial input). Displaying it is nearly free; influence is v2. The production lesson still holds: a live show that cannot be interrupted by the room feels taped.

### 1.4 What TBPN is *not*

They "don't consider themselves journalists" and identify as "tech-positive" (NYT, via subsequent coverage). The interesting discussion is not adversarial interviewing. It is two insiders handicapping a league they love. If Runtime's Writer starts doing Crossfire, it will be copying the wrong ESPN show.

---

## 2. The segment as a lifecycle

A live talk-show "segment" is a timed room, not a topic. TV newsrooms already have the vocabulary. A rundown row has a slug, a type (VO, package, live, two-way), a duration, a back-time, and graphic cues. Blocks (A, B, C) are separated by commercials. Every block ends in a **tease**. A **bumper** is the branded breath between rooms. Mix long and short, package and chatter, or the hour dies.

That is the same object Runtime already named: the rundown YAML (`kind: timeline_react | bumper`, `target_len_s: 90`, `layout_plan`, `center`, `chyron_from`).

### 2.1 The headline beat (90 seconds)

This is the PTI unit, and it is the closest analogue to Runtime's Timeline React. *Pardon the Interruption* (ESPN, 2001–) puts two newspaper columnists at a desk, lists the day's topics on a rundown graphic, and puts a **countdown clock** on each one. Early PTI: most topics under 90 seconds; big stories 2–3 minutes. Entertainment Weekly in 2002 called the clock "what producers are always trying to do with television — make it so you can't stop watching."

Erik Rydholm, PTI's executive producer, on why the clock exists: by only talking a short time about each topic, they can come back to it tomorrow as the story develops "without exhausting everything the hosts would have to say." **Do not empty the well.** Runtime's 90s cap is not a limitation of H3. It is the format.

A 90-second headline beat has four phases. Runtime already names three of them on the Writer (`open / develop / close`). The fourth is production, not dialogue:

| Phase | Wall clock | Who | What happens |
| :---- | :---- | :---- | :---- |
| **Open** | ~5s (one take) | BOT1 or BOT2, alternating which host *starts* across segments | Name the object and the *question*. Not "what happened." The chyron is already up. Do not read the card. |
| **Develop** | ~70s (takes 2–n-1) | Alternate speakers unless `thought_open` | One conversational *move* per take: poke, number, reframe, callback. The listener's next line is a reaction, not a parallel essay. |
| **Hold / graphic** | 0–several takes, as needed | Director, not Writer | Card full, sting, bumper. This is how generation delay becomes a beat. SportsCenter already "lets the clip speak." |
| **Close** | ~5s (last take) | Whoever didn't open, or whoever has the land | One line that could be the chyron. Then a sting. Leave residue. |

The Writer already receives `segment_phase`. It does not yet receive *move type*, *which host's question this angle belongs to*, or *whether this is the land*. Those are the prompt upgrades.

### 2.2 The show as a stack of rooms

Legacy TV does not improvise the hour. It stacks rooms of different temperatures:

| Room | Legacy cue | Runtime analogue | Temperature |
| :---- | :---- | :---- | :---- |
| Cold open | Show open, 3–4 top-story tease | Baked bumper | High, wordless |
| A-block headlines | Top stories, live shots, short VOs | Several 90s timeline reacts | Fast |
| Bumper / ad | Commercial, sponsored sting | Bake-once ad read | Free |
| B-block | The piece you cannot get elsewhere | Longer develop, or a guest | Slower |
| Lightning | PTI Big Finish; SportsCenter High-5; TBPN hour 3 | Many objects, 1–2 lines each | Fastest |
| Outro ritual | "Same time tomorrow, knuckleheads" | Baked outro | Identical every night |

CUNY's TV-producing notes are blunt about the A-block: newest and most important, show open highlighting 3–4 top stories, live shots, then a 20–25s tease so people sit through the break. The B-block is not "less important"; it is where the show differentiates. For a Twitch desk show, the A-block is the feed; the B-block is the one post you actually have a thesis about.

SportsCenter's own ombudsman era is a pacing warning: they deliberately cut analyst segments, shortened sponsored bits, and aimed for "more and shorter segments. And smarter ones." Three-hour TBPN works because the *rooms* change. A language model that treats 90 seconds as a magazine essay will sound like a podcast, not a desk.

### 2.3 Rituals are load-bearing

PTI's body is the clock. Its *skeleton* is ritual:

- Open: "Pardon the Interruption, but I'm Mike Wilbon" → a sarcastic question to Kornheiser → "Welcome to PTI, boys and girls."
- Alternate who introduces each topic.
- Close: "We're out of time, we'll try to do better the next time" / "Same time tomorrow, you knuckleheads."
- Errors & omissions as a scheduled beat, so being wrong is cheap.

Siskel & Ebert's thumbs are the same idea: a binary land the audience can argue with in the hallway. Car Talk's "third half" of the show is a running joke that makes the last block a place.

Runtime should have a **segment sting** and a **land line**. It does not need catchphrases in the generated audio (H3 verbatim is already a risk). The OBS layer can carry the ritual: chyron in, on-air highlight, sting out.

---

## 3. How two hosts generate interesting discussion

Interesting two-host talk is almost never "two people who disagree." It is **two people who cannot ask the same question of the same object.**

### 3.1 Complementary information axes (the TBPN / Runtime default)

John wants the technology. Jordi wants the business. UNIT wants the reason. RIVET wants the number. PHASEONE[lol] shrugs at the thesis; deb will not let a shrug pass.

This is the strongest LLM-replicable dynamic because it is a *procedure*, not a personality:

- Host A, on every card: "Is there a thesis, or is this weather?"
- Host B, on every card: "What moved, by how much, for whom?"

They can agree that the tweet happened. They cannot both be satisfied by the same sentence. That produces ping-pong without anyone having to "play devil's advocate."

### 3.2 Shared-object commentary (Siskel & Ebert, and the riffing cousins)

Siskel and Ebert sat in the same theater, watched the same clips, and argued as "two friends who have seen a movie and have a difference of opinion." The Television Academy notes both men agreed the animated dialogue was "more compelling than criticism from a solitary voice." The Ringer: they boiled big observations into a few cutting sentences; they got heated; they were never mean.

The structural steal is the **shared object**. Runtime already puts the tweet in the center slot. The hosts should talk *about the card*, not *recite the card*. SportsCenter anchors get a monitor in the desk and a shot sheet; the skill is switching between "let the action speak" and "one word can describe this highlight" (Dan Patrick). If the chyron and the spoken line say the same thing, one of them is waste.

The riffing cousins — Mystery Science Theater, Statler and Waldorf, Beavis and Butt-Head — are the same machine with the satire turned up: two voices, one text, commentary rather than report. Runtime is a desk show, not a balcony show, but the *job* of the 90s MVP is closer to this than to a guest interview.

### 3.3 Double act: feed and punch (PTI, Car Talk, vaudeville)

The straight man is not "the boring one." He is the **feed**: he sets the premise, asks the question, holds the norm so the other can break it. Wikipedia's double-act history: the straight man existed in music halls because noisy rooms needed the setup repeated; he became the engineer of the joke.

PTI casts this on personality, not on job. Awful Announcing on the 20th anniversary: Kornheiser leans into curmudgeon and dated references; Wilbon is more willing to play the straight man. They were already friends at the *Washington Post*; Rydholm picked chemistry rather than manufacturing it. "It's like when best friends argue… they remain best friends."

Car Talk is the gentler version. Producer Doug Berman: Ray is "the voice of reason," Tom pursues philosophical tangents and the cackle. The automotive question is a pretext for the duo. When they lack a ready answer, they leave the car and enter the caller's life. For Runtime: the tweet is the pretext. If the Writer only explains the tweet, there is no show.

**Do not** make one host a clown. PHASEONE[lol]'s deadpan *is* the straight man. deb's lean-in *is* the comic/needle. That is already in the character bible. The Writer currently does not know that, because `WRITER_SYSTEM` only says "BOT1 and BOT2."

### 3.4 What not to copy: Embrace Debate

ESPN's *First Take* is the cautionary opposite. Jamie Horowitz turned a morning-variety show into all-debate after focus groups. The production rule, from coordinating-side interviews, is to find topics the two stars already feel strongly about — and, in practice, topics they split on. Consensus is a wasted segment.

That format needs heat, time, and two pundits whose brand *is* the fight. It also trained a generation of viewers to hear disagreement as performance. TBPN's actual energy is boosterish handicapping, not "Skip vs Stephen A." A 5-second H3 take cannot carry a blow-up. If the Writer is told to "disagree more," it will emit cable-news cadence that the pictures cannot support.

Clayman and Heritage's work on broadcast talk is the academic version of this warning. Classic news interviews run on **neutralism + adversarialness**, with pre-allocated Q/A. Talk shows run on **personalization + congeniality**. Panel formats let interviewees talk *to each other*, not only through the host. Runtime's two hosts are both hosts: there is no third-party allocator. The Writer must simulate **negotiated turn-taking** — adjacency pairs (assertion → challenge, poke → number, reframe → land) — without a moderator saying "your turn."

Georgakopoulou's work on disagreement in TV discussions: the host is the institutional regulator of allocation, duration, and topic; the audience is the real addressee; face is at maximum risk because the encounter is public. For two cartoon bots, "face" is the bit. They can needle. They should not humiliate. The Conductor brief already forbids mentioning they are AI; add: they never dunk on the *poster as a person*, only on the move.

---

## 4. The archetypal dynamic to give a language model

Lock this. It is a procedure.

**Name:** Complementary questions on a shared object.

**Cast:**

| | BOT1 / PHASEONE[lol] | BOT2 / deb |
| :---- | :---- | :---- |
| Axis | Thesis / weather | Number / stake |
| Stance | Dry, unbothered, will call a shrug a shrug | Curious, needling, will not let a shrug pass |
| Classic cue | Straight man, Wilbon, Ray Magliozzi, UNIT | Feed-breaker, Kornheiser, Tom, RIVET |
| Default open | Names the object as a feeling or a rumor | Asks for the timestamp, the dollar, the name |
| Forbidden | Explaining the tweet; saying it is an AI | Explaining the tweet; being merely "energetic" |

**Shared rules:**

1. The card is true. Do not invent facts. Do not argue about whether the post exists.
2. The argument is about *what the move means*.
3. One new idea per take. A thought is a finished conversational move, not a paragraph.
4. The next speaker must *use* the previous line (poke it, number it, reframe it, or land it). Parallel monologues are a failed segment.
5. Do not empty the well. Close while there is still an unsaid angle.
6. The chyron is the thesis, not the tweet's first clause.
7. Do not read the card aloud. The audience can see it. SportsCenter lets the clip speak.
8. Alternate who opens, across segments. Inside a segment, alternate unless `thought_open`.
9. Needle the move, not the poster. Congeniality, not Crossfire.
10. The land is one sentence that could survive as an X clip.

**Move vocabulary** (give this to the Writer as an enum, or as `angle_used` discipline):

| Move | Phase | Typical speaker | Example shape |
| :---- | :---- | :---- | :---- |
| `frame` | open | either | "If you have no thesis, is the move even information?" |
| `poke` | develop | BOT2 | "Then give me the timestamp." |
| `number` | develop | BOT2 | A demand for a quantity already in the facts. |
| `reframe` | develop | BOT1 | Changes the question without abandoning the card. |
| `callback` | develop | either | Reuses a phrase from earlier in the script. |
| `let_card` | develop | neither (Director) | Graphic beat. No new line. |
| `land` | close | opposite of who framed | "Fear has a ticker now, and it shrugs." |

The Conductor brief's worked example is already this format. Keep using it as the golden script.

---

## 5. Tried-and-true production approaches

These are the ones that survive contact with a 5-second clip model.

### 5.1 Rundown with clocks (PTI)

A visible list of topics plus a timer. Runtime cannot show a countdown on generated mouths, but the Director already has a segment clock. Use it: when the clock is in the last take, force `close`. When spend is hot, force `let_card` or a bumper. Rydholm's insight still applies: short clocks are how you get to come back tomorrow.

### 5.2 Topic package, not a script (TBPN 6:30am + Segmenter)

Do not write the 90 seconds in advance as dialogue. Write the **question, framing, and angles**. The live Writer fills thoughts 2 ahead. That is how PTI can go over the clock to land a final point, and how TBPN can rebuild an hour when chat revolts. Runtime already does this. The Segmenter's missing discipline is: **every angle must belong to one host's question.** An angle that both hosts could say is a wasted angle.

### 5.3 Alternate who introduces (PTI Headlines)

Wilbon and Kornheiser take turns opening topics. If BOT1 always frames, BOT2 is structurally the sidekick. Flip `next_speaker` on take 1 across segments.

### 5.4 Graphics as evidence, talk as comment (SportsCenter)

Shot sheets, desk monitors, "let the action speak." The tweet card, the chyron, and the spoken line are three channels. They must not be three copies. If H3 is late, `card_full` is not a failure — it is the VO while the tape rolls.

### 5.5 Mix of formats inside an hour (news producing)

Packages, VOs, live shots, two-ways. Runtime's mix is: wide two-shot, split, solo, card_full, hold, baked bumper. A segment that is wall-to-wall host talk is the cost ceiling, not the plan. TBPN runs stings and ads constantly; the two-host architecture doc already says a block that is half free is the difference between a demo and something you can leave running.

### 5.6 Tease, bumper, sting (universal)

End the room by selling the next room. Brand the breath. The visual research already proposed 0.8s utility wipes, 3s closers, 5s segment bumpers, 10s cold opens. Editorial use: a sting is the period at the end of a land. Without it, 90 seconds of talk feels like a podcast that someone forgot to stop.

### 5.7 Pre-record the one thing that cannot slip (PTI Five Good Minutes)

PTI tapes the guest before the rest of the show and trims. Guests are often booked *the day of*. For Runtime, guests are later; the analogue is **bake-once** (bumpers, ad reads, the land sting) and **Writer-ahead** (thoughts exist before the camera needs them). Never generate speculatively, but always have two thoughts in the queue.

### 5.8 Errors as a format (PTI Stat Boy)

A scheduled "we got that wrong" beat makes factual humility cheap. For an LLM that must not invent citations, the honest move is: if the facts do not support a number, BOT2 asks and BOT1 refuses. "Feeling is not a number" is an Errors & Omissions in one line.

### 5.9 Don't manufacture disagreement; pick topics that split on the two questions

First Take's producers look for topics the talent *feel*. PTI's producers look for a rundown that will move. Siskel and Ebert disagreed because they had actually seen different movies in the same movie. The Segmenter's job is to pick the post that is **commentable**, with a question that is **arguable**, and angles that **split**. "What happened" is a news VO. "If you have no thesis, is the move even information?" is a desk show.

### 5.10 High/low at once (TBPN's actual originality)

Network furniture, group-chat talk. Borrow laterally from sports television and F1 sponsorships, not recursively from other tech podcasts. Dahl quotes them: "My biggest critique of tech is that there's a really big world, and you can go and borrow from anywhere." Runtime already made this choice in the pictures. The Writer should make it in the talk: insider density, no explainers for people who are not in the room. TBPN makes content for ~200,000 people and refuses to soften the references. A Twitch cartoon desk can do the same.

---

## 6. Mapping onto Runtime as it exists

| Production idea | Already in the repo | Gap |
| :---- | :---- | :---- |
| Topic package (question, framing, angles) | Segmenter / `SegmentPackage` | Angles are not assigned to a host axis |
| Thought as a move, not a duration | Writer / `Thought` | No move enum; system prompt does not name the two questions |
| `open / develop / close` | Writer `segment_phase` | Close is not instructed to *land*; open is not instructed to skip reading the card |
| Alternate speakers | `segment.py` flips on `thought_open` | Take 1 always BOT1 |
| Chyron as headline | Planner emits `chyron` | Not constrained to be the thesis-of-the-land |
| Graphics beats as delay cover | Director layouts `card_full`, `hold` | Writer does not know a `let_card` beat exists, so it may over-explain |
| Bumpers / stings as free minutes | Rundown `kind: bumper` | Need a sting-after-land convention |
| Two thoughts ahead | Writer pipeline | Fine |
| Complementary personas | Character bible + old UNIT/RIVET copy | `WRITER_SYSTEM` currently says only "BOT1 and BOT2" |

The cheapest prompt upgrade, when someone next touches Writer, is to restore the UNIT/RIVET questions onto PHASEONE[lol] and deb without putting those old names in the prompt:

- BOT1: thesis / weather. Dry. Will call a shrug a shrug.
- BOT2: number / stake. Needling. Will not let a shrug pass.
- Open: do not read the card. Ask the question.
- Close: one land line.
- Each line must be a reaction to the previous line.

Do not add Crossfire. Do not add guest-host "gotcha." Do not add catchphrases that H3 has to pronounce.

---

## 7. Sources

Primary and near-primary, actually retrieved:

- Mike Isaac, *The New York Times*, "What if SportsCenter and LinkedIn Merged?" / "How TBPN Became Silicon Valley's Newest Obsession," 11 Oct 2025. Quoted via [Talking Biz News](https://talkingbiznews.com/media-news/whats-behind-the-success-of-tbpn/) and [Securities Docket](https://www.securitiesdocket.com/2025/10/13/how-tbpn-became-silicon-valleys-newest-obsession-the-new-york-times/). Formula: Fantasy Football league; SportsCenter for the terminally online MBA; BREAKING poach graphics.
- Television Academy, [Why Top Tech Titans Talk to TBPN](https://www.televisionacademy.com/features/online-originals/tbpn-john-coogan-jordi-hays). Coogan on the "spiritual" SportsCenter comparison. Abruscato on the three-hour rundown.
- Jackson Dahl, [Breaking down the magic behind TBPN](https://jdahl.substack.com/p/breaking-down-the-magic-behind-tbpn) (Dialectic 33, 18 Nov 2025). 6:30am pre-game, complementary obsessions, lateral borrowing, newsletter as transcription.
- Dylan Abruscato, [LinkedIn on chat as co-host](https://www.linkedin.com/posts/dylanabruscato_the-new-york-times-called-tbpn-sportscenter-activity-7488282020633042945-worp). Chat corrections and rundown rebuilds.
- [Wikipedia: TBPN](https://en.wikipedia.org/wiki/TBPN). Hours, hosts, staff size, guest list. Treat acquisition claims as reported, not as format evidence.
- [Wikipedia: Pardon the Interruption](https://en.wikipedia.org/wiki/Pardon_the_Interruption). Headlines + clock, Five Good Minutes, Happy Time, Big Finish, alternate introductions, rundown graphic.
- Entertainment Weekly, [Pardon the Interruption](https://ew.com/article/2002/07/26/pardon-interruption/) (26 Jul 2002). 90-second clocks, rundown as can't-stop-watching.
- WTOP, [Behind the scenes at Pardon the Interruption](https://wtop.com/sports/2015/01/behind-scenes-pardon-interruption/). Rydholm on not exhausting topics; morning Google Doc; chemistry as opposites who are friends.
- Awful Announcing, [Happy 20th anniversary to PTI](https://awfulannouncing.com/espn/happy-20th-anniversary-pti-sports-show-that-changed-sports-talk.html). Straight man / curmudgeon cast.
- Sports Business Journal, [The 25 best sports studio shows: PTI](https://www.sportsbusinessjournal.com/Articles/2024/10/28/pardon-the-interruption/). Format that suits the personalities; clock and bell from day one.
- Youth Journalism International, [Inside ESPN's SportsCenter](https://youthjournalism.org/inside-espns-sportscenter/). Shot sheets, desk monitor, "one word can describe" vs let the action speak.
- ESPN ombudsman, via [espn.com print](https://www.espn.com/espn/print?id=3299217). More and shorter segments.
- CUNY J-school, [TV Newscast Producing](https://oer.journalism.cuny.edu/lesson-plan-tv-newscast-producing-week-1/). A-block, tease, B-block as differentiator.
- Cuez, [How to Create and Automate a TV Talk Show](https://cuez.app/blog/how-to-create-and-automate-a-talk-show/). Script → rundown → cue cards.
- Television Academy, [Siskel & Ebert & the Movies](https://interviews.televisionacademy.com/shows/siskel-ebert-the-movies). Dialogue more compelling than a solitary voice; disagreement as two friends.
- The Ringer, [How Gene Siskel and Roger Ebert Taught a Generation to Argue](https://www.theringer.com/2021/07/20/movies/gene-and-roger-episode-1-excerpt-creating-blueprint).
- Current, [Car Talk profile](https://current.org/1995/06/since-were-on-public-radio-we-might-as-well-have-fun/). Ray as reason, Tom as tangent.
- [Wikipedia: Double act](https://en.wikipedia.org/wiki/Double_act). Straight man as feed.
- Clayman & Loeb, [Conversation Analysis and News Interviews](https://oxfordre.com/communication/display/10.1093/acrefore/9780190228613.001.0001/acrefore-9780190228613-e-138). Neutralism / adversarialness vs talk-show personalization / congeniality.
- Clayman & Heritage, *The News Interview*, chapter on [panel interviews](https://doi.org/10.1017/cbo9780511613623.008). Interviewees talk to each other.
- SI, [Q&A with First Take leadership](https://www.si.com/more-sports/2014/06/23/first-take-media-circus-skip-bayless-stephen-smith). Topics the talent feel; it is a debate show.
- RockWater, [OpenAI Buys TBPN](https://wearerockwater.com/openai-buys-tbpn/). Clipping-native three-hour; ~50–100 topics (via Hays, as reported in adjacent coverage).

**Inference, marked:** 90s as a headline rather than a deep dive; assigning each angle to one host axis; `let_card` as a Writer-visible move; flipping take-1 speaker across segments; sting-after-land. These are recommendations, not claims TBPN or PTI documented in those words.

**Discounted:** merchtbpn.com "line-up" posts and similar SEO pages that invent call-in hours. Not used.

---

## 8. What I could not answer

- I did not watch a full TBPN episode end-to-end for this pass. Hour timings come from Abruscato's interview, not from a coded rundown.
- I could not retrieve the full NYT Isaac piece (paywall / fetch timeout). Quotes are from contemporaneous excerpts that match each other.
- Host-level split of *who says what* on TBPN is described as complementary obsessions, not as a documented "John always opens." Do not overfit.
- No public TBPN rundown software or clock graphic is documented the way PTI's is. Do not assume they run a visible PTI-style timer.
- Conversation-analytic transcripts of TBPN do not exist in the literature yet. The Clayman/Heritage mapping is by analogy.
