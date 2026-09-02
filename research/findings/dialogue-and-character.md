# Simulating realistic dialogue and two complementary voices

**Status:** Research brief for Runtime's chat harness (two HostMinds, last-line only) · **Date:** 31 Aug 2026

This is editorial research, not a visual lane. Named shows, game titles, and character-platform brands are cited here so a human can look them up. They must never enter a generation prompt. Steal the *move*, not the trademark, the cadence, or the display name.

Runtime already has the right skeleton: two `HostMind`s, a last-line contract, a move enum (`frame / poke / number / reframe / callback / question / land`), complementary jobs (BOT1 = thesis/weather, BOT2 = number/stake), a 120-character spoken line, and coverage that refuses to close after one bounce. What this brief adds is the production grammar those pieces are supposed to be imitating — from interactive drama, improv, practitioner character systems, and conversation analysis — without handing the Writer a script.

---

## Executive summary

Talk feels alive when a line is a **move on a shared object**, not a paragraph of personality. That is the result that survives Facade, Versu, Prom Week, Talk of the Town, Dwarf Fortress rumor-talk, and every working LLM character stack: the speaker has a job, the last utterance creates an obligation, and the next line *uses* that utterance. Chatbots fail the other way: they recap, they fold, they empty the well on turn 2, they treat "be charismatic" as an adjective.

The complementary-voices problem is older than language models. Two people on one object become interesting when they cannot ask the same question of it. Keith Johnstone's status work and the feed/punch double act are the same machine: a small, persistent gap, not manufactured opposition. Yes-and is the agreement that the card is real. Complementary status is the disagreement about what the card *means*. "Be funny" fails because it is a verdict. "Have a job" works because it is a procedure.

Practitioner character systems that actually ship — Anthropic's constitution / soul document, Character.AI definitions and lorebooks, SillyTavern / Tavern Card V2, AI Dungeon Story Cards, Inworld / Convai / NVIDIA ACE, Park et al.'s generative agents — converge on the same split: **standing views stay loaded; world facts stay on standby; goals may be hidden; speech is short and example-taught; the planner is not the speaker.** HostMind already encodes most of that. The remaining steal is discipline: do-not-fold, do-not-restate, coverage that stays open, callback as reincorporation, status as a tiny gap, specificity as the source of wit.

---

## 1. Games: what made talk feel alive vs chatbot

The systems that felt like talk, not like a helpdesk, did not generate "more personality." They generated **the next move in a social practice**, with private state the audience never hears.

### 1.1 Facade: joint lines, one beat, handlers that interrupt

Mateas and Stern's *Façade* (2005) is still the clearest demonstration that believable two-character talk is authored as **joint action**, not as two chatbots. Characters Grace and Trip are written in ABL (A Behavior Language). The atomic unit is the **joint dialogue behavior** (JDB): a tightly coordinated exchange of 1–5 lines, a few seconds long, that can change story state. A *beat* — larger than McKee's dramatic beat; roughly a minute — holds 10–100 JDBs around one narrative goal (redecorating as a fight; the Italy honeymoon as a secret). Only one beat is active. Handlers mix in or resequence when the player does a discourse act. The drama manager sequences beats; the characters perform them.

What felt alive: Trip and Grace talk *to each other* about a shared apartment and a failing marriage. They have complementary obsessions (control vs. taste; the trip vs. the marriage). They interrupt, they mix in, they do not recap the premise. What felt authored: the surface is not free generation. The aliveness is the **obligation to answer the last act** inside a beat that still has unused JDBs.

HostMind already has the JDB shape: one spoken line, a required `reply_to`, a named `move`. The Facade steal is not ABL. It is: the pair is the unit; the beat is not empty after one bounce; mix-ins (poke / number / reframe) are how you stay in the room.

### 1.2 Versu / Blood & Laurels: practices suggest, agents choose

Richard Evans and Emily Short's Versu is a simulationist drama built from **agents** and **social practices**. A practice (greeting, dinner, conversation) assigns roles and offers affordances; it never puppets the agent. Utility-based selection picks among suggestions. Multiple practices run at once — dinner *and* conversation — so a character is several roles simultaneously.

Short's 2013 implementation note is the part that maps onto a two-host desk:

- Conversation state is **whose turn, a set of salient topics, and a preferred speech-act** — not a single selected topic. An earlier prototype with one topic exhausted subjects mechanically. Expanding to a *set* of salient topics is what made talk fluid.
- Dialogue is authored as **quips**: text plus metadata (topics, follow-from, beliefs, emotions). A quip can be about several topics. Characters prefer to stay on topic unless enough narrative time has passed to drop it.
- Norms are real: respond when spoken to; respect salient topics. NPCs notice violations. The player may violate them.

*Blood & Laurels* (the largest Versu release) showed the same machine at banquet scale: NPCs keep talking to each other if you stay quiet; a poisoned guest still gets one or two lines before collapsing. Talk is a social practice with residue, not a Q&A form.

HostMind steal: `last_line` is the obligation. Coverage / topic-map beats are the salient-topic set. Do not collapse to one question and close.

