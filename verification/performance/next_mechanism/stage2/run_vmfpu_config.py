#!/usr/bin/env python3
"""Bounded real-VMFPU gate for the fixed-three-cycle QBS configuration guard."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('full_fp', HERE / 'run_vmfpu_fp.py')
FP = importlib.util.module_from_spec(spec)
spec.loader.exec_module(FP)
ROOT = Path('/home/wangwy/openproject/ara_dsa')
OWN = ('run_vmfpu_config.py', 'test_run_vmfpu_config.py')
REUSED = ('run_vmfpu_fp.py', 'vmfpu_fp_tb.sv', 'vmfpu_tb.sv')
STATIC = ('hardware/src/ara.sv', 'hardware/src/vlsu/vlsu.sv',
          'hardware/src/vlsu/qbs/qbs_engine.sv',
          'hardware/src/vlsu/qbs/qbs_compute_engine.sv')
VARIANTS = (('standard0', 0, 0), ('shared0', 1, 0),
            ('standard1_disabled', 0, 1), ('standard2_disabled', 0, 2))
SCOPE = ('One actual VMFPU: unchanged full-FP positive gate in standard/shared '
         'configurations; standard EW8 latency 1/2 disables borrowing while native '
         'integer instructions complete. Top/VLSU selection is static only; no SoC '
         'execution, variable-latency borrowing, performance or new capacity claim.')


def compact(text):
    text = re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)
    return re.sub(r'\s+', '', text)


def audit_composition(texts):
    t = {name: compact(value) for name, value in texts.items()}
    pkg = t['hardware/include/ara_pkg.sv']
    required = ("`ifdefARA_SHARED_SIMD_MULlocalparambitQbsLaneMulLatencySupported=1'b1;"
                '`elselocalparambitQbsLaneMulLatencySupported=LatMultiplierEW8==0;`endif')
    if required not in pkg:
        raise ValueError('Package latency predicate is not tied to the selected core')
    guards = {
        'hardware/src/ara.sv': ('localparambitQbsLaneMulSupported=EnableQbsLaneMul&&'
            'qbs_pkg::QbsEnable&&NrLanes==4&&VLEN==1024&&QbsLaneMulLatencySupported;'),
        'hardware/src/vlsu/vlsu.sv': ('localparambitQbsLaneMulSupported=EnableQbsLaneMul&&'
            'NrLanes==4&&VLEN==1024&&QbsLaneMulLatencySupported;'),
    }
    for name, guard in guards.items():
        if guard not in t[name]:
            raise ValueError('Missing end-to-end selection guard: ' + name)
    if t['hardware/src/ara.sv'].count('.EnableQbsLaneMul(QbsLaneMulSupported)') != 2:
        raise ValueError('Ara must pass the same selection to lanes and VLSU')
    if '.CooperativeWaves(QbsLaneMulSupported)' not in t['hardware/src/vlsu/vlsu.sv']:
        raise ValueError('VLSU scheduler did not inherit the selection')
    v = t['hardware/src/lane/vmfpu.sv']
    for fragment in (
        'localparambitQbsLaneMulEnabled=EnableQbsLaneMul&&QbsLaneMulLatencySupported;',
        'assignqbs_mul_requested=QbsLaneMulEnabled&&qbs_mul_lease_i;',
        'if(QbsLaneMulEnabled)begin:gen_qbs_mul_borrow',
        'if(QbsLaneMulEnabled)begin:gen_qbs_mul_checks',
        "simd_mul_shared#(.FixPtSupport(FixPtSupport),.Bypass8(1'b1))i_shared_mul(",
        '.NumPipeRegs(LatMultiplierEW8),.ElementWidth(EW8)',
    ):
        if fragment not in v:
            raise ValueError('VMFPU core/guard composition changed: ' + fragment)
    if '.CooperativeWaves(CooperativeWaves)' not in t['hardware/src/vlsu/qbs/qbs_engine.sv']:
        raise ValueError('Engine did not forward cooperative selection')
    c = t['hardware/src/vlsu/qbs/qbs_compute_engine.sv']
    if ('assigncooperative_command=CooperativeWaves&&m_q==4\'d8&&' not in c or
            'if(wide_command&&!cooperative_command&&!context_wave_q)' not in c):
        raise ValueError('Original second-wave fallback is not selected')
    return dict(state='STATIC_COMPOSITION_CHECKED', top_vlsu_executed=False,
                standard_latency_0=True, standard_latency_1=False,
                standard_latency_2=False, shared_ew8_explicit_bypass=True)


def disabled_tb(original):
    marker = '  initial begin\n'
    if original.count(marker) != 1 or not original.rstrip().endswith('endmodule'):
        raise ValueError('Unexpected sealed integer TB structure')
    prefix = original.split(marker)[0]
    return prefix + r'''
  int disabled_cycles = 0, native_completions = 0, grant_stalls = 0;
  always @(posedge clk) if (rst) begin
    if (owned !== 1'b0 || borrow_ready !== 1'b0 || borrow_result_valid !== 1'b0 ||
        dut.qbs_mul_requested !== 1'b0 || dut.qbs_mul_issue !== 1'b0)
      $fatal(1, "Unsupported latency activated QBS borrowing");
    if (lease && borrow_valid) disabled_cycles++;
    if (|native_done) begin
      if (native_done !== (NrVInsn'(1) << operation.id))
        $fatal(1, "Wrong native completion identity");
      native_completions++;
    end
    if (native_result_valid && !native_grant) grant_stalls++;
  end

  initial begin
    operation = '0;
    if (!(LatMultiplierEW8 inside {1, 2}) || QbsLaneMulLatencySupported !== 1'b0 ||
        dut.EnableQbsLaneMul !== 1'b1 || dut.QbsLaneMulEnabled !== 1'b0 ||
        dut.i_simd_mul_ew8.NumPipeRegs != LatMultiplierEW8)
      $fatal(1, "Negative test did not elaborate the actual incompatible core");
    repeat (4) @(negedge clk);
    rst = 1;
    lease = 1;
    borrow_valid = 1;
    weight = 16'h8080;
    activation = 64'h8080808080808080;
    repeat (8) @(negedge clk);
    for (int sew = 0; sew < 4; sew++) native_case(sew, 0);
    for (int sew = 0; sew < 4; sew++) native_case(sew, 1);
    repeat (8) @(negedge clk);
    if (native_cases != 8 || native_written != 8 || native_completions != 8 ||
        borrowed != 0 || returned != 0 || cancelled != 0 ||
        disabled_cycles < 100 || grant_stalls < 8)
      $fatal(1, "Incomplete disabled-borrow/native-progress evidence");
    $display("STAGE2_VMFPU_CONFIG_DISABLED latency=%0d native=%0d writes=%0d dones=%0d blocked=%0d grant_stalls=%0d borrowed=%0d returned=%0d",
        LatMultiplierEW8, native_cases, native_written, native_completions,
        disabled_cycles, grant_stalls, borrowed, returned);
    $finish;
  end
endmodule
'''


def check_disabled(text, latency):
    if FP.ERROR.search(text):
        raise ValueError('Simulator error/fatal')
    rows = re.findall(r'^STAGE2_VMFPU_CONFIG_DISABLED (.*)$', text, re.M)
    if len(rows) != 1:
        raise ValueError('Missing/duplicate disabled terminal')
    match = re.fullmatch(r'latency=(\d+) native=(\d+) writes=(\d+) dones=(\d+) '
                         r'blocked=(\d+) grant_stalls=(\d+) borrowed=(\d+) returned=(\d+)', rows[0])
    if not match:
        raise ValueError('Malformed disabled accounting')
    keys = ('latency', 'native', 'writes', 'dones', 'blocked', 'grant_stalls', 'borrowed', 'returned')
    row = dict(zip(keys, map(int, match.groups())))
    if (latency not in (1, 2) or row['latency'] != latency or
            any(row[k] != 8 for k in ('native', 'writes', 'dones')) or
            row['blocked'] < 100 or row['grant_stalls'] < 8 or
            row['borrowed'] != 0 or row['returned'] != 0):
        raise ValueError('Disabled guard or native progress not covered')
    return row


def prepare(out):
    if out.parent != FP.OUT or out.exists() or not shutil.which('vcs'):
        raise ValueError('Require a new signoff output and host VCS')
    branch = subprocess.check_output(
        ['git', '-C', str(FP.OUT.parents[1]), 'branch', '--show-current'], text=True).strip()
    if branch != 'ara_dsa_signoff_integration':
        raise ValueError('Wrong verification worktree branch')
    FP.verify(FP.ADMISSION)
    receipt = json.loads((FP.ACCEPTED / 'report.json').read_text())
    if receipt['state'] != 'PASS' or not receipt['post_pins_match'] or not receipt['post_image_match']:
        raise ValueError('Frozen FP dependency admission failed')
    accepted = json.loads((FP.ACCEPTED / 'source-pins.json').read_text())
    sources = FP.dependencies(FP.FILELIST.read_text())
    out.mkdir()
    inputs = out / 'inputs'
    pins = dict(FP.ADMISSION)
    for rel in sources:
        source = (ROOT if rel in FP.OVERLAY else FP.FROZEN) / rel
        FP.copy_pin(source, inputs / rel, pins, None if rel in FP.OVERLAY else accepted[str(source)])
    for rel in STATIC:
        FP.copy_pin(ROOT / rel, inputs / rel, pins)
    headers = FP.FROZEN / 'hardware/deps/common_cells/include'
    for source in sorted(p for p in headers.rglob('*') if p.is_file()):
        FP.copy_pin(source, inputs / source.relative_to(FP.FROZEN), pins, accepted[str(source)])
    for name in OWN + REUSED:
        FP.copy_pin(HERE / name, inputs / name, pins)
    names = (*STATIC, 'hardware/include/ara_pkg.sv', 'hardware/src/lane/vmfpu.sv')
    audit = audit_composition({name: (inputs / name).read_text() for name in names})
    configs = []
    for name, shared, latency in VARIANTS:
        folder = inputs / name
        folder.mkdir()
        package = (inputs / 'hardware/include/ara_pkg.sv').read_text()
        package, count = re.subn(r'(localparam int unsigned LatMultiplierEW8\s*=\s*)0;',
                                 lambda m: m[1] + str(latency) + ';', package)
        if count != 1:
            raise ValueError('Package latency mutation did not match exactly once')
        (folder / 'ara_pkg.sv').write_text(package)
        tb = inputs / 'vmfpu_fp_tb.sv'
        top = 'stage2_vmfpu_fp_tb'
        if latency:
            tb = folder / 'disabled_tb.sv'
            tb.write_text(disabled_tb((inputs / 'vmfpu_tb.sv').read_text()))
            top = 'stage2_vmfpu_tb'
        selected = [folder / 'ara_pkg.sv' if rel == 'hardware/include/ara_pkg.sv'
                    else inputs / rel for rel in sources]
        filelist = folder / 'sources.f'
        filelist.write_text('+incdir+' + str(inputs / headers.relative_to(FP.FROZEN)) + '\n' +
                            '\n'.join(map(str, [*selected, tb])) + '\n')
        configs.append(dict(name=name, shared=shared, latency=latency, top=top,
                            filelist=str(filelist), tb=str(tb)))
        for path in folder.iterdir():
            pins[str(path)] = FP.sha(path)
    vcs = str(Path(shutil.which('vcs')).resolve())
    pins[vcs] = FP.sha(vcs)
    FP.save(out / 'config.json', dict(scope=SCOPE, branch=branch, configurations=configs, vcs=vcs,
                                     compile_seconds=600, run_seconds=120, static=audit))
    pins[str(out / 'config.json')] = FP.sha(out / 'config.json')
    FP.verify(pins)
    FP.save(out / 'source-pins.json', pins)
    FP.save(out / 'prepared.json', dict(state='PREPARED_NOT_EXECUTED', static=audit))
    print(out / 'inputs/run_vmfpu_config.py')


def execute(out):
    if Path(__file__).resolve() != out / 'inputs/run_vmfpu_config.py':
        raise ValueError('Execute frozen runner only')
    config = json.loads((out / 'config.json').read_text())
    pins = json.loads((out / 'source-pins.json').read_text())
    report = dict(state='FAIL', scope=SCOPE, static=config['static'], configurations=[],
                  source_pins_sha256=FP.sha(out / 'source-pins.json'))
    try:
        FP.verify(pins)
        cgroup = Path('/proc/self/cgroup').read_text()
        if '.service' not in cgroup:
            raise ValueError('Direct systemd owner required')
        FP.save(out / 'owner.json', dict(pid=os.getpid(), cgroup=cgroup))
        FP.save(out / 'status.json', dict(state='RUNNING', pid=os.getpid()))
        with (out / 'host.log').open('x') as stream:
            subprocess.run([sys.executable, '-B', str(out / 'inputs/test_run_vmfpu_config.py'), '-v'],
                           stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=30)
        report['host_log_sha256'] = FP.sha(out / 'host.log')
        for c in config['configurations']:
            work = out / c['name']
            work.mkdir()
            compile_cmd = [config['vcs'], '-full64', '-sverilog', '-timescale=1ns/1ps', '-j4',
                           '+define+SIMULATION', '-top', c['top'], '-o', 'simv', '-f', c['filelist']]
            if c['shared']:
                compile_cmd.append('+define+ARA_SHARED_SIMD_MUL')
            run_cmd = [str(work / 'simv'), '-no_save']
            FP.save(work / 'commands.json', dict(compile=compile_cmd, run=run_cmd))
            images = {}
            for label, command, limit in (('compile', compile_cmd, config['compile_seconds']),
                                           ('run', run_cmd, config['run_seconds'])):
                print('CONFIG_' + label.upper() + ' ' + c['name'], flush=True)
                with (work / (label + '.log')).open('x') as stream:
                    subprocess.run(['timeout', '--signal=TERM', '--kill-after=10s', str(limit),
                                    *command], cwd=work, stdout=stream, stderr=subprocess.STDOUT,
                                   check=True)
                FP.verify(pins)
                if FP.ERROR.search((work / (label + '.log')).read_text(errors='replace')):
                    raise ValueError('Tool error: ' + c['name'] + '/' + label)
                if label == 'compile':
                    images = {str(p): FP.sha(p) for p in (work / 'simv.daidir').rglob('*') if p.is_file()}
                    images[str(work / 'simv')] = FP.sha(work / 'simv')
                    FP.save(work / 'image-pins.json', images)
            FP.verify(images)
            text = (work / 'run.log').read_text()
            checked = check_disabled(text, c['latency']) if c['latency'] else FP.check(text)
            artifacts = {str(work / n): FP.sha(work / n) for n in
                         ('commands.json', 'compile.log', 'run.log', 'image-pins.json')}
            report['configurations'].append(dict(**c, checked=checked, artifacts=artifacts))
            FP.save(out / 'progress.json', report)
        FP.verify(pins)
        for c in report['configurations']:
            FP.verify(c['artifacts'])
            FP.verify(json.loads((out / c['name'] / 'image-pins.json').read_text()))
        report.update(state='PASS', source_pins_match=True, image_pins_match=True)
    except Exception as exc:
        report['error'] = str(exc)
    FP.save(out / 'report.json', report)
    FP.save(out / 'status.json', dict(state=report['state'], pid=os.getpid()))
    print('STAGE2_VMFPU_CONFIG_' + report['state'], flush=True)
    return int(report['state'] != 'PASS')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    p.add_argument('--execute', action='store_true')
    args = p.parse_args()
    if args.execute:
        return execute(args.output.resolve())
    prepare(args.output.resolve())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
