"""Nine-policy backend and data contract; no configuration preparation or launch."""
import argparse
import ast
import csv
import inspect
import json
from pathlib import Path
import re
import sys
from types import SimpleNamespace

import lzc_snapshot_eight_policy_runtime as eight
import capture_rvh_branch_full_empty_v2 as rvh
import closure_point_inventory as inventory

frozen, require = eight.frozen, eight.require
SCRIPT = Path(__file__).resolve()
TCL = SCRIPT.with_suffix('.tcl')
TEST = SCRIPT.with_name('test_rvh_nine_policy_runtime.py')
EIGHT_SHA = 'ccd7b4f6e25da2571ae8bb2d57a385bbed8f9be08a1f81703fb904c7b3cd9580'
EIGHT_TCL_SHA = '0caf7e4ee810238b1495b4f122caa0123a6991b0973aa669774d49c3d3fc2a1c'
RVH_REVIEW_SHA = 'ff85648ed6ad98aab4a0e2dc980488594eaa338b6bd02b6581199e4eb49f520c'
RVH_EL_SHA = 'acd42ddcf86a258491960e29ccc8ce2ea47f2f916fd8df8999276a1102ef068e'
STAGES = eight.STAGES
COLUMNS = ['scope', 'metric', 'coordinate', 'meta', 'path', 'excluded']


def immutable_eight():
    require(frozen.sha(eight.SCRIPT) == EIGHT_SHA and frozen.sha(eight.TCL) == EIGHT_TCL_SHA,
            'Frozen eight backend changed')


def dependencies():
    return (SCRIPT,TCL,TEST,eight.SCRIPT,eight.TCL,Path(eight.metric.__file__).resolve(),
            Path(rvh.__file__).resolve(),Path(rvh.frozen.__file__).resolve(),
            Path(rvh.frozen.pilot.__file__).resolve(),Path(rvh.frozen.debug.__file__).resolve(),
            Path(inventory.__file__).resolve(),Path(sys.executable).resolve(strict=True))


def eight_library():
    immutable_eight()
    boundary = 'set failed [catch {eight_initialize; qbsapp_session} message]\n'
    source = eight.TCL.read_text()
    require(source.count(boundary) == 1, 'Eight library boundary changed')
    return source.split(boundary)[0]


def sources(contract):
    result = {}
    for name, ref in contract['sources'].items():
        path = Path(ref['path'])
        require(path.is_file() and not path.is_symlink() and frozen.sha(path) == ref['sha256'],
                'Native source drift: '+name)
        result[name] = path.read_bytes()
    require(set(result) == {'six', 'lzc', 'snapshot', 'rvh'}, 'Wrong policy streams')
    return result


def capture_config(contract):
    ref = contract['rvh_capture_config']
    return frozen.load_sealed(Path(ref['path']), ref['sha256'])


def partition(raw, contract):
    approved = sources(contract)
    parts = eight.route(raw, approved)
    capture = capture_config(contract)
    require(rvh.frozen.bind_native(parts['rvh'], capture) ==
            rvh.frozen.bind_native(approved['rvh'], capture), 'RVH exact247 signature differs')
    runtime=frozen.load_sealed(Path(contract['eight_output'])/'runtime-plan.json',contract['eight_seal'])
    config=frozen.load_sealed(Path(runtime['six_output'])/'config.json',runtime['six_config_sha256'])
    eight.split_bind(b''.join(parts[n] for n in ('six','lzc','snapshot')),config,
                     {n:approved[n] for n in ('six','lzc','snapshot')},runtime['snapshot_candidates'])
    return parts


def eight_fragment(raw, contract):
    approved = sources(contract)
    identities = {key for name, data in approved.items() if name != 'rvh'
                  for key, _ in eight.metric.blocks(data)}
    # Preserve cross-policy order of the original eight stream, not just each group.
    return b''.join(chunk for key, chunk in eight.metric.blocks(raw) if key in identities)


def split_bind(raw, config, old_sources, candidates, states=None):
    contract = config['rvh9_contract']
    parts = partition(raw, contract)
    return eight.split_bind(b''.join(parts[n] for n in ('six', 'lzc', 'snapshot')),
                            config, old_sources, candidates, states)