### 1.3 Prom Week / Comme il Faut: volition is not the line

McCoy, Treanor, Samuel, Wardrip-Fruin, and Mateas's Comme il Faut (CiF), shipped in *Prom Week* (2012), is a playable social model. Characters do not pick lines. They form **volitions** for social exchanges from thousands of influence rules over relationships (friends / dating / enemies), networks (buddy / romance / cool), statuses, traits, and a cultural knowledge base. The player (or the sim) picks among top desires; the exchange then plays out and writes back into social state.

The design lesson from CiF 2 is explicit in the FDG 2010 writeup: driving social games from bare psychological needs was unintuitive. The system got better when it modeled **statuses and relationships** — what you are to the other person right now — rather than "be witty." Goffman and Berne are cited as inspiration. Wit is a trait that *weights* exchanges. It is not a prompt adjective.

HostMind steal: `soul` and `opinions` are standing volitions. `job` / `stance` are the current exchange. Do not prompt "be charismatic." Prompt the job that charisma would be in service of.

### 1.4 Talk of the Town: moves, obligations, subjective knowledge

Ryan, Mateas, and Wardrip-Fruin's Talk of the Town (AIIDE 2016; DiGRA dialogue-manager paper the same year) renders knowledge exchange as conversation. Three notions matter:

1. **Dialogue moves** — greet, ask about the weather, assert a proposition. A line performs a move.
2. **Conversational obligations** — "How are you?" obligates `answer how are you`. An unresolved obligation wins the next turn.
3. **Topics** — persist across lulls; they are not emptied by one successful answer.

Knowledge is subjective. NPCs believe what they have seen or been told; they propagate rumors; they can be wrong. Surface language is generated from annotated grammars (Expressionist / Productionist) *after* the manager has chosen the move. Planner first, speaker second.

HostMind already names moves and binds `reply_to`. The steal is obligation: if BOT2 asks for the number, BOT1's next line is an answer, a refusal, or a reframe — not a new essay.

### 1.5 Dwarf Fortress: rumor as the object, menu as the move

Dwarf Fortress conversations are not LLM talk and do not pretend to be. Adventure-mode talking (wiki: `Talking`) is a menu of **moves on known incidents**: bring up a rumor, inquire about troubles, state an opinion, express an emotion, tell a story. Rumors have witnesses, propagate when you leave a site, and are limited by what the speaker actually knows. Fortress-mode socializing trains skills (conversation, comedy, flatter, judge of intent) against personality, not against a "be funny" flag.

What felt alive in DF is the **world as a rumor mill** plus a hard move list. What felt dead is the menu itself — no adjacency, no feed. HostMind already has the move list. It should keep DF's honesty (you cannot number a fact you do not have) and ignore the menu cadence.

### 1.6 LLM NPC / roleplay stacks: memory and goals, still not a script

These are products, not drama engines. The ones that feel less like ChatGPT have the same split Facade already had: **identity always loaded, lore on trigger, hidden goals, short speech.**

| Stack | Always-on | On trigger | Hidden from the other speaker | Speech rule |
| :---- | :---- | :---- | :---- | :---- |
| Character.AI | Definition (identity, voice, rules) | Lorebook keywords | Motives in definition / lore, not dumped in greeting | Greeting is a scene, not a bio; short examples beat adjectives |
| SillyTavern / Tavern Card V2 | `description`, `personality`, `system_prompt` | `character_book` entries | `creator_notes` never sent; goals belong in description | `mes_example` teaches rhythm; `post_history_instructions` restates discipline after the chat |
| AI Dungeon | Plot Essentials, Author's Note, AI Instructions | Story Cards (ex–World Info) by trigger | Author's Note is style, not spoken | Memory Bank / auto-summary retrieve; do not reload the bible every turn |
| Inworld + NVIDIA ACE | Personality, cognition, backstory | Knowledge / contextual mesh | Goals, relationships, trust | ACE: perceive → plan → speak/act; memory via embeddings |
| Convai | Backstory, personality, speaking style | Knowledge Bank (RAG or in-context) | Narrative-design goals, guardrails | LLM + behavior trees; knowledge scoped so the NPC does not lecture |
| Park et al. generative agents (UIST 2023) | Identity paragraph | Memory stream (recency × relevance × importance) | Reflections and plans | Plan first, then a short reaction; ablations without planning eat lunch three times |

Shanahan, McDonell, and Reynolds (*Nature*, 2023) are the clean theoretical warning: an LLM is role-playing a simulacrum, not inhabiting a soul. The practical consequence for HostMind is the same as theirs: lock the role with a document and examples, then sample a line. Do not ask the model to "be" charismatic. Ask it to play a job.

AI Dungeon and Character.AI both say the same thing about lore: **do not put the well in the always-on prompt.** Character.AI's Lorebook launch post: "The best stories don't explain everything up front — they reveal the world as you go." That is the coverage rule. HostMind's facts and angles are the well. The spoken line is one cup.

---

## 2. Improv and comedy craft

