# Format-Routing Gauntlet - v1.1.2 Tier 0 Closure

**Date:** 2026-04-27
**Scanner version:** Bayyinah 1.1.2 (live at https://bayyinah.dev once deployed; v1.1.1 baseline 2 of 4 vectors FAIL)
**Triggered by:** The 2026-04-27 Mughlaq Trap stress test (`docs/adversarial/mughlaq_trap_REPORT.md`)
**Result (target):** 6 of 6 routing-divergence fixtures CAUGHT with Tier 0; 1 control fixture passes through with no Tier 0 finding fired.

The 42-fixture per-format gauntlet probes whether each analyzer catches concealment within its declared format. It does not probe whether the routing decision that put the file in front of that analyzer was honest. The Mughlaq Trap stress test on April 27 showed that v1.1.1 silently trusts magic bytes over the user's declared extension - a real adversarial PDF renamed to `.docx` was routed to the PDF analyzer without any disclosure. The Tier 0 layer added in v1.1.2 closes that gap.

This gauntlet is the falsifiability surface for the Tier 0 layer. Each fixture pairs one routing-divergence vector to one expected trigger condition; CI re-runs the gauntlet on every commit so a regression fails loudly.

## Summary table

| # | Fixture | Vector | Expected trigger | Expected verdict | Fixture size |
|---|---|---|---|---|---|
| 01 | `01_polyglot.docx` | PDF magic + `.docx` extension (V1 seed) | T0a `trusted_magic_bytes` | mughlaq | 1,535 B |
| 02 | `02_pdf_as_txt.txt` | PDF magic + `.txt` extension (V2 seed) | T0a `trusted_magic_bytes` | mughlaq | 1,535 B |
| 03 | `03_empty.pdf` | 4-byte `%PDF` body with `.pdf` extension (V3 seed) | T0c `below_content_depth_floor` | mughlaq | 4 B |
| 04 | `04_truncated.pdf` | 12-byte PDF preamble, no body, no EOF | T0c `below_content_depth_floor` | mughlaq | 12 B |
| 05 | `05_docx_as_xlsx.xlsx` | DOCX zip container with `.xlsx` extension | T0d `ooxml_internal_path_divergence` | mughlaq | 37,064 B |
| 06 | `06_unanalyzed.txt` | 4-byte `.txt` (V5 case from Mughlaq Trap) | T0c `below_content_depth_floor` | mughlaq | 4 B |
| 07 | `07_control.pdf` | Real PDF with real extension (V4 control) | none (clean baseline) | mukhfi (downstream Tier 1) | 1,535 B |

**Target hit rate: 6 of 6 routing-divergence fixtures + 1 of 1 control = 7 of 7 honest verdicts.**

The control fixture is essential. A Tier 0 layer that fires on every file is no honest disclosure - it is just a global mughlaq flag. Verifying that fixture 07 passes through with no Tier 0 finding (and the existing v1.1.1 Tier 1 white-on-white finding still fires) is what keeps the layer falsifiable.

## Per-fixture root cause

### 01 - polyglot.docx - T0a trusted_magic_bytes

```
claimed_format:    docx
inferred_format:   pdf
routing_decision:  trusted_magic_bytes
bytes_sampled:     1535
analyzer_invoked:  pdf
```

The user uploaded a file labelled `.docx`. The router's magic-byte loop matched `%PDF-` at byte 0; the extension map said `.docx` -> DOCX; FileRouter set `extension_mismatch=True`. The Tier 0 detector translates that flag into a `format_routing_divergence` finding with the `trusted_magic_bytes` routing decision. The verdict resolver in `domain.value_objects.tamyiz_verdict` floors at mughlaq.

The downstream PDF analyzer still runs and may emit Tier 1 findings (the underlying bytes are the same adversarial PDF that produces `white_on_white_text` in the per-format gauntlet). Those findings are recorded; the verdict stays mughlaq because the routing question takes precedence over the content question. The user sees: "this file's identity is in dispute, and within the analyzer that ran, here is what was found."

### 02 - pdf_as_txt.txt - T0a trusted_magic_bytes

```
claimed_format:    txt
inferred_format:   pdf
routing_decision:  trusted_magic_bytes
bytes_sampled:     1535
analyzer_invoked:  pdf
```

Same shape as fixture 01 with a different lying extension. Confirms the layer fires regardless of which non-PDF extension is claimed.

### 03 - empty.pdf - T0c below_content_depth_floor

```
claimed_format:    pdf
inferred_format:   unknown
routing_decision:  below_content_depth_floor
bytes_sampled:     4
analyzer_invoked:  null
```

A 4-byte file cannot carry a verified concealment verdict regardless of extension. The current v1.1.1 behaviour (mughlaq via `scan_incomplete=true` from the PDF analyzer's "Could not open PDF" error) is honest, but the disclosure is opaque - the user is told the scan failed for an unspecified reason, not that the file was structurally insufficient. The Tier 0 layer surfaces the structural fact directly.

### 04 - truncated.pdf - T0c below_content_depth_floor

```
claimed_format:    pdf
inferred_format:   pdf
routing_decision:  below_content_depth_floor
bytes_sampled:     12
analyzer_invoked:  null
```

12 bytes is enough to satisfy the magic-byte sniff (`%PDF-1.4\n%a\n` starts with `%PDF-`) but well below any honest analysis floor. The router would otherwise route this to the PDF analyzer, which would then error with `Could not open PDF`. Same end-state verdict (mughlaq), more honest disclosure path: the size check fires before the analyzer attempts to parse a body that is not there.

### 05 - docx_as_xlsx.xlsx - T0d ooxml_internal_path_divergence

```
claimed_format:    xlsx
inferred_format:   docx
routing_decision:  ooxml_internal_path_divergence
bytes_sampled:     37064
analyzer_invoked:  xlsx
```

Both DOCX and XLSX share the ZIP magic `PK\x03\x04`; the v1.1.1 router disambiguates on extension. A `.xlsx` whose ZIP head declares `word/document.xml` is a DOCX in disguise. The Tier 0 layer inspects the head bytes for the canonical OOXML part names and surfaces the divergence. Without this check the file would route to XlsxAnalyzer dishonestly.

### 06 - unanalyzed.txt - T0c below_content_depth_floor

```
claimed_format:    txt
inferred_format:   code
routing_decision:  below_content_depth_floor
bytes_sampled:     4
analyzer_invoked:  null
```

The Mughlaq Trap report's V5 case. On v1.1.1 a 4-byte `.txt` returns score 1.0 sahih because TextFileAnalyzer finds no concealment patterns in `aaaa`. The Tier 0 layer rejects the verdict on content-depth grounds: 4 bytes cannot honestly sustain a sahih claim regardless of which analyzer ran. The layer's content-depth floor (16 bytes) is calibrated to admit single-line CSV/JSON/EML and short clean code files while rejecting structurally insufficient inputs.

### 07 - control.pdf - clean baseline

No Tier 0 finding fires. The downstream PDF analyzer's existing v1.1.1 mechanism (`white_on_white_text`) still fires as Tier 1, integrity score is 0.82, verdict resolves to mukhfi via the existing `tamyiz_verdict` path. This fixture verifies the Tier 0 layer is falsifiable: a real PDF with a real extension does not get false-flagged.

## Verification

```
# Build the fixtures (deterministic - byte-identical on every re-run).
python3 docs/adversarial/format_routing_gauntlet/build_fixtures.py

# Run the gauntlet against the live API.
python3 docs/adversarial/format_routing_gauntlet/run_gauntlet.py
```

A passing gauntlet shows: fixtures 01-06 produce a `format_routing_divergence` Tier 0 finding with the appropriate `routing_decision` value, verdict mughlaq for each; fixture 07 produces no Tier 0 finding.

## What this gauntlet does NOT cover

This gauntlet covers routing-divergence honesty. It does not cover concealment within a given format - that work lives in the seven per-format gauntlets. A polyglot file (fixture 01) that contains genuinely concealed content will produce both a Tier 0 routing finding and any Tier 1/2/3 concealment findings the downstream analyzer fires; the verdict floors at mughlaq because the routing question is unresolved, but the concealment findings are still recorded for the user to inspect.

The five reserved future-work routing rules named in `docs/adversarial/mughlaq_trap_REPORT.md` (cross_stem_metadata_clash, embedded_media_recursive_scan, etc.) are out of scope for v1.1.2 and queued for v1.2+.

> "Wa la talbisu al-haqqa bil-batil wa taktumu al-haqqa wa antum ta'lamun." (Al-Baqarah 2:42)

Bismillah. Tawakkaltu 'ala Allah.
