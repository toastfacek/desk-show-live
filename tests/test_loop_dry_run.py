"""Full-loop smoke test: run_live.py --dry-run, headless, real ffmpeg.
Verifies the whole pipeline (writer fallback → generator → post → manifest → hold)
without a single billed take."""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def write_test_config(tmp_path: Path) -> Path:
    import yaml

    with open(REPO / "config.yaml") as f:
        cfg = yaml.safe_load(f)
    cfg["writer"]["base_url"] = "http://127.0.0.1:9"  # unreachable → canned-line fallback
    cfg["writer"]["timeout_s"] = 0.2
    cfg["video"]["duration"] = 1
    cfg["dry_run"]["simulate_latency_s"] = 0.1
    cfg["player"] = "none"
    cfg["loop"]["turns"] = 3
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(cfg))
    return path


def run_loop(cfg_path: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO / "run_live.py"), "--config", str(cfg_path),
         "--dry-run", "--player", "none", *extra],
        capture_output=True, text=True, timeout=120, cwd=cfg_path.parent,
    )


def read_manifest(tmp_path: Path) -> list[dict]:
    manifest = tmp_path / "out" / "takes.jsonl"
    assert manifest.exists(), "manifest not written"
    return [json.loads(ln) for ln in manifest.read_text().splitlines() if ln.strip()]


def test_dry_run_three_takes(tmp_path):
    cfg = write_test_config(tmp_path)
    proc = run_loop(cfg)
    assert proc.returncode == 0, proc.stderr[-2000:]
    rows = read_manifest(tmp_path)
    ready = [r for r in rows if r["status"] == "ready"]
    assert len(ready) == 3
    for r in ready:
        assert (tmp_path / r["clip"]).exists()
        assert (tmp_path / r["raw"]).exists()
        assert (tmp_path / r["frame_png"]).exists()
        assert r["line"].endswith(".")
        assert r["cost_usd"] == 0  # dry runs are free
    # last-frame chain: takes 2 and 3 anchor on the previous take's frame
    assert ready[0]["anchor"] == "hero"
    assert ready[1]["anchor"] == "chain"


def test_forced_hold_recovers(tmp_path):
    """E6 logic: a killed in-flight generation is logged as failed and the loop
    keeps going on its own."""
    cfg = write_test_config(tmp_path)
    proc = run_loop(cfg, "--force-hold-at", "2")
    assert proc.returncode == 0, proc.stderr[-2000:]
    rows = read_manifest(tmp_path)
    failed = [r for r in rows if r["status"] == "failed"]
    ready = [r for r in rows if r["status"] == "ready"]
    assert len(failed) == 1 and failed[0]["error"] == "forced_hold_e6"
    assert len(ready) == 2  # loop recovered and finished the remaining turns
