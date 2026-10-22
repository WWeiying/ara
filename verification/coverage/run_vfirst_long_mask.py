"""Prepare one separately authorized600s frozen-image vfirst run; no retry."""
import argparse
from pathlib import Path
from types import FunctionType, SimpleNamespace, ModuleType

import preflight_vfirst_long_mask as p
import run_pure_war_simulation as worker
import targeted_toggle_evidence_v2 as toggle
import coverage_bitmap_delta as bitmap

life, require = p.life, p.require
NAME = 'vfirst_long_mask_scalar'
PRE = life.OUT / 'vfirst-long-mask-preflight-agent-20261007-02/preflight.json'
PRE_SHA = '11498ad03cb3378280ea6c92f9cfa525ec955707516fe8ef86a874a9cee99cec'
ELF = PRE.parent / 'input.elf'
ELF_SHA = '32282e9de0acd40cd25b13d856a9732427782e746f35e4568eca7cf03de110ff'
IMAGE_SHA = '2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3'
COMPILE = life.OUT / 'repaired-aligned-build-20260930-01/compile.command.json'
COMPILE_SHA = '30cdd93809c183f5004767d6190ca33d1d78aed68e73dcf42d6fef793269cbb1'
STATIC = life.OUT / 'vfirst-long-mask-static-review775-agent-20261007-01.json'
STATIC_SHA = 'a79117aa3a4ce552f2a6208aa1f43e6b191987a77df20d066c118512568a7cab'
BASE = life.OUT / 'vmacc-offline-admitted775-parent-20261007-01'
BASE_SHA = '59d67f7d5088baefaa498eda1d8e0f607e0eaf87945cc79a5f83607f8d679a13'
CACHE = life.OUT / 'toggle741-capacity-ranking-agent-20261007-01.json'
BUDGET = 600


def command(out):
    return [str(life.IMAGE), '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
            '+PRELOAD=' + str(ELF), '+TESTCASE=' + NAME, '+COMMIT_TOHOST=80001000',
            '+COMMIT_TRACE=' + str(out / 'commit_trace.csv'), '+VECTOR_TRACE=' + str(out / 'vector_trace.csv'),
            '-cm', 'line+cond+fsm+tgl+branch', '-cm_dir', str(out / 'code.vdb'), '-cm_name', NAME]


def preflight():
    pre = life.read_bound(PRE, PRE_SHA)
    life.check(pre['input_pins'])
    counts = pre['counts']; runtime = counts['runtime']
    require(pre['status'] == 'VFIRST_LONG_MASK_HOST_SPIKE_PASS_NOT_DUT' and
            pre['ELF'] == str(ELF) and life.digest(ELF) == ELF_SHA and
            counts['checks'] == 384 and counts['cases'] == 8 and counts['source_writers'] == 8 and
            counts['vfirst_VRF_writers'] == 0 and counts['whole_v0_bytes'] == 1024 and
            runtime['entry_to_tohost_instructions'] == 9918 and runtime['stack_depth'] == 32 and
            runtime['stack_top'] == 0x80040000 and runtime['all_runtime_memory_widths_decoded'] is True and
            pre['actual_static_vector_instructions'] == ['vsetvli', 'vlm.v', 'vfirst.m', 'vs1r.v'] and
            pre['coverage_admitted'] is False and pre['VCS_started'] is False, 'Exact frozen preflight')
    require('sim_l2_mb=2' in life.read_bound(COMPILE, COMPILE_SHA)['command'], 'Frozen2MiB build')
    return pre


