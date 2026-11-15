"""LangChain adapter: scan documents before they reach a model or an index.

    from integrations.langchain import BayyinahDocumentScanner

    docs = loader.load()
    docs = BayyinahDocumentScanner(on_flagged="drop").transform_documents(docs)

Each document is checked twice where possible: the file named in
``metadata["source"]`` (once per file, cached) and the document's own
text. The file check is the one that sees white text, off-page text and
hidden runs; see ``integrations.core``.

``on_flagged``:
  ``"annotate"``  keep every document, record the result in metadata (default)
  ``"drop"``      remove flagged documents
  ``"clean"``     strip hidden characters from the text; file-level
                  findings cannot be cleaned, so those documents stay
                  annotated
  ``"raise"``     raise ``HiddenContentError`` on the first flagged document

Requires ``langchain-core``.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from langchain_core.documents import BaseDocumentTransformer, Document

from integrations.core import Verdict, check_file, check_text

_MODES = ("annotate", "drop", "clean", "raise")


class HiddenContentError(RuntimeError):
    def __init__(self, source: str, verdict: Verdict) -> None:
        super().__init__(
            f"hidden content in {source}: {', '.join(verdict.mechanisms)}")
        self.verdict = verdict


class BayyinahDocumentScanner(BaseDocumentTransformer):
    """Scan, annotate, drop or clean LangChain documents."""

    def __init__(
        self, on_flagged: str = "annotate", *, scan_source_files: bool = True,
        only_instruction_like: bool = False,
    ) -> None:
        if on_flagged not in _MODES:
            raise ValueError(f"on_flagged must be one of {_MODES}")
        self.on_flagged = on_flagged
        self.scan_source_files = scan_source_files
        self.only_instruction_like = only_instruction_like
        self._file_cache: dict[str, Verdict] = {}

    def _file_verdict(self, source: Any) -> Verdict | None:
        if not (self.scan_source_files and isinstance(source, (str, Path))):
            return None
        key = str(source)
        if key not in self._file_cache:
            path = Path(key)
            try:
                ok = path.is_file()
            except OSError:
                ok = False
            if not ok:
                return None
            self._file_cache[key] = check_file(path)
        return self._file_cache[key]

    def _hit(self, v: Verdict | None) -> bool:
        if v is None:
            return False
        return v.instruction_like if self.only_instruction_like else v.flagged

    def transform_documents(
        self, documents: Sequence[Document], **kwargs: Any,
    ) -> Sequence[Document]:
        out: list[Document] = []
        for doc in documents:
            source = doc.metadata.get("source")
            file_v = self._file_verdict(source)
            text_v = check_text(doc.page_content, str(source or "<text>"))
            flagged = self._hit(file_v) or self._hit(text_v)
            mechanisms = list(dict.fromkeys(
                (file_v.mechanisms if file_v else ()) + text_v.mechanisms))
            meta = dict(doc.metadata)
            meta["bayyinah_flagged"] = flagged
            meta["bayyinah_instruction_like"] = bool(
                (file_v and file_v.instruction_like) or text_v.instruction_like)
            meta["bayyinah_mechanisms"] = mechanisms
            meta["bayyinah_file_scanned"] = file_v is not None
            content = doc.page_content
            if flagged:
                if self.on_flagged == "raise":
                    raise HiddenContentError(
                        str(source or "<text>"), file_v if self._hit(file_v) else text_v)
                if self.on_flagged == "drop":
                    continue
                if self.on_flagged == "clean":
                    from application.sanitize import clean_text
                    result = clean_text(content)
                    content = result.text
                    meta["bayyinah_removed"] = result.total_removed
            out.append(Document(page_content=content, metadata=meta))
        return out


__all__ = ["BayyinahDocumentScanner", "HiddenContentError"]