Wit on a desk is not a personality trait. It is what happens when two people with jobs stay on one object.

### 2.1 Yes-and is the card; complementary status is the show

Tina Fey's *Bossypants* popularization (2011) is the version everyone knows: agree; yes-and; make statements; there are no mistakes. "Yes" means respect what your partner created. "And" means add something of your own. If BOT2 says "Then give me the timestamp" and BOT1 says "Yeah…", the scene dies. If BOT1 says "Feeling is not a number," that is yes-and: the demand is accepted as real, and a stance is added.

Yes-and is **not** "agree with the thesis." Fey is explicit that real life is full of no. The rule is: do not deny the *object*. HostMind already says the hosts agree the card is real. That is the yes. The and is each host's job.

Johnstone does not use "yes-and." He writes **accepting offers** vs **blocking**. Blocking is how LLM pairs become parallel monologues: each host starts a new essay. Accepting the last line as an offer is the last-line contract.

### 2.2 Status: a small, persistent gap

Keith Johnstone, *Impro* (1979), ch. 2: status is something you *do*, not a rank you *have*. There is no neutral status. The exercise that made scenes "authentic" was: get your status just a little above or below your partner's, and keep the gap minimal. The see-saw: I go up, you go down. Friends are people who have agreed to play status games together. "Normally we are forbidden to see status transactions except when there's a conflict. In reality status transactions continue all the time."

Manufactured Crossfire is a huge gap (hero vs villain). Complementary hosts are a **minimal gap**: dry vs needling, thesis vs number, unbothered vs will-not-let-a-shrug-pass. The laugh is the see-saw, not the insult.

Johnstone on wit: "The improviser has to realise that the more obvious he is, the more original he appears." Ordinary people search for an "original" idea because they want to be thought clever; they say fried mermaid when the audience wanted fish. "An artist who is inspired is being obvious… accepting his first thoughts." "If he wants to impress us with his originality, then he'll search out ideas that are actually commoner and less interesting."

That is why **"be funny" fails** and **"have a job" works**. Funny is a verdict the performer cannot aim at. A job (name the weather; name the stake) forces the obvious next move. Specificity is a side-effect of doing the job on *this* card, not of fishing for a quip.

### 2.3 Feed and punch; callbacks; constraint

The double-act history is mechanical. The straight man is the **feed**: he holds the premise so the other can break it. UCB's version is **game of the scene**: find the unusual thing, then spend the rest of the scene asking "if this is true, what else is true?" and "what is my honest reaction?" "Play at the top of your intelligence" means react as a real person would — not rattle trivia, not quip. Matt Besser: commit to playing it as real as possible. The straight man (voice of reason) makes the game legible. A wet-blanket "that's weird" is a block.

HostMind's cast is already this: BOT1 is the feed (weather until proven otherwise). BOT2 is the punch (name it or it is a vibe). Do not invert them into clown and announcer.

**Callbacks** are Johnstone's **reincorporation**: reuse what has already been introduced. That is why `callback` is a develop move and why `you_already_said` exists. A callback is not a recap of the card. It is a phrase from an earlier *line* brought back under new pressure.

**Constraint is the source of wit.** 120 characters, one move, last-line only, facts you may not invent: those are the room. Facade's JDB is a few seconds. PTI's clock is 90 seconds. A model told to "be witty" in an open essay will produce a monologue. A model told to number the last line in 120 characters will sometimes land a joke because the job is tight.

---

## 3. LLM character systems practitioners actually use

The stacks below are the ones people run, not the ones papers wish they ran. They agree more than they advertise.

### 3.1 Soul documents: written *for* the model, explain *why*

Anthropic published **Claude's Constitution** (2025–26; CC0) as the public successor to the internal "soul document." It is addressed to Claude. It is the final authority on intended character. The design claim, from Anthropic's own post and from Amanda Askell's interviews (TIME, The Verge): models do better when they understand *why* a behavior is wanted, not only *what* to output. The older 2023 constitution was a list of guidelines. The new one is a holistic identity document used in training and treated as living.

HostMind already has `soul` and `stance` on `HostVoice`. The steal is the constitution's method, not Claude's values: a short standing document that states the job, the reason for the job, and the tradeoff when jobs collide. "Treat news as weather until a control surface moved" is a soul line. "Be dry and charismatic" is not.

### 3.2 Character cards: show, don't adjective

**SillyTavern / Tavern Card V2** (`chara_card_v2`, spec by malfoyslastname, 2023; implemented in SillyTavern) is the de facto interchange format. Always-on strings: `description`, `personality`, `scenario`, `first_mes`, `mes_example`. Discipline after the thread: `system_prompt`, `post_history_instructions`. Lore on keys: `character_book`. `creator_notes` is for humans and is not sent.

**Character.AI** splits the same way. Official help: the Definition is the instruction manual (personality, backstory, speech, rules). Vague adjectives ("friendly," "complex") "don't give the AI anything to work with." Concrete trait → behavior pairs do ("Remembers everyone's name… changes the subject the moment anyone asks about hers"). Dialogue examples teach more than a paragraph of traits. The greeting is a *scene*, not a bio; two sharp lines beat two paragraphs. Lorebooks (2025–26 product) hold world facts on keywords so the definition is not stuffed with the well. Help Center rule of thumb: always-relevant → Definition; sometimes-relevant → Lorebook; this-chat-only → pinned memory.