def roundtrip(left, right, contract):
    partition(left, contract)
    partition(right, contract)
    require(eight_fragment(left, contract) == eight_fragment(right, contract),
            'Original eight export bytes/order changed')
    return True


def branch_change_allowed(scope, metric, target_scopes):
    return metric in ('Branch', 'Score') and any(
        s == scope or s.startswith(scope+'.') for s in target_scopes)


def audit_rows(rows, expected, targets, active):
    got = {}
    require(targets <= expected.keys(), 'Target absent from inventory')
    for row in rows:
        require(set(row) == set(COLUMNS), 'Malformed RVH row fields')
        key = row['scope'], row['metric'], row['coordinate']
        require(key in expected and key not in got and row['metric'] == 'branch',
                'Extra/duplicate/wrong-metric RVH row')
        require((row['meta'], row['path']) == expected[key], 'Measured RVH binding changed')
        require(row['excluded'] == str(int(active and key in targets)),
                'RVH target/protected singleton differs')
        got[key] = expected[key]
    require(got == expected, 'Incomplete RVH inventory')
    return got


def audit_states(path, contract, stage):
    require(stage in STAGES and path.is_file() and not path.is_symlink(), 'Invalid RVH stage/file')
    expected = {(r[0], 'branch', r[1]): (r[2], r[3]) for r in contract['native_rows']}
    targets = {(r[0], 'branch', r[1]) for r in contract['native_rows'] if r[4]}
    require(len(expected) == 1780 and len(targets) == 247, 'Wrong measured247/1780 inventory')
    with path.open(newline='') as stream:
        reader = csv.DictReader(stream, delimiter='\t')
        require(reader.fieldnames == COLUMNS, 'RVH audit header differs')
        rows = list(reader)
    return audit_rows(rows, expected, targets, stage in ('selected', 'reloaded', 'after-root'))


