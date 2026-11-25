#!/usr/bin/env python3
"""Same mapped netlist, time-zero init of unreset unused ALU-B FIFO data only.

Compile once, validate opposite initial payloads against RTL scalar results,
then admit bounded activity jobs. Never force active signals or sanitize X.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('activity', HERE / 'gate_activity_v3.py')
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)
b = g.b
PARENT = b.GATE
BUILD = b.OUT / 'power_gate_build_20261117_payload_init_01'
STATE = 'DC_MATCHED_GATE_PAYLOAD_INIT_BUILT_NOT_VALIDATED'
UNIT = 'power-gate-build-20261117-payload-init-01.service'
RELEASE = b.OUT / 'power_native_release_20261117_activity_03/release.json'


def configure(image):
    b.GATE = image
    b.GATE_STATE = STATE


def payload_cells(text):
    modules = {m[1]: m[0] for m in re.finditer(
        r'^[ \t]*module\s+(\w+)\b.*?^endmodule\b', text, re.M | re.S)}
    def child(body, instance):
        matches = re.findall(r'\b(\w+)\s+' + re.escape(instance) + r'\s*\(', body)
        b.require(len(matches) == 1, 'Ambiguous mapped instance: ' + instance)
        return modules[matches[0]]
    cells = []
    for lane in range(4):
        name = 'gen_lanes_%d__i_lane' % lane
        body = child(text, name)
        for instance in ('i_operand_queues', 'i_operand_queue_alu_b', 'i_input_buffer'):
            body = child(body, instance)
        flops = re.findall(r'^\s+(DFQD\w+)\s+(mem_q_reg_\d+__\d+_)\s*\(', body, re.M)
        b.require(len(flops) == 320 and len({f[1] for f in flops}) == 320,
                  'Expected exactly five 64-bit unreset ALU-B payload words')
        prefix = 'ara_tb.dut.i_ara_soc.i_system.i_ara.' + name + '.i_operand_queues.i_operand_queue_alu_b.i_input_buffer.'
        cells += [prefix + f[1] for f in flops]
    b.require(len(cells) == len(set(cells)) == 1280, 'Payload whitelist mismatch')
    return cells


def prepare(image):
    b.require(image == BUILD and not image.exists(), 'Fresh owned build required')
    b.verify(b.read(PARENT / 'source-pins.json'))
    admission = b.admit(PARENT, RELEASE, b.sha(RELEASE))
    b.require(b.read(b.OUT / 'power_alu_merge_probe_20261117_02/result.json')['state'] ==
              'MAPPED_ALU_X_PESSIMISM_PROVED_NOT_SOC_VALIDATION', 'Mapped ALU discriminator required')
    image.mkdir()
    for directory in ('source', 'models', 'inputs'):
        shutil.copytree(PARENT / directory, image / directory)
    shutil.copyfile(PARENT / 'elfloader.o', image / 'elfloader.o')
    (image / 'sim').mkdir()
    (image / 'logs').mkdir()
    net = image / 'source/ara_soc_dc.v'
    b.require(b.sha(net) == b.sha(PARENT / 'source/ara_soc_dc.v'), 'Mapped netlist changed')
    cells = payload_cells(net.read_text())
    for seed in (0, 1):
        (image / ('init%d.cfg' % seed)).write_text('defaultvalue x\n' +
            ''.join('instance %s %d\n' % (cell, seed) for cell in cells))
    (image / 'sources.f').write_text((PARENT / 'sources.f').read_text().replace(str(PARENT), str(image)))
    for name in ('gate_payload_env_v1.py', 'gate_activity_v3.py', 'test_gate_activity_v3.py',
                 'gate_native_v2.py', 'audit_gate_capture_eof.py'):
        shutil.copyfile(HERE / name, image / 'inputs' / name)
    argv = [v.replace(str(PARENT), str(image)) for v in b.read(PARENT / 'plan.json')['compile_argv_template_not_authorized']]
    argv.insert(1, '+vcs+initreg+config+' + str(image / 'init0.cfg'))
    receipt = b.read(PARENT / 'gate-receipt.json')
    receipt.update(schema='dc-matched-scoped-payload-init-environment-v1',
        parent_image=str(PARENT), parent_netlist_sha256=b.sha(net),
        environment_delta='Time-zero initialization of exactly 1280 unreset ALU-B FIFO data flops; no controls/SRAM/cell/netlist edits',
        formal_or_timing_acceptance=False, runtime_force=False)
    b.save(image / 'gate-receipt.json', receipt, True)
    env_plan = b.read(image / 'inputs/rtl-plan.json')
    env_plan['environment']['VCS_PRINT_INITREG_INITIALIZATION'] = '1'
    b.save(image / 'inputs/rtl-plan.json', env_plan)
    plan = dict(schema='scoped-payload-environment-build-v1', image=str(image), parent=str(PARENT),
        compile_command=argv, netlist_sha256=b.sha(net), initialized_cells=cells,
        release=str(RELEASE), release_sha256=b.sha(RELEASE),
        unit=UNIT, timeout_seconds=7200, initialization_time=0, no_runtime_forcing=True,
        scope='Environment candidate, not RTL/netlist repair; seed diagnostics gate all measurement launches')
    b.save(image / 'plan.json', plan, True)
    b.save(image / 'rtl-admission.json', admission, True)
    pins = {str(p): b.sha(p) for p in image.rglob('*') if p.is_file()}
    pins[str(PARENT / 'source-pins.json')] = b.sha(PARENT / 'source-pins.json')
    pins[str(Path(__file__).resolve())] = b.sha(__file__)
    b.save(image / 'source-pins.json', pins, True)
    worker = ['/usr/bin/python3', '-B', str(image / 'inputs/gate_payload_env_v1.py'), 'pipeline',
        '--build', str(image), '--authorize-compile', '--plan-sha256', b.sha(image / 'plan.json')]
    service = ['/usr/bin/systemd-run', '--user', '--unit=' + UNIT, '--property=Type=exec',
        '--property=KillMode=control-group', '--property=RuntimeMaxSec=20000',
        '--property=TimeoutStopSec=30', '--property=StandardOutput=append:' + str(image / 'service.stdout.log'),
        '--property=StandardError=append:' + str(image / 'service.stderr.log'), *worker]
    b.save(image / 'ready-command.json', dict(service=service, shell=b.shlex.join(service), launched=False), True)


def init_evidence(out, image):
    report = out / 'run/vcs_initreg_random_value.txt'
    b.require(report.is_file(), 'Missing actual initreg report; do not assume scope applied')
    allowed = set(b.read(image / 'plan.json')['initialized_cells'])
    observed = set()
    for line in report.read_text().splitlines():
        if not line.strip():
            continue
        fields = line.split('=', 1)
        b.require(len(fields) == 2 and re.fullmatch(r'\s*[01]\s*//\s*1\s+REG\s*', fields[1]),
                  'Unknown initreg report syntax or non-bit payload state')
        path = fields[0].strip().strip('[]')
        matches = [cell for cell in allowed if path == cell or path.startswith(cell + '.')]
        b.require(len(matches) == 1, 'Initialization outside data-only whitelist: ' + path)
        observed.add(matches[0])
    b.require(observed == allowed, 'Missing initialized data cells')
    return dict(path=str(report), sha256=b.sha(report), cells=len(observed), controls_initialized=False,
                SRAM_initialized=False, runtime_force=False)


def final_check(out, plan, binding, run):
    result = g.final_check(out, plan, binding, run)
    text = (out / 'run/console.log').read_text()
    b.require(not re.search(r'input (?:CLK|CEB/CEBM|WEB/WEBM|A/AM|BWEB/BWEBM) unknown/high-Z', text),
              'Active memory clock/control/address X remains; no power acceptance')
    result.update(environment='SCOPED_ALU_B_PAYLOAD_TIME_ZERO_INIT', init_seed=plan['init_seed'],
        init_evidence=init_evidence(out, Path(plan['image'])),
        mapped_netlist_sha256=b.read(Path(plan['image']) / 'plan.json')['netlist_sha256'])
    if plan['environment_diagnostic']:
        result['state'] = 'ENVIRONMENT_DIAGNOSTIC_COMPLETE_NOT_POWER'
        result['representative_power_window'] = False
    return result


def prepare_run(image, key, seed, diagnostic):
    configure(image)
    out = b.OUT / ('power_gls_20261117_payload_%s_%s_0%d' % (key, 'diag' if diagnostic else 'activity', seed+1))
    release = b.OUT / ('power_native_release_20261117_activity_03/%s-release.json' % key)
    saved = g.CASES['m1']
    if diagnostic:
        g.CASES['m1'] = (saved[0], 12980, 13430, 13500, 'Opposite time-zero payload seeds; match RTL scalar reductions, not power')
    args = argparse.Namespace(case=key, release=release, release_sha256=b.sha(release))
    g.prepare(args, out)
    g.CASES['m1'] = saved
    private = out / 'inputs/gate_payload_env_v1.py'
    shutil.copyfile(__file__, private)
    plan = b.read(out / 'plan.json')
    config = image / ('init%d.cfg' % seed)
    plan['command'].append('+vcs+initreg+config+' + str(config))
    plan.update(init_seed=seed, environment_diagnostic=diagnostic)
    b.save(out / 'plan.json', plan)
    pins = b.read(out / 'source-pins.json')
    pins.update({str(p): b.sha(p) for p in (private, Path(__file__).resolve(), out / 'plan.json', config)})
    b.save(out / 'source-pins.json', pins)
    b.bind_image(out)
    ready = b.read(out / 'ready-command.json')
    for name in ('service', 'worker'):
        ready[name] = [str(private) if v == str(out / 'inputs/gate_run.py') else v for v in ready[name]]
        ready[name] += ['--build', str(image)]
    ready['shell'] = b.shlex.join(ready['service'])
    b.save(out / 'ready-command.json', ready)
    subprocess.run(ready['service'], check=True, timeout=30)
    return out


def reduction_values(path):
    values, current, pending, result = {}, None, False, {0x80001380: set(), 0x80001384: set()}
    def sample():
        if not pending:
            return
        pc, ack, data = values.get('(Hk', 'x'), values.get('(I.', 'x'), values.get('(I)', 'x')
        if set(pc) <= set('01') and int(pc, 2) in result and ack.endswith('1'):
            b.require(set(data[-64:]) <= set('01'), 'Committed scalar reduction still contains X')
            result[int(pc, 2)].add(int(data[-32:], 2))
    with path.open() as stream:
        for raw in stream:
            line = raw.strip()
            if line.startswith('#'):
                sample()
                current, pending = int(line[1:]), False
            elif line == '0&':
                pending = True
            elif line.startswith('b'):
                fields = line.split()
                if len(fields) == 2 and fields[1] in ('(Hk', '(I.', '(I)'):
                    values[fields[1]] = fields[0][1:]
        sample()
    expected = {0x80001380: {0x3f1604c5}, 0x80001384: {0xbef882d7}}
    b.require(result == expected, 'Scalar reductions do not match exact RTL trace: ' + str(result))
    return {hex(k): [hex(v) for v in sorted(s)] for k, s in result.items()}


def pipeline(image, plan_sha, authorized):
    b.require(authorized and Path(__file__).resolve() == image / 'inputs/gate_payload_env_v1.py', 'Frozen compile worker required')
    b.require(b.sha(image / 'plan.json') == plan_sha, 'Build plan drift')
    owner = subprocess.check_output(['systemctl', '--user', 'show', UNIT, '-p', 'MainPID', '--value'], text=True).strip()
    b.require(owner == str(os.getpid()) and UNIT in Path('/proc/self/cgroup').read_text(), 'Direct service owner required')
    b.require(not (image / 'attempt.json').exists(), 'No build retry')
    b.save(image / 'attempt.json', dict(pid=os.getpid(), started_ns=time.time_ns()), True)
    plan = b.read(image / 'plan.json')
    try:
        b.verify(b.read(image / 'source-pins.json'))
        configure(image)
        b.admit(image, Path(plan['release']), plan['release_sha256'])
        b.save(image / 'status.json', dict(state='COMPILING_SAME_NETLIST_SCOPED_INIT'))
        env = b.read(image / 'inputs/rtl-plan.json')['environment']
        with (image / 'logs/compile-console.log').open('x') as log:
            proc = subprocess.run(plan['compile_command'], cwd=image / 'sim', env=env,
                                  stdout=log, stderr=subprocess.STDOUT, timeout=7200)
        b.require(proc.returncode == 0, 'Successor compile failed')
        b.verify(b.read(image / 'source-pins.json'))
        b.require(b.sha(image / 'source/ara_soc_dc.v') == plan['netlist_sha256'] ==
                  b.sha(PARENT / 'source/ara_soc_dc.v'), 'Netlist identity changed')
        files = [image / 'sim/simv', *(p for p in (image / 'sim/simv.daidir').rglob('*') if p.is_file())]
        pins = {str(p): b.sha(p) for p in files}
        b.save(image / 'image-pins.json', pins, True)
        b.save(image / 'build.json', dict(state=STATE, image_pins=pins, simulation_validated=False,
            netlist_sha256=plan['netlist_sha256'], environment_delta='Exact 1280 payload-only time-zero initializations'), True)
        diagnostics = [prepare_run(image, 'm1', seed, True) for seed in (0, 1)]
        b.save(image / 'status.json', dict(state='OPPOSITE_PAYLOAD_SEED_DIAGNOSTICS_RUNNING', runs=list(map(str, diagnostics))))
        deadline = time.monotonic() + 7200
        for out in diagnostics:
            while not (out / 'result.json').exists():
                b.require(time.monotonic() < deadline, 'Finite seed diagnostic wait expired')
                time.sleep(30)
            b.require(b.read(out / 'result.json')['state'] == 'ENVIRONMENT_DIAGNOSTIC_COMPLETE_NOT_POWER',
                      'Seed diagnostic failed; do not launch activity captures')
        reductions = [reduction_values(out / 'run/window.vcd') for out in diagnostics]
        b.require(reductions[0] == reductions[1], 'Initial-state dependence remains')
        b.save(image / 'environment-validation.json', dict(state='SCOPED_PAYLOAD_INIT_DIAGNOSTICS_PASS_NOT_TASK_PASS',
            seeds=[0, 1], reductions=reductions, runs=list(map(str, diagnostics)),
            netlist_unchanged=True, no_runtime_force=True, controls_or_SRAM_initialized=False), True)
        runs = [prepare_run(image, key, 0, False) for key in ('m1', 'akv', 'm4')]
        b.save(image / 'status.json', dict(state='VALIDATED_ENVIRONMENT_ACTIVITY_SERVICES_LAUNCHED', runs=list(map(str, runs)),
                                          power_acceptance=False, whole_task_pass=False))
        return 0
    except BaseException as error:
        b.save(image / 'status.json', dict(state='FAIL_STOP_NO_AUTOMATIC_RETRY', error=repr(error), power_acceptance=False))
        raise


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('action', choices=('prepare', 'pipeline', 'execute'))
    parser.add_argument('--build', type=Path, default=BUILD)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--plan-sha256')
    parser.add_argument('--binding-sha256')
    parser.add_argument('--authorize-compile', action='store_true')
    parser.add_argument('--authorize-run', action='store_true')
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare(args.build.resolve())
    elif args.action == 'pipeline':
        return pipeline(args.build.resolve(), args.plan_sha256, args.authorize_compile)
    else:
        out = b.scoped_output(args.output)
        b.require(Path(__file__).resolve() == out / 'inputs/gate_payload_env_v1.py', 'Frozen runtime worker required')
        configure(args.build.resolve())
        b.final_check = final_check
        return b.execute(out, args.plan_sha256, args.binding_sha256, args.authorize_run)
    return 0


if __name__ == '__main__':
    sys.exit(main())
