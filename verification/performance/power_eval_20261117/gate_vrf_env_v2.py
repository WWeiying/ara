#!/usr/bin/env python3
"""Same mapped netlist, reset-only legal startup contents of VRF memory only.

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
BUILD = b.OUT / 'power_gate_build_20261117_vrf_init_02'
STATE = 'DC_MATCHED_GATE_VRF_INIT_BUILT_NOT_VALIDATED'
UNIT = 'power-gate-build-20261117-vrf-init-02.service'
RELEASE = b.OUT / 'power_native_release_20261117_activity_03/release.json'


def configure(image):
    b.GATE = image
    b.GATE_STATE = STATE


def vrf_memories(text):
    modules = {m[1]: m[0] for m in re.finditer(
        r'^[ \t]*module\s+(\w+)\b.*?^endmodule\b', text, re.M | re.S)}
    def child(body, instance):
        matches = re.findall(r'^[ \t]*(\w+)\s+' + re.escape(instance) + r'\s*\(', body, re.M)
        b.require(len(matches) == 1, 'Ambiguous mapped instance: ' + instance)
        return modules[matches[0]]
    memories = []
    for lane in range(4):
        name = 'gen_lanes_%d__i_lane' % lane
        body = child(child(text, name), 'i_vrf')
        for bank in range(8):
            instance = 'gen_banks_%d__data_sram' % bank
            b.require(re.search(r'TS1N28HPCPUHDSVTB16X64M1SWBSO\s+' +
                      instance + r'\s*\(', body), 'Wrong VRF SRAM geometry')
            memories.append('ara_tb.dut.i_ara_soc.i_system.i_ara.' + name + '.i_vrf.' + instance)
    b.require(len(set(memories)) == 32, 'VRF SRAM inventory mismatch')
    return memories


def vrf_initializer(memories):
    header = """module power_vrf_init;
  timeunit 1ns; timeprecision 100fs;
  integer seed;
  bit done=0;
  initial begin
    if (!$value$plusargs("GATE_VRF_INIT_SEED=%d",seed) || !(seed inside {0,1}))
      $fatal(1,"Mandatory reviewed VRF startup seed");
    wait (ara_tb.rst_n === 1'b0);
    repeat (3) @(negedge ara_tb.clk);
    #0.1;
    if (ara_tb.rst_n !== 1'b0) $fatal(1,"VRF initialization must precede reset release");
"""
    body = ''.join("    for (int row=0; row<16; row++) %s.MEMORY[row][0] = seed ? '1 : '0;\n" % path for path in memories)
    footer = """    done=1;
    $display("GATE_VRF_INIT_COMPLETE seed=%0d words=512 reset=0 runtime_force=0",seed);
  end
  always @(posedge ara_tb.rst_n)
    if (!done) $fatal(1,"VRF startup initialization did not finish in reset");
endmodule
"""
    return header + body + footer


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
    memories = vrf_memories(net.read_text())
    (image / 'source/power_vrf_init.sv').write_text(vrf_initializer(memories))
    (image / 'sources.f').write_text((PARENT / 'sources.f').read_text().replace(str(PARENT), str(image)))
    for name in ('gate_vrf_env_v2.py', 'gate_activity_v3.py', 'test_gate_activity_v3.py',
                 'gate_native_v2.py', 'audit_gate_capture_eof.py'):
        shutil.copyfile(HERE / name, image / 'inputs' / name)
    argv = [v.replace(str(PARENT), str(image)) for v in b.read(PARENT / 'plan.json')['compile_argv_template_not_authorized']]
    argv[1:1] = ['-top', 'power_vrf_init', str(image / 'source/power_vrf_init.sv')]
    receipt = b.read(PARENT / 'gate-receipt.json')
    receipt.update(schema='dc-matched-scoped-payload-init-environment-v1',
        parent_image=str(PARENT), parent_netlist_sha256=b.sha(net),
        environment_delta='Reset-only initialization of exactly 512 VRF SRAM data words; no controls/CPU/cache/cell/netlist edits',
        formal_or_timing_acceptance=False, runtime_force=False)
    b.save(image / 'gate-receipt.json', receipt, True)
    env_plan = b.read(image / 'inputs/rtl-plan.json')
    b.save(image / 'inputs/rtl-plan.json', env_plan)
    plan = dict(schema='scoped-payload-environment-build-v1', image=str(image), parent=str(PARENT),
        compile_command=argv, netlist_sha256=b.sha(net), initialized_memories=memories,
        release=str(RELEASE), release_sha256=b.sha(RELEASE),
        unit=UNIT, timeout_seconds=7200, initialization_time="reset, after three falling edges and before release", no_runtime_forcing=True,
        scope='Environment candidate, not RTL/netlist repair; seed diagnostics gate all measurement launches')
    b.save(image / 'plan.json', plan, True)
    b.save(image / 'rtl-admission.json', admission, True)
    pins = {str(p): b.sha(p) for p in image.rglob('*') if p.is_file()}
    pins[str(PARENT / 'source-pins.json')] = b.sha(PARENT / 'source-pins.json')
    pins[str(Path(__file__).resolve())] = b.sha(__file__)
    b.save(image / 'source-pins.json', pins, True)
    worker = ['/usr/bin/python3', '-B', str(image / 'inputs/gate_vrf_env_v2.py'), 'pipeline',
        '--build', str(image), '--authorize-compile', '--plan-sha256', b.sha(image / 'plan.json')]
    service = ['/usr/bin/systemd-run', '--user', '--unit=' + UNIT, '--property=Type=exec',
        '--property=KillMode=control-group', '--property=RuntimeMaxSec=20000',
        '--property=TimeoutStopSec=30', '--property=StandardOutput=append:' + str(image / 'service.stdout.log'),
        '--property=StandardError=append:' + str(image / 'service.stderr.log'), *worker]
    b.save(image / 'ready-command.json', dict(service=service, shell=b.shlex.join(service), launched=False), True)


def init_evidence(out, image):
    plan = b.read(out / 'plan.json')
    text = (out / 'run/console.log').read_text()
    rows = re.findall(r'^GATE_VRF_INIT_COMPLETE seed=([01]) words=512 reset=0 runtime_force=0\s*$', text, re.M)
    b.require(len(rows) == 1 and int(rows[0]) == plan['init_seed'], 'Exact reset-only startup initialization missing')
    return dict(seed=int(rows[0]), memories=32, words=512, bytes=4096, VRF_only=True,
                controls_initialized=False, CPU_or_cache_initialized=False, runtime_force=False,
                initializer_sha256=b.sha(image / 'source/power_vrf_init.sv'))


def final_check(out, plan, binding, run):
    result = g.final_check(out, plan, binding, run)
    text = (out / 'run/console.log').read_text()
    b.require(not re.search(r'input (?:CLK|CEB/CEBM|WEB/WEBM|A/AM|BWEB/BWEBM) unknown/high-Z', text),
              'Active memory clock/control/address X remains; no power acceptance')
    result.update(environment='RESET_ONLY_VRF_MEMORY_INITIALIZATION', init_seed=plan['init_seed'],
        init_evidence=init_evidence(out, Path(plan['image'])),
        mapped_netlist_sha256=b.read(Path(plan['image']) / 'plan.json')['netlist_sha256'])
    if plan['environment_diagnostic']:
        result['state'] = 'ENVIRONMENT_DIAGNOSTIC_COMPLETE_NOT_POWER'
        result['representative_power_window'] = False
    return result


def prepare_run(image, key, seed, diagnostic):
    configure(image)
    out = b.OUT / ('power_gls_20261117_vrfinit_%s_%s_0%d' % (key, 'diag' if diagnostic else 'activity', seed+1))
    release = b.OUT / ('power_native_release_20261117_activity_03/%s-release.json' % key)
    saved = g.CASES['m1']
    if diagnostic:
        g.CASES['m1'] = (saved[0], 12980, 13430, 13500, 'Opposite time-zero payload seeds; match RTL scalar reductions, not power')
    args = argparse.Namespace(case=key, release=release, release_sha256=b.sha(release))
    g.prepare(args, out)
    g.CASES['m1'] = saved
    private = out / 'inputs/gate_vrf_env_v2.py'
    shutil.copyfile(__file__, private)
    plan = b.read(out / 'plan.json')
    config = image / 'source/power_vrf_init.sv'
    plan['command'].append('+GATE_VRF_INIT_SEED=' + str(seed))
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
    b.require(authorized and Path(__file__).resolve() == image / 'inputs/gate_vrf_env_v2.py', 'Frozen compile worker required')
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
        b.save(image / 'status.json', dict(state='COMPILING_SAME_NETLIST_RESET_ONLY_VRF_INIT'))
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
            netlist_sha256=plan['netlist_sha256'], environment_delta='Exactly 512 VRF data words initialized during reset'), True)
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
        b.save(image / 'environment-validation.json', dict(state='RESET_ONLY_VRF_INIT_DIAGNOSTICS_PASS_NOT_TASK_PASS',
            seeds=[0, 1], reductions=reductions, runs=list(map(str, diagnostics)),
            netlist_unchanged=True, no_runtime_force=True, controls_initialized=False, VRF_only_memory_initialized=True), True)
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
        b.require(Path(__file__).resolve() == out / 'inputs/gate_vrf_env_v2.py', 'Frozen runtime worker required')
        configure(args.build.resolve())
        b.final_check = final_check
        return b.execute(out, args.plan_sha256, args.binding_sha256, args.authorize_run)
    return 0


if __name__ == '__main__':
    sys.exit(main())

