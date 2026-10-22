"""Fresh formal773 report consumer plus exact Branch720; prepare is offline only."""
import argparse
import copy
import csv
import io
import json
from pathlib import Path
import re
from types import FunctionType
import branch720_next_report_contract as branch
import report_dispatcher_four_union762 as stdout_contract
import verify_full771_pack_owner_offline as owner
from fsm741_transition_native import tcl_atom

frozen, life, require = owner.frozen, owner.life, owner.require
HERE = Path(__file__).resolve().parent
TCL = Path(__file__).with_suffix('.tcl')
SCHEMA = 'FORMAL773_CLOSED771_PLUS_EXACT_BRANCH720_V1'
MANIFEST = life.OUT / 'sv39-fault-alternating-offline-admitted-773-agent-20261007-01/admission-manifest.json'
MANIFEST_SHA = '65710f130e698571f9e17800e57361b0baa2a9d407a02287409797de64f64060'
QUAL = life.OUT / 'native-full771-pack-owner-offline-closure-agent-20261007-01/qualification.json'
QUAL_SHA = '5cb90569a4cde0cfaa8dc064269f90cb2eb9c20a88c732fbaf7b615e1b1b29fd'
CLOSURE_SHA = 'b26e3f1a721ad71323ac7e4ae699205ea4a4d74578c5fa657e0324307c7ed752'
CONTRACT = life.OUT / 'branch720-next-report-contract-772-agent-20261007-01/contract.json'
CONTRACT_SHA = '316c8546bf0256b09cdececde3182c7ecd89d53300a1b39bbba7c55c0939a5c5'
BASE772 = branch.subset.BASE / 'admission-manifest.json'


def merge(*books):
    result = {}
    for book in books:
        for path, sha in book.items():
            require(path not in result or result[path] == sha, 'Conflicting exact pins: ' + path)
            result[path] = sha
    return result


def population(manifest, previous, bits, previous_bits, single, ledger, old_ledger):
    require(manifest['coverage_admitted'] is True and manifest['output'] == str(MANIFEST.parent) and
            manifest['baseline'] == str(BASE772.parent) and manifest['baseline_seal'] == branch.subset.BASE_SHA,
            'Exact formal772->773 admission')
    require(previous['coverage_admitted'] is True and previous['baseline'] == str(frozen.MANIFEST.parent) and
            previous['baseline_seal'] == frozen.MANIFEST_SHA, 'Exact formal771->772 admission')
    require(len(bits['tests']) == len(set(bits['tests'])) == 773 and
            len(previous_bits['tests']) == len(set(previous_bits['tests'])) == 772 and
            bits['tests'][:-1] == previous_bits['tests'] and ledger == [old_ledger[0], *bits['tests']] and
            ledger[:-2] == old_ledger, 'Exact complete771 prefix and unique773 population')
    require(bits['design'] == previous_bits['design'], 'Same frozen design')
    require(single['design'] == bits['design'] and single['tests'] == bits['tests'][-1:], 'Exact single773')
    require(set(bits['metrics']) == set(previous_bits['metrics']) == set(single['metrics']) and
            sum(len(v) for v in bits['metrics'].values()) == 6162, 'Complete metric instance shape')
    for metric, rows in previous_bits['metrics'].items():
        require(set(bits['metrics'][metric]) == set(rows) == set(single['metrics'][metric]), 'Missing/extra metric scope')
        for scope, old in rows.items():
            new = bits['metrics'][metric][scope]
            sample = single['metrics'][metric][scope]
            require((new['width'], new['checksum']) == (old['width'], old['checksum']) ==
                    (sample['width'], sample['checksum']) and
                    int(new['bits'], 16) == (int(old['bits'], 16) | int(sample['bits'], 16)),
                    'Shape/monotone union differs')


def fresh_targets(audit, bits):
    for point in audit['targets']:
        row = bits['metrics']['branch'][point['scope']]
        require(row['width'] == 101 and row['checksum'] in (None, '1417162425') and
                not (int(row['bits'], 16) & (1 << (100 - point['raw_index']))),
                'Branch720 target hit/shape drift at773')


def nonbranch_text(text):
    result = []
    for block in re.split(r'(?m)(?=^CHECKSUM:)', text):
        lines = [line for line in block.splitlines() if not line.startswith('Branch ')]
        directives = [line for line in lines if line.startswith(('Toggle ', 'Fsm ', 'Transition ', 'State '))]
        originally_branch = any(line.startswith('Branch ') for line in block.splitlines())
        if lines and (directives or not originally_branch):
            result.append('\n'.join(lines) + '\n')
    return ''.join(result)


def records(text, c):
    branch.check_stage_el(text.encode('ascii'), 'applied', Path(c['canonical_EL']['path']).read_bytes(),
                          c['branch720']['expected_native'])
    view = dict(c, output=str(owner.OUT))
    return frozen.model()['records'](nonbranch_text(text), view)


