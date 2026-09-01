"""Last-frame persistence for H3 takes.

The picture chains only while the same host keeps talking. A speaker change
is a cut: rebase to the locked hero so grain does not compound across the
seam. Same-speaker runs still force a hero rebase every reanchor_every takes.
"""

from __future__ import annotations

from typing import Literal

Anchor = Literal["hero", "chain"]


def persist_anchor(
    *,
    take: int,
    speaker: str,
    previous_speaker: str | None,
    previous_frame_url: str | None,
    reanchor_every: int,
    hero_url: str,
) -> tuple[Anchor, str]:
    if take <= 1:
        return "hero", hero_url
    if previous_speaker is not None and speaker != previous_speaker:
        return "hero", hero_url
    if reanchor_every > 0 and (take - 1) % reanchor_every == 0:
        return "hero", hero_url
    if previous_frame_url:
        return "chain", previous_frame_url
    return "hero", hero_url
