# Landing Mock v2: Light Through The Page

Original visual identity for `bayyinah.dev`. Single-file static prototype, no build step.

## Why a v2

The v1 mock (`docs/landing-mock/`) was a fast study. It picked up tokens, type, and motion directly from Fraz's reference sites (`settletsp.com`, `eidolonlab.dev`, `elcaminoislam.com`) so we could move quickly and ship something coherent. That choice was honest about its lineage but it left the brand visually downstream of someone else's work.

This v2 stops borrowing. It takes the metaphor that has always been at the core of the product (surface vs. substrate, the seen vs. the concealed) and makes the page *behave* like that idea instead of describing it. The result is a visual language that belongs to Bayyinah and would not transplant cleanly onto any of the three reference sites.

## The core metaphor

A page held up to a lamp.

When light passes through translucent paper, the ink on the back becomes visible from the front, mirrored. That single physical fact is the entire concept. Bayyinah is the act of holding the file up to the lamp and reading what is on both sides.

The hero shows one document. The "surface" layer is the sanitized story (`$1,000`, "revenue grew 8% YoY"). The "substrate" layer underneath bleeds through during the lamp cycle, mirrored ink showing the real payload (`$10,000`, `HIDDEN_TEXT_PAYLOAD: actual revenue`). It is not a comparison of two files. It is two readings of the same file. That is the product.

## What is original here

- Transmission imaging metaphor (lamp + vellum + mirrored substrate). Not a particle field, not concentric rings, not a dashboard.
- Lab-notebook layout. Sticky 200px left margin index carries case file metadata (CASE / DATE / SCANS / CORPUS), a §-numbered TOC, and a bottom signature. The main column never exceeds 760px, like a single page in a binder.
- Color palette built from physical materials: dark room (`#0F1115`), warm vellum (`#E8E4D8`), raking lamp light (`#F4D58A`), terracotta evidence ink (`#E2725B`). Deliberately not the Settle slate palette.
- Type stack: Instrument Serif display, Inter body, JetBrains Mono data. Deliberately not Fraunces / Inter Tight / IBM Plex Mono.
- Hand-tuned easing `cubic-bezier(0.32, 0.72, 0.24, 1.0)` over an 8-second cycle. Slow enough to feel like patient examination, not a hover effect.
- Etymology footer in place of a Bismillah card. `bayyinah · noun · arabic · بَيِّنَة` defined as clear evidence; that which makes the truth manifest. The signature reads "A scanner is only as honest as the misses it publishes."

## Sections

1. **§ 01 Premise.** The lit-page hero. One document, two readings.
2. **§ 02 Examination.** Three real fixtures (clean PDF / adversarial PDF / encrypted PDF) on the same lit-page surface. Three buttons, three pre-recorded examinations. The simulator and the hero are the same component playing different roles.
3. **§ 03 Three Facts.** ẓāhir, bāṭin, bayyinah defined in three columns.
4. **§ 04 Why Now.** Four-prerequisite convergence (transformer attention 2022, content-anomaly forensics 2023, FinCEN beneficial-ownership 2024, regulatory enforcement 2026). The 2026 row is rendered in lamp gradient.
5. **§ 05 Honest Baseline.** The 42-fixture adversarial table from `docs/adversarial/REPORT.md`. Hits, misses, and the unflattering totals (2 caught / 2 partial / 38 missed at v1.1.1) are on screen.
6. **§ 06 Scan.** Drop-zone CTA. Stateless, no telemetry beyond Cloudflare access logs.

## Honest numbers (verified from the codebase)

- **23 file kinds.** `infrastructure/file_router.py::FileKind`.
- **106 detection mechanisms.** `grep -rohE 'mechanism\s*=\s*["\x27][a-z_]+["\x27]' analyzers/ application/ domain/ | sort -u | wc -l`.
- **42 adversarial fixtures, 2 caught / 2 partial / 38 missed at v1.1.1.** From `docs/adversarial/REPORT.md` at commit `ccd7c3e`.

These appear in the `.stats` band under the hero and again in § 05.

## How to run locally

```
cd docs/landing-mock-v2
python3 -m http.server 8766
# open http://localhost:8766/
```

Lamp cycle is 8 seconds. The substrate hits peak opacity around the 4-second mark. That is the screenshot moment.

## Accessibility and motion

- Respects `prefers-reduced-motion: reduce`. Substrate falls back to a low static opacity (0.18). Lamp glow softens. No animation loops.
- All examination fixtures are keyboard-reachable via the tab buttons. The verdict bar updates `aria-live="polite"`.
- Mobile breakpoint at 880px collapses the margin index into a top strip and the lab-notebook becomes single-column. Tested at 390px.

## Status

Not yet promoted to the `/` route on `bayyinah.dev`. Lives at `docs/landing-mock-v2/index.html` alongside v1 so Fraz can pick the design we ship, or roast both.

## Files

- `index.html`. Full mock, single file (~38 KB, no build step, no external runtime JS).
- `README.md`. This document.

## Trail

- v1 mock committed in `7eb133a` (Settle-leaning tokens; called out as borrowed).
- CSV/JSON gauntlet baseline committed in `ccd7c3e` (the 42-fixture corpus this page reports against).
- v2 mock committed in this change.
