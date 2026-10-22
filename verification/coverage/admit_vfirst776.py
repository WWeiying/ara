"""Exact historical775+one qualified vfirst; offline, explicit parent admission only."""
import argparse
import hashlib
import json
from pathlib import Path

import collect_vfirst_long_mask as case
from admit_stride_metadata768 import dedup

life, require = case.life, case.require
runner, bitmap, toggle = case.runner, case.runner.bitmap, case.runner.toggle
RUN = life.OUT / 'vfirst-long-mask-vcs-parent-20261007-01'
QUAL = life.OUT / 'vfirst-long-mask-qualified-parent-20261007-01/qualification.json'
QUAL_SHA = 'a5ba45a9bf32ea9b02047222145e32139be0fed401a7541f73d6d567d192adb7'
REPLAY = life.OUT / 'vfirst-long-mask-qualified-parent-review-20261007-01/qualification.json'
REPLAY_SHA = 'f648835ecb81792a89baccde689aad80dcb1e0f55a41def67483149dee3cc5c2'
RUN_SEAL = '07c589307c81c855b86e7fda468c6ddfdbd5c82e599a8ec6c0f39ab8ebed23b5'


def architecture(q, pre=None):
    require(q['status'] == 'VFIRST_FULL_SCALAR_NATIVE_MASK_CSR_RAW775_PASS_NOT_ADMITTED' and
            q['run'] == str(RUN) and q['prepared_seal'] == RUN_SEAL and
            q['coverage_admitted'] is False and q['RTL_modified'] is False and q['EDA_launched'] is False,
            'Exact qualified vfirst run')
    pre = runner.preflight() if pre is None else pre
    reference = case.reference_prefix(pre)
    case.common.scalar_exact(q['scalar'], case.common.reference_counts(reference, pre['symbols']))
    require(q['scalar_memory'] == dict(instructions=9918, scalar_memory_accesses=2232,
            compressed_memory_accesses=1494, unmodeled_memory_effects=0), 'Every scalar/RVC memory access')
    require(q['signature'] == dict(checks=384, failures=0, scalar_results=8, CSR_values=56,
            whole_v0_bytes=1024, source_guard_bytes=1280, required_read_bytes=3072, retirements=9918),
            'Complete independent mask/rd/source/guards/CSR')
    n = q['native']; l = q['lifecycle']
    loads = [c for c in reference if c.pc == pre['symbols']['vfirst_mask_load']]
    require(n['mask_loads'] == n['vfirst_without_VRF_write'] == 8 and n['compared_bytes'] == 1024 and
            n['skipped_bytes'] == n['duplicate_bytes'] == 0 and len(n['native_mask_writers']) == 8 and
            [(r['pc'], r['opcode']) for r in n['native_mask_writers']] == [(c.pc, c.instruction) for c in loads] and
            [r['arch_seq'] for r in n['native_mask_writers']] == list(range(3, 74, 10)) and
            all(r['compared_bytes'] == 128 and r['allocations'] == r['completions'] == 1
                for r in n['native_mask_writers']) and
            l == dict(requests=81, responses=81, exceptions=0, rejected_arch_seqs=[],
                rejected_backend_uops=0, rejected_vrf_activities=0, backend_uops=24, exact_SID_owner_checked=True),
            'Every native vlm writer/no vfirst VRF and complete SID contract')
    terminal = q['terminal']
    require(terminal['status'] == 'SIMULATION_EXITED_NOT_ADMITTED' and type(terminal['returncode']) is int and
            terminal['returncode'] == 0 and terminal['timeout'] is False and terminal['case'] == runner.NAME and
            terminal['coverage_admitted'] is False and terminal['admission_performed'] is False and
            terminal['pid'] == 473252, 'Actual successful OS terminal identity')
    require(q['input_pins'].get(str(runner.ELF)) == runner.ELF_SHA and
            q['input_pins'].get(str(life.IMAGE)) == runner.IMAGE_SHA and
            q['input_pins'].get(str(runner.PRE)) == runner.PRE_SHA, 'Exact pinned ELF/reference/image preflight')


