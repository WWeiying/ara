#!/usr/bin/env python3
"""Analyze the pinned distinct-register candidate, not the older split ELF."""
import argparse
import hashlib
import json
from pathlib import Path

from analyze_trace import analyze

ELF_SHA256 = '93ae62518cc49d754850b65d09355e4e6c34f7160b327c20e926411433affb17'
SITES = {
    '3e883457': ('original_slide', 180),
    'c68100d7': ('original_reduce', 192),
    '3e4740d7': ('layout_slide', 192),
    'c6118157': ('layout_reduce', 192),
    '9e803257': ('layout_copy_low', 12),
    '9e903257': ('layout_copy_high', 12),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', type=Path, required=True)
    parser.add_argument('--trace', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    digest = hashlib.sha256(args.elf.read_bytes()).hexdigest()
    if digest != ELF_SHA256:
        parser.error('ELF differs from reviewed instruction-site mapping')
    raw = args.trace.read_bytes()
    raw = raw[:raw.rfind(b'\n') + 1]
    groups = analyze(raw, SITES)
    report = dict(
        source=str(args.trace.resolve()), elf=str(args.elf.resolve()),
        elf_sha256=digest, snapshot_sha256=hashlib.sha256(raw).hexdigest(),
        scope='First K1536 ABBA selected instructions only; not a functional PASS',
        interpretation='Residence times overlap; write bytes include internal VRF work, not DRAM traffic',
        instruction_sites=SITES, groups=groups)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'trace-prefix.csv').write_bytes(raw)
    (args.output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