def baseline(static):
    base = life.read_bound(BASE / 'admission-manifest.json', BASE_SHA)
    require(base['coverage_admitted'] is True and static['population'] == 775 and
            static['manifest_sha'] == BASE_SHA and static['missing_serialized_slots'] == 20,
            'Formal775/static target binding')
    path = BASE / 'combined-inputs.txt'
    require(life.digest(path) == base['output_pins'][str(path)], 'Formal ledger drift')
    ledger = path.read_text().splitlines()
    require(len(ledger) == len(set(ledger)) == 776, 'Exact775 ledger')
    bits_path = BASE / 'combined-bits.json'
    bits = life.read_bound(bits_path, base['output_pins'][str(bits_path)])
    require(bits['tests'] == ledger[1:], 'Exact775 bitmap prefix')
    scope = static['scope']
    cache = life.read_bound(CACHE, static['pins'][str(CACHE)])
    value = {scope: {k: cache['instances'][scope][k] for k in ('width', 'checksum', 'bits')}}
    for db in ledger[742:]:
        files = list((Path(db) / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(files) == 1 and str(files[0]) in static['pins'], 'Exact admitted suffix Toggle pin')
        sample, sha = toggle.rows(files[0], [scope])
        require(sha == static['pins'][str(files[0])], 'Suffix data drift')
        value = toggle.union(value, sample)
    require(value[scope]['width'] == static['serialized_width'] and
            value[scope]['checksum'] == static['toggle_checksum'], 'Exact native Toggle shape')
    slots = [i for t in static['targets'] for i in t['serialized_slots']]
    require(len(slots) == len(set(slots)) == 20 and all(
        not (int(value[scope]['bits'], 16) >> (value[scope]['width'] - 1 - i) & 1) for i in slots),
        'All twenty target slots must remain before0')
    return base, bits, value


def prepare(out, existing=False):
    import collect_vfirst_long_mask  # Include the complete collector import closure in run pins.
    require(out.parent == life.OUT and out.resolve() == out and
            (out.is_dir() if existing else not out.exists()), 'Fresh run or explicit terminal directory')
    pre = preflight()
    static = life.read_bound(STATIC, STATIC_SHA); life.check(static['pins'])
    base, bits, before = baseline(static)
    image = life.read_bound(life.PLAN, life.PLAN_SEAL)
    require(len(image['image']) == 66 and image['image'][str(life.IMAGE)] == IMAGE_SHA,
            'Exact frozen runtime66')
    pins = life.merge_pins(life.merge_pins(pre['input_pins'], static['pins']), image['image'])
    fixed = {PRE: PRE_SHA, STATIC: STATIC_SHA, COMPILE: COMPILE_SHA, life.PLAN: life.PLAN_SEAL,
             BASE / 'admission-manifest.json': BASE_SHA}
    for name in ('combined-inputs.txt', 'combined-bits.json'):
        path = BASE / name; fixed[path] = base['output_pins'][str(path)]
    for name, sha in bits['design'].items():
        path = Path((BASE / 'combined-inputs.txt').read_text().splitlines()[0]) / 'snps/coverage/db' / name
        require(base['input_pins'][str(path)] == sha, 'Design source pin ownership')
        fixed[path] = sha
    book = p.source_pins()
    snapshot = life.OUT / 'old-image-source-evidence-20261006-01/ara_dispatcher.sv'
    source_book = life.read_bound(life.OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json',
        book[str(life.OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json')])
    fixed[snapshot] = source_book[str(life.ROOT / 'hardware/src/ara_dispatcher.sv')]
    require(life.digest(snapshot) == fixed[snapshot] and
            'ara_req.vl         = (csr_vl_q >> 3) + |csr_vl_q[2:0];' in snapshot.read_text(),
            'Frozen mask-load native VL=ceil(1024/8)=128')
    modules, seen = [p, worker, toggle, bitmap, collect_vfirst_long_mask], set()
    while modules:
        module = modules.pop()
        if id(module) in seen: continue
        seen.add(id(module))
        file = getattr(module, '__file__', None)
        if file:
            path = Path(file).resolve()
            if path.suffix == '.py' and life.ROOT / 'verification' in path.parents:
                fixed[path] = life.digest(path)
                modules.extend(value for value in vars(module).values() if isinstance(value, ModuleType))
    for name in ('run_vfirst_long_mask.py', 'collect_vfirst_long_mask.py', 'test_vfirst_long_mask_run_collect.py'):
        path = Path(__file__).with_name(name).resolve(); fixed[path] = life.digest(path)
    pins = life.merge_pins(pins, {str(path): sha for path, sha in fixed.items()}); life.check(pins)
    return dict(schema='VFIRST_LONG_MASK_RUN775_V1', case=NAME, output=str(out), command=command(out),
        pins=pins, preflight=str(PRE), preflight_seal=PRE_SHA, image_sha256=IMAGE_SHA, elf_sha256=ELF_SHA,
        baseline=775, baseline_seal=BASE_SHA, targets=static['targets'], scope=static['scope'],
        scoped_toggle_before=before, timeout_s=BUDGET, scalar_reference_instructions=9918,
        expected_missing_coordinates=20, old_image_files_checked=66, foreground_lifetime=True,
        authorization_source='SEPARATE_PARENT_AGENT_REVIEW_REQUIRED_BEFORE_RUN',
        systemd_policy=dict(RuntimeMaxSec=660, TimeoutStopSec=10, KillMode='control-group'),
        automatic_retry=False, no_FSDB=True, raw_commit=True, raw_vector=True,
        coverage_admitted=False, admission_performed=False, RTL_modified=False,
        qualification_required='Full scalar/memory/CSR/guard and native8 vlm/no vfirst VRF; exact775 delta')


def invoke_run(out, manifest):
    ns = dict(worker.run.__globals__, BUDGET=BUDGET, PRE=ELF.parent, ELF_SEAL=ELF_SHA,
              IMAGE_SEAL=IMAGE_SHA, preflight=SimpleNamespace(NAME=NAME), command=command)
    run = FunctionType(worker.run.__code__, ns, argdefs=worker.run.__defaults__)
    run(out, dict(manifest, authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'verify', 'run'))
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--seal')
    parser.add_argument('--parent-authorized', action='store_true')
    args = parser.parse_args()
    require((args.mode != 'prepare') == bool(args.seal), 'Verify/run need prepared seal')
    require((args.mode == 'run') == args.parent_authorized, 'Separate explicit parent run authorization')
    out = args.output.resolve(); record = out.with_name(out.name + '.prepared.json')
    manifest = prepare(out)
    if args.mode == 'prepare':
        life.save(record, manifest); print('PREPARED_NO_VCS', life.digest(record), len(manifest['pins']), flush=True)
    else:
        require(life.read_bound(record, args.seal) == manifest, 'Prepared command/pins differ')
        if args.mode == 'verify': print('VERIFY_PASS_NO_VCS', flush=True)
        else: invoke_run(out, manifest)


if __name__ == '__main__': main()