def replay_equal(q, parent):
    require({k: v for k, v in q.items() if k != 'input_pins'} ==
            {k: v for k, v in parent.items() if k != 'input_pins'}, 'Independent full semantic replay equality')


def context_gate(activities, mapping, reference, symbols):
    expected = {seq: reference[index] for seq, index in mapping.items()
                if reference[index].pc == symbols['vfirst_scalar_op']}
    require(sorted(expected) == list(range(5, 76, 10)), 'Exact eight vfirst PC/arch_seq identities')
    records = []
    for seq, commit in sorted(expected.items()):
        require(seq in activities, 'Missing native vfirst activity')
        activity = activities[seq]
        require(commit.instruction == 0x4208a757 and activity.instruction == commit.instruction and
                activity.vl == 1024 and activity.vstart == activity.eew == 0 and
                activity.use_vd is False and activity.allocations == activity.completions == 1 and
                not activity.writes, 'Exact vfirst native context/identity/no VRF write')
        records.append(dict(arch_seq=seq, pc=commit.pc, opcode=commit.instruction, vl=activity.vl,
            vstart=activity.vstart, eew=activity.eew, use_vd=activity.use_vd,
            allocations=activity.allocations, completions=activity.completions, VRF_writes=0))
    return dict(requests=8, expected_VL=1024, expected_vstart=0, expected_eew=0,
                use_vd=False, zero_VRF_writes=True, records=records)


def native_context(q, pre):
    paths = (RUN / 'commit_trace.csv', RUN / 'vector_trace.csv')
    for path in paths:
        require(q['input_pins'].get(str(path)) == life.digest(path), 'Sealed native context trace pin')
    lanes, vlen, activities = case.vc._parse_vector_trace(paths[1])
    starts, retires, rejected = case.vc._parse_architecture_mapping(paths[0])
    require((lanes, vlen) == (4, 1024) and not rejected, 'Native context geometry/no faults')
    reference = case.reference_prefix(pre)
    mapping = case.vc._map_spike_commits(case.vc._map_architecture_retires(starts, retires, rejected), reference)
    result = context_gate(activities, mapping, reference, pre['symbols'])
    for path in paths:
        require(q['input_pins'][str(path)] == life.digest(path), 'Native context phase-end drift')
    return dict(result, trace_pins={str(path): q['input_pins'][str(path)] for path in paths})


def full_union(before, single):
    require(single['tests'] == [str(RUN / 'code.vdb')], 'Exact one qualified candidate VDB')
    after = bitmap.combine(before, single)
    case.exact_raw_union(before, single, after)
    return after


def historical(ledger, authority):
    audit = dedup(ledger, runner.ELF_SHA, authority)
    require(audit['ledger_members'] == 775 and not audit['duplicate'] and
            [r['vdb'] for r in audit['members']] == ledger[1:] and
            all(authority.get(path) == sha for path, sha in audit['pins'].items()),
            'Every historical775 ELF/command must be formal775-owned, not candidate-owned')
    return dict(audit, baseline=775,
                previous_preflight_dedup_scope='Complete775 admitted ledger ELF/command audit; no candidate pins used as history')


