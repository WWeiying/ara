#!/usr/bin/env python3
"""Finite exact-ELF native activity collection; RTL evidence owns task acceptance."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


n = load('gate_native_v2')
a = load('audit_gate_capture_eof')
b = n.b
CONTROL_SHA = 'd0ec28d8870c2dff756706c9543e166216f399fb20df6736c46c9cd610cdc7a6'
CASES = {
    'm1': ('qwen3_real_decode_attn_q_m1_n64_native', 36520, 39994, 45000,
           'Second full-K N32 QBS command, RTL retire anchors 36519 and 39994'),
    'm4': ('qwen3_attn_q_q4k_m4_n64_direct_native', 206000, 208048, 215000,
           '2048-cycle interior of second command, RTL retire anchors 203222 and 212844'),
    'akv': ('power_attention_akv', 48405, 51399, 55000,
            'Second KV64 PV row-load/FMA phase, RTL row-load anchors 48406 through 51367'),
}


def final_check(out, plan, binding, run):
    b.require(plan['mode'] == 'capture' and run['returncode'] == 0, 'Not a successful bounded simulator exit')
    log, vcd = out / 'run/run.vcs.log', out / 'run/window.vcd'
    text = log.read_text()
    b.clean_log(text)
    b.clean_log((out / 'run/console.log').read_text())
    first, last = b.capture_markers(text, plan['first_cycle'], plan['last_cycle'])
    b.require(re.search(r'\$finish at simulation time\s+' + str(last) + r'\s*$', text, re.M) and
              'V C S   S i m u l a t i o n   R e p o r t' in text, 'Missing clean native EOF/finish')
    stat = vcd.stat()
    b.require(0 < stat.st_size <= plan['max_vcd_bytes'] and
              run['started_ns'] <= stat.st_mtime_ns <= run['finished_ns'] + 2*10**9 and
              run['started_ns'] <= stat.st_ctime_ns <= run['finished_ns'] + 2*10**9,
              'VCD file provenance/size mismatch')
    evidence = a.inspect_vcd(vcd, first, last, plan['last_cycle']-plan['first_cycle'])
    return dict(state='CAPTURE_COMPLETE_NOT_TASK_PASS', schema='power-native-activity-v3',
        case_id=plan['case_id'], vcd=str(vcd), log=str(log), first_cycle=plan['first_cycle'],
        last_cycle=plan['last_cycle'], first_tick=first, last_tick=last, clock_period_ns=1,
        vcd_sha256=b.sha(vcd), log_sha256=b.sha(log), simv_sha256=binding['simv_sha256'],
        elf_sha256=plan['elf_map']['sha256'], elf_map=plan['elf_map'], release=plan['release'],
        release_sha256=plan['release_sha256'], source_pins=str(out / 'source-pins.json'),
        image_pins=str(out / 'image-pins.json'), vcd_evidence=evidence,
        full_gate_task_pass=False, task_pass=False, gate_numeric_checked=False,
        gate_protocol_checked=False, roi_gate_phase_verified=False,
        rtl_admission_preserved=True, power_acceptance=False, timing_acceptance=False,
        scope='Native bounded EOF capture only; confirm mapped workload phase and SAIF X activity before relative-power use',
        checked_artifacts={str(p): b.sha(p) for p in [out / 'plan.json', out / 'source-pins.json',
            out / 'image-pins.json', out / 'image-binding.json', out / 'roi-selection.json', log, vcd]}, **run)


def prepare(args, out):
    case, first, last, maximum, selection = CASES[args.case]
    b.require(b.sha(b.GATE / 'source/power_capture.sv') == CONTROL_SHA, 'Frozen TB drift')
    config = argparse.Namespace(output=out, image=b.GATE, release=args.release.resolve(),
        release_sha256=args.release_sha256, case=case, mode='capture', first_cycle=first,
        last_cycle=last, max_cycles=maximum, wall_seconds=14400, slot_seconds=21600,
        max_vcd_bytes=4*1024**3)
    # Sealed base permits at most four hours of slot wait.
    config.slot_seconds = 14400
    b.prepare(config)
    plan = b.read(out / 'plan.json')
    work = Path(plan['original_result']).parent
    roi = dict(first_cycle=first, last_cycle=last, selection=selection,
        trace=str(work / 'commit.csv'), trace_sha256=b.sha(work / 'commit.csv'),
        gate_phase_verified=False, whole_task_energy=False,
        limitation='RTL-derived compute-phase hypothesis; confirm mapped gate activity after capture')
    b.save(out / 'roi-selection.json', roi, True)
    pins = b.read(out / 'source-pins.json')
    for name in ('gate_activity_v3.py', 'test_gate_activity_v3.py', 'gate_native_v2.py', 'audit_gate_capture_eof.py'):
        source, dest = HERE / name, out / 'inputs' / name
        b.shutil.copyfile(source, dest)
        pins[str(source)] = b.sha(source)
        pins[str(dest)] = b.sha(dest)
    for path in (out / 'roi-selection.json', work / 'commit.csv', work / 'run.vcs.log'):
        pins[str(path)] = b.sha(path)
    b.save(out / 'source-pins.json', pins)


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('action', choices=('prepare', 'bind-image', 'check', 'execute'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--case', choices=CASES)
    parser.add_argument('--release', type=Path)
    parser.add_argument('--release-sha256')
    parser.add_argument('--plan-sha256')
    parser.add_argument('--binding-sha256')
    parser.add_argument('--authorize-run', action='store_true')
    args = parser.parse_args()
    out = b.scoped_output(args.output)
    if args.action == 'execute':
        b.require(Path(__file__).resolve() == out / 'inputs/gate_activity_v3.py', 'Frozen own worker required')
        b.require(b.sha(b.GATE / 'source/power_capture.sv') == CONTROL_SHA, 'TB control identity drift')
        b.final_check = final_check
        return b.execute(out, args.plan_sha256, args.binding_sha256, args.authorize_run)
    b.require(not args.authorize_run, 'Authorization only for frozen execute')
    if args.action == 'prepare':
        b.require(args.case and args.release and args.release_sha256, 'Explicit case and release required')
        prepare(args, out)
    elif args.action == 'bind-image':
        b.bind_image(out)
        ready = b.read(out / 'ready-command.json')
        for key in ('service', 'worker'):
            ready[key] = [str(out / 'inputs/gate_activity_v3.py') if v == str(out / 'inputs/gate_run.py')
                          else v for v in ready[key]]
        ready['shell'] = b.shlex.join(ready['service'])
        b.save(out / 'ready-command.json', ready)
    else:
        b.check_binding(out, args.plan_sha256, args.binding_sha256)
    print(json.dumps(dict(action=args.action, output=str(out), launched=False)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
