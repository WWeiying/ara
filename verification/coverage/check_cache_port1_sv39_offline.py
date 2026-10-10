"""Exact cache-boundary replay candidate against historical716; no simulation/admission."""
import argparse
import json
import struct
from pathlib import Path
from types import SimpleNamespace

import admit_gap97_offline as common
import admit_gap99_offline as zero
import build_cache_port1_sv39_crossline_preflight as oracle
import run_cache_port1_sv39_simulation as runner

life, require = runner.life, oracle.require
RUN = life.OUT / 'cache-port1-sv39-old-image-20261006-01'
RUN_SEAL = '8c12c0d781c6f648953433e66461b0177c49a19d9cfd3cf8a36b14c2c7c345f2'
BASE = life.OUT / 'gap101a-offline-admitted-716-20261006-01'
BASE_SEAL = 'df9e35f425734bce6d22416acf3f91fbea85f007ceb1e45f2e1eee703da4fd8a'


def validate_scalar(result):
    expected = dict(status='TERMINAL_TOHOST_MATCH', matched_instructions=12335,
        matched_scalar_writes=4015, matched_scalar_memory_accesses=2062,
        ara_committed_instructions=12335, ara_retired_instructions=12337,
        ara_trap_events=2, skipped_unobservable_register_values=0,
        stopped_at_unobservable=None, mismatch=None, matched_floating_writes=0,
        rvfi_store_data_layout='unshifted')
    require(all(k in result and type(result[k]) is type(v) and result[k] == v for k, v in expected.items()),
            'Incomplete/different scalar boundary')


def rows(path):
    hexes = {'pc', 'insn', 'rd_wdata', 'mem_addr', 'mem_rmask', 'mem_wmask', 'mem_wdata'}
    result = [{k: v if k == 'event' else int(v, 16 if k in hexes else 10)
               for k, v in r.items()} for r in common.read_csv(path, common.COMMIT_FIELDS)]
    require(len(result) == 12337 and [r['order'] for r in result] == list(range(len(result))) and
            all(r['event'] == 'retire' and r['trap'] in (0, 1) and 0 <= r['rd'] < 32 for r in result) and
            all(a['cycle'] <= b['cycle'] for a, b in zip(result, result[1:])),
            'Incomplete/non-scalar/reordered commit trace')
    return result


def architecture(records, symbols):
    traps = [r for r in records if r['trap']]
    expected_pcs = [0x40000000 + (slot + 1) * 4096 + 32 for slot in (3, 35)]
    require([r['pc'] for r in traps] == expected_pcs and all(r['insn'] == 0x73 and
            r['rd'] == r['rd_wdata'] == r['mem_rmask'] == r['mem_wmask'] == 0 for r in traps),
            'Unexpected/missing trap boundary')
    commits, terminals = [], []
    for r in records:
        if r['trap']:
            continue
        accesses = []
        if r['mem_wmask']:
            size = bin(r['mem_wmask']).count('1')
            require(size in (1, 2, 4, 8) and r['mem_addr'] % size == 0 and
                    r['mem_wmask'] == ((1 << size) - 1) << (r['mem_addr'] & 7),
                    'Invalid unshifted store mask')
            accesses.append((r['mem_addr'], r['mem_wdata'] & ((1 << (8 * size)) - 1)))
            if r['mem_addr'] == symbols['tohost']:
                require(size == 8, 'Partial terminal store')
                terminals.append((r['order'], r['mem_wdata']))
        commits.append(SimpleNamespace(pc=r['pc'], instruction=r['insn'], vector_writes=[],
            gpr_writes={r['rd']: r['rd_wdata']} if r['rd'] else {}, memory_accesses=accesses))
    require(terminals == [(len(records) - 1, 1)], 'Wrong/duplicate/nonterminal tohost')
    result = oracle.validate(commits, symbols)
    return dict(status='CACHE_BOUNDARY_DUT_OUTPUT_TRAP_PTE_EXACT', oracle=result,
                trap_rows=traps, full_scalar_retirements=len(records),
                output_bytes=160, trap_ledger_bytes=64, checks=35)


