# Vendored test fonts

This directory holds fonts vendored into the repository so that
fixture builds are deterministic across hosts. These fonts are used
only by the test fixture builder (`tests/make_test_documents.py`)
and never by the production scanner.

## LiberationSans-Regular.ttf

- Project: Liberation Fonts (Red Hat, Inc., with digitized data
  contributions from Google, Inc.).
- Upstream: https://github.com/liberationfonts/liberation-fonts
- License: SIL Open Font License, Version 1.1
  (see `OFL.txt` in this directory).
- Trademark: "Liberation" is a trademark of Red Hat, Inc.
  This vendored copy is used unmodified, retains the original
  font name as required by the OFL, and is bundled solely for
  reproducible test fixture generation.

## Why vendored

`tests/make_test_documents.build_text_homoglyph` renders a Cyrillic
lookalike character (U+0430) so the homoglyph and tounicode_anomaly
detectors can both fire on the same fixture. Whether the second
signal survives into the as-built PDF depends on whether the chosen
TTF embeds a /ToUnicode CMap. System fonts vary by host. Vendoring
LiberationSans-Regular.ttf removes that variance and lets the test
suite enforce both detector firings on every machine.

The Liberation Sans font carries Cyrillic coverage, embeds a
/ToUnicode CMap when used through pymupdf, and ships under the SIL
OFL which permits redistribution alongside this repository.

## Production scanner unaffected

This font is loaded only during fixture generation. Running
`bayyinah` against user PDFs never touches this directory.
