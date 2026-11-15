"""
Second-stage assessment of recovered concealed text.

The scanner's detectors answer "is something hidden in this file?". They do
not say what the hidden thing is, and most hidden text in real documents is
harmless: OCR layers behind scanned pages, watermarks, pagination notes,
accessibility text. This module reads the text a detector recovered and
answers one further, narrower question:

    Does this hidden text read as an instruction addressed to an AI system?

It is a deterministic phrase-pattern scorer, not a model. It looks only for
positive evidence in six families (override of prior instructions, disclosure
of secrets or system text, steering of the output, tool or agent direction,
authority or exemption framing, and direct address of the model). Absence of
evidence returns ``False``; nothing is ever classified as "benign" on the
strength of what it says about itself.

Tier discipline. The result is interpretive (Tier 3). It does not replace or
downgrade the concealment finding it annotates, and a ``False`` does not make
hidden text safe: an instruction phrased in a way these patterns do not
anticipate, written in another language, or split so the walker cannot
reassemble it will be missed. Treat ``True`` as "a reader should look at this
first", not as a verdict of intent.

Shortcut hygiene. Bracketed key=value tags and angle-bracket wrapper tags are
stripped before scoring, so labels a generator or attacker puts around a
message ("<SYSTEM>", "[TYPE=...]") cannot by themselves decide the result.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Score at or above which text is reported as instruction-like.
THRESHOLD = 3

_TAG = re.compile(r"<[^<>]{0,80}>|\[[A-Za-z0-9_ ]{1,40}=[^\[\]]{0,80}\]")
_WS = re.compile(r"\s+")


def sanitize(text: str) -> str:
    """Remove wrapper tags and collapse whitespace."""
    return _WS.sub(" ", _TAG.sub(" ", text or "")).strip()


def _p(*alts: str) -> re.Pattern[str]:
    """Compile alternatives; a space in a pattern matches zero or more
    whitespace characters so glyph-split text with lost spaces still matches."""
    return re.compile("|".join("(?:" + a.replace(" ", r"\s*") + ")" for a in alts), re.I)


_OBJ = r"(?:instruction|directive|prompt|rule|guideline|guidance|hierarchy|polic(?:y|ies)|constraint|context)s?"
_SECRET = (r"(?:(?:system|startup|initial|hidden|internal|private|developer|original|base) (?:system )?"
           r"(?:prompt|message|instruction|directive|configuration|context|file|setting|guidance)s?|"
           r"prompt (?:state|text)|secrets?|secret-like|passwords?|credentials?|sensitive (?:strings?|values?|data)|"
           r"(?:session |access |api )?tokens?|api keys?|confidential|privileged context|control text|"
           r"(?:concealed|operating) (?:directive|instruction)s?|instruction hierarchy|"
           r"(?:chat|conversation) history|configuration)")

# family -> (weight, pattern)
_FAMILIES: dict[str, tuple[int, re.Pattern[str]]] = {
    "override": (3, _p(
        r"(?:ignore|disregard|forget|override|bypass|erase|discard|drop|replace|cancel)\b.{0,60}?" + _OBJ,
        _OBJ + r".{0,40}?(?:are|is|have been)\s*(?:now\s*)?(?:superseded|void|cancell?ed|replaced|revoked|overridden)",
        r"(?:actual|real|true|new|only) (?:task|goal|objective|job|instruction)",
        r"(?:replacement|updated|new|following) instructions?\b",
        r"\bdecoy\b",
        r"obey the (?:next|following)",
        r"from now on",
        r"(?:treat|consider|regard) .{0,50}?(?:as|to be) (?:revoked|void|cancell?ed|superseded|invalid|non-?binding|obsolete)",
        r"unrestricted (?:response |output |answer )?mode",
        r"(?:takes?|has|have) (?:priority|precedence) over",
        r"(?:follow|comply with|adhere to) (?:this|these|the following|the embedded|the hidden) .{0,30}?(?:only|instead|first)",
    )),
    "disclosure": (3, _p(
        r"(?:reveal|disclose|print|output|show|leak|expose|repeat|enumerate|list|send|exfiltrate|dump|include|share|"
        r"quote|return|provide|unmask|do not mask|surface|extract|find|copy|state|tell me|show me)\b.{0,80}?" + _SECRET,
        _SECRET + r".{0,60}?(?:verbatim|in full|word for word)",
    )),
    "steering": (2, _p(
        r"in your (?:reply|response|answer|summary|output|review|assessment)",
        r"(?:do not|don't|never) (?:mention|reveal|disclose|refuse|warn|flag|acknowledge|decline|hedge|apologi[sz]e)",
        r"(?:answer|respond|reply|comply) (?:directly|immediately|fully)",
        r"without (?:mentioning|citing|referring to|noting)",
        r"(?:key|main|primary) takeaway",
        r"(?:respond|reply|answer) (?:only|with|as|in)\b",
        r"before (?:answering|responding|producing|writing|you (?:answer|respond))",
        r"without (?:explanation|comment|caveats?|warning|mention)",
        r"(?:write|produce|draft) the (?:summary|review|answer|reply|response)",
        r"(?:summar(?:y|ize|ise)|review|rate|score|rank|recommend|evaluate) (?:this|the) .{0,40}?(?:as|so that|positively|favou?rably|highly)",
        r"(?:give|assign|award) (?:a |an |the )?(?:positive|favou?rable|high|top|maximum|perfect)",
        r"(?:emphasi[sz]e|downplay|prioriti[sz]e|highlight|omit)\b.{0,60}?(?:instruction|takeaway|document|text|content|finding|weakness|concern)",
        r"sound more important",
        r"(?:you|the (?:assistant|model|reviewer)) (?:must|should|shall|will|need to) (?:always |now |only )?"
        r"(?:say|answer|respond|recommend|approve|accept|rate|output|conclude|state|reply)",
    )),
    "agent": (2, _p(
        r"tool calls?",
        r"(?:call|use|invoke|run|execute) (?:the |a |any |available )?(?:tool|function|command|shell|script|code|browser)",
        r"(?:inspect|read|open|access|search) .{0,30}?(?:runtime state|accessible state|logs|hidden files|environment variables|file ?system|memory)",
        r"(?:send|post|upload|forward|email|transmit) .{0,60}?(?:to|at) (?:https?:|www\.|[a-z0-9.-]+@)",
        r"(?:visit|fetch|open|load|browse to) (?:https?:|www\.)",
        r"if a tool can",
    )),
    "authority": (2, _p(
        r"(?:research|compliance|safety|testing|debug|developer|admin(?:istrator)?|review|evaluation|audit|maintenance|"
        r"risk review|document review|unrestricted|god) (?:exemption|exception|mode|override|rubric|clearance|access)",
        r"safety filter(?:ing|s)?",
        r"(?:policy|safety|content) (?:boundar(?:y|ies)|restrictions?|guardrails?)",
        r"\brestrictions\b",
        r"obedient",
        r"(?:is|are) (?:hereby )?(?:authori[sz]ed|permitted|allowed|cleared) to",
        r"(?:mode|exemption|exception|policy) (?:permits|allows|instructs|requires|authori[sz]es)",
        r"you are now\b",
        r"(?:end|begin|start) of (?:document|system|user|context)",
        r"^(?:system|assistant|developer)\s*:",
        r"jailbreak|do anything now",
    )),
    "addressee": (1, _p(
        r"\b(?:the )?(?:assistant|chatbot|language model|llm|ai (?:system|agent|model|assistant|reviewer|reader))\b",
        r"\b(?:gpt|claude|gemini|copilot|chatgpt)\b",
        r"\byour (?:task|instructions?|reply|response|answer|summary|output|role|goal|review)\b",
        r"\byou are (?:a|an|the)\b",
        r"\bif you are (?:a|an) (?:ai|llm|language model|assistant|bot)\b",
    )),
}

# Other languages: override, disclosure and steering in sixteen languages.
from analyzers.instruction_phrases_i18n import I18N_FAMILIES  # noqa: E402

_FAMILIES.update(I18N_FAMILIES)


# ---------------------------------------------------------------------------
# Directive shape: a short hidden text that (a) gives an order and (b) is
# about a model's own inputs, outputs or rules. This is a grammatical test,
# not a topic list of known attacks: it asks whether the text tells someone
# to do something with prompts, instructions, answers, tools or policies.
# ---------------------------------------------------------------------------
_IMPERATIVE_VERBS = (
    "ignore|disregard|forget|override|bypass|erase|discard|replace|cancel|treat|consider|follow|obey|comply|"
    "reveal|disclose|print|output|show|leak|expose|repeat|enumerate|list|send|exfiltrate|dump|include|share|quote|"
    "return|provide|surface|extract|find|copy|state|tell|search|collect|gather|locate|read|open|inspect|access|"
    "write|draft|produce|frame|summari[sz]e|describe|present|rate|score|rank|recommend|approve|accept|reject|"
    "emphasi[sz]e|downplay|prioriti[sz]e|highlight|omit|mention|answer|respond|reply|confirm|continue|start|begin|"
    "stop|use|call|invoke|run|execute|visit|fetch|load|act|behave|pretend|assume|switch|enter|enable|disable|"
    "prefer|refuse|decline|translate|append|insert|add|remove|delete|keep|hide|conceal|give|make|ensure|always|never|"
    "pause|halt|proceed|recite|restate|rewrite|classify|label|mark|report|notify|upload|post|email|forward"
)
_DIRECTIVE = re.compile(
    r"(?:^|[.!?:;,]\s*|\b(?:please|kindly|now|then|first|and|instead|immediately)\s+)(?:" + _IMPERATIVE_VERBS + r")\b"
    r"|\b(?:do not|don't|never|you may not|you cannot|you must|you should|you shall|you will|you are to|you need to)\b"
    r"|\b(?:the )?(?:assistant|model|reviewer|reader|agent|system) (?:must|shall|should|will|is to|is required to|is instructed to)\b"
    r"|\b(?:is mandatory|are mandatory|has (?:highest|top) priority|have (?:highest|top) priority)\b",
    re.I,
)
_DIRECTIVE_SQUASHED = re.compile(
    r"(?:^|[.!?:;])(?:" + _IMPERATIVE_VERBS + r")"
    r"|donot|don't|youmaynot|youcannot|youmust|youshould|youshall|youwill|youareto|youneedto"
    r"|ismandatory|aremandatory|isrequiredto|arerequiredto",
    re.I,
)
_DOMAIN = (
    r"prompts?|instructions?|directives?|rules?|guidelines?|constraints?|polic(?:y|ies)|safety|restrictions?|"
    r"context|conversation|session|summary|summar(?:ize|ise)|answer|reply|response|output|review|assessment|"
    r"assistant|model|chatbot|\bai\b|tools?|function calls?|secrets?|secret-looking|hidden|concealed|embedded|"
    r"confidential|passwords?|credentials?|tokens?|override|refus(?:e|al)|comply|compliance|content|document|task|user|"
    r"requests?|safeguards?|disclosure|behaviou?r|responses?"
)
_DOMAIN_RE = re.compile(r"\b(?:" + _DOMAIN + r")\b", re.I)
_DOMAIN_SQUASHED = re.compile("(?:" + _DOMAIN.replace(r"\b", "") + ")", re.I)


def _directive_shape(clean: str, squashed: bool) -> str | None:
    d = (_DIRECTIVE_SQUASHED if squashed else _DIRECTIVE).search(clean)
    if not d:
        return None
    n = (_DOMAIN_SQUASHED if squashed else _DOMAIN_RE).search(clean)
    if not n:
        return None
    return (_WS.sub(" ", d.group(0)).strip(" .:;") + " ... " + n.group(0))[:80]


@dataclass(frozen=True)
class Assessment:
    instruction_like: bool
    score: int
    families: tuple[str, ...]
    evidence: tuple[str, ...]
    text_chars: int


# Hidden text longer than this is treated as a text layer (for example OCR
# behind a scanned page), where a single generic phrase proves little.
SHORT_TEXT_CHARS = 600

# Variants of the patterns with word-boundary anchors removed, for text whose
# spaces were lost when a message was split one glyph per operator.
_FAMILIES_SQUASHED: dict[str, tuple[int, re.Pattern[str]]] = {
    k: (w, re.compile(p.pattern.replace(r"\b", ""), re.I)) for k, (w, p) in _FAMILIES.items()
}


def _is_squashed(clean: str) -> bool:
    return len(clean) >= 20 and clean.count(" ") / len(clean) < 0.04


def assess(text: str) -> Assessment:
    """Score recovered concealed text for instruction-likeness.

    Decision rule. Text is instruction-like when its score reaches
    ``THRESHOLD``; a short hidden snippet (at most ``SHORT_TEXT_CHARS``) also
    qualifies on a single family other than bare address of the model, because
    a short hidden line that steers output or claims authority has no ordinary
    reason to be there. A short snippet is also tested for directive shape (an
    order about prompts, answers, tools or rules). Long hidden text needs the
    full threshold from the phrase families.
    """
    clean = sanitize(text)
    table = _FAMILIES_SQUASHED if _is_squashed(clean) else _FAMILIES
    score = 0
    fams: list[str] = []
    ev: list[str] = []
    for name, (weight, pat) in table.items():
        m = pat.search(clean)
        if m:
            score += weight
            fams.append(name)
            ev.append(_WS.sub(" ", m.group(0))[:80])
    short = len(clean) <= SHORT_TEXT_CHARS
    if short:
        shape = _directive_shape(clean, table is _FAMILIES_SQUASHED)
        if shape:
            score += 2
            fams.append("directive_shape")
            ev.append(shape)
    strong = any(f != "addressee" for f in fams)
    hit = score >= THRESHOLD or (strong and short)
    return Assessment(hit, score, tuple(fams), tuple(ev), len(clean))


# ---------------------------------------------------------------------------
# Acrostic channel. A message can be spelled by the first letter of each
# sentence of an otherwise bland paragraph. When concealed text has enough
# sentences, the initials are read as a string and tested against the phrase
# families only (never the looser directive-shape test, because a string of
# initials has no word boundaries and short words match by accident).
# ---------------------------------------------------------------------------
ACROSTIC_MIN_SENTENCES = 12
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def acrostic_of(text: str) -> str:
    """Return the sentence-initial letters of ``text`` as one lowercase string,
    or an empty string when there are too few sentences to carry a message."""
    sentences = [x for x in _SENTENCE_SPLIT.split(sanitize(text)) if x and x[0].isalpha()]
    if len(sentences) < ACROSTIC_MIN_SENTENCES:
        return ""
    return "".join(x[0] for x in sentences).lower()


def assess_acrostic(text: str) -> Assessment:
    """Assess the acrostic of concealed text. Phrase families only; the full
    threshold is always required."""
    letters = acrostic_of(text)
    score = 0
    fams: list[str] = []
    ev: list[str] = []
    if letters:
        for name, (weight, pat) in _FAMILIES_SQUASHED.items():
            if name == "addressee":
                continue
            m = pat.search(letters)
            if m:
                score += weight
                fams.append("acrostic:" + name)
                ev.append(m.group(0)[:80])
    return Assessment(score >= THRESHOLD, score, tuple(fams), tuple(ev), len(letters))


def concealed_text_of(findings) -> str:
    """Concatenate the concealed text carried by a report's findings, in order.

    Accepts Finding objects or their dict form. Only the recovered text is
    used; mechanism names and locations are not.
    """
    parts: list[str] = []
    for f in findings:
        c = getattr(f, "concealed", None)
        if c is None and isinstance(f, dict):
            c = f.get("concealed") or (f.get("inversion_recovery") or {}).get("concealed")
        if not c:
            continue
        c = str(c)
        m = re.match(r"(?:Tm origin \([^)]*\); )?recovered text: (['\"])(.*)\1\.{0,3}$", c, re.S)
        parts.append(m.group(2) if m else c)
    return " ".join(parts)


def assess_findings(findings) -> Assessment:
    """Assess all concealed text recovered in one scan: the text as written,
    and, if that is not instruction-like, its sentence-initial acrostic."""
    text = concealed_text_of(findings)
    direct = assess(text)
    if direct.instruction_like:
        return direct
    hidden = assess_acrostic(text)
    return hidden if hidden.instruction_like else direct


__all__ = ["Assessment", "assess", "assess_findings", "concealed_text_of", "sanitize", "THRESHOLD", "SHORT_TEXT_CHARS",
           "acrostic_of", "assess_acrostic", "ACROSTIC_MIN_SENTENCES"]


# ---------------------------------------------------------------------------
# Report integration
# ---------------------------------------------------------------------------

LEGACY_PARITY_ENV = "BAYYINAH_LEGACY_PARITY"


def legacy_parity_mode() -> bool:
    """True when the scan must reproduce the v0 / v0.1 detector set exactly.

    The stream-level PDF pass and the ``concealed_instruction`` finding
    did not exist in v0.1, so a byte-parity comparison against it has to
    switch them off. Set ``BAYYINAH_LEGACY_PARITY=1``. The older opt-out
    ``BAYYINAH_STREAM_CONCEALMENT=0`` is honoured for the stream pass.
    """
    import os
    return os.environ.get(LEGACY_PARITY_ENV) == "1"


def instruction_finding(findings, file_path=None, *, is_pdf: bool = False):
    """A ``concealed_instruction`` Finding when the text this scan found
    hidden is written as an instruction to an AI system, else ``None``.

    Reads only what other mechanisms recovered (and, for a PDF, the full
    text of the runs the stream walk classed as unseen). It never reads
    visible text, so an article *about* prompt injection does not fire.
    """
    if legacy_parity_mode() or not findings:
        return None
    if any(getattr(f, "mechanism", None) == "concealed_instruction" for f in findings):
        return None
    result = None
    if is_pdf and file_path is not None:
        try:
            from analyzers.pdf_stream_concealment import assess_pdf
            result = assess_pdf(file_path, findings)
        except Exception:
            result = None
    if result is None:
        result = assess_findings(findings)
    if not result.instruction_like:
        return None
    from domain import Finding
    from domain.config import TIER
    families = ", ".join(result.families)
    evidence = "; ".join(repr(e) for e in result.evidence[:4])
    return Finding(
        mechanism="concealed_instruction",
        tier=TIER["concealed_instruction"],
        confidence=min(0.95, 0.5 + 0.08 * result.score),
        description=(
            "Text that a reader of this file cannot see is written as an "
            f"instruction to an AI system (signals: {families}). Matched: "
            f"{evidence}. This is a phrase-based reading of the hidden "
            "text; it does not understand paraphrase, and its silence is "
            "not evidence that hidden text is harmless."
        ),
        location=str(file_path) if file_path is not None else "",
        surface="(not visible to a reader)",
        concealed=f"instruction-like hidden text; matched {evidence}",
    )


__all__ += ["instruction_finding", "legacy_parity_mode", "LEGACY_PARITY_ENV"]
