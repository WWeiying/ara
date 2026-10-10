"""One separately authorized 900s frozen-image matrix; no compilation/retry."""
import argparse
from pathlib import Path
from types import FunctionType, ModuleType, SimpleNamespace
import preflight_fclass_divsqrt783 as p
import run_c910_float_edge_initialized777 as template

life, require = p.life, p.require
NAME = 'fclass_divsqrt_matrix783'
PRE = life.OUT / 'fclass-divsqrt-matrix783-preflight-agent-20261008-04/preflight.json'
PRE_SHA = 'c305ec9c710bfc78e137ef05562e19972a167ce6db1a0553d82b12325bb48618'
ELF = PRE.parent / 'input.elf'
ELF_SHA = '347249b94a6d78fdfb4292a1c4bac9efe5d7e31fd854446d14651c6a37a6bb08'
BASE, BASE_SHA = p.BASE, p.BASE_SHA
IMAGE_SHA, COMPILE, COMPILE_SHA = template.IMAGE_SHA, template.COMPILE, template.COMPILE_SHA
BUDGET, INSTRUCTIONS = 900, 165928


def command(out):
    return [str(life.IMAGE), '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
        '+PRELOAD=' + str(ELF), '+TESTCASE=' + NAME, '+COMMIT_TOHOST=80001000',
        '+COMMIT_TRACE=' + str(out / 'commit_trace.csv'), '+VECTOR_TRACE=' + str(out / 'vector_trace.csv'),
        '-cm', 'line+cond+fsm+tgl+branch', '-cm_dir', str(out / 'code.vdb'), '-cm_name', NAME]


def preflight():
    pre = life.read_bound(PRE, PRE_SHA); life.check(pre['input_pins'])
    c = pre['counts']; r = c['runtime']
    require(pre['status'] == 'FINITE_FCLASS_DIVSQRT783_HOST_SPIKE_PASS_NOT_DUT'
        and pre['ELF'] == str(ELF) and life.digest(ELF) == ELF_SHA
        and c['checks'] == 2251 and c['cases'] == 75 and c['FCLASS'] == 30 and c['DIV'] == 30
        and c['SQRT'] == 15 and c['CSR_values'] == 452 and c['initialization_bytes'] == 3072
        and c['defined_vector_writer_bytes'] == 7200 and c['no_skip'] is True
        and r['entry_to_tohost_instructions'] == INSTRUCTIONS and r['scalar_memory_events'] == 30460
        and r['all_runtime_memory_widths_decoded'] is True and r['stack_depth'] == 384
        and pre['population'] == 783 and pre['baseline_seal'] == BASE_SHA
        and pre['VCS_started'] is False and pre['coverage_admitted'] is False, 'Exact frozen matrix preflight')
    require('sim_l2_mb=2' in life.read_bound(COMPILE, COMPILE_SHA)['command'], 'Frozen memory configuration')
    return pre


def baseline():
    m = life.read_bound(BASE / 'admission-manifest.json', BASE_SHA)
    require(m['coverage_admitted'] is True, 'Formal783 required')
    ledger = BASE / 'combined-inputs.txt'
    require(life.digest(ledger) == m['output_pins'][str(ledger)], 'Exact ledger SHA')
    lines = ledger.read_text().splitlines()
    require(len(lines) == len(set(lines)) == 784, '783 unique tests and design')
    path = BASE / 'combined-bits.json'; bits = life.read_bound(path, m['output_pins'][str(path)])
    require(bits['tests'] == lines[1:] and {k: len(v) for k, v in bits['metrics'].items()} ==
        dict(line=1892, cond=2023, branch=2155, fsm=92), 'Exact population/all6162 instances')
    return m, bits, lines


