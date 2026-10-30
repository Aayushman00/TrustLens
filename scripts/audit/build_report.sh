#!/usr/bin/env bash
# Build report/main.pdf without a host TeX install: Docker texlive-medium + CTAN titlesec, in a scratch copy.
# `multirow` is declared in main.tex but unused, and absent from the image, so the scratch copy drops it.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; B="$(mktemp -d)"
cp -r "$ROOT/report/main.tex" "$ROOT/report/chapters" "$ROOT/report/figures" "$ROOT/report/prompts" "$B/"
sed -i 's/multirow,//' "$B/main.tex"
curl -sSL -o "$B/t.zip" https://mirrors.ctan.org/macros/latex/contrib/titlesec.zip
(cd "$B" && unzip -oq t.zip && cp titlesec/*.sty .)
MSYS_NO_PATHCONV=1 docker run --rm -v "$(cd "$B" && pwd -W 2>/dev/null || pwd):/w" -w /w texlive/texlive:latest-medium \
  sh -c 'for i in 1 2 3 4; do pdflatex -interaction=nonstopmode main.tex >/dev/null 2>&1 || true; done'
grep -n "^!" "$B/main.log" || true
echo "undefined refs: $(grep -c undefined "$B/main.log" || true)"; grep -n "Overfull" "$B/main.log" || true
cp "$B/main.pdf" "$ROOT/report/main.pdf"; echo "built: $ROOT/report/main.pdf (scratch: $B)"
