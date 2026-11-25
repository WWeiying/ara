#!/usr/bin/env python3
"""Wrap immutable existing run plans with an explicit campaign scope."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--scope', required=True)
    a = p.parse_args()
    data = json.loads(a.input.read_text())
    if not data['cases'] or a.output.exists():
        raise ValueError('Cases and new output required')
    data.update(scope=a.scope, original_manifest=str(a.input.resolve()),
                original_manifest_sha256=hashlib.sha256(a.input.read_bytes()).hexdigest())
    with a.output.open('x') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')


if __name__ == '__main__':
    main()
