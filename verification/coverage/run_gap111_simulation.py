"""Fixed180s GAP111 runner; prepare/verify never start VCS."""
import argparse
import json
import struct
from pathlib import Path
from types import FunctionType, SimpleNamespace

import build_gap111_preflight as oracle
import run_pure_war_simulation as frozen

life, require = oracle.life, oracle.require
PRE = life.OUT / 'gap111-pte-line-preflight-740-agent-20261007-02'
PRE_SHA = '47cb73382c248469e9f079c2ed671b993eefa541671f4bf1c0f749c71a076484'
ELF_SHA = '160f1e5b18fcce48c18b1a69fa9e6b99c702a5c5e235908a81eb9e5c72c4fdfc'
IMAGE_SHA = '2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3'
LIFECYCLE_SHA = '2e7ded5ac7c1caeff20a0d1febbb7123dbd30973a9fdef0435ad051673e11626'
NAME, BUDGET = 'vgap111_pte_line_collision', 180


def validate(pre):
    require(pre['schema'] == 'GAP111_SAME_PTE_LINE_PREFLIGHT_V1' and
            pre['status'] == 'GAP111_SPIKE_SOFTWARE_PASS_NOT_FSM_PROOF' and
            type(pre['baseline_tests']) is int and pre['baseline_tests'] == 740 and
            pre['baseline_manifest_sha256'] == oracle.BASE_SHA and
            pre['VCS_authorized'] is False and pre['coverage_admitted'] is False and
            pre['runtime_overlap_proven'] is False, 'Exact preflight contract differs')
    require(pre['input_elf'] == str(PRE / 'input.elf') and
            pre['input_spike_trace'] == str(PRE / 'spike.trace') and
            pre['output_pins'][str(PRE / 'input.elf')] == ELF_SHA and
            pre['symbols']['tohost'] == 0x80001000, 'Exact ELF/reference identity differs')
    require(pre['validation']['checks'] == 26 and pre['validation']['expected_traps'] == 1 and
            pre['validation']['scalar_counts'] == dict(instructions=11537, GPR_writes=3645, memory_accesses=3561),
            'Expected terminal architecture boundary differs')
    return life.merge_pins(pre['pins'], pre['output_pins'])


def command(out):
    return [str(life.IMAGE), '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
            '+PRELOAD=' + str(PRE / 'input.elf'), '+TESTCASE=' + NAME, '+COMMIT_TOHOST=80001000',
            '+COMMIT_TRACE=' + str(out / 'commit_trace.csv'), '+VECTOR_TRACE=' + str(out / 'vector_trace.csv'),
            '-cm', 'line+cond+fsm+tgl+branch', '-cm_dir', str(out / 'code.vdb'), '-cm_name', NAME]


def elf_fit(raw):
    require(len(raw) >= 64 and raw[:6] == b'\x7fELF\x02\x01'
            and struct.unpack_from('<HHI', raw, 16) == (2, 243, 1), 'Not RISC-V ELF64 executable')
    entry, offset = struct.unpack_from('<QQ', raw, 24)
    size, count = struct.unpack_from('<HH', raw, 54)
    require(entry == 0x80000000 and size == 56 and count > 0 and offset + size * count <= len(raw),
            'ELF entry/program header differs')
    segments = []
    for index in range(count):
        kind, flags, file_offset, va, pa, file_size, memory_size, alignment = struct.unpack_from(
            '<IIQQQQQQ', raw, offset + size * index)
        if kind != 1:
            continue
        require(file_size <= memory_size and file_offset + file_size <= len(raw) and va == pa
                and 0x80000000 <= pa < 0x80200000 and pa + memory_size <= 0x80200000,
                'PT_LOAD outside frozen 2MiB L2 or malformed segment')
        segments.append(dict(address=pa, file_bytes=file_size, memory_bytes=memory_size))
    require(segments and any(s['address'] <= entry < s['address'] + s['memory_bytes'] for s in segments),
            'No boot-address LOAD segment')
    return dict(entry=entry, L2_bytes=2 << 20, segments=segments)