**AI Dungeon** (Latitude help): Plot Essentials always in context; Story Cards (ex–World Info) enter on triggers; Memory Bank retrieves; Author's Note is style. Official advice: write Story Card entries in concise plain English; the AI does not see the title, only the entry.

The shared anti-pattern is the same: a novel in the always-on prompt, no examples, adjectives instead of jobs. The shared fix is: standing views + example rhythm + triggered facts + a last-turn reminder not to fold.

### 3.3 Hidden goals, relationship memory, planner ≠ speaker

Inworld's public Character Engine (NVIDIA ACE writeups; Lightspeed; Unreal runtime docs) splits **Character Brain** (personality, emotion, memory, goals, motivated actions) from **Contextual Mesh** (knowledge, narrative, safety, relationships). Goals and relationship/trust state are first-class and are not required to be spoken. NVIDIA ACE's own framing (GeForce / GTC 2024, later autonomous-character posts): perceive → cognize / plan → remember (RAG embeddings) → act/speak. Covert Protocol (Inworld + ACE, GDC/GTC 2024) is a detective game whose outcomes depend on NPC goals the player does not get as a briefing.

Convai (NVIDIA spotlight; official Character Crafting / Knowledge Bank docs): backstory + personality + speaking style always; Knowledge Bank as RAG or whole-context; narrative-design APIs for story goals; LLM conversation sitting on behavior trees so the NPC has a default job when the player is quiet.

Park, O'Brien, Cai, Morris, Liang, and Bernstein, *Generative Agents* (UIST 2023): memory stream, periodic reflection, recursive plans. The planning ablation is the one HostMind should remember: if you only ask "what do you say now?", the agent repeats the same satisfying action. A plan (here: topic-map beat + job + coverage) is what keeps the next line from being lunch again.

HostMind is already planner-vs-speaker: the topic map / beat / coverage is the plan; the model only speaks. Do not let the speaker rewrite the plan. Do not let the plan appear in the spoken line.

### 3.4 Don't fold / don't people-please

Sharma, Tong, Korbak, et al., *Towards Understanding Sycophancy in Language Models* (Anthropic; ICLR 2024): RLHF assistants match user beliefs over truth across free-form tasks. Human preference data and preference models both reward the match. Sycophancy is a general behavior of feedback-trained models, not a one-off jailbreak.

For two HostMinds, the "user" is the other host's last line. The default RLHF move is to agree, recap, and soften. That is folding. Practitioner cards fight it with **positive constraints** (Character.AI / community template consensus: write what the character *does*, not a stack of "never"): "Ask for the number. If they shrug, ask again from a different fact. Do not adopt their weather as your thesis." SillyTavern's `post_history_instructions` exists specifically to restates this *after* the chat, because the model drifts toward helpfulness as the thread grows.

A second, newer result (open-weight roleplay study, arXiv 2604.10733, 2026): persona agreeableness predicts sycophancy. Do not put "warm, agreeable, charismatic" on either host.

---

## 4. Broadcast talk, as moves only

Named shows appear here so a human can look them up. They are **not** a voice to imitate. See §8.

Two-host desk talk that works is almost never "two people who disagree." It is **two people who cannot ask the same question of the same object.** The adjacency-pair shapes (not the trademarks) are:

| Pair (first → second) | Desk meaning | HostMind move |
| :---- | :---- | :---- |
| Assertion → challenge | "That's weather" → "Then give me the timestamp" | `frame` / `reframe` → `poke` |
| Demand → number or refusal | "What moved?" → a quantity, or "Feeling is not a number" | `poke` → `number` |
| Number → reframe | The stake is named; the thesis is still weather | `number` → `reframe` |
| Offer → callback | A phrase from earlier comes back under pressure | `callback` |
| Closing implication → land | One line that could be the chyron | `land` |

That is Sacks/Schegloff adjacency, not a show bible. Complementary obsessions (thesis vs number) are the TBPN / UNIT-RIVET / PHASEONE–deb procedure already in the sibling brief. Shared-object commentary (two voices, one text, comment not recitation) is the Siskel & Ebert / riffing-cousin *job*. Feed and punch is the double-act *job*. Embrace-Debate manufactured opposition is the failure mode (§6).

Clayman and Heritage's news-interview norms are **neutralism + adversarialness** with pre-allocated Q/A. Talk-show interview norms (Loeb, under Clayman/Heritage; Loeb 2015 on celebrity talk shows) are **personalization + congeniality**. Runtime's two hosts are both hosts. There is no interviewer. Simulate **negotiated turn-taking**: each line is a second pair-part to the last line and a first pair-part for the next. Congeniality means needle the *move*, not the poster. Adversarialness belongs to the jobs, not to the relationship.

---

## 5. Academic, short enough to use

