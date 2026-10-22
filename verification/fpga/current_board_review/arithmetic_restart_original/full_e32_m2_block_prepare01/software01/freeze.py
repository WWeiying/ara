#!/usr/bin/env python3
"""One exclusive finalized source manifest, before independent review."""
import sys
sys.dont_write_bytecode=True
import generate as g
import json
old=json.loads((g.HERE/'source_manifest.json').read_text())
pins={p:h for p,h in old['pins'].items() if not g.Path(p).is_relative_to(g.HERE)}
for p,h in pins.items():g.require(g.sha(p)==h,'Prior source drift '+p)
for p in g.HERE.rglob('*'):
    if p.is_file():pins[str(p)]=g.sha(p)
g.save(g.HERE/'SOURCE_FREEZE.json',dict(status='SOURCE_FROZEN_PENDING_INDEPENDENT_REVIEW',pins=pins,scope=old['scope']))
print(g.sha(g.HERE/'SOURCE_FREEZE.json'))
