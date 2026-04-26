"""
Bayyinah application layer — the orchestrator (Al-Baqarah 2:285).

    ءَامَنَ ٱلرَّسُولُ بِمَآ أُنزِلَ إِلَيْهِ مِن رَّبِّهِۦ وَٱلْمُؤْمِنُونَ ۚ كُلٌّ ءَامَنَ بِٱللَّهِ وَمَلَـٰٓئِكَتِهِۦ
    وَكُتُبِهِۦ وَرُسُلِهِۦ لَا نُفَرِّقُ بَيْنَ أَحَدٍ مِّن رُّسُلِهِۦ

    "The Messenger has believed in what was revealed to him from his
    Lord, and the believers. All have believed in Allah and His angels
    and His books and His messengers — we make no distinction between
    any of His messengers."

The architectural reading: this layer makes no distinction between any
of its witnesses. Every analyzer's findings are composed without
privilege. No analyzer is weighted higher than another; no analyzer is
silenced when another speaks. The application layer is where the
middle-community contract (``analyzers/base.py``) meets the infrastructure
(``infrastructure/pdf_client.py``) and produces one unified
``IntegrityReport`` that the rest of Bayyinah can render, serialise, or
decide against.

Phase 6 of the Al-Baqarah refactor. Additive-only: ``bayyinah_v0`` and
``bayyinah_v0_1`` continue to own their own ScanService orchestrators
until a later phase migrates the default pipeline onto this one.

Structural contents:

    ScanService            — orchestrator. Given a PDF path, routes it
                             through the file router, pre-flights
                             pymupdf, dispatches every registered
                             analyzer via the AnalyzerRegistry, and
                             returns one merged ``IntegrityReport``.
    default_pdf_registry   — factory producing the shipped default
                             registry: ZahirTextAnalyzer then
                             BatinObjectAnalyzer, in that order
                             (matches v0.1's finding emission order).
"""

from __future__ import annotations

from application.scan_service import (
    ScanService,
    default_pdf_registry,
    default_registry,
)

__all__ = [
    "ScanService",
    "default_pdf_registry",
    "default_registry",
]
