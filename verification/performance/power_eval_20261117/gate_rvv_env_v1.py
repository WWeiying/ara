#!/usr/bin/env python3
"""Fail-closed baseline first-X diagnosis, data-only startup candidate and capture.

No mapped logic, cell model, ELF, reset, active control or runtime data repair.
An unchanged mapped ALU discriminator and opposite VRF seeds precede capture.
"""
import argparse
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

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('rvv_firstx_readonly', HERE / 'gate_rvv_xdiag_v1.py')
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)
b, s = d.b, d.s
OUT, OLD, PARENT = b.OUT, d.OLD, b.GATE
DEFAULT = OUT / 'power_gls_20261117_baseline_rvv_env_01'
DIAG = d.DEFAULT
NET_SHA = '113e08053dab899b1e2a646e936218068d8cfbffb80c26b0b3a92a5d21364d7b'
EXPECTED = {'0x80001380': ['0xffffffff3f1604c5'], '0x80001384': ['0xffffffffbef882d7']}


def known(bits):
    return bool(bits) and set(bits) <= {'0', '1'}


def firstx_witness(report):
    b.require(report['state'] == 'FIRST_X_DIAGNOSTIC_COMPLETE_NOT_POWER', 'Original first-X diagnostic required')
    rows = []
    for row in report['wave']['merge_samples']:
        v = {k.rsplit('.', 1)[-1]: x for k, x in row['values'].items()}
        a, other, result = (v.get(k, '') for k in ('operand_a_i', 'operand_b_i', 'result_o'))
        if (known(a) and not known(other) and not known(result) and
                v.get('vm_i') == '1' and known(v.get('mask_i', '')) and int(v['mask_i'], 2) == 255):
            rows.append(dict(tick=row['tick'], a=hex(int(a, 2)), b=other, result=result))
    b.require(rows, 'No selected-known-A / unused-B-X / merge-result-X witness; do not guess repair')
    b.require(any(not x.startswith('0x') for values in report['wave']['reductions'].values() for x in values),
              'No propagated scalar reduction X; do not assume same root cause')
    return rows[0]


def memories(text):
    modules = {m[1]: m[0] for m in re.finditer(r'^module\s+(\w+)\b.*?^endmodule\b', text, re.M | re.S)}
    def child(body, instance):
        hits = re.findall(r'^\s*(\w+)\s+' + re.escape(instance) + r'\s*\(', body, re.M)
        b.require(len(hits) == 1, 'Ambiguous mapped instance: ' + instance)
        return modules[hits[0]]
    result = []
    for lane in range(4):
        inst = 'gen_lanes_%d__i_lane' % lane
        body = child(child(text, inst), 'i_vrf')
        for bank in range(8):
            name = 'gen_banks_%d__data_sram' % bank
            b.require(re.search(r'TS1N28HPCPUHDSVTB16X64M1SWBSO\s+' + name + r'\s*\(', body),
                      'Unexpected VRF geometry')
            result.append('ara_tb.dut.i_ara_soc.i_system.i_ara.' + inst + '.i_vrf.' + name)
    b.require(len(set(result)) == 32, 'Exact VRF whitelist required')
    return result


def initializer(paths):
    return '''module power_rvv_vrf_startup;
  timeunit 1ns; timeprecision 100fs;
  integer seed;
  bit done=0;
  initial begin
    if (!$value$plusargs("GATE_VRF_INIT_SEED=%d", seed) || !(seed inside {0,1}))
      $fatal(1,"Explicit VRF diagnostic seed required");
    wait (ara_tb.rst_n === 1'b0);
    repeat (3) @(negedge ara_tb.clk);
    #0.1;
    if (ara_tb.rst_n !== 1'b0) $fatal(1,"Startup must be inside reset");
''' + ''.join("    for (int row=0; row<16; row++) %s.MEMORY[row][0] = seed ? '1 : '0;\n" % x for x in paths) + '''    done=1;
    $display("GATE_RVV_VRF_INIT seed=%0d words=512 reset=0 force=0",seed);
  end
  always @(posedge ara_tb.rst_n)
    if (!done) $fatal(1,"Startup not completed before reset release");
endmodule
'''


