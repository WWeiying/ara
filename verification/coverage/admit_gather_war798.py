"""Offline798 full replay proposal; publication requires separate parent authority."""
import argparse
import hashlib
import json
from pathlib import Path

import gather_war797 as g
import collect_gather_war797_successor as successor
import admit_vsmul_saturation797 as previous

life, require = g.life, g.require
BASE, BASE_SHA = g.BASE, g.BASE_SHA
RUN = life.OUT / 'gather-war797-old-image-parent-20261008-01'
PREPARED_SHA = 'e344e4f083ab58c3f6a30ae6ad7f34cd3991678abffee914403d700bd149cd5f'
STATUS = 'GATHER_WAR797_FULL_STRICT_AND_NEW_TARGET_GAIN_PASS_NOT_ADMITTED'
QUAL = life.OUT / 'gather-war797-successor-qualified-parent-20261008-01/qualification.json'
Q_SHA = 'f7fbbcb4da9b7dab57cbb963ffdbc38fd48cc8fef1b1e03179cc82cf089e9677'
exact, membership = previous.exact, previous.membership


def qualification(q):
    require(q['status'] == STATUS and q['prepared_seal'] == PREPARED_SHA and
            all(q[k] is False for k in ('coverage_admitted', 'EDA_launched', 'RTL_modified')),
            'Exact new Gather full-strict qualification, not failed/admitted')
    result = q['native']['architectural_vector_diff']
    require(result['status'] == 'PASS' and result['stopped_at_spike_index'] is None and
            result['first_mismatch'] is None, 'No vector mismatch or early stop')
    for key, value in dict(vector_destination_requests=16, prefix_vector_destination_requests=16,
                           compared_instructions=16, compared_bytes=16384, skipped_unknown_bytes=0,
                           non_bit_exact_instructions=0, unobservable_instructions=0).items():
        require(type(result[key]) is int and result[key] == value, 'Strict typed native count: ' + key)
    require(all(result[k] == [] for k in ('incomplete_requests', 'unretired_requests', 'trapped_requests')),
            'No incomplete/unretired/trapped requests')
    require(len(result['instructions']) == 16 and all(type(r[k]) is int and r[k] == 0
            for r in result['instructions'] for k in ('unknown_write_bytes', 'skipped_unknown_bytes', 'mismatch_count')),
            'All16 generic instruction guards')
    writers = q['native']['primary_writers']
    wanted = {(role, phase) for role in ('gw_load_source', 'gw_load_index', 'gw_gather', 'gw_overwrite')
              for phase in range(4)}
    require(len(writers) == 16 and {(w['role'], w['phase']) for w in writers} == wanted and
            all(type(w['phase']) is int and type(w['arch_seq']) is int and
                type(w['compared_bytes']) is int and w['compared_bytes'] == 1024 for w in writers) and
            len({w['arch_seq'] for w in writers}) == 16, 'All16 distinct full-group writers')
    scalar = q['scalar']
    require(type(scalar['skipped_unobservable_register_values']) is int and
            scalar['skipped_unobservable_register_values'] == 0, 'No scalar skips')
    require(scalar['status'] == 'TERMINAL_TOHOST_MATCH' and scalar['mismatch'] is None and
            scalar['stopped_at_unobservable'] is None and scalar['rvfi_store_data_layout'] == 'unshifted',
            'Full exact scalar terminal comparison')
    for key in ('matched_instructions', 'ara_retired_instructions', 'ara_committed_instructions'):
        require(type(scalar[key]) is int and scalar[key] == 39052, 'Complete39052 scalar prefix')
    require(type(scalar['ara_trap_events']) is int and scalar['ara_trap_events'] == 0 and
            type(q['scalar_memory']['unmodeled_memory_effects']) is int and
            q['scalar_memory']['unmodeled_memory_effects'] == 0 and
            type(q['scalar_memory']['instructions']) is int and q['scalar_memory']['instructions'] == 39052,
            'No trap/unmodeled memory')
    exact(q['footprint'], dict(checks=3192, required_read_bytes=25536, CSR_values=24, retirements=39052),
          'Complete source/snapshot guards and CSR footprint')
    require(q['lifecycle']['exact_SID_owner_checked'] is True and
            all(type(q['lifecycle'][k]) is int and q['lifecycle'][k] == 0
                for k in ('exceptions', 'rejected_backend_uops', 'rejected_vrf_activities')),
            'Exact owner/lifecycle guards')
    gain = q['raw_gain']
    require(type(gain['baseline']) is int and gain['baseline'] == 797 and gain['full2989'] is True and
            gain['target_queue_slots'] == [0, 1, 2, 3] and
            all(type(v) is int for v in gain['target_queue_slots']) and
            type(gain['target_new_slots']) is int and gain['target_new_slots'] > 0,
            'Positive exact four-slot target gain')


