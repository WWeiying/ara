#!/usr/bin/env python3
"""Fail-closed entry point for the sealed staging implementation."""
import argparse
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
from stage import HERE, ROOT, atomic_json, hashes
from guard import accepted_inputs, audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to(ROOT / 'verification/out') or out.exists():
        raise ValueError('Fresh independent output required')
    pins = accepted_inputs()
    if hashes(map(Path, pins)) != pins:
        raise ValueError('Accepted inputs drifted before staging')
    subprocess.run([sys.executable, '-B', str(HERE / 'stage.py'), '--output', str(out)], check=True)
    # No downstream consumer may accept the legacy staging report alone.
    atomic_json(out / 'accepted-input-audit.json', audit(out))


if __name__ == '__main__':
    main()
