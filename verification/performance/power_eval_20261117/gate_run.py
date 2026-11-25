#!/usr/bin/env python3
"""Prepare/bind finite GLS jobs; execute only as an explicitly authorized service.

Smoke proves target completion/numerics; a bounded capture never proves task PASS.
The gate builder and its TB remain sealed. No command here compiles or converts.
"""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import resource
import shlex
import shutil
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
GATE = OUT / 'power_gate_build_20261117_all_on_01'
INITIAL_SHA = '5d5bd21694374abce4a4050f992613c682a529fbe25c36c78883a3502c5bcbba'
GATE_STATE = 'DC_MATCHED_GATE_BUILT_NOT_SIMULATED'
FUTURE_BASELINE_STATE = 'RECONSTRUCTED_BASELINE_GATE_BUILT_NOT_SIMULATED'
Q8 = 'legacy_q8_qbs_sdk_v2_successor'
MAX_SLOTS = 4
MAX_WINDOW = 4096
KNOWN_DISPATCHERS = {
    'precheck.py': 'a9784e436fdd68ef5e6e157de874b409aa7af5a0bbc7ad63f893a02ae10fdab3',
    'precheck_v2.py': '699bc377a22a0a6f98d976b48b511c053139df97e7377c55fbc18b3500e7646a',
}
UNIT_FS = {'s': 10**15, 'ms': 10**12, 'us': 10**9, 'ns': 10**6, 'ps': 1000, 'fs': 1}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, data, exclusive=False):
    path = Path(path)
    if exclusive:
        with path.open('x') as stream:
            json.dump(data, stream, indent=2, sort_keys=True)
            stream.write('\n')
    else:
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')
        tmp.replace(path)


def verify(pins):
    for path, digest in pins.items():
        require(sha(path) == digest, 'Identity drift: ' + str(path))


def scoped_output(path):
    path = Path(path).absolute()
    require(path == path.resolve() and path.parent == OUT and
            re.fullmatch(r'power_gls_20261117_[a-zA-Z0-9_]+', path.name), 'Fresh direct power_gls output required')
    return path


def admit(image, release, digest):
    require(image == GATE, 'Only exact all-on image is supported; baseline requires a separate future adapter')
    require(re.fullmatch(r'[0-9a-f]{64}', digest or '') and sha(release) == digest, 'Explicit release identity required')
    pins = read(image / 'source-pins.json')
    validator = image / 'inputs/build_gate.py'
    require(pins.get(str(validator)) == sha(validator), 'Unpinned frozen release validator')
    spec = importlib.util.spec_from_file_location('sealed_power_gate_admission', validator)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.check_release_data(read(release))
    require(result['state'] == 'COMPOSITE_RTL_EVIDENCE_ADMITTED_NOT_COMPILE_AUTHORIZATION', 'Release not admitted')
    verify({release: digest})
    return result


def validate_limits(mode, first, last, cycles, wall, byte_limit, slot_seconds):
    require(mode in ('smoke', 'capture') and 1 <= cycles <= 5000000, 'Finite cycle budget required')
    require(1 <= wall <= 14400 and 1 <= slot_seconds <= 14400, 'Finite wall/slot budget required')
    require(1024 <= byte_limit <= 4 * 1024**3, 'Invalid VCD/file byte budget')
    if mode == 'smoke':
        require(first is None and last is None, 'Smoke must not request VCD')
    else:
        require(type(first) is int and type(last) is int and 0 < first < last < cycles and
                2 <= last - first <= MAX_WINDOW, 'Capture requires a bounded 2..4096-cycle window')


