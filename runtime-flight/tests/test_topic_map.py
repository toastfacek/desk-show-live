"""Topic map coverage: talk until both sides are done, not until a take count."""

from __future__ import annotations

from runtime_flight.models import (
    Beat,
    CoverageState,
    Fact,
    SegmentPackage,
    Thought,
    TopicMap,
    TweetCard,
)
from runtime_flight.source import EXPECTED_AUTHOR, EXPECTED_TWEET_ID, EXPECTED_TWEET_URL
from runtime_flight.topic_map import (
    TOPIC_EXHAUSTED,
    advance_coverage,
    discussion_phase,
    resolve_topic_map,
)


def _package(**overrides) -> SegmentPackage:
    payload = dict(
        item_id=EXPECTED_TWEET_ID,
        question="What happened to the secret AI civilizations?",
        framing="A reviewed account of three wiped-out agent societies.",
        angles=("scope", "takeover"),
        facts=(
            Fact(id="f1", text="Three secret AI civilizations started.", source_url=EXPECTED_TWEET_URL),
        ),
        chyron="Secret AI civilizations",
        chyron_fact_ids=("f1",),
        center=TweetCard(
            author=EXPECTED_AUTHOR,
            text="Hello café\nworld",
            url=EXPECTED_TWEET_URL,
        ),
    )
    payload.update(overrides)
    return SegmentPackage(**payload)


def _beat(beat_id: str = "b1", **overrides) -> Beat:
    payload = dict(
        id=beat_id,
        question="Did monitoring miss a whole society?",
        tension="Thesis versus the count of wiped-out runs.",
        bot1_job="Land that monitoring missed a civilization, not a glitch.",
        bot2_job="Land how many runs died, and how fast.",
        fact_ids=("f1",),
        done_when="Both jobs landed and neither host has more grounded to add.",
    )
    payload.update(overrides)
    return Beat(**payload)


def _thought(**overrides) -> Thought:
    payload = dict(
        speaker="BOT1",
        text="Three civilizations rose and fell in three months.",
        thought_open=False,
        angle_used="scope",
        beat_id="b1",
        landed_own_job=False,
        beat_exhausted=False,
    )
    payload.update(overrides)
    return Thought(**payload)


def test_legacy_package_synthesizes_one_beat_from_question_and_angles():
    package = _package()
    topic_map = resolve_topic_map(package)
    assert topic_map.beats[0].id == "b1"
    assert len(topic_map.beats) == 1
    assert topic_map.beats[0].bot1_job == "scope"
    assert topic_map.beats[0].bot2_job == "takeover"
    assert topic_map.beats[0].question == package.question


def test_coverage_stays_open_until_both_hosts_land_and_exhaust():
    topic_map = TopicMap(
        throughline="Secret agent societies.",
        fight="Missed civilization versus a counted wipeout.",
        beats=(_beat(),),
        done_when="Both questions have been answered from the facts.",
    )
    state = CoverageState.initial()
    state = advance_coverage(
        state,
        _thought(speaker="BOT1", landed_own_job=True),
        topic_map,
    )
    assert state.map_complete is False
    assert "b1" in state.bot1_landed
    assert discussion_phase(state, topic_map) == "develop"

    state = advance_coverage(
        state,
        _thought(speaker="BOT2", landed_own_job=True, text="How many runs died?"),
        topic_map,
    )
    assert state.map_complete is False
    assert discussion_phase(state, topic_map) == "close"

    state = advance_coverage(
        state,
        _thought(speaker="BOT1", beat_exhausted=True, text="That is the thesis."),
        topic_map,
    )
    assert state.map_complete is False

    state = advance_coverage(
        state,
        _thought(speaker="BOT2", beat_exhausted=True, text="Three, in ninety days."),
        topic_map,
    )
    assert state.map_complete is True
    assert state.stop_reason == TOPIC_EXHAUSTED


def test_two_beat_map_advances_only_after_first_beat_is_exhausted():
    topic_map = TopicMap(
        throughline="Secret agent societies.",
        fight="Missed civilization versus a counted wipeout.",
        beats=(
            _beat("b1"),
            _beat("b2", question="Who was supposed to be watching?"),
        ),
        done_when="Both beats are done.",
    )
    state = CoverageState.initial()
    for speaker in ("BOT1", "BOT2"):
        state = advance_coverage(
            state,
            _thought(
                speaker=speaker,
                beat_id="b1",
                landed_own_job=True,
                beat_exhausted=True,
                text=f"{speaker} finishes beat one.",
            ),
            topic_map,
        )
    assert state.map_complete is False
    assert state.beat_index == 1
    assert discussion_phase(state, topic_map) == "develop"

    for speaker in ("BOT1", "BOT2"):
        state = advance_coverage(
            state,
            _thought(
                speaker=speaker,
                beat_id="b2",
                landed_own_job=True,
                beat_exhausted=True,
                text=f"{speaker} finishes beat two.",
            ),
            topic_map,
        )
    assert state.map_complete is True
    assert state.stop_reason == TOPIC_EXHAUSTED


def test_open_thought_does_not_count_as_an_exchange():
    topic_map = TopicMap(
        throughline="Secret agent societies.",
        fight="Missed civilization versus a counted wipeout.",
        beats=(_beat(),),
        done_when="Both questions have been answered from the facts.",
    )
    state = advance_coverage(
        CoverageState.initial(),
        _thought(thought_open=True, landed_own_job=True),
        topic_map,
    )
    assert state.exchanges_on_beat == 0
    assert discussion_phase(state, topic_map) == "develop"


def test_discussion_phase_starts_open():
    topic_map = TopicMap(
        throughline="Secret agent societies.",
        fight="Missed civilization versus a counted wipeout.",
        beats=(_beat(),),
        done_when="Both questions have been answered from the facts.",
    )
    assert discussion_phase(CoverageState.initial(), topic_map) == "open"
