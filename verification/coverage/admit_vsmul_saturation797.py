"""Offline797 preparation and separately parent-authorized publication."""
import argparse
import hashlib
import json
from pathlib import Path

import collect_vsmul_saturation796 as c

r = c.runner
life, require = c.life, c.require
BASE, BASE_SHA = r.BASE, r.BASE_SHA
QUAL = life.OUT / 'vsmul-saturation796-qualified-parent-20261008-01'
Q_SHA = 'a1894829082271554496c996d487152156b56e06c17e352d22265137da7fc7c2'
RUN = life.OUT / 'vsmul-saturation796-vcs-prepared-agent-20261008-01'
PREPARED_SHA = 'ee3f91fb8f132991115153498bb79708fe280eaafffe3af54ebf08cade61b16f'


def exact(actual, saved, label):
    def encode(value):
        return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
    require(encode(actual) == encode(saved), 'Complete typed replay: ' + label)


def qualification(q):
    require(q['status'] == 'VSMUL796_FULL_SCALAR_NATIVE_SOURCE_CSR_MEMORY_PASS_NOT_ADMITTED'
            and q['run'] == str(RUN) and q['prepared_seal'] == PREPARED_SHA
            and all(q[k] is False for k in ('coverage_admitted', 'EDA_launched', 'RTL_modified')),
            'Exact sealed VSMUL qualification identity')
    c.generic_gate(q['native']['architectural_vector_diff'])
    require(type(q['scalar']['skipped_unobservable_register_values']) is int
            and q['scalar']['skipped_unobservable_register_values'] == 0,
            'No scalar skips')


def membership(root, pins):
    paths = list(root.rglob('*'))
    require(root.is_dir() and not root.is_symlink() and not any(p.is_symlink() for p in paths),
            'No symlink native evidence')
    actual = {str(p) for p in paths if p.is_file()}
    require(actual and actual == {p for p in pins if p.startswith(str(root) + '/')},
            'Complete exact native evidence membership')


def full_union(before, single):
    require(single['tests'] == [str(RUN / 'code.vdb')], 'Unique actual native candidate')
    after = r.bitmap.combine(before, single)
    c.exact_raw_union(before, single, after, population=796)
    return after


def toggle_or(before, single, after):
    expected = c.exact_toggle_union(before, single)
    for rows in (before, single, after):
        require(all(type(row['width']) is int and row['width'] >= 0
                    and 0 <= int(row['bits'], 16) < 1 << row['width'] for row in rows.values()),
                'Bounded nonnegative typed Toggle records')
    exact(after, expected, 'All2989 Toggle OR')


def historical(base, ledger, authority):
    path = BASE / 'elf-ledger-dedup.json'
    old = life.read_bound(path, base['output_pins'][str(path)])
    require(old['ledger_members'] == 795 and old['duplicate'] is False
            and len(old['members']) == 795 and [m['vdb'] for m in old['members']] == ledger[1:-1],
            'Complete historical795 ELF prefix')
    for member in old['members']:
        require(member['ELF_candidates'] and all(authority.get(p) == h and h != r.ELF_SHA
                for p, h in member['ELF_candidates'].items()), 'Historical ELF authority/dedup')
    command_path = Path(ledger[-1]).parent / 'manifest.json'
    record = life.read_bound(command_path, authority[str(command_path)])
    elves = [s.split('=', 1)[1] for s in record['command'] if s.startswith('+PRELOAD=')]
    require(len(elves) == 1 and record['pins'].get(elves[0]) == authority.get(elves[0])
            and elves[0] in authority and authority[elves[0]] != r.ELF_SHA, 'Actual796 ELF command dedup')
    return dict(baseline=796, ledger_members=796, duplicate=False, new_ELF_sha256=r.ELF_SHA,
                members=old['members'] + [dict(vdb=ledger[-1], ELF_candidates={elves[0]:authority[elves[0]]},
                                             command_sources=[str(command_path)])])


