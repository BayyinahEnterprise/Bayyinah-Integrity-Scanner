"""
EmlAnalyzer — full zahir/batin witness for RFC 5322 email messages.

    وَلَا تَلْبِسُوا الْحَقَّ بِالْبَاطِلِ وَتَكْتُمُوا الْحَقَّ وَأَنتُمْ تَعْلَمُونَ
    (Al-Baqarah 2:42)

    "Do not mix truth with falsehood, nor conceal the truth while you
    know it."

Architectural reading. Email is the format that most literally ships
different content to different audiences. A single message carries:

  * The rendered HTML body — what the recipient sees when their client
    displays the message.
  * The ``text/plain`` alternative — what text-only readers, search
    indexers, spam filters, and LLM ingestion pipelines read.
  * The envelope headers — what the routing infrastructure trusts.
  * The attachment graph — payloads that may or may not be surfaced to
    the reader, each its own document format.

Al-Baqarah 2:14 — "When they meet those who believe, they say, 'We
believe,' but when they are alone with their devils, they say, 'Indeed,
we are with you'." Multipart/alternative is the canonical envelope
shape of exactly this pattern: two audiences, two renderings, one
message.

Zahir (what the audience sees / can perceive)
  * ``eml_multipart_alternative_divergence`` — the ``text/plain`` and
    ``text/html`` parts of a ``multipart/alternative`` diverge in
    material content. Human reader and text indexer see different
    messages.
  * ``eml_hidden_html_content`` — text in the HTML body sits inside a
    render-suppressed element. Parallels ``html_hidden_text`` but
    scoped to the email body surface.
  * ``eml_display_name_spoof`` — the ``From`` header's display name
    performs a trusted identity while the real address lives in an
    unrelated domain (``"Bank Support" <attacker@evil.example>``).
  * ``eml_encoded_subject_anomaly`` — an RFC 2047 encoded-word in a
    header decodes to a codepoint stream carrying a concealment class
    (zero-width / TAG / bidi-control / homoglyph / math-alphanumeric).

Batin (structural / object graph)
  * ``eml_executable_attachment`` — attachment with an executable
    filename extension or declared MIME type.
  * ``eml_macro_attachment`` — attachment with a macro-enabled Office
    extension (.docm / .xlsm / .pptm / …).
  * ``eml_attachment_present`` — any attachment at all. Tier-3
    interpretive; surfaced for reader context.
  * ``eml_external_reference`` — HTML body contains resource-loading
    attributes pointing at absolute remote URLs (tracking pixels,
    remote images, remote scripts, remote CSS).
  * ``eml_smuggled_header`` — duplicate single-instance headers
    (``From``, ``Subject``, ``Date``, …) or CRLF-injected header values.
  * ``eml_nested_eml`` — a ``message/rfc822`` attachment carrying
    another email inside.
  * ``eml_mime_boundary_anomaly`` — multipart boundary that is
    suspiciously short, reused, or appears inside a part's body.

Supported FileKinds: ``{FileKind.EML}``. The router classifies emails
via RFC 5322 header-shape sniff (canonical header name at byte 0, or
an mbox ``From `` envelope line) plus extension fallback.

Composition with the analyzer registry. Attachments are recursively
scanned via ``application.default_registry()`` — the EML analyzer
does not duplicate PDF / DOCX / HTML / image / XLSX / PPTX detection
logic. Each attachment's bytes are written to a bounded temporary
file, classified by the file router, dispatched through the registry,
and the nested findings are folded into the outer report with the
attachment's name prefixed into their location string so the reader
can trace provenance. This is the "each tribe knew its
drinking-place" (Al-Baqarah 2:60) principle applied at the container
boundary: the email analyzer knows emails, the format analyzers know
their formats, and the registry composes them without cross-talk.

Additive-only. Nothing in this module is imported by ``bayyinah_v0.py``
or ``bayyinah_v0_1.py``; the PDF pipeline remains byte-identical. All
new mechanisms are registered in ``domain/config.py`` alongside the
existing catalog.
"""

from __future__ import annotations

import email
import email.header
import email.message
import email.policy
import os
import re
import tempfile
from pathlib import Path
from typing import ClassVar, Iterable

from analyzers.base import BaseAnalyzer
from domain import (
    Finding,
    IntegrityReport,
    SourceLayer,
    apply_scan_incomplete_clamp,
    compute_muwazana_score,
    get_current_limits,
)
from domain.config import (
    BIDI_CONTROL_CHARS,
    CONFUSABLE_TO_LATIN,
    MATH_ALPHANUMERIC_RANGE,
    TAG_CHAR_RANGE,
    TIER,
    ZERO_WIDTH_CHARS,
)
from infrastructure.file_router import FileKind, FileRouter

# v1.1.2 EML format-gauntlet detectors. Each is a standalone byte-
# deterministic function that opens its own bytes from the same path;
# they parallel the DOCX / XLSX / HTML v1.1.2 wiring pattern. Failures
# are absorbed by the dispatch loop in ``scan`` so the walker findings
# remain authoritative.
from analyzers.eml_from_replyto_mismatch import detect_eml_from_replyto_mismatch
from analyzers.eml_returnpath_from_mismatch import (
    detect_eml_returnpath_from_mismatch,
)
from analyzers.eml_received_chain_anomaly import detect_eml_received_chain_anomaly
from analyzers.eml_base64_text_part import detect_eml_base64_text_part
from analyzers.eml_header_continuation_payload import (
    detect_eml_header_continuation_payload,
)
from analyzers.eml_xheader_payload import detect_eml_xheader_payload


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maximum bytes of a .eml we inspect in one pass. Real email is rarely
# over a few MB after attachments are counted; 32 MB caps pathological
# or adversarial bulk while accommodating legitimate 25 MB attachment
# limits common to most providers.
_MAX_EML_BYTES: int = 32 * 1024 * 1024

# Maximum individual attachment size we write to disk for recursive
# scanning. An adversarial email could attach a multi-gigabyte blob to
# exhaust disk during scanning; we cap at 16 MB which is generous for
# real attachments while protective under abuse.
_MAX_ATTACHMENT_BYTES: int = 16 * 1024 * 1024

