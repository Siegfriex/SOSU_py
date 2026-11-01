#!/usr/bin/env bash
# Reproducible per-page text extraction of the owner's guidebook PDF.
# Raw text goes to a SCRATCH dir (never into the repo: it is proprietary content).
# Only per-page character counts (metadata) are written into the repo.
# Usage: extract_text.sh <path-to-전자본_소수.pdf> <scratch_out_dir> [render_pages...]
set -euo pipefail
PDF="$1"; OUT="$2"; shift 2
EXPECTED=957e8dc0b6eb66d2f073b778905f7f14df76958726cb91f8406c8baa8c822cb3  # 전자본_소수.pdf (2026-11-02)
HERE="$(cd "$(dirname "$0")" && pwd)"
actual=$(sha256sum "$PDF" | cut -d' ' -f1)
[ "$actual" = "$EXPECTED" ] || { echo "sha256 mismatch: $actual" >&2; exit 1; }
mkdir -p "$OUT/text"
N=$(pdfinfo "$PDF" 2>/dev/null | awk '/^Pages:/{print $2}'); N=${N:-45}
echo "{" > "$HERE/page_chars.json"
for i in $(seq 1 "$N"); do
  f="$OUT/text/p$(printf %02d "$i").txt"
  pdftotext -layout -f "$i" -l "$i" "$PDF" "$f"
  c=$(tr -d '[:space:]' < "$f" | wc -m)
  sep=","; [ "$i" = "$N" ] && sep=""
  echo "  \"$i\": $c$sep" >> "$HERE/page_chars.json"
done
echo "}" >> "$HERE/page_chars.json"
# optional page renders for image review (e.g. 14 23 29 31)
for p in "$@"; do pdftoppm -f "$p" -l "$p" -r 60 -png "$PDF" "$OUT/img_p$p"; done
echo "extracted $N pages to $OUT/text; counts -> $HERE/page_chars.json"
