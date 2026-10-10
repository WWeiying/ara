"""Thin adapter to the sealed operand native runner; parent authorization required."""
import argparse
import json
import re
from pathlib import Path

import prepare_mask_store_snapshot_cond24 as prepared
import capture_operand_1144 as runner

HERE = Path(__file__).resolve().parent
BASE_SEAL = '79d3fab018b585106a88ff50cfa6bf4ba1a143051422a19598602a03fa99c7b5'
OUTPUT = prepared.OUT/'mask-store-cond24-native-prepared-agent-725-20261006-01'
AUTHORIZATION = 'PARENT_APPROVED_COND24_QUALIFICATION_ONLY'
require, digest = prepared.require, prepared.digest


def prepare(output):
    require(output == OUTPUT and not (output/'runtime-config.json').exists(), 'Exact fresh runtime plan required')
    base = prepared.read_config(output, BASE_SEAL)
    members = {}
    evidence = json.loads((output/'readonly-evidence.json').read_bytes())
    for root in (evidence['design_vdb'], evidence['selected_sample']):
        members[root] = runner.proof.tree_members(root)
        require(all(str(Path(root)/m) in base['pins'] for m in members[root]), 'Unpinned input member')
    pins = dict(base['pins'])
    for f in (output/'config.json', Path(__file__).resolve(),
              HERE/'test_run_mask_store_snapshot_cond24.py', HERE/'capture_operand_1144.py',
              HERE/'seal_operand_1144_preflight.py'):
        pins[str(f)] = digest(f)
    selection = output/'selection.tcl'
    with selection.open('x') as stream:
        stream.write('# No secondary selector: exporter reads exact pinned inputs.txt and groups.tcl.\n')
    pins[str(selection)] = digest(selection)
    config = dict(schema='MASK_STORE_COND24_NATIVE_RUNTIME_ADAPTER_V1', output=str(output),
        base_config_sha256=BASE_SEAL, pins=pins,
        plan=dict(input_membership=members, tool_identity=base['tool_identity']),
        command=runner.tool.launch_command(base['tool_identity'], Path(base['exporter'])),
        timeout_seconds=1800, authorization_required=AUTHORIZATION,
        qualification_only=True, application_approval=False, original_config_unchanged=True)
    runner.check_inputs(config)
    prepared.save(output/'runtime-config.json', config)
    seal = digest(output/'runtime-config.json')
    prepared.save(output/'status.json', dict(status='PREPARED_NO_DVE', runtime_config_sha256=seal,
                                           application_approval=False))
    return dict(status='RUNTIME_PREPARED_NO_LAUNCH', output=str(output), seal=seal)


def read_config(output, seal):
    require(output == OUTPUT and output.resolve() == output and
            not (output/'runtime-config.json').is_symlink() and
            digest(output/'runtime-config.json') == seal, 'Runtime plan seal differs')
    base = prepared.read_config(output, BASE_SEAL)
    config = json.loads((output/'runtime-config.json').read_bytes())
    require(config['schema'] == 'MASK_STORE_COND24_NATIVE_RUNTIME_ADAPTER_V1' and
            config['output'] == str(output) and config['base_config_sha256'] == BASE_SEAL and
            config['timeout_seconds'] == 1800 and config['application_approval'] is False and
            config['qualification_only'] is True and config['authorization_required'] == AUTHORIZATION,
            'Runtime scope differs')
    require(config['plan']['tool_identity'] == base['tool_identity'] and config['command'] ==
            runner.tool.launch_command(base['tool_identity'], Path(base['exporter'])), 'Runtime tool/command differs')
    require(all(config['pins'].get(k) == v for k,v in base['pins'].items()), 'Missing base pin')
    evidence = json.loads((output/'readonly-evidence.json').read_bytes())
    require(set(config['plan']['input_membership']) ==
            {evidence['design_vdb'], evidence['selected_sample']} and
            all(str(Path(root)/name) in config['pins']
                for root, names in config['plan']['input_membership'].items() for name in names),
            'Missing/foreign membership gate')
    runner.check_inputs(config)
    return config


def environment(identity, output):
    base = prepared.read_config(output, BASE_SEAL)
    require(identity == base['tool_identity'], 'Environment tool identity differs')
    env = runner.tool.controlled_environment(identity, runner.os.environ)
    for key in base['future_environment']['remove']:
        env.pop(key, None)
    env.update(base['future_environment']['set_values'])
    require('DVE' not in env and 'ENV' not in env, 'Forbidden launcher environment')
    return env