def observers(out, c):
    oc = life.read_bound(Path(c['future_captures']['c910240']['output']) / 'config.json', owner.OWNER_CONFIG)
    bindings = owner.native.source_bindings(oc)
    original = frozen.model()['merged_observers'](c)
    groups, proof, _ = owner.corrected_groups(original, oc['instances'], bindings,
                    {tuple(r) for r in c['expected_union']['c910240']})
    for name in ('applied.el', 'reloaded.el'):
        require(records((out / name).read_text(), c) == c['expected_union'], 'Complete native EL union')
    frozen.base.prior.audit_observers(out, dict(c, observer_captures=groups))
    for stage in branch.STAGES:
        name = 'initial' if stage == 'raw' else stage
        branch.check_stage_rows((out / ('states_' + name + '.tsv')).read_bytes(), stage, c['branch720'])
    return proof


def selection(original, contract):
    atom = tcl_atom
    text = original + '\nset ::op1144_scopes [list %s]\n' % ' '.join(map(atom, contract['scopes']))
    for scope in contract['scopes']:
        points = [p for p in contract['branch_inventory'] if p['scope'] == scope]
        for variable, values in [('op1144_keys', [p['selector'] for p in points]),
                                 ('op1144_targets', [p['selector'] for p in points if p['target']])]:
            text += 'set ::%s(%s) [list %s]\n' % (variable, scope, ' '.join(map(atom, values)))
    return text


def check(out, seal):
    c = life.read_bound(out / 'config.json', seal)
    require(c['schema'] == SCHEMA and c['output'] == str(out) and c['population'] == 773 and
            c['successor_entry'] == str(Path(__file__).resolve()) and
            c['admission']['manifest'] == str(MANIFEST) and c['admission']['seal'] == MANIFEST_SHA and
            c['runtime_timeout_seconds'] == 5400 and c['runtime_apply_authorized'] is True,
            'Exact773 identity/lifecycle')
    old = life.read_bound(owner.OUT / 'config.json', owner.SEAL)
    changed = {'schema', 'output', 'population', 'successor_entry', 'admission', 'input_ledger',
               'expected_selected', 'pins', 'hierarchy_roots', 'canonical_EL', 'branch720', 'predecessor_full_qualification'}
    require(all(c.get(k) == v for k, v in old.items() if k not in changed), 'Retained policies/config changed')
    life.check(c['pins'])
    audit = life.read_bound(branch.AUDIT, branch.AUDIT_SHA)
    contract = life.read_bound(CONTRACT, CONTRACT_SHA)
    expected = branch.validate_subset(audit, (branch.AUDIT.parent / 'candidate720.el').read_bytes())
    require(c['branch720'] == dict(contract, expected_native=expected), 'Exact reviewed Branch720 contract only')
    roots = copy.deepcopy(old['hierarchy_roots'])
    for scope in contract['scopes']:
        if not any(r['scope'] == scope for r in roots): roots.append(dict(scope=scope, name=scope.split('.')[-1]))
    require(c['hierarchy_roots'] == roots and c['canonical_EL'] ==
            dict(path=str(owner.OUT / 'combined.el'), sha256=old['pins'][str(owner.OUT / 'combined.el')]),
            'Exact hierarchy/canonical ownership')
    require((out / 'inputs.txt').read_text().splitlines() == c['input_ledger'] and
            len(c['expected_selected']) == len(set(c['expected_selected'])) == 773, 'Exact membership')
    fresh_targets(life.read_bound(branch.AUDIT, branch.AUDIT_SHA),
                  life.read_bound(MANIFEST.parent / 'combined-bits.json',
                    c['pins'][str(MANIFEST.parent / 'combined-bits.json')]))
    require(records((out / 'combined.el').read_text(), c) == c['expected_union'], 'Exact native combined')
    return c


def namespace():
    ns = frozen.namespace()
    def snapshot(data, out):
        c = life.read_bound(out / 'config.json', data['config_seal'])
        stdout_contract.snapshot_stdout(data, out)
        data.update(population=773, admission=c['admission'], formal773_manifest_seal=MANIFEST_SHA,
            qualified_families_unchanged_from_closed771=True, branch720_targets=720, branch720_protected=492,
            expected_branch_denominator_delta=720, official_denominator_verified=False,
            additional_MFPU_or_running_RVH0_included=False,
            observer_owner_reconciliation=dict(existing_family='c910240', objects=48,
                source_qualification_seal=QUAL_SHA, changed_EL_coordinates=0),
            source_first_full_session_qualified=sorted(set(frozen.old.frozen.frozen.inherited.FIRST) | {'queue312'}))
    ns.update(check=check, records=records, audit_observers=observers, snapshot_stdout=snapshot,
              TCL=TCL, __file__=__file__)
    for name in ('verify', 'run'):
        ns[name] = FunctionType(ns[name].__code__, ns)
    return ns