**Adjacency pairs** (Schegloff & Sacks 1973; Schegloff 2007): two turns, two speakers, relatively ordered (first pair-part / second pair-part), type-fitted. Given an FPP, a type-fitted SPP is **conditionally relevant**. The next turn is how participants show they understood the last (the next-turn proof procedure; Sacks, Schegloff, Jefferson 1974). HostMind's `reply_to` is that proof. A parallel essay is a missing SPP.

**Preference organization** (Pomerantz 1984; Schegloff 2007; Pomerantz & Heritage overviews): alternatives are not equal. Preferred SPPs (agreement, grant, acceptance) come fast and simple. Dispreferred SPPs (disagreement, refusal) come with delay, preface, account. This is structural, not psychological. For the desk: BOT1 refusing to treat a vibe as a number *should* be short and preferred in *that* pair-type ("Feeling is not a number"), because the job makes refusal the aligned action. Do not mark every disagreement with cable-news hedging. That is fake dispreference.

**Goffman face** (*On Face-Work*, 1955; *Interaction Ritual*, 1967): face is "the positive social value a person effectively claims for himself by the line others assume he has taken." Face-work keeps conduct consistent with that line. On a public desk, face is the bit. They can needle. They should not humiliate the poster-as-person. Folding is a face-saving offer to the other host ("you're right, it's a thesis") that kills the job.

**Broadcast vs talk-show** (Clayman & Heritage, *The News Interview*, 2002; Loeb 2015): news interview = neutralism + adversarialness, host allocates turns. Talk show = personalization + congeniality; panel formats let people talk *to each other*. Two HostMinds are a panel of two hosts. No third allocator. The last line *is* the allocation.

---

## 6. What fails

These are the failure modes that show up in Facade-without-beats, in RLHF assistants, and in desk-show drafts that asked the model to "be more interesting."

1. **Sycophancy / folding.** The second host adopts the first host's thesis so the segment can "resolve." Sharma et al.: this is the rewarded move. A fold looks polite and reads as death. BOT2 must still want the number after BOT1 calls weather. BOT1 must still want a thesis after BOT2 names a dollar.
2. **Parallel monologues.** Two essays that could be swapped. No `reply_to` in spirit. Versu would call it a dropped obligation. CA would call it a missing SPP.
3. **Info-dumping the well on turn 2.** Reciting the card, the chyron, and three facts. Character.AI and AI Dungeon both warn that always-on lore becomes a lecture. The audience can see the card.
4. **Manufactured Crossfire.** "I strongly disagree" with no job split. First Take's production rule (topics the talent already split on) needs heat, time, and brands built on the fight. A 120-character last-line turn cannot carry a blow-up. It will emit cable cadence the pictures cannot support.
5. **"Be charismatic" as an adjective.** CiF already learned this: traits without exchanges do not play. Johnstone: aiming at original / clever / funny produces mermaid. Character.AI help: adjectives do not give the model anything to do.
6. **Long essays.** Facade JDBs are seconds. HostMind is 120 characters. A paragraph is a podcast, not a desk.
7. **Recapping the card / the other speaker.** Restating is a fake SPP. It looks like listening and advances nothing. Ban: do not quote the last line back; do not read the chyron; do not summarize `you_already_said`.
8. **Closing after one bounce.** Versu's single-topic prototype. Coverage that treats `landed_own_job` on take 2 as `beat_exhausted`. Runtime already refuses this (`MIN_EXCHANGES_BEFORE_EXHAUST = 6`). Keep that number sacred.
9. **Planner-as-speaker.** Generative-agents ablation: no plan, repeated satisfying action. If the spoken line restates the beat job or the throughline, the planner has leaked.

---

## 7. What to steal for HostMind

Concrete checklist. Implement as data and validators, not as "please be interesting."

### 7.1 Move enum (already named; keep it closed)

`frame | poke | number | reframe | callback | question | land`

Rules that belong next to the enum, not in a vibe paragraph:

- First line (`last_line` null): `frame` only. Ask the host's question of the object. Do not read the card.
- Every later line: `reply_to` equals the last line's text exactly. `move` ≠ `frame`.
- The line must be a type-fitted SPP: poke the claim, number it, reframe the question, callback a prior phrase, ask a job-shaped question, or land.
- `land` is allowed only when coverage says the beat may close. One sentence. Residue left on the table.
- One new idea per line. 120 characters. No stage directions, no quotes, no prefix.

### 7.2 Standing views: soul / opinions / stance / job

Load every turn, keep them short, write them as procedures:

| Field | BOT1 | BOT2 |
| :---- | :---- | :---- |
| Job | Thesis or weather. Is there a control surface, or is this climate? | Number / stake. What moved, by how much, for whom? |
| Stance | Dry. Will call a shrug a shrug. | Needling. Will not let a shrug pass. |
| Soul | Would rather be bored than impressed. Weather until proven otherwise. | If it cannot be named, counted, or assigned, it is a vibe. |
| Opinions | Standing takes (3–5), specific, reusable. Not adjectives. | Standing takes (3–5), specific, reusable. Not adjectives. |