def clean_quality(report, warnings):
    b.require(not warnings['counts'], 'Actual enabled SRAM X warning remains; no activity admission')
    required = ('pc_commit', 'commit_ack_commit_id', 'state_q')
    for name in required:
        rows = [v for k, v in report['signals'].items() if k.endswith('.' + name)]
        b.require(len(rows) == 1 and rows[0]['unknown_records'] == 0, 'Control/PC X remains: ' + name)
    b.require(report['signals']['ara_tb.dut.i_ara_soc.clk_i']['unknown_records'] == 0,
              'Top-level clock X')


def prepare(out):
    b.require(out == DEFAULT and not out.exists(), 'Fresh owned environment output required')
    b.verify(b.read(OLD / 'source-pins.json'))
    b.verify(b.read(PARENT / 'source-pins.json'))
    b.require(b.sha(PARENT / 'source/ara_soc_dc.v') == NET_SHA, 'Original mapped netlist required')
    out.mkdir()
    (out / 'inputs').mkdir()
    image = out / 'image'
    image.mkdir()
    for folder in ('source', 'models'):
        shutil.copytree(PARENT / folder, image / folder)
    for folder in ('sim', 'logs'):
        (image / folder).mkdir()
    shutil.copyfile(PARENT / 'elfloader.o', image / 'elfloader.o')
    paths = memories((image / 'source/ara_soc_dc.v').read_text())
    (image / 'source/power_rvv_vrf_startup.sv').write_text(initializer(paths))
    (image / 'sources.f').write_text((PARENT / 'sources.f').read_text().replace(str(PARENT), str(image)))
    argv = [x.replace(str(PARENT), str(image)) for x in b.read(PARENT / 'plan.json')['compile_argv_template_not_authorized']]
    argv[1:1] = ['-top', 'power_rvv_vrf_startup', str(image / 'source/power_rvv_vrf_startup.sv')]
    pins = {}
    for name in ('gate_rvv_env_v1.py', 'test_gate_rvv_env_v1.py', 'gate_rvv_xdiag_v1.py',
                 'test_gate_rvv_xdiag_v1.py', 'gate_rvv_activity_v2.py', 'gate_rvv_activity.py',
                 'gate_run.py', 'audit_gate_capture_eof.py'):
        src, dst = HERE / name, out / 'inputs' / name
        shutil.copyfile(src, dst)
        pins[str(src)] = pins[str(dst)] = b.sha(src)
    # Save an independent rejection; the original successful EOF record is not changed.
    old = b.read(OLD / 'cases/m1/result.json')
    old_wave = d.inspect(OLD / 'cases/m1/run/window.vcd')
    old_warnings = d.log_evidence(OLD / 'cases/m1/run/run.vcs.log')
    b.save(out / 'original-m1-x-audit.json', dict(state='X_CONTAMINATED_NOT_POWER',
        original_result=str(OLD / 'cases/m1/result.json'), original_result_sha256=b.sha(OLD / 'cases/m1/result.json'),
        original_vcd_sha256=old['vcd_sha256'], original_log_sha256=old['log_sha256'],
        wave=old_wave, warnings=old_warnings, power_acceptance=False), True)
    cases = []
    for kind, seed, diagnostic in [('m1', 0, True), ('m1', 1, True),
                                    ('m1', 0, False), ('m4', 0, False), ('attention', 0, False)]:
        key = 'diag%d' % seed if diagnostic else kind
        case = out / 'cases' / key
        shutil.copytree(OLD / 'cases' / kind / 'inputs', case / 'inputs')
        (case / 'run').mkdir()
        plan = b.read(OLD / 'cases' / kind / 'plan.json')
        # Small padding admits the two actual mapped PC anchors for phase checking.
        first, last = (15170, 15690) if diagnostic else (plan['first_cycle'] - 64, plan['last_cycle'] + 64)
        command = [str(image / 'sim/simv'), '-no_save', '-l', str(case / 'run/run.vcs.log'),
                   '+PRELOAD=' + str(case / 'inputs/program.elf'), '+TESTCASE=rvv_env_' + key,
                   '+NO_FSDB', '+NO_INSTR_TRACE', '+GATE_MAX_CYCLES=' + str(last + 128),
                   '+GATE_VCD=' + str(case / 'run/window.vcd'), '+GATE_ROI_FIRST=' + str(first),
                   '+GATE_ROI_LAST=' + str(last), '+GATE_STOP_AFTER_CAPTURE', '+GATE_VRF_INIT_SEED=' + str(seed)]
        plan.update(command=command, image=str(image), elf=str(case / 'inputs/program.elf'),
                    first_cycle=first, last_cycle=last, max_cycles=last + 128, init_seed=seed,
                    diagnostic_only=diagnostic, cwd=str(case / 'run'))
        b.save(case / 'plan.json', plan, True)
        cases.append(dict(key=key, path=str(case)))
    with (out / 'host-tests.log').open('x') as log:
        subprocess.run([sys.executable, '-B', str(out / 'inputs/test_gate_rvv_env_v1.py'), '-v'],
                       check=True, stdout=log, stderr=subprocess.STDOUT, timeout=120)
    b.save(out / 'plan.json', dict(schema='rvv-scoped-startup-environment-v1', cases=cases,
        original_firstx=str(DIAG), parent_image=str(PARENT), image=str(image), compile_command=argv,
        initialized_memories=paths, initialized_words=512, initialized_bytes=4096,
        netlist_sha256=NET_SHA, controls_initialized=False, cells_or_models_changed=False,
        runtime_force=False, original_ELFs_unchanged=True, strict_FAIL_preserved=True,
        require_opposite_seed_reductions=EXPECTED, power_acceptance=False,
        stop_after_first_failure=True, automatic_retry=False), True)
    for p in out.rglob('*'):
        if p.is_file():
            pins[str(p)] = b.sha(p)
    for p in (OLD / 'source-pins.json', PARENT / 'source-pins.json',
              OLD / 'cases/m1/result.json', DIAG / 'source-pins.json'):
        pins[str(p)] = b.sha(p)
    b.save(out / 'source-pins.json', pins, True)
    worker = ['/usr/bin/python3', '-B', str(out / 'inputs/gate_rvv_env_v1.py'), 'execute', '--output', str(out),
              '--plan-sha256', b.sha(out / 'plan.json')]
    service = ['systemd-run', '--user', '--unit=' + out.name.replace('_', '-') + '.service',
               '--property=Type=exec', '--property=KillMode=control-group', '--property=RuntimeMaxSec=86400',
               '--property=StandardOutput=append:' + str(out / 'service.stdout.log'),
               '--property=StandardError=append:' + str(out / 'service.stderr.log'), *worker]
    b.save(out / 'ready-command.json', dict(service=service), True)