def bounded(rows):
    require(all(type(r['width']) is int and r['width'] >= 0 and
                0 <= int(r['bits'], 16) < 1 << r['width'] for r in rows.values()),
            'Bounded typed nonnegative raw rows')


def full_union(before, single):
    require(single['tests'] == [str(RUN / 'code.vdb')], 'Exact unique actual Gather VDB')
    for blob in (before, single):
        for rows in blob['metrics'].values():
            bounded(rows)
    after = g.bitmap.combine(before, single)
    g.mature.exact_raw_union(before, single, after, population=797)
    return after


def toggle_or(before, single, after):
    for rows in (before, single, after):
        bounded(rows)
    exact(after, g.mature.exact_toggle_union(before, single), 'Complete2989 Toggle OR')


def raw_gain(before, single, after, bt, st, at, targets):
    proof = g.mature.exact_raw_union(before, single, after, population=797)
    toggle_or(bt, st, at)
    additions = g.toggle.gains(bt, at)
    ts = [dict(scope=t['scope'], name=t['name'], new_coordinates=[i for i in t['raw_coordinates']
               if i in additions[t['scope']]]) for t in targets]
    slots = {int(t['name'].split('vinsn[')[1].split(']')[0]) for t in ts
             if 'vinsn[' in t['name'] and t['new_coordinates']}
    require(slots == set(range(4)), 'HOLD: positive target gain required in all four queue slots')
    result = dict(baseline=797, full6162=proof, full2989=True,
                  metrics=g.bitmap.delta(before, after)['metrics'], targets=ts,
                  target_new_slots=sum(len(t['new_coordinates']) for t in ts),
                  target_queue_slots=sorted(slots), full_toggle_new_slots=sum(map(len, additions.values())),
                  official_percentage=None)
    require(result['target_new_slots'] > 0, 'HOLD: no target gain')
    return result, additions


def historical(base, ledger, authority, manifest):
    path = BASE / 'elf-ledger-dedup.json'
    old = life.read_bound(path, base['output_pins'][str(path)])
    require(old['ledger_members'] == 797 and old['duplicate'] is False and len(old['members']) == 797 and
            [m['vdb'] for m in old['members']] == ledger[1:], 'Complete historical797 ELF prefix')
    elves = [s.split('=', 1)[1] for s in manifest['command'] if s.startswith('+PRELOAD=')]
    require(len(elves) == 1, 'One native PRELOAD ELF')
    elf = elves[0]
    require(authority.get(elf) == manifest['elf_sha256'] == life.digest(Path(elf)), 'Actual new ELF authority')
    known = {h for member in old['members'] for h in member['ELF_candidates'].values()}
    require(known and manifest['elf_sha256'] not in known, 'Unique new ELF versus authoritative797 ledger')
    return dict(baseline=797, ledger_members=798, duplicate=False, new_ELF_sha256=manifest['elf_sha256'],
                members=old['members'] + [dict(vdb=str(RUN / 'code.vdb'), ELF_candidates={elf:manifest['elf_sha256']},
                                              command_sources=[str(RUN / 'manifest.json')])])


