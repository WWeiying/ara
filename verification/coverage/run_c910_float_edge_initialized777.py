"""One separately authorized600s old-image run; no rebuild/retry/admission."""
import argparse
from pathlib import Path
from types import FunctionType, ModuleType, SimpleNamespace
import preflight_c910_float_edge_initialized as p
import run_vfirst_long_mask as inherited

life, require = p.life, p.require
NAME = 'c910_float_edge_initialized'
PRE = life.OUT / 'c910-float-edge-initialized-preflight777-agent-20261007-02/preflight.json'
PRE_SHA = '87bd79d63e58c6d2056fce535377a348c08c7ad3baacf0cdb829e245ca4e5bdb'
ELF = PRE.parent / 'input.elf'
ELF_SHA = '3412e2557352787ec788c1608c401bf4a0c78524a534db662c7d1c858d825b58'
BASE = life.OUT / 'akv-entropy-offline-admitted777-parent-20261007-01'
BASE_SHA = '39ad0375146e5a6d98f1ef0141030f95309e2a8409dc71f6d510b59631bc3d52'
IMAGE_SHA, COMPILE, COMPILE_SHA = inherited.IMAGE_SHA, inherited.COMPILE, inherited.COMPILE_SHA
BUDGET = 600
SIGNALS = ['ex4_result_lfn', 'vfdsu_ex4_result_lfn', 'vfdsu_ex4_potnt_of',
           'vfdsu_ex4_of', 'ex4_of_plus', 'vfdsu_ex4_potnt_uf', 'ex4_uf_plus']


def command(out):
    return [str(life.IMAGE), '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
        '+PRELOAD=' + str(ELF), '+TESTCASE=' + NAME, '+COMMIT_TOHOST=80001000',
        '+COMMIT_TRACE=' + str(out / 'commit_trace.csv'), '+VECTOR_TRACE=' + str(out / 'vector_trace.csv'),
        '-cm', 'line+cond+fsm+tgl+branch', '-cm_dir', str(out / 'code.vdb'), '-cm_name', NAME]


def preflight():
    pre = life.read_bound(PRE, PRE_SHA); life.check(pre['input_pins'])
    counts = pre['counts']; runtime = counts['runtime']
    require(pre['status'] == 'C910_INITIALIZED_FLOAT_EDGE_HOST_SPIKE_PASS_NOT_DUT' and pre['ELF'] == str(ELF)
        and life.digest(ELF) == ELF_SHA and counts['checks'] == 1440 and counts['cases'] == 48
        and counts['CSR_values'] == 288 and counts['defined_vector_writer_bytes'] == 4608
        and counts['result_store_bytes'] == 1536 and counts['no_skip'] is True
        and runtime['entry_to_tohost_instructions'] == 36997 and runtime['stack_top'] == 0x80040000
        and runtime['stack_depth'] == 176 and runtime['all_runtime_memory_widths_decoded'] is True
        and pre['coverage_admitted'] is False and pre['VCS_started'] is False, 'Exact frozen floating-edge preflight')
    require(counts['initialization'] == dict(groups=3, bytes=3072, registers=24, VL=1024, vtype=3, vstart=0, vcsr=0), 'Full initialized groups')
    require(sorted(pre['actual_static_vector_instructions']) == sorted(['vsetvli', 'vfdiv.vv'] * 3 +
        [f'vle{w}.v' for w in (16, 32, 64) for _ in range(2)] + [f'vse{w}.v' for w in (16, 32, 64)] + ['vsetvli'] + ['vmv.v.i'] * 3), 'Explicit linked RVV set')
    require('sim_l2_mb=2' in life.read_bound(COMPILE, COMPILE_SHA)['command'], 'Frozen 2MiB configuration')
    return pre


def baseline():
    base = life.read_bound(BASE / 'admission-manifest.json', BASE_SHA)
    require(base['coverage_admitted'] is True, 'Formal777 admitted required')
    ledger_path = BASE / 'combined-inputs.txt'
    require(life.digest(ledger_path) == base['output_pins'][str(ledger_path)], 'Sealed777 ledger')
    ledger = ledger_path.read_text().splitlines()
    require(len(ledger) == len(set(ledger)) == 778, 'Exactly777 unique inputs')
    bits_path = BASE / 'combined-bits.json'
    bits = life.read_bound(bits_path, base['output_pins'][str(bits_path)])
    require(bits['tests'] == ledger[1:], 'Exact formal777 bitmap prefix')
    counts = dict(line=1892, cond=2023, branch=2155, fsm=92)
    require(set(bits['metrics']) == set(counts) and all(len(bits['metrics'][m]) == n for m, n in counts.items()), 'Full6162 metric-instance population')
    return base, bits, ledger


