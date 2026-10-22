"""Offline formal776 plus qualified AKV entropy; no model, simulation or DVE."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shlex
import xml.etree.ElementTree as ET

import collect_akv_entropy as case
import targeted_toggle_evidence_v2 as toggle
from admit_stride_metadata768 import dedup

life, require, bitmap = case.life, case.require, case.bitmap
BASE = life.OUT / 'vfirst-offline-admitted776-parent-20261007-01'
BASE_SHA = '85abeb09ddfc3c4ddbfc43eefa7c71d860932dd66af572edac0bd7030ce3c33c'
QUAL = life.OUT / 'akv-entropy-qualified-manifest-parent-20261007-01'
Q_SHA = 'a32928e4a26ab3456d9a59ea8d29ce7ff4a282b9fe8419f121ba12f9fb5e50d0'
C_SHA = 'feda50282f581f106598ed50e32ff519837c786682c0c247e581b9e652982f57'
RUN = life.OUT / 'akv-entropy-old-image775-parent-20261007-01'
PREPARED_SHA = '96c4dc17891d08ed191d1426aee04b61508570079bd0622d44b140a0842db487'
ACTUAL_SHA = '94dd5c6f0d4d748cb3e5204b6f646989eba3abced9f9fae16a70c6c45da929d2'
ELF_SHA = '2432ecf4e69be60fef9a994fa3d649a4431863a4440d9ae87b94dd0eaae32acc'
RETAINED = ('vmacc-toggle-gain774.json', 'retained-itlb-toggle-gain.json', 'vfirst-toggle-gain775.json')


def qualification(q, closure):
    require(q['status'] == 'AKV_ENTROPY_NATIVE_INDEPENDENT_QUALIFIED_NOT_ADMITTED' and
            q['baseline_tests'] == 775 and q['coverage_admitted'] is False and
            q['native_Spike_comparison'] is False and q['software_adapter_not_native'] is True and
            type(q['scalar_model_skips']) is int and q['scalar_model_skips'] == 0,
            'Exact bounded native qualification, not native Spike')
    require(closure['status'] == 'ORIGINAL_FULL_COLLECT_PASS_MANIFEST_ORDER_CLOSURE' and
            closure['original_qualification'] == str(QUAL / 'qualification.json') and
            closure['original_qualification_sha256'] == Q_SHA and
            closure['prepared_sha256'] == PREPARED_SHA and closure['actual_manifest_sha256'] == ACTUAL_SHA and
            closure['original_input_pins'] == q['input_pins'] and
            closure['original_output_pins'] == q['output_pins'] and
            closure['coverage_admitted'] is False and closure['EDA_launched'] is False,
            'Exact manifest-order bridge closure')
    for name, key in (('collect_akv_entropy_manifest.py', 'wrapper_sha256'),
                      ('test_collect_akv_entropy_manifest.py', 'tests_sha256')):
        path = Path(__file__).with_name(name)
        require(closure['input_pins'].get(str(path)) == closure[key], 'Bridge dependency omitted')
    for inventory in (q['input_pins'], q['output_pins']):
        require(all(closure['input_pins'].get(p) == h for p, h in inventory.items()),
                'Closure omitted qualified input/output')


def native_identity(sim, args, command, design):
    tests = sim.findall('srctest')
    require(sim.tag == 'test' and len(tests) == 1, 'One native test identity')
    t = tests[0]
    require(shlex.split(t.get('cmdline', '')) == command and t.get('workdir') == str(RUN) and
            t.get('seed') == '1' and t.get('teststatus') == 'unknown',
            'Exact native command/workdir/seed; XML unknown is not PASS')
    require(t.get('starttime') == '1791437363665491' and t.get('finishtime') == '1791437616152178',
            'Exact observed native duration identity')
    require(args.tag == 'vcm_args' and args.get('compvdbpath') == design and
            sorted(n.get('vcm_opt') for n in args.findall('vcm_arg_data') if n.get('vcm_opt')) ==
            ['-cm branch', '-cm cond', '-cm fsm', '-cm line', '-cm tgl'],
            'Exact compiled VDB and five native metrics')
    return dict(seed=1, workdir=str(RUN), command=command, compvdb=design,
                duration_seconds=252.486687, XML_teststatus='unknown',
                functional_PASS_authority='sealed independent native qualification')


def full_union(before, single):
    require(len(before['tests']) == len(set(before['tests'])) == 776 and
            single['tests'] == [str(RUN / 'code.vdb')] and
            str(RUN / 'code.vdb') not in before['tests'], 'Exact776 plus unique candidate')
    require(set(before['metrics']) == set(single['metrics']) == set(bitmap.METRICS) and
            sum(len(v) for v in before['metrics'].values()) == 6162,
            'All6162 four-metric instances')
    after = bitmap.combine(before, single)
    case.independent_or(before, single, after)
    return after


def rebased_gain(old, added, single):
    scope = case.fixture.SCOPE
    before = toggle.union({scope: old}, added)
    after = toggle.union(before, single)
    b, s, a = before[scope], single[scope], after[scope]
    require(b['checksum'] == '4015856550' and b['width'] == 12374, 'Exact AKV Toggle shape')
    fresh = int(a['bits'], 16) & ~int(b['bits'], 16)
    require(fresh != 0, 'No new Toggle gain against formal776')
    return dict(baseline_tests=776, scope=scope, before=b, single=s, after=a,
                new_positions=bin(fresh).count('1'),
                new_serialized_indices=[i for i in range(b['width']) if fresh >> (b['width']-1-i) & 1],
                serialized_direction_labels_claimed=False, official_percentage_claimed=False,
                historical775_gain_not_recounted=True)


def historical(ledger, authority):
    audit = dedup(ledger, ELF_SHA, authority)
    require(audit['ledger_members'] == 776 and audit['duplicate'] is False and
            [r['vdb'] for r in audit['members']] == ledger[1:] and
            all(authority.get(p) == h for p, h in audit['pins'].items()),
            'Historical776-only ELF/command authority; no candidate inventory')
    return dict(audit, baseline=776)


def evaluate():
    base = life.read_bound(BASE / 'admission-manifest.json', BASE_SHA)
    require(base['coverage_admitted'] is True and base['output'] == str(BASE), 'Formal776 authority')
    q = life.read_bound(QUAL / 'qualification.json', Q_SHA)
    closure = life.read_bound(QUAL / 'manifest-order-closure.json', C_SHA)
    qualification(q, closure)
    pins = life.merge_pins(base['input_pins'], base['output_pins'])
    pins = life.merge_pins(pins, closure['input_pins'])
    def base_doc(name):
        p = BASE / name
        return life.read_bound(p, base['output_pins'][str(p)])
    def product(name):
        p = QUAL / name
        return life.read_bound(p, q['output_pins'][str(p)])
    status = base_doc('status.json')
    require(status['aggregate_passed'] == 776 and status['coverage_admitted'] is True and
            status['exact775_prefix'] is True and status['full_OR_metric_instances'] == 6162,
            'Sealed776 prefix/fullOR status')
    before = base_doc('combined-bits.json')
    ledger = (BASE / 'combined-inputs.txt').read_text().splitlines()
    require(len(ledger) == len(set(ledger)) == 777 and ledger[1:] == before['tests'], 'Exact776 ledger')
    life.check(pins)
    manifest = life.read_bound(RUN / 'manifest.json', ACTUAL_SHA)
    record = RUN.with_name(RUN.name + '.prepared.json')
    preloads = [s.split('=', 1)[1] for s in manifest['command'] if s.startswith('+PRELOAD=')]
    require(manifest == life.read_bound(record, PREPARED_SHA) and len(preloads) == 1 and
            manifest['pins'].get(preloads[0]) == ELF_SHA and pins.get(preloads[0]) == ELF_SHA,
            'Exact executed/prepared semantics and ELF')
    single_inputs = QUAL / 'single-inputs.txt'
    require(q['output_pins'].get(str(single_inputs)) == life.digest(single_inputs) and
            single_inputs.read_text().splitlines() == [ledger[0], str(RUN / 'code.vdb')], 'Qualified single inputs')
    # Fresh native data extraction only: never rerun the architecture/model qualification.
    single = bitmap.collect(single_inputs)
    require(single == product('single-bits.json') and
            all(pins.get(p) == h for p, h in single['input_hashes'].items()), 'Fresh sealed singleton equality')
    for relative, h in single['design'].items():
        p = str(Path(ledger[0]) / 'snps/coverage/db' / relative)
        require(pins.get(p) == h, 'Bound compatible compiled input')
    after = full_union(before, single)
    delta = bitmap.delta(before, after)
    folder = RUN / 'code.vdb/snps/coverage/db/testdata/akv_descriptor_entropy'
    require(list(folder.parent.iterdir()) == [folder], 'One exact native testcase')
    def xml(p):
        require(pins.get(str(p)) == life.digest(p), 'Unbound native XML')
        data = p.read_bytes()
        return ET.fromstring(gzip.decompress(data) if data[:2] == b'\x1f\x8b' else data)
    identity = native_identity(xml(folder / 'siminfo.xml'), xml(folder / 'vcmArguments.xml'),
                               manifest['command'], ledger[0])
    old_gain = product('toggle-gain775.json')
    require(old_gain['baseline_tests'] == 775 and old_gain['scope'] == case.fixture.SCOPE and
            product('combined-bits-diagnostic.json')['tests'][:-1] == before['tests'][:-1],
            'Qualified775 scope prefix plus formal776 last member')
    def sample(vdb, authority):
        files = list((Path(vdb) / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(files) == 1, 'One Toggle XML per member')
        rows, sha = toggle.rows(files[0], [case.fixture.SCOPE])
        require(authority.get(str(files[0])) == sha, 'Sealed Toggle member')
        return rows
    added = sample(before['tests'][-1], base['input_pins'])
    t_single = sample(str(RUN / 'code.vdb'), pins)
    require(t_single[case.fixture.SCOPE] == old_gain['single'], 'Qualified native Toggle singleton')
    gain = rebased_gain(old_gain['before'], added, t_single)
    elf = historical(ledger, base['input_pins'])
    pins = life.merge_pins(pins, elf['pins'])
    fixed = {str(BASE / 'admission-manifest.json'): BASE_SHA,
             str(QUAL / 'qualification.json'): Q_SHA, str(QUAL / 'manifest-order-closure.json'): C_SHA,
             str(record): PREPARED_SHA, str(RUN / 'manifest.json'): ACTUAL_SHA}
    for p in (Path(__file__).resolve(), Path(__file__).with_name('test_admit_akv_entropy777.py')):
        fixed[str(p)] = life.digest(p)
    for module in (case, bitmap, toggle, toggle.base, life):
        p = str(Path(module.__file__).resolve())
        require(pins.get(p) == life.digest(p), 'Unbound reused helper')
    require(pins.get(str(Path(dedup.__code__.co_filename).resolve())) ==
            life.digest(Path(dedup.__code__.co_filename)), 'Unbound historical dedup helper')
    pins = life.merge_pins(pins, fixed)
    life.check(pins)
    products = {name: base_doc(name) for name in RETAINED}
    products.update({'combined-bits.json': after, 'single-bits.json': single, 'raw-delta.json': delta,
        'akv-toggle-gain776.json': gain, 'native-vdb-identity.json': identity,
        'elf-ledger-dedup.json': elf, 'evidence-pins.json': pins,
        'status.json': dict(status='PASS_RAW_UNION_HISTORICAL_ONLY', aggregate_passed=777,
            baseline=776, new_passed=1, coverage_admitted=True, exact776_prefix=True,
            full_OR_metric_instances=6162, unique_new_vdb=True, duplicate_ELF=False,
            scoped_toggle_new_serialized_positions=gain['new_positions'], raw_delta=delta['metrics'],
            prior_gain_records_retained_not_recounted=True, native_Spike_comparison=False,
            independent_native_qualification=True, XML_teststatus='unknown',
            official_percentage_claimed=False, new_simulation=False, RTL_changed=False)})
    return products, '\n'.join([ledger[0], *after['tests']]) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'verify', 'admit'))
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--seal'); parser.add_argument('--parent-authorized', action='store_true')
    args = parser.parse_args(); out = args.output.resolve()
    require(args.parent_authorized == (args.mode == 'admit'), 'Explicit parent admission only')
    require(bool(args.seal) == (args.mode != 'prepare'), 'Prepared seal required')
    require(out.parent == life.OUT and not out.exists(), 'Fresh777 output')
    products, text = evaluate()
    hashes = {str(out / n): hashlib.sha256((json.dumps(v, indent=2)+'\n').encode()).hexdigest()
              for n, v in products.items()}
    for name in ('combined-inputs.txt', 'generic-coverage-inputs.txt'):
        hashes[str(out / name)] = hashlib.sha256(text.encode()).hexdigest()
    proposal = dict(output=str(out), baseline=str(BASE), baseline_seal=BASE_SHA,
        qualification=str(QUAL / 'qualification.json'), qualification_seal=Q_SHA,
        closure_seal=C_SHA, input_pins=products['evidence-pins.json'], output_pins=hashes,
        coverage_admitted=False)
    record = out.with_name(out.name+'.prepared.json')
    if args.mode == 'prepare':
        life.save(record, proposal); print('PREPARED777_NOT_ADMITTED', life.digest(record)); return
    require(life.read_bound(record, args.seal) == proposal, 'Prepared777 drift')
    if args.mode == 'verify': print('VERIFY_PASS_NO_ADMISSION'); return
    out.mkdir()
    for name, value in products.items(): life.save(out / name, value)
    for name in ('combined-inputs.txt', 'generic-coverage-inputs.txt'):
        with (out / name).open('x') as stream: stream.write(text)
    life.check(proposal['input_pins']); life.check(hashes)
    life.save(out / 'admission-manifest.json', dict(proposal, coverage_admitted=True,
        prepared=str(record), prepared_seal=args.seal,
        authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL'))
    print('ADMITTED777', life.digest(out / 'admission-manifest.json'))


if __name__ == '__main__': main()