def evaluate(qual, qseal):
    require(qual == QUAL and qseal == Q_SHA and
            not (qual.parent / 'failure.json').exists(), 'Fresh successful qualification only; failed package rejected')
    q = life.read_bound(qual, qseal)
    qualification(q)
    before, bt, ledger, baseline_pins = g.baseline()
    base = life.read_bound(BASE / 'admission-manifest.json', BASE_SHA)
    authority = life.merge_pins(base['input_pins'], base['output_pins'])
    pins = life.merge_pins(life.merge_pins(authority, baseline_pins), q['input_pins'])
    pins = life.merge_pins(pins, {str(qual):qseal})
    checker_pins = successor.source_pins()
    for name in ('test_gather_war797.py', 'collect_gather_war797_successor.py',
                 'test_collect_gather_war797_successor.py'):
        p = Path(__file__).with_name(name).resolve()
        checker_pins[str(p)] = life.digest(p)
    require(all(q['input_pins'].get(p) == h for p, h in checker_pins.items()),
            'Sealed q binds corrected successor/test/source guards')
    for name in ('admit_gather_war798.py', 'test_admit_gather_war798.py'):
        p = Path(__file__).with_name(name).resolve()
        pins = life.merge_pins(pins, {str(p):life.digest(p)})
    life.check(pins)
    membership(RUN, q['input_pins'])
    membership(qual.parent, {**q['input_pins'], str(qual):qseal})
    status = life.read_bound(BASE / 'status.json', authority[str(BASE / 'status.json')])
    require(type(status['aggregate_passed']) is int and status['aggregate_passed'] == 797 and
            status['coverage_admitted'] is True and ledger[0] == str(life.IMAGE) + '.vdb',
            'Exact admitted797 compile-first authority')
    side = RUN.with_name(RUN.name + '.prepared.json')
    require(pins.get(str(side)) == PREPARED_SHA, 'Original prepared run seal remains bound')
    m = life.read_bound(side, PREPARED_SHA)
    require(m['schema'] == 'GATHER_WAR797_RUN_V1' and m['output'] == str(RUN) and m['baseline'] == 797 and
            m['command'] == g.command(RUN, Path(m['preflight']).parent / 'input.elf') and
            m['image_sha256'] == g.IMAGE_SHA and m['coverage_admitted'] is False and m['RTL_modified'] is False,
            'Original executed command/image/preflight identity')
    ts, target_pins = g.targets()
    exact(ts, m['targets'], 'All11 source-bound176 target coordinates')
    require(all(pins.get(p) == h for p, h in target_pins.items()), 'Target compiled/EL/source authority')
    pre = life.read_bound(Path(m['preflight']), m['preflight_seal'])
    require(pins.get(m['preflight']) == m['preflight_seal'], 'Bound preflight')
    require(pre['status'] == 'GATHER_WAR797_HOST_SPIKE_PASS_NOT_DUT' and pre['baseline'] == 797,
            'Sealed original reference qualification')
    state_path = RUN / 'simulation-status.json'
    state = life.read_bound(state_path, pins[str(state_path)])
    exact(state, q['terminal'], 'Actual sealed OS terminal')
    require(type(state['returncode']) is int and state['returncode'] == 0 and state['timeout'] is False and
            state['status'] == 'SIMULATION_EXITED_NOT_ADMITTED' and state['case'] == g.NAME and
            state['coverage_admitted'] is False and state['admission_performed'] is False,
            'True successful native terminal')
    actual_path = RUN / 'manifest.json'
    exact(life.read_bound(actual_path, pins[str(actual_path)]),
          dict(m, authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL'), 'Exact executed manifest')
    # Parent-sealed successor qualification already owns the full scalar/VRF replay.
    replay = {name:q[name] for name in ('scalar', 'scalar_memory', 'native', 'footprint', 'lifecycle')}
    native = successor.corrected_native()(RUN, g.reference(pre), pre['symbols'], pre)
    exact(native, q['native'], 'Corrected MASKU2 all16writer native replay')
    replay['native'] = native
    folder = RUN / 'code.vdb/snps/coverage/db/testdata' / g.NAME
    require(list(folder.parent.iterdir()) == [folder], 'Exactly one native coverage identity')
    identity_pins = g.coverage_identity(folder, RUN, m, Path(ledger[0]))
    require(all(pins.get(p) == h for p, h in identity_pins.items()), 'Complete native identity pins')
    inputs = qual.parent / 'single-inputs.txt'
    require(inputs.read_text() == ledger[0] + '\n' + str(RUN / 'code.vdb') + '\n', 'Actual singleton compile-first ledger')
    def doc(name):
        p = qual.parent / name
        return life.read_bound(p, q['input_pins'][str(p)])
    single = g.bitmap.collect(inputs)
    exact(single, doc('single-bits.json'), 'Actual6162 singleton')
    after = full_union(before, single)
    exact(after, doc('proposed-combined-bits.json'), 'All6162 exact797-prefix OR')
    st, sha = g.toggle.rows(folder / 'tgl.verilog.data.xml', list(bt))
    require(sha == pins[str(folder / 'tgl.verilog.data.xml')], 'Actual Toggle XML')
    exact(st, doc('single-toggle-bits.json'), 'Actual2989 singleton')
    at = doc('proposed-combined-toggle-bits.json')
    gain, additions = raw_gain(before, single, after, bt, st, at, ts)
    exact(gain, q['raw_gain'], 'Every raw gain field and four slots')
    exact(additions, doc('full-toggle-gain.json'), 'All Toggle additions')
    history = historical(base, ledger, pins, m)
    products = {Path(p).name:life.read_bound(Path(p), h) for p,h in base['output_pins'].items()
                if Path(p).parent == BASE and p.endswith('.json') and
                ('toggle-gain' in Path(p).name or Path(p).name.startswith('retained-'))}
    products.update({'single-bits.json':single, 'combined-bits.json':after, 'combined-toggle-bits.json':at,
        'raw-delta.json':g.bitmap.delta(before, after), 'gather-toggle-gain797.json':gain,
        'elf-ledger-dedup.json':history, 'evidence-pins.json':pins, 'replay-audit.json':replay,
        'native-vdb-identity.json':dict(command=m['command'], cwd=str(RUN), compile_vdb=ledger[0], pins=identity_pins),
        'status.json':dict(status='PASS_RAW_UNION_HISTORICAL_ONLY', aggregate_passed=798, baseline=797,
            new_passed=1, exact797_prefix=True, unique_new_vdb=True, duplicate_ELF=False,
            full_OR_metric_instances=6162, full_OR_Toggle_instances=2989, raw_gain=gain,
            qualification_seal=qseal, coverage_admitted=True, EDA_launched=False, RTL_modified=False)})
    life.check(pins)
    return products, '\n'.join([ledger[0], *after['tests']]) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'verify', 'admit'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--qualification', type=Path, required=True)
    parser.add_argument('--qualification-seal', required=True)
    parser.add_argument('--seal')
    parser.add_argument('--parent-authorized', action='store_true')
    a = parser.parse_args(argv)
    require((a.mode != 'prepare') == bool(a.seal), 'Verify/admit requires prepared seal')
    require((a.mode == 'admit') == a.parent_authorized, 'Separate explicit parent publication authority')
    out, qual = a.output.absolute(), a.qualification.absolute()
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh publication destination')
    products, text = evaluate(qual, a.qualification_seal)
    hashes = {str(out / name):hashlib.sha256((json.dumps(value, indent=2) + '\n').encode()).hexdigest()
              for name,value in products.items()}
    for name in ('combined-inputs.txt', 'generic-coverage-inputs.txt'):
        hashes[str(out / name)] = hashlib.sha256(text.encode()).hexdigest()
    proposal = dict(schema='GATHER_WAR798_ADMISSION_V1', output=str(out), baseline=str(BASE), baseline_seal=BASE_SHA,
        qualification=str(qual), qualification_seal=a.qualification_seal,
        input_pins=products['evidence-pins.json'], output_pins=hashes,
        audit=dict(products['status.json'], coverage_admitted=False, status='PREPARED798_FULL_REPLAY_PASS_NOT_ADMITTED'),
        coverage_admitted=False, EDA_launched=False, RTL_modified=False)
    sidecar = out.with_name(out.name + '.prepared.json')
    if a.mode == 'prepare':
        require(not sidecar.exists(), 'No prepared overwrite')
        life.save(sidecar, proposal)
        print('PREPARED798_NOT_ADMITTED', life.digest(sidecar))
        return
    exact(proposal, life.read_bound(sidecar, a.seal), 'Complete typed prepared replay')
    if a.mode == 'verify':
        print('PREPARED798_VERIFY_PASS_NOT_ADMITTED')
        return
    out.mkdir()
    for name,value in products.items():
        life.save(out / name, value)
    for name in ('combined-inputs.txt', 'generic-coverage-inputs.txt'):
        with (out / name).open('x') as stream:
            stream.write(text)
    life.check(products['evidence-pins.json'])
    life.check(hashes)
    life.save(out / 'admission-manifest.json', dict(proposal, coverage_admitted=True,
        prepared=str(sidecar), prepared_seal=a.seal,
        authorization_source='EXPLICIT_PARENT_ADMISSION_AUTHORIZATION_WITHIN_USER_GOAL'))
    print('ADMITTED798', life.digest(out / 'admission-manifest.json'))


if __name__ == '__main__':
    main()