def prepare(args):
    out = scoped_output(args.output)
    require(not out.exists(), 'No reuse/overwrite of run outputs')
    validate_limits(args.mode, args.first_cycle, args.last_cycle, args.max_cycles,
                    args.wall_seconds, args.max_vcd_bytes, args.slot_seconds)
    image, release = args.image.resolve(), args.release.resolve()
    admission = admit(image, release, args.release_sha256)
    entries = [c for c in admission['cases'] if c['id'] == args.case]
    require(len(entries) == 1, 'Case is not in the explicit composite release')
    entry = entries[0]
    require(args.mode != 'smoke' or args.case == Q8,
            'Only Q8 successor has an admitted full target checker without RTL-only PERF requirements')
    original = Path(entry['original_result']['path'])
    campaign = original.parent.parent.parent
    source_plan = read(campaign / 'plan.json')
    case = next(c for c in source_plan['cases'] if c['id'] == args.case)
    require(case['elf'] == entry['elf'] and case['elf_sha256'] == entry['elf_sha256'], 'Prechecked ELF map mismatch')
    require(image == GATE and read(image / 'gate-receipt.json')['revision'].startswith('870cadb9'), 'Wrong gate source')
    verify(read(image / 'source-pins.json'))
    out.mkdir()
    (out / 'inputs').mkdir()
    (out / 'run').mkdir()
    pins = {}

    def pin(path):
        pins[str(path)] = sha(path)

    for name in ('gate_run.py', 'test_gate_run.py'):
        src, dest = HERE / name, out / 'inputs' / name
        shutil.copyfile(src, dest)
        pin(src)
        pin(dest)
    private_elf = out / 'inputs/program.elf'
    shutil.copyfile(entry['elf'], private_elf)
    require(sha(private_elf) == entry['elf_sha256'], 'ELF copy differs byte-for-byte')
    pin(private_elf)
    pin(Path(entry['elf']))
    for path in (release, image / 'source-pins.json', image / 'gate-receipt.json',
                 image / 'plan.json', image / 'inputs/build_gate.py', campaign / 'plan.json',
                 campaign / 'source-pins.json', Path(case['source_pins'])):
        pin(path)
    for ref in read(release)['cases']:
        for key in ('original_result', 'numerical', 'protocol', 'protocol_audit'):
            if key in ref:
                pin(Path(ref[key]['path']))
    # The smoke checker is exactly the prechecked command, never caller-supplied code.
    checker = case['checker'] if args.mode == 'smoke' else None
    if checker:
        require('--mode' in checker and checker[checker.index('--mode') + 1] == 'qbs' and
                any(Path(s).name == 'original_checker.py' for s in checker), 'Unknown smoke checker')
        for item in checker:
            if Path(item).is_file():
                pin(Path(item))
    for name in ('gate-plan.json', 'rtl-plan.json'):
        source = image / ('plan.json' if name == 'gate-plan.json' else 'inputs/rtl-plan.json')
        dest = out / 'inputs' / name
        shutil.copyfile(source, dest)
        pin(dest)
        pin(source)
    argv = [str(image / 'sim/simv'), '-no_save', '-l', str(out / 'run/run.vcs.log'),
            '+PRELOAD=' + str(private_elf), '+TESTCASE=' + args.case, '+NO_FSDB', '+NO_INSTR_TRACE',
            '+GATE_MAX_CYCLES=' + str(args.max_cycles)]
    if args.mode == 'capture':
        argv += ['+GATE_VCD=' + str(out / 'run/window.vcd'),
                 '+GATE_ROI_FIRST=' + str(args.first_cycle), '+GATE_ROI_LAST=' + str(args.last_cycle),
                 '+GATE_STOP_AFTER_CAPTURE']
    plan = dict(schema='power-gls-run-v1', mode=args.mode, case_id=args.case, image=str(image),
        expected_build_state=GATE_STATE, configuration='dc_870cadb9_all_on',
        release=str(release), release_sha256=args.release_sha256, checker=checker,
        command=argv, cwd=str(out / 'run'), original_result=str(original),
        elf_map=dict(prechecked=entry['elf'], gls=str(private_elf), sha256=entry['elf_sha256']),
        first_cycle=args.first_cycle, last_cycle=args.last_cycle, clock_period_ns=1,
        max_cycles=args.max_cycles, wall_seconds=args.wall_seconds, slot_seconds=args.slot_seconds,
        max_vcd_bytes=args.max_vcd_bytes, max_log_bytes=256 * 1024**2,
        max_concurrent_simulators=MAX_SLOTS, automatic_retry=False,
        baseline_supported=False, future_baseline_build_state=FUTURE_BASELINE_STATE,
        capture_is_full_task_pass=False, image_binding_required=True,
        progress_semantics='Wall/CPU/file progress plus emitted ROI/target cycles only; '
                           'sealed TB has no periodic smoke cycle heartbeat, so unavailable cycles are null')
    save(out / 'plan.json', plan, True)
    pin(out / 'plan.json')
    save(out / 'admission.json', admission, True)
    pin(out / 'admission.json')
    save(out / 'source-pins.json', pins, True)
    save(out / 'prepare-receipt.json', dict(state='PREPARED_WAITING_FOR_GATE_IMAGE_BINDING',
        plan_sha256=sha(out / 'plan.json'), image_bound=False, jobs_launched=0,
        next_action='bind-image after immutable gate build/image receipts exist'), True)
    save(out / 'status.json', dict(state='PREPARED_WAITING_FOR_GATE_IMAGE_BINDING', jobs_launched=0))
    return out


