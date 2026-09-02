# Design brief — Desk Show broadcast CG

You are designing the **deterministic 1080 graphics layer** for Desk Show, a two-host live desk programme. Another system generates a 1344×768 two-shot of the hosts. You never draw the hosts. You draw everything that makes the frame read as television.

This brief is the creative contract. The file-level contract is [ASSET_MANIFEST.md](ASSET_MANIFEST.md). The JSON the live overlay must accept is [overlay-state.schema.json](overlay-state.schema.json). Pixel grammar lives in [../runtime-graphics-spec.md](../runtime-graphics-spec.md). A layout lock (with two known revisions) is [../mocks/production-view.html](../mocks/production-view.html).

The 2026-09-01 relock is accepted. [RELOCK_PROPOSAL.md](RELOCK_PROPOSAL.md) is the decision record; where older research below differs, the manifest and relocked pixel grammar win.

Named shows (SportsCenter, PTI, any ticker show used as research) **do not appear** in marks, copy, filenames, or prompts.

## The picture you are making

One object on a card. Two hosts who ask different questions of it. A chyron that could survive as a clip. A ticker that is a third channel. A sting that is the period.

It is a **headline beat**, not a debate set and not a podcast zoomed to 1080.

| Channel | Owns | Must not do |
| --- | --- | --- |
| Host wells | Faces, desk, listening | Recap the card. Contain type. |
| Centre card | The shared object (post, later chart/image) | Duplicate the chyron. Show raw URLs. |
| Chyron | The land line — one clip-safe sentence | Read the tweet back. |
| Ticker | Other facts in the rundown | Repeat the chyron. Two moving rows. |
| Bug / LIVE / clock | “This is a show, it is live, it has a clock” | Animate on every topic change. |
| Active name plate | Who is intended to speak | Audio-follow, glow, zoom, or colour-only state. |

The two hosts are complementary, not funny/serious and not Crossfire:

- **PHASEONE[lol]** (left, amber) — is there a thesis, or is this weather?
- **deb** (right, teal) — what moved, by how much, for whom?

They agree the card is true. They cannot both be satisfied by the same sentence. Your furniture only needs to know which host is active. Exact name case is mandatory.

## Voice of the package

High furniture, low conversation. Network pictures, group-chat talk.

- Warm espresso plates, off-white type, and acid lemon as the programme accent in the desk rule and kicker chips only.
- Flat 93% panels. No borders, glow, skew, gradient, hairline, or fine texture that a Twitch 480p encode will eat.
- Archivo for display, Inter for data, and JetBrains Mono for system text. Fit display copy with Archivo's width axis before reducing size.
- Speaker state is value, not hue: invert exactly one host-name plate when a speaker is known.
- Coarse code texture may live in gutters and host-free fields. It stays static whenever a host is visible.
- One motion cadence for the whole family (when you reach Package B): sync sweep, geometric lock, ready button. Utility wipes under 1.2 s. Bumpers hold a title at the end. No readable type in any baked plate.

Do not clone a forest-green F1 suite, a finance J-screen, or any licensed display face. The production OFL stack is Archivo 600–800 + Inter 600/700 + JetBrains Mono 500.

## What “done” looks like

A still of `split` with a post card, both host IDs, one inverted active name plate, chyron, ticker, mark, LIVE, and clock must read as a show at 1920×1080 **and** after a 480p downscale. A designer who has never seen the hosts should still know: what the object is, who is speaking, and what the land is.

The first real content fixture is the 10.4 s Dwarkesh / OpenAI-agents segment. Use [fixtures/segment-20260831T154227Z.json](fixtures/segment-20260831T154227Z.json). The package chyron in the flight recaps the card — **reject that**. Write a land.

## Hard no

- Type, logos, or UI inside anything a video model will generate.
- Catchphrases a clip model has to pronounce.
- Devil’s-advocate / debate chrome.
- Chat-as-third-host chrome (v2).
- A second sponsor row that moves.
- DIN 2014, Record Laser, or any seat-licensed face.
- Shipping Google Fonts as the production path. Preview CDNs are fine in mocks; deliverables vendor OFL files.
