# Bayyinah Landing Mock — for Fraz Review

This is a static prototype of a redesigned `bayyinah.dev` landing page, built in the visual language of [settletsp.com](https://settletsp.com), [eidolonlab.dev](https://eidolonlab.dev), and [elcaminoislam.com](https://elcaminoislam.com).

Single file, vanilla HTML/CSS/JS, no build step. Open `index.html` in any browser.

## What's here

A six-section landing page:

1. **Hero — Split Document** — a single visual that animates the surface/substrate inversion. `$1,000` (what the LLM reads) cycles to reveal `$10,000` and the hidden payload underneath. The visualization IS the pitch.
2. **Live simulator** — three pre-recorded scan results (Clean PDF, Adversarial PDF, Encrypted PDF). Click, watch findings drop in, see the verdict in Arabic (ṣaḥīḥ / mukhfī / mushtabih). No file upload, no friction.
3. **How it works** — three columns: ẓāhir, bāṭin, the gap.
4. **Why this couldn't exist five years ago** — five-row convergence timeline (2022 → 2026). Pure narrative copy; no library or framework.
5. **Honest baseline** — table of v1.1.1 gauntlet results, links directly to the published 42-fixture corpus.
6. **Scan a file** — entry to the real `/scan` endpoint, restyled.

## Visual tokens used

Borrowed deliberately from Settle:
- Paper palette: `#F4F0E6` background, `#FBF8F1` cards, `#0C0A07` ink
- Type stack: Fraunces (display), Inter Tight (body), IBM Plex Mono (data)
- Status colors: ok `#1F7A55`, info `#245D7A`, warn `#8A5A12`, err `#A5322A`
- Easing: `cubic-bezier(0.4, 0, 0.2, 1)` and `cubic-bezier(0.16, 1, 0.3, 1)`

Adapted to Bayyinah:
- Tier 1 / 2 / 3 mapped to err / info / warn
- Verdict states named in Arabic transliteration (ṣaḥīḥ, mushtabih, mukhfī) per the project's diagnostic vocabulary
- Footer reads `Bismillāhir-Raḥmānir-Raḥīm` in El Camino's voice

## What it does NOT do

This is a static mock, not a wired-up product:

- The simulator replays pre-recorded JSON, it does not call the live `/scan` API
- The scan box is a link to existing `bayyinah.dev/scan`, not a working drop zone in the mock
- No router, no build, no JS framework

These are deliberate. The point is to put a screenshot-quality landing in front of Fraz before any production code changes. If approved, the next step wires the simulator to actual `/scan` responses recorded from the v1.1.1 endpoint, and replaces the current `/` template.

## Running locally

```bash
cd docs/landing-mock
python3 -m http.server 8765
# open http://localhost:8765
```

Reduced-motion is respected. Mobile breakpoint at 720px.

## Honesty checks

- The "106 detection mechanisms" stat counts distinct `mechanism="..."` literals in `analyzers/`, `application/`, `domain/`. Reproduce: `grep -rohE 'mechanism\s*=\s*["\x27][a-z_]+["\x27]' analyzers/ application/ domain/ | sed -E 's/.*["\x27]([a-z_]+)["\x27]/\1/' | sort -u | wc -l`.
- The "23 file kinds" stat is from `infrastructure/file_router.py::FileKind`.
- The "42 fixtures" / "2 caught / 2 partial / 38 missed" numbers are from `docs/adversarial/REPORT.md` (the v1.1.1 honest baseline shipped in commit `ccd7c3e`).
- The Greenblatt 2024 citation is the alignment-faking paper.
- All other claims are verifiable from the code at the linked HEAD.

If any of these is wrong, the site is wrong.

## Next steps (after Fraz review)

1. Apply Fraz's targeted feedback as edits to `index.html` here
2. Wire the simulator to actual `/scan` responses (replace the inlined `FIXTURES` JSON with real recorded scans of three known fixtures)
3. Replace the current root template with this layout
4. Add as a new route or behind a feature flag for safe rollback

— Bilal
