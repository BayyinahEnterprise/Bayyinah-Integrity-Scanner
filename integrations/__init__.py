"""Adapters that place the scanner in front of an AI pipeline.

``integrations.core``        framework-free helpers (``check_text``, ``check_file``)
``integrations.langchain``   LangChain document transformer
``integrations.llamaindex``  LlamaIndex transform component
``integrations.mcp_server``  Model Context Protocol server

Each framework module imports its framework lazily, so installing
bayyinah never pulls one in.
"""

from integrations.core import Verdict, check_file, check_text

__all__ = ["Verdict", "check_file", "check_text"]
