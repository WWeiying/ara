#!/usr/bin/env python3
"""Native-only exact-ELF capture plus target completion, without another GLS run.

Reuse pinned runner primitives, never edit a sealed runner/TB/checker. Gate target
proofs deliberately exclude unavailable RTL engine/protocol/commit monitors.
"""
import argparse
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
BASE = OUT / 'power_gls_20261117_q8_smoke_02/inputs/gate_run.py'
BASE_SHA = 'e05b5a5b23a5ca3ade67aebd10843029b5e1012745210fb1d87678ae43f37f5d'
CONTROL_SHA = 'd0ec28d8870c2dff756706c9543e166216f399fb20df6736c46c9cd610cdc7a6'
M1 = 'qwen3_real_decode_attn_q_m1_n64_native'
AKV = 'power_attention_akv'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base_path = HERE / 'gate_run_base.py' if (HERE / 'gate_run_base.py').exists() else BASE
if sha(base_path) != BASE_SHA:
    raise ValueError('Sealed base runner identity drift')
b = load(base_path, 'native_gate_base')
require, read, save, verify = b.require, b.read, b.save, b.verify


def ref(path):
    return dict(path=str(path), sha256=sha(path))


def make_release(output):
    require(output.parent == OUT and output.name.startswith('power_native_release_20261117_') and
            not output.exists(), 'Fresh native release output required')
    selected = [('power_precheck_20261117_native_projection_01', M1,
                 'power_protocol_audit_20261117_q4_m1_01'),
                ('power_precheck_20261117_native_attention_02', AKV,
                 'power_protocol_audit_20261117_attention_01')]
    cases = []
    for queue, case_id, audit in selected:
        campaign = OUT / queue
        case = next(c for c in read(campaign / 'plan.json')['cases'] if c['id'] == case_id)
        work = campaign / 'runs' / case_id
        cases.append(dict(id=case_id, elf=ref(Path(case['elf'])), original_result=ref(work / 'result.json'),
            numerical=ref(work / 'numerical.json'), protocol=ref(OUT / audit / 'protocol.json'),
            protocol_audit=ref(OUT / audit / 'result.json')))
    # Composite admission names the prechecked RTL image, not the later GLS image.
    rtl_image = read(b.GATE / 'gate-receipt.json')['rtl_image']
    release = dict(schema='power-gate-release-v1', state='READY_FOR_AUDIT', image=rtl_image, cases=cases)
    output.mkdir()
    save(output / 'release.json', release, True)
    digest = sha(output / 'release.json')
    try:
        admission = b.admit(b.GATE, output / 'release.json', digest)
    except Exception as error:
        save(output / 'status.json', dict(state='RELEASE_ADMISSION_FAIL', error=repr(error), gls_jobs_launched=0), True)
        raise
    save(output / 'admission.json', dict(admission, release_sha256=digest), True)
    save(output / 'status.json', dict(state='NATIVE_M1_AKV_ADMITTED_NOT_LAUNCHED',
        release_sha256=digest, cases=[c['id'] for c in cases],
        m4='PENDING exact ELF numeric/protocol receipt; raw and compact successors are not interchangeable',
        gls_jobs_launched=0), True)
    return digest


def fields(line, prefix, strings=()):
    result = {}
    for word in line[len(prefix):].split():
        require(word.count('=') == 1, 'Malformed target record')
        key, value = word.split('=')
        require(key not in result and (key in strings or re.fullmatch('[0-9]+', value)), 'Target field syntax')
        result[key] = value if key in strings else int(value)
    return result


