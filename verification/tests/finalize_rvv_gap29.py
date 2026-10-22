#!/usr/bin/env python3
"""Publish aggregate-compatible READY after checking every preparation pin."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
prepared = HERE / 'rvv_gap29_prepared.json'
record = json.loads(prepared.read_text())
for filename, digest in record['files'].items():
    if hashlib.sha256(Path(filename).read_bytes()).hexdigest() != digest:
        raise SystemExit('pin drift: ' + filename)
record['status'] = 'READY'
record['spike_results'] = next(p for p in record['files'] if p.endswith('/spike_results.json'))
for path in (prepared, Path(__file__).resolve(), HERE / 'RVV_GAP29.md'):
    record['files'][str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
target = HERE / 'rvv_gap29_ready.json'
with target.open('x') as stream:
    json.dump(record, stream, indent=2)
    stream.write('\n')
print(target)
print(hashlib.sha256(target.read_bytes()).hexdigest())
