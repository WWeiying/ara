#!/usr/bin/env python3
"""Bind existing pilot failure evidence; no simulation or acceptance mutation."""
import json
from pathlib import Path
from analyze import HERE, sha, save

d = json.loads((HERE / 'ledger.json').read_text())
w = json.loads((HERE / 'wave_metadata.json').read_text())
root = HERE.parent
ref = root / 'reference03'
case = ref / d['case']
faults = d['fault_handlers']
assert len(faults) == len(d['target_requests']) == 17
assert len(d['index_reload_requests']) == len(d['helpers']) == 1
assert len(d['capture']) == 32 and len(d['replay']) == 8
assert d['complete_initial_capture']
assert d['first_failed_check']['ordinal'] == 160
assert len(d['checks']) == 160
assert all(x['equal'] for x in d['checks'][:-1])
assert not d['controls_directory_exists'] and not d['checkpoints']
assert not d['observer_file_exists']
indices = d['helpers'][0]['indices']
for i, fault in enumerate(faults):
    csr = fault['csr']
    assert csr['vstart'] == i and csr['mepc'] == 0x80000d64
    assert (csr['mcause'], csr['vl'], csr['vtype'], csr['fcsr'], csr['vcsr']) == (13, 32, 17, 117, 5)
    if i < 16:
        assert csr['mtval'] == 0x40000000 + indices[i]
        assert fault['pte_writes'] and fault['mret']
    else:
        assert not fault['pte_writes'] and not fault.get('mret')
bad = faults[-1]['csr']['mtval']
assert bad - 0x40000000 == (indices[17] << 32) | indices[16]
assert w['scale'] == '100fs' and w['maximum_ns'] == 370949.5
assert w['conversion']['returncode'] == 0
pins = dict(d['evidence_pins'])
for path in pins:
    assert sha(Path(path)) == pins[path], path
additional = [HERE / name for name in ('ledger.json', 'wave_header.py', 'wave_metadata.json',
              'fsdb_summary.log', 'conversion.log', 'compact.vcd', 'README.md', 'finalize.py')]
additional += [ref / name for name in ('original.S', 'identities.json', 'fixture.S', 'pins.json')]
additional += [case / name for name in ('original.elf', 'soc.elf')]
for path in additional:
    pins[str(path)] = sha(path)
private = next(Path(p) for p in pins if p.endswith('/input.elf'))
assert sha(private) == sha(case / 'soc.elf')
result = dict(
    status=d['status'], case=d['case'], attempt_zero_based=16,
    target_pc='0x80000d64', opcode='0645f207',
    target_cvx=d['target_requests'][-1], csr=faults[-1]['csr'],
    csr_reads=faults[-1]['csr_reads'], first_failed_check=d['first_failed_check'],
    diagnostic=d['diagnostics'][0], expected_tval='0x40017000',
    actual_tval=hex(bad), source_indices_16_17=[hex(indices[16]), hex(indices[17])],
    data_clue='actual_tval - VA == (indices[17] << 32) | indices[16]',
    rtl_root_cause_proven=False,
    counts=dict(target_cvx_requests=17, exception_responses=17, correct_fault_repairs=16,
                index_prologues=1, initial_capture_events=32, logged_replay_events=8,
                completed_rounds=0, controls_run=0),
    firmware_mismatch_not_checker_rejection=True,
    profile_temporal_miss=False, wave=w,
    pins_rechecked=True, evidence_pins=pins,
    scope='Observed failed pilot only; no round, full-program, control, or Linux acceptance.',
    no_simulation_rerun=True, no_rtl_or_sealed_input_changes=True,
)
save(HERE / 'first_error.json', result)
print(json.dumps(dict(status=result['status'], pins=len(pins),
                     output=str(HERE / 'first_error.json')), indent=2))