def build_contract(eight_output, eight_seal, review_output, review_seal):
    """Read-only data assembly; future prepare must hash all inherited pins again."""
    immutable_eight()
    runtime = frozen.load_sealed(eight_output/'runtime-plan.json', eight_seal)
    require(runtime['schema'] == 'lzc-snapshot-eight-explicit-population-v1' and
            runtime['population'] >= 727 and (runtime['targets'], runtime['protected'], runtime['audited']) ==
            (5892, 17774, 23666), 'Explicit latest eight plan required')
    six = frozen.load_sealed(Path(runtime['six_output'])/'config.json', runtime['six_config_sha256'])
    require(six['population'] == runtime['population'] and
            six['admission_manifest_sha256'] == runtime['admission_sha256'], 'Population relabel forbidden')
    seal = frozen.load_sealed(review_output/'seal.json', review_seal)
    for p, h in seal['output_pins'].items(): require(frozen.sha(p) == h, 'RVH reviewed output drift')
    review = frozen.load_sealed(review_output/'review-receipt.json', RVH_REVIEW_SHA)
    require(review['status'] == 'LIMITED_NATIVE_ROUNDTRIP_REVIEWED_NOT_APPLICATION' and
            (review['exact_records'], review['protected_branch_positions'], review['inventory']) == (247,1533,1780)
            and review['measurement_sample_population'] == 725 and review['final_reset'] is True and
            review['native_record_signature_parity'] is True and all(review[k] is False for k in
                ('application_approval', 'native_el_applied', 'population727_application',
                 'condition_or_other_metric_qualification', 'native_EL_byte_stability_general_claim')),
            'Limited RVH review contract differs')
    capture_path = Path(review['capture_directory'])/'config.json'
    capture = frozen.load_sealed(capture_path, review['config_seal'])
    require(capture['plan']['design_vdb'] == six['inputs'][0], 'Different compiled design')
    bits = json.loads((Path(six['admitted_base'])/'combined-bits.json').read_bytes())
    manifest = frozen.load_sealed(Path(six['admitted_base'])/'admission-manifest.json', runtime['admission_sha256'])
    bp = str(Path(six['admitted_base'])/'combined-bits.json')
    require(frozen.sha(bp) == manifest['output_pins'][bp], 'Latest bitmap not sealed')
    design = eight.seven.proof.Design(Path(six['inputs'][0]))
    measured = rvh.frozen.audit_states(Path(review['capture_directory'])/'states_before.tsv', capture, 'before')
    rows = []
    for scope, metrics in capture['plan']['scopes'].items():
        record = bits['metrics']['branch'][scope]
        definition = design.definition(scope, 'branch')
        require(inventory.points('branch',definition,record['width']) == [r['point'] for r in metrics['branch']]
                and definition.get('chksum') == record['checksum'], 'Latest RVH complete shape changed')
        for row in metrics['branch']:
            require(row['module_checksum'] == design.hierarchy[scope].get('chksum') and
                    row['metric_checksum'] == definition.get('chksum') and type(row['target']) is bool,
                    'RVH module/metric/target identity differs')
            raw = row['point']['raw_index']
            require(not row['target'] or not(int(record['bits'],16) & (1 << (record['width']-1-raw))),
                    'New population hits RVH target: HOLD')
            meta, path = measured[scope,'branch',row['coordinate']]
            rows.append([scope,row['coordinate'],meta,path,row['target']])
    old_scopes = set(six['scope_owners'])
    lzc_plan = frozen.load_sealed(Path(runtime['seven_output'])/'application-plan.json',runtime['seven_plan_sha256'])
    old_scopes.update(r['scope'] for r in lzc_plan['exact_lzc_protection_rows'])
    old_scopes.update(g['scope'] for g in runtime['snapshot_groups'])
    require(not old_scopes & capture['plan']['scopes'].keys(), 'Target/protection cross-scope overlap needs review')
    refs = dict(six=Path(runtime['six_output'])/'combined.el', lzc=eight.SOURCE_PROOF/'candidate60.el',
                snapshot=eight.MASK_EL, rvh=review_output/'limited-native-247.el')
    require(frozen.sha(refs['rvh']) == RVH_EL_SHA, 'RVH native copy changed')
    require(len(rows) == 1780 and sum(r[4] for r in rows) == 247 and len(capture['plan']['scopes']) == 14,
            'Wrong RVH complete inventory')
    contract = dict(schema='RVH_NINE_POLICY_DATA_CONTRACT_V1', population=runtime['population'],
        admission_sha256=runtime['admission_sha256'], eight_output=str(eight_output), eight_seal=eight_seal,
        rvh_review=str(review_output), rvh_review_seal=review_seal,
        rvh_capture_config=dict(path=str(capture_path),sha256=review['config_seal']),
        sources={k:dict(path=str(p),sha256=frozen.sha(p)) for k,p in refs.items()}, native_rows=rows,
        rvh_target_scopes=sorted({r[0] for r in rows if r[4]}), targets=6139,protected=19307,audited=25446,
        stages=list(STAGES),state_checks=25446*6,application_approval=False,launch_supported=False,
        full_EL_byte_parity_required=False,eight_fragment_byte_parity_required=True,
        rvh_signature_parity_required=True,official_denominator_verified=False,
        callback_dependencies={str(p):frozen.sha(p) for p in dependencies()},
        python=dict(path=str(Path(sys.executable).resolve(strict=True)),
                    sha256=frozen.sha(Path(sys.executable).resolve(strict=True))))
    partition(b''.join(sources(contract).values()),contract)
    return contract


def selection_payload(contract, callback_seal):
    require(re.fullmatch('[0-9a-f]{64}',callback_seal or ''), 'Sealed callback contract required')
    by_scope = {}
    for scope, coordinate, meta, path, target in contract['native_rows']:
        by_scope.setdefault(scope,[]).append((coordinate,meta,path,target))
    literal = eight.prior.lifecycle.literal
    keys, targets, expected = [], [], []
    for scope, rows in sorted(by_scope.items()):
        keys.extend((literal(scope),literal(' '.join(r[0] for r in rows))))
        targets.extend((literal(scope),literal(' '.join(r[0] for r in rows if r[3]))))
        for coordinate,meta,path,_ in rows:
            expected.extend((literal(scope+'|'+coordinate),literal(meta+' '+path)))
    return ('namespace eval rvh9 {\nvariable scopes {'+' '.join(literal(s) for s in sorted(by_scope))+'}\n'
        'variable keys; array set keys {'+' '.join(keys)+'}\n'
        'variable targets; array set targets {'+' '.join(targets)+'}\n'
        'variable expected; array set expected {'+' '.join(expected)+'}\n'
        'variable driver '+literal(str(SCRIPT))+'\nvariable python '+literal(contract['python']['path'])+
        '\nvariable callback_seal '+literal(callback_seal)+'\n}\n')