def projection_numeric(text, m, compact=False):
    """Exhaustive target comparator/CSR proof; no invented QBS_PERF evidence."""
    b.clean_log(text)
    require(text.count('Core Test *** SUCCESS ***') == 1 and '[QBS_PERF]' not in text,
            'Gate completion or monitor scope mismatch')
    c = m['case']
    if compact:
        require(m['mode'] == 'native' and (c['m'], c['n'], c['k']) == (4, 64, 2048), 'Compact M4 geometry')
        meta = dict(id=m['build_id'], m=4, n=64, k=2048, profile=1, rvv=0, trials=2)
        prefixes = ('OPQ_META ', 'OPQ_TRIAL ', 'OPQC_CHECK ', 'OPQ_DONE ')
        kinds = ('GUARD', 'Q8', 'PACK', 'OUT')
        goldens = m['golden_checks']
    else:
        require(c['backend'] == 'native' and (c['m'], c['n'], c['k']) == (1, 64, 2048), 'Native M1 geometry')
        meta = dict(id=m['build_id'], m=1, n=64, k=2048, profile=c['profile'], ap=c['activation_profile'],
                    kb=c['k_blocks'], ab=c['activation_block_bytes'], rvv=0, trials=2, policy=1)
        prefixes = ('OPR_META ', 'OPR_TRIAL ', 'OPR_CHECK ', 'OPR_DONE ')
        kinds = ('Q8', 'PACK', 'OUT', 'GUARD')
        goldens = m['comparisons']
    records, power = [], []
    for line in text.splitlines():
        if compact and line.startswith('OPQC_POWER '):
            power.append(fields(line, 'OPQC_POWER '))
        elif line.startswith(('OPR_', 'OPQ_', 'OPQC_')):
            prefix = line.split(' ', 1)[0] + ' '
            require(prefix in prefixes, 'Unknown target comparator record')
            records.append((prefix, fields(line, prefix, ('id', 'kind'))))
    require(len(records) == 12 and records[0] == (prefixes[0], meta) and
            records[-1] == (prefixes[3], {'errors': 0}), 'Incomplete target workload records')
    trials = []
    for trial in range(2):
        tag, row = records[1 + trial * 5]
        require(tag == prefixes[1] and row['trial'] == trial and row['status'] == 0 and
                row['commands'] == 2 and row['vcsr'] == 2 and row['vstart'] == 0 and
                row['quant_fcsr'] & ~3 == 0 and row['fcsr'] == m['plan']['flags'] | m['flag_seeds'][trial],
                'Target SDK/flags/CSR failure')
        if compact:
            require(row['context'] == row['eligible'] == 0 and row['coop'] in (0, 1), 'Unexpected context path')
        else:
            require(row['quant_vcsr'] == 2, 'Quantizer CSR drift')
        stamps = [row['t%d' % i] for i in range(6)]
        require(all(0 <= x < y < 2**64 for x, y in zip(stamps, stamps[1:])) and
                (not trials or row['t0'] > trials[-1]['t5']), 'Uncompleted/overlapping target trial')
        for offset, kind in enumerate(kinds):
            tag, check = records[2 + trial * 5 + offset]
            gold = goldens[kind]
            require(tag == prefixes[2] and check['trial'] == trial and check['kind'] == kind and
                    check['count'] == gold['count'] and check['expected_hash'] == gold['expected_hash'] and
                    check['actual_hash'] == check['expected_hash'] and check['mismatches'] == 0 and
                    check['raw_differences'] == 0 and check['first'] == 0xffffffff and
                    check['first_actual'] == check['first_expected'] == 0, 'Exhaustive target comparison failure')
        trials.append(row)
    if compact:
        require(len(power) == 2 and all((r['trial'], r['count'], r['finite'], r['mismatches'], r['first']) ==
                (i, 256, 256, 0, 0xffffffff) for i, r in enumerate(power)), 'Missing finite-output summaries')
        require(all(r['max_abs_bits'] == r['max_ratio_bits'] == 0 for r in power), 'Nonzero strict-native error summary')
    return dict(state='GATE_TARGET_NUMERIC_PASS_NO_RTL_MONITORS', trials=trials,
        output_values_checked=2 * c['m'] * c['n'], exhaustive_target_comparisons=True,
        flags_checked=True, guards_checked=True, gate_engine_monitor_checked=False,
        gate_protocol_checked=False, actual_command_issue_observed=False,
        scope='Target comparator/SDK/CSR/guard proof only; complete RTL work/protocol proof remains separate')


def family(build):
    if build.get('schema') == 'power-attention-single-mode-firmware-20261117-v1':
        c = build['fixture']['case']
        require(build['mode_name'] == 'akv' and build['order'] == [1, 1] and
                (c['dimension'], c['heads'], c['kv_heads'], c['tokens']) == (128, 2, 1, 137), 'Not selected native AKV firmware')
        return 'akv'
    if build.get('schema') == 'power-q4-m4-compact-20261117-v2':
        c = build['case']
        require(build['mode'] == 'native' and (c['m'], c['n'], c['k'], c['profile']) == (4, 64, 2048, 1),
                'Not selected native M4 compact firmware')
        return 'm4_compact'
    c = build.get('case', {})
    require(c.get('backend') == 'native' and c.get('profile') == 1 and
            (c.get('m'), c.get('n'), c.get('k')) == (1, 64, 2048),
            'No completed-gate checker for this firmware; use audited compact M4 successor, not raw UART substitution')
    return 'm1'


