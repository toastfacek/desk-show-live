# Design-agent handoff

Give the next agent these three files, in this order:

1. [DESIGN_BRIEF.md](DESIGN_BRIEF.md) — what the picture is for
2. [ASSET_MANIFEST.md](ASSET_MANIFEST.md) — files, pixels, acceptance
3. [overlay-state.schema.json](overlay-state.schema.json) — live JSON

First content fixture: [fixtures/segment-20260831T154227Z.json](fixtures/segment-20260831T154227Z.json). The flight’s package chyron recaps the card. Do not paint it. Use the land in the fixture.

Compositor for the 10.4 s two-shot under these plates: [../mocks/composite_segment_through_cg.py](../mocks/composite_segment_through_cg.py).