def bind_image(out):
    require(not (out / 'image-binding.json').exists(), 'Binding is immutable; use a fresh run output')
    verify(read(out / 'source-pins.json'))
    plan = read(out / 'plan.json')
    image = Path(plan['image'])
    admit(image, Path(plan['release']), plan['release_sha256'])
    build = read(image / 'build.json')
    require(build['state'] == GATE_STATE, 'Gate compile is not successfully complete; no identity substitutes')
    image_pins = read(image / 'image-pins.json')
    require(build['image_pins'] == image_pins and str(image / 'sim/simv') in image_pins,
            'Build/image inventory disagreement')
    verify(image_pins)
    verify(read(image / 'source-pins.json'))
    runtime = {str(image / 'sim/simv')} | {str(p) for p in (image / 'sim/simv.daidir').rglob('*.so')}
    require(runtime <= set(image_pins) and len(runtime) > 1, 'Incomplete executable loader inventory')
    binding = dict(schema='power-gls-image-binding-v1', state='IMAGE_BOUND_NOT_LAUNCHED',
        plan_sha256=sha(out / 'plan.json'), source_pins_sha256=sha(out / 'source-pins.json'),
        gate_build=dict(path=str(image / 'build.json'), sha256=sha(image / 'build.json')),
        gate_image_inventory=dict(path=str(image / 'image-pins.json'), sha256=sha(image / 'image-pins.json')),
        simv_sha256=image_pins[str(image / 'sim/simv')], runtime_image={k: image_pins[k] for k in sorted(runtime)},
        image_pins=image_pins)
    save(out / 'image-pins.json', image_pins, True)
    save(out / 'image-binding.json', binding, True)
    binding_hash = sha(out / 'image-binding.json')
    unit = out.name.replace('_', '-') + '.service'
    command = ['/usr/bin/python3', '-B', str(out / 'inputs/gate_run.py'), 'execute', '--output', str(out),
               '--plan-sha256', binding['plan_sha256'], '--binding-sha256', binding_hash, '--authorize-run']
    launcher = ['/usr/bin/systemd-run', '--user', '--unit=' + unit, '--property=Type=exec',
        '--property=KillMode=control-group', '--property=RuntimeMaxSec=' + str(plan['wall_seconds'] + plan['slot_seconds'] + 1800),
        '--property=TimeoutStopSec=30', '--property=StandardOutput=append:' + str(out / 'service.stdout.log'),
        '--property=StandardError=append:' + str(out / 'service.stderr.log'), *command]
    save(out / 'ready-command.json', dict(service=launcher, shell=shlex.join(launcher), worker=command,
                                        launched=False, unit=unit), True)
    save(out / 'status.json', dict(state='IMAGE_BOUND_NOT_LAUNCHED', binding_sha256=binding_hash, jobs_launched=0))
    return binding_hash


def check_binding(out, plan_hash, binding_hash):
    require(sha(out / 'plan.json') == plan_hash and sha(out / 'image-binding.json') == binding_hash,
            'Reviewed plan/binding identity changed')
    verify(read(out / 'source-pins.json'))
    plan, binding = read(out / 'plan.json'), read(out / 'image-binding.json')
    require(binding['plan_sha256'] == plan_hash and
            binding['source_pins_sha256'] == sha(out / 'source-pins.json'), 'Binding/plan disagreement')
    image = Path(plan['image'])
    for key in ('gate_build', 'gate_image_inventory'):
        verify({binding[key]['path']: binding[key]['sha256']})
    require(read(image / 'build.json')['state'] == GATE_STATE and
            read(image / 'image-pins.json') == read(out / 'image-pins.json') == binding['image_pins'], 'Gate image drift')
    verify(binding['image_pins'])
    verify(read(image / 'source-pins.json'))
    runtime = {str(image / 'sim/simv')} | {str(p) for p in (image / 'sim/simv.daidir').rglob('*.so')}
    require(runtime == set(binding['runtime_image']), 'Loader set drift')
    result = admit(image, Path(plan['release']), plan['release_sha256'])
    selected = [c for c in result['cases'] if c['id'] == plan['case_id']]
    require(len(selected) == 1 and selected[0]['elf'] == plan['elf_map']['prechecked'] and
            selected[0]['elf_sha256'] == plan['elf_map']['sha256'] == sha(plan['elf_map']['gls']), 'Exact ELF admission drift')
    return plan, binding


def clean_log(text):
    require(not re.search(r'(?mi)^\s*(?:Error[-:]|Fatal:)|Assertion failed|\$fatal|\bFAILED\b|'
                          r'\bQ8_TRAP\b|\bGate watchdog\b|Gate exit before ROI|Unhandled trap|illegal instruction', text),
            'Gate UART/tohost/assertion/watchdog failure')
    for line in text.splitlines():
        if re.match(r'\s*UVM_(?:ERROR|FATAL)\b', line):
            require(re.fullmatch(r'\s*UVM_(?:ERROR|FATAL)\s*:\s*0\s*', line), 'UVM error')