def numeric(text, build_path, kind):
    build = read(build_path)
    if kind == 'akv':
        tool = load(ROOT / 'verification/performance/power_eval_20261117/prepare_attention.py', 'native_attention_gate_checker')
        tool.receipt(build_path.parent)
        result = tool.check_text(text, build['fixture'])
        require(result['state'] == 'PASS', 'Native AKV target numerical failure')
        return dict(result, state='GATE_TARGET_NUMERIC_PASS_NO_RTL_MONITORS', gate_protocol_checked=False)
    return projection_numeric(text, build, compact=(kind == 'm4_compact'))


def roi_candidate(work, case_id):
    """Use first-call compute events, avoiding late verbose UART and startup."""
    path = work / 'commit.csv'
    events = []
    if case_id == M1:
        wanted, limit = {0x00b5045b}, 45000
    elif case_id == AKV:
        wanted, limit = {0x0205345b}, 60000
    else:
        raise ValueError('M4 needs an explicit ROI from its own exact-ELF precheck')
    with path.open() as stream:
        for row in csv.DictReader(stream):
            cycle = int(row['cycle'])
            if cycle > limit:
                break
            if row['event'] == 'retire' and int(row['insn'], 16) in wanted:
                require(row['trap'] == '0', 'Architectural trap at ROI anchor')
                events.append(dict(cycle=cycle, pc=row['pc'], insn=row['insn']))
    if case_id == M1:
        require(len(events) == 2, 'Missing first-trial QBS commands')
        first, last = events[0]['cycle'] + 1, events[1]['cycle']
        description = 'Second full-K N32 QBS command and intervening SDK/memory-wait cycles; first trial'
        anchors = events
    else:
        require(len(events) >= 128, 'Missing native PV row-load work')
        anchors = events[64:128]
        first, last = anchors[0]['cycle'] - 1, anchors[-1]['cycle'] + 32
        description = 'Second KV64 tile native PV row-load/FMA phase; not full Attention average'
    require(1024 <= last - first <= b.MAX_WINDOW, 'ROI candidate outside representative bounded budget')
    return dict(first_cycle=first, last_cycle=last, source=ref(path), anchors=anchors,
        selection=description, gate_phase_verified=False, measured_power=False,
        limitation='RTL-cycle hypothesis, not a gate phase guarantee or whole-task energy claim')


