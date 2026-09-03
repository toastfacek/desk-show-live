"""Filesystem inbox. Producers drop staged tweets; the cook worker dequeues."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

PENDING = "pending"
CLAIMED = "claimed"
DONE = "done"
DROPPED = "dropped"
PACKAGE_NAME = "package.json"
PACKET_NAME = "source_packet.local.json"
LOCK_NAME = "source_packet.lock.json"
MANIFEST_NAME = "queue.jsonl"

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
    if has_item(inbox, item_id):
        raise QueueError(f"inbox already has {item_id}")
    dest = inbox / PENDING / item_id
    shutil.copytree(source, dest)
    _append_manifest(inbox, item_id)
    return dest


def has_item(inbox: Path, item_id: str) -> bool:
    inbox = Path(inbox).resolve()
    return any((inbox / lane / item_id).is_dir() for lane in INBOX_LANES)


def queue_ids(inbox: Path) -> tuple[str, ...]:
    manifest = Path(inbox).resolve() / MANIFEST_NAME
    if not manifest.is_file():
        return ()
    ids: list[str] = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        item_id = row.get("id")
        if isinstance(item_id, str) and item_id:
            ids.append(item_id)
    return tuple(ids)


def pending_ids(inbox: Path) -> tuple[str, ...]:
    inbox = Path(inbox).resolve()
    pending = inbox / PENDING
    if not pending.is_dir():
        return ()
    on_disk = {path.name for path in pending.iterdir() if path.is_dir()}
    ordered = [item_id for item_id in queue_ids(inbox) if item_id in on_disk]
    extras = sorted(on_disk.difference(ordered))
    return tuple(ordered + extras)


def needs_producer(inbox: Path) -> tuple[str, ...]:
    inbox = Path(inbox).resolve()
    return tuple(
        item_id
        for item_id in pending_ids(inbox)
        if not (inbox / PENDING / item_id / PACKAGE_NAME).is_file()
    )


def cookable_ids(inbox: Path) -> tuple[str, ...]:
    inbox = Path(inbox).resolve()
    return tuple(
        item_id
        for item_id in pending_ids(inbox)
        if (inbox / PENDING / item_id / PACKAGE_NAME).is_file()
    )


def claim_next(inbox: Path, *, dissected: bool = True) -> Path | None:
    inbox = ensure_inbox(inbox)
    ready = cookable_ids(inbox) if dissected else pending_ids(inbox)
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


def release_claimed(inbox: Path) -> tuple[str, ...]:
    inbox = ensure_inbox(inbox)
    claimed = inbox / CLAIMED
    released: list[str] = []
    if not claimed.is_dir():
        return ()
    for path in claimed.iterdir():
        if not path.is_dir():
            continue
        dest = inbox / PENDING / path.name
        path.rename(dest)
        released.append(path.name)
    return tuple(released)


def _move_claimed(inbox: Path, item_id: str, lane: str) -> Path:
    inbox = Path(inbox).resolve()
    source = inbox / CLAIMED / item_id
    if not source.is_dir():
        raise QueueError(f"{item_id} is not claimed")
    dest = inbox / lane / item_id
    source.rename(dest)
    return dest


def _append_manifest(inbox: Path, item_id: str) -> None:
    path = Path(inbox).resolve() / MANIFEST_NAME
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"id": item_id}, separators=(",", ":")) + "\n")