def capture_markers(text, first, last):
    clean_log(text)
    begins = re.findall(r'^GATE_ROI_BEGIN cycle=(\d+) time=(\d+)\s*$', text, re.M)
    ends = re.findall(r'^GATE_CAPTURE_WINDOW_COMPLETE cycle=(\d+) time=(\d+) task_pass=0\s*$', text, re.M)
    require(len(begins) == len(ends) == 1, 'Exactly one complete gate capture window required')
    begin, end = tuple(map(int, begins[0])), tuple(map(int, ends[0]))
    require(begin[0] == first and end[0] == last and begin[1] < end[1] and
            text.index('GATE_ROI_BEGIN') < text.index('GATE_CAPTURE_WINDOW_COMPLETE'), 'Capture scope/order mismatch')
    return begin[1], end[1]


def validate_vcd(path, first_tick, last_tick, cycles):
    """Stream the native VCD: header, complete initial state, bounded clock edges."""
    codes, initial = set(), set()
    scopes, timescale = [], []
    reading_timescale = False
    clock = None
    unit_fs = None
    header_done = in_initial = initial_done = False
    current = None
    timestamps = 0
    clock_value = clock_time = None
    clock_edges = 0
    dump_off = False
    with Path(path).open('r', errors='strict') as stream:
        for raw in stream:
            line = raw.strip()
            if not header_done:
                if line.startswith('$timescale'):
                    reading_timescale = True
                if reading_timescale:
                    timescale.append(line)
                    require(sum(map(len, timescale)) < 256, 'Oversized VCD timescale directive')
                    if '$end' in line:
                        reading_timescale = False
                if line.startswith('$scope '):
                    scopes.append(line.split()[2])
                elif line.startswith('$upscope'):
                    require(scopes, 'Unbalanced VCD scope')
                    scopes.pop()
                elif line.startswith('$var '):
                    fields = line.split()
                    require(len(fields) >= 6, 'Malformed VCD declaration')
                    code, name = fields[3:5]
                    codes.add(code)
                    if '.'.join([*scopes, name]) == 'ara_tb.dut.i_ara_soc.clk_i':
                        clock = code
                elif line.startswith('$enddefinitions'):
                    match = re.search(r'\$timescale\s+(1|10|100)\s*(s|ms|us|ns|ps|fs)\s+\$end', ' '.join(timescale))
                    require(match is not None and clock and codes, 'Missing native gate scope/clock/timescale')
                    unit_fs = int(match[1]) * UNIT_FS[match[2]]
                    require((last_tick - first_tick) * unit_fs == cycles * 10**6 and
                            500000 % unit_fs == 0, 'Capture duration/timescale mismatch')
                    header_done = True
                continue
            if not line:
                continue
            if line.startswith('#'):
                tick = int(line[1:])
                require(first_tick <= tick <= last_tick and (current is None or tick >= current), 'Unbounded/nonmonotonic VCD time')
                require(current is not None or tick == first_tick, 'VCD lacks selected-start initial state')
                if current is not None and tick > current:
                    require(initial_done, 'Missing complete initial dumpvars')
                current = tick
                timestamps += 1
                continue
            if line == '$dumpvars':
                require(current == first_tick and not in_initial and not initial_done, 'Unexpected VCD initial dump')
                in_initial = True
                continue
            if line == '$dumpoff':
                require(current == last_tick and initial_done and not dump_off, 'Premature/duplicate dumpoff')
                dump_off = True
                continue
            if line == '$end':
                if in_initial:
                    require(initial == codes, 'VCD initial state omits declared identifiers')
                    in_initial, initial_done = False, True
                continue
            require(not line.startswith('$'), 'Unexpected VCD control record')
            require(current is not None, 'VCD change before selected-start timestamp')
            if line[0] in '01xXzZ':
                value, code = line[0].lower(), line[1:]
            elif line[0] in 'bBrR':
                fields = line.split()
                require(len(fields) == 2, 'Malformed vector VCD change')
                value, code = fields
            else:
                raise ValueError('Unsupported VCD change')
            require(code in codes, 'Undeclared VCD identifier')
            if in_initial:
                initial.add(code)
            if code == clock and not dump_off:
                require(value in ('0', '1'), 'Unknown clock inside selected window')
                if clock_value is not None and value != clock_value:
                    require((current - clock_time) * unit_fs == 500000, 'Nonperiodic gate clock')
                    clock_edges += 1
                if clock_value is None or value != clock_value:
                    clock_time = current
                clock_value = value
    require(header_done and initial_done and not in_initial and current == last_tick and timestamps >= 2 and
            dump_off and clock_edges in (2 * cycles - 1, 2 * cycles), 'Truncated/nonrepresentative gate window')
    return dict(timescale_fs=unit_fs, first_tick=first_tick, last_tick=last_tick,
                duration_ticks=last_tick - first_tick, duration_fs=(last_tick - first_tick) * unit_fs,
                declared_identifiers=len(codes), initial_identifiers=len(initial), clock_edges=clock_edges,
                clock_path='ara_tb.dut.i_ara_soc.clk_i', complete_initial_state=True)


