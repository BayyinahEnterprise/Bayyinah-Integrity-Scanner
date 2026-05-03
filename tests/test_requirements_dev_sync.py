"""Structural enforcement of the requirements-dev.txt / [dev] sync.

The leading comment in requirements-dev.txt has long claimed equivalence
with the [project.optional-dependencies].dev table in pyproject.toml, but
no test enforced it. The two surfaces drifted by four entries between
v1.1.x and v1.2.2. This test parses both files and asserts the
dependency specs are identical, so any future drift fails CI rather
than slipping into a release.

Closes Fraz round 10 MEDIUM 1.
"""

from __future__ import annotations

from pathlib import Path

# tomllib is stdlib in 3.11+; project supports 3.10+ so use the tomli
# back-compat alias when running on 3.10. tomli is a transitive dev
# dep available in this environment.
try:
    import tomllib  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - 3.10 path
    import tomli as tomllib  # type: ignore[import-not-found, no-redef]


_REPO_ROOT = Path(__file__).resolve().parent.parent


def _parse_pyproject_dev_extras() -> set[str]:
    """Return the [project.optional-dependencies].dev set from pyproject."""
    with (_REPO_ROOT / "pyproject.toml").open("rb") as f:
        data = tomllib.load(f)
    extras = data["project"]["optional-dependencies"]["dev"]
    return {entry.strip() for entry in extras}


def _parse_requirements_dev_txt() -> set[str]:
    """Return the dependency-line set from requirements-dev.txt.

    Skips blank lines, comment lines (``#``-prefixed), and ``-r``
    references to other requirements files.
    """
    deps: set[str] = set()
    path = _REPO_ROOT / "requirements-dev.txt"
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        if line.startswith("-r"):
            continue
        deps.add(line)
    return deps


def test_requirements_dev_matches_pyproject_dev_extras() -> None:
    """requirements-dev.txt must list the same dependency specs as
    [project.optional-dependencies].dev in pyproject.toml.

    Failure prints which file is missing which entries so the fix shape
    is obvious from the test output alone.
    """
    pyproj = _parse_pyproject_dev_extras()
    reqs = _parse_requirements_dev_txt()

    missing_from_reqs = pyproj - reqs
    missing_from_pyproj = reqs - pyproj

    msg_lines: list[str] = []
    if missing_from_reqs:
        msg_lines.append(
            "Entries in pyproject [dev] but missing from "
            f"requirements-dev.txt: {sorted(missing_from_reqs)}"
        )
    if missing_from_pyproj:
        msg_lines.append(
            "Entries in requirements-dev.txt but missing from "
            f"pyproject [dev]: {sorted(missing_from_pyproj)}"
        )

    assert pyproj == reqs, "\n".join(msg_lines) or "drift detected"
