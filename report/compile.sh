#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "=== Pass 1: pdflatex ==="
pdflatex -interaction=nonstopmode ecosynth_report.tex

echo "=== BibTeX ==="
bibtex ecosynth_report

echo "=== Pass 2: pdflatex ==="
pdflatex -interaction=nonstopmode ecosynth_report.tex

echo "=== Pass 3: pdflatex (resolve refs) ==="
pdflatex -interaction=nonstopmode ecosynth_report.tex

echo "=== Done ==="
ls -lh ecosynth_report.pdf