# Executable filename extensions that fire ``eml_executable_attachment``.
# The list mirrors the canonical Microsoft "level 1" attachment blocklist
# plus common cross-platform script extensions. Lower-case, no leading
# dot.
_EXECUTABLE_EXTENSIONS: frozenset[str] = frozenset({
    # Windows PE / installer
    "exe", "com", "scr", "pif", "msi", "msp", "cpl", "dll",
    # Shell / batch
    "bat", "cmd", "sh",
    # Scripting — Windows
    "vbs", "vbe", "wsf", "wsh", "ws", "hta",
    "ps1", "psm1", "psd1", "ps1xml", "ps2", "ps2xml",
    # Scripting — cross-platform
    "js", "jse", "jar",
    # Registry / shortcut / config vectors
    "reg", "lnk", "inf", "url", "scf",
    # Misc executable-class
    "chm", "application", "gadget", "workflow",
    # Legacy but occasionally still observed
    "bas", "isp", "vb", "ws", "wsc",
})

# Macro-enabled Office extensions that fire ``eml_macro_attachment``.
# These are the file types whose format explicitly enables VBA macro
# execution at open time (contrast: docx / xlsx / pptx do not).
_MACRO_EXTENSIONS: frozenset[str] = frozenset({
    "docm", "dotm",       # Word macro-enabled
    "xlsm", "xltm", "xlsb", "xlam",  # Excel macro-enabled + binary
    "pptm", "potm", "ppsm",         # PowerPoint macro-enabled
})

# MIME content types we treat as executable. These are the
# canonical types a mail scanner pipeline has historically
# blocklisted; the list is deliberately short.
_EXECUTABLE_MIME_TYPES: frozenset[str] = frozenset({
    "application/x-msdownload",
    "application/x-msi",
    "application/x-bat",
    "application/x-sh",
    "application/x-msdos-program",
    "application/x-dosexec",
    "application/x-executable",
    "application/hta",
    "application/javascript",
    "application/x-shockwave-flash",
    "application/x-ms-shortcut",
})

# Headers that RFC 5322 §3.6 declares single-occurrence. A message
# carrying two of any of these is either a forwarded-and-re-wrapped
# fragment (rare in the wild) or deliberate smuggling.
_SINGLE_INSTANCE_HEADERS: frozenset[str] = frozenset({
    "from", "sender", "reply-to", "to", "cc", "bcc",
    "message-id", "in-reply-to", "references", "subject", "date",
    "mime-version",
})

# Minimum boundary length considered safe. Real MUA-emitted boundaries
# are 30+ characters of random hex or base64; a 3-or-fewer char boundary
# is a smuggling-aid shape ("=", "--", "-A-").
_MIN_SAFE_BOUNDARY_LEN: int = 4

# Multipart/alternative word-level Jaccard similarity below which plain
# and HTML bodies are called "materially divergent". 0.5 is a forgiving
# threshold — routine HTML wrappers (font, color, logo text) naturally
# add a few words not in plain text, but a value this low requires over
# half the words to differ, which is the shape we target.
_ALTERNATIVE_DIVERGENCE_THRESHOLD: float = 0.5

# Minimum word count in either body before divergence is evaluated.
# Trivially short bodies produce unstable similarity scores; we stay
# silent below this length.
_ALTERNATIVE_MIN_WORDS: int = 6

# Hidden-HTML detection patterns (subset of HtmlAnalyzer's list — the
# email body variant intentionally restricts to the most common idioms
# to keep false positives low in newsletter HTML, which routinely uses
# tracking-pixel imagery that is technically "invisible" but not
# content-bearing).
_HIDDEN_STYLE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"display\s*:\s*none\b",           re.IGNORECASE),
    re.compile(r"visibility\s*:\s*hidden\b",      re.IGNORECASE),
    re.compile(r"opacity\s*:\s*0(?:\.0+)?\b",     re.IGNORECASE),
    re.compile(r"font-size\s*:\s*0(?:px|pt|em)?\b", re.IGNORECASE),
)

# Absolute-remote URL prefixes used by external-reference detection.
_EXTERNAL_URL_PREFIXES: tuple[str, ...] = (
    "http://", "https://", "//", "ftp://",
)

# Element attribute positions that load a remote resource at render time.
# HTML's full attribute set is in HtmlAnalyzer._EXTERNAL_REF_ATTRS; the
# email variant focuses on the attributes that actually appear in mail
# HTML bodies (no <form action>, no <object data> — those are web-app
# shapes, not mail shapes).
_EMAIL_EXTERNAL_REF_ATTRS: dict[str, tuple[str, ...]] = {
    "img":    ("src",),
    "image":  ("src",),
    "link":   ("href",),
    "script": ("src",),
    "iframe": ("src",),
    "source": ("src",),
}


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _decode_header_value(value: str | None) -> str:
    """Decode an RFC 2047 encoded-word header value into a unicode str.

    ``email.header.decode_header`` returns a list of (bytes_or_str,
    charset) pairs; we reassemble them into a single string,
    best-effort-decoding bytes fragments via the declared charset and
    falling back to UTF-8 with replacement on failure. Headers with no
    encoded-words pass through unchanged.
    """
    if value is None:
        return ""
    parts = email.header.decode_header(value)
    out: list[str] = []
    for chunk, charset in parts:
        if isinstance(chunk, bytes):
            try:
                out.append(chunk.decode(charset or "utf-8", errors="replace"))
            except (LookupError, UnicodeDecodeError):
                out.append(chunk.decode("utf-8", errors="replace"))
        else:
            out.append(chunk)
    return "".join(out)


def _extract_email_address(raw: str) -> tuple[str, str]:
    """Split a From-style field into ``(display_name, address)``.

    Returns ``("", "")`` when no address can be extracted. The
    parser is intentionally permissive — adversarial From fields often
    include unbalanced quotes or angle brackets, and we want to surface
    what a casual reader would see.
    """
    if not raw:
        return ("", "")
    # Angle-bracket form: "Display Name" <addr@host>
    m = re.match(
        r"""
        \s*
        (?:"([^"]*)"|([^<]*?))   # display name (quoted or bare)
        \s*<\s*([^>\s]+)\s*>\s*  # <addr>
        $
        """,
        raw,
        re.VERBOSE,
    )
    if m:
        quoted, bare, addr = m.groups()
        name = (quoted if quoted is not None else bare) or ""
        return (name.strip(), addr.strip())

    # Bare address with no display name.
    m2 = re.match(r"\s*([^\s<>@]+@[^\s<>@]+)\s*$", raw)
    if m2:
        return ("", m2.group(1).strip())

    return ("", "")


def _domain_of(addr: str) -> str:
    """Return the lowercased domain portion of an email address."""
    if "@" not in addr:
        return ""
    return addr.split("@", 1)[1].strip().lower().rstrip(">")


