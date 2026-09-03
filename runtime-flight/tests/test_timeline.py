"""Cook waterfall and flame graph from logged stage clocks."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from runtime_flight.__main__ import main
from runtime_flight.timeline import (
    flame_tree_from_row,
    load_cook_rows,
    merge_flame_trees,
    render_timeline_html,
    spans_from_row,
    write_timeline,
)


def _row() -> dict:
    return {
        "take": 2,
        "status": "ready",
        "duration_s": 5,
        "t_inference_s": 2.79,
        "t_submit_s": 0.134,
        "t_first_progress_s": 0.0,
        "t_completed_s": 25.516,
        "t_download_s": 0.335,
        "t_post_s": 1.979,
        "t_cook_s": 27.831,
        "t_validate_s": 0.4,
        "t_extract_s": 0.5,
        "t_upload_frame_s": 0.8,
        "t_copy_s": 0.279,
        "status_samples": [
            {"t_s": 0.05, "status": "IN_PROGRESS"},
            {"t_s": 25.4, "status": "COMPLETED"},
        ],
    }


def test_spans_split_post_and_place_reported_inference() -> None:
    spans = spans_from_row(_row())
    names = [span["name"] for span in spans]
    assert names[0] == "submit"
    assert "in_progress" in names
    assert "inference" in names
    assert "validate" in names
    infer = next(span for span in spans if span["name"] == "inference")
    assert infer["dur_s"] == 2.79
    assert infer["source"] == "fal"


def test_flame_nests_inference_and_keeps_after_denoise() -> None:
    tree = flame_tree_from_row(_row())
    assert tree["name"] == "take 2"
    wait = next(child for child in tree["children"] if child["name"] == "fal_wait")
    progress = next(child for child in wait["children"] if child["name"] == "in_progress")
    names = [child["name"] for child in progress["children"]]
    assert names == ["inference", "after_denoise"]
    infer = next(child for child in progress["children"] if child["name"] == "inference")
    leftover = next(child for child in progress["children"] if child["name"] == "after_denoise")
    assert infer["value"] == 2.79
    assert leftover["value"] > 20
    post = next(child for child in tree["children"] if child["name"] == "post")
    assert {child["name"] for child in post["children"]} == {
        "validate",
        "extract",
        "upload_frame",
        "copy",
    }


def test_merged_flame_sums_across_takes() -> None:
    first = dict(_row())
    first["take"] = 1
    trees = [flame_tree_from_row(first), flame_tree_from_row(_row())]
    merged = merge_flame_trees(trees)
    assert merged["name"] == "all cooks"
    assert merged["value"] == round(sum(tree["value"] for tree in trees), 3)
    wait = next(child for child in merged["children"] if child["name"] == "fal_wait")
    assert wait["value"] > 40


def test_write_timeline_html_includes_waterfall_and_flame(tmp_path: Path) -> None:
    path = tmp_path / "summary.json"
    path.write_text(
        __import__("json").dumps({"takes": [_row()], "duration_s": 5}),
        encoding="utf-8",
    )
    html_path = write_timeline(tmp_path, title="cook timeline test", duration_s=5)
    text = html_path.read_text(encoding="utf-8")
    assert html_path.name == "timeline.html"
    assert "Flame graph" in text
    assert "Waterfall" in text
    assert "after denoise" in text
    assert "merged_flame" in text
    assert "2.79" in text


def test_timeline_cli_renders_from_dir(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "fal_cook.jsonl").write_text(
        __import__("json").dumps(_row()) + "\n", encoding="utf-8"
    )
    code = main(["timeline", "--dir", str(tmp_path)])
    captured = capsys.readouterr()
    assert code == 0
    assert "timeline.html" in captured.out
    assert (tmp_path / "logs" / "timeline.html").is_file()


def test_timeline_module_stays_isolated() -> None:
    path = Path(__file__).resolve().parents[1] / "runtime_flight" / "timeline.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported.isdisjoint({"writer", "obs_session", "harness_live", "fal_client"})
    assert load_cook_rows
    assert render_timeline_html
