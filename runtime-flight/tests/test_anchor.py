"""Picture persistence: chain the same host, rebase to hero on a cut."""

from runtime_flight.anchor import persist_anchor, planned_anchor

HERO = "hero"
FRAME = "https://v3.fal.media/files/frame-1.png"


def test_take_one_is_always_the_hero() -> None:
    anchor, url = persist_anchor(
        take=1,
        speaker="BOT1",
        previous_speaker=None,
        previous_frame_url=None,
        reanchor_every=5,
        hero_url=HERO,
    )
    assert (anchor, url) == ("hero", HERO)


def test_speaker_cut_rebases_to_hero() -> None:
    anchor, url = persist_anchor(
        take=2,
        speaker="BOT2",
        previous_speaker="BOT1",
        previous_frame_url=FRAME,
        reanchor_every=60,
        hero_url=HERO,
    )
    assert (anchor, url) == ("hero", HERO)


def test_same_speaker_chains_the_exact_last_frame() -> None:
    anchor, url = persist_anchor(
        take=2,
        speaker="BOT1",
        previous_speaker="BOT1",
        previous_frame_url=FRAME,
        reanchor_every=5,
        hero_url=HERO,
    )
    assert (anchor, url) == ("chain", FRAME)


def test_same_speaker_still_rebases_on_the_interval() -> None:
    anchor, url = persist_anchor(
        take=6,
        speaker="BOT1",
        previous_speaker="BOT1",
        previous_frame_url=FRAME,
        reanchor_every=5,
        hero_url=HERO,
    )
    assert (anchor, url) == ("hero", HERO)


def test_missing_last_frame_falls_back_to_hero() -> None:
    anchor, url = persist_anchor(
        take=2,
        speaker="BOT1",
        previous_speaker="BOT1",
        previous_frame_url=None,
        reanchor_every=5,
        hero_url=HERO,
    )
    assert (anchor, url) == ("hero", HERO)


def test_planned_chain_waits_until_the_previous_frame_exists() -> None:
    anchor, url, available = planned_anchor(
        take=2,
        speaker="BOT1",
        previous_speaker="BOT1",
        previous_frame_url=None,
        previous_complete=False,
        reanchor_every=5,
        hero_url=HERO,
    )
    assert (anchor, url, available) == ("chain", "", False)


def test_planned_speaker_cut_is_available_while_the_other_take_cooks() -> None:
    anchor, url, available = planned_anchor(
        take=2,
        speaker="BOT2",
        previous_speaker="BOT1",
        previous_frame_url=None,
        previous_complete=False,
        reanchor_every=60,
        hero_url=HERO,
    )
    assert (anchor, url, available) == ("hero", HERO, True)