def process_snapshot(proc_root=Path('/proc')):
    rows = {}
    for path in proc_root.iterdir():
        if not path.name.isdigit():
            continue
        try:
            if path.stat().st_uid != os.getuid():
                continue
            argv = [s.decode() for s in (path / 'cmdline').read_bytes().split(b'\0') if s]
            status = (path / 'status').read_text()
            ppid = int(re.search(r'^PPid:\s+(\d+)', status, re.M)[1])
            if argv:
                rows[int(path.name)] = (ppid, argv)
        except (OSError, UnicodeError, TypeError):
            continue
    return rows


def dispatcher_reservation(pid, worker, output, rows, simulations):
    """Bound future VCS dispatch from a known one-shot worker, not its thread count.

    A missing run directory is still pending. A directory without published VCS
    status, or a VCS PID absent from the process snapshot, reserves a launch in
    flight. This covers mkdir/Popen/status publication races without trusting a
    stale numerical/protocol state to describe some other process.
    """
    snapshots = {}

    def snapshot(path):
        data = path.read_bytes()
        snapshots[path] = data
        return json.loads(data)

    require(worker == output / 'inputs' / worker.name and worker.name in KNOWN_DISPATCHERS,
            'Unknown dispatcher path')
    pins = snapshot(output / 'source-pins.json')
    require(pins.get(str(worker)) == KNOWN_DISPATCHERS[worker.name] == sha(worker), 'Dispatcher identity drift')
    if worker.name == 'precheck_v2.py':
        helper = output / 'inputs/precheck.py'
        require(pins.get(str(helper)) == KNOWN_DISPATCHERS['precheck.py'] == sha(helper), 'Dispatcher helper drift')
    plan_path = output / 'plan.json'
    plan = snapshot(plan_path)
    require(pins.get(str(plan_path)) == hashlib.sha256(snapshots[plan_path]).hexdigest(), 'Unpinned dispatcher plan')
    require(snapshot(output / 'attempt.json')['pid'] == pid, 'Dispatcher PID identity mismatch')
    parallel = plan['parallel']
    require(type(parallel) is int and 1 <= parallel <= MAX_SLOTS, 'Invalid dispatcher parallelism')
    cases = {c['id']: c for c in plan['cases']}
    require(cases and len(cases) == len(plan['cases']) and
            all(re.fullmatch(r'[A-Za-z0-9_-]+', c) for c in cases), 'Invalid dispatcher cases')
    aggregate = snapshot(output / 'status.json')
    require(aggregate['state'] in ('PREPARED', 'RUNNING', 'STOPPING_AFTER_FAILURE', 'PASS', 'INCOMPLETE') and
            aggregate['total'] == len(cases), 'Unknown dispatcher state')
    reported = aggregate.get('cases', [])
    require(len(reported) == aggregate['completed'] and len({c['id'] for c in reported}) == len(reported) and
            all(c['id'] in cases and c['state'] in ('PASS', 'FAIL', 'TIMEOUT', 'NOT_DISPATCHED_AFTER_FAILURE')
                for c in reported), 'Inconsistent dispatcher completion inventory')
    if aggregate['state'] == 'STOPPING_AFTER_FAILURE':
        require(any(c['state'] in ('FAIL', 'TIMEOUT') for c in reported), 'Stop condition not yet published')
    live = {}
    for child, parent in simulations.items():
        if parent != pid:
            continue
        argv = rows[child][1]
        names = [a[len('+TESTCASE='):] for a in argv if a.startswith('+TESTCASE=')]
        require(len(names) == 1 and names[0] in cases and names[0] not in live, 'Unknown/duplicate live VCS case')
        case_id = names[0]
        require(argv.count('+PRELOAD=' + cases[case_id]['elf']) == 1 and
                argv[0] == str(Path(plan['image']) / 'sim/simv'), 'Live VCS image/ELF identity mismatch')
        live[case_id] = child
    pending = launching = 0
    for case_id in cases:
        directory = output / 'runs' / case_id
        result_path, status_path = directory / 'result.json', directory / 'status.json'
        if result_path.exists():
            result = snapshot(result_path)
            require(result['id'] == case_id and result['state'] in ('PASS', 'FAIL', 'TIMEOUT') and
                    case_id not in live, 'Terminal/live case disagreement')
        elif status_path.exists():
            status = snapshot(status_path)
            stage = status['state']
            require(stage in ('VCS', 'NUMERICAL', 'PROTOCOL'), 'Unknown per-case stage')
            require(type(status['pid']) is int and isinstance(status['command'], list), 'Missing stage process identity')
            if case_id in live:
                require(stage == 'VCS' and status['pid'] == live[case_id] and
                        status['command'] == rows[live[case_id]][1], 'VCS publication changed during snapshot')
            elif stage == 'VCS':
                # The process snapshot may precede Popen/status publication or
                # follow VCS exit. Retain one slot until a later stage proves it.
                launching += 1
            else:
                # NUMERICAL/PROTOCOL cannot reenter VCS in these exact workers.
                # A different live command under the same PID is a race/reuse.
                if status['pid'] in rows:
                    require(rows[status['pid']][0] == pid and rows[status['pid']][1] == status['command'],
                            'Checker PID reuse/publication race')
        elif case_id in live or directory.is_dir():
            if case_id not in live:
                launching += 1
        else:
            pending += 1
    active = len(live)
    require(active + launching <= parallel, 'Dispatcher capacity disagreement')
    # Re-read mutable records: mixed snapshots must never release capacity.
    require(all(path.read_bytes() == data for path, data in snapshots.items()), 'Dispatcher changed during snapshot')
    return active + launching + min(parallel - active - launching, pending)


