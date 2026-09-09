#!/usr/bin/env python3
"""Check the immutable exported files; build/reports/output files are ignored."""
import hashlib
from pathlib import Path
import sys

root = Path(__file__).resolve().parent.parent
errors = []
rows = (root / "SHA256SUMS").read_text().splitlines()
for row in rows:
    digest, name = row.split("  ", 1)
    path = root / name
    if not path.is_file():
        errors.append("Missing: " + name)
    elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        errors.append("Changed: " + name)
if errors:
    print("\n".join(errors))
    sys.exit(1)
print(f"PASS: {len(rows)} exported files match SHA256SUMS")
