"""Stub delay: jitter applies; forced-late stays exact."""

import random
from pathlib import Path

from performer_stub import StubPerformer


def _pool(tmp_path: Path) -> Path:
    clips = tmp_path / "clips"
    clips.mkdir()
    (clips / "c0.mp4").write_bytes(b"fake")
    return clips


def _stub(tmp_path: Path, **kwargs) -> StubPerformer:
    return StubPerformer(
        clip_pool=_pool(tmp_path),
        ready_dir=tmp_path / "ready",
        **kwargs,
    )


def test_zero_jitter_is_exact(tmp_path):
    stub = _stub(tmp_path, delay_s=4.0, delay_jitter_s=0.0)
    assert stub.delay_for(1) == 4.0


def test_jitter_spreads_non_forced_delay(tmp_path):
    stub = _stub(
        tmp_path,
        delay_s=4.0,
        delay_jitter_s=0.5,
        rng=random.Random(0),
    )
    samples = [stub.delay_for(1) for _ in range(20)]
    assert all(3.5 - 1e-9 <= s <= 4.5 + 1e-9 for s in samples)
    assert any(abs(s - 4.0) > 1e-9 for s in samples)


def test_forced_late_ignores_jitter(tmp_path):
    stub = _stub(
        tmp_path,
        delay_s=4.0,
        delay_jitter_s=0.5,
        forced_late_takes=[3],
        forced_late_delay_s=8.0,
        rng=random.Random(0),
    )
    assert stub.delay_for(3) == 8.0
