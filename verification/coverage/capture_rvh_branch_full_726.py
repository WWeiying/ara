"""Sealed full247 native measurement adapter; single725 sample, not726 application."""
import inspect
import json
from pathlib import Path
import re

import capture_rvh_branch_pilot_725 as pilot

HERE = pilot.HERE
SCRIPT = Path(__file__).resolve()
TCL = SCRIPT.with_suffix('.tcl')
TEST = HERE / 'test_capture_rvh_branch_full_726.py'
require, sha = pilot.require, pilot.sha
prepared, lifecycle, debug = pilot.prepared, pilot.lifecycle, pilot.debug
PLAN_ROOT, PLAN_SHA, SAMPLE = pilot.PLAN_ROOT, pilot.PLAN_SHA, pilot.SAMPLE
ANNOTATION = 'RVH frozen-config direct-if full247 native measurement only; not population application'
PILOT_ROOT = prepared.static.OUT / 'rvh-branch-native-pilot-agent-725-20261006-01'
PILOT_RESULT_SHA = '48f23b5e1d2cc57fc6bf975ced00b5eb6b09b24f080eb1748a73a251f486c9ed'
PILOT_SOURCE_SHA = 'ee31ed86b858771afda6a0c0b667f62d7bab9eed45f1b186804aee1f7a51c796'
STAGES = pilot.STAGES


def generate_valid(value):
    # Exact expected value is taken from each sealed compiled group, not a whitelist of i=0.
    return value is None or (isinstance(value, str) and bool(value) and
        value.isascii() and not any(c in value for c in '\r\n\0"\\') and
        'vcs_gen_' not in value)


def adapted(function, replacements, **bindings):
    require(sha(Path(pilot.__file__)) == PILOT_SOURCE_SHA, 'Frozen pilot source changed')
    source = inspect.getsource(function)
    for before, after, count in replacements:
        require(source.count(before) == count, 'Adapter boundary differs: '+before)
        source = source.replace(before, after)
    namespace = dict(function.__globals__, **globals(), **bindings)
    exec(compile(source, str(SCRIPT)+':'+function.__name__, 'exec'), namespace)
    return namespace[function.__name__]


def pilot_pins():
    require(sha(PILOT_ROOT/'capture-result.json') == PILOT_RESULT_SHA, 'Pilot result seal differs')
    result = json.loads((PILOT_ROOT/'capture-result.json').read_bytes())
    require(result['native_pilot_qualified'] and result['records'] == 3 and result['final_reset']
            and not result['application_approval'], 'Pilot not qualified')
    pins = dict(result['files'])
    pins[str(PILOT_ROOT/'capture-result.json')] = PILOT_RESULT_SHA
    config = json.loads((PILOT_ROOT/'config.json').read_bytes())
    pins.update(config['pins'])
    for path, digest in pins.items():
        require(sha(path) == digest, 'Pilot evidence drift: '+path)
    return pins


def bind_native(raw, config):
    return adapted(pilot.bind_native, [
        ("gen is None or re.fullmatch(r'i=0',gen)", 'generate_valid(gen)', 1),
        ('len(rows) == 3', 'len(rows) == 247', 1),
        ('exact3', 'exact247', 2),
    ])(raw, config)


def audit_states(path, config, stage, previous=None):
    return adapted(pilot.audit_states, [
        ('len(identities)==100', 'len(identities)==1780', 1),
        ('scope==prepared.PILOT', "scope in config['plan']['scopes']", 1),
    ])(path, config, stage, previous)


def validate_config(config):
    require(config['schema']=='RVH_FULL247_NATIVE_MEASUREMENT_V1' and
            config['source_plan_seal']==PLAN_SHA and config['pilot_result_seal']==PILOT_RESULT_SHA and
            config['targets']=={'branch':247} and config['protected']=={'branch':1533} and
            config['timeout_seconds']==10500 and config['annotation']==ANNOTATION and
            not config['application_approval'] and not config['launch_approved'] and
            not config['automatic_retry'] and not config['full247_authorized'], 'Wrong full247 contract')
    plan=json.loads((PLAN_ROOT/'native-plan.json').read_bytes())
    require(config['plan']['scopes']==plan['full_scopes'] and
            config['plan']['selected_test_vdb']==str(SAMPLE), 'Full source/native selectors changed')
    rows=[r for metrics in config['plan']['scopes'].values() for r in metrics['branch']]
    require(len(config['plan']['scopes'])==14 and len(rows)==1780 and
            sum(r['target'] for r in rows)==247 and
            all(generate_valid(r['point']['attributes'].get('generate_info')) for r in rows if r['target']),
            'Incomplete full inventory or illegal compiled generate binding')


