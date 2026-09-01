import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from core import Manifest
from spend import SpendCapReached, SpendMeter
from writer import sanitize_line


class TestSpendMeter:
    def test_charge_accumulates(self):
        m = SpendMeter(0.04, 20.0)
        cost, cum = m.charge(5)
        assert cost == pytest.approx(0.20)
        assert cum == pytest.approx(0.20)
        _, cum = m.charge(5)
        assert cum == pytest.approx(0.40)

    def test_authorize_refuses_past_cap(self):
        m = SpendMeter(0.04, 0.30)
        m.charge(5)  # 0.20
        with pytest.raises(SpendCapReached):
            m.authorize(5)  # 0.20 + 0.20 > 0.30

    def test_resume_from_prior_spend(self):
        m = SpendMeter(0.04, 1.0, already_spent=0.95)
        assert not m.can_afford(5)


class TestSanitizeLine:
    def test_enforces_max_words_and_period(self):
        line = sanitize_line("one two three four five six seven eight nine ten", 5)
        assert line == "one two three four five."

    def test_strips_stage_directions_quotes_labels(self):
        line = sanitize_line('VOLT-9: *leans in* "The news is (pause) fine"', 12)
        assert line == "The news is fine."

    def test_takes_first_line_only(self):
        assert sanitize_line("First line.\nSecond line.", 12) == "First line."

    def test_exclamation_becomes_period(self):
        assert sanitize_line("Breaking news!", 12) == "Breaking news."

    def test_empty_stays_empty(self):
        assert sanitize_line("   \n  ", 12) == ""


class TestManifest:
    def test_roundtrip_spend_and_numbering(self, tmp_path):
        m = Manifest(tmp_path / "takes.jsonl")
        assert m.next_take_number() == 1
        m.append({"take": 1, "cost_usd": 0.2, "status": "ready"})
        m.append({"take": 2, "cost_usd": 0.2, "status": "dropped_422"})
        assert m.total_spend() == pytest.approx(0.4)
        assert m.next_take_number() == 3
