"""Filesystem inbox. Producers drop staged tweets; the cook worker dequeues."""

from __future__ import annotations

import shutil
from pathlib import Path

PENDING = "pending"
CLAIMED = "claimed"
DONE = "done"
DROPPED = "dropped"
PACKAGE_NAME = "package.json"
PACKET_NAME = "source_packet.local.json"
LOCK_NAME = "source_packet.lock.json"

INBOX_LANES = (PENDING, CLAIMED, DONE, DROPPED)


class QueueError(Exception):
    """Raised when the inbox cannot accept or claim an item."""


def ensure_inbox(root: Path) -> Path:
    inbox = Path(root).resolve()
    for lane in INBOX_LANES:
        (inbox / lane).mkdir(parents=True, exist_ok=True)
    return inbox


def enqueue(inbox: Path, source_dir: Path) -> Path:
    inbox = ensure_inbox(inbox)
    source = Path(source_dir).resolve()
    if not source.is_dir():
        raise QueueError(f"enqueue source is not a directory: {source}")
    if not (source / PACKET_NAME).is_file() or not (source / LOCK_NAME).is_file():
        raise QueueError("enqueue source is missing a reviewed packet")
    item_id = source.name
    dest = inbox / PENDING / item_id
    if dest.exists() or (inbox / CLAIMED / item_id).exists():
        raise QueueError(f"inbox already has {item_id}")
    shutil.copytree(source, dest)
    return dest


def pending_ids(inbox: Path) -> tuple[str, ...]:
    pending = Path(inbox).resolve() / PENDING
    if not pending.is_dir():
        return ()
    return tuple(sorted(path.name for path in pending.iterdir() if path.is_dir()))


def needs_producer(inbox: Path) -> tuple[str, ...]:
    return tuple(
        item_id
        for item_id in pending_ids(inbox)
        if not (Path(inbox).resolve() / PENDING / item_id / PACKAGE_NAME).is_file()
    )


def cookable_ids(inbox: Path) -> tuple[str, ...]:
    return tuple(
        item_id
        for item_id in pending_ids(inbox)
        if (Path(inbox).resolve() / PENDING / item_id / PACKAGE_NAME).is_file()
    )


def claim_next(inbox: Path) -> Path | None:
    inbox = ensure_inbox(inbox)
    ready = cookable_ids(inbox)
    if not ready:
        return None
    item_id = ready[0]
    source = inbox / PENDING / item_id
    dest = inbox / CLAIMED / item_id
    source.rename(dest)
    return dest


def mark_done(inbox: Path, item_id: str) -> Path:
    return _move_claimed(inbox, item_id, DONE)


def mark_dropped(inbox: Path, item_id: str) -> Path:
    return _move_claimed(inbox, item_id, DROPPED)


def _move_claimed(inbox: Path, item_id: str, lane: str) -> Path:
    inbox = Path(inbox).resolve()
    source = inbox / CLAIMED / item_id
    if not source.is_dir():
        raise QueueError(f"{item_id} is not claimed")
    dest = inbox / lane / item_id
    source.rename(dest)
    return dest
