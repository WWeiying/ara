"""Prepare singleton native condition qualification; never launch or approve EDA."""
import argparse
import csv
import json
from pathlib import Path

import prove_mask_store_snapshot_zero as proof
import capture_lzc_batch as native
from closure_point_inventory import points
from lzc_native_records import parse_records
import dve_tool_identity as tool

ROOT, OUT = proof.ROOT, proof.OUT
HERE = Path(__file__).resolve().parent
PROOF = OUT / 'maskm6-sta7-snapshot-zero-proof-724-20261006-01.json'
PROOF_SHA = '672a54dc8cc195c85a986efd0daaff2a58d45e2b8466611d8016279e61468b87'
LATEST = OUT / 'gap105-offline-admitted-725-parent-20261006-01'
LATEST_SHA = '0f49638e8cea36b28b5832e7eaeea39ee9b5249a162de3f3732c0fcd13a5a397'
SIX = OUT / 'branch-combo-six-policy-707-20261006-02/config.json'
SIX_SHA = '9412f766aa75e7099fb3c0b354db655b78b1b6bee3abf39032b81d651128acaa'
CURRENT_SIX = OUT / 'branch-combo-six-policy-population-724-parent-20261006-01/config.json'
CURRENT_SIX_SHA = '32d8deca7e562af7e5e0f8f28768d386772ecfc1c9f3908c193f9d2e5ce0d7cd'
HOOK = HERE / 'capture_mask_store_snapshot_cond24.tcl'
TEST = HERE / 'test_prepare_mask_store_snapshot_cond24.py'
require, digest = proof.require, proof.digest


def coordinate(row):
    return row['scope'], row['metric'], row['point']['raw_index']


def split_candidates(rows):
    require(len(rows) == 32 and len({coordinate(r) for r in rows}) == 32, 'Not exact32 candidates')
    require(all(r['port'] in (6, 7) and not r['hit_before'] for r in rows), 'Foreign/hit candidate')
    selected = [r for r in rows if r['metric'] == 'cond']
    held = [dict(r, decision='HOLD_EXISTING_DEBUG_PROTECTED_NOT_CAPTURE_TARGET')
            for r in rows if r['metric'] == 'branch']
    require(len(selected) == 24 and len(held) == 8, 'Condition/HOLD population differs')
    return selected, held


def groups(candidates, protected):
    selected = {coordinate(r) for r in candidates}
    require(len(selected) == len(candidates) == 24 and
            all(r['metric'] == 'cond' and r['port'] in (6, 7) for r in candidates),
            'Only exact24 condition targets allowed')
    result = {}
    for row in candidates + protected:
        if row['metric'] != 'cond':
            continue
        p = row['point']; t = p['truth_table']
        ncols, nrows = int(t['ncols']), int(t['nrows'])
        require(ncols in (1, 2) and nrows in (2, 3) and len(t['vecs']) == ncols*nrows,
                'Unknown condition table')
        names = [t['vecs'][i*ncols:(i+1)*ncols] for i in range(nrows)]
        require(len(set(names)) == nrows and set(t['vecs']) <= {'0', '1'} and
                p['vector'] in names, 'Invalid vector names')
        k = row['scope'], p['expression']
        g = result.setdefault(k, dict(scope=k[0], expression=k[1], names=names, targets=[]))
        require(g['names'] == names, 'Conflicting condition table')
        if coordinate(row) in selected:
            require(p['vector'] not in g['targets'], 'Duplicate target vector')
            g['targets'].append(p['vector'])
    for g in result.values():
        g['targets'].sort()
        g['retained'] = sorted(set(g['names']) - set(g['targets']))
        require(g['retained'], 'Whole-condition exclusion forbidden')
    rows = [result[k] for k in sorted(result)]
    require(len(rows) == 36 and sum(len(g['targets']) for g in rows) == 24,
            'Incomplete port6/7/8 condition audit')
    return rows


