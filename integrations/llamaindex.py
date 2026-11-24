"""LlamaIndex adapter: a transform component for an ingestion pipeline.

    from llama_index.core.ingestion import IngestionPipeline
    from integrations.llamaindex import BayyinahNodeScanner

    pipeline = IngestionPipeline(
        transformations=[BayyinahNodeScanner(on_flagged="drop"), splitter, embedder])

The file named in a node's ``file_path`` metadata is scanned once and
cached; the node text is scanned as well. ``on_flagged`` takes the same
values as the LangChain adapter: ``annotate``, ``drop``, ``clean``,
``raise``. Place the component before the splitter so one decision
covers a whole document.

Requires ``llama-index-core``.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from llama_index.core.schema import BaseNode, TransformComponent
from pydantic import PrivateAttr

from integrations.core import Verdict, check_file, check_text

_MODES = ("annotate", "drop", "clean", "raise")


class HiddenContentError(RuntimeError):
    def __init__(self, source: str, verdict: Verdict) -> None:
        super().__init__(
            f"hidden content in {source}: {', '.join(verdict.mechanisms)}")
        self.verdict = verdict


class BayyinahNodeScanner(TransformComponent):
    """Scan, annotate, drop or clean LlamaIndex nodes."""

    on_flagged: str = "annotate"
    scan_source_files: bool = True
    only_instruction_like: bool = False
    _file_cache: dict = PrivateAttr(default_factory=dict)

    def _file_verdict(self, node: BaseNode) -> Verdict | None:
        if not self.scan_source_files:
            return None
        source = node.metadata.get("file_path") or node.metadata.get("source")
        if not isinstance(source, (str, Path)):
            return None
        key = str(source)
        if key not in self._file_cache:
            try:
                ok = Path(key).is_file()
            except OSError:
                ok = False
            if not ok:
                return None
            self._file_cache[key] = check_file(key)
        return self._file_cache[key]

    def _hit(self, v: Verdict | None) -> bool:
        if v is None:
            return False
        return v.instruction_like if self.only_instruction_like else v.flagged

    def __call__(self, nodes: Sequence[BaseNode], **kwargs: Any) -> Sequence[BaseNode]:
        if self.on_flagged not in _MODES:
            raise ValueError(f"on_flagged must be one of {_MODES}")
        out: list[BaseNode] = []
        for node in nodes:
            text = node.get_content()
            file_v = self._file_verdict(node)
            text_v = check_text(text)
            flagged = self._hit(file_v) or self._hit(text_v)
            node.metadata["bayyinah_flagged"] = flagged
            node.metadata["bayyinah_instruction_like"] = bool(
                (file_v and file_v.instruction_like) or text_v.instruction_like)
            node.metadata["bayyinah_mechanisms"] = list(dict.fromkeys(
                (file_v.mechanisms if file_v else ()) + text_v.mechanisms))
            node.metadata["bayyinah_file_scanned"] = file_v is not None
            if flagged:
                if self.on_flagged == "raise":
                    raise HiddenContentError(
                        str(node.metadata.get("file_path", "<text>")),
                        file_v if self._hit(file_v) else text_v)
                if self.on_flagged == "drop":
                    continue
                if self.on_flagged == "clean":
                    from application.sanitize import clean_text
                    result = clean_text(text)
                    node.set_content(result.text)
                    node.metadata["bayyinah_removed"] = result.total_removed
            out.append(node)
        return out


__all__ = ["BayyinahNodeScanner", "HiddenContentError"]