def prepare(out):
    require(out.parent == life.OUT and not out.exists(), 'Fresh independent773 output')
    q = life.read_bound(QUAL, QUAL_SHA)
    closed = life.read_bound(QUAL.parent / 'closure.json', CLOSURE_SHA)
    require(closed['status'] == 'FULL771_EXISTING_PACK_OWNER_OFFLINE_CLOSURE_PASS' and
            closed['qualification_sha256'] == QUAL_SHA and closed['changed_EL_coordinates'] == 0 and
            closed['source_directory_unchanged'] is True and q['population'] == 771 and
            q['observer_owner_reconciliation']['unique_existing_objects'] == 48,
            'Exact closed771 source qualification')
    old = life.read_bound(owner.OUT / 'config.json', owner.SEAL)
    manifest = life.read_bound(MANIFEST, MANIFEST_SHA)
    previous = life.read_bound(BASE772, branch.subset.BASE_SHA)
    pins = merge(q['input_pins'], q['output_pins'], q['offline_adapter_pins'], closed['input_pins'],
                 closed['adapter_pins'], manifest['input_pins'], manifest['output_pins'])
    for path, sha in ((QUAL, QUAL_SHA), (QUAL.parent / 'closure.json', CLOSURE_SHA),
                      (owner.OUT / 'config.json', owner.SEAL), (MANIFEST, MANIFEST_SHA),
                      (CONTRACT, CONTRACT_SHA), (branch.AUDIT, branch.AUDIT_SHA)):
        pins = merge(pins, {str(path): sha})
    bits = life.read_bound(MANIFEST.parent / 'combined-bits.json', pins[str(MANIFEST.parent / 'combined-bits.json')])
    prevbits = life.read_bound(BASE772.parent / 'combined-bits.json', pins[str(BASE772.parent / 'combined-bits.json')])
    ledger = (MANIFEST.parent / 'combined-inputs.txt').read_text().splitlines()
    single = life.read_bound(MANIFEST.parent / 'single-bits.json', pins[str(MANIFEST.parent / 'single-bits.json')])
    population(manifest, previous, bits, prevbits, single, ledger, old['input_ledger'])
    status = life.read_bound(MANIFEST.parent / 'status.json', pins[str(MANIFEST.parent / 'status.json')])
    require(status['aggregate_passed'] == 773 and status['coverage_admitted'] is True and
            status['full_OR_instances'] == 6162 and status['exact772_prefix'] is True, 'Formal773 terminal status')
    audit = life.read_bound(branch.AUDIT, branch.AUDIT_SHA)
    contract = life.read_bound(CONTRACT, CONTRACT_SHA)
    candidate = branch.AUDIT.parent / 'candidate720.el'
    require(life.digest(candidate) == audit['output_pins'][str(candidate)], 'Candidate native EL pin')
    expected = branch.validate_subset(audit, candidate.read_bytes())
    fresh_targets(audit, bits)
    canonical = owner.OUT / 'combined.el'
    branch.assert_no_overlap(canonical.read_bytes(), audit)
    pins = merge(pins, audit['pins'], contract['pins'], {str(candidate): life.digest(candidate)})
    selected = [str(Path(db).with_suffix('') / p.name) for db in ledger for p in
                sorted((Path(db) / 'snps/coverage/db/testdata').glob('*')) if p.is_dir()]
    require(len(selected) == len(set(selected)) == 773, 'Exactly one native test per admitted VDB')
    c = copy.deepcopy(old)
    c.update(schema=SCHEMA, output=str(out), population=773, successor_entry=str(Path(__file__).resolve()),
        admission=dict(manifest=str(MANIFEST), seal=MANIFEST_SHA, population=773, exact771prefix=True, full6162_OR=True),
        input_ledger=ledger, expected_selected=selected,
        predecessor_full_qualification=dict(path=str(QUAL), seal=QUAL_SHA),
        canonical_EL=dict(path=str(canonical), sha256=life.digest(canonical)),
        branch720=dict(contract, expected_native=expected))
    for scope in contract['scopes']:
        if not any(r['scope'] == scope for r in c['hierarchy_roots']):
            c['hierarchy_roots'].append(dict(scope=scope, name=scope.split('.')[-1]))
    files = [Path(__file__).resolve(), TCL, HERE / 'test_report_native_full773_branch720.py',
             HERE / 'capture_operand_1144.tcl', Path(branch.__file__).resolve()]
    pins = merge(pins, {str(p): life.digest(p) for p in files})
    life.check(pins)
    generated = selection((owner.OUT / 'selection.tcl').read_text(), contract)
    out.mkdir()
    for name, text in [('combined.el', canonical.read_text() + candidate.read_text()),
                       ('selection.tcl', generated), ('inputs.txt', '\n'.join(ledger) + '\n')]:
        with (out / name).open('x') as stream: stream.write(text)
        pins[str(out / name)] = life.digest(out / name)
    c['pins'] = pins
    life.save(out / 'config.json', c)
    print(json.dumps(dict(status='PREPARED_NO_EDA', output=str(out), seal=life.digest(out / 'config.json'),
                         tests=773, additional_Branch_targets=720, protected_Branch=492,
                         official_denominator_verified=False)), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'check', 'verify', 'run'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal')
    parser.add_argument('--authorize-reviewed-run', action='store_true')
    args = parser.parse_args(); out = args.output.resolve()
    if args.mode == 'prepare': prepare(out)
    else:
        require(args.seal, 'Exact sealed config required')
        if args.mode == 'run': require(args.authorize_reviewed_run, 'Parent launch authorization required')
        namespace()[args.mode](out, args.seal)
