#!/usr/bin/env python3
"""Seal the already completed single reference attempt; never execute it."""
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
from scope import HERE, CASES, sha, require

out = HERE/'reference01'
status = json.loads((out/'status.json').read_text())
pins = json.loads((out/'input_pins.json').read_text())
for path, digest in pins.items():
    require(sha(path) == digest, 'Reference input drift: '+path)
require(status['status'] == 'HOST_SPIKE_PASS_NOT_DUT' and status['process_returncode'] == 0,
        'Reference not complete')
require(status['cases'] == [c['id'] for c in CASES] and status['checks'] == 3567,
        'Reference case/check scope differs')
for p in sorted(out.rglob('*')):
    if p.is_file():
        pins[str(p)] = sha(p)
for name in ('scope.py', 'source_manifest.json', 'STATIC_COST.md', 'REFERENCE.md', 'seal_reference.py'):
    pins[str(HERE/name)] = sha(HERE/name)
ready = dict(status='SOURCE_REFERENCE_PASS_PENDING_INDEPENDENT_REVIEW_NOT_DUT',
             cases=status['cases'], case_count=4, pins=pins,
             soc_elf=dict(path=str(out/'soc.elf'), sha256=sha(out/'soc.elf')),
             spike_elf=dict(path=str(out/'spike.elf'), sha256=sha(out/'spike.elf')),
             isa=status['isa'], parsed_spike_records=status['commits'],
             full_output_halfwords_per_case=128, guards_per_case=2,
             memory_bytes_per_case=8192, checks=status['checks'],
             Linux_signalframe_proved=False, VCS_started=False,
             mask_domain=dict(original_array_bytes=128, fixture_array_bytes=16,
                              helper_capacity_elements=64, consumed_mask_bytes=8))
with (HERE/'READY.json').open('x') as stream:
    json.dump(ready, stream, indent=2); stream.write('\n')
print(sha(HERE/'READY.json'))
