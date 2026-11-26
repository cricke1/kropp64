#!/usr/bin/env python3
"""Räknar tecknen i varje kodblock i docs/BIDRAG-FINAL.md mot formulärets gränser."""
import re, sys
from pathlib import Path
s = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).with_name("BIDRAG-FINAL.md")).read_text()
for rubrik, gräns, text in re.findall(r"^## (.+?) \(max (\d+)\)\n\n```text\n(.*?)\n```", s, re.S | re.M):
    n = len(text.strip())
    print(f"{'OK ' if n <= int(gräns) else 'FÖR LÅNG'} {n:5d} / {gräns:>4}  {rubrik}")
