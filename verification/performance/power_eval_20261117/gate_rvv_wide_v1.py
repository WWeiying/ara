#!/usr/bin/env python3
"""Four >=20000-cycle contiguous RVV windows, immutable reused image, no retry."""
import argparse
import csv
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


t = load(HERE / 'gate_rvv_short_v1.py', 'wide_readonly_predecessor')
b, e, d, s = t.b, t.e, t.d, t.s
OUT, PARENT = b.OUT, t.DEFAULT
IMAGE = PARENT / 'image'
DEFAULT = OUT / 'power_gls_20261117_baseline_rvv_wide_02'
POWER = OUT / 'power_dc_20261117_baseline_rvv_wide_02'
Q8_RELEASE = e.PARENT / 'releases/q8_01/release.json'
GIB = 1024 ** 3


def anchors_window(trace, pc, minimum_first):
    anchors = []
    with Path(trace).open() as stream:
        for row in csv.DictReader(stream):
            cycle = int(row['cycle'])
            if row['event'] == 'retire' and int(row['pc'], 16) == pc and cycle >= minimum_first:
                anchors.append(cycle)
                if cycle - anchors[0] >= 20000:
                    break
    b.require(len(anchors) >= 2 and 20000 <= anchors[-1] - anchors[0] <= 32768,
              'Complete same-phase loop/tile boundaries must span 20000..32768 cycles')
    return dict(first_cycle=anchors[0] + 1, last_cycle=anchors[-1] + 1,
                cycles=anchors[-1] - anchors[0], anchor_pc=hex(pc), anchor_cycles=anchors,
                trace=str(trace), trace_sha256=b.sha(trace), includes_compute_and_wait=True,
                interval_semantics='Contiguous clock interval, no idle/stall filtering',
                clock_relation='RTL pre-edge to gate post-edge +1; measured mapped phase must pass independently',
                gate_phase_checked=False, whole_task_energy=False)


def disk_check(free, remaining):
    required = (256 + remaining * 48) * GIB
    b.require(free >= required, 'Insufficient independent VCD/SAIF/headroom disk reserve')
    return dict(free_bytes=free, required_free_bytes=required, remaining_cases=remaining,
                per_case_vcd_limit=32 * GIB, per_case_reserved_bytes=48 * GIB,
                other_workers_headroom_bytes=256 * GIB)


def identities(kind):
    if kind == 'q8':
        root = OUT / 'power_legacy_q8_prepare_20261117_01'
        left, right = root / 'qbs', root / 'rvv'
        names = ('activation_f32.bin', 'source_weight.bin', 'golden_f32.bin')
        shape, phase = dict(m=1, n=256, k=896, weight='Q8_0', input='runtime F32->Q8_0'), 'quantized_matmul'
    elif kind == 'm1':
        root = OUT / 'operator_projection_real_prepare_20261115_release_01/cases'
        left = root / 'qwen3_real_decode_attn_q_m1_n64_native'
        right = root / 'qwen3_real_decode_attn_q_m1_n64_rvv_x32'
        names = ('input_f32.bin', 'weights_row.bin', 'expected.bin')
        shape, phase = dict(m=1, n=64, k=2048, weight='Q4_K', input='runtime F32->Q8_K'), 'quantized_matmul'
    elif kind == 'm4':
        left = OUT / 'power_q4_m4_compact_20261117_native_02/data'
        right = OUT / 'power_q4_m4_compact_20261117_rvv_02/data'
        names = ('input_f32.bin', 'weights_row.bin', 'expected.bin', 'expected_q8.bin', 'expected_packed.bin')
        shape, phase = dict(m=4, n=64, k=2048, weight='Q4_K', input='runtime F32->Q8_K'), 'quantized_matmul'
    else:
        left = OUT / 'power_attention_prepare_20261117_akv_01/inputs'
        right = OUT / 'power_attention_prepare_20261117_rvv_01/inputs'
        names = ('query.bin', 'key.bin', 'value.bin', 'mask.bin', 'golden.bin', 'model_golden.bin')
        shape, phase = dict(d=128, heads=2, kvheads=1, kv_tokens=137, tile_tokens=64), 'pack_QK_softmax_PV_complete_tile'
    pairs, pins = {}, {}
    for name in names:
        a, z = left / name, right / name
        h = b.sha(a)
        b.require(h == b.sha(z), 'Native/RVV captured data identity mismatch: ' + kind + '/' + name)
        pins.update({str(a): h, str(z): h})
        pairs[name] = dict(native=str(a), rvv=str(z), sha256=h)
    return dict(shape=shape, phase=phase, paired_capture_inputs=pairs,
                formal_pair_requirement='Native and RVV >=20000 cycles, same shape and semantic phase; measured control/phase admission required',
                existing_short_native_window_is_not_a_formal_pair=True,
                phase_comparability_verified=False, paired_ratio_publishable=False), pins


