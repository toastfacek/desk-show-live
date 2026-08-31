import json
import subprocess
from pathlib import Path


def test_requested_candidate_filter_never_mixes_casts():
    script = r"""
const selection = require("./pack_manager/web/selection.js");
const candidates = [
  {id: "root-a", cast_key: "cast-a", is_current_canonical: true, canonical_candidate_id: null, status: "approved"},
  {id: "variant-a-draft", cast_key: "cast-a", canonical_candidate_id: "root-a", theme: "Snow", status: "draft"},
  {id: "variant-a-approved", cast_key: "cast-a", canonical_candidate_id: "root-a", theme: "Night", status: "approved"},
  {id: "unrelated-root", cast_key: "cast-b", is_current_canonical: true, canonical_candidate_id: null, status: "approved"},
  {id: "unrelated-variant", cast_key: "cast-b", canonical_candidate_id: "unrelated-root", theme: "Beach", status: "approved"},
  {id: "old-root-a", cast_key: "cast-a", is_current_canonical: false, canonical_candidate_id: null, status: "approved"},
  {id: "old-variant-a", cast_key: "cast-a", canonical_candidate_id: "old-root-a", theme: "Old", status: "approved"},
];
const result = selection.requestedCandidatesForCanonical(candidates, "cast-a");
console.log(JSON.stringify(result.map((item) => ({
  id: item.id,
  label: selection.requestedCandidateLabel(item),
}))));
"""
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=Path(__file__).parents[1],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == [
        {"id": "root-a", "label": "Canonical · approved"},
        {"id": "variant-a-draft", "label": "Snow · draft"},
        {"id": "variant-a-approved", "label": "Night · approved"},
    ]


def test_ui_default_manifest_is_flight_ready_v2():
    root = Path(__file__).parents[1] / "pack_manager" / "web"
    selection = root / "selection.js"
    javascript = (root / "app.js").read_text()

    script = r"""
const selection = require("./pack_manager/web/selection.js");
console.log(JSON.stringify({
  character: selection.manifestTemplateForKind("character"),
  scene: selection.manifestTemplateForKind("scene"),
}));
"""
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=Path(__file__).parents[1],
        check=True,
        capture_output=True,
        text=True,
    )
    templates = json.loads(completed.stdout)

    assert templates["character"]["schema_version"] == 2
    assert templates["scene"]["schema_version"] == 2
    assert templates["character"]["tts"]["enabled"] is False
    assert "manifestTemplateForKind" in javascript
    assert "flight_ready" in javascript
    assert "syncManifestTemplateForSelectedPack" in javascript
    assert selection.read_text()


def test_manifest_templates_differ_by_kind():
    script = r"""
const selection = require("./pack_manager/web/selection.js");
const character = selection.manifestTemplateForKind("character");
const scene = selection.manifestTemplateForKind("scene");
console.log(JSON.stringify({
  characterHasTts: Object.prototype.hasOwnProperty.call(character, "tts"),
  sceneHasFrame: Object.prototype.hasOwnProperty.call(scene, "frame"),
}));
"""
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=Path(__file__).parents[1],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == {
        "characterHasTts": True,
        "sceneHasFrame": True,
    }


def test_ui_requires_two_hosts_and_refreshes_requested_candidates():
    root = Path(__file__).parents[1] / "pack_manager" / "web"
    html = (root / "index.html").read_text()
    javascript = (root / "app.js").read_text()

    assert 'name="BOT1"' in html
    bot2 = html.split('name="BOT2"', 1)[1].split("</select>", 1)[0]
    assert "required" in bot2
    assert "requestedCandidatesForCanonical" in javascript
    assert "addEventListener(" in javascript
    assert '"change"' in javascript
