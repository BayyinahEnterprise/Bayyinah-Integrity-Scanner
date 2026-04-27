# File Type Coverage - Bayyinah v1.2 Scope Memo

> **SUPERSEDED 2026-04-26 by [ADR-001-v1_2_scope.md](ADR-001-v1_2_scope.md).**
> Claude flagged that this memo silently overrode the prior depth-before-scope rule. The competition win condition is depth, not breadth. v1.1.2 closes the existing 42-fixture adversarial gauntlet first; v1.2.0 adds only RTF and Jupyter on top of CC-1. Most of the original Tier A defers to v1.2.1+. This memo is kept as an appendix for the per-format threat-surface notes; do not implement as written.

**For:** Claude (Anthropic)
**From:** Bilal Syed Arfeen (Bayyinah, product/architecture/research)
**Date:** 2026-04-26 (~44 days to Perplexity Billion Dollar Build, June 9 2026)
**Repo:** `https://github.com/BayyinahEnterprise/Bayyinah-Integrity-Scanner`
**Branch:** `main`
**Current version:** v1.1.1 (HEAD `a03e566`)
**Target version:** v1.2.0

---

## Why this exists

The judges will pull a file we did not anticipate. We need every reasonable extension a reviewer might drop into the demo to either (a) return a real verdict from a real analyzer or (b) return a deliberate, well-rendered "out of scope by policy" verdict, never a confused 0.5 with `scan_incomplete: true` that looks like a bug.

Today the scanner covers 19 distinct `FileKind` values. A `.odt`, `.rtf`, `.docm`, `.gif`, `.webp`, or `.ipynb` falls through to the fallback analyzer and returns `score=0.5 / scan_incomplete=true / findings=[unknown_format Tier-3]`. Mathematically defensible. Demo-disastrous.

This memo specifies every gap, the threat surface for each format, the recommended analyzer reuse, the LOC estimate, the new mechanisms it would yield, and the priority tier for the v1.2 ship before June 9.

---

## Current support - verified inventory

Run `grep -E '^\s+[A-Z_]+\s*=\s*"' infrastructure/file_router.py` to confirm.

**FileKind enum (19 real + UNKNOWN):**

| Family | FileKinds | Extensions today |
|---|---|---|
| Document | PDF, DOCX, PPTX, XLSX | `.pdf .docx .xlsx .pptx` |
| Markup / data | HTML, MARKDOWN, JSON, CSV, EML | `.html .htm .md .markdown .json .csv .tsv .psv .eml` |
| Code / text | CODE | `.txt .py .js .ts .tsx .jsx .go .rs .java .c .cpp .h .hpp .rb` |
| Image | IMAGE_PNG, IMAGE_JPEG, IMAGE_SVG | `.png .jpg .jpeg .svg .svgz` |
| Audio | AUDIO_MP3, AUDIO_WAV, AUDIO_FLAC, AUDIO_M4A, AUDIO_OGG | `.mp3 .wav .wave .flac .m4a .m4b .ogg .oga .opus` |
| Video | VIDEO_MP4, VIDEO_MOV, VIDEO_WEBM, VIDEO_MKV | `.mp4 .m4v .mov .webm .mkv` |

The landing page advertises **23 file kinds** because `htm` / `tsv` / `m4v` / `wave` / `oga` / `opus` count as distinct extensions even though they collapse into the same `FileKind`. The honest count of distinct kinds is **19**.

**Existing analyzers in `analyzers/`:**
`audio_analyzer.py`, `csv_analyzer.py`, `docx_analyzer.py`, `eml_analyzer.py`, `fallback_analyzer.py`, `html_analyzer.py`, `image_analyzer.py`, `json_analyzer.py`, `object_analyzer.py`, `pptx_analyzer.py`, `svg_analyzer.py`, `text_analyzer.py`, `text_file_analyzer.py`, `video_analyzer.py`, `xlsx_analyzer.py`, plus correlation modules.

---

## Cross-cutting fix (do this first, in parallel with everything else)

### CC-1. Render the `mughlaq` (closed) verdict in the v2 simulator and drop-zone

**File:** `docs/landing-mock-v2/index.html`, function `deriveVerdict(report)`