def reserved_slots(rows, own_child=None):
    dispatchers, simulations, waiting_dispatch = {}, {}, False
    for pid, (ppid, argv) in rows.items():
        if pid == own_child:
            continue
        if Path(argv[0]).name == 'simv':
            simulations[pid] = ppid
        if not any('power_eval_20261117' in arg or '/inputs/precheck' in arg for arg in argv):
            continue
        if any(Path(arg).name == 'after_compile.py' for arg in argv):
            waiting_dispatch = True
        workers = [Path(arg) for arg in argv if Path(arg).name in KNOWN_DISPATCHERS]
        if 'execute' in argv and any(Path(arg).name.startswith('precheck') and
                                     Path(arg).suffix == '.py' for arg in argv) and not workers:
            return MAX_SLOTS
        if 'execute' in argv and workers:
            try:
                require(len(workers) == 1 and argv.count('--output') == 1, 'Ambiguous dispatcher command')
                dispatchers[pid] = (workers[0], Path(argv[argv.index('--output') + 1]))
            except (OSError, KeyError, ValueError, IndexError, TypeError):
                return MAX_SLOTS
    if waiting_dispatch:
        return MAX_SLOTS
    try:
        reservations = sum(dispatcher_reservation(pid, worker, output, rows, simulations)
                           for pid, (worker, output) in dispatchers.items())
        return reservations + sum(ppid not in dispatchers for ppid in simulations.values())
    except (OSError, KeyError, ValueError, IndexError, TypeError, AttributeError):
        return MAX_SLOTS


@contextmanager
def slot_lock():
    with (OUT / '.power_gls_20261117_slots.lock').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield
        fcntl.flock(stream, fcntl.LOCK_UN)


def stop_process(proc):
    if proc.poll() is None:
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()


def last_progress(path):
    if not path.exists():
        return dict(last_observed_cycle=None, target_compute_cycles=None)
    with path.open('rb') as stream:
        stream.seek(max(0, path.stat().st_size - 65536))
        text = stream.read().decode(errors='replace')
    cycles = re.findall(r'GATE_(?:ROI_BEGIN|CAPTURE_WINDOW_COMPLETE) cycle=(\d+)', text)
    compute = re.findall(r'\bcompute_cycles=(\d+)', text)
    return dict(last_observed_cycle=int(cycles[-1]) if cycles else None,
                target_compute_cycles=int(compute[-1]) if compute else None)


def cpu_seconds(pid):
    try:
        fields = Path('/proc', str(pid), 'stat').read_text().rsplit(')', 1)[1].split()
        return (int(fields[11]) + int(fields[12])) / os.sysconf('SC_CLK_TCK')
    except (OSError, IndexError, ValueError):
        return None