def prepare(out, existing=False):
    require(out.parent == life.OUT and out.resolve() == out and
        (out.is_dir() if existing else not out.exists()), 'Fresh run or explicit terminal directory')
    pre = preflight(); base, bits, ledger = baseline()
    image = life.read_bound(life.PLAN, life.PLAN_SEAL)
    require(len(image['image']) == 66 and image['image'][str(life.IMAGE)] == IMAGE_SHA, 'Exact frozen runtime66')
    pins = life.merge_pins(pre['input_pins'], image['image'])
    fixed = {PRE: PRE_SHA, COMPILE: COMPILE_SHA, life.PLAN: life.PLAN_SEAL,
             BASE / 'admission-manifest.json': BASE_SHA}
    for name in ('combined-inputs.txt', 'combined-bits.json'):
        path = BASE / name; fixed[path] = base['output_pins'][str(path)]
    for name, sha in bits['design'].items():
        path = Path(ledger[0]) / 'snps/coverage/db' / name
        require(base['input_pins'][str(path)] == sha, 'Design source identity')
        fixed[path] = sha
    # Pin the actual worker import closure, not a future mutable collector.
    modules, seen = [p, inherited], set()
    while modules:
        module = modules.pop()
        if id(module) in seen: continue
        seen.add(id(module)); file = getattr(module, '__file__', None)
        if file:
            path = Path(file).resolve()
            if path.suffix == '.py' and life.ROOT / 'verification' in path.parents:
                fixed[path] = life.digest(path)
                modules.extend(v for v in vars(module).values() if isinstance(v, ModuleType))
    for name in ('run_c910_float_edge_initialized777.py', 'test_run_c910_float_edge_initialized777.py'):
        path = Path(__file__).with_name(name); fixed[path] = life.digest(path)
    pins = life.merge_pins(pins, {str(path): sha for path, sha in fixed.items()}); life.check(pins)
    return dict(schema='C910_INITIALIZED_FLOAT_EDGE_RUN777_V1', case=NAME, output=str(out), command=command(out), pins=pins,
        preflight=str(PRE), preflight_seal=PRE_SHA, image_sha256=IMAGE_SHA, elf_sha256=ELF_SHA,
        baseline=777, baseline_seal=BASE_SHA, timeout_s=600, scalar_reference_instructions=36997,
        old_image_files_checked=66, foreground_lifetime=True, automatic_retry=False,
        authorization_source='SEPARATE_PARENT_AGENT_REVIEW_REQUIRED_BEFORE_RUN',
        systemd_policy=dict(RuntimeMaxSec=660, TimeoutStopSec=10, KillMode='control-group'),
        no_FSDB=True, raw_commit=True, raw_vector=True, coverage_admitted=False, admission_performed=False,
        RTL_modified=False, source_hypothesis_signals=SIGNALS, expected_gain=None,
        qualification_required='Full scalar/memory/CSR/defined native RVV strict diff; exact777 all6162 OR; no gain assumed')


def invoke_run(out, manifest):
    worker = inherited.worker
    namespace = dict(worker.run.__globals__, BUDGET=BUDGET, PRE=ELF.parent, ELF_SEAL=ELF_SHA,
        IMAGE_SEAL=IMAGE_SHA, preflight=SimpleNamespace(NAME=NAME), command=command)
    FunctionType(worker.run.__code__, namespace, argdefs=worker.run.__defaults__)(out,
        dict(manifest, authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL'))


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('mode', choices=('prepare', 'verify', 'run'))
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--seal')
    parser.add_argument('--parent-authorized', action='store_true'); args = parser.parse_args()
    require((args.mode != 'prepare') == bool(args.seal), 'Verify/run prepared seal required')
    require((args.mode == 'run') == args.parent_authorized, 'Explicit separate parent run authorization required')
    out = args.output.resolve(); record = out.with_name(out.name + '.prepared.json'); manifest = prepare(out)
    if args.mode == 'prepare': life.save(record, manifest); print('PREPARED_NO_VCS', life.digest(record), len(manifest['pins']), flush=True)
    else:
        require(life.read_bound(record, args.seal) == manifest, 'Prepared command/pins differ')
        if args.mode == 'verify': print('VERIFY_PASS_NO_VCS', flush=True)
        else: invoke_run(out, manifest)


if __name__ == '__main__': main()

