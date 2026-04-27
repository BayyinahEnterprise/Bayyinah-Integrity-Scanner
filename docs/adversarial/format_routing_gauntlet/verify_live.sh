#!/usr/bin/env bash
# Day 1 live-curl verification gate (v1.1.2 prompt section 3.2).
#
# Runs after deploying v1.1.2 to bayyinah.dev. All three commands
# below must return `true` for Day 1 to be considered complete and
# Day 2 (PDF) to begin. From the prompt:
#
#   "All three must return `true`. If any return `false`, Day 1 is
#    not complete and Day 2 does not begin."
#
# Cannot run from the build sandbox - bayyinah.dev is the live
# Cloudflare-fronted Railway deployment, and the v1.1.2 code in
# this branch has not been pushed yet. Run this on the deploy
# machine after `git push` and Railway rolls v1.1.2 forward.

set -euo pipefail

GAUNTLET="docs/adversarial/format_routing_gauntlet/fixtures"

echo "v1.1.2 Day 1 live-curl gate -> https://bayyinah.dev/scan"
echo "================================================================"

echo
echo "V1: polyglot must return mughlaq with Tier 0 finding"
v1=$(curl -s https://bayyinah.dev/scan \
        -F "file=@$GAUNTLET/01_polyglot.docx" \
     | jq -e '.verdict == "mughlaq" and (.findings | any(.tier == 0))')
echo "  result: $v1"

echo
echo "V2: PDF-as-txt must return mughlaq with Tier 0 finding"
v2=$(curl -s https://bayyinah.dev/scan \
        -F "file=@$GAUNTLET/02_pdf_as_txt.txt" \
     | jq -e '.verdict == "mughlaq" and (.findings | any(.tier == 0))')
echo "  result: $v2"

echo
echo "V5: 4-byte text must return mughlaq (not sahih)"
printf 'aaaa' > /tmp/v5.txt
v5=$(curl -s https://bayyinah.dev/scan \
        -F "file=@/tmp/v5.txt" \
     | jq -e '.verdict == "mughlaq"')
echo "  result: $v5"
rm -f /tmp/v5.txt

echo
echo "================================================================"
if [[ "$v1" == "true" && "$v2" == "true" && "$v5" == "true" ]]; then
    echo "  ALL PASS - Day 1 complete; Day 2 (PDF) may begin."
    exit 0
else
    echo "  AT LEAST ONE FAIL - Day 1 NOT complete."
    echo "  v1=$v1  v2=$v2  v5=$v5"
    exit 1
fi