Soul explains *why*. Opinions are the CiF-style influence rules. Job is the current exchange. Do not merge them into "personality: witty."

### 7.3 Coverage that does not close after one bounce

- A beat stays open until both jobs have actually landed **and** a minimum exchange count has passed (Runtime: 6 before exhaust, 8 before complete). Do not trust `beat_exhausted` on an early turn.
- Salient-topic set, not a single question: unused angles remain live. Versu's fix.
- `you_already_said` is a ban list, not a recap list. Do not restate those lines.
- Facts stay in the user payload (the lorebook). They are not spoken unless the move is `number` and the quantity is in the facts.
- Leave residue. PTI's clock exists so you can come back tomorrow.

### 7.4 Do-not-fold rules (positive constraints)

Write them as things the host *does*:

1. Agree the card exists. Do not agree what it means.
2. If the other host lands their job, do not adopt it as yours. Answer it from your job.
3. A shrug is not consensus. BOT2 asks again from a different fact. BOT1 may refuse a number that is not in the facts.
4. Do not praise the other host. Do not soften a poke into a hedge.
5. Do not people-please the imagined audience. Insider density; no explainer.
6. Needle the move, not the poster. Congeniality is the relationship; the fight is the jobs.

### 7.5 Callback, status, specificity

- **Callback:** reuse a short phrase from an earlier spoken line (not from the card). Johnstone reincorporation. Prefer this over a new metaphor.
- **Status:** keep a *minimal* gap. BOT1 slightly high-status dry; BOT2 slightly low-status lean-in (or the reverse across segments). Do not escalate to humiliation. Do not flatten to two golden retrievers.
- **Specificity:** the obvious noun already in the facts (the cluster, the timestamp, the admin bit). No fried mermaid. No "this space." No "the broader conversation."
- **Feed / punch:** BOT1 holds the norm (weather). BOT2 breaks it (stake). Alternate who *frames* across segments so neither is structurally the sidekick. Inside a segment, alternate speakers.

### 7.6 Planner vs speaker

- Topic map / beat / coverage / facts = planner. HostMind = speaker.
- The speaker sees last line, own job, soul, opinions, current beat, coverage flags. The speaker does not invent a new throughline.
- Hidden from the spoken line: beat `done_when`, coverage internals, the other host's soul, the word "card," any claim to be AI.
- If the facts cannot support a number, BOT2's move is `question` or `poke`, and BOT1's legal SPP is a refusal. That is Errors & Omissions in one line.

---

## 8. Never put in a generation prompt

These tokens teach the model to impersonate. They belong in research docs and in human rundowns only.

- **Named shows and franchises:** TBPN, PTI / *Pardon the Interruption*, SportsCenter, First Take, Crossfire, Siskel & Ebert, Car Talk, *Mystery Science Theater 3000*, Statler and Waldorf, Beavis and Butt-Head, any ESPN / NPR / late-night show name.
- **Named hosts and display names:** John Coogan, Jordi Hays, Mike Wilbon, Tony Kornheiser, Skip Bayless, Stephen A. Smith, Gene Siskel, Roger Ebert, Tom and Ray Magliozzi, UNIT, RIVET, PHASEONE[lol], deb — and any other on-air or bible display name. The prompt speakers are `BOT1` and `BOT2`.
- **Catchphrases and ritual copy:** "Pardon the Interruption," "Same time tomorrow, knuckleheads," thumbs up/down as a named bit, "third half of the show," gong-as-TBPN, "who ya got" as a catchphrase.
- **Voice clones and likeness:** any instruction to sound like a named person, to match a show's cadence, or to use a cloned voice. H3 gets `voice_direction` from the pack, not a celebrity target.
- **Platform / engine brand voice:** "talk like Character.AI," "SillyTavern style," "Inworld NPC," "Facade Grace/Trip."
- **Adjective soup:** charismatic, witty, hilarious, iconic, unhinged, based, riffing in the MST3K sense.
- **The card as script:** do not paste the tweet text into the system prompt as something to read aloud. Do not tell the model to "explain the post."
- **Writer-script leftovers:** a pre-written dialogue, a joke list, a "say this then that" rundown. HostMind is last-line only.

Describe the move ("demand the quantity already in the facts") never the show ("do a PTI rundown").

---

## 9. Mapping onto Runtime as it exists