def claim_once(output, seal, authorization):
    require(authorization == AUTHORIZATION, 'Explicit parent authorization required')
    require(not any((output/n).exists() for n in ('execution.json','DVEfiles','first.el','capture-result.json')),
            'Previous launch evidence exists')
    prepared.save(output/'launch-once.json', dict(runtime_config_sha256=seal,
        authorization=authorization, capture_only=True, application_approval=False))


def verify_artifacts(output, config):
    base = prepared.read_config(output, BASE_SEAL)
    result = prepared.verify_artifacts(output, base)
    execution = json.loads((output/'execution.json').read_bytes())
    live = json.loads((output/'live-identity.json').read_bytes())
    require(execution['launch_count'] == 1 and execution['returncode'] == 0 and
            execution['timeout_seconds'] == 1800 and execution['command'] == config['command'] and
            live['executable_verified'] is True and live['executable'] == config['plan']['tool_identity']['executable'] and
            live['launch_pid'] == execution['launch_pid'] and
            live['launch_starttime'] == execution['launch_starttime'] and
            type(live['pid']) is int and live['pid'] > 0, 'Execution/live identity differs')
    require(json.loads((output/'launch-once.json').read_bytes()) == dict(runtime_config_sha256=
            digest(output/'runtime-config.json'), authorization=AUTHORIZATION,
            capture_only=True, application_approval=False), 'Once receipt differs')
    for name, field in (('integrity-before.json','checked'),('integrity-after.json','unchanged')):
        require(json.loads((output/name).read_bytes()) == {field:True,'pins':config['pins'],
                'membership':config['plan']['input_membership']}, 'Input integrity differs')
    require((output/'live-ready').read_text() == 'LIVE_EXECUTABLE_VERIFIED\n', 'Missing live-ready gate')
    for f in (output/'launcher.log', output/'DVEfiles/dve_gui.log'):
        require(not re.search(r'(?:^|\s)(?:Error|Fatal):|DVEENVDIRNFND|EK-CMD-|checksum.*mismatch|EXPORT_FAILED',
                              f.read_text(), re.I), 'Native diagnostic failure')
    runner.check_inputs(config)
    files = ('first.el','second.el','initial-empty.el','reset-empty.el','final-empty.el',
        'neighbor-audit.csv','selected_tests.txt','summary.csv.partial','DVEfiles/dve_gui.log',
        'launcher.log','execution.json','live-identity.json','live-ready','launch-once.json',
        'integrity-before.json','integrity-after.json','runtime-config.json','config.json','selection.tcl')
    require(all((output/n).is_file() and not (output/n).is_symlink() for n in files), 'Missing/aliased native artifact')
    result.update(status='COND24_NATIVE_ROUNDTRIP_NOT_APPLICATION_APPROVAL',
                  files={str(output/n):digest(output/n) for n in files})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','check','capture','verify'))
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--seal')
    parser.add_argument('--authorization')
    parser.add_argument('--artifact-seal')
    a=parser.parse_args(); output=a.output.absolute()
    if a.mode=='prepare':
        require(not(a.seal or a.authorization or a.artifact_seal), 'Fresh prepare arguments required')
        print(json.dumps(prepare(output))); return
    require(a.seal, 'Runtime seal required'); config=read_config(output,a.seal)
    if a.mode=='check':
        require(not(a.authorization or a.artifact_seal), 'Check is read-only')
        print('COND24_RUNTIME_CHECK_PASS_NO_LAUNCH'); return
    if a.mode=='capture':
        require(not a.artifact_seal, 'Capture cannot reuse result')
        claim_once(output,a.seal,a.authorization)
        runner.TCL=Path(prepared.HERE/'export_dve_coverage.tcl')
        runner.config_read=read_config; runner.environment=environment
        runner.verify_artifacts=verify_artifacts
        runner.capture(output,a.seal)
    else:
        require(not a.authorization and a.artifact_seal and
                digest(output/'capture-result.json')==a.artifact_seal, 'Capture result seal required')
        saved=json.loads((output/'capture-result.json').read_bytes())
        require(saved['config_sha256']==a.seal, 'Result runtime binding differs')
        result=verify_artifacts(output,config)
        require(all(saved.get(k)==v for k,v in result.items()), 'Saved result differs')
        print('COND24_INDEPENDENT_VERIFY_PASS_NOT_APPLICATION_APPROVAL')


if __name__=='__main__':
    main()
