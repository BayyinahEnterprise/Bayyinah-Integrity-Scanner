"""
CorrelationEngine — cross-modal witness layer (Al-Baqarah 2:282 framing).

    وَاسْتَشْهِدُوا شَهِيدَيْنِ مِن رِّجَالِكُمْ ۖ فَإِن لَّمْ يَكُونَا
    رَجُلَيْنِ فَرَجُلٌ وَامْرَأَتَانِ مِمَّن تَرْضَوْنَ مِنَ الشُّهَدَاءِ

    "And call to witness two witnesses from among your men;
    if there are not two men, then a man and two women …"

Architectural reading. A single witness to a concealed payload is a
finding; two independent witnesses to the *same* payload are
coordination. Bayyinah's earlier phases built the individual witnesses
(one per analyzer, one per carrier layer). Phase 12 composes them:
when the zahir surface of one layer and the batin structure of another
both carry the same hidden string, the file is saying one thing with
two voices.

The engine is not a detector in the analyzer sense — it does not
inspect bytes, and it is not dispatched by file kind. It is a
*post-analysis composer* that runs against the Finding list a scan
has already produced, and emits new Findings only when the cross-
reference is unambiguous.

Two correlation modes:

    intra_file_correlate    A single file's findings.  Emits
                            ``coordinated_concealment`` when the same
                            normalised hidden-payload string appears in
                            two or more distinct findings (different
                            mechanism or different location).

    cross_file_correlate    A list of (file_path, findings) pairs from a
                            batch scan.  Emits
                            ``cross_format_payload_match`` when the same
                            normalised hidden-payload string appears in
                            findings from two or more distinct files.

Both modes share a single payload-extraction surface: the
``concealed`` field of each Finding, with some normalisation to strip
analyzer-specific framing (counts, parentheticals) and leave the
content.

Additive-only.  This module is imported by ``ScanService`` for the
non-PDF dispatch path; the PDF dispatch path never touches it, and
``bayyinah_v0.py`` / ``bayyinah_v0_1.py`` never reference it.  PDF
byte-identical parity is preserved by construction.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from domain import Finding
from domain.config import (
    CORRELATION_BASE_CONFIDENCE,
    CORRELATION_ESCALATION_COUNT,
    CORRELATION_FINGERPRINT_LEN,
    CORRELATION_LONG_PAYLOAD_LEN,
    CORRELATION_MAX_CONFIDENCE,
    CORRELATION_MIN_FILES,
    CORRELATION_MIN_OCCURRENCES,
    CORRELATION_MIN_PAYLOAD_ENTROPY,
    CORRELATION_MIN_PAYLOAD_LEN,
    CORRELATION_SHORT_PAYLOAD_LEN,
    CORRELATION_STOPWORDS,
    TIER,
)


# ---------------------------------------------------------------------------
# Payload extraction
# ---------------------------------------------------------------------------

# Mechanisms whose ``concealed`` / ``surface`` fields carry a literal
# hidden string worth correlating.  Counts-and-summaries mechanisms
# (e.g. "3 zero-width codepoint(s)") are excluded because their
# ``concealed`` field is boilerplate and would false-correlate across
# unrelated files.
_CORRELATABLE_MECHANISMS: frozenset[str] = frozenset({
    "image_text_metadata",
    "svg_hidden_text",
    "svg_microscopic_text",
    "high_entropy_metadata",
    "generative_cipher_signature",
    "tag_chars",
    "svg_embedded_script",
    "svg_embedded_data_uri",
    "svg_external_reference",
})

# Per-mechanism regex extracting the payload-bearing substring from the
# finding's description or concealed field.  Each regex's first capture
# group is the payload.  None = fall back to the concealed field itself.
_PAYLOAD_EXTRACTORS: dict[str, re.Pattern[str] | None] = {
    # ImageAnalyzer._emit_text_metadata_findings writes:
    #   description = f"Human-readable text found in {source}: {preview!r}. ..."
    # `preview!r` is a Python repr — a quoted string.  We capture the
    # inside of the repr quotes.
    "image_text_metadata": re.compile(
        r"Human-readable text found in [^:]+: ['\"](.+?)['\"]\. ",
        re.DOTALL,
    ),
    # SvgAnalyzer._detect_hidden_text writes:
    #   description = f"... Preview: {preview!r}. ..."
    #   concealed   = f"<{local}> text: {preview!r}"
    "svg_hidden_text": re.compile(
        r"Preview: ['\"](.+?)['\"]\. ",
        re.DOTALL,
    ),
    "svg_microscopic_text": re.compile(
        r"Preview: ['\"](.+?)['\"]\.",
        re.DOTALL,
    ),
    # ImageAnalyzer._emit_high_entropy_finding writes:
    #   concealed = "{N}-byte high-entropy payload (H=...)"
    # The payload itself is not in the finding — entropy is a shape
    # signal, not a content signal.  Fall back to the full concealed
    # string; correlation on high_entropy is by size+hash proxy rather
    # than content.  The shared-payload path comes via the
    # generative_cipher_signature finding (below), whose concealed field
    # DOES carry a representative slice of the matched payload.
    "high_entropy_metadata": None,
    # generative_cipher_signature emits the matched base64/hex substring
    # in its concealed field (see ImageAnalyzer Phase 12 helper).
    "generative_cipher_signature": re.compile(
        r"cipher-shape payload: ['\"](.+?)['\"]",
        re.DOTALL,
    ),
    # TAG char decoded shadow — from ImageAnalyzer, SvgAnalyzer,
    # TextFileAnalyzer, JsonAnalyzer descriptions:
    #   "... Decoded shadow: 'hidden'."
    "tag_chars": re.compile(
        r"Decoded shadow: ['\"](.+?)['\"]\.",
        re.DOTALL,
    ),
    # svg_embedded_script preview:
    #   "... Preview: 'alert(1)'"
    "svg_embedded_script": re.compile(
        r"Preview: ['\"](.+?)['\"]",
        re.DOTALL,
    ),
    # data: URI — we capture the full 'data:...' surface string.
    "svg_embedded_data_uri": None,
    # external URL — capture from description.
    "svg_external_reference": re.compile(
        r"external URL ['\"](.+?)['\"] ",
        re.DOTALL,
    ),
}


def _normalise_payload(s: str) -> str:
    """Canonicalise a payload for hashing.

    Strips leading/trailing whitespace, collapses internal whitespace
    runs to single spaces, and lowercases.  These transforms make two
    payloads whose only differences are whitespace or case compare
    equal — the adversarial case is often a payload inserted into two
    different contexts with cosmetic variation.
    """
    return " ".join(s.split()).lower()


def _payload_hash(payload: str) -> str:
    """SHA-256 first ``CORRELATION_FINGERPRINT_LEN`` hex chars.

    A short prefix of SHA-256 is collision-resistant at the scales
    Bayyinah operates on (thousands of findings per batch) and fits
    readably into a report description.
    """
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return digest[:CORRELATION_FINGERPRINT_LEN]


def _payload_entropy(payload: str) -> float:
    """Shannon entropy (bits per character) of a normalised payload.

    Empty input returns 0.0. Uniformly-random payloads approach
    ``log2(alphabet_size)`` — e.g. ~4.7 for hex, ~5 for lowercase ASCII,
    ~6 for full base64. Natural language falls in the 3.5-4.5 range
    (per-character, not per-word). Phase 13's gate uses this to reject
    payloads whose entropy is too low to plausibly be a deliberate
    marker — repetitive filler like ``"aaaaaa..."`` or whitespace-
    padded strings clear the length gate but should not correlate.
    """
    if not payload:
        return 0.0
    counts = Counter(payload)
    total = len(payload)
    entropy = 0.0
    for count in counts.values():
        probability = count / total
        entropy -= probability * math.log2(probability)
    return entropy


def _score_confidence(
    payload: str,
    match_count: int,
    mechanism_count: int,
) -> float:
    """Scale correlation-finding confidence on the strength of evidence.

    Four additive factors, each bounded in ``[0.0, 1.0]``, blended with
    small weights that sum to a single boost added to
    ``CORRELATION_BASE_CONFIDENCE``:

      * length factor — longer payloads are harder to reproduce by
        accident. Linear from 0 (short floor) to 1 (long floor).
      * count factor — more matches = more evidence. Linear from the
        minimum-occurrences floor upward, clamped at +4 extra matches.
      * diversity factor — more distinct *mechanisms* is stronger than
        the same mechanism firing twice. Linear from 1 to 4 mechanisms.
      * entropy factor — distinctive (random-looking) payloads are
        less likely to be coincidental. Linear from the entropy gate
        up to 5.0 bits/char (practical cap for ASCII-ish payloads).

    Result is clamped to ``[CORRELATION_BASE_CONFIDENCE,
    CORRELATION_MAX_CONFIDENCE]`` so even the weakest case reports at
    the base floor and the strongest case never claims certainty.

    This function is pure and deterministic; the caller supplies the
    already-normalised payload.
    """
    length_span = max(
        CORRELATION_LONG_PAYLOAD_LEN - CORRELATION_SHORT_PAYLOAD_LEN,
        1,
    )
    length_factor = (len(payload) - CORRELATION_SHORT_PAYLOAD_LEN) / length_span
    length_factor = max(0.0, min(1.0, length_factor))

    # Count factor — reward evidence above the minimum-occurrences
    # floor, clamped at +4 extra so a 100-way match does not runaway.
    extra_matches = max(match_count - CORRELATION_MIN_OCCURRENCES, 0)
    count_factor = min(extra_matches / 4.0, 1.0)

    # Diversity factor — the distinctness of *which* carriers ship the
    # payload. A payload in only one mechanism (even if repeated many
    # times) contributes zero; each additional mechanism up to four
    # earns a linear share.
    diversity_factor = min(max(mechanism_count - 1, 0) / 3.0, 1.0)

    entropy = _payload_entropy(payload)
    entropy_span = max(5.0 - CORRELATION_MIN_PAYLOAD_ENTROPY, 0.1)
    entropy_factor = (entropy - CORRELATION_MIN_PAYLOAD_ENTROPY) / entropy_span
    entropy_factor = max(0.0, min(1.0, entropy_factor))

    boost = (
        0.08 * length_factor
        + 0.08 * count_factor
        + 0.04 * diversity_factor
        + 0.04 * entropy_factor
    )
    confidence = CORRELATION_BASE_CONFIDENCE + boost
    return max(
        CORRELATION_BASE_CONFIDENCE,
        min(CORRELATION_MAX_CONFIDENCE, confidence),
    )


def _maybe_escalate_tier(base_tier: int, match_count: int) -> int:
    """Escalate a correlation finding's tier one step when coordination
    spans ``CORRELATION_ESCALATION_COUNT`` or more sites.

    Tiers in Bayyinah are lower-is-more-severe (1 = Verified, 2 =
    Structural, 3 = Interpretive). Escalation subtracts 1; base tier 1
    cannot escalate further. A wide-spread match — five or more
    coordinated sites — crosses from "pattern" into "unambiguous"
    territory, so we raise the tier to reflect that.
    """
    if match_count >= CORRELATION_ESCALATION_COUNT and base_tier > 1:
        return base_tier - 1
    return base_tier


def extract_payload(finding: Finding) -> str | None:
    """Extract the correlatable payload string from a finding, if any.

    Returns None when the finding's mechanism is not correlatable, when
    the extractor regex does not match, or when the resulting payload
    falls below ``CORRELATION_MIN_PAYLOAD_LEN``.  The minimum-length
    gate suppresses spurious matches on short generic strings.
    """
    if finding.mechanism not in _CORRELATABLE_MECHANISMS:
        return None

    extractor = _PAYLOAD_EXTRACTORS.get(finding.mechanism)
    candidate: str | None = None
    if extractor is None:
        # Fall back to the concealed field — surfaced directly by the
        # analyzer with no framing to strip.
        candidate = finding.concealed
    else:
        m = extractor.search(finding.description)
        if m is not None:
            candidate = m.group(1)
        else:
            # Secondary fallback: try the concealed field — some
            # analyzers put the same payload there.
            m2 = extractor.search(finding.concealed)
            if m2 is not None:
                candidate = m2.group(1)

    if candidate is None:
        return None

    normalised = _normalise_payload(candidate)
    if len(normalised) < CORRELATION_MIN_PAYLOAD_LEN:
        return None
    # Phase 13 stopword gate — exact-match on the full normalised
    # payload. Substring containment is deliberately NOT used: a payload
    # like "admin panel credentials" should still correlate; only the
    # bare token "admin" is rejected.
    if normalised in CORRELATION_STOPWORDS:
        return None
    # Phase 13 entropy gate — reject repetitive runs that clear the
    # length floor but carry too little information to be a marker.
    if _payload_entropy(normalised) < CORRELATION_MIN_PAYLOAD_ENTROPY:
        return None
    return normalised


# ---------------------------------------------------------------------------
# CorrelationEngine
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _PayloadRef:
    """Lightweight reference to a finding that carries a given payload.

    Captured during correlation so the emitted ``coordinated_concealment``
    finding can name the specific mechanisms + locations it cross-
    references.  Kept internal to the module — not part of the public
    surface.
    """
    mechanism: str
    location: str


class CorrelationEngine:
    """Compose per-finding observations into cross-layer witnesses.

    Stateless: every call receives its inputs and returns its emitted
    findings; no internal caches or registration state.  A caller may
    share one engine across threads without coordination.
    """

    def intra_file_correlate(
        self,
        findings: Iterable[Finding],
        file_path: Path,
    ) -> list[Finding]:
        """Emit coordinated_concealment findings for one file's scan.

        Rules:

          * Only findings whose mechanism is in ``_CORRELATABLE_MECHANISMS``
            are considered; everything else passes through unexamined.
          * Each qualifying finding's payload is extracted and normalised.
          * When the same normalised payload appears in
            ``CORRELATION_MIN_OCCURRENCES`` or more findings AND those
            findings use at least two distinct (mechanism, location)
            pairs, one ``coordinated_concealment`` finding is emitted
            per unique payload.

        The "two distinct (mechanism, location) pairs" guard prevents
        multiple findings from the same scan of the same carrier (e.g.
        two tEXt chunks at different offsets with the same text) from
        firing coordination unless they are in different mechanisms or
        distinct locations.

        Returns a new list; does not mutate the input.
        """
        buckets: dict[str, list[_PayloadRef]] = {}
        for finding in findings:
            payload = extract_payload(finding)
            if payload is None:
                continue
            buckets.setdefault(payload, []).append(_PayloadRef(
                mechanism=finding.mechanism,
                location=finding.location,
            ))

        emitted: list[Finding] = []
        for payload, refs in buckets.items():
            if len(refs) < CORRELATION_MIN_OCCURRENCES:
                continue
            unique_sites = {(r.mechanism, r.location) for r in refs}
            if len(unique_sites) < CORRELATION_MIN_OCCURRENCES:
                continue

            mechanisms = sorted({r.mechanism for r in refs})
            locations = sorted({r.location for r in refs})
            fp = _payload_hash(payload)
            preview = payload if len(payload) <= 80 else payload[:77] + "..."
            # Phase 13 — scale confidence + escalate tier on spread.
            # Intra-file spread is measured by distinct sites (unique
            # mechanism + location pairs) so a payload deposited in one
            # mechanism at one location that repeats many times does not
            # inflate the signal.
            site_count = len(unique_sites)
            confidence = _score_confidence(
                payload,
                match_count=site_count,
                mechanism_count=len(mechanisms),
            )
            tier = _maybe_escalate_tier(
                TIER["coordinated_concealment"],
                match_count=site_count,
            )
            emitted.append(Finding(
                mechanism="coordinated_concealment",
                tier=tier,
                confidence=confidence,
                description=(
                    f"Same hidden payload (fingerprint {fp}) present in "
                    f"{len(refs)} finding(s) across {len(mechanisms)} "
                    f"mechanism(s) ({', '.join(mechanisms)}) and "
                    f"{len(locations)} location(s). "
                    "Two carrier layers ship the same concealed content — "
                    "a coordination pattern rather than an incidental "
                    f"repeat. Payload preview: {preview!r}."
                ),
                location=str(file_path),
                surface="(each carrier layer shows clean surface output)",
                concealed=(
                    f"payload fingerprint {fp} "
                    f"({len(refs)} findings, {len(mechanisms)} mechanisms)"
                ),
                source_layer="batin",
            ))
        return emitted

    def cross_file_correlate(
        self,
        scans: Iterable[tuple[Path, Iterable[Finding]]],
    ) -> list[Finding]:
        """Emit cross_format_payload_match findings for a batch.

        Takes a sequence of ``(file_path, findings)`` pairs — typically
        the output of ``ScanService.scan_batch``.  For each unique
        normalised payload, records which files carry it; emits one
        finding per payload that appears in
        ``CORRELATION_MIN_FILES`` or more distinct files.

        The emitted findings reference every file the payload was seen
        in.  Their ``location`` field carries a semicolon-joined list of
        the file paths — intentionally verbose so the reader can locate
        the coordinated set directly.
        """
        buckets: dict[str, dict[Path, list[str]]] = {}
        for file_path, findings in scans:
            for finding in findings:
                payload = extract_payload(finding)
                if payload is None:
                    continue
                by_file = buckets.setdefault(payload, {})
                by_file.setdefault(file_path, []).append(finding.mechanism)

        emitted: list[Finding] = []
        for payload, by_file in buckets.items():
            if len(by_file) < CORRELATION_MIN_FILES:
                continue
            fp = _payload_hash(payload)
            files_sorted = sorted(by_file.keys(), key=lambda p: str(p))
            mechanisms = sorted({
                m for ms in by_file.values() for m in ms
            })
            preview = payload if len(payload) <= 80 else payload[:77] + "..."
            # Phase 13 — scale confidence + escalate tier on spread.
            # Cross-file spread is measured in distinct files: a payload
            # that surfaces in six unrelated files is stronger evidence
            # than one that surfaces in the bare minimum two.
            file_count = len(files_sorted)
            confidence = _score_confidence(
                payload,
                match_count=file_count,
                mechanism_count=len(mechanisms),
            )
            tier = _maybe_escalate_tier(
                TIER["cross_format_payload_match"],
                match_count=file_count,
            )
            emitted.append(Finding(
                mechanism="cross_format_payload_match",
                tier=tier,
                confidence=confidence,
                description=(
                    f"Same hidden payload (fingerprint {fp}) present in "
                    f"{len(files_sorted)} distinct file(s) via mechanism(s) "
                    f"{', '.join(mechanisms)}. "
                    "A payload shared across unrelated files in the same "
                    "scan batch is a coordination signal beyond any single "
                    f"file's concealment surface. Payload preview: "
                    f"{preview!r}."
                ),
                location="; ".join(str(p) for p in files_sorted),
                surface="(each file shows clean surface output in isolation)",
                concealed=(
                    f"payload fingerprint {fp} "
                    f"across {len(files_sorted)} file(s)"
                ),
                source_layer="batin",
            ))
        return emitted


__all__ = [
    "CorrelationEngine",
    "extract_payload",
]