def manifest(out):
    out = Path(out).absolute()
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh direct run required')
    pre = life.read_bound(PRE / 'preflight-manifest.json', PRE_SHA)
    pins = validate(pre)
    require(life.digest(Path(frozen.__file__)) == LIFECYCLE_SHA, 'Frozen lifecycle drift')
    plan = life.read_bound(life.PLAN, life.PLAN_SEAL)
    require(plan['simv'] == str(life.IMAGE) and len(plan['image']) == 66 and
            plan['image'].get(str(life.IMAGE)) == IMAGE_SHA, 'Exact frozen image66 required')
    pins = life.merge_pins(pins, plan['image'])
    pins = life.merge_pins(pins, plan['design_files'])
    files = [Path(__file__).resolve(), Path(__file__).with_name('test_run_gap111_simulation.py'),
             Path(frozen.__file__).resolve(), life.PLAN,
             life.ROOT / 'verification/coverage/scoped_rv64c_memory.py',
             life.ROOT / 'verification/coverage/test_scoped_rv64c_memory.py']
    files += list((life.ROOT / 'verification/ara_verify').rglob('*.py'))
    pins = life.merge_pins(pins, {str(p): life.digest(p) for p in files})
    pins = life.merge_pins(pins, {str(PRE / 'preflight-manifest.json'): PRE_SHA})
    compile_path = oracle.BUILD / 'compile.command.json'
    pins = life.merge_pins(pins, {str(compile_path): life.digest(compile_path)})
    life.check(pins)
    compile_command = json.loads(compile_path.read_bytes())['command']
    require([x for x in compile_command if x.startswith('sim_l2_mb=')] == ['sim_l2_mb=2'],
            'Frozen L2 size selection differs')
    fit = elf_fit((PRE / 'input.elf').read_bytes())
    validation = oracle.validate(oracle.shared.parse_spike_commits(PRE / 'spike.trace'), pre['symbols'])
    require(validation == pre['validation'], 'Independent software oracle replay differs')
    bits = life.read_bound(oracle.BASE / 'combined-bits.json', pins[str(oracle.BASE / 'combined-bits.json')])
    shape = oracle.read_xml(oracle.BUILD / 'sim/simv.vdb/snps/coverage/db/shape/fsm.verilog.shape.xml')
    target = life.read_bound(PRE / 'target-before.json', pins[str(PRE / 'target-before.json')])
    require(target == dict(baseline=740, manifest_sha256=oracle.BASE_SHA, targets=oracle.targets(bits, shape)),
            'Actual compiled target binding differs')
    return dict(schema='GAP111_SINGLE_EXPERIMENT_RUN_V1', case=NAME, output=str(out), command=command(out),
                preflight=str(PRE / 'preflight-manifest.json'), preflight_seal=PRE_SHA,
                pins=pins, timeout_s=BUDGET, baseline_tests=740, targets=target['targets'],
                input_elf=str(PRE / 'input.elf'), input_spike_trace=str(PRE / 'spike.trace'),
                image_sha256=IMAGE_SHA, elf_sha256=ELF_SHA, old_image_files_checked=66,
                ELF_fit=fit,
                scalar_reference_counts=validation['scalar_counts'], expected_checks=26,
                expected_S_ecalls=1, expected_output_bytes=80, expected_trap_bytes=32,
                checker_contract=pre['checker_contract'],
                coverage_admitted=False, admission_performed=False, rtl_changed=False,
                new_RTL_signoff=False, terminal_oracle_verified=False, automatic_retry=False,
                no_FSDB=True, foreground_lifetime=True, simulator_exit_is_not_functional_pass=True,
                authorization_source='SEPARATE_PARENT_REVIEW_REQUIRED_FOR_ONE_FIXED_RUN',
                no_gain_action=pre['no_gain_action'],
                systemd_policy=dict(RuntimeMaxSec=240, TimeoutStopSec=10, KillMode='control-group'))


def invoke_run(out, record):
    require(record == manifest(out), 'Exact prepared manifest/pins drift')
    namespace = dict(frozen.run.__globals__, PRE=PRE, ELF_SEAL=ELF_SHA, IMAGE_SEAL=IMAGE_SHA,
                     BUDGET=BUDGET, command=command, preflight=SimpleNamespace(NAME=NAME))
    FunctionType(frozen.run.__code__, namespace, 'gap111_private_run')(Path(out).absolute(), record)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'verify', 'run'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prepared-seal')
    parser.add_argument('--parent-authorized', action='store_true')
    args = parser.parse_args()
    require((args.mode != 'prepare') == bool(args.prepared_seal), 'Fixed seal required for verify/run')
    require((args.mode == 'run') == args.parent_authorized, 'Run requires separate parent authorization')
    out = args.output.absolute()
    sidecar = out.with_name(out.name + '.prepared.json')
    if args.mode == 'prepare':
        require(not sidecar.exists(), 'Exclusive prepared sidecar required')
        record = manifest(out)
        life.save(sidecar, record)
        print(json.dumps(dict(prepared=str(sidecar), seal=life.digest(sidecar), timeout_s=BUDGET,
                              pins=len(record['pins']), VCS_started=False)))
    else:
        record = life.read_bound(sidecar, args.prepared_seal)
        if args.mode == 'run':
            invoke_run(out, record)
        else:
            require(record == manifest(out), 'Prepared identity differs')
            print('GAP111_IMAGE66_TARGET14_ORACLE26_PREPARED_VERIFY_PASS_NO_VCS')


if __name__ == '__main__':
    main()