def run_simulator(out, plan, clock=time.monotonic):
    work = out / 'run'
    console, vcd = work / 'console.log', work / 'window.vcd'
    require(not console.exists() and not vcd.exists(), 'Run artifacts already exist')
    deadline, proc = clock() + plan['slot_seconds'], None
    waiting = clock()
    while proc is None:
        with slot_lock():
            count = reserved_slots(process_snapshot())
            if count < MAX_SLOTS:
                start_ns = time.time_ns()
                handle = console.open('x')
                max_size = max(plan['max_vcd_bytes'], plan['max_log_bytes'])
                def limits():
                    resource.setrlimit(resource.RLIMIT_FSIZE, (max_size, max_size))
                try:
                    env = dict(read(out / 'inputs/rtl-plan.json')['environment'], PYTHONDONTWRITEBYTECODE='1')
                    proc = subprocess.Popen(plan['command'], cwd=work, env=env, stdout=handle,
                        stderr=subprocess.STDOUT, start_new_session=True, preexec_fn=limits)
                finally:
                    handle.close()
        if proc is None:
            require(clock() < deadline, 'Finite slot-wait budget exhausted')
            save(out / 'status.json', dict(state='WAITING_FOR_SHARED_SIMULATOR_SLOT', reserved_slots=count,
                                          elapsed_seconds=clock() - waiting, pid=os.getpid()))
            time.sleep(5)
    started, last_status = clock(), 0
    try:
        while proc.poll() is None:
            elapsed = clock() - started
            require(elapsed < plan['wall_seconds'], 'Finite GLS wall watchdog expired')
            require(not vcd.exists() or vcd.stat().st_size <= plan['max_vcd_bytes'], 'VCD byte budget exceeded')
            for path in (console, work / 'run.vcs.log'):
                require(not path.exists() or path.stat().st_size <= plan['max_log_bytes'], 'Log byte budget exceeded')
            require(reserved_slots(process_snapshot(), own_child=proc.pid) < MAX_SLOTS,
                    'Concurrent RTL/GLS slot drift; stopping owned GLS')
            if elapsed - last_status >= 15 or last_status == 0:
                status = dict(state='GLS_RUNNING', child_pid=proc.pid, owner_pid=os.getpid(),
                    elapsed_seconds=elapsed, child_cpu_seconds=cpu_seconds(proc.pid), cycle_watchdog=plan['max_cycles'],
                    vcd_bytes=vcd.stat().st_size if vcd.exists() else 0,
                    console_bytes=console.stat().st_size, **last_progress(console))
                save(out / 'status.json', status)
                with (out / 'progress.jsonl').open('a') as stream:
                    stream.write(json.dumps(status) + '\n')
                last_status = elapsed
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
        return dict(returncode=proc.returncode, started_ns=start_ns, finished_ns=time.time_ns(),
                    elapsed_seconds=clock() - started, slot_wait_seconds=started - waiting,
                    **last_progress(console))
    finally:
        stop_process(proc)


