#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# make-archive.sh — produce a clean zip of the Bayyinah working tree.
#
# macOS's Finder zip and `ditto -c` both inject __MACOSX/ resource-fork
# sidecar directories and .DS_Store files into archives. Those pollute
# the zip for every collaborator who extracts it, and they are exactly
# the kind of silent-surface artifact this scanner is designed to flag.
#
# This script wraps `zip` with the two exclusions that keep a shared
# archive clean. Run from the repository root:
#
#     ./scripts/make-archive.sh                         # default name
#     ./scripts/make-archive.sh bayyinah-v1.0-share     # custom name
#
# Output: <name>.zip, one level up from the repo root so the extracted
# folder reconstructs cleanly.
# ---------------------------------------------------------------------------

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARCHIVE_NAME="${1:-$(basename "$REPO_ROOT")}"
ARCHIVE_PATH="${REPO_ROOT}/../${ARCHIVE_NAME}.zip"

cd "$(dirname "$REPO_ROOT")"
FOLDER="$(basename "$REPO_ROOT")"

echo "Creating clean archive: ${ARCHIVE_PATH}"
echo "Excluding: .DS_Store, __MACOSX/, __pycache__/, *.egg-info, .pytest_cache"

# -r     : recurse into directories
# -x ... : exclusion patterns — each must cover both top-level and nested
#          occurrences. The patterns match against the archive path, not
#          the filesystem path.
zip -r "${ARCHIVE_PATH}" "${FOLDER}" \
    -x "*.DS_Store" \
    -x "*__MACOSX/*" \
    -x "*__pycache__/*" \
    -x "*.egg-info/*" \
    -x "*.pytest_cache/*" \
    -x "*.mypy_cache/*" \
    -x "*.ruff_cache/*" \
    -x "*build/*" \
    -x "*/bayyinah-1.0.0/*"

echo ""
echo "Done. Archive contents summary:"
unzip -l "${ARCHIVE_PATH}" | tail -1
echo ""
echo "Verify no junk entries:"
if unzip -l "${ARCHIVE_PATH}" | grep -E "(__MACOSX|\.DS_Store|__pycache__|\.egg-info)" > /dev/null; then
    echo "  WARNING — junk entries found in archive:"
    unzip -l "${ARCHIVE_PATH}" | grep -E "(__MACOSX|\.DS_Store|__pycache__|\.egg-info)"
    exit 1
else
    echo "  OK — no .DS_Store / __MACOSX / __pycache__ / .egg-info in archive."
fi
