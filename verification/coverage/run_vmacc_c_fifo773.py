"""One parent-authorized600s frozen-image run; offline collector is separate."""
import argparse
import json
from pathlib import Path
from types import FunctionType, SimpleNamespace

import preflight_vmacc_c_fifo_l2_773 as p
import run_pure_war_simulation as worker
import targeted_toggle_evidence_v2 as toggle
import coverage_bitmap_delta as bitmap

life, require = p.life, p.require
NAME = 'vmacc_c_fifo_length_ring'
PRE = life.OUT / 'vmacc-C-fifo-l2-preflight773-agent-20261007-02/runtime-qualified.json'
PRE_SHA = '193ff5901e0c8cfc51183fafedde77b57ae3307579a58e6a51aa45667b0dfa99'
ELF = life.OUT / 'vmacc-C-fifo-l2-preflight773-agent-20261007-01/input.elf'
ELF_SHA = '4f6ddb00d9c859fad4b1ee9b9cc328c9ba64d2b279dff21bcc958ea90ccaba9d'
IMAGE_SHA = '2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3'
COMPILE = life.OUT / 'repaired-aligned-build-20260930-01/compile.command.json'
COMPILE_SHA = '30cdd93809c183f5004767d6190ca33d1d78aed68e73dcf42d6fef793269cbb1'
BUDGET = 600


def command(out):
    return [str(life.IMAGE), '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
            '+PRELOAD=' + str(ELF), '+TESTCASE=' + NAME, '+COMMIT_TOHOST=80001000',
            '+COMMIT_TRACE=' + str(out / 'commit_trace.csv'), '+VECTOR_TRACE=' + str(out / 'vector_trace.csv'),
            '-cm', 'line+cond+fsm+tgl+branch', '-cm_dir', str(out / 'code.vdb'), '-cm_name', NAME]


def preflight():
    pre = life.read_bound(PRE, PRE_SHA)
    life.check(pre['input_pins'])
    require(pre['status'] == 'VMACC_FIFO_L2_RUNTIME_AND_EVERY_VECTOR_GOLD_PREFLIGHT_PASS_NOT_DUT' and
            pre['baseline'] == 773 and pre['baseline_seal'] == p.old.SEAL and
            pre['ELF'] == str(ELF) and life.digest(ELF) == ELF_SHA and
            pre['counts']['checks'] == 2344 and pre['counts']['target_VMACC'] == 12 and
            pre['runtime']['entry_to_tohost_instructions'] == 36339 and pre['runtime']['stack_depth'] == 48 and
            pre['runtime']['stack_top'] == 0x80040000 and pre['runtime']['all_runtime_memory_widths_decoded'] and
            pre['numerical_vectors']['writers'] == 19 and not pre['coverage_admitted'], 'Exact runtime preflight')
    require('sim_l2_mb=2' in life.read_bound(COMPILE, COMPILE_SHA)['command'], 'Frozen2MiB build')
    return pre


def prepare(out):
    import collect_vmacc_c_fifo773 as collector
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh run directory')
    pre = preflight()
    image = life.read_bound(life.PLAN, life.PLAN_SEAL)
    require(len(image['image']) == 66 and image['image'][str(life.IMAGE)] == IMAGE_SHA, 'Exact frozen simv66')
    pins = life.merge_pins(pre['input_pins'], image['image'])
    for path in (PRE, COMPILE, life.PLAN, Path(__file__).resolve(),
                 Path(__file__).with_name('test_vmacc_c_fifo773_run_collect.py'),
                 Path(__file__).with_name('test_qualify_queue_mask_source_lifetime_terminal.py')):
        pins = life.merge_pins(pins, {str(path): life.digest(path)})
    for module in (p, worker, toggle, toggle.base, bitmap, collector, collector.control,
                   collector.control.previous, collector.common, collector.memory, collector.memory.prior):
        path = Path(module.__file__).resolve()
        pins = life.merge_pins(pins, {str(path): life.digest(path)})
    for path in sorted((life.ROOT / 'verification/ara_verify').glob('*.py')):
        pins = life.merge_pins(pins, {str(path): life.digest(path)})
    base = life.read_bound(p.old.BASE / 'admission-manifest.json', p.old.SEAL)
    for name in ('combined-inputs.txt', 'combined-bits.json'):
        path = p.old.BASE / name
        pins = life.merge_pins(pins, {str(path): base['output_pins'][str(path)]})
    static = life.read_bound(p.old.STATIC, p.old.STATIC_SHA)
    require(static['population'] == 773 and static['zero_slots'] == 144, 'Exact144 target binding')
    pins = life.merge_pins(pins, {str(p.old.STATIC): p.old.STATIC_SHA})
    life.check(pins)
    return dict(case=NAME, preflight=str(PRE), preflight_seal=PRE_SHA,
                output=str(out), command=command(out), timeout_s=BUDGET, pins=pins,
                image_sha256=IMAGE_SHA, elf_sha256=ELF_SHA, baseline=773, baseline_seal=p.old.SEAL,
                targets=static['targets'], scoped_toggle_before=static['baseline'],
                compiled_L2_bytes=2 * 1024 * 1024, scalar_reference_instructions=36339,
                expected_missing_coordinates=144, measured_gain=None,
                authorization_source='SEPARATE_PARENT_AGENT_REVIEW_REQUIRED_BEFORE_RUN',
                automatic_retry=False, no_FSDB=True, raw_commit=True, raw_vector=True,
                foreground_lifetime=True, systemd_policy=dict(RuntimeMaxSec=630, TimeoutStopSec=10, KillMode='control-group'),
                coverage_admitted=False, admission_performed=False, RTL_modified=False,
                qualification_required='Offline complete scalar/vector/signature/lifecycle and exact773 raw gain')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('prepare', 'verify', 'run'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal')
    parser.add_argument('--parent-authorized', action='store_true')
    args = parser.parse_args()
    require((args.mode != 'prepare') == bool(args.seal), 'Verify/run require prepared seal')
    require((args.mode == 'run') == args.parent_authorized, 'Only explicitly authorized run')
    out = args.output.resolve()
    manifest = prepare(out)
    record = out.with_name(out.name + '.prepared.json')
    if args.mode == 'prepare':
        life.save(record, manifest)
        print('PREPARED', life.digest(record), len(manifest['pins']), flush=True)
    else:
        require(life.read_bound(record, args.seal) == manifest, 'Prepared scope/command/pins differ')
        if args.mode == 'verify':
            print('VERIFY_PASS simv66/2MiB/773/144/600s NO_VCS', flush=True)
        else:
            manifest = dict(manifest, authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL')
            run = FunctionType(worker.run.__code__, dict(worker.run.__globals__, BUDGET=BUDGET,
                PRE=ELF.parent, ELF_SEAL=ELF_SHA, IMAGE_SEAL=IMAGE_SHA,
                preflight=SimpleNamespace(NAME=NAME), command=command), argdefs=worker.run.__defaults__)
            run(out, manifest)


if __name__ == '__main__':
    main()
