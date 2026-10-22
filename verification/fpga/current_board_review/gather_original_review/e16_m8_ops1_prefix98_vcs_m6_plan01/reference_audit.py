#!/usr/bin/env python3
"""Finish the offline reference audit without changing the prepared reference."""
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REF = HERE.parent / 'e16_m8_ops1_prefix98_prepare01'
sys.path.insert(0, str(REF))
import reference_check as ref
sys.path.insert(0, str(HERE.parent))
import prepare_batch as base
import prepare_stall_prefix2 as old
sys.path.insert(0, str(base.INTEGRATION))
from prepare import adapt

read = lambda p: json.loads(p.read_text())


def audit():
    baseline = read(REF / 'baseline_pins.json')
    for p, h in baseline.items():
        ref.require(base.sha(Path(p)) == h, 'Reference baseline drift: ' + p)
    proof = read(REF / 'source_elf_proof.json')
    original = REF / 'prepared' / ref.NAME / 'original'
    ref.require((original.parent / 'case.c').read_text() == old.prefix(
        adapt((original / 'scenario.c').read_text(), ref.NAME), 98), 'Source adaptation drift')
    for key, file in (('original_c_sha256', 'scenario.c'),
                      ('original_linux_elf_sha256', 'original_linux.elf')):
        ref.require(base.sha(original / file) == proof[key], 'Original identity drift')
    for backend in ('soc', 'spike'):
        elf = proof[backend + '_elf']
        ref.require(base.sha(Path(elf['path'])) == elf['sha256'], 'ELF drift')
        routine = ref.instructions(Path(elf['path']), ref.NAME + '_op_1')
        ref.require(routine == proof[backend + '_routine'] and
                    [r['insn'] for r in routine] == [r['insn'] for r in proof['original_routine']],
                    'Original 13 instructions differ')
    model = ref.model()
    ref.require(model == read(REF / 'host_expected.json'), 'Reference model drift')
    host = read(REF / 'host/host_gate.json')
    ref.require(len(host['tests']) == 8 and all(t['status'] == 'PASS' and
        base.sha(REF / 'host' / (t['injection'] + '.log')) == t['log_sha256']
        for t in host['tests']), 'Host8 gate/log drift')
    recorded = read(REF / 'reference/reference.json')
    raw = ref.audit_trace(REF / 'reference/commits.log', Path(proof['spike_elf']['path']), model)
    ref.require(all(recorded[k] == v for k, v in raw.items()) and recorded['returncode'] == 0 and
        recorded['elapsed_s'] < 120 and base.sha(REF / 'reference/commits.log') == recorded['commit_sha256'],
        'Raw reference/exit/pin differs')
    negatives = []
    for name, reason in (('wrong_halfword', 'Output mismatch'), ('target_encoding', '13asm order/encoding'),
                        ('nonzero_vstart', 'vstart did not reset'),
                        ('missing_source_bytes', 'Missing initialized source bytes'),
                        ('missing_oracle', 'Incomplete calls/asm/oracle/exit')):
        path = REF / 'audit01' / (name + '.trace')
        try:
            ref.audit_trace(path, Path(proof['spike_elf']['path']), model)
        except ValueError as error:
            ref.require(reason in str(error), 'Unexpected negative rejection: ' + str(error))
            negatives.append(dict(name=name, reason=str(error), sha256=base.sha(path)))
        else:
            raise ValueError('Negative accepted: ' + name)
    return dict(status='PASS_REFERENCE_RAW98_NOT_DUT', calls=98, fullcap=50176, guards=196,
        asm_counts=[98]*13, returned_vstart_zero=98, setup_values_per_call=2178,
        retired=raw['firmware_retired_to_htif_store'], spike_elapsed_s=recorded['elapsed_s'],
        negative_results=negatives, old_audit01_preserved=True,
        old_audit01_error='Negative EOF correctly rejected; expected-message assertion was too specific.',
        exact_historical_stopped_tuple=None, full_child_acceptance=False, vcs_started=False)


if __name__ == '__main__':
    out = HERE / 'reference_audit02.json'
    ref.require(not out.exists(), 'Fresh audit only')
    result = audit()
    result['auditor_sha256'] = base.sha(Path(__file__))
    result['reference_pins'] = {str(p): base.sha(p) for p in sorted(REF.rglob('*'))
                              if p.is_file() and '__pycache__' not in p.parts}
    base.save(out, result)
    print(result['status'], result['retired'], flush=True)
