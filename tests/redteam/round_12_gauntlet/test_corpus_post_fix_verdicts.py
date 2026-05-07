"""Post-fix verdict tests for the Round 12 corpus.

Each fixture's post_fix_v1_2_4 expectation is asserted. Passes
on v1.2.4 with the closure commits applied; fails on v1.2.3
(by design, that is the calibration gap Round 12 closes).
"""
from __future__ import annotations
import json
from pathlib import Path
import pytest
from bayyinah import scan_pdf

CORPUS_DIR = Path(__file__).parent
EXPECTED = json.loads((CORPUS_DIR / "EXPECTED.json").read_text())


@pytest.mark.parametrize("fixture_name", sorted(EXPECTED.keys()))
def test_post_fix_verdict(fixture_name: str) -> None:
    fixture = CORPUS_DIR / fixture_name
    if not fixture.exists():
        pytest.skip(f"{fixture_name} not regenerated; run builders")
    expected = EXPECTED[fixture_name]["post_fix_v1_2_4"]

    rd = scan_pdf(fixture).to_dict()
    fires = sorted({f.get('mechanism') for f in rd.get('findings', [])})

    assert rd.get('integrity_score') == expected["integrity_score"], (
        f"{fixture_name}: expected score {expected['integrity_score']}, "
        f"got {rd.get('integrity_score')}; fires={fires}"
    )
    assert fires == expected["fires"], (
        f"{fixture_name}: expected fires {expected['fires']}, got {fires}"
    )


def test_corpus_round_trip_byte_stable_on_pdftex_fixtures() -> None:
    """The pdfTeX builders are byte-stable across consecutive runs.

    Determinism is the v3 §12.1 pre-flight item: a non-deterministic
    fixture means future regen produces a different sha256, breaking
    EXPECTED.json's promise. SOURCE_DATE_EPOCH=0 strips the build
    timestamp.
    """
    import hashlib
    import subprocess
    targets = [
        ("build_clean_pdftex_article.py", "fixture_clean_pdftex_article.pdf"),
        ("build_clean_pdftex_with_hyperref.py", "fixture_clean_pdftex_with_hyperref.pdf"),
    ]
    for builder, output in targets:
        out_path = CORPUS_DIR / output
        if not out_path.exists():
            pytest.skip(f"{output} not present; run builder")
        sha_first = hashlib.sha256(out_path.read_bytes()).hexdigest()
        # Re-run builder
        result = subprocess.run(
            ["python3", str(CORPUS_DIR / builder)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            pytest.skip(f"builder failed (likely missing pdflatex): {result.stderr}")
        sha_second = hashlib.sha256(out_path.read_bytes()).hexdigest()
        assert sha_first == sha_second, (
            f"{output} not byte-stable across runs: {sha_first} != {sha_second}"
        )