def prepare(args):
    out = b.scoped_output(args.output)
    require(not out.exists(), 'Fresh native run output required')
    release = args.release.resolve()
    admission = b.admit(b.GATE, release, args.release_sha256)
    selected = [c for c in admission['cases'] if c['id'] == args.case]
    require(len(selected) == 1, 'Exact case is not admitted')
    selected = selected[0]
    work = Path(selected['original_result']['path']).parent
    campaign = work.parent.parent
    case = next(c for c in read(campaign / 'plan.json')['cases'] if c['id'] == args.case)
    checker = case['checker']
    build_dir = Path(checker[checker.index('--build') + 1])
    build_path = build_dir if build_dir.name == 'build.json' else build_dir / 'build.json'
    m = read(build_path)
    kind = family(m)
    require(sha(selected['elf']) == m['elf_sha256'], 'Firmware receipt/ELF mismatch')
    require(sha(b.GATE / 'source/power_capture.sv') == CONTROL_SHA, 'Gate capture control changed')
    roi = roi_candidate(work, args.case) if args.first_cycle is None and args.last_cycle is None else dict(
        first_cycle=args.first_cycle, last_cycle=args.last_cycle, source=ref(work / 'commit.csv'),
        selection='Explicit reviewer-selected exact-ELF ROI', gate_phase_verified=False, measured_power=False)
    first, last = roi['first_cycle'], roi['last_cycle']
    b.validate_limits('capture', first, last, args.max_cycles, args.wall_seconds, args.max_vcd_bytes, args.slot_seconds)
    require(last - first >= 1024, 'Native power conversion requires at least 1024 captured cycles')
    verify(read(b.GATE / 'source-pins.json'))
    out.mkdir()
    (out / 'inputs').mkdir()
    (out / 'run').mkdir()
    pins = {}
    def pin(path):
        pins[str(path)] = sha(path)
    for src, name in [(Path(__file__).resolve(), 'gate_native.py'), (HERE / 'test_gate_native.py', 'test_gate_native.py'),
                      (base_path, 'gate_run_base.py'), (b.GATE / 'inputs/rtl-plan.json', 'rtl-plan.json')]:
        dest = out / 'inputs' / name
        shutil.copyfile(src, dest)
        pin(src); pin(dest)
    private = out / 'inputs/program.elf'
    shutil.copyfile(selected['elf'], private)
    require(sha(private) == selected['elf_sha256'], 'Exact ELF copy changed')
    pin(private); pin(Path(selected['elf']))
    for path in (release, build_path, Path(case['source_pins']), campaign / 'plan.json',
                 campaign / 'source-pins.json', work / 'commit.csv', work / 'run.vcs.log',
                 b.GATE / 'source-pins.json', b.GATE / 'gate-receipt.json',
                 b.GATE / 'inputs/build_gate.py', b.GATE / 'source/power_capture.sv'):
        pin(path)
    if kind == 'akv':
        pin(ROOT / 'verification/performance/power_eval_20261117/prepare_attention.py')
    plan = dict(schema='power-native-gate-run-v1', mode='capture-complete', case_id=args.case,
        image=str(b.GATE), release=str(release), release_sha256=args.release_sha256,
        family=kind, build=str(build_path), first_cycle=first, last_cycle=last, clock_period_ns=1,
        elf_map=dict(prechecked=selected['elf'], gls=str(private), sha256=selected['elf_sha256']),
        command=[str(b.GATE / 'sim/simv'), '-no_save', '-l', str(out / 'run/run.vcs.log'),
            '+PRELOAD=' + str(private), '+TESTCASE=' + args.case, '+NO_FSDB', '+NO_INSTR_TRACE',
            '+GATE_MAX_CYCLES=' + str(args.max_cycles), '+GATE_VCD=' + str(out / 'run/window.vcd'),
            '+GATE_ROI_FIRST=' + str(first), '+GATE_ROI_LAST=' + str(last)],
        max_cycles=args.max_cycles, wall_seconds=args.wall_seconds, slot_seconds=args.slot_seconds,
        max_vcd_bytes=args.max_vcd_bytes, max_log_bytes=256 * 1024**2,
        target_completion_required=True, stop_after_capture=False, max_concurrent_simulators=4,
        automatic_retry=False, rtl_monitors_required_in_gate=False,
        gate_protocol_checked=False, roi_candidate=roi,
        scope='One bounded VCD window plus full target completion; no fabricated RTL counters or protocol proof')
    save(out / 'plan.json', plan, True); pin(out / 'plan.json')
    save(out / 'roi-selection.json', roi, True); pin(out / 'roi-selection.json')
    save(out / 'admission.json', admission, True); pin(out / 'admission.json')
    save(out / 'source-pins.json', pins, True)
    save(out / 'status.json', dict(state='PREPARED_NOT_IMAGE_BOUND', jobs_launched=0))
    return out


