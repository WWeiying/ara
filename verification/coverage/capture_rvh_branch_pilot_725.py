"""Exact3 RVH pilot adapter to frozen branch metadata/audit and foreground lifecycle."""
import argparse
import copy
import json
from pathlib import Path
import re
import sys
from types import FunctionType

import prepare_rvh_branch_native_plan_725 as prepared
import capture_operand_debug as debug
import capture_operand_1144 as lifecycle

HERE = Path(__file__).resolve().parent
SCRIPT = Path(__file__).resolve()
TCL = SCRIPT.with_suffix('.tcl')
TEST = HERE / 'test_capture_rvh_branch_pilot_725.py'
PLAN_ROOT = prepared.static.OUT / 'rvh-branch-native-plan-agent-725-20261006-01'
PLAN_SHA = '7a09ad1757428e7d40c3774e50e4224f4b84205dcfc332013f7e5686bca9d5d8'
ANNOTATION = 'RVH frozen-config direct-if native pilot only; not population application'
require, sha = prepared.require, prepared.digest
SAMPLE = prepared.static.OUT / 'gap105-m8-phase8-old-image-parent-20261006-01/code.vdb'
WRAPPER = Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/bin/dve')
STAGES = lifecycle.STAGES


def private(function, **bindings):
    namespace = dict(function.__globals__, **bindings)
    return FunctionType(function.__code__, namespace, function.__name__, function.__defaults__, function.__closure__)


def branch_library():
    raw = (HERE/'capture_operand_debug_branch_v2.tcl').read_text()
    marker = 'proc dbg_session {} {\n'
    require(raw.count(marker) == 1, 'Frozen branch library boundary differs')
    text = raw.split(marker)[0]
    require('proc dbg_metadata' in text and 'proc dbg_audit' in text and 'gui_exit' not in text,
            'Not a library-only primitive prefix')
    return text


def quoted(text):
    return text.replace('\\','\\\\').replace('"','\\"')


def bind_native(raw, config):
    require(raw.endswith(b'\n') and b'\r' not in raw and b'\0' not in raw, 'Invalid native export bytes')
    expected = copy.deepcopy(config)
    annotations = {}
    for scope, metrics in expected['plan']['scopes'].items():
        for row in metrics['branch']:
            for expression in row['point']['expressions']:
                expression['exprstr'] = quoted(expression['exprstr'])
            if row['target']:
                p = row['point']; gen = p['attributes'].get('generate_info')
                require(gen is None or re.fullmatch(r'i=0',gen), 'Pilot generate binding differs')
                key = scope, 'Branch %s (%s)' % (p['native_id'],p['vector'])
                annotations[key] = ANNOTATION if gen is None else 'vcs_gen_start:'+gen+':vcs_gen_end:'+ANNOTATION
    lines = raw.decode('ascii').splitlines(); normalized = list(lines); seen = {}; scope = None
    for i,line in enumerate(lines):
        if line.startswith('INSTANCE:'):
            scope = line.split(':',1)[1].strip()
        if line.startswith('ANNOTATION:'):
            require(i+1<len(lines), 'Dangling annotation')
            match = re.fullmatch(r'Branch (\d+) "[0-9]+" ".*" \((\d+)\) ".*"', lines[i+1])
            require(match is not None, 'Only exact branch directives allowed')
            key = scope, 'Branch %s (%s)' % match.groups()
            require(key in annotations and key not in seen and line == 'ANNOTATION: "'+annotations[key]+'"',
                    'Extra/duplicate/wrong scope or generate annotation')
            seen[key] = line
            normalized[i] = 'ANNOTATION: "'+ANNOTATION+'"'
    require(set(seen) == set(annotations), 'Missing exact3 native exports')
    rows = private(debug.bind_native, ANNOTATION=ANNOTATION)(('\n'.join(normalized)+'\n').encode('ascii'), expected)
    require(len(rows) == 3, 'Pilot native export is not exact3')
    for row in rows: row['native_annotation'] = seen[row['scope'],row['point']]
    return sorted(rows,key=lambda r:(r['scope'],r['point']))


