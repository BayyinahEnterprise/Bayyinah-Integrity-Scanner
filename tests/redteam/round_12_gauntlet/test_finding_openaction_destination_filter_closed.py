"""Round 12 HIGH 1 closure: openaction destination-vs-action filter.

Per ISO 32000-1 section 12.6.3, /OpenAction values that are bare
destination arrays or /GoTo-family wrapped destinations are
navigation hints, not executable content. The v1.2.4 fix filters
them before emission. Executable subtypes (/JavaScript, /Launch,
/URI, /SubmitForm, /ImportData) still fire.
"""
from __future__ import annotations
import io
from pathlib import Path
import pypdf
from pypdf.generic import (
    ArrayObject, DictionaryObject, NameObject, NullObject,
    TextStringObject, ByteStringObject,
)
import pytest
from bayyinah import scan_pdf

CORPUS = Path(__file__).parent


def _build_minimal_seed_pdf() -> Path:
    """Build a minimal seed PDF; we modify its catalog for each test."""
    seed = CORPUS / "fixture_libreoffice_writer_native.pdf"
    return seed


def _scan_with_open_action(open_action_value) -> list[dict]:
    """Inject open_action_value into the catalog of the minimal seed
    and return the resulting finding list as dicts."""
    seed = _build_minimal_seed_pdf()
    reader = pypdf.PdfReader(seed)
    writer = pypdf.PdfWriter(clone_from=reader)
    writer._root_object[NameObject("/OpenAction")] = open_action_value
    buf = io.BytesIO()
    writer.write(buf)

    # Persist to a temp path because scan_pdf takes a Path.
    tmp = CORPUS / "_test_oa_tmp.pdf"
    tmp.write_bytes(buf.getvalue())
    try:
        rd = scan_pdf(tmp).to_dict()
        return rd.get("findings", [])
    finally:
        tmp.unlink(missing_ok=True)


def _fires_openaction(findings) -> bool:
    return any(f.get("mechanism") == "openaction" for f in findings)


def test_openaction_destination_array_does_not_fire():
    """Case 1: bare destination array such as
    [page_ref /XYZ left top zoom] is benign navigation."""
    seed = pypdf.PdfReader(_build_minimal_seed_pdf())
    first_page = seed.pages[0].indirect_reference
    dest = ArrayObject([
        first_page,
        NameObject("/XYZ"),
        NullObject(), NullObject(), NullObject(),
    ])
    findings = _scan_with_open_action(dest)
    assert not _fires_openaction(findings), (
        f"openaction fired on benign destination array; findings={findings}"
    )


def test_openaction_goto_wrapped_destination_does_not_fire():
    """Case 2: {/S: /GoTo, /D: [...]} wraps a destination."""
    seed = pypdf.PdfReader(_build_minimal_seed_pdf())
    first_page = seed.pages[0].indirect_reference
    action = DictionaryObject({
        NameObject("/S"): NameObject("/GoTo"),
        NameObject("/D"): ArrayObject([
            first_page,
            NameObject("/XYZ"),
            NullObject(), NullObject(), NullObject(),
        ]),
    })
    findings = _scan_with_open_action(action)
    assert not _fires_openaction(findings), (
        f"openaction fired on /GoTo-wrapped destination; findings={findings}"
    )


def test_openaction_gotor_does_not_fire():
    """/GoToR (remote-document GoTo) is also navigation only."""
    action = DictionaryObject({
        NameObject("/S"): NameObject("/GoToR"),
        NameObject("/F"): TextStringObject("other.pdf"),
    })
    findings = _scan_with_open_action(action)
    assert not _fires_openaction(findings)


def test_openaction_javascript_action_fires():
    """/JavaScript subtype is executable; openaction must still fire."""
    action = DictionaryObject({
        NameObject("/S"): NameObject("/JavaScript"),
        NameObject("/JS"): TextStringObject("app.alert('test');"),
    })
    findings = _scan_with_open_action(action)
    assert _fires_openaction(findings), (
        f"openaction failed to fire on /JavaScript; findings={findings}"
    )


def test_openaction_launch_action_fires():
    """/Launch subtype is executable; openaction must still fire."""
    action = DictionaryObject({
        NameObject("/S"): NameObject("/Launch"),
        NameObject("/F"): TextStringObject("/bin/echo test"),
    })
    findings = _scan_with_open_action(action)
    assert _fires_openaction(findings), (
        f"openaction failed to fire on /Launch; findings={findings}"
    )


def test_openaction_uri_action_fires():
    """/URI subtype is executable (network call); openaction fires."""
    action = DictionaryObject({
        NameObject("/S"): NameObject("/URI"),
        NameObject("/URI"): TextStringObject("https://attacker.example/"),
    })
    findings = _scan_with_open_action(action)
    assert _fires_openaction(findings), (
        f"openaction failed to fire on /URI; findings={findings}"
    )
