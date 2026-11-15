"""Reader's view and the render-versus-extract check."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from analyzers.pdf_render_oracle import examine_pdf
from application.reader_view import ReaderViewError, reader_view
from application.scan_service import ScanService
from bench.concealment_map.grammar import MARK, Config, build
from cli.main import main as cli_main

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.mark.parametrize("cfg", [
    Config(color="white"), Config(alpha="0"), Config(clip="clip_away"),
    Config(overlay="white_box"), Config(render_mode="3"), Config(render_mode="7"),
    Config(scale="tiny"), Config(color="near_white"),
])
def test_hidden_payload_is_reported_and_left_out_of_the_view(tmp_path: Path, cfg: Config) -> None:
    pdf = tmp_path / "doc.pdf"
    build(cfg, str(pdf))
    assert ScanService().scan(pdf).findings, cfg.key()
    receipt = reader_view(pdf)
    view = Path(receipt["view_path"]).read_text(encoding="utf-8")
    assert "Quarterly vendor summary" in view
    assert MARK not in view


def test_visible_text_is_kept_and_not_reported(tmp_path: Path) -> None:
    pdf = tmp_path / "doc.pdf"
    build(Config(), str(pdf))
    assert ScanService().scan(pdf).findings == []
    result = examine_pdf(pdf)
    assert not result.unseen and len(result.seen) == 2
    view = Path(reader_view(pdf)["view_path"]).read_text(encoding="utf-8")
    assert MARK in view


def test_render_check_names_no_cause(tmp_path: Path) -> None:
    pdf = tmp_path / "doc.pdf"
    build(Config(alpha="0"), str(pdf))
    (f,) = [x for x in ScanService().scan(pdf).findings
            if x.mechanism == "pdf_text_not_rendered"]
    assert MARK in f.concealed and f.location == "page 1"


def test_receipt(tmp_path: Path) -> None:
    pdf = tmp_path / "doc.pdf"
    build(Config(color="white"), str(pdf))
    original = pdf.read_bytes()
    receipt = reader_view(pdf)
    assert pdf.read_bytes() == original
    on_disk = json.loads(Path(receipt["receipt_path"]).read_text(encoding="utf-8"))
    assert on_disk["schema"] == "bayyinah.reader-view-receipt/1"
    assert on_disk["spans_left_out"] == 1 and on_disk["spans_kept"] == 1
    assert MARK in on_disk["left_out_preview"][0]
    assert "not a certificate" in on_disk["statement"]


def test_office_file_hidden_text_is_left_out(tmp_path: Path) -> None:
    if not (shutil.which("soffice") or shutil.which("libreoffice")):
        pytest.skip("LibreOffice not installed")
    src = tmp_path / "h.docx"
    shutil.copy(FIXTURES / "docx" / "adversarial" / "hidden_text.docx", src)
    receipt = reader_view(src)
    view = Path(receipt["view_path"]).read_text(encoding="utf-8")
    assert "Visible intro" in view and "HIDDEN" not in view
    assert receipt["rendered_via"] == "libreoffice"


def test_unsupported_and_cli(tmp_path: Path, capsys) -> None:
    txt = tmp_path / "a.txt"
    txt.write_text("hello\n", encoding="utf-8")
    with pytest.raises(ReaderViewError):
        reader_view(txt)
    assert cli_main(["view", str(txt)]) == 2
    pdf = tmp_path / "doc.pdf"
    build(Config(color="white"), str(pdf))
    assert cli_main(["view", str(pdf)]) == 0
    assert "left out 1" in capsys.readouterr().out
