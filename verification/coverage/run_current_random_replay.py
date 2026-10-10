#!/usr/bin/env python3
"""Prepare and replay the fixed old-image random corpus without simulations."""
import argparse
import json
from pathlib import Path
import time

import current_random_trace_replay as replay


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=201)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    started = time.time()
    print(json.dumps(dict(phase="PREPARING", tests=args.limit,
                          workers=args.workers, simulations_started=False)), flush=True)
    prepared = replay.prepare(args.output, limit=args.limit, timeout_s=180)
    print(json.dumps(prepared), flush=True)
    result = replay.check(args.output, prepared["manifest_sha256"],
                          workers=args.workers, timeout_s=180)
    print(json.dumps(dict(result, elapsed_s=round(time.time()-started, 2))), flush=True)
    return int(result["failed"] != 0)


if __name__ == "__main__":
    raise SystemExit(main())
