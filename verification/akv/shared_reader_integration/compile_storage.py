#!/usr/bin/env python3
"""Type-check the new storage snapshot, then reuse the sealed VLSU compiler."""
import argparse
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from prepare_storage import validate_snapshot
import compile as original


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--snapshot", type=Path, required=True)
    args, _ = parser.parse_known_args()
    validate_snapshot(args.snapshot.resolve(strict=True))
    original.main()