def final_check(out, plan, binding, run):
    work, log = out / 'run', out / 'run/run.vcs.log'
    require(run['returncode'] == 0 and log.is_file(), 'Gate simulator failed/missing log')
    text = log.read_text(errors='strict')
    clean_log(text)
    clean_log((work / 'console.log').read_text(errors='strict'))
    common = dict(schema='power-gls-result-v1', case_id=plan['case_id'], mode=plan['mode'],
        log=str(log), elf_sha256=plan['elf_map']['sha256'], elf_map=plan['elf_map'],
        simv_sha256=binding['simv_sha256'], source_pins=str(out / 'source-pins.json'),
        image_pins=str(out / 'image-pins.json'), image_binding=str(out / 'image-binding.json'),
        release=plan['release'], release_sha256=plan['release_sha256'], clock_period_ns=1,
        rtl_admission_preserved=True, timing_acceptance=False, power_acceptance=False, **run)
    if plan['mode'] == 'smoke':
        require(text.count('Core Test *** SUCCESS ***') == 1 and
                'GATE_ROI_BEGIN' not in text and 'GATE_CAPTURE_WINDOW_COMPLETE' not in text and
                not (work / 'window.vcd').exists(), 'Smoke completion/VCD scope failure')
        output = work / 'numerical.json'
        require(not output.exists(), 'Numerical receipt exists already')
        substitutions = dict(log=str(log), result=str(output), run=str(work))
        argv = [s.format(**substitutions) for s in plan['checker']]
        with (work / 'checker.log').open('x') as stream:
            subprocess.run(argv, cwd=work, stdout=stream, stderr=subprocess.STDOUT,
                           timeout=600, check=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        numeric = read(output)
        require(numeric['state'] == 'PASS' and numeric['log_sha256'] == sha(log), 'Full target numerical gate failed')
        common.update(state='GATE_SMOKE_PASS', full_gate_task_pass=True,
                      numericproof=dict(path=str(output), sha256=sha(output)), numerical=numeric)
    else:
        first, last = capture_markers(text, plan['first_cycle'], plan['last_cycle'])
        vcd = work / 'window.vcd'
        stat = vcd.stat()
        require(0 < stat.st_size <= plan['max_vcd_bytes'] and
                run['started_ns'] <= stat.st_mtime_ns <= run['finished_ns'] + 2 * 10**9 and
                run['started_ns'] <= stat.st_ctime_ns <= run['finished_ns'] + 2 * 10**9,
                'VCD not generated inside this owned run')
        evidence = validate_vcd(vcd, first, last, plan['last_cycle'] - plan['first_cycle'])
        common.update(state='CAPTURE_COMPLETE_NOT_TASK_PASS', full_gate_task_pass=False,
            task_pass=False, vcd=str(vcd), vcd_sha256=sha(vcd), first_cycle=plan['first_cycle'],
            last_cycle=plan['last_cycle'], first_tick=first, last_tick=last, vcd_evidence=evidence,
            file_stat=dict(size=stat.st_size, mtime_ns=stat.st_mtime_ns, ctime_ns=stat.st_ctime_ns),
            gate_numeric_checked=False, acceptance_scope='Bounded native mapped VCD with initial state, not task acceptance')
    common['checked_artifacts'] = {str(p): sha(p) for p in
        [out / 'plan.json', out / 'source-pins.json', out / 'image-pins.json', out / 'image-binding.json',
         *(p for p in work.iterdir() if p.is_file())]}
    return common


def execute(out, plan_hash, binding_hash, authorized):
    require(authorized, 'Explicit --authorize-run required')
    require(Path(__file__).resolve() == out / 'inputs/gate_run.py', 'Use frozen worker')
    require(not (out / 'attempt.json').exists(), 'No automatic retry/overwrite')
    unit = out.name.replace('_', '-') + '.service'
    group = Path('/proc/self/cgroup').read_text()
    owner = subprocess.check_output(['/usr/bin/systemctl', '--user', 'show', unit, '-p', 'MainPID', '--value'], text=True).strip()
    require('/' + unit in group and owner == str(os.getpid()), 'Service must directly own runner')
    plan, binding = check_binding(out, plan_hash, binding_hash)
    save(out / 'attempt.json', dict(pid=os.getpid(), cgroup=group, plan_sha256=plan_hash,
        binding_sha256=binding_hash, started_ns=time.time_ns()), True)
    report = dict(state='FAIL', mode=plan['mode'], case_id=plan['case_id'], full_gate_task_pass=False)
    def interrupted(signum, frame):
        raise InterruptedError('Owned GLS interrupted by signal ' + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        run = run_simulator(out, plan)
        report = final_check(out, plan, binding, run)
        check_binding(out, plan_hash, binding_hash)
    except BaseException as error:
        report = dict(state='FAIL', mode=plan['mode'], case_id=plan['case_id'],
                      full_gate_task_pass=False, error=repr(error), artifacts_preserved=True)
    save(out / 'result.json', report, True)
    save(out / 'status.json', dict(state=report['state'], completed=True, child_pid=None))
    print(json.dumps({k: report[k] for k in ('state', 'case_id', 'full_gate_task_pass')}))
    return int(report['state'] == 'FAIL')


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('action', choices=('prepare', 'bind-image', 'check', 'execute', 'status'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--image', type=Path, default=GATE)
    parser.add_argument('--release', type=Path, default=GATE / 'initial-release.json')
    parser.add_argument('--release-sha256', default=INITIAL_SHA)
    parser.add_argument('--mode', choices=('smoke', 'capture'), default='smoke')
    parser.add_argument('--case', default=Q8)
    parser.add_argument('--first-cycle', type=int)
    parser.add_argument('--last-cycle', type=int)
    parser.add_argument('--max-cycles', type=int, default=1000000)
    parser.add_argument('--wall-seconds', type=int, default=7200)
    parser.add_argument('--slot-seconds', type=int, default=7200)
    parser.add_argument('--max-vcd-bytes', type=int, default=1024**3)
    parser.add_argument('--plan-sha256')
    parser.add_argument('--binding-sha256')
    parser.add_argument('--authorize-run', action='store_true')
    args = parser.parse_args()
    out = scoped_output(args.output)
    if args.action == 'execute':
        return execute(out, args.plan_sha256, args.binding_sha256, args.authorize_run)
    require(not args.authorize_run, 'Authorization only applies to execute')
    if args.action == 'prepare':
        prepare(args)
        print(json.dumps(read(out / 'prepare-receipt.json')))
    elif args.action == 'bind-image':
        print(json.dumps(dict(state='IMAGE_BOUND_NOT_LAUNCHED', binding_sha256=bind_image(out))))
    elif args.action == 'check':
        verify(read(out / 'source-pins.json'))
        if (out / 'image-binding.json').exists():
            check_binding(out, args.plan_sha256, args.binding_sha256)
        print('HOST_PIN_CHECK_PASS_NO_GLS_LAUNCHED')
    else:
        print(json.dumps(read(out / 'status.json')))
    return 0


if __name__ == '__main__':
    sys.exit(main())