Today `deriveVerdict` collapses `scan_incomplete=true` to `mushtabih`. The README at `api.py` already defines `mughlaq` ("closed - scan incomplete or errored, no verdict can be issued"). Use it. Update the rule to:

- **`sahih`** - `integrity_score === 1.0 && findings.length === 0 && scan_incomplete === false`
- **`mukhfi`** - at least one Tier-1 or Tier-2 finding
- **`mushtabih`** - Tier-3 only, `scan_incomplete === false`
- **`mughlaq`** - `scan_incomplete === true` (any cause: encrypted PDF, unknown format, parser error). This is the current 0.5 case. Render it with a copy block: "This file kind is outside Bayyinah's verified scope. The scanner refused to issue a verdict rather than guess." Plus a list of what we would have looked for.
- **`munafiq`** - reserved for `integrity_score < 0.3` with verified mechanisms; do not derive in the simulator yet. (Already in the legend at api.py:368.)

Also add a `scope` field to each finding when the cause is "unknown format" so the panel can render a friendly "this is what we would scan if we supported it" hint.

**Cost:** ~80 LOC of JS in the simulator + 30 lines of CSS for a fifth tier-pill style. **No backend changes.**

**Why it matters:** Every gap below currently produces a `mughlaq` outcome. Rendering it well converts every "we don't support this yet" moment from a bug into a deliberate scope boundary. Ship CC-1 before any analyzer work.

---

## Tier A - must-ship before June 9

These cover ~95% of what a judge would realistically pull. All are doable in the remaining 44 days.

### A-1. OpenDocument family - `.odt`, `.ods`, `.odp`, `.odg`, `.fodt`, `.fods`, `.fodp`

**Format:** ZIP container with `mimetype` file at offset 0 (must be uncompressed and the first entry - strict OpenDocument spec). Inside: `content.xml`, `styles.xml`, `meta.xml`, `manifest.xml`, optional `Scripts/` directory for Basic macros, optional `Pictures/` for embedded media.

**Threat surface (mirrors DOCX):**
- Hidden text (text style with `text:display="none"` or invisible font color)
- Tracked changes left in `content.xml`
- Comments not rendered in normal view
- Embedded macros under `Scripts/` (LibreOffice Basic, Python via APSO)
- External references in `meta.xml` (linked images, linked sections)
- Mismatch between rendered text in `content.xml` and OCR of any embedded image
- Manifest declarations vs actual ZIP contents (declared encrypted but not, vice versa)

**Reuse:** `docx_analyzer.py` covers ~70% of the same threats. Lift the ZIP-container scanning, the XML namespace traversal, the embedded-image extractor, and the comment/hidden-text detectors. The XML namespace prefixes change (`text:`, `office:`, `style:` instead of `w:`, `wp:`) but the structure is parallel.

**New analyzer:** `analyzers/odf_analyzer.py`. Single class `OpenDocumentAnalyzer` handles all six extensions because the format is uniform; the `mimetype` entry tells you which kind it is.

**Router changes:** Add seven extensions to `_EXT_MAP`. Add a magic-byte rule: ZIP magic + first-entry-name == `mimetype` → read the mimetype string, route by content. Add three FileKinds: `ODF_TEXT`, `ODF_SHEET`, `ODF_PRESENTATION`.