def target_hits(before, sample, combined, targets):
    result = []
    for target in targets:
        metric, scope, raw = target['metric'], target['scope'], target['raw_index']
        values = []
        for bitmap in (before, sample, combined):
            row = bitmap['metrics'][metric][scope]
            require(row['width'] == target['width'] and row['checksum'] == target['definition_checksum'],
                    'Target shape drift')
            values.append(bool(int(row['bits'], 16) & (1 << (row['width'] - 1 - raw))))
        result.append(dict(target=target, hit_before716=values[0], hit_sample=values[1],
                           hit_union=values[2], newly_hit=values[2] and not values[0]))
    return dict(targets=result, sample_hit_targets=sum(r['hit_sample'] for r in result),
                new_targets=sum(r['newly_hit'] for r in result),
                replay_FSM_sample_observed=all(r['hit_sample'] for r in result if r['target']['metric'] == 'fsm'),
                cycle_level_refill_cause_proven=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    out = parser.parse_args().output.absolute()
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh direct output required')
    out.mkdir()
    pins = {}
    try:
        manifest = life.read_bound(RUN / 'manifest.json', RUN_SEAL)
        require(life.read_bound(RUN.with_name(RUN.name + '.prepared.json'), RUN_SEAL) == manifest and
                manifest['command'] == runner.command(RUN) and manifest['timeout_s'] == 600 and
                manifest['old_image_files_checked'] == 66, 'Executed command/prepared differs')
        pre = life.read_bound(runner.PRE / 'preflight-manifest.json', runner.PRE_SEAL)
        runner.validate(pre)
        require(manifest['preflight'] == pre, 'Executed preflight differs')
        pins = life.merge_pins(manifest['pins'], pre['pins'])
        status = json.loads((RUN / 'simulation-status.json').read_bytes())
        require(status == dict(status='SIMULATION_EXITED_NOT_ADMITTED', returncode=0, case=runner.NAME,
                               coverage_admitted=False, admission_performed=False), 'Failed/nonterminal simulation')
        ref = life.read_bound(BASE / 'admission-manifest.json', BASE_SEAL)
        life.check(ref['output_pins'])
        pins = life.merge_pins(pins, ref['output_pins'])
        inherited = json.loads((BASE / 'evidence-pins.json').read_bytes())
        pins = life.merge_pins(pins, inherited)
        before = json.loads((BASE / 'combined-bits.json').read_bytes())
        state = json.loads((BASE / 'status.json').read_bytes())
        require(state['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY' and state['aggregate_passed'] == 716 and
                len(before['tests']) == len(set(before['tests'])) == 716 and
                (BASE / 'combined-inputs.txt').read_text().splitlines() == [str(common.DESIGN), *before['tests']],
                'Not exact formal716 baseline')
        require(all(inherited.get(p) == h for p, h in before['input_hashes'].items()),
                'Baseline raw metrics not bound to inherited ledger')
        life.check(pins)
        require((RUN / 'console.log').read_text().count('Core Test *** SUCCESS ***') == 1,
                'Missing/duplicate console SUCCESS')
        target = json.loads((runner.PRE / 'target-before.json').read_bytes())
        runner.validate_targets(target)
        for p in (RUN / 'manifest.json', RUN.with_name(RUN.name + '.prepared.json'), RUN / 'simulation-status.json',
                  RUN / 'commit_trace.csv', RUN / 'vector_trace.csv', RUN / 'run.vcs.log', RUN / 'console.log',
                  BASE / 'admission-manifest.json', Path(__file__).resolve(),
                  Path(__file__).with_name('test_check_cache_port1_sv39_offline.py')):
            pins = life.merge_pins(pins, {str(p): life.digest(p)})
        # Pin the actually loaded comparison/parser/oracle implementation files.
        for module in (common, zero, oracle, runner, common.bitmap):
            p = Path(module.__file__).resolve()
            pins = life.merge_pins(pins, {str(p): life.digest(p)})
        import ara_verify.spike_trace as checker
        import ara_verify.vector_commit as vector_checker
        import ara_verify.contract as contract_checker
        for module in (checker, vector_checker, contract_checker):
            p = Path(module.__file__).resolve()
            pins = life.merge_pins(pins, {str(p): life.digest(p)})
        for p in Path(checker.__file__).resolve().parent.rglob('*.py'):
            pins = life.merge_pins(pins, {str(p): life.digest(p)})
        vdb_files = sorted(p for p in (RUN / 'code.vdb').rglob('*') if p.is_file())
        require(vdb_files and not any(p.is_symlink() for p in (RUN / 'code.vdb').rglob('*')),
                'Missing/aliased VDB inventory')
        pins = life.merge_pins(pins, {str(p): life.digest(p) for p in vdb_files})
        life.save(out / 'vdb-inventory.json', {str(p): pins[str(p)] for p in vdb_files})
        records = rows(RUN / 'commit_trace.csv')
        arch = architecture(records, pre['symbols'])
        entry = struct.unpack_from('<Q', (runner.PRE / 'input.elf').read_bytes(), 24)[0]
        scalar = common.compare_commit_prefix(runner.PRE / 'spike.trace', RUN / 'commit_trace.csv', entry,
            terminal_tohost_address=pre['symbols']['tohost'], rvfi_store_data_layout='unshifted')
        validate_scalar(scalar)
        zero.vector_zero(RUN / 'vector_trace.csv')
        vector = common.compare_vector_commits(runner.PRE / 'spike.trace', RUN / 'commit_trace.csv',
                                               RUN / 'vector_trace.csv', entry)
        common.validate_vector(vector)
        contract = zero.zero_contract(RUN / 'run.vcs.log')
        for name, value in (('scalar-comparison.json', scalar), ('architecture-audit.json', arch),
                            ('vector-comparison.json', vector), ('contract-audit.json', contract)):
            life.save(out / name, value)
        inputs = out / 'new-inputs.txt'
        with inputs.open('x') as stream:
            stream.write(str(common.DESIGN) + '\n' + str(RUN / 'code.vdb') + '\n')
        sample = common.bitmap.collect(inputs)
        require(sample['tests'] == [str(RUN / 'code.vdb')], 'Unexpected sample membership')
        pins = life.merge_pins(pins, sample['input_hashes'])
        db = common.DESIGN / 'snps/coverage/db'
        pins = life.merge_pins(pins, {str(db / rel): h for rel, h in sample['design'].items()})
        combined = common.bitmap.combine(before, sample)
        require(combined['tests'] == [*before['tests'], str(RUN / 'code.vdb')] and
                len(set(combined['tests'])) == 717, 'Wrong proposed716+1 population')
        hits = target_hits(before, sample, combined, target['targets'])
        delta = common.bitmap.delta(before, combined)
        for name, value in (('sample-bits.json', sample), ('proposed-combined-bits.json', combined),
                            ('target-hit-audit.json', hits), ('raw-bitmap-delta.json', delta)):
            life.save(out / name, value)
        with (out / 'proposed-inputs.txt').open('x') as stream:
            stream.write('\n'.join([str(common.DESIGN), *combined['tests']]) + '\n')
        require(vdb_files == sorted(p for p in (RUN / 'code.vdb').rglob('*') if p.is_file()),
                'VDB membership changed')
        life.check(pins)
        life.save(out / 'status.json', dict(status='STRICT_CACHE_BOUNDARY_CANDIDATE_NOT_ADMITTED',
            baseline_tests=716, proposed_tests=717, coverage_admitted=False, official_DVE_report=False,
            rtl_changed=False, simulations_started=False, new_RTL_signoff=False,
            raw_delta=delta['metrics'], target_sample_hits=hits['sample_hit_targets'],
            new_targets=hits['new_targets'], replay_FSM_sample_observed=hits['replay_FSM_sample_observed'],
            vector_status='UNOBSERVABLE', vector_comparison_pass=False,
            inherited_baseline_readmission_performed=False, inherited_716_all_pins_rechecked=True))
        output_pins = {str(p): life.digest(p) for p in out.iterdir() if p.is_file()}
        life.save(out / 'candidate-seal.json', dict(pins=pins, output_pins=output_pins,
                  inherited_716_ledger=str(BASE / 'evidence-pins.json'), baseline_admission_seal=BASE_SEAL))
        print(json.dumps(dict(output=str(out), seal=life.digest(out / 'candidate-seal.json'),
                              target_hits=hits, raw_delta=delta['metrics'])))
    except Exception as error:
        life.save(out / 'failure.json', dict(status='CACHE_BOUNDARY_NOT_QUALIFIED', reason=str(error)))
        raise


if __name__ == '__main__':
    main()