| Steal | Already in the repo | Gap |
| :---- | :---- | :---- |
| Last-line obligation / SPP | `last_line`, `reply_to` must match | No validator that the *text* uses the last line (only that the field copies it) |
| Move enum | `MOVES` in `discuss.py` | Fine; do not grow it with `disagree` or `banter` |
| Complementary jobs | `STANCE`, beat `bot1_job` / `bot2_job` | Keep thesis/weather vs number/stake; do not rename in-prompt |
| Soul / opinions | `HostVoice.soul`, `.opinions`, baseline defaults | Ensure packs ship concrete opinions, not adjectives |
| Coverage floor | `MIN_EXCHANGES_BEFORE_EXHAUST = 6`, complete = 8 | Do not lower these to "feel snappier" |
| Planner ≠ speaker | Topic map + coverage vs HostMind | Speaker must not echo `throughline` / `done_when` |
| Short line | `MAX_LINE_CHARS = 120` | Fine |
| No card recap | `HOST_SYSTEM` already forbids recap / chyron | Add: do not restate the other speaker |
| Do-not-fold | Not named | Add positive rules on each voice (`rules` / soul) |
| Callback | Move exists | Prefer reuse of `you_already_said` *phrases*, never full-line recap |
| Status gap | Implicit in default soul | Make the gap explicit as dry vs needle, not funny vs serious |
| Hidden goals | Jobs live in the user payload | Never speak the job name ("as the number host…") |
| Triggered lore | Facts in the user payload | Speak a fact only on `number` / grounded `poke` |

The cheapest next discipline, when someone next touches HostMind (not this brief): restore do-not-fold and do-not-restate as `rules` on each voice, and treat a line that could be said by either host as invalid.

---

## 10. Sources

Primary and near-primary, actually retrieved:

