"""Stay / leave rules for a streamer content object.

The host does not decide exhaustion in prose. The loop does.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import streamer_loop as loop  # noqa: E402


def _gta() -> loop.ContentObject:
    return loop.gta_footage_fixture()


def _start(now: float = 0.0) -> loop.LoopState:
    return loop.open_object(_gta(), now=now)


def test_fixture_is_footage_with_moments() -> None:
    obj = _gta()
    assert obj.kind == "footage"
    assert len(obj.moments) >= 4
    assert obj.hard_clock_s > obj.moments[-1].t
    assert all(a.t <= b.t for a, b in zip(obj.moments, obj.moments[1:]))


def test_first_tick_glances_does_not_land() -> None:
    state = _start(0)
    action = loop.next_action(state, now=0.5, events=())
    assert action.move == "glance"
    assert action.decision == "stay"
    assert "open" in action.why
    state = loop.apply(state, action, now=0.5)
    assert state.glanced is True
    assert state.landed is False


def test_new_moment_points_and_stays() -> None:
    state = loop.apply(_start(0), loop.next_action(_start(0), now=0.2, events=()), now=0.2)
    moment = _gta().moments[1]
    action = loop.next_action(
        state,
        now=moment.t,
        events=(loop.NewMoment(moment_id=moment.id),),
    )
    assert action.move == "point"
    assert action.decision == "stay"
    assert action.moment_id == moment.id
    state = loop.apply(state, action, now=moment.t)
    assert moment.id in state.pointed_ids


def test_second_moment_reacts_instead_of_landing() -> None:
    state = _start(0)
    state = loop.apply(state, loop.next_action(state, now=0.2, events=()), now=0.2)
    first = _gta().moments[1]
    second = _gta().moments[2]
    state = loop.apply(
        state,
        loop.next_action(state, now=first.t, events=(loop.NewMoment(first.id),)),
        now=first.t,
    )
    action = loop.next_action(
        state,
        now=second.t,
        events=(loop.NewMoment(second.id),),
    )
    assert action.move == "react"
    assert action.decision == "stay"
    assert action.moment_id == second.id


def test_pending_chat_while_footage_plays_is_an_interrupt() -> None:
    state = _start(0)
    state = loop.apply(state, loop.next_action(state, now=0.2, events=()), now=0.2)
    action = loop.next_action(
        state,
        now=10,
        events=(loop.ChatPick(comment_id="c1", text="is that the wanted system?", why="asks a real question"),),
    )
    assert action.move == "chat"
    assert action.decision == "stay"
    assert action.comment_id == "c1"
    state = loop.apply(state, action, now=10)
    assert state.chat_answered == 1


def test_unseen_moments_block_land() -> None:
    state = _start(0)
    state = loop.apply(state, loop.next_action(state, now=0.2, events=()), now=0.2)
    # Pretend we took a side early.
    state = loop.LoopState(
        **{**state.as_dict(), "took": True, "pointed_ids": list(state.pointed_ids)}
    )
    action = loop.next_action(state, now=5, events=())
    assert action.decision == "stay"
    assert action.move != "land"
    assert any("unseen" in reason or "moment" in reason for reason in action.still_open)


def test_footage_ended_without_a_take_stays_for_take() -> None:
    obj = _gta()
    state = _start(0)
    state = loop.apply(state, loop.next_action(state, now=0.2, events=()), now=0.2)
    for moment in obj.moments[1:]:
        action = loop.next_action(
            state, now=moment.t, events=(loop.NewMoment(moment.id),)
        )
        state = loop.apply(state, action, now=moment.t)
    ended_at = obj.moments[-1].t + 0.5
    action = loop.next_action(
        state, now=ended_at, events=(loop.FootageEnded(),)
    )
    assert action.decision == "stay"
    assert action.move == "take"
    state = loop.apply(state, action, now=ended_at)
    assert state.took is True


def test_footage_ended_after_take_lands() -> None:
    obj = _gta()
    state = _start(0)
    now = 0.2
    state = loop.apply(state, loop.next_action(state, now=now, events=()), now=now)
    for moment in obj.moments[1:]:
        now = moment.t
        state = loop.apply(
            state,
            loop.next_action(state, now=now, events=(loop.NewMoment(moment.id),)),
            now=now,
        )
    now = obj.moments[-1].t + 0.5
    state = loop.apply(
        state,
        loop.next_action(state, now=now, events=(loop.FootageEnded(),)),
        now=now,
    )
    assert state.took is True
    action = loop.next_action(state, now=now + 0.2, events=())
    assert action.move == "land"
    assert action.decision == "leave"
    assert action.why.startswith("sum")
    state = loop.apply(state, action, now=now + 0.2)
    assert state.landed is True
    nxt = loop.next_action(state, now=now + 1, events=())
    assert nxt.decision == "next"
    assert nxt.move == "next"


def test_pending_chat_after_take_delays_land() -> None:
    obj = _gta()
    state = _start(0)
    now = 0.2
    state = loop.apply(state, loop.next_action(state, now=now, events=()), now=now)
    for moment in obj.moments[1:]:
        now = moment.t
        state = loop.apply(
            state,
            loop.next_action(state, now=now, events=(loop.NewMoment(moment.id),)),
            now=now,
        )
    now = obj.moments[-1].t + 0.5
    state = loop.apply(
        state,
        loop.next_action(state, now=now, events=(loop.FootageEnded(),)),
        now=now,
    )
    action = loop.next_action(
        state,
        now=now + 0.1,
        events=(loop.ChatPick(comment_id="c2", text="would you play this?", why="asks a real question"),),
    )
    assert action.move == "chat"
    assert action.decision == "stay"
    state = loop.apply(state, action, now=now + 0.1)
    land = loop.next_action(state, now=now + 0.3, events=())
    assert land.move == "land"
    assert land.decision == "leave"


def test_hard_clock_forces_land_once_there_is_a_take() -> None:
    obj = _gta()
    state = _start(0)
    state = loop.apply(state, loop.next_action(state, now=0.2, events=()), now=0.2)
    first = obj.moments[1]
    state = loop.apply(
        state,
        loop.next_action(state, now=first.t, events=(loop.NewMoment(first.id),)),
        now=first.t,
    )
    state = loop.LoopState(**{**state.as_dict(), "took": True})
    action = loop.next_action(state, now=obj.hard_clock_s + 0.1, events=())
    assert action.move == "land"
    assert action.decision == "leave"
    assert "clock" in action.why


def test_hard_clock_without_take_takes_first() -> None:
    state = _start(0)
    state = loop.apply(state, loop.next_action(state, now=0.2, events=()), now=0.2)
    action = loop.next_action(state, now=_gta().hard_clock_s + 0.1, events=())
    assert action.decision == "stay"
    assert action.move == "take"


def test_quiet_after_point_and_take_lands() -> None:
    obj = _gta()
    state = _start(0)
    state = loop.apply(state, loop.next_action(state, now=0.2, events=()), now=0.2)
    first = obj.moments[1]
    state = loop.apply(
        state,
        loop.next_action(state, now=first.t, events=(loop.NewMoment(first.id),)),
        now=first.t,
    )
    state = loop.LoopState(**{**state.as_dict(), "took": True, "turns": max(state.turns, 3)})
    quiet_at = first.t + obj.quiet_s + 0.2
    action = loop.next_action(state, now=quiet_at, events=())
    assert action.move == "land"
    assert action.decision == "leave"
    assert "quiet" in action.why


def test_quiet_without_min_turns_stays() -> None:
    obj = _gta()
    state = _start(0)
    state = loop.apply(state, loop.next_action(state, now=0.2, events=()), now=0.2)
    first = obj.moments[1]
    state = loop.apply(
        state,
        loop.next_action(state, now=first.t, events=(loop.NewMoment(first.id),)),
        now=first.t,
    )
    state = loop.LoopState(**{**state.as_dict(), "took": True, "turns": 1})
    action = loop.next_action(state, now=first.t + obj.quiet_s + 1, events=())
    assert action.decision == "stay"
    assert action.move != "land"


def test_full_gta_run_points_then_lands() -> None:
    obj = _gta()
    state = _start(0)
    now = 0.0
    moves: list[str] = []
    events: list[loop.Event] = []
    moment_i = 0
    while True:
        now += 0.5
        while moment_i < len(obj.moments) and obj.moments[moment_i].t <= now:
            events.append(loop.NewMoment(obj.moments[moment_i].id))
            moment_i += 1
        if now >= obj.moments[-1].t + 0.5 and not state.footage_ended:
            events.append(loop.FootageEnded())
        action = loop.next_action(state, now=now, events=tuple(events))
        events = []
        if action.move == "wait":
            continue
        state = loop.apply(state, action, now=now)
        moves.append(action.move)
        if action.decision == "next":
            break
        if now > 200:
            raise AssertionError("loop did not leave")
    assert moves[0] == "glance"
    assert "point" in moves
    assert "react" in moves
    assert "take" in moves
    assert moves[-2] == "land"
    assert moves[-1] == "next"
    assert state.landed is True
    assert len(state.pointed_ids) >= 2


def test_isolation_has_no_display_names() -> None:
    source = Path(loop.__file__).read_text(encoding="utf-8")
    lowered = source.lower()
    assert "phaseone" not in lowered
    assert "\ndeb" not in lowered and "deb " not in lowered
    assert "writer" not in lowered
    obj = _gta()
    blob = " ".join([obj.title, obj.question] + [m.what for m in obj.moments])
    assert "PHASEONE" not in blob
    assert "deb" not in blob.lower()


def test_js_port_keeps_the_same_moves() -> None:
    source = (ROOT / "js" / "loop.js").read_text(encoding="utf-8")
    for move in ("glance", "point", "react", "chat", "take", "land", "wait", "next"):
        assert f'"{move}"' in source or f"'{move}'" in source
    assert "quiet" in source
    assert "hard_clock" in source or "hardClock" in source