def prepare(out):
    b.require(out == DEFAULT and not out.exists() and not POWER.exists(), 'Fresh owned wide outputs required')
    b.verify(b.read(PARENT / 'source-pins.json'))
    b.verify(b.read(IMAGE / 'source-pins.json'))
    images = b.read(IMAGE / 'image-pins.json')
    b.verify(images)
    validation = b.read(IMAGE / 'environment-validation.json')
    b.require(validation['state'] == 'OPPOSITE_VRF_SEEDS_EXACT_REDUCTIONS_PASS' and
              validation['seeds'] == [0, 1] and validation['runtime_force'] is False and
              validation['controls_initialized'] is False, 'Reuse only the actually validated startup environment')
    disk = disk_check(shutil.disk_usage(OUT).free, 4)
    out.mkdir()
    (out / 'inputs').mkdir()
    for p in (PARENT / 'inputs').glob('*.py'):
        shutil.copyfile(p, out / 'inputs' / p.name)
    for name in ('gate_rvv_wide_v1.py', 'test_gate_rvv_wide_v1.py', 'gate_rvv_wide_power_v1.py'):
        shutil.copyfile(HERE / name, out / 'inputs' / name)
    binding = b.read(PARENT / 'image-binding.json')
    b.save(out / 'image-binding.json', binding, True)
    release = b.read(Q8_RELEASE)
    b.verify(release['evidence_pins'])
    q8_original = Path(release['cases'][0]['evidence']['result.json']['path'])
    q8 = b.read(q8_original)
    b.require(q8['state'] == q8['numeric']['state'] == 'PASS' and q8['independent_protocol_checked'] is True,
              'Original strict Q8 RTL numerical/protocol PASS required')
    b.save(out / 'q8-admission.json', dict(schema='wide-q8-original-strict-pass-admission-v1',
        state='STRICT_RTL_PASS_REUSED_FOR_ACTIVITY', original_result=str(q8_original),
        original_result_sha256=b.sha(q8_original), release=str(Q8_RELEASE), release_sha256=b.sha(Q8_RELEASE),
        elf_sha256=q8['elf_sha256'], original_worker_reclassified=False, full_gate_task_pass=False), True)
    contracts, cases, extra = {}, [], {}
    for kind, pc, first in [('q8', 0x80000478, 62618), ('m1', 0x800022f8, 32413),
                             ('attention', 0x80001308, 59757), ('m4', 0x80002568, 207736)]:
        contract, cpins = identities(kind)
        extra.update(cpins)
        if kind == 'q8':
            p = b.read(PARENT / 'cases/m1/plan.json')
            audit = out / 'q8-admission.json'
            elf = Path(release['cases'][0]['elf']['path'])
            trace = q8_original.parent / 'commit.csv'
            expected_state = 'PASS'
        else:
            p = b.read(PARENT / 'cases' / kind / 'plan.json')
            audit, elf = Path(p['rtl_admission']), Path(p['elf'])
            trace = Path(b.read(audit)['run']) / 'commit.csv'
            expected_state = 'FAIL'
        window = anchors_window(trace, pc, first)
        contract['window'] = window
        contract['strict_original_state'] = expected_state
        contracts[kind] = contract
        case = out / 'cases' / kind
        (case / 'inputs').mkdir(parents=True)
        (case / 'run').mkdir()
        shutil.copyfile(elf, case / 'inputs/program.elf')
        shutil.copyfile(PARENT / 'cases/m1/inputs/rtl-plan.json', case / 'inputs/rtl-plan.json')
        maximum = window['last_cycle'] + 128
        command = [str(IMAGE / 'sim/simv'), '-no_save', '-l', str(case / 'run/run.vcs.log'),
            '+PRELOAD=' + str(case / 'inputs/program.elf'), '+TESTCASE=rvv_wide_' + kind,
            '+NO_FSDB', '+NO_INSTR_TRACE', '+GATE_VRF_INIT_SEED=0', '+GATE_MAX_CYCLES=' + str(maximum),
            '+GATE_VCD=' + str(case / 'run/window.vcd'), '+GATE_ROI_FIRST=' + str(window['first_cycle']),
            '+GATE_ROI_LAST=' + str(window['last_cycle']), '+GATE_STOP_AFTER_CAPTURE']
        p.update(kind=kind, command=command, cwd=str(case / 'run'), image=str(IMAGE),
            elf=str(case / 'inputs/program.elf'), elf_sha256=b.sha(elf), rtl_admission=str(audit),
            rtl_admission_sha256=b.sha(audit), first_cycle=window['first_cycle'], last_cycle=window['last_cycle'],
            max_cycles=maximum, window_basis=window, diagnostic_only=False, strict_original_state=expected_state,
            wall_seconds=21600, slot_seconds=21600, max_vcd_bytes=32 * GIB, max_log_bytes=256 * 1024**2,
            minimum_formal_cycles=20000, phase_contract=contract)
        b.save(case / 'plan.json', p, True)
        extra.update({str(trace): b.sha(trace), str(elf): b.sha(elf), str(audit): b.sha(audit)})
        cases.append(dict(key=kind, path=str(case)))
    b.save(out / 'phase-contracts.json', contracts, True)
    b.save(out / 'disk-budget.json', disk, True)
    b.save(out / 'plan.json', dict(schema='rvv-four-wide-windows-v1', cases=cases, image=str(IMAGE),
        no_compile=True, no_existing_worker_changes=True, minimum_cycles=20000, own_parallelism=1,
        max_global_simv=4, shared_locks='canonical GLS then v3 interop', automatic_retry=False,
        stop_after_first_failure=True, full_task_pass=False, paired_ratio_publishable=False), True)
    with (out / 'host-tests.log').open('x') as log:
        subprocess.run([sys.executable, '-B', str(out / 'inputs/test_gate_rvv_wide_v1.py'), '-v'],
                       check=True, stdout=log, stderr=subprocess.STDOUT, timeout=120)
    pins = {str(p): b.sha(p) for p in out.rglob('*') if p.is_file()}
    pins.update(extra)
    pins.update(images)
    for p in (PARENT / 'source-pins.json', IMAGE / 'source-pins.json', IMAGE / 'image-pins.json',
              IMAGE / 'environment-validation.json', Q8_RELEASE):
        pins[str(p)] = b.sha(p)
    b.save(out / 'source-pins.json', pins, True)
    unit = out.name.replace('_', '-') + '.service'
    worker = ['/usr/bin/python3', '-B', str(out / 'inputs/gate_rvv_wide_v1.py'), 'execute', '--output', str(out),
              '--plan-sha256', b.sha(out / 'plan.json')]
    service = ['systemd-run', '--user', '--unit=' + unit, '--property=Type=exec', '--property=KillMode=control-group',
        '--property=RuntimeMaxSec=172800', '--property=StandardOutput=append:' + str(out / 'service.stdout.log'),
        '--property=StandardError=append:' + str(out / 'service.stderr.log'), *worker]
    b.save(out / 'ready-command.json', dict(service=service), True)