- Mateas & Stern, [Structuring Content in the Façade Interactive Drama Architecture](https://doi.org/10.1609/aiide.v1i1.18722) (AIIDE 2005); [Writing Façade](https://users.soe.ucsc.edu/~michaelm/publications/mateas-second-person-2007.pdf); [A Behavior Language](https://users.soe.ucsc.edu/~michaelm/publications/mateas-aaai-symp-aiide-2002.pdf). JDB 1–5 lines; beat of 10–100 JDBs; handlers / mix-ins.
- Evans & Short, [Versu—A Simulationist Storytelling System](https://doi.org/10.1109/tciaig.2013.2287297) / [PDF](https://www.cs.uky.edu/~sgware/reading/papers/evans2014versu.pdf); [The AI Architecture of Versu](https://versu.com/wp-content/uploads/2014/05/versu.pdf). Practices suggest; agents choose.
- Emily Short, [Versu: Conversation Implementation](https://emshort.blog/2013/02/26/versu-conversation-implementation/) (26 Feb 2013). Salient-topic *set*; quips; speech-act + next speaker. [Conversation as Gameplay](https://emshort.blog/2019/01/20/conversation-as-gameplay-talk/) on *Blood & Laurels*.
- McCoy, Treanor, Samuel, Wardrip-Fruin, Mateas, [Comme il Faut](https://ojs.aaai.org/index.php/AIIDE/article/view/12454) (AIIDE 2011); [Social Story Worlds With Comme il Faut](https://cs.uky.edu/~sgware/reading/papers/mccoy2014cif.pdf); [Prom Week: Social Physics as Gameplay](http://www.ben-samuel.com/wp-content/uploads/2015/09/FDG-2011-Prom-Week-Social-Physics-as-Gameplay.pdf) (FDG 2011); CiF 2 / Goffman shift: [INT 2010](http://www.ben-samuel.com/wp-content/uploads/2015/09/CiF-FDG2010-IntelligentNarrativeTechnologies3.pdf).
- Ryan, Mateas, Wardrip-Fruin, [Characters Who Speak Their Minds](https://ojs.aaai.org/index.php/AIIDE/article/view/12877) (AIIDE 2016); [A Lightweight Videogame Dialogue Manager](https://doi.org/10.26503/dl.v2016i1.798) (DiGRA/FDG 2016). Moves, obligations, topics.
- [Dwarf Fortress Wiki: Talking](https://dwarffortresswiki.org/index.php/Talking); [Rumor](https://dwarffortresswiki.org/index.php/DF2014:Rumor); [Social skill](https://dwarffortresswiki.org/index.php/Social_skill). Menu of moves on known incidents; rumor propagation.
- Shanahan, McDonell, Reynolds, [Role play with large language models](https://doi.org/10.1038/s41586-023-06647-8), *Nature* 623 (2023). Simulacra, not souls.
- Park et al., [Generative Agents](https://doi.org/10.1145/3586183.3606763) (UIST 2023) / [arXiv](https://doi.org/10.48550/arxiv.2304.03442). Memory, reflection, planning; planning ablation.
- Anthropic, [Claude's Constitution](https://www.anthropic.com/constitution); [announcement](https://www.anthropic.com/news/claude-new-constitution). Soul-document method; written for the model. Coverage: [TIME](https://time.com/7354738/claude-constitution-ai-alignment/), [The Verge](https://www.theverge.com/ai-artificial-intelligence/865185/anthropic-claude-constitution-soul-doc).
- Sharma, Tong, Korbak, et al., [Towards Understanding Sycophancy in Language Models](https://www.anthropic.com/research/towards-understanding-sycophancy-in-language-models) (ICLR 2024) / [arXiv](https://arxiv.org/abs/2310.13548).
- [Tavern Card spec V2](https://github.com/malfoyslastname/character-card-spec-v2/blob/main/spec_v2.md); SillyTavern `spec-v2` types. Character.AI: [Character Definition](https://support.character.ai/hc/en-us/articles/50609183646875-5-Character-Definition), [Lorebooks](https://support.character.ai/hc/en-us/articles/52739596326811-Lorebooks), [What makes a good Lorebook](https://support.character.ai/hc/en-us/articles/52739683169179-What-makes-a-good-Lorebook), [Lorebook launch](https://blog.character.ai/lorebook/).
- AI Dungeon help: [Story Cards](https://help.aidungeon.com/faq/story-cards), [Memory System](https://help.aidungeon.com/faq/the-memory-system).
- NVIDIA, [ACE / Covert Protocol](https://www.nvidia.com/en-us/geforce/news/nvidia-ace-gdc-gtc-2024-ai-character-game-and-app-demo-videos/); [ACE autonomous characters](https://www.nvidia.com/en-gb/geforce/news/nvidia-ace-autonomous-ai-companions-pubg-naraka-bladepoint/); [In-Game Inferencing SDK](https://developer.nvidia.com/blog/bring-nvidia-ace-ai-characters-to-games-with-the-new-in-game-inference-sdk/); [ACE Agent NPC bots](https://docs.nvidia.com/ace/ace-agent/4.1/sample-bots/gaming-npc-bot.html). Inworld layers via NVIDIA + [Lightspeed](https://lsvp.com/stories/inworld-ai-npcs-character-engine/). Convai: [NVIDIA spotlight](https://developer.nvidia.com/blog/spotlight-convai-reinvents-non-playable-character-interactions/), [Knowledge Bank](https://docs.convai.com/api-docs/convai-playground/character-customization/knowledge-bank).
- Keith Johnstone, *Impro: Improvisation and the Theatre* (1979), status chapter and spontaneity / "be obvious" passages; quoted via [Fluid Self excerpts](https://fluidself.org/books/art/impro) and matching secondary quotations.
- Tina Fey, *Bossypants* (2011), "Rules of Improvisation…"; widely reprinted excerpt.
- UCB game / top-of-intelligence: Besser via [Vice / practitioner writeups](https://tomsimprovpages.wordpress.com/2019/06/21/playing-to-the-top-of-your-intelligence/); game questions in [UCB teaching notes](https://funnyshmunny.wordpress.com/ucb-the-game/).
- Schegloff & Sacks, "Opening up Closings" (1973); Schegloff, *Sequence Organization in Interaction* (2007); Sacks, Schegloff, Jefferson, "A simplest systematics…" (*Language*, 1974). [EMCA Wiki: adjacency pair](https://emcawiki.net/Adjacency_pair).
- Goffman, "On Face-Work" (1955), reprinted in *Interaction Ritual* (1967): face as positive social value claimed by a line.
- Clayman & Heritage, *The News Interview* (CUP, 2002). Loeb, [Talk Show Talk](https://escholarship.org/uc/item/4p98t7f7) (UCLA dissertation); Loeb, "The celebrity talk show: Norms and practices" (*Discourse, Context & Media*, 2015) — personalization + congeniality vs neutralism + adversarialness.
- Sibling brief: [talk-show-segment-lifecycle.md](talk-show-segment-lifecycle.md) for the desk-show contract those broadcast names actually support.

**Inference, marked:** do-not-fold as a HostMind `rules` item; treating a line either host could say as invalid; callback as reuse of an earlier spoken phrase rather than of the card; status as dry-vs-needle rather than funny-vs-serious; "have a job" as the operational translation of Johnstone's "be obvious" plus UCB's game. These are recommendations, not claims the cited systems used those words.

**Discounted:** SEO character-card blogs that invent "official" Character.AI templates; merch and fandom wikis for named shows (see sibling brief); any Inworld "paper" that is only a funding announcement.

---

## 11. What I could not verify

- I did not find a peer-reviewed Inworld architecture paper comparable to Evans & Short or Mateas & Stern. Inworld claims above are from NVIDIA, Lightspeed, and product docs. Treat layer names (Brain / Mesh) as vendor vocabulary, not as a standard.
- I could not retrieve a first-party Tarn Adams design essay that theorizes DF conversation; the wiki is accurate about the menu and rumors, not about authorial intent.
- Johnstone's exact wording is "be obvious" / don't search for an "original" idea to seem clever. The desk slogan "don't try to be funny; have a job" is a translation, not a quotation.
- Character.AI's internal model and the precise injection order of Definition vs Lorebook vs memory are not fully public. Field-level advice above is from official help and the Lorebook launch, not from a leaked prompt.
- SillyTavern prompt assembly order varies by build. The V2 *fields* are stable; what a given install injects is not.
- The 2026 agreeableness-and-sycophancy roleplay study (arXiv 2604.10733) is a preprint on open-weight models. Use Sharma et al. 2024 as the load-bearing citation; treat the later result as supporting, not as Character.AI-specific.
- I did not run HostMind against a live model for this pass. The mapping table is from `discuss.py` / `topic_map.py` as they exist on 31 Aug 2026.
- Conversation-analytic transcripts of LLM two-host desks do not exist. The Schegloff / Goffman / Clayman mapping is by analogy.
