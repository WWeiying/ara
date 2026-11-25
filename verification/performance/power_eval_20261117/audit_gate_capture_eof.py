#!/usr/bin/env python3
"""Independent native-VCD EOF audit. Never rewrite the original failed receipt."""
import argparse
import importlib.util
import json
from pathlib import Path
import re


def require(ok, message):
    if not ok:
        raise ValueError(message)


def inspect_vcd(path, first, last, cycles):
    codes, initial, scopes = set(), set(), []
    header = []
    definitions = snapshot = initial_done = False
    current = clock = clock_value = clock_time = unit_fs = None
    edges = stamps = records = unknown_initial = 0
    with path.open() as stream:
        for raw in stream:
            require(raw.endswith('\n'), 'Partial final VCD record')
            line = raw.strip()
            if not definitions:
                if line.startswith('$scope '):
                    scopes.append(line.split()[2])
                elif line.startswith('$upscope'):
                    require(scopes, 'Unbalanced scope')
                    scopes.pop()
                elif line.startswith('$var '):
                    fields = line.split()
                    code, name = fields[3:5]
                    codes.add(code)
                    if '.'.join([*scopes, name]) == 'ara_tb.dut.i_ara_soc.clk_i':
                        require(clock is None, 'Duplicate root clock')
                        clock = code
                if len(header) < 40:
                    header.append(line)
                if line.startswith('$enddefinitions'):
                    match = re.search(r'\$timescale\s+(1|10|100)\s*(fs|ps|ns)\s+\$end', ' '.join(header))
                    require(match and clock and codes and not scopes, 'VCD header/scope/clock incomplete')
                    unit_fs = int(match[1]) * {'fs': 1, 'ps': 1000, 'ns': 1000000}[match[2]]
                    require((last-first)*unit_fs == cycles*1000000, 'Cycle/timescale disagreement')
                    definitions = True
                continue
            if not line:
                continue
            if line.startswith('#'):
                tick = int(line[1:])
                require(first <= tick <= last and (current is None and tick == first or
                        current is not None and tick >= current), 'VCD bounds/order')
                require(current is None or tick == current or initial_done, 'Unterminated initial state')
                current = tick
                stamps += 1
                continue
            if line == '$dumpvars':
                require(current == first and not snapshot and not initial_done, 'Initial state start')
                snapshot = True
                continue
            if line == '$end':
                require(snapshot and initial == codes, 'Initial state inventory incomplete')
                snapshot, initial_done = False, True
                continue
            require(not line.startswith('$') and current is not None, 'Unexpected VCD control record')
            if line[0] in '01xXzZ':
                value, code = line[0].lower(), line[1:]
            else:
                parts = line.split()
                require(line[0] in 'bBrR' and len(parts) == 2, 'Malformed VCD value record')
                value, code = parts
                if line[0] in 'bB':
                    require(set(value[1:].lower()) <= set('01xz'), 'Invalid binary value')
            require(code in codes, 'Undeclared VCD identifier')
            records += 1
            if snapshot:
                initial.add(code)
                unknown_initial += int('x' in value.lower() or 'z' in value.lower())
            else:
                require(initial_done, 'Value outside complete initial state')
            if code == clock:
                require(value in ('0', '1'), 'Unknown root clock')
                if clock_value is not None and value != clock_value:
                    require((current-clock_time)*unit_fs == 500000, 'Clock half-period disagreement')
                    edges += 1
                if clock_value is None or value != clock_value:
                    clock_time = current
                clock_value = value
    require(definitions and initial_done and not snapshot and current == last and stamps >= 2 and
            edges in (cycles*2-1, cycles*2), 'EOF window incomplete')
    return dict(first_tick=first, last_tick=last, duration_fs=(last-first)*unit_fs,
        timescale_fs=unit_fs, declared_identifiers=len(codes), initial_identifiers=len(initial),
        complete_initial_state=True, clock_path='ara_tb.dut.i_ara_soc.clk_i', clock_edges=edges,
        timestamps=stamps, value_records=records, initial_unknown_value_records=unknown_initial,
        eof_at_selected_end=True, textual_dumpoff_present=False,
        endpoint_contract='Closed native EOF at matching TB $finish; no waveform bytes added or removed')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run, out = args.run.resolve(), args.output.resolve()
    require(out.parent == run.parent and out.name.startswith('power_gate_capture_audit_20261117_') and
            not out.exists(), 'Fresh independent audit output required')
    spec = importlib.util.spec_from_file_location('frozen_capture_runner', run / 'inputs/gate_run.py')
    b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(b)
    require(b.sha(run / 'inputs/gate_run.py') ==
            'e05b5a5b23a5ca3ade67aebd10843029b5e1012745210fb1d87678ae43f37f5d', 'Frozen checker identity')
    attempt = b.read(run / 'attempt.json')
    plan, binding = b.check_binding(run, attempt['plan_sha256'], attempt['binding_sha256'])
    original = b.read(run / 'result.json')
    require(original['state'] == 'FAIL' and original['error'] ==
            "ValueError('Truncated/nonrepresentative gate window')", 'Not the scoped EOF-check failure')
    require(plan['mode'] == 'capture' and plan['case_id'] == b.Q8 and
            '+GATE_STOP_AFTER_CAPTURE' in plan['command'], 'Wrong capture scope')
    log, vcd = run / 'run/run.vcs.log', run / 'run/window.vcd'
    text = log.read_text()
    b.clean_log(text)
    b.clean_log((run / 'run/console.log').read_text())
    first, last = b.capture_markers(text, plan['first_cycle'], plan['last_cycle'])
    require(re.search(r'\$finish at simulation time\s+' + str(last) + r'\s*$', text, re.M) and
            'V C S   S i m u l a t i o n   R e p o r t' in text and
            'Core Test *** SUCCESS ***' not in text, 'Not a clean bounded TB finish')
    progress = [json.loads(line) for line in (run / 'progress.jsonl').read_text().splitlines()]
    require(progress and all(p['owner_pid'] == attempt['pid'] and
            p['child_pid'] == progress[0]['child_pid'] for p in progress), 'Owned PID scope disagreement')
    paths = [Path(__file__).resolve(), run / 'result.json', run / 'attempt.json', run / 'progress.jsonl',
        run / 'plan.json', run / 'source-pins.json', run / 'image-pins.json', run / 'image-binding.json',
        log, vcd, run / 'run/console.log', Path(plan['release']), b.GATE / 'source/power_capture.sv']
    pins = {str(p): b.sha(p) for p in paths}
    stat = vcd.stat()
    require(attempt['started_ns'] <= stat.st_mtime_ns <= log.stat().st_mtime_ns + 2*10**9 and
            0 < stat.st_size <= plan['max_vcd_bytes'], 'Capture timestamp/size provenance')
    evidence = inspect_vcd(vcd, first, last, plan['last_cycle']-plan['first_cycle'])
    b.verify(pins)
    out.mkdir()
    b.save(out / 'source-pins.json', pins, True)
    result = dict(state='CAPTURE_COMPLETE_NOT_TASK_PASS', schema='independent-native-eof-capture-audit-v1',
        original_result=dict(path=str(run / 'result.json'), sha256=pins[str(run / 'result.json')], state='FAIL'),
        original_worker_reclassified=False, independent_audit=True, vcd=str(vcd), log=str(log),
        vcd_sha256=pins[str(vcd)], log_sha256=pins[str(log)], first_cycle=plan['first_cycle'],
        last_cycle=plan['last_cycle'], first_tick=first, last_tick=last, clock_period_ns=1,
        simv_sha256=binding['simv_sha256'], elf_sha256=plan['elf_map']['sha256'],
        source_pins=str(run / 'source-pins.json'), image_pins=str(run / 'image-pins.json'),
        checked_artifacts=pins, vcd_evidence=evidence, owner_pid=attempt['pid'],
        simulator_pid=progress[0]['child_pid'], rtl_admission_preserved=True,
        capture_is_task_pass=False, task_pass=False, full_gate_task_pass=False,
        gate_numeric_checked=False, gate_protocol_checked=False, timing_acceptance=False, power_acceptance=False,
        reason='Original checker required a textual $dumpoff; native file instead closes at exact TB $finish',
        limitation='Clock/window integrity only; gate compute-phase representativeness and internal X activity remain separate')
    b.save(out / 'result.json', result, True)
    print(json.dumps(dict(state=result['state'], output=str(out), evidence=evidence)))


if __name__ == '__main__':
    main()