def power_worker(out, kind):
    dc = load(out / 'inputs/dc_power.py', 'wide_power_prepare_' + kind)
    oldpair = OUT / 'power_dc_20261117_activity_follow_02' / ('akv' if kind == 'attention' else kind)
    template = OUT / 'power_dc_20261117_activity_follow_02/m1' if kind == 'q8' else oldpair
    job = dc.read(template / 'rvv/chain-plan.json')
    pair, role = POWER / kind, POWER / kind / 'rvv'
    (role / 'inputs').mkdir(parents=True)
    (role / 'reports').mkdir()
    limits = ['Contiguous >=20000-cycle compute-and-wait window, not full-task energy or GLS PASS',
              'Native paired ratio blocked until same shape/phase >=20000-cycle native evidence is admitted',
              'Original strict outcomes retained; Q8 PASS and Q4/attention FAIL are distinct',
              'Unknown idle SRAM is reported; critical controls and real compute phase must pass',
              'Reconstructed historical baseline byte identity UNPROVEN']
    dc.save(pair / 'pair-plan.json', dict(runs=dict(native=str(pair / 'native-not-collected'), rvv=str(role)),
        library_sha256=job['library_sha256'], limitations=limits))
    unit = 'power-dc-20261117-baseline-rvv-wide-' + kind + '-01.service'
    job.update(kind='akv' if kind == 'attention' else kind, capture_run=str(out / 'cases' / kind),
        pair=str(pair), service_unit=unit, limitations=limits,
        conversion_output=str(OUT / ('power_saif_20261117_baseline_rvv_wide_' + kind + '_01')))
    dc.save(role / 'chain-plan.json', job)
    pins = {str(p): dc.sha(p) for p in (pair / 'pair-plan.json', role / 'chain-plan.json')}
    for name in ('dc_power.py', 'convert.py', 'gate_rvv_wide_power_v1.py'):
        dst = role / 'inputs' / name
        shutil.copyfile(out / 'inputs' / name, dst)
        pins[str(dst)] = dc.sha(dst)
    dc.save(role / 'chain-pins.json', pins)
    service = ['systemd-run', '--user', '--unit=' + unit, '--property=Type=exec', '--property=KillMode=control-group',
        '--property=RuntimeMaxSec=86400', '--property=StandardOutput=append:' + str(role / 'service.stdout.log'),
        '--property=StandardError=append:' + str(role / 'service.stderr.log'), '/usr/bin/python3', '-B',
        str(role / 'inputs/gate_rvv_wide_power_v1.py'), '--output', str(role), '--authorize-dc']
    dc.save(role / 'ready-command.json', dict(service=service))
    subprocess.run(service, check=True, timeout=30)