def evaluate():
    base = life.read_bound(runner.BASE / 'admission-manifest.json', runner.BASE_SHA)
    require(base['coverage_admitted'] is True and base['output'] == str(runner.BASE), 'Exact formal775')
    life.check(base['input_pins']); life.check(base['output_pins'])
    def document(name):
        path = runner.BASE / name
        return life.read_bound(path, base['output_pins'][str(path)])
    old_status = document('status.json')
    require(old_status['aggregate_passed'] == 775 and old_status['coverage_admitted'] is True and
            old_status['exact774_prefix'] is True and old_status['full_OR_instances'] == 6162 and
            old_status['candidate_not_historical_ELF_authority'] is True, 'Sealed775 admission status')
    q = life.read_bound(QUAL, QUAL_SHA); parent = life.read_bound(REPLAY, REPLAY_SHA)
    pre = runner.preflight(); architecture(q, pre); architecture(parent, pre); replay_equal(q, parent)
    life.check(q['input_pins']); life.check(parent['input_pins'])
    context = native_context(q, pre)
    record = RUN.with_name(RUN.name + '.prepared.json')
    manifest = life.read_bound(record, RUN_SEAL)
    require(manifest['baseline'] == 775 and manifest['baseline_seal'] == runner.BASE_SHA and
            manifest['command'] == runner.command(RUN) and manifest['elf_sha256'] == runner.ELF_SHA,
            'Actual prepared run population/ELF/command')
    require(case.terminal(RUN, manifest) == q['terminal'], 'Actual OS terminal matches qualification')
    static = life.read_bound(runner.STATIC, runner.STATIC_SHA)
    bound_base, before, scoped_before = runner.baseline(static)
    require(bound_base == base, 'Same sealed775 authority')
    ledger_path = runner.BASE / 'combined-inputs.txt'; ledger = ledger_path.read_text().splitlines()
    require(len(ledger) == len(set(ledger)) == 776 and ledger[1:] == before['tests'] and
            str(RUN / 'code.vdb') not in ledger, 'Exact775 prefix/no reused VDB')
    for name, sha in before['design'].items():
        path = Path(ledger[0]) / 'snps/coverage/db' / name
        require(base['input_pins'].get(str(path)) == sha == life.digest(path), 'Frozen compiled source/shape')
    path = QUAL.parent / 'single-inputs.txt'
    require(q['input_pins'].get(str(path)) == life.digest(path) and
            path.read_text().splitlines() == [ledger[0], str(RUN / 'code.vdb')], 'Bound exact single collection')
    single = bitmap.collect(path)
    saved_single = QUAL.parent / 'single-bits.json'
    require(single == life.read_bound(saved_single, q['input_pins'][str(saved_single)]) and
            all(q['input_pins'].get(path) == sha for path, sha in single['input_hashes'].items()),
            'Exact independent native recollection')
    after = full_union(before, single); delta = bitmap.delta(before, after)
    proposed = QUAL.parent / 'proposed-combined-bits.json'
    require(after == life.read_bound(proposed, q['input_pins'][str(proposed)]) and
            delta == life.read_bound(QUAL.parent / 'raw-delta.json',
                q['input_pins'][str(QUAL.parent / 'raw-delta.json')]), 'Sealed complete OR/delta equality')
    folder = RUN / 'code.vdb/snps/coverage/db/testdata' / runner.NAME
    require(list(folder.parent.iterdir()) == [folder], 'Exactly one native test')
    siminfo = folder / 'siminfo.xml'
    require(q['input_pins'].get(str(siminfo)) == life.digest(siminfo), 'Pinned native command identity')
    tgl = folder / 'tgl.verilog.data.xml'
    sample, sha = toggle.rows(tgl, [static['scope']])
    require(q['input_pins'].get(str(tgl)) == sha, 'Qualified Toggle sample pin')
    gain, gained = case.target_gain(scoped_before, sample, static['targets'])
    gain.update(four_metrics=delta['metrics'], native_toggle_data_sha=sha,
                full_union=case.exact_raw_union(before, single, after))
    require(gain == q['raw_gain'] and gain['target_hit_count'] == 20 and gain['target_unhit_count'] == 0 and
            gain['scoped_toggle_new_slots'] == 20 and sum(map(len, gained.values())) == 20,
            'Positive real775 twenty target slots, no invented percentages')
    elf = historical(ledger, base['input_pins'])
    pins = life.merge_pins(base['input_pins'], base['output_pins'])
    for extra in (q['input_pins'], parent['input_pins'], elf['pins']): pins = life.merge_pins(pins, extra)
    fixed = {QUAL: QUAL_SHA, REPLAY: REPLAY_SHA, record: RUN_SEAL, runner.STATIC: runner.STATIC_SHA,
             runner.BASE / 'admission-manifest.json': runner.BASE_SHA}
    for module in (case, runner, bitmap, toggle, toggle.base):
        path = Path(module.__file__).resolve(); fixed[path] = life.digest(path)
    for path in (Path(__file__).resolve(), Path(__file__).with_name('test_admit_vfirst776.py'),
                 Path(dedup.__code__.co_filename).resolve()): fixed[path] = life.digest(path)
    pins = life.merge_pins(pins, {str(path): sha for path, sha in fixed.items()}); life.check(pins)
    # Historical evidence is retained as evidence, not added to current gains.
    retained = {name: document(name) for name in ('vmacc-toggle-gain774.json', 'retained-itlb-toggle-gain.json')}
    products = dict(retained)
    products.update({'combined-bits.json': after, 'single-bits.json': single, 'raw-delta.json': delta,
        'vfirst-native-context.json': context,
        'vfirst-toggle-gain775.json': dict(gain, before=scoped_before, single=sample,
            after=toggle.union(scoped_before, sample), gained=gained), 'elf-ledger-dedup.json': elf,
        'evidence-pins.json': pins, 'status.json': dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',
            aggregate_passed=776, baseline=775, new_passed=1, coverage_admitted=True, exact775_prefix=True,
            full_OR_metric_instances=6162, unique_new_vdb=True, duplicate_ELF=False,
            scoped_toggle_new_serialized_positions=20, target_hit_count=20,
            full_scalar_memory_native_mask_CSR_guards_lifecycle_verified=True,
            independent_vfirst_native_context8_verified=True,
            prior_gain_records_retained_not_recounted=True, candidate_not_historical_ELF_authority=True,
            raw_delta=delta['metrics'], historical_fixed_image_only=True, official_percentage_claimed=False,
            new_RTL_signoff=False, new_simulation=False, RTL_changed=False)})
    return products, '\n'.join([ledger[0], *after['tests']]) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'verify', 'admit'))
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--seal')
    parser.add_argument('--parent-authorized', action='store_true')
    args = parser.parse_args(); out = args.output.resolve()
    require(args.parent_authorized == (args.mode == 'admit'), 'Separate explicit parent admission approval')
    require((args.mode != 'prepare') == bool(args.seal), 'Verify/admit require prepared seal')
    require(out.parent == life.OUT and not out.exists(), 'Fresh formal776 output')
    products, text = evaluate()
    hashes = {str(out / n): hashlib.sha256((json.dumps(v, indent=2) + '\n').encode()).hexdigest()
              for n, v in products.items()}
    for name in ('combined-inputs.txt', 'generic-coverage-inputs.txt'):
        hashes[str(out / name)] = hashlib.sha256(text.encode()).hexdigest()
    proposal = dict(output=str(out), baseline=str(runner.BASE), baseline_seal=runner.BASE_SHA,
        qualification=str(QUAL), qualification_seal=QUAL_SHA, parent_replay=str(REPLAY),
        parent_replay_seal=REPLAY_SHA, input_pins=products['evidence-pins.json'], output_pins=hashes,
        coverage_admitted=False)
    record = out.with_name(out.name + '.prepared.json')
    if args.mode == 'prepare':
        life.save(record, proposal); print('PREPARED776_NOT_ADMITTED', life.digest(record), flush=True); return
    require(life.read_bound(record, args.seal) == proposal, 'Prepared776 drift')
    if args.mode == 'verify': print('VERIFY_PASS_NO_ADMISSION', flush=True); return
    out.mkdir()
    for name, value in products.items(): life.save(out / name, value)
    for name in ('combined-inputs.txt', 'generic-coverage-inputs.txt'):
        with (out / name).open('x') as stream: stream.write(text)
    life.check(proposal['input_pins']); life.check(hashes)
    life.save(out / 'admission-manifest.json', dict(proposal, coverage_admitted=True, prepared=str(record),
        prepared_seal=args.seal, authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL'))
    print('ADMITTED776', life.digest(out / 'admission-manifest.json'), flush=True)


if __name__ == '__main__': main()