def bind(out):
    require(not (out / 'image-binding.json').exists(), 'Immutable binding already exists')
    verify(read(out / 'source-pins.json'))
    plan = read(out / 'plan.json')
    b.admit(b.GATE, Path(plan['release']), plan['release_sha256'])
    build, images = read(b.GATE / 'build.json'), read(b.GATE / 'image-pins.json')
    require(build['state'] == b.GATE_STATE and build['image_pins'] == images, 'Gate image is not compiled/qualified')
    verify(images)
    verify(read(b.GATE / 'source-pins.json'))
    runtime = {str(b.GATE / 'sim/simv')} | {str(p) for p in (b.GATE / 'sim/simv.daidir').rglob('*.so')}
    require(runtime <= images.keys() and len(runtime) > 1, 'Incomplete runtime image inventory')
    binding = dict(schema='power-gls-image-binding-v1', plan_sha256=sha(out / 'plan.json'),
        source_pins_sha256=sha(out / 'source-pins.json'), image_pins=images,
        simv_sha256=images[str(b.GATE / 'sim/simv')], runtime_image={k: images[k] for k in runtime},
        gate_build=ref(b.GATE / 'build.json'), gate_image_inventory=ref(b.GATE / 'image-pins.json'))
    save(out / 'image-pins.json', images, True)
    save(out / 'image-binding.json', binding, True)
    digest = sha(out / 'image-binding.json')
    worker = ['/usr/bin/python3', '-B', str(out / 'inputs/gate_native.py'), 'execute', '--output', str(out),
        '--plan-sha256', binding['plan_sha256'], '--binding-sha256', digest, '--authorize-run']
    unit = out.name.replace('_', '-') + '.service'
    service = ['/usr/bin/systemd-run', '--user', '--unit=' + unit, '--property=Type=exec',
        '--property=KillMode=control-group', '--property=RuntimeMaxSec=' + str(plan['wall_seconds'] + plan['slot_seconds'] + 1800),
        '--property=TimeoutStopSec=30', '--property=StandardOutput=append:' + str(out / 'service.stdout.log'),
        '--property=StandardError=append:' + str(out / 'service.stderr.log'), *worker]
    save(out / 'ready-command.json', dict(service=service, shell=b.shlex.join(service), launched=False), True)
    save(out / 'status.json', dict(state='IMAGE_BOUND_NOT_LAUNCHED', binding_sha256=digest, jobs_launched=0))
    return digest


def bounded_window(raw, output, last_tick):
    """Keep the entire original initial-state window; omit only empty late timestamps."""
    require(not output.exists(), 'Do not overwrite bounded VCD')
    trailing = False
    omitted = 0
    with raw.open('rb') as source, output.open('xb') as dest:
        for line in source:
            value = line.strip()
            if value.startswith(b'#') and int(value[1:]) > last_tick:
                trailing = True
            if trailing:
                require(not value or value.startswith(b'#') and value[1:].isdigit(),
                        'Post-window VCD activity/control found; preserve raw for audit, never silently discard')
                omitted += len(line)
            else:
                dest.write(line)
    return dict(raw=ref(raw), bounded=ref(output), omitted_empty_trailer_bytes=omitted,
                initial_state_retained=True, window_activity_bytes_changed=False)


def final_check(out, plan, binding, run):
    work = out / 'run'
    log, raw = work / 'run.vcs.log', work / 'window.vcd'
    require(run['returncode'] == 0 and log.is_file() and raw.is_file(), 'Native gate did not finish')
    text = log.read_text()
    b.clean_log(text); b.clean_log((work / 'console.log').read_text())
    require(text.count('Core Test *** SUCCESS ***') == 1, 'Full target completion required')
    first_tick, last_tick = b.capture_markers(text, plan['first_cycle'], plan['last_cycle'])
    require(text.index('GATE_CAPTURE_WINDOW_COMPLETE') < text.index('Core Test *** SUCCESS ***'), 'Target ended before capture')
    stat = raw.stat()
    require(0 < stat.st_size <= plan['max_vcd_bytes'] and
            run['started_ns'] <= stat.st_mtime_ns <= run['finished_ns'] + 2*10**9 and
            run['started_ns'] <= stat.st_ctime_ns <= run['finished_ns'] + 2*10**9,
            'VCD not generated within this owned run')
    proof = numeric(text, Path(plan['build']), plan['family'])
    save(work / 'target-numerical.json', dict(proof, log_sha256=sha(log)), True)
    window = work / 'bounded-window.vcd'
    derivation = bounded_window(raw, window, last_tick)
    evidence = b.validate_vcd(window, first_tick, last_tick, plan['last_cycle'] - plan['first_cycle'])
    result = dict(state='CAPTURE_COMPLETE_NOT_TASK_PASS', schema='power-native-gate-result-v1',
        case_id=plan['case_id'], vcd=str(window), log=str(log), first_cycle=plan['first_cycle'], last_cycle=plan['last_cycle'],
        first_tick=first_tick, last_tick=last_tick, clock_period_ns=1, vcd_sha256=sha(window), log_sha256=sha(log),
        simv_sha256=binding['simv_sha256'], elf_sha256=plan['elf_map']['sha256'], elf_map=plan['elf_map'],
        source_pins=str(out / 'source-pins.json'), image_pins=str(out / 'image-pins.json'),
        target_completion=dict(state='GATE_TARGET_COMPLETION_PASS', tohost=0,
                               numericproof=ref(work / 'target-numerical.json')),
        capture_is_task_pass=False, task_pass=False, full_gate_task_pass=False,
        vcd_evidence=evidence, vcd_derivation=derivation,
        raw_file_stat=dict(size=stat.st_size, mtime_ns=stat.st_mtime_ns, ctime_ns=stat.st_ctime_ns),
        gate_protocol_checked=False, gate_engine_monitor_checked=False,
        roi_gate_phase_verified=False, power_acceptance=False, timing_acceptance=False, **run)
    result['checked_artifacts'] = {str(p): sha(p) for p in [out / 'plan.json', out / 'source-pins.json',
        out / 'image-pins.json', out / 'image-binding.json', *(p for p in work.iterdir() if p.is_file())]}
    return result


