"""Prepare historical714 plus GAP100 candidate; never publish an admission."""
import argparse
import json
from pathlib import Path

import audit_gap100_trap_ledger as ledger
import coverage_bitmap_delta as bitmap

runner, runtime, require = ledger.runner, ledger.runtime, ledger.require
life, OUT = runner.life, ledger.OUT
BASE = OUT / 'closure92-offline-admitted-714-20261006-01'
BASE_SEAL = '94d9714d5b68a6196e61022e517d63ddff58d7d527cffcbcc5c26cae89a94ea8'
LEDGER = OUT / 'gap100-exact-trap-ledger-714-20261006-02.json'
LEDGER_SEAL = 'f52ccbe5b54702d6359c2d7a46d5d5e7e3dd937d45aadfceae231a300872fa63'
IDENTITIES = OUT / 'closure92-offline-five-manifest708-20261006-01.json'


def save(path, value):
    with path.open('x') as stream:
        stream.write(value if isinstance(value, str) else json.dumps(value, indent=2) + '\n')


def verify_ledger(actual, proof):
    serialized = json.loads(json.dumps(actual))
    require(all(serialized[k] == proof[k] for k in serialized),
            'Saved/independently rebuilt trap ledger differs')


def validate_runtime(checks):
    contract = checks['contract']
    require(checks['scalar_comparison_qualified'] is True and
            contract['status'] == 'EXACT_ZERO_CVX_CONTRACT' and
            set(contract['counts']) == {'requests', 'responses', 'exceptions', 'mmu_request_cycles',
                                       'protocol_errors', 'outstanding', 'req_stalled', 'resp_stalled'} and
            all(v == 0 for v in contract['counts'].values()) and
            contract['shared_checker_activity_requirements_only_inapplicable'] is True and
            len(contract['shared_checker_issues_preserved']) == 2 and
            checks['vector']['status'] == 'UNOBSERVABLE' and checks['vector_comparison_pass'] is False,
            'Runtime/scalar/zero-activity contract not qualified')


def validate_membership(old, lines, identities, vdb, elf):
    require(len(old['tests']) == len(set(old['tests'])) == 714 and
            len(lines) == 715 and lines[1:] == old['tests'], 'Exact714 population/order required')
    require([x['vdb'] for x in identities] == old['tests'], 'ELF identity membership/order differs')
    require(vdb not in old['tests'], 'Duplicate candidate VDB')
    require(elf not in {x['elf_sha256'] for x in identities}, 'Duplicate candidate ELF')
    require(all(str(Path(p).resolve(strict=True)) == p for p in lines + [vdb]),
            'Noncanonical/missing coverage input')


def validate_reference(ref):
    require(ref['status'] == 'GAP100_NO_CLINT_DTB_FULL_SCALAR_DIAGNOSTIC_NOT_ADMISSION' and
            ref['scalar_comparison_qualified'] is True and ref['normalization_performed'] is False and
            ref['coverage_admitted'] is False and ref['RTL_reexecuted'] is False and
            ref['input_elf_sha256'] == runner.ELF_SEAL and
            ref['original_RTL_run'] == str(runtime.RUN), 'Reference identity/qualification differs')
    scalar = ref['scalar']
    require(scalar['status'] == 'TERMINAL_TOHOST_MATCH' and scalar['matched_instructions'] == 6830 and
            scalar['matched_scalar_writes'] == 3116 and scalar['matched_scalar_memory_accesses'] == 1306 and
            scalar['ara_trap_events'] == 15 and scalar['skipped_unobservable_register_values'] == 0 and
            scalar['mismatch'] is None and scalar['stopped_at_unobservable'] is None and
            scalar['aligned_vector_faults'] == [], 'Incomplete/different full scalar comparison')
    require(ref['complete_nontrap_instructions'] == 6830 and ref['full_instruction_differences'] == [],
            'Independent instruction replay differs')


def target_rebind(old, sample, combined, original):
    runner.validate_targets(original)
    records = []
    for item in original['targets']:
        metric, scope, raw = item['metric'], item['scope'], item['point']['raw_index']
        before, actual, after = [b['metrics'][metric][scope] for b in (old, sample, combined)]
        require((before['width'], before['checksum']) == (actual['width'], actual['checksum']) ==
                (after['width'], after['checksum']) and 0 <= raw < before['width'], 'Target shape drift')
        mask = 1 << (before['width'] - 1 - raw)
        hit = [bool(int(r['bits'], 16) & mask) for r in (before, actual, after)]
        require(hit[1] and hit[2], 'Candidate target not hit')
        records.append(dict(metric=metric, scope=scope, point=item['point'],
                            hit_before714=hit[0], hit_candidate=hit[1], hit_proposed715=hit[2]))
    return records


