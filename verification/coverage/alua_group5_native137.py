"""Exact AluA group5 Branch137 local native qualification; no global application."""
import argparse
import copy
import json
import os
from pathlib import Path
import re
from types import FunctionType

import review_alua_group5_domain795 as source
import capture_rvh_branch_pilot_725 as primitive

life, debug = primitive.lifecycle, primitive.debug
need, sha = primitive.require, primitive.sha
HERE = Path(__file__).resolve().parent
SCRIPT = Path(__file__).resolve()
TCL = SCRIPT.with_suffix('.tcl')
TEST = HERE/'test_alua_group5_native137.py'
PACKET = source.OUT/'alua-group5-domain795-source-review-agent-20261008-03.json'
PACKET_SHA = 'b2d4cd3deafca08aa8990d50f41a100d4f531e8c95c65b589ee12bb36eca6b1d'
ANNOTATION = 'Frozen AluA group5 exact producer-domain Branch137; post-reset only; local qualification not application'
SCHEMA = 'ALUA_GROUP5_EXACT137_LOCAL_NATIVE_V1'
STAGES = life.STAGES


def dependency_files():
    return (SCRIPT,TCL,TEST,Path(source.__file__),Path(source.old.__file__),Path(primitive.__file__),
            Path(debug.__file__),Path(life.__file__),Path(life.tool.__file__),Path(life.proof.__file__),
            HERE/'capture_operand_debug_branch_v2.tcl',HERE/'capture_operand_debug.tcl',
            HERE/'reviewed_20261004/audit_readonly.py',HERE/'inventory_operand_debug.py',
            HERE/'closure_point_inventory.py',HERE/'closure_scorecard.py',HERE/'branch720_next_report_contract.py')


def signature(group, point):
    vector = point['native_vector']['vector']
    def bit(index):
        need(0 < int(index) <= len(vector), 'Compiled branch bit bound')
        return vector[-int(index)]
    values = []
    for expression in group:
        if expression.tag == 'branch_cexpr':
            active = [n for n in expression.findall('branch_citem') if bit(n.get('index')) == '1']
            need(len(active) <= 1, 'Ambiguous compiled case item')
            values.append(active[0].get('name') if active else '-')
        elif expression.tag == 'branch_expr':
            values.append(bit(expression.get('index')) if bit(expression.get('parent_bit')) == '1' else '-')
    need(len(values) == int(group.get('width')) and values[0] != '-', 'Complete group5 signature columns')
    return group[0].get('exprstr')+' '+','.join(values)


def build_plan(packet, bitmap, design):
    need(packet['status'] == 'ALUA_GROUP5_795_SOURCE_ONLY_EXACT_UNREACHABLE_CANDIDATES' and
         packet['population'] == 795 and packet['candidate_count'] == 137 and
         len(packet['candidates']) == 137 and not packet['native_qualified'] and
         len(packet['protected_group5_vectors']) == 47 and packet['inherited_proved_vectors'] == [],
         'Exact137 source-only review partition')
    targets = {(r['scope'],debug.coordinate(r['point'],'branch')):r for r in packet['candidates']}
    need(len(targets) == 137, 'Duplicate source target')
    scopes = {}
    for scope in sorted({s for s,_ in targets}):
        need(re.fullmatch(r'ara_tb\.dut\.i_ara_soc\.i_system\.i_ara\.gen_lanes\[[0-3]\]\.i_lane\.i_operand_queues\.i_operand_queue_alu_a',scope), 'Only four exact AluA child scopes')
        definition = design.definition(scope,'branch'); row = bitmap['metrics']['branch'][scope]
        need(definition.get('chksum') == '1417162425' and row['checksum'] in (None,'1417162425') and row['width'] == 101,
             'Branch checksum/null fallback requires actual compiled definition')
        groups = {g.get('id'):g for g in definition.iter('branch_spec')}
        need(groups['5'].get('chksum') == '718333796', 'Exact group5 checksum')
        rows = []
        for point in source.points('branch',definition,row['width']):
            coordinate = debug.coordinate(point,'branch'); target = targets.get((scope,coordinate))
            if target:
                need(point == target['point'] and point['native_id'] == '5' and target['reason'] and
                     not target['already_EL_owned'] and not target['current795_hit'] and
                     not(int(row['bits'],16) >> (row['width']-1-point['raw_index']) & 1),
                     'Source/compiled/795 zero target drift')
            rows.append(dict(coordinate=coordinate,point=point,target=bool(target),
                module_checksum=design.hierarchy[scope].get('chksum'),metric_checksum=definition.get('chksum'),
                expected_signature=signature(groups['5'],point) if target else None))
        need(len(rows) == 101 and {r['point']['raw_index'] for r in rows} == set(range(101)), 'Full branch complement')
        scopes[scope] = dict(branch=rows)
    need(len(scopes) == 4 and sum(r['target'] for m in scopes.values() for r in m['branch']) == 137,
         'Exact4/137 plan')
    actual_protected = {(s,r['coordinate']) for s,m in scopes.items() for r in m['branch']
                        if r['point']['native_id'] == '5' and not r['target']}
    need(actual_protected == {(r['scope'],debug.coordinate(r['point'],'branch'))
                             for r in packet['protected_group5_vectors']}, 'All47 group5 dynamic vectors protected')
    other = {(s,r['point']['native_id'],r['point']['vector']) for s,m in scopes.items()
             for r in m['branch'] if r['point']['native_id'] != '5'}
    need(other == {(r['scope'],r['group'],v) for r in packet['protected_other_branch_groups']
                   for v in r['protected_vectors']}, 'Every other branch group protected')
    return scopes