def execute(out, plan_hash, binding_hash, authorized):
    require(authorized and Path(__file__).resolve() == out / 'inputs/gate_native.py', 'Authorized frozen worker required')
    require(not (out / 'attempt.json').exists(), 'No retry in this output')
    unit = out.name.replace('_', '-') + '.service'
    owner = subprocess.check_output(['/usr/bin/systemctl', '--user', 'show', unit, '-p', 'MainPID', '--value'], text=True).strip()
    require('/' + unit in Path('/proc/self/cgroup').read_text() and owner == str(os.getpid()), 'Direct service owner required')
    plan, binding = b.check_binding(out, plan_hash, binding_hash)
    require(plan['schema'] == 'power-native-gate-run-v1' and '+GATE_STOP_AFTER_CAPTURE' not in plan['command'], 'Not combined native plan')
    save(out / 'attempt.json', dict(pid=os.getpid(), started_ns=time.time_ns(), plan_sha256=plan_hash,
                                    binding_sha256=binding_hash), True)
    def interrupted(signum, frame):
        raise InterruptedError('Native gate interrupted: ' + str(signum))
    signal.signal(signal.SIGTERM, interrupted); signal.signal(signal.SIGINT, interrupted)
    try:
        run = b.run_simulator(out, plan)
        result = final_check(out, plan, binding, run)
        b.check_binding(out, plan_hash, binding_hash)
    except BaseException as error:
        result = dict(state='FAIL', error=repr(error), task_pass=False, artifacts_preserved=True)
    save(out / 'result.json', result, True)
    save(out / 'status.json', dict(state=result['state'], completed=True, child_pid=None))
    print(json.dumps(dict(state=result['state'], task_pass=False)))
    return int(result['state'] == 'FAIL')


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('action', choices=('release', 'prepare', 'bind-image', 'check', 'execute'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--release', type=Path)
    parser.add_argument('--release-sha256')
    parser.add_argument('--case', choices=None)
    parser.add_argument('--first-cycle', type=int)
    parser.add_argument('--last-cycle', type=int)
    parser.add_argument('--max-cycles', type=int, default=5000000)
    parser.add_argument('--wall-seconds', type=int, default=14400)
    parser.add_argument('--slot-seconds', type=int, default=7200)
    parser.add_argument('--max-vcd-bytes', type=int, default=1024**3)
    parser.add_argument('--plan-sha256')
    parser.add_argument('--binding-sha256')
    parser.add_argument('--authorize-run', action='store_true')
    args = parser.parse_args()
    if args.action == 'release':
        require(not args.authorize_run, 'No launch from release')
        print(json.dumps(dict(release_sha256=make_release(args.output.resolve()), jobs_launched=0)))
        return 0
    out = b.scoped_output(args.output)
    if args.action == 'execute':
        return execute(out, args.plan_sha256, args.binding_sha256, args.authorize_run)
    require(not args.authorize_run, 'Authorization only for execute')
    if args.action == 'prepare':
        require(args.release and args.release_sha256 and args.case, 'Explicit release hash and case required')
        prepare(args)
        print(json.dumps(dict(state='PREPARED_NOT_IMAGE_BOUND', output=str(out), plan_sha256=sha(out / 'plan.json'))))
    elif args.action == 'bind-image':
        print(json.dumps(dict(state='IMAGE_BOUND_NOT_LAUNCHED', binding_sha256=bind(out))))
    else:
        b.check_binding(out, args.plan_sha256, args.binding_sha256)
        print('NATIVE_HOST_PIN_CHECK_PASS_NO_LAUNCH')
    return 0


if __name__ == '__main__':
    sys.exit(main())