def bind(records, candidates):
    """Bind checksum/expression/vector; DVE condition/vector IDs are observed only."""
    expected = {(r['scope'], r['point']['expression'], r['point']['vector']): r for r in candidates}
    require(len(expected) == len(candidates) == len(records), 'Exact condition population differs')
    ids, vectors = {}, {}
    for r in records:
        key = r['scope'], r['expression'], r['vector']
        require(key in expected, 'Extra/unapproved native vector')
        c = expected.pop(key); attrs = c['point']['attributes']
        require(all(r[k] == v for k, v in dict(module_checksum=c['module_checksum'],
                metric_checksum=c['checksum'], point_checksum=attrs['chksum'],
                width=attrs['width'], bit='-1').items()), 'Compiled native signature differs')
        # Neither an XML row number nor a vector ordering is used as a GUI ID.
        identity = r['scope'], r['native_id']
        require(identity not in ids or ids[identity] == r['expression'], 'Native condition ID alias')
        ids[identity] = r['expression']
        vector_key = identity + (r['vector_id'],)
        require(vector_key not in vectors, 'Native vector ID alias')
        vectors[vector_key] = r['vector']
    require(not expected, 'Missing native vector')


def evidence():
    pins = {}
    def pin(path, expected=None):
        path = Path(path).absolute()
        require(path.resolve() == path and not path.is_symlink(), 'Aliased input')
        sha = digest(path)
        require(expected is None or sha == expected, 'Input pin differs: '+str(path))
        pins[str(path)] = sha
        return path
    original = json.loads(pin(PROOF, PROOF_SHA).read_bytes())
    require(len(original['pins']) == 54, 'Not frozen54 proof pins')
    for path, sha in original['pins'].items():
        pin(path, sha)
    texts = {k: Path(v).read_text() for k, v in original['sources'].items()}
    require(proof.source_contract(**texts) == original['source_contract'], 'Independent source ledger differs')
    manifest = json.loads(pin(LATEST/'admission-manifest.json', LATEST_SHA).read_bytes())
    require(manifest['baseline'] == str(proof.BASE) and manifest['baseline_seal'] ==
            digest(proof.BASE/'admission-manifest.json'), 'Not exact724->725 ancestry')
    def product(name):
        f = LATEST/name
        return pin(f, manifest['output_pins'][str(f)])
    bits = json.loads(product('combined-bits.json').read_bytes())
    old = json.loads((proof.BASE/'combined-bits.json').read_bytes())
    state = json.loads(product('status.json').read_bytes())
    require(state['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY' and state['aggregate_passed'] == 725
            and len(bits['tests']) == len(set(bits['tests'])) == 725 and
            bits['tests'][:-1] == old['tests'] and bits['design'] == old['design'],
            'Not exact formal725 population/design')
    design_vdb = proof.context.old.BUILD/'sim/simv.vdb'
    require(product('combined-inputs.txt').read_text().splitlines() == [str(design_vdb), *bits['tests']],
            'Latest input ledger differs')
    design = proof.context.s.Design(design_vdb)
    candidates, protected = proof.compiled_points(design, bits)
    require(candidates == original['candidates'], 'Latest candidates changed or hit')
    configs = [json.loads(pin(f, sha).read_bytes()) for f, sha in
               ((SIX, SIX_SHA), (CURRENT_SIX, CURRENT_SIX_SHA))]
    require(configs[1]['qualification707_config_sha256'] == SIX_SHA, 'Six-policy qualification link differs')
    candidate_keys = {coordinate(r) for r in candidates}
    all_sets, crosses, compiled = [], [], {}
    for config in configs:
        targets, guards = set(), set()
        for name, group in config['groups'].items():
            if name == 'operand':
                require(len(group['qualified']) == 1144, 'Not exactoperand1144')
                for row in group['qualified']:
                    scope = row['scope']; key = scope, 'branch', row['raw_index']
                    require(key not in targets, 'Duplicate six-policy target')
                    targets.add(key)
                    if scope not in compiled:
                        definition = design.definition(scope, 'branch')
                        mapped = {r['raw_index']: r for r in points('branch', definition,
                                  bits['metrics']['branch'][scope]['width'])}
                        compiled[scope] = definition, mapped
                    definition, mapped = compiled[scope]; point = mapped[row['raw_index']]
                    require(definition.get('chksum') == row['checksum'][1] and
                            design.hierarchy[scope].get('chksum') == row['checksum'][0] and
                            point['attributes']['chksum'] == row['spec_checksum'] and
                            point['native_vector']['vector'] == row['vector'], 'Operand compiled binding differs')
                for scope, tab in group['plan']['scopes'].items():
                    guards.update((scope, 'branch', r['raw_index']) for r in tab['protected'])
            else:
                count = 0
                for scope, tab in group['plan']['scopes'].items():
                    for row in tab['branch']:
                        require(bits['metrics']['branch'][scope]['checksum'] == row['metric_checksum'],
                                'Six-policy shape differs')
                        key = scope, 'branch', row['point']['raw_index']
                        if row['target']:
                            require(key not in targets, 'Duplicate policy target')
                            targets.add(key); count += 1
                        else:
                            guards.add(key)
                require(count == config['coordinate_review']['target_counts'][name], 'Policy population differs')
        require(len(targets) == 5808 and not targets & candidate_keys, 'Duplicate existing waiver candidate')
        all_sets.append(targets); crosses.append(guards & candidate_keys)
    require(all_sets[0] == all_sets[1] and crosses[0] == crosses[1] ==
            {coordinate(r) for r in candidates if r['metric'] == 'branch'}, 'Unexpected protection conflict')
    cond, hold = split_candidates(candidates)
    for r in cond:
        r['module_checksum'] = design.hierarchy[r['scope']].get('chksum')
        require(r['module_checksum'] == '2909207138', 'Requester module checksum differs')
    # Protect original328 plus all8 branch holds; no blanket queue exclusions.
    preserved = protected + hold
    require({coordinate(r) for r in protected} == {coordinate(r) for r in original['protected']},
            'Original protection inventory changed')
    return dict(schema='MASK_STORE_COND24_READONLY_REBIND_725_V1',
        status='READONLY725_EXACT32_DISJOINT_COND24_PREPARE_ONLY', pins=pins,
        proof54_verified=True, original_proof_sha256=PROOF_SHA, baseline=str(LATEST),
        baseline_seal=LATEST_SHA, historical_tests=725, duplicate_targets=0,
        candidate_count=32, condition_capture_count=24, branch_HOLD_count=8,
        candidates=cond, branch_HOLD=hold, original_protected=protected,
        preserved_protected=preserved, groups=groups(cond, preserved),
        selected_sample=bits['tests'][0], design_vdb=str(design_vdb),
        protection_basis='All original328 and8HOLD retained. All condition neighbors queried individually; '
                         'all branch protections enforced by strict condition-only EL allowlist plus3empty stages. '
                         'No per-branch GUI query is claimed.',
        native_selector_status='XML expression/table requests only; not native qualified. Exact mismatch fails; '
                               'no alternative expression, ID or vector ordering guessed.',
        aggregate_application=False, application_approval=False, EDA_started=False)


def save(path, data):
    with Path(path).open('x') as stream:
        json.dump(data, stream, indent=2); stream.write('\n')


def prepare(output):
    output = output.absolute()
    require(output.parent == OUT and output.resolve() == output and not output.exists(), 'Fresh agent output required')
    data = evidence(); pins = data['pins']
    for tree in (Path(data['design_vdb']), Path(data['selected_sample'])):
        for f in sorted(tree.rglob('*')):
            require(not f.is_symlink(), 'Aliased compiled input')
            if f.is_file():
                pins[str(f)] = digest(f)
    testroot = Path(data['selected_sample'])/'snps/coverage/db/testdata'
    tests = sorted(f.name for f in testroot.iterdir() if f.is_dir())
    require(len(tests) == 1, 'Exactly one admitted sample required')
    selected = str(Path(data['selected_sample']).with_suffix('')/tests[0])
    for f in (Path(__file__).resolve(), TEST, HOOK, HERE/'capture_lzc_batch.tcl',
              HERE/'capture_lzc_batch.py', HERE/'lzc_native_records.py',
              HERE/'export_dve_coverage.tcl', HERE/'dve_tool_identity.py'):
        pins[str(f)] = digest(f)
    tool_record = tool.prepare('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/bin/dve', '/usr/bin/xvfb-run')
    for f in tool_record['files']:
        pins[f['path']] = f['sha256']
    for f, sha in pins.items():
        require(digest(f) == sha, 'Input changed during preparation')
    output.mkdir()
    save(output/'readonly-evidence.json', data)
    (output/'inputs.txt').write_text(data['design_vdb']+'\n'+data['selected_sample']+'\n')
    (output/'groups.tcl').write_text(native.group_script(data['groups']))
    config = dict(schema='MASK_STORE_COND24_PREPARED_V1', output=str(output),
        pins=pins, readonly_evidence_sha256=digest(output/'readonly-evidence.json'),
        groups=data['groups'], candidates=data['candidates'],
        preserved_protected=data['preserved_protected'], expected_selected_tests=[selected],
        tool_identity=tool_record, lifecycle=['initial-empty','before','selected','first-export',
            'reset','reset-empty','import-first','reloaded','second-export','final-reset','final-empty'],
        hook=str(HOOK), base_native_hook=str(HERE/'capture_lzc_batch.tcl'),
        exporter=str(HERE/'export_dve_coverage.tcl'),
        future_launch_gate='Parent approval + pinned runtime runner + live descendant executable identity required.',
        future_environment=dict(set_values=dict(DVE_COVERAGE_OUTPUT=str(output),
            DVE_REVIEWED_WAIVERS=str(HOOK), MASK_SNAPSHOT_BASE_TCL=str(HERE/'capture_lzc_batch.tcl'),
            VCS_HOME=tool_record['environment']['VCS_HOME'], VCS_TARGET_ARCH='linux64'),
            remove=['DVE','ENV','BASH_ENV','LD_PRELOAD','LD_AUDIT']),
        GUI_condition_IDs='Observed from actual first.el; never inferred from compiled row IDs.',
        qualification_only=True, application_approval=False, launch_supported=False)
    for f in ('readonly-evidence.json','inputs.txt','groups.tcl'):
        config['pins'][str(output/f)] = digest(output/f)
    save(output/'config.json', config)
    return dict(output=str(output), seal=digest(output/'config.json'),
                evidence_seal=digest(output/'readonly-evidence.json'), status='PREPARED_NO_LAUNCH')


def read_config(output, seal):
    output = output.absolute(); f = output/'config.json'
    require(digest(f) == seal, 'Prepared seal differs')
    c = json.loads(f.read_bytes())
    require(c['output'] == str(output) and c['schema'] == 'MASK_STORE_COND24_PREPARED_V1' and
            c['launch_supported'] is False and c['application_approval'] is False, 'Prepared scope differs')
    for path, sha in c['pins'].items():
        require(digest(path) == sha, 'Prepared pin differs: '+path)
    return c


def verify_artifacts(output, config):
    first = parse_records((output/'first.el').read_text())
    second = parse_records((output/'second.el').read_text())
    bind(first, config['candidates']); bind(second, config['candidates'])
    require(sorted(first, key=lambda r: (r['scope'],r['expression'],r['vector'])) ==
            sorted(second, key=lambda r: (r['scope'],r['expression'],r['vector'])), 'Native roundtrip differs')
    for name in ('initial-empty.el','reset-empty.el','final-empty.el'):
        require(parse_records((output/name).read_text()) == [], 'Nonempty reset evidence')
    with (output/'neighbor-audit.csv').open(newline='') as stream:
        reader = csv.DictReader(stream); actual = list(reader)
        require(reader.fieldnames == native.AUDIT_COLUMNS, 'Audit columns differ')
    expected = []
    for stage in native.STAGES:
        for g in config['groups']:
            expected.append(dict(zip(native.AUDIT_COLUMNS, [stage,g['scope'],g['expression'],
                ' '.join(g['names']),' '.join(g['targets']),' '.join(g['retained']),
                str(len(g['targets']) if stage in ('selected','reloaded') else 0),'0'])))
    require(actual == expected, 'Target/protection audit differs')
    require((output/'selected_tests.txt').read_text().splitlines() == config['expected_selected_tests'],
            'Capture actual sample selection differs')
    lines = (output/'DVEfiles/dve_gui.log').read_text().splitlines()
    require(lines.count('MASK_STORE_COND24_CAPTURE_DONE 24') == lines.count('DVE_COVERAGE_EXPORT_DONE') == 1
            and not any('FAILED' in line for line in lines), 'GUI lifecycle incomplete')
    return dict(status='FORMAT24_ROUNDTRIP_NOT_APPLICATION_APPROVAL', records=24, final_reset=True,
                full_protected_allowlist=True, per_branch_GUI_audit=False,
                application_approval=False, captured_native_IDs=first)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare','check','verify-format'))
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--seal')
    a = parser.parse_args()
    if a.mode == 'prepare':
        require(a.seal is None, 'Prepare does not accept existing seal')
        print(json.dumps(prepare(a.output)))
    else:
        require(a.seal, 'Seal required')
        config = read_config(a.output, a.seal)
        print(json.dumps(dict(status='PREPARED_CHECK_PASS_NO_LAUNCH') if a.mode == 'check'
                         else verify_artifacts(a.output, config)))


if __name__ == '__main__':
    main()