def prepare(out):
    out = Path(out).absolute()
    require(out.parent == OUT and out.resolve() == out and not out.exists(), 'Fresh direct output required')
    seals = life.read_bound(BASE / 'seals.json', BASE_SEAL)
    require(seals['status'] == 'SEALED_FORMAL_714_HISTORICAL_ONLY', 'Not formal historical714')
    ref = life.read_bound(ledger.REFERENCE / 'reference-result.json', ledger.REFERENCE_SEAL)
    proof = life.read_bound(LEDGER, LEDGER_SEAL)
    pins = life.merge_pins(seals['pins'], ref['pins'])
    pins = life.merge_pins(pins, proof['pins'])
    for path, seal in ((BASE / 'seals.json', BASE_SEAL),
                       (ledger.REFERENCE / 'reference-result.json', ledger.REFERENCE_SEAL), (LEDGER, LEDGER_SEAL)):
        pins = life.merge_pins(pins, {str(path): seal})
    for path in (Path(__file__).resolve(), Path(__file__).with_name('test_prepare_gap100_collector.py'),
                 Path(bitmap.__file__).resolve()):
        pins = life.merge_pins(pins, {str(path): life.digest(path)})
    require(str(IDENTITIES) in pins, 'Unsealed historical ELF inventory')
    life.check(pins)
    status = json.loads((BASE / 'status.json').read_bytes())
    require(status['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY' and status['aggregate_passed'] == 714,
            'Formal baseline not PASS714')
    pre = life.read_bound(runner.PRE / 'preflight-manifest.json', runner.PRE_SEAL)
    runner.validate(pre)
    manifest = life.read_bound(runtime.RUN / 'manifest.json', runtime.RUN_SEAL)
    require(manifest['command'] == runner.command(runtime.RUN) and manifest['preflight'] == pre,
            'Original execution command/input differs')
    validate_reference(ref)
    rows = runtime.commit_rows(runtime.RUN / 'commit_trace.csv')
    symbols = dict(pre['symbols'], g100_return=ledger.software.shared._elf_symbol(
        Path(pre['input_elf']), ledger.software.shared.LLVM / 'llvm-readelf', 'g100_return'))
    actual = ledger.audit(rows, (runtime.RUN / 'trace_hart_0.log').read_text(), symbols)
    verify_ledger(actual, proof)
    tail = actual['terminal_same_cycle_self_jump'][0]
    require(ref['scalar']['next_spike']['pc'] == '0x%016x' % tail['pc'] and
            ref['scalar']['next_spike']['instruction'] == '0x%08x' % tail['insn'],
            'Terminal tracer self-jump differs from same-ELF reference')
    checks = runtime.runtime(runtime.RUN, pre, ref['scalar'])
    validate_runtime(checks)
    old = json.loads((BASE / 'combined-bits.json').read_bytes())
    lines = (BASE / 'combined-inputs.txt').read_text().splitlines()
    prior = json.loads(IDENTITIES.read_bytes())
    identities = prior['baseline_identity'] + [dict(vdb=c['vdb'], elf_sha256=c['elf']['sha256'])
                                                for c in prior['cases']]
    admissions = json.loads((BASE / 'admissions.json').read_bytes())
    identities += [dict(vdb=c['vdb'], elf_sha256=c['elf']['sha256']) for c in admissions['cases']]
    vdb = str(runtime.RUN / 'code.vdb')
    validate_membership(old, lines, identities, vdb, runner.ELF_SEAL)
    require(lines[0] == str(life.IMAGE) + '.vdb', 'Not exact old-image design')
    original = life.read_bound(runner.PRE / 'target-before.json', pre['pins'][str(runner.PRE / 'target-before.json')])
    out.mkdir()
    save(out / 'candidate-inputs.proposed.txt', lines[0] + '\n' + vdb + '\n')
    sample = bitmap.collect(out / 'candidate-inputs.proposed.txt')
    combined = bitmap.combine(old, sample)
    require(combined['tests'] == old['tests'] + [vdb] and len(combined['tests']) == 715,
            'Not exact714 prefix plus1')
    pins = life.merge_pins(pins, sample['input_hashes'])
    targets = target_rebind(old, sample, combined, original)
    change = bitmap.delta(old, combined)
    for name, value in (('candidate-bits.proposed.json', sample), ('combined-bits.proposed.json', combined),
                        ('raw-delta.proposed.json', change), ('target-rebound-714.json', targets),
                        ('runtime-qualification.json', checks)):
        save(out / name, value)
    save(out / 'combined-inputs.proposed.txt', '\n'.join([lines[0], *combined['tests']]) + '\n')
    save(out / 'prepare.json', dict(status='PREPARED_714_PLUS1_NOT_ADMITTED', baseline=714,
        proposed_total=715, proposed_new=1, admitted=0, case=dict(name=runner.NAME, vdb=vdb,
        elf_sha256=runner.ELF_SEAL), reference_seal=ledger.REFERENCE_SEAL, trap_ledger_seal=LEDGER_SEAL,
        baseline_seal=BASE_SEAL, raw_delta=change['metrics'], target_count=len(targets),
        targets_newly_hit=sum(not r['hit_before714'] for r in targets), scalar_comparison_qualified=True,
        vector_data_comparison='UNOBSERVABLE_ZERO_EXPECTED_DESTINATIONS_NOT_VECTOR_PASS',
        platform_scope='Same ELF; native DTB minus CLINT only; Bare/PMP0/noMMIO case',
        simulations_started=False, coverage_admitted=False, official_DVE_report=False, new_RTL_signoff=False))
    for path in out.iterdir():
        pins = life.merge_pins(pins, {str(path): life.digest(path)})
    life.check(pins)
    save(out / 'seals.json', dict(status='SEALED_715_CANDIDATE_NOT_ADMITTED', pins=pins))
    print(json.dumps(dict(output=str(out), seal=life.digest(out / 'seals.json'),
                          status='PREPARED_714_PLUS1_NOT_ADMITTED', delta=change['metrics'])))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    prepare(p.parse_args().output)
