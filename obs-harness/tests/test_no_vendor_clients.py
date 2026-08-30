"""T11: this package must not grow a fal or OpenAI client."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Split so this file does not match its own needles.
BANNED = (
    ("import", "fal"),
    ("from", "fal"),
    ("import", "openai"),
    ("from", "openai"),
    ("fal", "_client"),
)


def test_t11_no_vendor_clients():
    hits = []
    for path in ROOT.rglob("*.py"):
        if ".venv" in path.parts or ".pytest_cache" in path.parts:
            continue
        if path.name == "test_no_vendor_clients.py":
            continue
        text = path.read_text()
        for left, right in BANNED:
            needle = left + " " + right if right != "_client" else left + right
            if needle in text:
                hits.append(f"{path}: {needle}")
    assert hits == []
