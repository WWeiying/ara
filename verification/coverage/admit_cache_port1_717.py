"""Verify a sealed strict candidate and publish historical717; no EDA launch."""
import argparse
import json
from pathlib import Path

import check_cache_port1_sv39_offline as audit

life, require = audit.life, audit.require
CANDIDATE = life.OUT / 'cache-port1-sv39-strict-candidate-716-20261006-01'
SEAL = '69fe13a7e2505d78e8202795f8daad0bec4a185b769400b18f6e4128f5b3c963'


def validate(data):
    old, sample, combined = data['before'], data['sample'], data['combined']
    status = data['status']
    require(status['status'] == 'STRICT_CACHE_BOUNDARY_CANDIDATE_NOT_ADMITTED' and
            status['baseline_tests'] == 716 and status['proposed_tests'] == 717 and
            status['coverage_admitted'] is False and status['inherited_716_all_pins_rechecked'] is True,
            'Wrong candidate status')
    require(len(old['tests']) == len(set(old['tests'])) == 716 and
            sample['tests'] == [str(audit.RUN / 'code.vdb')] and
            combined == audit.common.bitmap.combine(old, sample) and
            len(combined['tests']) == len(set(combined['tests'])) == 717,
            'Not exact716 prefix plus sole qualified sample')
    require(data['inputs'] == '\n'.join([str(audit.common.DESIGN), *combined['tests']]) + '\n',
            'Combined input ordering differs')
    audit.runner.validate_targets(data['targets'])
    hits = audit.target_hits(old, sample, combined, data['targets']['targets'])
    require(hits == data['hits'] and hits['sample_hit_targets'] == hits['new_targets'] == 0 and
            hits['replay_FSM_sample_observed'] is False and
            all(not r[k] for r in hits['targets'] for k in ('hit_before716', 'hit_sample', 'hit_union', 'newly_hit')),
            'Replay/target claim differs')
    delta = audit.common.bitmap.delta(old, combined)
    require(delta == data['delta'] and delta['metrics'] == dict(line=0, cond=4, branch=0, fsm=0),
            'Unexpected raw delta')
    gains = {r['instance']: r['new_bits'] for r in delta['instances']}
    ctrl = audit.oracle.C
    arb = 'ara_tb.dut.i_ara_soc.i_system.i_ariane.gen_cache_wt.i_cache_subsystem.i_wt_dcache.i_wt_dcache_mem.i_rr_arb_tree'
    require(gains == {ctrl: 1, arb: 3} and len(delta['instances']) == 2 and
            all(r['metric'] == 'cond' for r in delta['instances']), 'Unexpected delta scope')
    audit.validate_scalar(data['scalar'])
    audit.common.validate_vector(data['vector'])
    require(data['architecture']['status'] == 'CACHE_BOUNDARY_DUT_OUTPUT_TRAP_PTE_EXACT' and
            data['architecture']['checks'] == 35 and data['architecture']['output_bytes'] == 160 and
            data['architecture']['trap_ledger_bytes'] == 64, 'Incomplete architecture oracle')
    # Independent reconstruction from actual CSV, not only the saved verdict.
    pre = json.loads((audit.runner.PRE / 'preflight-manifest.json').read_bytes())
    require(audit.architecture(audit.rows(audit.RUN / 'commit_trace.csv'), pre['symbols']) == data['architecture'],
            'Actual DUT architecture differs')
    audit.zero.vector_zero(audit.RUN / 'vector_trace.csv')
    require(audit.zero.zero_contract(audit.RUN / 'run.vcs.log') == data['contract'], 'Actual contract differs')