def adapted_eight_verifier(read_config):
    immutable_eight()
    tree = ast.parse(inspect.getsource(eight.verify))
    needle = ast.parse("f.read_bytes()==(output/'applied.el').read_bytes()",mode='eval').body
    class Adapter(ast.NodeTransformer):
        changed = 0
        def visit_Compare(self,node):
            if ast.dump(node) == ast.dump(needle):
                self.changed += 1
                return ast.copy_location(ast.parse("nine_roundtrip(f.read_bytes(),(output/'applied.el').read_bytes(),config)",mode='eval').body,node)
            return self.generic_visit(node)
    adapter=Adapter();tree=adapter.visit(tree)
    require(adapter.changed == 1, 'Frozen eight byte gate boundary changed')
    active_contract=None
    def verifier(namespace,allow):
        def extended(scope,metric,active):
            require(active_contract is not None,'Missing successor contract')
            return allow(scope,metric,active) or branch_change_allowed(scope,metric,active_contract['rvh_target_scopes'])
        return eight.prior.seven_verifier(namespace,extended)
    proxy=SimpleNamespace(**vars(eight.prior));proxy.seven_verifier=verifier
    def read(path,seal):
        nonlocal active_contract
        ctx,cfg=read_config(path,seal);active_contract=cfg['rvh9_contract'];return ctx,cfg
    namespace=dict(eight.__dict__,read_config=read,split_bind=split_bind,prior=proxy,
                   nine_roundtrip=lambda l,r,c:roundtrip(l,r,c['rvh9_contract']))
    exec(compile(ast.fix_missing_locations(tree),str(SCRIPT),'exec'),namespace)
    return namespace['verify']


def verify_successor(output,seal,read_config):
    result=adapted_eight_verifier(read_config)(output,seal)
    _,cfg=read_config(output,seal);contract=cfg['rvh9_contract']
    log=(output/'DVEfiles/dve_gui.log').read_text()
    require(not re.search(r'NINE_(FAILED|ERROR)',log),'Nine session failed')
    extra=[]
    for stage in STAGES:
        path=output/'rvh'/('states_'+stage+'.tsv');audit_states(path,contract,stage);extra.append(path)
        for marker in ('NINE_RVH_AUDIT %s 1780'%stage,'NINE_FULL_AUDIT %s 25446'%stage):
            require(log.splitlines().count(marker)==1,'Incomplete nine audit: '+marker)
    for marker in ('NINE_RUNTIME_INSTALLED','NINE_CALLBACK_EXACT6139_SIGNATURE_PASS',
                   'NINE_ACTUAL_RELOAD_SIGNATURE6139','NINE_DONE_EXACT6139'):
        require(log.splitlines().count(marker)==1,'Missing nine completion')
    result.update(status='HISTORICAL_NINE_POLICY_REPORT_NOT_FINAL_APPROVAL',records=6139,protected=19307,
                  audited=25446,state_checks=25446*6,rvh_records=247,rvh_protected=1533,
                  full_EL_byte_parity_claim=False,eight_fragment_byte_parity_verified=True,
                  rvh_signature_parity_verified=True,application_approval=False)
    result['files'].update({str(p):frozen.sha(p) for p in extra})
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('check-roundtrip',))
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--contract-seal',required=True)
    args=parser.parse_args();output=args.output.absolute()
    require(output.parent==frozen.OUT and output.resolve()==output,'Unsafe callback output')
    contract=frozen.load_sealed(output/'rvh9-contract.json',args.contract_seal)
    require(contract['schema']=='RVH_NINE_POLICY_DATA_CONTRACT_V1','Invalid callback contract')
    for p in dependencies():
        require(contract['callback_dependencies'].get(str(p))==frozen.sha(p),'Callback dependency drift')
    for name in ('applied.el','reloaded.el'):
        require((output/name).is_file() and not(output/name).is_symlink(),'Aliased callback export')
    roundtrip((output/'applied.el').read_bytes(),(output/'reloaded.el').read_bytes(),contract)
    print('NINE_CALLBACK_EXACT6139_SIGNATURE_PASS')


if __name__=='__main__':main()