def mapped_probe(out, witness, environment):
    probe = out / 'mapped-probe'
    probe.mkdir()
    text = (PARENT / 'source/ara_soc_dc.v').read_text()
    match = re.search(r'^module simd_alu_1_0_ara_soc\b.*?^endmodule\b', text, re.M | re.S)
    b.require(match, 'Actual lane0 mapped ALU required')
    (probe / 'mapped_alu.v').write_text(match[0] + '\n')
    (probe / 'probe.sv').write_text('''module rvv_merge_discriminator;
  timeunit 1ns; timeprecision 100fs;
  reg [63:0] a=64'h%s, b='x;
  wire [63:0] result;
  wire [7:0] sat;
  simd_alu_1_0_ara_soc dut(.operand_a_i(a),.operand_b_i(b),.valid_i(1'b1),
    .vm_i(1'b1),.mask_i(8'hff),.narrowing_select_i(1'b0),.op_i(8'd29),
    .vew_i(3'd2),.vxsat_o(sat),.rm(8'b0),.vxrm_i(2'b0),.result_o(result));
  initial begin
    #1;
    if (!$isunknown(result)) $fatal(1,"Witness did not reproduce");
    for(int i=0;i<1024;i++) begin
      b=i==0 ? 64'b0 : i==1 ? 64'hffffffffffffffff : {$urandom,$urandom};
      #0.1;
      if(result !== a) $fatal(1,"Selected A depends on concrete unused B");
    end
    $display("BASELINE_MAPPED_MERGE_X_PESSIMISM_PROVED concrete_B_vectors=1024");
    $finish;
  end
endmodule
''' % witness['a'][2:])
    argv = [b.read(PARENT / 'plan.json')['compile_argv_template_not_authorized'][0], '-full64', '-sverilog',
            '+nospecify', '+notimingchecks', '-timescale=1ns/100fs', '-top', 'rvv_merge_discriminator',
            str(probe / 'probe.sv'), str(probe / 'mapped_alu.v'), '-o', str(probe / 'simv')]
    for path in sorted((PARENT / 'models').glob('tcbn*.v')):
        argv += ['-v', str(path)]
    with (probe / 'compile.log').open('x') as log:
        subprocess.run(argv, cwd=probe, env=environment, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=600)
    deadline = time.monotonic() + 14400
    while True:
        with b.shared_launch_locks():
            snapshot = b.capacity(b.g.process_snapshot())
            if snapshot['launch_allowed'] and not s.q8_gls_units():
                with (probe / 'run.log').open('x') as log:
                    p = subprocess.Popen([str(probe / 'simv')], cwd=probe, env=environment,
                                         stdout=log, stderr=subprocess.STDOUT)
                break
        b.require(time.monotonic() < deadline, 'Bounded probe slot wait expired')
        time.sleep(60)
    try:
        b.require(p.wait(timeout=30) == 0, 'Mapped discriminator failed')
    finally:
        b.g.stop_process(p)
    b.require('BASELINE_MAPPED_MERGE_X_PESSIMISM_PROVED concrete_B_vectors=1024' in
              (probe / 'run.log').read_text(), 'Missing actual mapped proof')
    return dict(state='BASELINE_MAPPED_UNUSED_B_X_PESSIMISM_PROVED_NOT_TASK_PASS', witness=witness,
                concrete_B_vectors=1024, files={str(p): b.sha(p) for p in
                (probe / 'mapped_alu.v', probe / 'probe.sv', probe / 'compile.log', probe / 'run.log')})