**Estimate:** ~600 LOC analyzer + ~80 LOC router. **8-10 mechanisms** (mirroring docx_analyzer's set with namespace-aware variants).

**Risk:** None. Format is open, well-documented, and structurally identical to OOXML.

---

### A-2. Macro-enabled OOXML - `.docm`, `.dotm`, `.xlsm`, `.xltm`, `.pptm`, `.potm`

**Format:** Same ZIP container as DOCX/XLSX/PPTX, but with an additional part: `word/vbaProject.bin` (or `xl/`, `ppt/`). The `[Content_Types].xml` declares the `application/vnd.ms-office.vbaProject` content type. The `vbaProject.bin` is itself an OLE2/CFBF compound document containing VBA modules.

**Threat surface:**
- **Tier-1 finding: presence of `vbaProject.bin`.** Unsigned macros are a verified concealment mechanism. The whole reason `.docm` exists as a separate extension is to flag macros at the filesystem level.
- Auto-execute macros (`Document_Open`, `Workbook_Open`, `Auto_Open`)
- VBA stomping (the source code in the compressed module disagrees with the compiled p-code)
- External code loading (`Shell`, `URLDownloadToFile`, `MSXML2.XMLHTTP`)
- Office signing certificate present but expired or self-signed

**Reuse:** Existing `docx_analyzer`, `xlsx_analyzer`, `pptx_analyzer` already parse the ZIP. Add macro detection as a **shared helper** in `analyzers/macro_detector.py` and call it from each.

**Optional dependency:** [`oletools`](https://github.com/decalage2/oletools) (pip-installable, MIT) gives you VBA module enumeration, p-code stomping detection, and IOC extraction. If we add it, mark it optional in `pyproject.toml` extras to keep the core install lean.

**Router changes:** Add six extensions to `_EXT_MAP`, mapping to existing DOCX/XLSX/PPTX kinds. Or add three new FileKinds (`DOCM`, `XLSM`, `PPTM`) if we want them rendered separately in the UI. **Recommend the latter** - judges should see "macro-enabled Word document" in the verdict panel, not "Word document."

**Estimate:** ~400 LOC shared helper + ~150 LOC integration into the three analyzers + router updates. **5-7 mechanisms.**

**Risk:** Low if we use `oletools`. Medium if we hand-roll VBA decompression.

---

### A-3. RTF - `.rtf`

**Format:** Plain-text with `{\rtf1...}` outer braces, control words start with `\`, groups nest with `{}`.

**Threat surface (RTF is a textbook concealment vector):**
- **Hidden text:** `\v ... \v0` makes a run invisible
- **Font color = background color:** `\cf1\cb1` with the same color in the color table
- **Embedded objects:** `\object \objemb \objdata` with hex-encoded payload (classic OLE-via-RTF)
- **`\*\template` external links:** auto-fetch a remote template (CVE-2017-0199 territory)
- **Encoded payloads:** `\bin{N}` followed by N raw bytes that don't appear in any rendering
- **Font/color table mismatches:** colors referenced that aren't defined; font 0 hidden
- **Whitespace concealment:** repeated `\par` or `\page` separating visible and concealed sections

**New analyzer:** `analyzers/rtf_analyzer.py`. Pure-Python parser - RTF tokenizer is ~150 LOC, the rest is mechanism logic.

**Router changes:** Magic byte: `{\rtf1`. Extension: `.rtf`. New FileKind: `RTF`.

**Estimate:** ~600 LOC analyzer + ~30 LOC router. **8-10 mechanisms** (each of the bullets above).

**Risk:** Low. RTF is fully specified by Microsoft; no ambiguity.

**Why this matters most:** RTF is the canonical "I made a Word doc that hides $10,000 in it" example. Not covering RTF is a credibility gap. Reviewers from the security community will specifically test it.

---

### A-4. Jupyter notebooks - `.ipynb`

**Format:** JSON document. Top-level keys: `cells[]`, `metadata`, `nbformat`, `nbformat_minor`. Each cell has `cell_type` (code/markdown/raw), `source`, `outputs`, `metadata`.

**Threat surface (high relevance to Perplexity / AI demographic):**
- **Hidden cells:** `metadata.jupyter.source_hidden = true` or `metadata.collapsed = true` - the cell executes but the source isn't shown in the rendered view
- **Hidden outputs:** `metadata.jupyter.outputs_hidden = true` - the output (which may contain prompt injection) is invisible in normal view
- **Base64-encoded outputs > N bytes** that aren't images (concealment via `application/octet-stream` MIME)
- **Shell magics:** `!curl ...`, `!pip install <suspicious>`, `!wget ...`
- **`%load_ext` / `%run` of remote modules:** `%run http://...`
- **`metadata.kernelspec` mismatch with code language:** Python kernel running cells claiming to be R
- **Execution count gaps:** cells with `execution_count: 5` followed by `execution_count: 12` (cells were run and removed, leaving artifact gaps that suggest hidden state)
- **`raw` cells with executable content:** raw cells aren't run but `nbconvert` can be configured to render them; concealment surface

**Reuse:** `json_analyzer` for the parse, plus existing Unicode concealment detectors over each cell's source.

**New analyzer:** `analyzers/ipynb_analyzer.py`. Subclasses or composes `JsonAnalyzer`. Adds the seven Jupyter-specific mechanisms.

**Router changes:** Extension `.ipynb` → new FileKind `IPYNB`. Magic-byte: file starts with `{` and contains `"nbformat"` in the first 1KB.

**Estimate:** ~400 LOC analyzer + ~30 LOC router. **7-9 mechanisms.**

**Risk:** Low. Format is JSON Schema-defined.

**Strategic value:** This is the *single most thematically aligned* format for the Perplexity competition. A scanner that catches hidden prompt injection in a notebook your LLM is about to load - that is the entire Bayyinah thesis in one demo. **Prioritize this even above A-2 if forced to choose.**

---

### A-5. Image family expansion - `.gif`, `.webp`, `.bmp`, `.tiff`, `.heic`, `.ico`

**Format summaries:**
- **GIF:** `GIF87a` / `GIF89a` magic. Multi-frame. Concealment via animated frames that look static, comments in extension blocks, application extensions (Netscape loop, XMP).
- **WebP:** `RIFF....WEBP` magic. Lossy/lossless variants. Concealment in EXIF/XMP chunks, ICCP chunks.
- **BMP:** `BM` magic. Steganography in unused header bytes, palette manipulation, raw pixel concealment.
- **TIFF:** `II*\x00` or `MM\x00*` magic. Famously extensible - IFD chains can hide data, multiple subfile types, EXIF in tags 0x8769, GeoTIFF tags.
- **HEIC/HEIF:** `ftypheic` / `ftypheif` ISO BMFF box. Same family as MP4. Concealment in `meta` boxes, alternate codings.
- **ICO:** Multi-resolution container. Concealment in unused frames, mismatched sizes.

**Threat surface (largely shared):**
- EXIF metadata concealment (camera says iPhone, file modified time differs by months)
- ICC profile presence with payload-shaped data
- XMP/IPTC fields containing scripts or URLs
- Trailing data after EOF marker (steganography)
- Palette / colormap manipulation (BMP, GIF) for QR-code-style concealment
- Frame count / loop count anomalies (GIF, WebP animated)

**Reuse:** `image_analyzer.py` already handles PNG/JPEG. Pillow (already a dep) handles GIF, WebP, BMP, TIFF, ICO natively. HEIC needs `pillow-heif` (optional extra).

**Approach:** Generalize `image_analyzer` into a family analyzer keyed by detected codec. Add per-format finding modules for GIF (frame analysis), TIFF (IFD walking), HEIC (box parsing - reuse `video_analyzer`'s ISO BMFF walker).

**Router changes:** Add six extensions, six new FileKinds (`IMAGE_GIF`, `IMAGE_WEBP`, `IMAGE_BMP`, `IMAGE_TIFF`, `IMAGE_HEIC`, `IMAGE_ICO`) or one combined `IMAGE_OTHER` with the codec carried in the detection metadata. **Recommend separate FileKinds** for clean per-format analyzer dispatch.

**Estimate:** ~700 LOC across new format-specific helpers, ~80 LOC router, ~50 LOC `pyproject.toml` extras. **10-12 mechanisms** spread across the formats.

**Risk:** Medium. HEIC parsing is the trickiest. If `pillow-heif` proves brittle, ship HEIC as Tier B and the rest as Tier A.

**Why it matters:** A judge demoing on a phone hands you a `.webp` or `.heic` because that's what their camera produces. Screenshot tools generate `.gif`. Old enterprise content is `.bmp` and `.tiff`. Not covering these reads as "missed the modern web."

---

### A-6. Old binary Office - `.doc`, `.xls`, `.ppt`, `.dot`, `.xlt`, `.pot`

**Format:** OLE2 / Compound File Binary Format (CFBF). Pre-2007 Office. Same container as `vbaProject.bin`. Magic: `D0 CF 11 E0 A1 B1 1A E1`.

**Threat surface:**
- **Macros:** legacy VBA, often less scrutinized than `.docm`
- **OLE-embedded objects:** Equation Editor exploits (CVE-2017-11882), Flash, Shockwave
- **Hidden streams:** CFBF supports unlimited named streams; concealment by storing payload in a non-standard stream
- **Tracked changes / revision history** in the document stream
- **Hidden columns/sheets** (XLS specifically)
- **Slack space** in the FAT-style allocation table

**Reuse:** Use `oletools` for VBA + IOC extraction. Use `olefile` (MIT) for raw stream walking. Both are standard, widely deployed.

**New analyzer:** `analyzers/ole2_analyzer.py`. Handles all six extensions; per-extension dispatch by examining the `WordDocument` / `Workbook` / `PowerPoint Document` named stream.

**Router changes:** Magic-byte rule for OLE2. Six extensions, three new FileKinds (`DOC`, `XLS`, `PPT`).

**Estimate:** ~600 LOC analyzer + ~50 LOC router. **8-10 mechanisms.**

**Risk:** Medium. CFBF is fiddly. `olefile` makes it tractable.

**Why include in Tier A:** Enterprise judges (legal, finance, government) still receive `.doc` and `.xls`. A scanner that says "this binary Office format is too old to verify" looks dated.

---

### A-7. Outlook MSG - `.msg`

**Format:** OLE2/CFBF (same family as A-6). Streams under `__substg1.0_*` encode each MAPI property. Email body in `PR_BODY` (plaintext) and `PR_HTML` (HTML). Attachments under `__attach_*` substorages.

**Threat surface:**
- Plaintext body and HTML body disagree (the canonical email-concealment vector - already covered for `.eml` in `eml_analyzer`)
- Attachment with display name disagreeing with `PR_ATTACH_FILENAME`
- Routing headers in `PR_TRANSPORT_MESSAGE_HEADERS` disagreeing with sender
- Hidden recipients in BCC fields
- Embedded MSG-in-MSG (nested email)

**Reuse:** `eml_analyzer` for the surface/substrate body comparison. `olefile` for the CFBF walk. `extract-msg` (BSD-licensed) is a clean library that flattens MSG → headers + bodies + attachments for analysis.

**New analyzer:** `analyzers/msg_analyzer.py`. Reads MSG via `extract-msg`, then hands the surface text + HTML + headers to the existing `eml_analyzer` pipeline.

**Router changes:** Magic-byte → OLE2; extension `.msg` → new FileKind `MSG`.

**Estimate:** ~300 LOC (mostly thin adapter) + ~30 LOC router. **3-5 net-new mechanisms** (most threats reuse `eml_analyzer`).

**Risk:** Low if we use `extract-msg`.

---

### A-8. EPUB - `.epub`

**Format:** ZIP container. `mimetype` first (uncompressed) = `application/epub+zip`. `META-INF/container.xml` points to the OPF package file. The OPF lists XHTML chapters, CSS, fonts, images.

**Threat surface:**
- Each XHTML chapter has the full HTML threat surface (script injection, hidden divs, tracking pixels, off-screen text)
- OPF manifest disagrees with ZIP contents (declared chapters not present, or vice versa)
- DRM declared but absent (or absent but encrypted)
- Embedded fonts with malformed tables (CVE-class)
- `application/javascript` or unsupported media types listed in manifest

**Reuse:** `html_analyzer.py` for each XHTML chapter. ZIP container handling from `docx_analyzer`.

**New analyzer:** `analyzers/epub_analyzer.py`. Walks the manifest, dispatches each chapter to `html_analyzer`, aggregates findings.

**Router changes:** Same ZIP+mimetype detection as A-1. Extension `.epub` → new FileKind `EPUB`.

**Estimate:** ~250 LOC + ~30 LOC router. **2-4 net-new mechanisms** (most threats reuse `html_analyzer`).

**Risk:** Low.

---

## Tier B - ship if Tier A finishes early

### B-1. Raw archives - `.zip`, `.7z`, `.tar`, `.tar.gz`, `.tgz`, `.rar`

**Threat surface:**
- **Zip-slip / path traversal:** entry names with `../` escape extraction
- **Zip bomb:** small file expanding to gigabytes
- **Polyglot archive:** entries with mismatched declared vs actual sizes
- **Hidden entries:** entries with `internal_file_attributes` flagged hidden
- **Encrypted entries** mixed with plaintext entries (selective concealment)
- **Mismatched magic between extension and content** (a `.zip` that's actually `.7z`)
- **Nested archives** (we report manifest, refuse to recurse beyond depth 1)

**Approach:** Single analyzer, multiple format detectors. Use stdlib `zipfile`, `tarfile`. Use `py7zr` (LGPL) for 7z, optional. **Refuse to recurse arbitrarily** - report contents, depth-1 manifest, and explicitly state recursion policy.

**Estimate:** ~700 LOC + ~50 LOC router. **6-8 mechanisms.** Three new FileKinds: `ARCHIVE_ZIP`, `ARCHIVE_7Z`, `ARCHIVE_TAR`.

**Risk:** Medium. Recursion policy needs explicit documentation in the README.

**Why Tier B not A:** Demo risk - a judge dropping a 1GB archive could time out. Need robust resource limits.

---

### B-2. Top-level XML - `.xml`, `.xsd`, `.xsl`, `.xslt`, `.rss`, `.atom`, `.kml`, `.gpx`

**Threat surface:**
- **XXE (XML External Entity):** `<!ENTITY xxe SYSTEM "file:///etc/passwd">`
- **Billion laughs / quadratic blowup:** entity expansion bombs
- **External DTDs:** loaded over network on parse
- **XSLT with `document()` / `unparsed-text()`:** read external resources during transform
- **XInclude:** embeds external XML during parse
- **CDATA concealment:** payload in `<![CDATA[...]]>` not visible in rendered view
- **XML Signature mismatches:** signed elements differ from rendered

**Reuse:** Pieces of `svg_analyzer.py` (XML parsing already there). `defusedxml` for safe parse with attack detection.

**Estimate:** ~500 LOC + ~50 LOC router. **6-8 mechanisms.** One new FileKind `XML`.

**Risk:** Low with `defusedxml`.

---

### B-3. Config / data interchange - `.yaml`, `.yml`, `.toml`, `.ini`, `.conf`

**Threat surface:**
- **YAML anchors/aliases creating recursion bombs**
- **YAML tag injection:** `!!python/object` and similar non-safe-load constructors (the `safe_load` vs `load` distinction)
- **Multi-document YAML** (`---` separators) with concealment in non-first docs
- **TOML with overlapping table definitions**
- **INI with `[DEFAULT]` shadowing other sections**
- **Comment-encoded payloads** (rare but real)

**New analyzer:** `analyzers/config_analyzer.py`. Uses `ruamel.yaml` (safer than PyYAML) and stdlib `tomllib`/`configparser`.

**Estimate:** ~400 LOC + ~50 LOC router. **5-7 mechanisms.** Three new FileKinds: `YAML`, `TOML`, `INI`.

**Risk:** Low.

**Why Tier B:** Less common as an attached judge file. More relevant for AI-context auditing (prompt files, agent configs) - strategic for v1.3.

---

### B-4. Calendar - `.ics`, `.ical`, `.vcf`, `.vcard`

**Threat surface:**
- **Hidden URLs in `URL:` field** (calendar invites with phishing links)
- **Attendees with display names spoofing email domains**
- **DTSTART/DTEND in different timezones than DTSTAMP** (concealment of true time)
- **VALARM with `ACTION:PROCEDURE`** (legacy execution vector)
- **VCARD with hidden fields** (X- extensions concealing payload)

**New analyzer:** `analyzers/ical_analyzer.py`. Use `icalendar` library (BSD).

**Estimate:** ~250 LOC + ~30 LOC router. **4-6 mechanisms.** Two new FileKinds: `ICS`, `VCARD`.

**Risk:** Low.

---

### B-5. Columnar data - `.parquet`, `.feather`, `.arrow`, `.orc`, `.avro`

**Threat surface:**
- **Schema metadata disagreeing with column data**
- **Custom key/value metadata** in Parquet footer (concealment in `key_value_metadata`)
- **Bloom filters or column statistics** that disagree with actual data
- **Embedded user-defined types** with serialization that triggers code paths
- **Dictionary encoding mismatches**

**Reuse:** `pyarrow` (Apache 2.0) handles all five.

**Estimate:** ~400 LOC + ~30 LOC router. **5-7 mechanisms.** One new FileKind `COLUMNAR_DATA` with codec carried in metadata.

**Risk:** Low.

**Why Tier B:** Niche but data-scientist judges will love it.

---

### B-6. SQLite - `.sqlite`, `.sqlite3`, `.db`

**Threat surface:**
- **Hidden tables** (named with leading `_` or in different schema)
- **Deleted-row carving:** SQLite doesn't zero deleted pages by default; old data recoverable
- **Triggers** that fire on innocuous-looking SELECTs
- **Application-defined functions** loaded via `sqlite3_load_extension`
- **Page count mismatch** between header and actual file size
- **Encrypted/SQLCipher detection** (header pattern differs)

**New analyzer:** `analyzers/sqlite_analyzer.py`. Use stdlib `sqlite3`.

**Estimate:** ~500 LOC + ~30 LOC router. **6-8 mechanisms.** One new FileKind `SQLITE`.

**Risk:** Medium. Deleted-row carving is genuinely hard; ship a basic version.

---

## Tier C - document as deliberate scope, do not implement for v1.2

These get a one-paragraph entry each in `docs/SCOPE.md` explaining why they're out of scope, plus the `mughlaq` verdict renders cleanly when a judge drops one.

- **Office 95-era binary formats** (`.doc97`, `.xls97`) beyond what's covered in A-6
- **Hancom Office** (`.hwp`, `.hwpx`) - Korean office suite, niche
- **Apple iWork** (`.pages`, `.numbers`, `.key`) - proprietary ZIP, undocumented internals
- **Visio** (`.vsdx`, `.vsd`) - XML/OLE2 hybrid, low base rate
- **AutoCAD** (`.dwg`, `.dxf`) - domain-specific, undocumented internals
- **Photoshop** (`.psd`) - layered raster, niche concealment surface
- **Encrypted containers** (`.gpg`, `.pgp`, `.age`) - by design we cannot inspect; report as encrypted, refuse verdict
- **Compiled binaries** (`.exe`, `.dll`, `.so`, `.dylib`, `.app`) - explicitly out of scope; this is a content-integrity tool, not malware analysis
- **Disk images** (`.iso`, `.dmg`, `.vhd`, `.vmdk`) - out of scope; recursion explosion
- **Video conferencing recordings** (`.dav`, proprietary) - vendor-specific
- **Game files, save files, ROMs, models** - out of scope by domain

---

## Summary table

| Tier | Format | New FileKinds | Mechanisms | LOC | Risk | Strategic value |
|---|---|---|---|---|---|---|
| **CC-1** | mughlaq verdict rendering | 0 | 0 | ~110 (JS+CSS) | None | Highest - converts every gap below into deliberate scope |
| **A-1** | OpenDocument family | 3 | 8-10 | ~680 | None | High (Bilal flagged) |
| **A-2** | Macro-enabled OOXML | 3 | 5-7 | ~550 | Low | High (canonical macro vector) |
| **A-3** | RTF | 1 | 8-10 | ~630 | Low | Highest (textbook concealment) |
| **A-4** | Jupyter (.ipynb) | 1 | 7-9 | ~430 | Low | **Highest** (perfect Perplexity fit) |
| **A-5** | Image family expansion | 6 | 10-12 | ~830 | Medium | High (modern web/phones) |
| **A-6** | Old binary Office | 3 | 8-10 | ~650 | Medium | Medium-high (enterprise) |
| **A-7** | Outlook MSG | 1 | 3-5 | ~330 | Low | Medium (enterprise) |
| **A-8** | EPUB | 1 | 2-4 | ~280 | Low | Medium |
| **B-1** | Raw archives | 3 | 6-8 | ~750 | Medium | Medium |
| **B-2** | Top-level XML | 1 | 6-8 | ~550 | Low | Medium |
| **B-3** | YAML/TOML/INI | 3 | 5-7 | ~450 | Low | Medium-high (AI configs) |
| **B-4** | Calendar / vCard | 2 | 4-6 | ~280 | Low | Low |
| **B-5** | Columnar data | 1 | 5-7 | ~430 | Low | Low-medium |
| **B-6** | SQLite | 1 | 6-8 | ~530 | Medium | Low-medium |

**Tier A totals:** 19 new FileKinds, **51-67 new mechanisms**, ~4,380 LOC.
**Tier B totals:** 11 new FileKinds, **32-44 new mechanisms**, ~2,990 LOC.
**Combined A+B:** 30 new FileKinds, 83-111 new mechanisms, ~7,370 LOC.

For context: v1.1.1 has 19 FileKinds and 106 mechanisms. **Tier A alone roughly doubles the surface.** Combined A+B brings the scanner to ~50 file kinds and ~190 mechanisms.

---

## Recommended sequencing for the 44-day window

**Week 1 (now to May 3):**
- CC-1 (mughlaq rendering) - deploy day 1
- A-3 (RTF) - single self-contained analyzer, builds confidence
- A-4 (.ipynb) - strategic Perplexity alignment

**Week 2 (May 4-10):**
- A-1 (OpenDocument) - heaviest reuse from existing DOCX analyzer
- A-2 (macro-enabled OOXML) - extends DOCX/XLSX/PPTX

**Week 3 (May 11-17):**
- A-5 (image family) - biggest visible win for non-technical demos
- A-8 (EPUB) - quick after A-1 lands the ZIP+mimetype pattern

**Week 4 (May 18-24):**
- A-6 (old binary Office) - needs `oletools` integration tested
- A-7 (MSG) - depends on A-6's OLE2 helper

**Week 5 (May 25-31):**
- 42-fixture adversarial gauntlet rerun against v1.2-rc1
- Update `docs/adversarial/REPORT.md` with new fixture scores
- Add 30-50 fixtures across the new formats (publish what we miss)

**Week 6 (June 1-8):**
- Bug fix only. No new features.
- Ship v1.2.0 by June 7. Tag, push, Zenodo DOI mint. Two days reserved for the unforeseen.

**June 9: competition.**

If a week slips: Tier B is intentionally deferred. The competition does not require completeness; it requires deliberate, well-rendered scope.

---

## Constraints for Claude

- **Existing repo conventions:** read `docs/ARCHITECTURE.md`, `docs/RUNBOOK.md`, and existing `analyzers/*.py` before writing. Match the style of `docx_analyzer.py` (the most mature analyzer).
- **Tier discipline:** every new mechanism declares its tier (1 verified / 2 structural / 3 interpretive). The `Munafiq Protocol` is enforced - Tier-1 needs a deterministic test in `tests/`.
- **No em-dashes in user-facing prose** (READMEs, error messages, finding descriptions). Code comments and CSS comments are exempt.
- **Falsifiability:** every Tier-1 finding must be reproducible from a published fixture in `tests/fixtures/`.
- **Honest baseline:** every miss is documented in `docs/adversarial/REPORT.md`. If the new analyzer doesn't catch something we expected it to, that's a fixture in the gauntlet, not silently dropped.
- **Optional dependencies:** anything beyond stdlib + Pillow + pikepdf goes in `pyproject.toml` `[project.optional-dependencies]` so the core install stays under 50MB.
- **Versioning:** v1.2.0 ships once Tier A is in. Tier B items become v1.2.1, v1.2.2, etc.
- **Commit hygiene:** one commit per analyzer + its router changes + its tests + its fixture set. Atomic.

---

## What "done" looks like

1. `bayyinah.dev/` accepts every Tier A extension, returns a real verdict (not `mughlaq`) with at least one positive-fixture test demonstrating real concealment detection.
2. `bayyinah.dev/` accepts every Tier C extension, returns a clean `mughlaq` verdict with the "out of scope by policy" copy.
3. `docs/SCOPE.md` exists and lists every supported and out-of-scope format with rationale.
4. `docs/adversarial/REPORT.md` shows v1.2 vs v1.1.1 fixture scores, with new fixtures for every new analyzer.
5. The landing page substitutes "23 file kinds" with the new honest count. (Probably **~50 file kinds, ~190 mechanisms** if we ship Tier A.)
6. Tag `v1.2.0` cut by June 7, 2026. Two days of buffer.

---

*Bismillah. Let's go.*