def check():
    sealfile = CANDIDATE / 'candidate-seal.json'
    sealed = life.read_bound(sealfile, SEAL)
    pins = life.merge_pins(sealed['pins'], sealed['output_pins'])
    pins = life.merge_pins(pins, {str(sealfile): SEAL})
    for p in (Path(__file__).resolve(), Path(__file__).with_name('test_admit_cache_port1_717.py')):
        pins = life.merge_pins(pins, {str(p): life.digest(p)})
    life.check(pins)
    expected_vdb = json.loads((CANDIDATE / 'vdb-inventory.json').read_bytes())
    actual_vdb = sorted(str(p) for p in (audit.RUN / 'code.vdb').rglob('*') if p.is_file())
    require(sorted(expected_vdb) == actual_vdb and all(pins.get(p) == h for p, h in expected_vdb.items()),
            'Actual VDB inventory differs')
    data = {key: json.loads((CANDIDATE / name).read_bytes()) for key, name in (
        ('sample', 'sample-bits.json'), ('combined', 'proposed-combined-bits.json'),
        ('status', 'status.json'), ('hits', 'target-hit-audit.json'), ('delta', 'raw-bitmap-delta.json'),
        ('scalar', 'scalar-comparison.json'), ('vector', 'vector-comparison.json'),
        ('architecture', 'architecture-audit.json'), ('contract', 'contract-audit.json'))}
    data['before'] = json.loads((audit.BASE / 'combined-bits.json').read_bytes())
    data['targets'] = json.loads((audit.runner.PRE / 'target-before.json').read_bytes())
    data['inputs'] = (CANDIDATE / 'proposed-inputs.txt').read_text()
    validate(data)
    return pins, data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('check-inputs', 'admit'))
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    require((args.mode == 'admit') == bool(args.output), 'Only admit requires output')
    out = args.output.absolute() if args.output else None
    if out:
        require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh output required')
        out.mkdir()
    try:
        pins, data = check()
        if not out:
            print(json.dumps(dict(status='HISTORICAL717_INPUTS_VERIFIED_NO_ADMISSION', pins=len(pins))))
            return
        for src, dst in (('proposed-combined-bits.json', 'combined-bits.json'),
                         ('proposed-inputs.txt', 'combined-inputs.txt'),
                         ('scalar-comparison.json', 'scalar-comparison.json'),
                         ('vector-comparison.json', 'vector-comparison.json'),
                         ('architecture-audit.json', 'architecture-audit.json'),
                         ('contract-audit.json', 'contract-audit.json'),
                         ('raw-bitmap-delta.json', 'raw-bitmap-delta.json'),
                         ('target-hit-audit.json', 'target-hit-audit.json')):
            raw = (CANDIDATE / src).read_bytes()
            require(life.digest(CANDIDATE / src) == pins[str(CANDIDATE / src)], 'Candidate changed before copy')
            with (out / dst).open('xb') as stream:
                stream.write(raw)
        life.check(pins)
        life.save(out / 'evidence-pins.json', pins)
        life.save(out / 'status.json', dict(status='PASS_RAW_UNION_HISTORICAL_ONLY', baseline=716,
            aggregate_passed=717, new_passed=1, candidate_seal=SEAL,
            raw_delta=data['delta']['metrics'], target_hits=0, new_targets=0,
            replay_FSM_sample_observed=False, cycle_level_refill_cause_proven=False,
            official_DVE_report=False, rtl_changed=False, new_RTL_signoff=False,
            simulations_started=False, inherited_716_oracle_readmission_performed=False,
            inherited_716_all_pins_rechecked=True, full_scalar_matched=12335,
            full_scalar_gpr_writes=4015, full_scalar_memory_accesses=2062,
            scalar_skips=0, expected_S_ecalls=2, checks=35, exact_output_bytes=160,
            exact_trap_ledger_bytes=64, vector_comparator_status='UNOBSERVABLE',
            vector_comparison_pass=False, vector_destination_requests=0, vector_bytes=0,
            cvx_requests=0, cvx_responses=0, verified_input_pins=len(pins)))
        output_pins = {str(p): life.digest(p) for p in out.iterdir() if p.is_file()}
        life.save(out / 'admission-manifest.json', dict(schema='CACHE_PORT1_HISTORICAL717_ADMISSION_V1',
            output=str(out), candidate=str(CANDIDATE), candidate_seal=SEAL,
            baseline=str(audit.BASE), output_pins=output_pins))
        print(json.dumps(dict(status='PASS_RAW_UNION_HISTORICAL_ONLY', aggregate_passed=717,
            output=str(out), admission_seal=life.digest(out / 'admission-manifest.json'),
            raw_delta=data['delta']['metrics'], replay_targets_hit=0)))
    except Exception as error:
        if out:
            life.save(out / 'failure.json', dict(status='HISTORICAL717_NOT_ADMITTED', reason=str(error)))
        raise


if __name__ == '__main__':
    main()