def bind_native(raw,config):
    expected = copy.deepcopy(config)
    for metrics in expected['plan']['scopes'].values():
        for row in metrics['branch']:
            for e in row['point']['expressions']:e['exprstr'] = primitive.quoted(e['exprstr'])
    rows = primitive.private(debug.bind_native,ANNOTATION=ANNOTATION)(raw,expected)
    signatures = {(s,'Branch 5 (%s)' % r['point']['vector']):r['expected_signature']
                  for s,m in config['plan']['scopes'].items() for r in m['branch'] if r['target']}
    need(len(rows) == 137, 'Exact137 native exports only')
    for row in rows:
        need(row['native_signature'] == primitive.quoted(signatures[row['scope'],row['point']]),
             'Native case/guard signature differs from exact compiled vector')
    return sorted(rows,key=lambda r:(r['scope'],r['point']))


def audit_states(path,config,stage,previous=None):
    need(stage in STAGES, 'Known native stage only')
    identities = debug.audit_states(path,config,stage,previous)
    need(len(identities) == 404, 'Full404 target/protected branch inventory required')
    for (scope,metric,coordinate),(meta,path) in identities.items():
        sid,vid = coordinate.split(',')
        need(metric == 'branch' and re.fullmatch(r'(Branch|MISSING_ELSE|MISSING_DEFAULT)'+sid+r'\.'+vid,meta)
             and path == 'Item'+sid+'.'+meta, 'Actual native child token/path binding')
    return identities


def validate(config):
    need(config['schema'] == SCHEMA and config['source_packet_seal'] == PACKET_SHA and
         config['targets'] == {'branch':137} and config['protected'] == {'branch':267} and
         config['annotation'] == ANNOTATION and config['timeout_seconds'] == 1800 and
         config['application_approval'] is False and config['automatic_retry'] is False and
         config['initial_X_qualified'] is False, 'Closed local qualification contract')


def config_read(output,seal):
    need(re.fullmatch('[0-9a-f]{64}',seal or '') and sha(output/'config.json') == seal, 'Exact config SHA')
    c = json.loads((output/'config.json').read_bytes());validate(c)
    need(c['output'] == str(output), 'Exact independent output identity')
    life.check_inputs(c)
    packet = json.loads(PACKET.read_bytes());need(sha(PACKET) == PACKET_SHA, 'Source packet unchanged')
    need(source.collect() == packet, 'Complete frozen producer-domain replay')
    bitmap = json.loads((source.BASE.parent/'combined-bits.json').read_bytes())
    design = source.Design(Path(c['plan']['design_vdb']))
    need(c['plan']['scopes'] == build_plan(packet,bitmap,design), 'Exact source/typed full partition')
    need(c['pythonpath'] and all(Path(p).is_absolute() and Path(p).is_dir() for p in c['pythonpath'].split(os.pathsep)), 'Sealed absolute child import paths')
    need((output/'branch-library.tcl').read_text() == primitive.branch_library(), 'Unmodified qualified branch library prefix')
    for p in (*dependency_files(),PACKET,output/'selection.tcl',output/'branch-library.tcl'):
        need(c['pins'].get(str(p)) == sha(p), 'Required native dependency pin')
    return c


def verify_artifacts(output,config):
    sample = Path(config['plan']['selected_test_vdb'])
    result = primitive.private(debug.verify_artifacts,bind_native=bind_native,audit_states=audit_states,SAMPLE=sample)(output,config)
    log = (output/'DVEfiles/dve_gui.log').read_text()
    need(log.splitlines().count('ALUA137_FIVE_STAGE_DONE') == 1 and
         not re.search(r'ALUA137_FAILED|EK-CMD-\d+|extra characters after close-brace',log), 'Actual full native completion')
    result.update(status='ALUA_GROUP5_BRANCH137_NATIVE_QUALIFIED_NOT_APPLIED',
                  source_packet_sha256=PACKET_SHA,full_branch_inventory=404,
                  protected_branch_positions=267,protected_group5=47,protected_other_groups=220,
                  other_metrics_protected_by_exact_global_EL=True,initial_X_qualified=False,
                  population_application=False,terminal_returncode=0)
    return result


