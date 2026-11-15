"""Gate: the scanner agrees with rendering on every small-scope page.

Pages differ from an ordinary visible line in at most two of the eight
grammar dimensions (124 pages). Within that horizon the scanner must
report every payload a text extractor returns and a reader cannot see,
must not report a legible one, and must never be incomplete. The one
known disagreement is pinned, so a change in either direction is
deliberate. Beyond the horizon nothing is claimed here; the full product
(3,840 pages) is run from ``bench/concealment_map/run_map.py``.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pikepdf")

from bench.concealment_map.grammar import DIMENSIONS, enumerate_configs
from bench.concealment_map.run_map import run

# Text set mostly beyond the right edge in a 3 pt font: the visible sliver
# is too small to call legible, yet no finding fires. Documented limit.
KNOWN_FALSE_NEGATIVES = {"position=edge|size=3"}


def test_grammar_size() -> None:
    product = 1
    for values in DIMENSIONS.values():
        product *= len(values)
    assert product == 3840
    assert sum(1 for _ in enumerate_configs(1)) == 17
    assert sum(1 for _ in enumerate_configs(2)) == 124


def test_small_scope_agrees_with_rendering() -> None:
    counts, disagreements = run(2)
    assert sum(counts.values()) == 124
    assert counts["incomplete"] == 0
    assert counts["false_positive"] == 0, [d["config"] for d in disagreements]
    false_negatives = {d["config"] for d in disagreements
                       if d["outcome"] == "false_negative"}
    assert false_negatives == KNOWN_FALSE_NEGATIVES
    # The map must be able to see: both verdicts occur.
    assert counts["agree_reported"] >= 100 and counts["agree_clean"] >= 5


def test_without_the_render_check_the_map_finds_misses(monkeypatch) -> None:
    """Evidence that the map sees: switch the invariant off and the
    mechanism-by-mechanism detectors alone miss whole classes."""
    monkeypatch.setenv("BAYYINAH_RENDER_ORACLE", "0")
    counts, disagreements = run(1)
    missed = {d["config"] for d in disagreements if d["outcome"] == "false_negative"}
    assert {"clip=clip_away", "alpha=0", "overlay=white_box", "render_mode=7"} <= missed