def prepare(out, existing=False):
    require(out.resolve() == out and out.parent == life.OUT and
        (out.is_dir() if existing else not out.exists()), 'Independent fresh output or explicit terminal')
    pre = preflight(); base, bits, lines = baseline()
    image = life.read_bound(life.PLAN, life.PLAN_SEAL)
    require(len(image['image']) == 66 and image['image'][str(life.IMAGE)] == IMAGE_SHA, 'Frozen66 files')
    pins = life.merge_pins(pre['input_pins'], image['image'])
    fixed = {str(PRE): PRE_SHA, str(COMPILE): COMPILE_SHA, str(life.PLAN): life.PLAN_SEAL,
        str(BASE / 'admission-manifest.json'): BASE_SHA}
    for name in ('combined-inputs.txt', 'combined-bits.json'):
        path = BASE / name; fixed[str(path)] = base['output_pins'][str(path)]
    for name, sha in bits['design'].items():
        path = Path(lines[0]) / 'snps/coverage/db' / name
        require(base['input_pins'][str(path)] == sha, 'Design/source identity')
        fixed[str(path)] = sha
    modules, seen = [p, template], set()
    while modules:
        module = modules.pop()
        if id(module) in seen: continue
        seen.add(id(module)); file = getattr(module, '__file__', None)
        if file:
            path = Path(file).resolve()
            if path.suffix == '.py' and life.ROOT / 'verification' in path.parents:
                fixed[str(path)] = life.digest(path)
                modules.extend(v for v in vars(module).values() if isinstance(v, ModuleType))
    for name in ('run_fclass_divsqrt783.py', 'test_run_fclass_divsqrt783.py'):
        path = Path(__file__).with_name(name); fixed[str(path)] = life.digest(path)
    pins = life.merge_pins(pins, fixed); life.check(pins)
    return dict(schema='FCLASS_DIVSQRT_RUN783_V1', case=NAME, output=str(out), command=command(out), pins=pins,
        preflight=str(PRE), preflight_seal=PRE_SHA, image_sha256=IMAGE_SHA, elf_sha256=ELF_SHA,
        baseline=783, baseline_seal=BASE_SHA, timeout_s=BUDGET, scalar_reference_instructions=INSTRUCTIONS,
        budget_estimate=dict(reference_instructions=193080, reference_wall_seconds=623,
            linear_estimate_seconds=INSTRUCTIONS * 623 / 193080, budget_seconds=BUDGET,
            measured_for_this_case=False, reason='Scalar estimate plus serialized DIV/SQRT allowance; no retry'),
        old_image_files_checked=66, foreground_lifetime=True, automatic_retry=False,
        authorization_source='SEPARATE_PARENT_AGENT_REVIEW_REQUIRED_BEFORE_RUN',
        systemd_policy=dict(RuntimeMaxSec=960, TimeoutStopSec=10, KillMode='control-group'),
        no_FSDB=True, raw_commit=True, raw_vector=True, coverage_admitted=False, admission_performed=False,
        RTL_modified=False, probe=dict(kind='existing_architectural_trace_and_native_VDB',
            pc_roles={k: v for k, v in pre['symbols'].items() if k.startswith('matrix_')},
            targets=str(PRE.parent / 'dynamic-targets783.json'), cycle_internal_signals_observed=False),
        qualification_required='Full scalar/RVC-memory/CSR/guards/native VRF+identity; target gain measured only')


def invoke_run(out, manifest):
    worker = template.inherited.worker
    ns = dict(worker.run.__globals__, BUDGET=BUDGET, PRE=ELF.parent, ELF_SEAL=ELF_SHA,
        IMAGE_SEAL=IMAGE_SHA, preflight=SimpleNamespace(NAME=NAME), command=command)
    FunctionType(worker.run.__code__, ns, argdefs=worker.run.__defaults__)(out,
        dict(manifest, authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'verify', 'run'))
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--seal')
    parser.add_argument('--parent-authorized', action='store_true'); a = parser.parse_args()
    require((a.mode != 'prepare') == bool(a.seal) and (a.mode == 'run') == a.parent_authorized, 'Exact authorization')
    out = a.output.resolve(); record = out.with_name(out.name + '.prepared.json'); m = prepare(out)
    if a.mode == 'prepare':
        life.save(record, m); print('PREPARED_NO_VCS', life.digest(record), len(m['pins']), flush=True)
    else:
        require(life.read_bound(record, a.seal) == m, 'Prepared contract differs')
        if a.mode == 'verify': print('VERIFY_PASS_NO_VCS', flush=True)
        else: invoke_run(out, m)


if __name__ == '__main__': main()
