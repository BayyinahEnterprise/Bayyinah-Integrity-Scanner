# EML Adversarial Gauntlet — v1.1.1 Baseline

**Date:** 2026-04-26
**Scanner version:** Bayyinah 1.1.1 (live at https://bayyinah.dev)
**Result:** 0 of 6 techniques caught.

The EML gauntlet was constructed deliberately around the v1.1.1 detectors. `EmlAnalyzer` already catches display-name spoofing on From/Sender/Reply-To, encoded-word concealment in headers, smuggled duplicate single-instance headers, multipart/alternative divergence, hidden HTML content, executable / macro attachments, nested rfc822 messages, external resource references, and MIME boundary anomalies. The six fixtures here probe header-relationship and body-encoding gaps the analyzer does not yet cover.

## Summary table

| Fixture | Technique | Result | Mechanism that should have caught it | Score |
|---|---|---|---|---|
| 01 | From and Reply-To real-domain divergence | **MISSED** | (`eml_replyto_domain_divergence` not implemented) | 1.00 |
| 02 | Return-Path / From divergence | **MISSED** | (`eml_returnpath_divergence` not implemented) | 1.00 |
| 03 | Received-chain last hop disjoint from From | **MISSED** | (`eml_received_chain_anomaly` not implemented) | 1.00 |
| 04 | Base64 plaintext body containing payload | **MISSED** | (`eml_body_payload_divergence` not implemented) | 1.00 |
| 05 | Folded continuation header carrying payload | **MISSED** | (`eml_header_continuation_payload` not implemented) | 1.00 |
| 06 | Long X-* custom header with payload | **MISSED** | (`eml_unknown_header_payload` not implemented) | 1.00 |

**Hit rate: 0/6. Local and live agree exactly.**

## What `EmlAnalyzer` v1.1.1 already catches (out of scope)

- Display-name spoof on From / Sender / Reply-To (display name implies a different domain than the address)
- Encoded-word anomalies in headers (`=?utf-8?B?...?=` carrying zahir-concealment codepoints)
- Smuggled duplicate single-instance headers (e.g., two `From:` headers)
- Multipart/alternative divergence (text and HTML parts disagree)
- Hidden HTML content in body parts (mirrors HtmlAnalyzer detectors)
- Executable / macro attachments (`.exe`, `.scr`, `.docm`, `.xlsm`, etc.)
- Nested rfc822 messages
- External resource references in HTML body
- MIME boundary anomalies

The misses below are orthogonal to all of the above.

## Per-fixture root cause

### 01 — From / Reply-To real-domain divergence — MISSED

The display-name spoof check fires only when the *display name* implies a domain different from the actual address. Here both From (`billing@trusted-vendor.example`) and Reply-To (`wire-transfer@attacker-controlled.example`) have no display names — just two different real domains in two different addresses. The recipient who clicks Reply lands at the attacker's domain.

**Fix path for v1.1.2:** Add `_check_replyto_domain_divergence`. Compare `_domain_of(From)` against `_domain_of(Reply-To)` whenever both are present. Emit `eml_replyto_domain_divergence` (Tier 1, confidence 0.95) when they differ AND From is not a known mailing-list shape. ~25 lines.

### 02 — Return-Path / From divergence — MISSED

Return-Path is set by the receiving MTA from the SMTP `MAIL FROM` envelope. A divergence between Return-Path and From is the canonical sign of envelope-vs-header mismatch — the technique behind classic sender-spoof phishing.

**Fix path for v1.1.2:** Add `_check_returnpath_divergence`. Compare `_domain_of(Return-Path)` against `_domain_of(From)`. Emit `eml_returnpath_divergence` (Tier 1, confidence 0.9). Honor common legitimate divergences (mailing-list rewrites, ESP envelope domains) via an allowlist. ~30 lines.

### 03 — Received chain anomaly — MISSED

The Received chain documents every relay hop. A genuine email from `vendor.example` typically shows the vendor's outbound MTA in the chain. Here the last hop is `relay.attacker.example` while From claims `vendor.example` — a real attacker injecting through a different relay than the claimed sender.

**Fix path for v1.1.2:** Add `_check_received_chain_anomaly`. Parse Received headers in order, extract the outbound-relay hostname / IP, compare against From's domain. Emit `eml_received_chain_anomaly` (Tier 2, confidence 0.7) when the last hop's domain shares no suffix with From's. Tier 2 because legitimate ESP routing breaks this naively; Tier 1 escalation requires SPF/DKIM context which is beyond pure-content scanning. ~50 lines.

### 04 — Base64 plaintext body payload — MISSED

The body is base64-encoded text/plain. EmlAnalyzer reads the decoded body for HTML hidden-text checks but does not run a *corpus-divergence / payload* check on the decoded plaintext body. An attacker who hides a long payload inside a base64-encoded plaintext block — visible in any mail client that decodes the body, but not part of the typical security review surface — escapes detection.

This is the email analogue of the PDF gauntlet's after-EOF technique: the payload is in the file, accessible to any consumer, just not in the place the analyzer looked.

**Fix path for v1.1.2:** Add `_scan_decoded_body_for_concealment`. After decoding, check the body length and run the per-codepoint concealment scans (zero-width / TAG / bidi / homoglyph). Add a `body_length_anomaly` check that flags bodies whose decoded length is much larger than the rendered length when an HTML alternative exists. ~35 lines.

### 05 — Header continuation smuggling — MISSED

RFC 5322 allows header values to be folded across multiple lines via CRLF + whitespace continuation. A header value that spans many continuation lines and contains a long natural-language payload is invisible to most mail UIs (which show the first line only) and uninspected by EmlAnalyzer.

**Fix path for v1.1.2:** Add `_check_header_continuation_payload`. For every header whose value, after unfolding, exceeds a length threshold and contains natural-language patterns, emit `eml_header_continuation_payload` (Tier 2). ~25 lines.

### 06 — Long X-* custom header payload — MISSED

EmlAnalyzer iterates a fixed allowlist of headers (From, Sender, Reply-To, Subject, To, Cc) and ignores the rest. An attacker who parks a long natural-language payload in `X-Originating-Note` or any custom header passes through cleanly. Real-world abuse shapes include `X-Spam-Status` and `X-Originating-IP` historically.

**Fix path for v1.1.2:** Add `_check_unknown_header_payload`. Iterate every header not in the recognised set. Emit `eml_unknown_header_payload` (Tier 2) when any single header's value exceeds a length threshold and contains natural-language patterns. ~20 lines.

## What this baseline says about Bayyinah v1.1.1 for EML

`EmlAnalyzer` v1.1.1 has strong coverage of the *attachment* and *body* surfaces (the obvious attack channels) and the *encoded-word header* concealment surface. It is largely uncovered on the *header-relationship* surface (cross-header consistency: Return-Path vs From, From vs Reply-To, Received chain vs From) and on the *encoded-body* / *unknown-header* concealment surfaces. The gap is structurally similar to the HTML analyzer's gap: format-specific channels that the analyzer's main loop chooses not to visit.

A real BEC (business email compromise) attacker constructs precisely these shapes — a Return-Path divergence on a wire-transfer email is the BEC textbook page 1.

## v1.1.2 milestone (EML additions)

Six new EML detectors estimated at ~185 LOC total:

1. `eml_replyto_domain_divergence` — From vs Reply-To domain comparison
2. `eml_returnpath_divergence` — Return-Path vs From domain comparison
3. `eml_received_chain_anomaly` — last-hop vs From domain comparison
4. `eml_body_payload_divergence` + `eml_decoded_body_concealment` — decoded-body checks
5. `eml_header_continuation_payload` — long-folded header detection
6. `eml_unknown_header_payload` — long custom header detection

Combined running totals: PDF (~155 LOC), DOCX (~200 LOC), XLSX (~190 LOC), HTML (~120 LOC), EML (~185 LOC) = ~850 LOC across five formats.

## Reproducing this report

```bash
cd Bayyinah-Integrity-Scanner/docs/adversarial/eml_gauntlet
python build_fixtures.py     # creates fixtures/*.eml (no extra deps)
python run_gauntlet.py local # in-process scan via ScanService
python run_gauntlet.py live  # POST to https://bayyinah.dev/scan
```

---

*Fifth installment of the multi-format gauntlet. PDF (2/6) → DOCX (0/6) → XLSX (0/6) → HTML (0/6) → EML (0/6 against gap-targeted fixtures). Image and CSV/JSON gauntlets follow.*
