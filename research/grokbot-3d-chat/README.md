# 3D grokbot chat — exploration

**Status:** Prototype, not the show. **Date:** 3 Sep 2026  
**Parent plan:** PR #37 (`cursor/agent-podcast-brief-4bcb`, `Desk Show — Embodied Agent Podcast.md`). That plan stays on its branch. This is the first playable face.

The lock is still [`SHOW.md`](../../SHOW.md): solo PHASEONE[lol], chat as the other voice, record only, fal off the live path. This folder does not change that lock.

## What this is

One HostMind-shaped speaker, one mouthless 3D face, a typed chat well in the empty right third.

- **Face:** Zdog sphere, charcoal, amber pill eyes, dashed construction equator that turns in 3D. Same squash-stretch talk and eye pulse as [`research/mocks/grokbots.html`](../mocks/grokbots.html). No mouth. No visemes. No second (deb) bot.
- **Chat:** You type. The host goes `thinking`, answers, `talking` while the line is spoken, then `listening`.
- **Bus:** Brain ≠ voice ≠ body. The brain emits `{ text, performance: { emotion, energy, thinking } }`. A speech-rate clock drives squash depth. The renderer has no LLM.
- **Brain:** Stub replies always work. Optional local server can call the existing text model (`TEXT_*`) if keys are present. No fal. No OBS. No `run-list`.

Closed emotion enum, copied from the SVG mock: `idle`, `talking`, `thinking`, `listening`, `laugh`, `happy`, `skeptical`.

## Open it

From the repo root, stub-only (no keys):

```bash
python3 -m http.server 8765 --directory research/grokbot-3d-chat
```

Then open [http://127.0.0.1:8765/](http://127.0.0.1:8765/).

Or open `index.html` as a file. The stub brain still drives the face.

Optional live brain (uses `TEXT_BASE_URL` / `TEXT_API_KEY` / `TEXT_MODEL` if set; otherwise the same stub). Does not read `FAL_KEY`.

```bash
python3 research/grokbot-3d-chat/server.py
```

Lines stay desk-show short (≤ 220 characters), last-line obligation, no meeting recap. Display names stay on the furniture; they do not enter the prompt.

## What it is not

Not the current show. Not a two-host discuss rebuild. Not a replacement of the PR #37 plan doc. Leave that PR open.