def _strip_html_tags(html: str) -> str:
    """Very permissive tag stripper — produces a rough text rendering.

    Good enough for word-token comparison; NOT a general-purpose HTML
    renderer. Script and style bodies are removed entirely (they are
    code, not user-visible text). Numeric character references are
    decoded via ``html.unescape``.
    """
    if not html:
        return ""
    import html as _html  # local import — only needed here

    # Remove script and style bodies outright.
    without_code = re.sub(
        r"<script[^>]*>.*?</script>", " ", html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    without_code = re.sub(
        r"<style[^>]*>.*?</style>", " ", without_code,
        flags=re.IGNORECASE | re.DOTALL,
    )
    # Strip remaining tags.
    no_tags = re.sub(r"<[^>]+>", " ", without_code)
    # Decode entities.
    return _html.unescape(no_tags)


def _word_tokens(text: str) -> set[str]:
    """Lowercased word tokens for jaccard comparison.

    Very short tokens (<= 2 chars) are discarded — prepositions and
    punctuation-stripped fragments are high-frequency noise that
    dominates similarity scores without carrying content signal.
    """
    if not text:
        return set()
    words = re.findall(r"[A-Za-z0-9]{3,}", text)
    return {w.lower() for w in words}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _has_hidden_style(style_value: str) -> bool:
    if not style_value:
        return False
    return any(p.search(style_value) for p in _HIDDEN_STYLE_PATTERNS)


def _is_external_url(url: str) -> bool:
    if not url:
        return False
    return url.strip().lower().startswith(_EXTERNAL_URL_PREFIXES)


def _is_latin_letter(ch: str) -> bool:
    cp = ord(ch)
    return 0x41 <= cp <= 0x5A or 0x61 <= cp <= 0x7A


# ---------------------------------------------------------------------------
# EmlAnalyzer
# ---------------------------------------------------------------------------


class EmlAnalyzer(BaseAnalyzer):
    """Dual-witness analyzer for RFC 5322 email messages.

    The scan workflow:

        1. Read the file (bounded by ``_MAX_EML_BYTES``) and parse with
           ``email.parser.BytesParser`` under ``email.policy.default``.
           A parse failure becomes a ``scan_error`` finding.
        2. Inspect the top-level headers for display-name spoofing,
           duplicate single-instance headers, and RFC 2047
           encoded-subject anomalies.
        3. Walk the message tree. For each part:
             - record multipart boundaries for later anomaly checks;
             - if the part is multipart/alternative, compare its
               text/plain and text/html children;
             - if the part is text/html, scan its body for hidden
               text and external references;
             - if the part is an attachment, classify it and
               (conditionally) dispatch it through the default
               analyzer registry for recursive scanning.
        4. Evaluate boundary anomalies against the collected set.
        5. Aggregate every finding into one ``IntegrityReport`` whose
           integrity score is the muwazana of the merged findings.

    ``supported_kinds = {FileKind.EML}`` keeps this analyzer disjoint
    from every other registered analyzer — an email never routes through
    the text-file path or the JSON path, and no other analyzer routes
    through this one.
    """

    name: ClassVar[str] = "eml"
    error_prefix: ClassVar[str] = "EML scan error"
    # Class default — ``scan_error`` findings are structural. Per-finding
    # source_layer is set individually for every zahir / batin detector.
    source_layer: ClassVar[SourceLayer] = "batin"
    supported_kinds: ClassVar[frozenset[FileKind]] = frozenset({FileKind.EML})

    # ------------------------------------------------------------------
    # Public scan
    # ------------------------------------------------------------------

    def scan(self, file_path: Path) -> IntegrityReport:  # noqa: D401
        """Scan the .eml file at ``file_path``."""
        try:
            raw = file_path.read_bytes()
        except OSError as exc:
            return self._scan_error_report(
                file_path, f"could not read file: {exc}",
            )

        if len(raw) > _MAX_EML_BYTES:
            raw = raw[:_MAX_EML_BYTES]

        try:
            msg = email.message_from_bytes(raw, policy=email.policy.default)
        except Exception as exc:  # noqa: BLE001 — email lib is quite permissive but not infallible
            return self._scan_error_report(
                file_path, f"could not parse email: {exc}",
            )

        findings: list[Finding] = []
        try:
            self._inspect_headers(msg, file_path, findings)
            self._walk_parts(msg, file_path, findings, depth=0)
        except Exception as exc:  # noqa: BLE001 — defensive guard
            findings.append(Finding(
                mechanism="scan_error",
                tier=TIER["scan_error"],
                confidence=1.0,
                description=(
                    f"EML walk aborted mid-message: {exc}"
                ),
                location=str(file_path),
                surface="(walk aborted)",
                concealed=(
                    "absence of later findings cannot be taken as cleanness"
                ),
                source_layer="batin",
            ))
            report = IntegrityReport(
                file_path=str(file_path),
                integrity_score=compute_muwazana_score(findings),
                findings=findings,
            )
            report.scan_incomplete = True
            return report

        # v1.1.2 — run the format-gauntlet detectors after the walker.
        # Each detector reads its own bytes from the same path; this
        # mirrors the DOCX / XLSX / HTML wiring pattern. Detector
        # failures are absorbed silently here (the surface they target
        # is the same bytes the walker just successfully decoded, so a
        # failure is extremely unlikely; if one occurs, the walker's
        # findings remain authoritative).
        for detector in (
            detect_eml_from_replyto_mismatch,
            detect_eml_returnpath_from_mismatch,
            detect_eml_received_chain_anomaly,
            detect_eml_base64_text_part,
            detect_eml_header_continuation_payload,
            detect_eml_xheader_payload,
        ):
            try:
                findings.extend(detector(file_path))
            except Exception:  # noqa: BLE001 — defensive
                continue

        # Phase 21 — if a ceiling tripped anywhere in the walk it left
        # a ``scan_limited`` finding. Promote that into the report's
        # ``scan_incomplete`` flag so the 0.5 clamp applies: "absence
        # of findings past the ceiling is not evidence of cleanness".
        scan_incomplete = any(
            f.mechanism == "scan_limited" for f in findings
        )
        score = compute_muwazana_score(findings)
        score = apply_scan_incomplete_clamp(
            score, scan_incomplete=scan_incomplete,
        )
        return IntegrityReport(
            file_path=str(file_path),
            integrity_score=score,
            findings=findings,
            scan_incomplete=scan_incomplete,
        )

    # ------------------------------------------------------------------
    # Header inspection
    # ------------------------------------------------------------------

    def _inspect_headers(
        self,
        msg: email.message.Message,
        file_path: Path,
        findings: list[Finding],
    ) -> None:
        """Display-name spoofing + duplicate single-instance headers +
        encoded-subject anomalies."""
        # --- Display-name spoof on From / Sender / Reply-To ---
        for header_name in ("From", "Sender", "Reply-To"):
            raw = msg.get(header_name)
            if not raw:
                continue
            decoded = _decode_header_value(raw)
            display_name, address = _extract_email_address(decoded)
            if not display_name or not address:
                continue
            if self._display_name_implies_domain(display_name, address):
                findings.append(Finding(
                    mechanism="eml_display_name_spoof",
                    tier=TIER["eml_display_name_spoof"],
                    confidence=0.9,
                    description=(
                        f"{header_name} header's display name "
                        f"{display_name!r} implies a trusted domain, "
                        f"but the actual address sits in "
                        f"{_domain_of(address)!r}. Most mail clients "
                        "render the display name prominently and the "
                        "real address secondarily — the reader sees the "
                        "performed identity, not the actual one."
                    ),
                    location=f"{file_path}:header:{header_name}",
                    surface=f"displayed as {display_name!r}",
                    concealed=f"actual address {address!r}",
                    source_layer="zahir",
                ))

        # --- Encoded-subject anomalies (and any encoded-word header
        # carrying a zahir-concealment codepoint) ---
        #
        # Under ``policy.default`` the ``msg.get(...)`` accessor returns
        # the fully-decoded header value — the ``=?...?=`` marker is
        # already consumed by the parser. To detect the encoded-word
        # carrier we must consult ``raw_items()``, which yields the
        # raw source form of each header. Not every Message
        # implementation provides ``raw_items``; fall through to the
        # parsed headers when it is missing.
        try:
            raw_header_items = list(msg.raw_items())
        except AttributeError:  # pragma: no cover — compat-32 / older API
            raw_header_items = list(msg.items())
        _target_header_names = {"subject", "from", "to", "cc", "reply-to"}
        for header_name, raw_value in raw_header_items:
            if header_name.lower() not in _target_header_names:
                continue
            raw_str = str(raw_value) if raw_value is not None else ""
            if "=?" not in raw_str:
                continue
            decoded = _decode_header_value(raw_str)
            concealment = self._classify_concealment_in_text(decoded)
            if not concealment:
                continue
            codepoints = ", ".join(sorted(concealment))
            findings.append(Finding(
                mechanism="eml_encoded_subject_anomaly",
                tier=TIER["eml_encoded_subject_anomaly"],
                confidence=0.95,
                description=(
                    f"{header_name} header uses RFC 2047 encoded-words "
                    f"whose decoded content carries concealment-class "
                    f"codepoints ({codepoints}). Encoded-words render "
                    "as their decoded text in every mail client; the "
                    "reader perceives the decoded glyphs as ordinary "
                    "header text while the underlying stream carries "
                    "the adversarial Unicode."
                ),
                location=f"{file_path}:header:{header_name}",
                surface=f"decoded display {decoded[:80]!r}",
                concealed=f"concealment classes: {codepoints}",
                source_layer="zahir",
            ))

        # --- Duplicate single-instance headers ---
        # ``Message.items`` returns every header-occurrence, so we count
        # manually. Some mail loops legitimately add their own
        # ``Received:`` — that header is multi-occurrence and not in the
        # single-instance set, so it does not fire.
        counts: dict[str, int] = {}
        for key, _value in msg.items():
            k = key.lower()
            counts[k] = counts.get(k, 0) + 1
        for k, n in counts.items():
            if k in _SINGLE_INSTANCE_HEADERS and n >= 2:
                findings.append(Finding(
                    mechanism="eml_smuggled_header",
                    tier=TIER["eml_smuggled_header"],
                    confidence=0.9,
                    description=(
                        f"Header {k!r} appears {n} times. RFC 5322 §3.6 "
                        "declares this header single-occurrence; "
                        "different mail handlers disagree on which "
                        "duplicate wins. Exact 2:14 shape at the routing "
                        "layer — one envelope ships one routing story "
                        "to one reader and another to a different "
                        "reader."
                    ),
                    location=f"{file_path}:header:{k}",
                    surface=f"{k}: (first occurrence)",
                    concealed=f"{n - 1} additional occurrence(s)",
                    source_layer="batin",
                ))

        # CRLF-injection inside a header value — look for raw ``\r\n``
        # tokens in the unfolded string form. Python's email parser
        # folds/unfolds transparently, so we inspect the *raw* bytes
        # prefix of the message for header-name-colon lines and check
        # for any value spanning a CRLF with a character that is not
        # whitespace (RFC 5322 folds must begin with WSP).
        # We keep this pattern simple: any ``header-name: value\r\n
        # X-Injected: …`` sequence where the second line's name belongs
        # to our single-instance set *and* the first line has no sane
        # terminator is a smuggling shape. In practice the duplicate
        # counter above catches these too, but header-injection can
        # smuggle a header that *was not otherwise present* — worth the
        # second detector.
        # (Minimal implementation for Phase 19: if any header value
        # contains embedded ``\r\n``, which python's parser does
        # surface in a raw value under the ``default`` policy, it is
        # flagged.)
        for key, value in msg.items():
            if value and ("\r" in value or "\n" in value):
                findings.append(Finding(
                    mechanism="eml_smuggled_header",
                    tier=TIER["eml_smuggled_header"],
                    confidence=0.95,
                    description=(
                        f"Header {key!r} carries an embedded CRLF / LF "
                        "sequence in its value. Legitimate folded header "
                        "values use CRLF followed by WSP; a bare CRLF "
                        "followed by a non-WSP byte injects a new "
                        "header into the message stream."
                    ),
                    location=f"{file_path}:header:{key.lower()}",
                    surface=f"{key}: (first line appears normal)",
                    concealed=(
                        "CRLF-injected continuation forges a header"
                    ),
                    source_layer="batin",
                ))

    def _display_name_implies_domain(
        self, display_name: str, address: str,
    ) -> bool:
        """Heuristic — does the display name PERFORM a domain that does
        not match the actual address's domain?

        Triggers on the two most common shapes:

          * The display name literally contains a recognised brand /
            keyword (``bank``, ``paypal``, ``google``, etc.) while the
            address sits in an unrelated domain.
          * The display name looks like an email address (contains ``@``)
            and that address's domain differs from the envelope address.

        The brand-keyword list is small and illustrative rather than
        exhaustive — the test is a structural signal, not a legal
        determination, and the tier (2) reflects that.
        """
        actual_domain = _domain_of(address)
        if not actual_domain:
            return False
        lower_name = display_name.lower()

        # Shape 1 — display name contains an email address itself.
        embedded_match = re.search(
            r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})",
            display_name,
        )
        if embedded_match:
            embedded_domain = _domain_of(embedded_match.group(1))
            if embedded_domain and embedded_domain != actual_domain:
                return True

        # Shape 2 — brand keyword in display name, actual domain is
        # not derived from ANY brand keyword that appears in the display
        # name. The keyword list targets names that phishing campaigns
        # impersonate most often; a display name like ``"Bank Support"``
        # with an address in ``attacker.example.com`` is the canonical
        # shape.
        #
        # Crucially: a display like ``"Google Security"`` from
        # ``noreply@google.com`` must NOT fire. The display contains
        # two brand keywords (``google`` and ``security``); the domain
        # derives from one of them (``google``); that is enough to
        # vindicate the pairing. The test is OR across all matched
        # keywords — the spoof only fires when no display-name
        # keyword is echoed by the actual domain.
        _brand_keywords = (
            "bank", "paypal", "google", "apple", "microsoft",
            "amazon", "facebook", "instagram", "linkedin", "netflix",
            "support", "security", "admin", "administrator", "postmaster",
            "it-team", "helpdesk", "accounts", "billing", "payroll",
            "hr ", "ceo ",
        )
        matched = [
            kw.strip() for kw in _brand_keywords
            if kw in lower_name and kw.strip()
        ]
        if not matched:
            return False
        for kw_stripped in matched:
            if kw_stripped in actual_domain:
                return False
        return True

    # ------------------------------------------------------------------
    # Part walking
    # ------------------------------------------------------------------

    def _walk_parts(
        self,
        msg: email.message.Message,
        file_path: Path,
        findings: list[Finding],
        depth: int,
    ) -> None:
        """Walk the multipart tree, collecting per-part findings.

        ``depth`` tracks recursion into message/rfc822 attachments so
        deeply nested emails are surfaced with a sensible location
        label. The walk is iterative over ``msg.walk()`` — the
        email library's flat iteration — and we re-enter recursively
        only for nested rfc822 messages.
        """
        boundaries: list[str] = []
        attachment_count = 0
        seen_multipart_alternative = False
        # Phase 21 — per-scan attachment ceiling. ``0`` disables.
        max_attachments = get_current_limits().max_eml_attachments
        attachment_ceiling_hit = False

        for part in msg.walk():
            # Track multipart boundaries as we encounter them.
            boundary = part.get_boundary()
            if boundary is not None:
                boundaries.append(boundary)

            content_type = (part.get_content_type() or "").lower()

            # --- multipart/alternative divergence ---
            if (
                content_type == "multipart/alternative"
                and not seen_multipart_alternative
            ):
                seen_multipart_alternative = True
                self._check_alternative_divergence(
                    part, file_path, findings,
                )

            # --- text/html body: hidden content + external refs ---
            if content_type == "text/html":
                self._check_html_body(part, file_path, findings)

            # --- attachment handling (skip the root-level container
            #     and any multipart part; only leaf non-body parts are
            #     candidates) ---
            #
            # ``message/rfc822`` is classified as multipart by
            # ``email.message.Message`` (it wraps a nested message tree)
            # but functionally IS the attachment we want to surface —
            # so we exempt it from the multipart skip.
            if part.is_multipart() and content_type != "message/rfc822":
                continue
            disposition = (part.get_content_disposition() or "").lower()
            filename = part.get_filename()
            is_attachment = (
                disposition == "attachment"
                or (disposition == "" and filename is not None)
                or content_type == "message/rfc822"
            )
            # Exclude the body parts of the top-level message — those
            # are already handled above as text/html or are plain body
            # (not an attachment per se).
            is_body_part = content_type in {
                "text/plain", "text/html",
            } and disposition != "attachment"
            if is_body_part:
                continue

            if not is_attachment:
                continue

            attachment_count += 1
            # Phase 21 — attachment-count ceiling. Legitimate mail
            # clients refuse well under a dozen attachments; a message
            # with thousands is a pathological shape we refuse to spend
            # cycles inspecting each. The attachment is still COUNTED
            # (eml_attachment_present below reports the full count so
            # the reader sees the magnitude) but the per-attachment
            # classification / recursion is skipped past the ceiling.
            if max_attachments and attachment_count > max_attachments:
                if not attachment_ceiling_hit:
                    attachment_ceiling_hit = True
                    findings.append(Finding(
                        mechanism="scan_limited",
                        tier=3,
                        confidence=1.0,
                        description=(
                            f"Message carries more than "
                            f"{max_attachments} attachment(s); per-"
                            "attachment classification and recursive "
                            "scan were skipped past that ceiling. The "
                            "total count is still surfaced below."
                        ),
                        location=f"{file_path}:attachments",
                        surface=(
                            f"(first {max_attachments} attachments "
                            "inspected)"
                        ),
                        concealed=(
                            f"exceeds max_eml_attachments="
                            f"{max_attachments}; trailing attachments "
                            "not inspected"
                        ),
                        source_layer="batin",
                    ))
                continue
            self._handle_attachment(
                part,
                file_path,
                findings,
                depth=depth,
            )

        # --- eml_attachment_present (one finding, summarising count) ---
        if attachment_count > 0:
            findings.append(Finding(
                mechanism="eml_attachment_present",
                tier=TIER["eml_attachment_present"],
                confidence=1.0,
                description=(
                    f"Message carries {attachment_count} attachment(s). "
                    "Attachments are routine but every one is an input "
                    "the recipient may be expected to open; the "
                    "dedicated mechanisms above classify their shape."
                ),
                location=f"{file_path}:attachments",
                surface="(attachment list visible in most mail clients)",
                concealed=f"{attachment_count} attachment payload(s)",
                source_layer="batin",
            ))

        # --- boundary anomalies ---
        self._check_boundary_anomalies(boundaries, file_path, findings)

    # ------------------------------------------------------------------
    # Multipart/alternative divergence
    # ------------------------------------------------------------------

    def _check_alternative_divergence(
        self,
        part: email.message.Message,
        file_path: Path,
        findings: list[Finding],
    ) -> None:
        plain_text = ""
        html_text = ""
        for sub in part.iter_parts():
            ct = (sub.get_content_type() or "").lower()
            if ct == "text/plain" and not plain_text:
                plain_text = self._decode_body(sub)
            elif ct == "text/html" and not html_text:
                html_text = self._decode_body(sub)
        if not plain_text or not html_text:
            return
        html_as_text = _strip_html_tags(html_text)
        plain_tokens = _word_tokens(plain_text)
        html_tokens = _word_tokens(html_as_text)
        if (
            len(plain_tokens) < _ALTERNATIVE_MIN_WORDS
            and len(html_tokens) < _ALTERNATIVE_MIN_WORDS
        ):
            return
        similarity = _jaccard(plain_tokens, html_tokens)
        if similarity >= _ALTERNATIVE_DIVERGENCE_THRESHOLD:
            return
        # Surface the divergence. Include a compact summary of the
        # word-sets' asymmetry so the reader can see what each audience
        # gets.
        plain_only = plain_tokens - html_tokens
        html_only = html_tokens - plain_tokens
        findings.append(Finding(
            mechanism="eml_multipart_alternative_divergence",
            tier=TIER["eml_multipart_alternative_divergence"],
            confidence=0.9,
            description=(
                f"multipart/alternative text/plain and text/html parts "
                f"diverge (jaccard similarity {similarity:.2f}, below "
                f"{_ALTERNATIVE_DIVERGENCE_THRESHOLD}). HTML-renderer "
                "readers and text-only readers see materially different "
                "messages. Exact 2:14 shape — one envelope, two "
                "audiences, two stories."
            ),
            location=f"{file_path}:multipart/alternative",
            surface=(
                f"HTML view unique words: {sorted(html_only)[:8]!r}…"
            ),
            concealed=(
                f"plain-text view unique words: "
                f"{sorted(plain_only)[:8]!r}…"
            ),
            source_layer="zahir",
        ))

    # ------------------------------------------------------------------
    # text/html body inspection — hidden content + external refs
    # ------------------------------------------------------------------

    def _check_html_body(
        self,
        part: email.message.Message,
        file_path: Path,
        findings: list[Finding],
    ) -> None:
        body = self._decode_body(part)
        if not body:
            return

        # --- Hidden content detection ---
        # Two shapes: inline style attribute with a hidden CSS pattern,
        # OR a ``hidden`` boolean attribute on an element.
        #
        # We scan tag-by-tag with a tolerant regex rather than a full
        # HTML parser so a single malformed tag does not abort the whole
        # body check. The HtmlAnalyzer's proper DOM walk is applied on
        # .html attachments via the recursive registry dispatch; the
        # email body variant here catches the top-2 idioms.
        for tag_match in re.finditer(
            r"<([a-zA-Z][\w:-]*)([^>]*)>", body,
        ):
            tag_name = tag_match.group(1).lower()
            attrs = tag_match.group(2)
            # Hidden style.
            style_m = re.search(
                r"""style\s*=\s*(['"])(.*?)\1""",
                attrs,
                re.IGNORECASE | re.DOTALL,
            )
            if style_m and _has_hidden_style(style_m.group(2)):
                # Fire only if the element plausibly contains text —
                # look for the closing tag and inspect the span.
                close_pat = re.compile(
                    rf"</\s*{re.escape(tag_name)}\s*>",
                    re.IGNORECASE,
                )
                close_m = close_pat.search(body, tag_match.end())
                if close_m:
                    inner = body[tag_match.end():close_m.start()]
                    inner_text = _strip_html_tags(inner).strip()
                    if inner_text:
                        findings.append(Finding(
                            mechanism="eml_hidden_html_content",
                            tier=TIER["eml_hidden_html_content"],
                            confidence=1.0,
                            description=(
                                f"<{tag_name}> in the HTML body carries a "
                                "render-suppressing style "
                                f"({style_m.group(2)[:80]!r}) yet "
                                "contains text content. The rendered "
                                "message omits this text while the raw "
                                "HTML and any text indexer that strips "
                                "CSS see it."
                            ),
                            location=f"{file_path}:body:<{tag_name}>",
                            surface="(rendered view omits this text)",
                            concealed=f"hidden text {inner_text[:80]!r}",
                            source_layer="zahir",
                        ))
                        break  # one finding per body is enough — avoid spam
            # Hidden attribute.
            if re.search(
                r"""(?<![\w-])hidden(?=\s|=|>|$)""",
                attrs,
                re.IGNORECASE,
            ):
                close_pat = re.compile(
                    rf"</\s*{re.escape(tag_name)}\s*>",
                    re.IGNORECASE,
                )
                close_m = close_pat.search(body, tag_match.end())
                if close_m:
                    inner = body[tag_match.end():close_m.start()]
                    inner_text = _strip_html_tags(inner).strip()
                    if inner_text:
                        findings.append(Finding(
                            mechanism="eml_hidden_html_content",
                            tier=TIER["eml_hidden_html_content"],
                            confidence=1.0,
                            description=(
                                f"<{tag_name} hidden> in the HTML body "
                                "contains text content. The HTML5 "
                                "``hidden`` attribute suppresses the "
                                "element from the rendered view while "
                                "leaving its text in the DOM."
                            ),
                            location=f"{file_path}:body:<{tag_name} hidden>",
                            surface="(rendered view omits this text)",
                            concealed=f"hidden text {inner_text[:80]!r}",
                            source_layer="zahir",
                        ))
                        break

        # --- External reference detection ---
        # Find all loaded-resource attributes pointing at absolute URLs.
        # One finding per unique external target to avoid spam.
        seen_refs: set[str] = set()
        for tag_match in re.finditer(
            r"<([a-zA-Z][\w:-]*)([^>]*)>", body,
        ):
            tag_name = tag_match.group(1).lower()
            if tag_name not in _EMAIL_EXTERNAL_REF_ATTRS:
                continue
            attrs = tag_match.group(2)
            for attr in _EMAIL_EXTERNAL_REF_ATTRS[tag_name]:
                attr_m = re.search(
                    rf"""{attr}\s*=\s*(['"])(.*?)\1""",
                    attrs,
                    re.IGNORECASE | re.DOTALL,
                )
                if not attr_m:
                    continue
                url = attr_m.group(2).strip()
                if not _is_external_url(url):
                    continue
                if url in seen_refs:
                    continue
                seen_refs.add(url)
                findings.append(Finding(
                    mechanism="eml_external_reference",
                    tier=TIER["eml_external_reference"],
                    confidence=0.9,
                    description=(
                        f"<{tag_name} {attr}=…> in the HTML body points "
                        f"at the absolute remote URL {url[:120]!r}. "
                        "The mail client reaches outside the message "
                        "when the body opens; common vectors are "
                        "tracking pixels, remote images, and remote CSS."
                    ),
                    location=f"{file_path}:body:<{tag_name}>:{attr}",
                    surface=f"<{tag_name}> (no inline indicator)",
                    concealed=f"external target {url[:120]!r}",
                    source_layer="batin",
                ))

    # ------------------------------------------------------------------
    # Attachment handling — classification + recursive scan
    # ------------------------------------------------------------------

    def _handle_attachment(
        self,
        part: email.message.Message,
        file_path: Path,
        findings: list[Finding],
        depth: int,
    ) -> None:
        filename = part.get_filename() or ""
        content_type = (part.get_content_type() or "").lower()
        ext = ""
        if filename:
            _stem, dot, ext = filename.rpartition(".")
            ext = ext.lower() if dot else ""

        # --- Classification: executable / macro / nested rfc822 ---
        if ext in _EXECUTABLE_EXTENSIONS or content_type in _EXECUTABLE_MIME_TYPES:
            findings.append(Finding(
                mechanism="eml_executable_attachment",
                tier=TIER["eml_executable_attachment"],
                confidence=1.0,
                description=(
                    f"Attachment {filename!r} ({content_type}) is an "
                    "executable file class. Opening it runs code in "
                    "the recipient's environment; this is the highest-"
                    "priority email-phishing shape."
                ),
                location=f"{file_path}:attachment:{filename or '(unnamed)'}",
                surface=f"attached as {filename!r}",
                concealed=(
                    f"executable class .{ext or content_type}"
                ),
                source_layer="batin",
            ))

        if ext in _MACRO_EXTENSIONS:
            findings.append(Finding(
                mechanism="eml_macro_attachment",
                tier=TIER["eml_macro_attachment"],
                confidence=1.0,
                description=(
                    f"Attachment {filename!r} ({content_type}) is a "
                    "macro-enabled Office format. Enabling content "
                    "executes embedded VBA; the inner analyzer will "
                    "additionally surface the macro payload itself."
                ),
                location=f"{file_path}:attachment:{filename or '(unnamed)'}",
                surface=f"attached as {filename!r}",
                concealed=f"macro-enabled Office file (.{ext})",
                source_layer="batin",
            ))

        if content_type == "message/rfc822" or ext == "eml":
            findings.append(Finding(
                mechanism="eml_nested_eml",
                tier=TIER["eml_nested_eml"],
                confidence=1.0,
                description=(
                    f"Attachment {filename or '(unnamed)'} is a nested "
                    "email (message/rfc822). EmlAnalyzer recurses into "
                    "nested messages; inner findings are folded into "
                    "this report with the attachment name prefixed "
                    "into their location."
                ),
                location=f"{file_path}:attachment:{filename or '(nested)'}",
                surface="(forwarded-as-attachment envelope)",
                concealed="recursive email nesting",
                source_layer="batin",
            ))

        # --- Recursive scan via the default analyzer registry ---
        # Guarded: only for non-executable attachments (running the PDF /
        # Office / image analyzers on a .exe is noise), bounded in
        # recursion depth, and bounded in payload size.
        #
        # Phase 21 — the recursion-depth ceiling is now sourced from
        # ``get_current_limits().max_recursion_depth`` (default 5, up
        # from the prior hard-coded 3). A value of 0 disables the
        # recursion entirely (attachments are still surfaced as
        # findings via the classification block above; only the inner
        # registry re-scan is suppressed). When the ceiling is hit,
        # emit a ``scan_limited`` finding so the reader sees
        # explicitly that the inner scan was skipped.
        max_depth = get_current_limits().max_recursion_depth
        if max_depth and depth >= max_depth:
            findings.append(Finding(
                mechanism="scan_limited",
                tier=3,
                confidence=1.0,
                description=(
                    f"Attachment {filename or '(unnamed)'} at recursion "
                    f"depth {depth} reached the configured "
                    f"max_recursion_depth={max_depth}; inner registry "
                    "re-scan was skipped. Findings for deeper nested "
                    "payloads (if any) are absent from this report."
                ),
                location=f"{file_path}:attachment:{filename or '(unnamed)'}",
                surface=f"(recursion depth {depth})",
                concealed=(
                    f"exceeds max_recursion_depth={max_depth}; nested "
                    "payload not inspected"
                ),
                source_layer="batin",
            ))
            return
        if ext in _EXECUTABLE_EXTENSIONS:
            return
        try:
            payload = part.get_payload(decode=True)
        except Exception:  # noqa: BLE001 — defensive on malformed CTE
            return
        if not payload or not isinstance(payload, bytes):
            return
        if len(payload) > _MAX_ATTACHMENT_BYTES:
            return

        self._recurse_into_attachment(
            payload=payload,
            filename=filename,
            content_type=content_type,
            parent_path=file_path,
            findings=findings,
            depth=depth,
        )

    def _recurse_into_attachment(
        self,
        payload: bytes,
        filename: str,
        content_type: str,
        parent_path: Path,
        findings: list[Finding],
        depth: int,
    ) -> None:
        """Write the attachment to a temp file, classify it, scan it.

        Lazy-imports ``application.default_registry`` / ``FileRouter`` to
        avoid a circular dependency (application imports analyzers; if
        analyzers imported application at module load the chain would
        loop). The lazy import runs once per attachment scan.
        """
        # Preserve the attachment's original extension in the temp file
        # name — FileRouter dispatch leans on extensions as a secondary
        # signal. If no extension is present, let the router classify
        # from bytes alone.
        suffix = ""
        if "." in filename:
            suffix = "." + filename.rsplit(".", 1)[-1]

        tmp_path: Path | None = None
        try:
            fd, tmp_name = tempfile.mkstemp(
                prefix="bayyinah_eml_", suffix=suffix,
            )
            tmp_path = Path(tmp_name)
            with os.fdopen(fd, "wb") as fh:
                fh.write(payload)
        except OSError:
            if tmp_path is not None:
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            return

        try:
            # Handle nested .eml recursively via this analyzer directly.
            # Running the full default_registry on a nested .eml is also
            # valid — default_registry does not currently include the
            # EmlAnalyzer (it will after Phase 19.7 wires it in). For
            # Phase 19 we handle nested email explicitly here so the
            # recursion is well-defined regardless of registry state.
            if content_type == "message/rfc822" or suffix == ".eml":
                try:
                    nested_msg = email.message_from_bytes(
                        payload, policy=email.policy.default,
                    )
                    nested_findings: list[Finding] = []
                    self._inspect_headers(
                        nested_msg, tmp_path, nested_findings,
                    )
                    self._walk_parts(
                        nested_msg, tmp_path, nested_findings,
                        depth=depth + 1,
                    )
                    for f in nested_findings:
                        findings.append(self._relocate_finding(
                            f,
                            parent_path=parent_path,
                            attachment_name=filename or "(nested)",
                        ))
                except Exception:  # noqa: BLE001
                    pass
                return

            # Non-email attachment — dispatch through the default
            # registry. Lazy import to avoid a circular dependency
            # (application depends on analyzers).
            try:
                from application import default_registry  # noqa: WPS433
            except Exception:  # noqa: BLE001 — analyzer usable without app
                return
            router = FileRouter()
            try:
                detection = router.detect(tmp_path)
            except OSError:
                return
            if detection.kind is FileKind.UNKNOWN:
                return
            # Exclude our own kind to avoid routing back into this
            # analyzer through the registry (the registry scan_all with
            # kind=EML would invoke EmlAnalyzer.scan on the temp file,
            # which is already handled by the explicit nested branch
            # above).
            if detection.kind is FileKind.EML:
                return
            try:
                registry = default_registry()
                nested_report = registry.scan_all(
                    tmp_path, kind=detection.kind,
                )
            except Exception:  # noqa: BLE001 — never let a nested crash kill the outer scan
                return
            for f in nested_report.findings:
                findings.append(self._relocate_finding(
                    f,
                    parent_path=parent_path,
                    attachment_name=filename or "(unnamed)",
                ))
        finally:
            if tmp_path is not None:
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    def _relocate_finding(
        self,
        finding: Finding,
        parent_path: Path,
        attachment_name: str,
    ) -> Finding:
        """Rewrite a nested finding's location to include the attachment
        name and the parent email path.

        The mechanism name and severity are preserved — the outer scoring
        rolls up every nested mechanism at its native weight. The
        location prefix tells the reader which attachment the finding
        came from.
        """
        return Finding(
            mechanism=finding.mechanism,
            tier=finding.tier,
            confidence=finding.confidence,
            description=(
                f"[in attachment {attachment_name!r}] "
                f"{finding.description}"
            ),
            location=(
                f"{parent_path}:attachment:{attachment_name}:"
                f"{finding.location}"
            ),
            surface=finding.surface,
            concealed=finding.concealed,
            source_layer=finding.source_layer,
        )

    # ------------------------------------------------------------------
    # Boundary anomaly detection
    # ------------------------------------------------------------------

    def _check_boundary_anomalies(
        self,
        boundaries: list[str],
        file_path: Path,
        findings: list[Finding],
    ) -> None:
        """Flag suspiciously short boundaries + reused boundaries.

        Legitimate boundaries are random strings of 30+ chars. A
        boundary below ``_MIN_SAFE_BOUNDARY_LEN`` is either an
        impoverished generator or a smuggling shape (short boundaries
        collide with body content far more easily, which is a carrier
        for parser-disagreement attacks).
        """
        if not boundaries:
            return
        flagged: set[str] = set()
        for b in boundaries:
            if len(b) < _MIN_SAFE_BOUNDARY_LEN and b not in flagged:
                flagged.add(b)
                findings.append(Finding(
                    mechanism="eml_mime_boundary_anomaly",
                    tier=TIER["eml_mime_boundary_anomaly"],
                    confidence=0.85,
                    description=(
                        f"Multipart boundary {b!r} is "
                        f"{len(b)} characters — below the "
                        f"{_MIN_SAFE_BOUNDARY_LEN}-character threshold "
                        "legitimate MUAs produce. Short boundaries "
                        "collide with body content and are a carrier "
                        "for parser-disagreement attacks."
                    ),
                    location=f"{file_path}:boundary",
                    surface="(no visible indication)",
                    concealed=f"boundary {b!r}",
                    source_layer="batin",
                ))
        # Duplicate boundaries across nested multiparts — the same
        # boundary string used at two depths is legal-but-unusual and
        # can confuse lenient parsers.
        seen = set()
        dupes: set[str] = set()
        for b in boundaries:
            if b in seen:
                dupes.add(b)
            seen.add(b)
        for b in dupes:
            if b in flagged:
                continue
            flagged.add(b)
            findings.append(Finding(
                mechanism="eml_mime_boundary_anomaly",
                tier=TIER["eml_mime_boundary_anomaly"],
                confidence=0.8,
                description=(
                    f"Multipart boundary {b!r} is reused across "
                    "multiple nested multipart parts. Most MUAs "
                    "generate unique random boundaries per part; a "
                    "reused boundary is either a generator bug or "
                    "a parser-disagreement shape."
                ),
                location=f"{file_path}:boundary:reused",
                surface="(no visible indication)",
                concealed=f"reused boundary {b!r}",
                source_layer="batin",
            ))

    # ------------------------------------------------------------------
    # Body decoding helper
    # ------------------------------------------------------------------

    def _decode_body(self, part: email.message.Message) -> str:
        """Return the decoded body of a ``text/*`` part as a str.

        Uses ``get_content()`` when available (modern policy) and falls
        back to ``get_payload(decode=True)`` for older envelopes. Binary
        content or decode failures return an empty string — the caller
        should treat "no body" as "no content to analyse", not as an
        error state.
        """
        try:
            content = part.get_content()
            if isinstance(content, str):
                return content
            if isinstance(content, bytes):
                return content.decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001 — fallback to get_payload
            pass
        try:
            raw = part.get_payload(decode=True)
            if isinstance(raw, bytes):
                return raw.decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
        return ""

    # ------------------------------------------------------------------
    # Unicode concealment classification — shared with header inspector
    # ------------------------------------------------------------------

    def _classify_concealment_in_text(self, text: str) -> set[str]:
        """Return the set of concealment-class tags present in ``text``.

        Classes:
          * ``zero_width`` — any ZERO_WIDTH_CHARS codepoint present.
          * ``tag``        — any TAG block codepoint present.
          * ``bidi``       — any BIDI_CONTROL_CHARS codepoint present.
          * ``math_alphanum`` — any MATH_ALPHANUMERIC_RANGE codepoint
                                 present.
          * ``homoglyph``  — mixed-script word (Latin + confusable)
                             present.
        """
        classes: set[str] = set()
        for ch in text:
            if ch in ZERO_WIDTH_CHARS:
                classes.add("zero_width")
            elif ch in BIDI_CONTROL_CHARS:
                classes.add("bidi")
            elif ord(ch) in TAG_CHAR_RANGE:
                classes.add("tag")
            elif ord(ch) in MATH_ALPHANUMERIC_RANGE:
                classes.add("math_alphanum")
        for word in text.split():
            if len(word) < 2:
                continue
            confusables = [c for c in word if c in CONFUSABLE_TO_LATIN]
            latin = [c for c in word if _is_latin_letter(c)]
            if confusables and (latin or len(confusables) >= 2):
                classes.add("homoglyph")
                break
        return classes


__all__ = ["EmlAnalyzer"]