def execute(out, plan_sha):
    b.require(out == DEFAULT and Path(__file__).resolve() == out / 'inputs/gate_rvv_env_v1.py', 'Frozen environment worker')
    unit = out.name.replace('_', '-') + '.service'
    owner = subprocess.check_output(['systemctl', '--user', 'show', unit, '-p', 'MainPID', '--value'], text=True).strip()
    b.require(owner == str(os.getpid()) and unit in Path('/proc/self/cgroup').read_text(), 'Direct service owner required')
    b.require(b.sha(out / 'plan.json') == plan_sha, 'Plan drift')
    pins = b.read(out / 'source-pins.json')
    b.verify(pins)
    plan = b.read(out / 'plan.json')
    b.save(out / 'attempt.json', dict(pid=os.getpid(), started_ns=time.time_ns()), True)
    def interrupted(signum, frame):
        raise InterruptedError(signum)
    signal.signal(signal.SIGTERM, interrupted)
    results = []
    try:
        b.q8_units = s.q8_gls_units
        b.save(out / 'status.json', dict(state='WAITING_ORIGINAL_FIRST_X_DIAGNOSTIC'))
        deadline = time.monotonic() + 7200
        while not (DIAG / 'result.json').exists():
            b.require(time.monotonic() < deadline, 'First-X diagnostic wait expired')
            time.sleep(60)
        original = b.read(DIAG / 'result.json')
        b.verify(b.read(DIAG / 'source-pins.json'))
        b.verify({original['capture']['vcd']: original['capture']['vcd_sha256'],
                  str(DIAG / 'cases/m1/run/run.vcs.log'): original['capture']['log_sha256']})
        witness = firstx_witness(original)
        environment = b.read(out / 'cases/diag0/inputs/rtl-plan.json')['environment']
        proof = mapped_probe(out, witness, environment)
        b.save(out / 'root-cause.json', dict(mapped_proof=proof, diagnostic=str(DIAG / 'result.json'),
            diagnostic_sha256=b.sha(DIAG / 'result.json'), original_warnings=original['warnings'],
            hypothesis='Unreset unused VRF payload reaches selected-A merge; mapped Boolean factoring propagates unused-B X into VRF, reductions, CPU and dispatcher',
            scoped_candidate_not_yet_validated=True, real_failures_not_hidden=True), True)
        b.verify(pins)
        image = Path(plan['image'])
        b.save(out / 'status.json', dict(state='COMPILING_SAME_NETLIST_DATA_ONLY_STARTUP_ENVIRONMENT'))
        with (image / 'logs/compile-console.log').open('x') as log:
            subprocess.run(plan['compile_command'], cwd=image / 'sim', env=environment, stdout=log,
                           stderr=subprocess.STDOUT, check=True, timeout=7200)
        b.verify(pins)
        b.require(b.sha(image / 'source/ara_soc_dc.v') == b.sha(PARENT / 'source/ara_soc_dc.v') == NET_SHA,
                  'Mapped netlist changed')
        images = {str(p): b.sha(p) for p in [image / 'sim/simv',
                  *(p for p in (image / 'sim/simv.daidir').rglob('*') if p.is_file())]}
        b.save(out / 'image-pins.json', images, True)
        binding = b.read(OLD / 'image-binding.json')
        binding.update(simv_sha256=images[str(image / 'sim/simv')], image_pins=images,
                       parent_image=str(PARENT), environment_delta='Reset-only VRF data startup; 512 words; no controls or model edits')
        for entry in plan['cases']:
            case = Path(entry['path'])
            capture_plan = b.read(case / 'plan.json')
            b.verify(pins)
            b.verify(images)
            run = b.run_capture(out, case, capture_plan, dict(pins, **images))
            result = b.finish_capture(case, capture_plan, binding, run)
            wave = d.inspect(case / 'run/window.vcd')
            warnings = d.log_evidence(case / 'run/run.vcs.log')
            clean_quality(wave, warnings)
            text = (case / 'run/run.vcs.log').read_text()
            marks = re.findall(r'^GATE_RVV_VRF_INIT seed=([01]) words=512 reset=0 force=0$', text, re.M)
            b.require(marks == [str(capture_plan['init_seed'])], 'Actual scoped startup evidence missing')
            if capture_plan['diagnostic_only']:
                b.require(wave['reductions'] == EXPECTED, 'Opposite seed must match exact original RTL reductions')
                result['state'] = 'EXACT_REDUCTION_DIAGNOSTIC_PASS_NOT_TASK_PASS'
            result.update(environment='RESET_ONLY_VRF_STARTUP', init_seed=capture_plan['init_seed'],
                          wave_quality=wave, memory_warnings=warnings, netlist_sha256=NET_SHA,
                          original_strict_FAIL_preserved=True, power_acceptance=False, gate_phase_checked=False)
            b.verify(pins)
            b.verify(images)
            b.save(case / 'result.json', result, True)
            results.append(dict(key=entry['key'], result=str(case / 'result.json'), state=result['state']))
            if entry['key'] == 'diag1':
                b.save(out / 'environment-validation.json', dict(state='OPPOSITE_VRF_SEEDS_EXACT_REDUCTIONS_PASS',
                    seeds=[0, 1], reductions=EXPECTED, full_gate_task_pass=False,
                    no_active_SRAM_X=True, controls_known=True, netlist_unchanged=True,
                    whole_task_initial_state_independence_proven=False, power_acceptance=False), True)
        result = dict(state='X_CLEAN_WINDOWS_CAPTURED_NOT_POWER_ACCEPTANCE', cases=results,
                      gate_phase_checked=False, power_acceptance=False, full_gate_task_pass=False)
    except BaseException as exc:
        result = dict(state='FAIL_STOP_NO_RETRY', error=repr(exc), completed_cases=results,
                      power_acceptance=False, original_FAILs_unchanged=True)
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