def execute(out, plan_sha):
    b.require(out == DEFAULT and Path(__file__).resolve() == out / 'inputs/gate_rvv_wide_v1.py', 'Frozen wide worker required')
    unit = out.name.replace('_', '-') + '.service'
    owner = subprocess.check_output(['systemctl', '--user', 'show', unit, '-p', 'MainPID', '--value'], text=True).strip()
    b.require(owner == str(os.getpid()) and unit in Path('/proc/self/cgroup').read_text(), 'Direct service owner required')
    b.require(b.sha(out / 'plan.json') == plan_sha, 'Plan drift')
    pins, plan = b.read(out / 'source-pins.json'), b.read(out / 'plan.json')
    b.verify(pins)
    b.save(out / 'attempt.json', dict(pid=os.getpid(), started_ns=time.time_ns()), True)
    def interrupted(signum, frame):
        raise InterruptedError(signum)
    signal.signal(signal.SIGTERM, interrupted)
    results = []
    try:
        b.q8_units = s.q8_gls_units
        dc = load(out / 'inputs/dc_power.py', 'wide_activity_checker')
        for index, entry in enumerate(plan['cases']):
            case = Path(entry['path'])
            p = b.read(case / 'plan.json')
            disk = disk_check(shutil.disk_usage(OUT).free, len(plan['cases']) - index)
            b.save(case / 'disk-admission.json', disk, True)
            b.verify(pins)
            run = b.run_capture(out, case, p, pins)
            result = b.finish_capture(case, p, b.read(out / 'image-binding.json'), run)
            # The inherited EOF helper has Q4-only metadata; retain Q8's true original PASS.
            result['strict_original_state'] = p['strict_original_state']
            warnings = d.log_evidence(case / 'run/run.vcs.log')
            b.require(not warnings['counts'], 'Enabled SRAM X remains; do not convert activity')
            ev = result['vcd_evidence']
            report = dc.scan_activity_vcd(case / 'run/window.vcd', p['last_cycle'] - p['first_cycle'],
                ev['first_tick'], ev['last_tick'], p['window_basis']['anchor_pc'])
            report.update(dc.activity_policy(report, 'rvv', 'akv' if entry['key'] == 'attention' else entry['key'], p['window_basis']['anchor_pc']))
            b.save(case / 'activity-audit.json', report, True)
            b.require(report['state'] == 'ACTIVITY_WINDOW_ELIGIBLE_NOT_GLS_PASS', 'Critical control/phase rejection: ' + str(report['reasons']))
            b.require(p['last_cycle'] - p['first_cycle'] >= 20000, 'Formal duration gate')
            result.update(log=str(case / 'run/run.vcs.log'), first_cycle=p['first_cycle'], last_cycle=p['last_cycle'],
                clock_period_ns=1, phase_contract=p['phase_contract'], minimum_formal_cycles=20000,
                mapped_compute_phase_observed=True, includes_compute_and_wait=True,
                paired_ratio_publishable=False, power_acceptance=False, full_gate_task_pass=False)
            b.verify(pins)
            b.save(case / 'result.json', result, True)
            results.append(dict(key=entry['key'], result=str(case / 'result.json')))
            power_worker(out, entry['key'])
        result = dict(state='FOUR_WIDE_WINDOWS_COMPLETE_POWER_CHAINS_LAUNCHED', cases=results,
                      power_acceptance=False, paired_ratio_publishable=False)
    except BaseException as exc:
        result = dict(state='FAIL_STOP_NO_RETRY', error=repr(exc), completed_cases=results,
                      original_data_unchanged=True, power_acceptance=False)
    b.save(out / 'result.json', result, True)
    b.save(out / 'status.json', dict(state=result['state']))
    return int(result['state'] == 'FAIL_STOP_NO_RETRY')


def main():
    p = argparse.ArgumentParser(allow_abbrev=False)
    p.add_argument('action', choices=('prepare', 'execute'))
    p.add_argument('--output', type=Path, default=DEFAULT)
    p.add_argument('--plan-sha256')
    a = p.parse_args()
    if a.action == 'prepare':
        prepare(a.output)
        return 0
    return execute(a.output, a.plan_sha256)


if __name__ == '__main__':
    raise SystemExit(main())
