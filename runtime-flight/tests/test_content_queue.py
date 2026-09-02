"""Inbox enqueue and dequeue. No writer, no OBS, no cook."""

from __future__ import annotations

import ast
import shutil
from pathlib import Path

import pytest

from runtime_flight.content_queue import (
    PACKAGE_NAME,
    claim_next,
    cookable_ids,
    enqueue,
    mark_done,
    needs_producer,
    pending_ids,
)
from test_prepare_queue import _write_staged

FORBIDDEN = {
    "harness_live",
    "obs_session",
    "playhead",
    "run_live",
    "studio",
    "writer",
    "fal_client",
}


def test_enqueue_orders_pending_and_skips_undissected(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    first = enqueue(inbox, _write_staged(tmp_path, "222", "two"))
    enqueue(inbox, _write_staged(tmp_path, "111", "one"))
    raw = enqueue(inbox, _write_staged(tmp_path, "333", "three"))
    (raw / PACKAGE_NAME).unlink()
    assert pending_ids(inbox) == ("111", "222", "333")
    assert cookable_ids(inbox) == ("111", "222")
    assert needs_producer(inbox) == ("333",)
    claimed = claim_next(inbox)
    assert claimed is not None
    assert claimed.name == "111"
    assert pending_ids(inbox) == ("222", "333")
    mark_done(inbox, "111")
    assert not (inbox / "claimed" / "111").exists()
    assert (inbox / "done" / "111").is_dir()
    assert first.is_dir()
    assert (inbox / "pending" / "222").is_dir()


def test_claim_next_is_none_when_only_undissected_remain(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    raw = enqueue(inbox, _write_staged(tmp_path, "111", "one"))
    (raw / PACKAGE_NAME).unlink()
    assert claim_next(inbox) is None
    assert needs_producer(inbox) == ("111",)


def test_enqueue_refuses_duplicates(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    source = _write_staged(tmp_path, "111", "one")
    enqueue(inbox, source)
    with pytest.raises(Exception, match="already has"):
        enqueue(inbox, source)
    copy = tmp_path / "copy" / "111"
    shutil.copytree(source, copy)
    with pytest.raises(Exception, match="already has"):
        enqueue(inbox, copy)


def test_content_queue_module_stays_isolated() -> None:
    path = Path(__file__).resolve().parents[1] / "runtime_flight" / "content_queue.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported.isdisjoint(FORBIDDEN)
    assert "from runtime_flight.writer" not in source
    assert "from runtime_flight.harness_live" not in source
    assert "obs" not in source
