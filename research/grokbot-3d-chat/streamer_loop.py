"""Streamer content loop. The clock decides stay / leave. The host only speaks.

Solo object. Chat is an interrupt. Footage moments are the continuous input.
No display names. No fal. No writer import.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

MOVES = ("glance", "point", "react", "chat", "take", "land", "wait", "next")
DECISIONS = ("stay", "leave", "next")


@dataclass(frozen=True)
class Moment:
    t: float
    id: str
    what: str
    why: str = ""


@dataclass(frozen=True)
class ContentObject:
    id: str
    kind: str
    title: str
    question: str
    moments: tuple[Moment, ...]
    hard_clock_s: float
    quiet_s: float = 6.0
    min_turns: int = 3

    def moment(self, moment_id: str) -> Moment | None:
        for row in self.moments:
            if row.id == moment_id:
                return row
        return None

    def establish_id(self) -> str:
        return self.moments[0].id if self.moments else ""


@dataclass(frozen=True)
class NewMoment:
    moment_id: str


@dataclass(frozen=True)
class ChatPick:
    comment_id: str
    text: str
    why: str = ""


@dataclass(frozen=True)
class FootageEnded:
    pass


Event = NewMoment | ChatPick | FootageEnded


@dataclass(frozen=True)
class Action:
    move: str
    decision: str
    why: str
    still_open: tuple[str, ...] = ()
    moment_id: str = ""
    comment_id: str = ""
    footage_ended: bool = False
    pending_chat: ChatPick | None = None


@dataclass(frozen=True)
class LoopState:
    obj: ContentObject
    glanced: bool = False
    pointed_ids: tuple[str, ...] = ()
    took: bool = False
    landed: bool = False
    footage_ended: bool = False
    chat_answered: int = 0
    pending_chat: ChatPick | None = None
    turns: int = 0
    last_activity_t: float = 0.0
    started_at: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "obj": self.obj,
            "glanced": self.glanced,
            "pointed_ids": list(self.pointed_ids),
            "took": self.took,
            "landed": self.landed,
            "footage_ended": self.footage_ended,
            "chat_answered": self.chat_answered,
            "pending_chat": self.pending_chat,
            "turns": self.turns,
            "last_activity_t": self.last_activity_t,
            "started_at": self.started_at,
        }

    def __init__(self, **kwargs: Any) -> None:
        object.__setattr__(self, "obj", kwargs["obj"])
        object.__setattr__(self, "glanced", bool(kwargs.get("glanced", False)))
        pointed = kwargs.get("pointed_ids", ())
        object.__setattr__(self, "pointed_ids", tuple(pointed))
        object.__setattr__(self, "took", bool(kwargs.get("took", False)))
        object.__setattr__(self, "landed", bool(kwargs.get("landed", False)))
        object.__setattr__(self, "footage_ended", bool(kwargs.get("footage_ended", False)))
        object.__setattr__(self, "chat_answered", int(kwargs.get("chat_answered", 0)))
        object.__setattr__(self, "pending_chat", kwargs.get("pending_chat"))
        object.__setattr__(self, "turns", int(kwargs.get("turns", 0)))
        object.__setattr__(self, "last_activity_t", float(kwargs.get("last_activity_t", 0.0)))
        object.__setattr__(self, "started_at", float(kwargs.get("started_at", 0.0)))


def gta_footage_fixture() -> ContentObject:
    return ContentObject(
        id="footage-drop-1",
        kind="footage",
        title="New footage drop",
        question="What in this clip is actually new, and do we care?",
        hard_clock_s=70.0,
        quiet_s=6.0,
        min_turns=3,
        moments=(
            Moment(0.0, "m0", "Night city card. Rain on the hood. The clip is selling weather."),
            Moment(8.0, "m1", "A bike cuts six lanes. Traffic shears around it.", "motion, density"),
            Moment(18.0, "m2", "Wanted stars pop. Cops commit instead of posing.", "system, chase"),
            Moment(28.0, "m3", "Gap jump. The landing is a little too lucky.", "physics tell"),
            Moment(40.0, "m4", "Sunset skyline, people on the overpass watching.", "tone, crowd"),
        ),
    )


def open_object(obj: ContentObject, now: float = 0.0) -> LoopState:
    return LoopState(obj=obj, started_at=now, last_activity_t=now)


def _incoming(
    state: LoopState, events: Sequence[Event]
) -> tuple[list[str], ChatPick | None, bool]:
    new_ids: list[str] = []
    pending = state.pending_chat
    ended = state.footage_ended
    for event in events:
        if isinstance(event, NewMoment):
            if state.obj.moment(event.moment_id) and event.moment_id not in new_ids:
                new_ids.append(event.moment_id)
        elif isinstance(event, ChatPick):
            pending = event
        elif isinstance(event, FootageEnded):
            ended = True
    return new_ids, pending, ended


def _interesting_pointed(state: LoopState) -> bool:
    establish = state.obj.establish_id()
    return any(moment_id != establish for moment_id in state.pointed_ids)


def still_open(
    state: LoopState, *, pending: ChatPick | None, ended: bool
) -> tuple[str, ...]:
    reasons: list[str] = []
    if not state.glanced:
        reasons.append("have not opened the object")
    if not _interesting_pointed(state):
        reasons.append("have not pointed at an interesting moment")
    leftover = [row.id for row in state.obj.moments if row.id not in state.pointed_ids]
    if leftover:
        reasons.append("unseen interesting moments remain")
    if not state.took:
        reasons.append("have not taken a side")
    if pending is not None:
        reasons.append("curated chat is waiting")
    if not ended:
        reasons.append("footage is still playing")
    if state.landed:
        return ()
    return tuple(reasons)


def next_action(
    state: LoopState, now: float, events: Iterable[Event] = ()
) -> Action:
    event_list = tuple(events)
    new_ids, pending, ended = _incoming(state, event_list)
    open_reasons = still_open(state, pending=pending, ended=ended)
    clock_hit = (now - state.started_at) >= state.obj.hard_clock_s
    quiet_hit = (now - state.last_activity_t) >= state.obj.quiet_s

    if state.landed:
        return Action(move="next", decision="next", why="object closed", still_open=())

    if not state.glanced:
        return Action(
            move="glance",
            decision="stay",
            why="open the object",
            still_open=open_reasons,
            footage_ended=ended,
            pending_chat=pending,
        )

    fresh = [mid for mid in new_ids if mid not in state.pointed_ids]
    if fresh:
        moment_id = fresh[0]
        move = "point" if not _interesting_pointed(state) else "react"
        return Action(
            move=move,
            decision="stay",
            why="new moment on the content view",
            still_open=open_reasons,
            moment_id=moment_id,
            footage_ended=ended,
            pending_chat=pending,
        )

    if pending is not None and not (clock_hit and state.took):
        return Action(
            move="chat",
            decision="stay",
            why="curated chat interrupt",
            still_open=open_reasons,
            comment_id=pending.comment_id,
            footage_ended=ended,
            pending_chat=pending,
        )

    if clock_hit and state.took:
        return Action(
            move="land",
            decision="leave",
            why="clock killed the topic",
            still_open=(),
            footage_ended=ended,
        )
    if clock_hit and not state.took:
        return Action(
            move="take",
            decision="stay",
            why="clock is up; take a side before the land",
            still_open=open_reasons,
            footage_ended=ended,
            pending_chat=pending,
        )

    if ended and not state.took:
        return Action(
            move="take",
            decision="stay",
            why="footage ended; take a side",
            still_open=open_reasons,
            footage_ended=True,
            pending_chat=pending,
        )
    if ended and pending is not None:
        return Action(
            move="chat",
            decision="stay",
            why="curated chat before the land",
            still_open=open_reasons,
            comment_id=pending.comment_id,
            footage_ended=True,
            pending_chat=pending,
        )
    if ended and state.took:
        return Action(
            move="land",
            decision="leave",
            why="sum up the reaction",
            still_open=(),
            footage_ended=True,
        )

    if (
        quiet_hit
        and state.took
        and _interesting_pointed(state)
        and state.turns >= state.obj.min_turns
    ):
        return Action(
            move="land",
            decision="leave",
            why="quiet; the topic has exhausted itself",
            still_open=(),
            footage_ended=ended,
        )

    return Action(
        move="wait",
        decision="stay",
        why="hold for the next moment or a chat poke",
        still_open=open_reasons,
        footage_ended=ended,
        pending_chat=pending,
    )


def apply(state: LoopState, action: Action, now: float) -> LoopState:
    pointed = list(state.pointed_ids)
    glanced = state.glanced
    took = state.took
    landed = state.landed
    turns = state.turns
    chat_answered = state.chat_answered
    pending = action.pending_chat
    last = state.last_activity_t
    ended = state.footage_ended or action.footage_ended

    if action.move == "glance":
        glanced = True
        establish = state.obj.establish_id()
        if establish and establish not in pointed:
            pointed.append(establish)
        turns += 1
        last = now
        pending = pending
    elif action.move in {"point", "react"}:
        if action.moment_id and action.moment_id not in pointed:
            pointed.append(action.moment_id)
        turns += 1
        last = now
    elif action.move == "chat":
        chat_answered += 1
        pending = None
        turns += 1
        last = now
    elif action.move == "take":
        took = True
        turns += 1
        last = now
    elif action.move == "land":
        landed = True
        pending = None
        turns += 1
        last = now
    elif action.move == "next":
        last = now

    return LoopState(
        obj=state.obj,
        glanced=glanced,
        pointed_ids=pointed,
        took=took,
        landed=landed,
        footage_ended=ended,
        chat_answered=chat_answered,
        pending_chat=pending,
        turns=turns,
        last_activity_t=last,
        started_at=state.started_at,
    )