def evaluate():
    q = life.read_bound(QUAL / 'qualification.json', Q_SHA)
    qualification(q)
    base, before, bt, ledger = r.baseline()
    require(base['output'] == str(BASE) and ledger[0] == str(life.IMAGE) + '.vdb', 'Admitted796 compile-first authority')
    authority = life.merge_pins(base['input_pins'], base['output_pins'])
    pins = life.merge_pins(authority, q['input_pins'])
    pins = life.merge_pins(pins, {str(BASE / 'admission-manifest.json'):BASE_SHA,
                                 str(QUAL / 'qualification.json'):Q_SHA})
    for name in ('admit_vsmul_saturation797.py', 'test_admit_vsmul_saturation797.py'):
        path = Path(__file__).with_name(name).resolve()
        pins = life.merge_pins(pins, {str(path):life.digest(path)})
    life.check(pins)
    membership(RUN, q['input_pins'])
    membership(QUAL, {**q['input_pins'], str(QUAL / 'qualification.json'):Q_SHA})
    def doc(name):
        path = QUAL / name
        return life.read_bound(path, q['input_pins'][str(path)])
    status_path = BASE / 'status.json'
    status = life.read_bound(status_path, authority[str(status_path)])
    require(type(status['aggregate_passed']) is int and status['aggregate_passed'] == 796
            and status['coverage_admitted'] is True, 'Formal796 PASS authority')
    manifest = life.read_bound(RUN.with_name(RUN.name + '.prepared.json'), PREPARED_SHA)
    exact(r.prepare(RUN, existing=True), manifest, 'Frozen prepared run')
    exact(c.terminal(RUN, manifest), q['terminal'], 'OS terminal')
    pre = r.preflight()
    reference = c.reference_prefix(pre)
    rows = c.common.read_csv((RUN / 'commit_trace.csv').read_bytes(), c.common.COMMIT_FIELDS)
    vectors = c.common.read_csv((RUN / 'vector_trace.csv').read_bytes(), c.common.VECTOR_FIELDS)
    lifecycle = c.control.lifecycle(rows, vectors)
    c.mature.logs(RUN, lifecycle)
    scalar = c.common.spike_trace.compare_commit_prefix(Path(pre['reference']), RUN / 'commit_trace.csv',
        0x80000000, terminal_tohost_address=pre['symbols']['tohost'],
        rtl_exception_log=RUN / 'trace_hart_0.log', rvfi_store_data_layout='unshifted')
    c.common.scalar_exact(scalar, c.common.reference_counts(reference, pre['symbols']))
    replay = dict(lifecycle=lifecycle, scalar=scalar,
                  signature=c.footprint(rows, pre['symbols'], reference),
                  scalar_memory=c.memory.scalar_memory_exact(rows, reference),
                  native=c.native(RUN, reference, pre['symbols'], pre))
    for name, value in replay.items():
        exact(value, q[name], name)
    folder = RUN / 'code.vdb/snps/coverage/db/testdata' / r.NAME
    require(list(folder.parent.iterdir()) == [folder], 'Exactly one native VDB test identity')
    identity_pins = c.coverage_identity(folder, RUN, manifest, Path(ledger[0]))
    require(all(pins.get(p) == h for p, h in identity_pins.items()), 'Bound complete native identity')
    inputs = QUAL / 'single-inputs.txt'
    require(inputs.read_text() == ledger[0] + '\n' + str(RUN / 'code.vdb') + '\n', 'Actual singleton input ledger')
    single = r.bitmap.collect(inputs)
    exact(single, doc('single-bits.json'), 'Actual6162 singleton')
    for rel, h in single['design'].items():
        path = Path(ledger[0]) / 'snps/coverage/db' / rel
        require(authority.get(str(path)) == h == life.digest(path), 'Compiled design authority')
    after = full_union(before, single)
    exact(after, doc('proposed-combined-bits.json'), 'Complete797 ordered union')
    delta = r.bitmap.delta(before, after)
    exact(delta, doc('raw-delta.json'), 'Raw delta')
    st, sha = r.toggle.rows(folder / 'tgl.verilog.data.xml', list(bt))
    require(sha == pins[str(folder / 'tgl.verilog.data.xml')], 'Actual Toggle XML SHA')
    exact(st, doc('single-toggle-bits.json'), 'Actual2989 singleton')
    at = doc('proposed-combined-toggle-bits.json')
    toggle_or(bt, st, at)
    gains = r.toggle.gains(bt, at)
    exact(gains, doc('full-toggle-gain.json'), 'Full Toggle gain')
    targets = [dict(scope=t['scope'], field=t['name'],
                    new_serialized_coordinates=[i for i in t['raw_coordinates'] if i in gains[t['scope']]])
               for t in manifest['targets']]
    raw = dict(baseline=796, full6162=c.exact_raw_union(before, single, after), full2989=True,
               metrics=delta['metrics'], full_toggle_new_slots=sum(map(len, gains.values())), targets=targets,
               primary_new_slots=sum(len(t['new_serialized_coordinates']) for t in targets), official_percentage=None)
    exact(raw, q['raw_gain'], 'All raw gain fields')
    require(sum(delta['metrics'].values()) + raw['full_toggle_new_slots'] > 0, 'Positive latest796 gain')
    hist = historical(base, ledger, authority)
    products = {Path(p).name:life.read_bound(Path(p), h) for p, h in base['output_pins'].items()
                if Path(p).parent == BASE and p.endswith('.json')
                and ('toggle-gain' in Path(p).name or Path(p).name.startswith('retained-'))}
    products.update({'single-bits.json':single, 'combined-bits.json':after, 'combined-toggle-bits.json':at,
        'raw-delta.json':delta, 'vsmul-toggle-gain796.json':raw, 'elf-ledger-dedup.json':hist,
        'native-vdb-identity.json':dict(command=manifest['command'], cwd=str(RUN),
                                       compile_vdb=ledger[0], pins=identity_pins),
        'evidence-pins.json':pins, 'replay-audit.json':replay,
        'status.json':dict(status='PASS_RAW_UNION_HISTORICAL_ONLY', aggregate_passed=797,
            baseline=796, new_passed=1, exact796_prefix=True, unique_new_vdb=True, duplicate_ELF=False,
            full_OR_metric_instances=6162, full_OR_Toggle_instances=2989, raw_gain=raw,
            qualification_seal=Q_SHA, coverage_admitted=True, EDA_launched=False, RTL_modified=False)})
    life.check(pins)
    return products, '\n'.join([ledger[0], *after['tests']]) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'verify', 'admit'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal')
    parser.add_argument('--parent-authorized', action='store_true')
    args = parser.parse_args()
    require((args.mode != 'prepare') == bool(args.seal), 'Verify/admit requires prepared seal')
    require((args.mode == 'admit') == args.parent_authorized, 'Separate explicit parent publication authority')
    out = args.output.absolute()
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh parent publication destination')
    products, text = evaluate()
    hashes = {str(out / name):hashlib.sha256((json.dumps(value, indent=2) + '\n').encode()).hexdigest()
              for name, value in products.items()}
    for name in ('combined-inputs.txt', 'generic-coverage-inputs.txt'):
        hashes[str(out / name)] = hashlib.sha256(text.encode()).hexdigest()
    proposal = dict(schema='VSMUL_SATURATION797_ADMISSION_V1', output=str(out), baseline=str(BASE),
        baseline_seal=BASE_SHA, qualification=str(QUAL / 'qualification.json'), qualification_seal=Q_SHA,
        input_pins=products['evidence-pins.json'], output_pins=hashes,
        audit=dict(products['status.json'], coverage_admitted=False, status='PREPARED797_FULL_REPLAY_PASS_NOT_ADMITTED'),
        coverage_admitted=False, EDA_launched=False, RTL_modified=False)
    sidecar = out.with_name(out.name + '.prepared.json')
    if args.mode == 'prepare':
        life.save(sidecar, proposal)
        print('PREPARED797_NOT_ADMITTED', life.digest(sidecar))
    else:
        exact(proposal, life.read_bound(sidecar, args.seal), 'Complete prepared replay')
        if args.mode == 'verify':
            print('PREPARED797_VERIFY_PASS_NOT_ADMITTED')
            return
        out.mkdir()
        for name, value in products.items():
            life.save(out / name, value)
        for name in ('combined-inputs.txt', 'generic-coverage-inputs.txt'):
            with (out / name).open('x') as stream:
                stream.write(text)
        life.check(products['evidence-pins.json'])
        life.check(hashes)
        life.save(out / 'admission-manifest.json', dict(proposal, coverage_admitted=True,
            prepared=str(sidecar), prepared_seal=args.seal,
            authorization_source='EXPLICIT_PARENT_ADMISSION_AUTHORIZATION_WITHIN_USER_GOAL'))
        print('ADMITTED797', life.digest(out / 'admission-manifest.json'))


if __name__ == '__main__':
    main()
