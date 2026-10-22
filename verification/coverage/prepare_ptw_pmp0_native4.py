#!/usr/bin/env python3
"""Seal a single-test PMP0 FSM capture plan; hold until native identities exist."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
import inventory_ptw_pmp0_candidates as proof
import capture_fp16_pack_native208_v2 as sample

HERE = Path(__file__).resolve().parent
OUT, ROOT = proof.OUT, proof.ROOT
INVENTORY = OUT / 'ptw-pmp0-fsm-candidates-706-20261006-01.json'
INVENTORY_SHA = '1ae2bce2df024309a192151045b21cad5453f0c17c70ee51536f10aa4e05c735'
FLAGS = OUT / 'ff1-native904-flags-audit-20261006-01/flags-audit.json'
FLAGS_SHA = '86b4aa45908db349ba061f192141039eb97e24f3aacb5685b3f178a7d454922d'
SAMPLE = sample.OUT / 'fp16-pack-native208-capture-prepare-20261006-02/config.json'
SAMPLE_SHA = '99c9c638f5fbfb3df697b039d51ae28367a8c76efc7fb1711d6f54cc49b2685e'
HOOK = HERE / 'probe_ptw_pmp0_fsm_api.tcl'
INSTALL = Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1')
require = proof.require


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_bound(path, pins, expected=None):
    path = Path(path).absolute()
    require(path.is_file() and not path.is_symlink() and path.resolve() == path,
            'Missing or aliased input: ' + str(path))
    raw = path.read_bytes()
    value = hashlib.sha256(raw).hexdigest()
    require(expected is None or value == expected, 'Expected pin differs: ' + str(path))
    require(str(path) not in pins or pins[str(path)] == value, 'Conflicting expected pin')
    pins[str(path)] = value
    return raw


def forwarding(text, module, instance, rhs):
    clean = proof.compact(text)
    if module == 'ara_system':
        # The frozen SoC has a TARGET_GATESIM alternative between params and instance.
        require('`ifndefTARGET_GATESIMara_system#(' in clean and
                ')`elseara_system`endifi_system(' in clean, 'SoC generate boundary differs')
        blocks = re.findall(r'ara_system#\((.*?)\)`elseara_system`endifi_system\(', clean)
    else:
        lexed = re.sub(r'/\*.*?\*/|//[^\n]*', ' ', text, flags=re.S)
        blocks = [proof.compact(b) for b in re.findall(
            r'\b' + re.escape(module) + r'\s*#\s*\((.*?)\)\s*' +
            re.escape(instance) + r'\s*\(', lexed, flags=re.S)]
    require(len(blocks) == 1 and blocks[0].count('.CVA6Cfg(') == 1 and
            '.CVA6Cfg(' + rhs + ')' in blocks[0], 'Exact instance config forwarding differs')
    return dict(module=module, instance=instance, parameter='CVA6Cfg', expression=rhs)


def logical_rows(saved):
    rows = sorted(saved['candidates'] + saved['protected'], key=lambda r: r['raw_index'])
    require([r['raw_index'] for r in rows] == list(range(35)), 'Incomplete FSM inventory')
    require([r['raw_index'] for r in rows if r['candidate']] == [2, 10, 11, 16],
            'Not exact PMP4 target set')
    states = {(r['fsm']['id'], r['item']['id']): r for r in rows if r['kind'] == 'state'}
    identities = []
    for row in rows:
        require(not row['candidate'] or (row['fsm']['name'] == 'state_q' and not row['raw_hit']),
                'Hit or foreign FSM contradicts PMP0 proof')
        identity = dict(fsm=row['fsm'], kind=row['kind'], compiled_item=row['item'])
        if row['kind'] == 'state':
            identity['state_name'] = row['name']
            identity['state_value'] = row['item']['value']
        else:
            ends = [states[(row['fsm']['id'], row['item'][key])] for key in ('fromid', 'toid')]
            require([r['name'] for r in ends] == [row['source'], row['destination']],
                    'Transition endpoint identity differs')
            identity['endpoints'] = [dict(name=r['name'], value=r['item']['value'],
                                          compiled_id=r['item']['id']) for r in ends]
        identities.append(dict(diagnostic_raw_index=row['raw_index'], target=row['candidate'],
                               compiled_identity=identity, native_selector=None,
                               native_signature=None))
    return identities


def build_plan():
    pins = {}
    saved = json.loads(read_bound(INVENTORY, pins, INVENTORY_SHA))
    require(saved == proof.inventory(), 'Independent source/shape proof reproduction differs')
    for path, expected in saved['pins'].items():
        read_bound(path, pins, expected)
    flags = json.loads(read_bound(FLAGS, pins, FLAGS_SHA))
    require(flags['effective_compile_flags_defparam_audit_complete'] is True and
            flags['source_defparam_or_config'] is False and flags['manifest_files'] == 458 and
            not any(d.split('=')[0] == 'TARGET_GATESIM' for d in flags['defines']),
            'Effective configuration override audit differs')
    for path, expected in flags['pins'].items():
        read_bound(path, pins, expected)
    build = json.loads(read_bound(proof.BUILD / 'build-source-pins.json', pins))
    chain = [
        ('hardware/src/ara_soc.sv', 'ara_system', 'i_system', 'CVA6AraConfig'),
        ('hardware/src/ara_system.sv', 'cva6', 'i_ariane', 'CVA6Cfg'),
        ('hardware/deps/cva6/core/cva6.sv', 'ex_stage', 'ex_stage_i', 'CVA6Cfg'),
        ('hardware/deps/cva6/core/ex_stage.sv', 'load_store_unit', 'lsu_i', 'CVA6Cfg'),
        ('hardware/deps/cva6/core/load_store_unit.sv', 'cva6_mmu', 'i_cva6_mmu', 'CVA6Cfg'),
        ('hardware/deps/cva6/core/cva6_mmu/cva6_mmu.sv', 'cva6_ptw', 'i_ptw', 'CVA6Cfg'),
        ('hardware/deps/cva6/core/cva6_mmu/cva6_ptw.sv', 'pmp', 'i_pmp_ptw', 'CVA6Cfg'),
    ]
    links = []
    for relative, module, instance, rhs in chain:
        path = ROOT / relative
        require(str(path) in flags['source_override_scan'], 'Forwarding source absent from compile audit')
        text = read_bound(path, pins, build[str(path)]).decode()
        links.append(dict(source=str(path), sha256=build[str(path)],
                          **forwarding(text, module, instance, rhs)))
    pc = json.loads(read_bound(SAMPLE, pins, SAMPLE_SHA))
    roots = (pc['plan']['design_vdb'], pc['plan']['selected_test_vdb'])
    for path, expected in pc['pins'].items():
        read_bound(path, pins, expected)
    listing = read_bound(proof.BASE / 'combined-inputs.txt', pins).decode().splitlines()
    bits = json.loads(read_bound(proof.BASE / 'combined-bits.json', pins))
    require(roots[0] == listing[0] and roots[1] in bits['tests'] and listing[1:] == bits['tests'],
            'Sample not in admitted historical PASS population')
    membership = {root: sample.lifecycle.proof.tree_members(root) for root in roots}
    require(membership == pc['plan']['input_membership'], 'Sample input membership differs')
    for root, names in membership.items():
        for name in names:
            read_bound(Path(root) / name, pins)
    sample.tool.revalidate(pc['plan']['tool_identity'])
    docs = [INSTALL / 'doc/examples/coverage/adaptiveExclusion' / n for n in
            ('adaptiveExclusion.tcl', 'Elfile_from_Version1.el')]
    for path in docs:
        read_bound(path, pins)
    for path in (Path(__file__), HOOK, HERE / 'test_prepare_ptw_pmp0_native4.py'):
        read_bound(path, pins)
    rows = logical_rows(saved)
    for path, expected in pins.items():
        require(digest(path) == expected, 'Input changed during prepare')
    return dict(status='PTW_PMP0_EXACT4_PLAN_HOLD_NATIVE_IDENTITY_NO_DVE',
                targets=4, protected=31, all_fsm_positions=35, scope=proof.SCOPE,
                metric_checksum=saved['metric_checksum'], source_proof=saved['proof'],
                exact_config_forwarding=links, effective_flags_sha256=FLAGS_SHA,
                inventory_sha256=INVENTORY_SHA, sample_config_sha256=SAMPLE_SHA,
                design_vdb=roots[0], selected_test_vdb=roots[1], selected_test=pc['selected_test'],
                selected_test_count=1, tool_identity=pc['plan']['tool_identity'],
                input_membership=membership, rows=rows, pins=pins,
                native_qualified=False, capture_ready=False, exclusions_applied=False,
                application_approval=False, full_population_application=False,
                H_stage_included=False, ordinary_fault_or_flush_arcs_included=False,
                hold_reasons=['No actual native state_q state/arc row token inventory for this checksum.',
                              'Installed legacy Fsm/Transition example does not establish state syntax or current signatures.',
                              'Before any capture: bind every one of 35 native rows to compiled names/values/endpoints, then audit 4/31 across save/reset/import/finalreset.'],
                help_probe=dict(hook=str(HOOK), exclusions_allowed=False,
                                command=sample.tool.launch_command(pc['plan']['tool_identity'], HOOK)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'verify'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal')
    args = parser.parse_args()
    output = args.output.absolute()
    require(output.parent == OUT and output.resolve() == output and not output.is_symlink(), 'Unsafe output')
    if args.command == 'prepare':
        require(not output.exists(), 'Fresh output required')
        plan = build_plan()
        output.mkdir()
        sample.write(output / 'capture-plan.json', plan)
        (output / 'inputs.txt').write_text(plan['design_vdb'] + '\n' + plan['selected_test_vdb'] + '\n')
        manifest = {str(output / name): digest(output / name) for name in ('capture-plan.json', 'inputs.txt')}
        sample.write(output / 'manifest.json', manifest)
        print(plan['status'] + ' seal=' + digest(output / 'manifest.json'))
    else:
        require(re.fullmatch('[0-9a-f]{64}', args.seal or '') and
                digest(output / 'manifest.json') == args.seal, 'External plan seal differs')
        manifest = json.loads((output / 'manifest.json').read_bytes())
        require(set(manifest) == {str(output / n) for n in ('capture-plan.json', 'inputs.txt')}, 'Wrong manifest')
        for path, expected in manifest.items():
            require(digest(path) == expected, 'Prepared member changed')
        saved = json.loads((output / 'capture-plan.json').read_bytes())
        require(saved == build_plan(), 'Independent plan reproduction differs')
        require((output / 'inputs.txt').read_text().splitlines() ==
                [saved['design_vdb'], saved['selected_test_vdb']], 'Wrong single-test inputs')
        print('PTW_PMP0_EXACT4_STATIC_PLAN_REVERIFIED_NATIVE_HOLD')


if __name__ == '__main__':
    main()