def config_read(output, seal):
    config=adapted(pilot.config_read, [('plan[\'pilot_scopes\']', "plan['full_scopes']", 1)])(output,seal)
    for path, digest in pilot_pins().items():
        require(config['pins'].get(path)==digest, 'Missing pilot prerequisite pin')
    return config


def verify_artifacts(output, config):
    result=adapted(pilot.verify_artifacts, [
        ('RVH_PILOT_DONE_EXACT3','RVH_FULL_DONE_EXACT247',1),
        ('RVH_PILOT_FAILED','RVH_FULL_FAILED',1),
        ('RVH_PILOT3_NATIVE_ROUNDTRIP_QUALIFIED_NOT_APPLICATION',
         'RVH_FULL247_NATIVE_ROUNDTRIP_QUALIFIED_NOT_APPLICATION',1),
        ('full_branch_inventory=100','full_branch_inventory=1780',1),
        ('protected_branch_positions=97','protected_branch_positions=1533',1),
        ('native_pilot_qualified=True,full247_qualified=False',
         'native_pilot_qualified=True,full247_qualified=True',1),
    ])(output,config)
    result.update(native_record_signature_parity=True, el_byte_parity_claim=False,
                  measurement_sample_population=725, population_report=False,
                  state_checks=8900, pilot_result_seal=PILOT_RESULT_SHA)
    return result


def prepare(output):
    prerequisite=pilot_pins()
    adapted(pilot.prepare, [
        ("plan['pilot_scopes']", "plan['full_scopes']",1),
        ("schema='RVH725_EXACT3_NATIVE_PILOT_V1'", "schema='RVH_FULL247_NATIVE_MEASUREMENT_V1',pilot_result_seal=PILOT_RESULT_SHA",1),
        ("targets={'branch':3},protected={'branch':97}", "targets={'branch':247},protected={'branch':1533}",1),
        ('timeout_seconds=1800','timeout_seconds=10500',1),
        ('config=dict(', 'pins.update(prerequisite)\n    config=dict(',1),
        ('targets=3,protected=97,audit=100','targets=247,protected=1533,audit=1780',1),
    ], prerequisite=prerequisite)(output)


def full_capture():
    # Only the two frozen lifecycle budget literals change; all cleanup/live/integrity gates remain.
    return adapted(lifecycle.capture, [('timeout_seconds=1800','timeout_seconds=10500',1),
                                       ('process.wait(timeout=1800)','process.wait(timeout=10500)',1)])


def run(output, seal, authorized):
    require(authorized, 'Explicit parent full247 measurement authorization required')
    config_read(output, seal)
    require(json.loads((output/'status.json').read_bytes())['status']=='PREPARED_NO_DVE', 'No repeated launch')
    with (output/'full-one-shot-claim.json').open('x') as stream:
        json.dump(dict(config_sha256=seal, targets=247, automatic_retry=False),stream)
    def environment(record,directory):
        env=lifecycle.environment(record,directory);env['RVH_CAPTURE_SEAL']=seal;return env
    pilot.private(full_capture(),environment=environment)(output,seal)


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','check','first','verify','run-foreground-reviewed'))
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--seal')
    parser.add_argument('--authorize-full-measurement',action='store_true');args=parser.parse_args()
    output=args.output.absolute()
    require(output.parent==prepared.static.OUT and output.resolve()==output,'Unsafe output')
    if args.mode=='prepare':
        require(not args.seal and not args.authorize_full_measurement,'Prepare never authorizes launch');prepare(output)
    elif args.mode=='run-foreground-reviewed':run(output,args.seal,args.authorize_full_measurement)
    else:
        require(not args.authorize_full_measurement,'Authorization only for reviewed run')
        config=config_read(output,args.seal)
        if args.mode=='first':bind_native((output/'first.el').read_bytes(),config);print('RVH_FIRST_EXACT247')
        elif args.mode=='check':print('CHECK_PASS FULL247_PREPARED_NO_DVE')
        else:print(json.dumps(verify_artifacts(output,config),indent=2))


if __name__=='__main__':main()