def audit_states(path, config, stage, previous=None):
    identities = debug.audit_states(path,config,stage,previous)
    require(len(identities)==100, 'Pilot full100 audit required')
    for (scope,metric,coordinate),(meta,path) in identities.items():
        sid,vid=coordinate.split(',')
        require(scope==prepared.PILOT and metric=='branch' and
                re.fullmatch(r'(Branch|MISSING_ELSE|MISSING_DEFAULT)'+sid+r'\.'+vid,meta)
                and path=='Item'+sid+'.'+meta, 'Measured complete native identity differs')
    return identities


def verify_artifacts(output, config):
    result = private(debug.verify_artifacts, bind_native=bind_native, audit_states=audit_states, SAMPLE=SAMPLE)(output,config)
    log=(output/'DVEfiles/dve_gui.log').read_text()
    require(log.splitlines().count('RVH_PILOT_DONE_EXACT3')==1
            and not re.search(r'RVH_PILOT_FAILED|EK-CMD-\d+|extra characters after close-brace',log), 'Pilot not complete')
    result.update(status='RVH_PILOT3_NATIVE_ROUNDTRIP_QUALIFIED_NOT_APPLICATION',
                  source_config_bound=True,full_branch_inventory=100,protected_branch_positions=97,
                  native_pilot_qualified=True,full247_qualified=False,processor_application=False)
    return result


def validate_config(config):
    require(config['schema']=='RVH725_EXACT3_NATIVE_PILOT_V1' and config['source_plan_seal']==PLAN_SHA
            and set(config['plan']['scopes'])=={prepared.PILOT}
            and config['targets']=={'branch':3} and config['protected']=={'branch':97}
            and not config['application_approval'] and not config['full247_authorized']
            and not config['launch_approved'] and not config['automatic_retry']
            and config['timeout_seconds']==1800 and config['annotation']==ANNOTATION, 'Wrong pilot contract')
    rows=config['plan']['scopes'][prepared.PILOT]['branch']
    require(len(rows)==100 and {r['point']['raw_index'] for r in rows}==set(range(100))
            and {r['coordinate'] for r in rows if r['target']}=={'15,4','15,0','18,0'}, 'Wrong exact3/full100 selectors')
    require(config['plan']['selected_test_vdb']==str(SAMPLE), 'Foreign sample')


def config_read(output, seal):
    require(seal and sha(output/'config.json')==seal, 'Wrong pilot config seal')
    config=json.loads((output/'config.json').read_bytes())
    require(config['output']==str(output), 'Wrong pilot directory')
    validate_config(config)
    lifecycle.check_inputs(config)
    plan=json.loads((PLAN_ROOT/'native-plan.json').read_bytes())
    require(config['plan']['scopes']==plan['pilot_scopes'], 'Exact source plan selectors changed')
    for path in (SCRIPT,TCL,TEST,output/'selection.tcl',output/'branch-library.tcl',PLAN_ROOT/'seal.json'):
        require(config['pins'].get(str(path))==sha(path), 'Missing actual adapter dependency')
    require((output/'branch-library.tcl').read_text()==branch_library(), 'Primitive library changed')
    return config