def prepare(output):
    need(output.parent == source.OUT and not output.exists(), 'Fresh independent local output')
    need(sha(PACKET) == PACKET_SHA, 'Exact reviewed packet')
    packet = json.loads(PACKET.read_bytes());need(source.collect() == packet, 'Full source review replay')
    manifest = json.loads(source.BASE.read_bytes()); pins = dict(packet['input_pins'])
    need(sha(source.BASE) == source.BASE_SHA and manifest['coverage_admitted'] is True, 'Formal795 sample authority')
    ledger_path = source.BASE.parent/'combined-inputs.txt'
    need(sha(ledger_path) == manifest['output_pins'][str(ledger_path)], 'Published795 ledger')
    ledger = ledger_path.read_text().splitlines();need(len(ledger) == len(set(ledger)) == 796, 'Unique full795 ledger')
    sample = Path(ledger[-1]);dirs = list((sample/'snps/coverage/db/testdata').iterdir())
    need(len(dirs) == 1 and dirs[0].is_dir() and not dirs[0].is_symlink(), 'One admitted measurement sample')
    design = source.Design(Path(ledger[0]))
    scopes = build_plan(packet,json.loads((source.BASE.parent/'combined-bits.json').read_bytes()),design)
    identity = life.tool.prepare(primitive.WRAPPER,Path('/usr/bin/xvfb-run'))
    plan = dict(scopes=scopes,design_vdb=ledger[0],selected_test_vdb=str(sample),tool_identity=identity,
                input_membership={str(sample):life.proof.tree_members(sample)})
    pins[str(ledger_path)] = manifest['output_pins'][str(ledger_path)]
    pins[str(PACKET)] = PACKET_SHA
    for p in sample.rglob('*'):
        if p.is_file():
            need(str(p) in manifest['input_pins'] and sha(p) == manifest['input_pins'][str(p)], 'Admitted sample file ownership')
            pins[str(p)] = manifest['input_pins'][str(p)]
    for entry in identity['files']:pins[entry['path']] = entry['sha256']
    for p in dependency_files():
        pins[str(p)] = sha(p)
    pythonpath = os.environ.get('PYTHONPATH','')
    need(pythonpath and all(Path(p).is_absolute() and Path(p).is_dir() for p in pythonpath.split(os.pathsep)), 'Prepare with explicit absolute PYTHONPATH')
    text = debug.selection(plan).replace('set dbg_driver '+life.literal(str(Path(debug.__file__).resolve())),
                                        'set dbg_driver '+life.literal(str(SCRIPT)))
    text += 'set a137_annotation '+life.literal(ANNOTATION)+'\nset a137_pythonpath '+life.literal(pythonpath)+'\n'
    config = dict(schema=SCHEMA,output=str(output),source_packet_seal=PACKET_SHA,plan=plan,pins=pins,
        targets={'branch':137},protected={'branch':267},annotation=ANNOTATION,timeout_seconds=1800,
        application_approval=False,automatic_retry=False,initial_X_qualified=False,pythonpath=pythonpath,
        command=life.tool.launch_command(identity,TCL))
    validate(config);life.check_inputs(config)
    output.mkdir();(output/'selection.tcl').write_text(text);(output/'branch-library.tcl').write_text(primitive.branch_library())
    for p in (output/'selection.tcl',output/'branch-library.tcl'):pins[str(p)] = sha(p)
    life.write(output/'config.json',config);seal = sha(output/'config.json')
    life.write(output/'status.json',dict(status='PREPARED_NO_DVE',config_sha256=seal,application_approval=False))
    print(json.dumps(dict(output=str(output),seal=seal,targets=137,protected=267,audit=404,EDA_started=False)),flush=True)


def run(output,seal,reviewed):
    need(reviewed == seal and seal, 'Explicit parent reviewed seal; no automatic EDA')
    def environment(record,directory):
        env = life.environment(record,directory);env['A137_CAPTURE_SEAL'] = seal
        return env
    primitive.private(life.capture,config_read=config_read,verify_artifacts=verify_artifacts,TCL=TCL,
                      environment=environment)(output,seal)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('prepare','check','first','verify','run-reviewed'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');p.add_argument('--parent-reviewed-seal')
    a = p.parse_args();out = a.output.resolve()
    if a.mode == 'prepare':need(not a.seal and not a.parent_reviewed_seal,'Prepare never authorizes launch');prepare(out)
    elif a.mode == 'run-reviewed':run(out,a.seal,a.parent_reviewed_seal)
    else:
        need(a.parent_reviewed_seal is None,'Authorization only for reviewed run');c = config_read(out,a.seal)
        if a.mode == 'check':print('ALUA137_CHECK_PASS_NO_EDA')
        elif a.mode == 'first':bind_native((out/'first.el').read_bytes(),c);print('ALUA137_FIRST_EXACT_NATIVE_PASS')
        else:print(json.dumps(verify_artifacts(out,c),indent=2))
