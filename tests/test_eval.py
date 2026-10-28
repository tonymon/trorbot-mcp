"""Run the ground-truth eval offline (replayed fixtures) as part of the test suite."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

EVAL_DIR = Path(__file__).parent.parent / "eval"


@pytest.fixture(scope="module")
def run_eval():
    spec = importlib.util.spec_from_file_location("run_eval", EVAL_DIR / "run_eval.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_eval_replay_all_cases_pass(run_eval):
    expected = json.loads((EVAL_DIR / "expected.json").read_text())
    results = await run_eval.run_cases(expected, "replay")
    failed = [r for r in results if not r["pass"]]
    assert not failed, json.dumps(failed, indent=2)
    assert len(results) == 8


def test_expected_answers_match_snapshot(run_eval):
    """Committed expected.json must be exactly what the snapshot implies."""
    snapshot = json.loads((EVAL_DIR / "fixtures" / "raw_snapshot.json").read_text())
    expected = json.loads((EVAL_DIR / "expected.json").read_text())
    assert json.loads(json.dumps(run_eval.compute_expected(snapshot))) == expected


@pytest.mark.parametrize(
    ("actual", "expected", "ok"),
    [
        (98.6437, 98.64373027, True),  # tool rounding is well inside 0.01%
        (98.6, 98.64373027, False),
        (0.0, 0.0, True),
        ("Department of Justice", "Department of Justice", True),
        ("department of justice", "Department of Justice", False),
        ([1.0, 2.0], [1.0, 2.0, 3.0], False),
        ({"agency": "A", "x": 1.0}, {"agency": "A"}, False),
        (None, 71, False),
    ],
)
def test_scoring(run_eval, actual, expected, ok):
    assert run_eval.matches(actual, expected) is ok