def prepare(output):
    require(output.parent==prepared.static.OUT and output.resolve()==output and not output.exists(), 'Fresh pilot output required')
    require(sha(PLAN_ROOT/'seal.json')==PLAN_SHA, 'Wrong reviewed native plan')
    sealed=json.loads((PLAN_ROOT/'seal.json').read_bytes());pins={**sealed['input_pins'],**sealed['output_pins']}
    pins[str(PLAN_ROOT/'seal.json')]=PLAN_SHA
    for path,h in pins.items(): require(sha(path)==h, 'Plan pin drift: '+path)
    plan=json.loads((PLAN_ROOT/'native-plan.json').read_bytes())
    require(plan['selected_admitted_test_vdb']==str(SAMPLE), 'Wrong admitted measurement sample')
    identity=lifecycle.tool.prepare(WRAPPER,Path('/usr/bin/xvfb-run'))
    for entry in identity['files']: pins[entry['path']]=entry['sha256']
    runtime_plan=dict(scopes=plan['pilot_scopes'],design_vdb=plan['design_vdb'],selected_test_vdb=str(SAMPLE),
        tool_identity=identity,input_membership={str(SAMPLE):lifecycle.proof.tree_members(SAMPLE)})
    for p in (SCRIPT,TCL,TEST,HERE/'capture_operand_1144.py',HERE/'seal_operand_1144_preflight.py',
              HERE/'dve_tool_identity.py',HERE/'capture_operand_debug.py',HERE/'reviewed_20261004/audit_readonly.py'):
        pins[str(p)]=sha(p)
    config=dict(schema='RVH725_EXACT3_NATIVE_PILOT_V1',source_plan_seal=PLAN_SHA,
        output=str(output),plan=runtime_plan,pins=pins,targets={'branch':3},protected={'branch':97},
        annotation=ANNOTATION,application_approval=False,full247_authorized=False,
        launch_approved=False,automatic_retry=False,timeout_seconds=1800)
    validate_config(config)
    text=debug.selection(runtime_plan)
    text=text.replace('set dbg_driver '+lifecycle.literal(str(Path(debug.__file__).resolve())),
                      'set dbg_driver '+lifecycle.literal(str(SCRIPT)))
    text+='set rvh_annotation '+lifecycle.literal(ANNOTATION)+'\n'
    text+='set rvh_capture_gate 0\n'
    output.mkdir()
    (output/'selection.tcl').write_text(text)
    (output/'branch-library.tcl').write_text(branch_library())
    for p in (output/'selection.tcl',output/'branch-library.tcl'): pins[str(p)]=sha(p)
    config['command']=lifecycle.tool.launch_command(identity,TCL)
    lifecycle.check_inputs(config)
    lifecycle.write(output/'config.json',config)
    seal=sha(output/'config.json')
    lifecycle.write(output/'status.json',dict(status='PREPARED_NO_DVE',config_sha256=seal,application_approval=False))
    print(json.dumps(dict(output=str(output),seal=seal,pins=len(pins),targets=3,protected=97,audit=100)))


def run(output, seal, authorized):
    require(authorized, 'Explicit parent pilot authorization required')
    config=config_read(output,seal)
    require(json.loads((output/'status.json').read_bytes())['status']=='PREPARED_NO_DVE', 'No repeated launch')
    with (output/'pilot-one-shot-claim.json').open('x') as stream:
        json.dump(dict(config_sha256=seal,targets=3,scope=prepared.PILOT,automatic_retry=False),stream)
    def environment(record,directory):
        env=lifecycle.environment(record,directory)
        env['RVH_CAPTURE_SEAL']=seal
        return env
    # Remain foreground until the frozen lifecycle has waited and verified.
    private(lifecycle.capture,config_read=config_read,verify_artifacts=verify_artifacts,TCL=TCL,
            environment=environment)(output,seal)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','check','run-foreground-reviewed','first','verify'))
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--seal')
    parser.add_argument('--authorize-pilot-measurement',action='store_true');args=parser.parse_args()
    output=args.output.absolute()
    require(output.parent==prepared.static.OUT and output.resolve()==output, 'Unsafe output')
    if args.mode=='prepare':
        require(not args.seal and not args.authorize_pilot_measurement,'Prepare never authorizes launch');prepare(output)
    elif args.mode=='run-foreground-reviewed': run(output,args.seal,args.authorize_pilot_measurement)
    else:
        require(not args.authorize_pilot_measurement,'Authorization only for reviewed run')
        config=config_read(output,args.seal)
        if args.mode=='first':
            bind_native((output/'first.el').read_bytes(),config);print('RVH_FIRST_EXACT3')
        elif args.mode=='check': print('CHECK_PASS RVH_PILOT_PREPARED_NO_DVE')
        else: print(json.dumps(verify_artifacts(output,config),indent=2))


if __name__=='__main__': main()
