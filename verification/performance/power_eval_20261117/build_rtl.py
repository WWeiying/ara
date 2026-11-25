#!/usr/bin/env python3
"""Prepare DC-matched RTL preflight inputs; never compile during preparation.

Only DC attempt_03 supplies design RTL/dependencies (including its port-default
adapter). The operator build_soc.py BASE supplies frozen TB, DPI object/source,
and VCS options, NOT its production archive or four-file FPGA gate overlay.
Use prepare, then inspect rtl-receipt.json and plan.json. Future execute requires
the frozen worker and --authorize-compile, under a directly owning systemd service.
No simulations, coverage, GLS, or power reporting are dispatched here.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time

ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
DC = Path('/home/wangwy/dc_runs/ara_main_870cadb9_all_on_20261111_01/attempt_03')
DC_SOURCE = DC / 'sources/home/wangwy/openproject/ara_dsa_dc_20261110'
BASE = OUT / 'enablement_soc_resident_deployment_20261112_022423'
REVISION = '870cadb9f32c79df8d30ab845e4dd2e463a00540'
ANCHORS = {
    DC / 'source-pins.json': 'd9e6596f5e95e557a7955cabdb36d16d92de0cfb4a581ce3a77bbcf48afbd0e3',
    BASE / 'source-pins.json': '6f72deab767889eee7d2de0126c51721063da5970805884e683c2c7631e7cd46',
}
REMOVE = {
    'SYNTHESIS', 'TARGET_SYNTHESIS', 'TARGET_SRAM_BLACKBOX', 'TARGET_SRAM_MC',
    'TARGET_TECH_CELLS_GENERIC_EXCLUDE_TC_SRAM',
}
ADD = {'SIM_L2_SIZE_BYTES=1048576', 'FOR_VERIFY', 'TARGET_NOTSYNTHESIS'}
# Explicit simulation supplements only. Anything already frozen by DC wins.
SUPPORT = (
    'hardware/deps/common_verification/src/clk_rst_gen.sv',
    'hardware/deps/common_verification/src/sim_timeout.sv',
    'hardware/deps/common_verification/src/stream_watchdog.sv',
    'hardware/deps/common_verification/src/signal_highlighter.sv',
    'hardware/deps/tech_cells_generic/src/rtl/tc_sram.sv',
    'hardware/deps/tech_cells_generic/src/rtl/tc_sram_impl.sv',
    'hardware/deps/cva6/common/local/util/sram_cache.sv',
    'hardware/deps/cva6/common/local/util/sram_pulp.sv',
    'hardware/deps/cva6/core/include/instr_tracer_pkg.sv',
    'hardware/deps/cva6/common/local/util/instr_tracer.sv',
    'hardware/deps/cva6/core/cva6_rvfi.sv',
    'hardware/tb/ara_commit_monitor.sv',
    'hardware/tb/llm_perf_monitor.sv',
    'hardware/deps/cva6/corev_apu/tb/common/mock_uart.sv',
    'hardware/tb/ara_testharness.sv',
    'hardware/tb/ara_tb.sv',
    'hardware/tb/vrf_perf_monitor.sv',
)
UVM = tuple('verification/uvm/' + n + '.sv' for n in (
    'ara_cvxif_if', 'ara_cvxif_uvm_pkg', 'ara_acc_contract_monitor', 'ara_cvxif_dut_bind'))


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, sort_keys=True) + '\n')


def verify(pins):
    for path, expected in pins.items():
        require(sha(path) == expected, 'Source drift: ' + str(path))


def parse_filelist(text):
    defines, includes, sources = set(), [], []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('//'):
            continue
        if line.startswith('+define+'):
            defines.update(line[len('+define+'):].split('+'))
        elif line.startswith('+incdir+'):
            includes.extend(Path(p) for p in line[len('+incdir+'):].split('+'))
        else:
            require(line.startswith('/') and len(shlex.split(line)) == 1,
                    'Unsupported filelist entry: ' + line)
            sources.append(Path(line))
    return defines, list(dict.fromkeys(includes)), list(dict.fromkeys(sources))


def prepare(out):
    require(not out.exists(), 'Output must be new; no reuse or automatic retry')
    verify(ANCHORS)
    dc_pins, tb_pins = read(DC / 'source-pins.json'), read(BASE / 'source-pins.json')
    verify(dc_pins)
    meta = {str(BASE / n): tb_pins[str(BASE / n)]
            for n in ('plan.json', 'sources.f', 'inventory.json', 'elfloader.o')}
    verify(meta)
    manifest = read(DC / 'manifest.json')
    require(manifest['main_rtl_commit'] == REVISION and manifest['l2_mib'] == 1,
            'Wrong DC configuration')
    require(manifest['shared_fma'] and manifest['dc_adapter_files'] == 12,
            'Wrong DC FMA/adapter configuration')
    definitions, includes, design = parse_filelist((DC / 'backend/flist/ara_soc_dc.f').read_text())
    require(definitions == set(manifest['defines']), 'DC define inventory mismatch')
    require(REMOVE <= definitions, 'Missing synthesis selectors')
    functional = definitions - REMOVE
    require({'NR_LANES=4', 'VLEN=1024', 'ARA_SHARED_SIMD_MUL=1',
             'ARA_AKV_RESIDENT_PV_ENABLE=1', 'ARA_AKV_RESIDENT_QK_ENABLE=1',
             'ARA_QBS_LANE_MUL_ENABLE=1'} <= functional, 'Incomplete DC configuration')
    require(not any('IDEAL_DISPATCHER' in x for x in definitions), 'Ideal dispatcher')
    source_map = {str(Path(p).relative_to(DC_SOURCE)): h for p, h in dc_pins.items()
                  if Path(p).is_relative_to(DC_SOURCE)}
    require(source_map, 'Empty DC inventory')
    for p in design:
        require(str(p) in dc_pins, 'Unpinned DC design input: ' + str(p))
    adapter = read(DC / 'dc_port_defaults.json')
    require(len(adapter) == 12, 'Adapter count mismatch')
    for item in adapter:
        require(dc_pins[item['file']] == item['after_sha256'], 'Adapter identity mismatch')

    out.mkdir(parents=True)
    source, inputs = out / 'source', out / 'inputs'
    inputs.mkdir()
    (out / 'sim').mkdir()
    origins = {}

    def copy(src, dest, expected, role):
        require(sha(src) == expected, 'Unpinned input: ' + str(src))
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        require(sha(dest) == expected, 'Copy drift: ' + str(src))
        origins[str(dest.relative_to(out))] = dict(origin=str(src), sha256=expected, role=role)

    for rel, expected in source_map.items():
        copy(DC_SOURCE / rel, source / rel, expected, 'exact-DC-frozen-source')
    inventory = read(BASE / 'inventory.json')['source']

    def supplement(rel):
        if rel in source_map:
            return
        src = BASE / 'source' / rel
        expected = inventory[str(src)]
        require(tb_pins[str(src)] == expected, 'TB inventory/pin disagreement')
        copy(src, source / rel, expected, 'pinned-simulation-support-not-DC')

    for rel in (*SUPPORT, *UVM, 'hardware/tb/dpi/elfloader.cc',
                'hardware/deps/cva6/corev_apu/tb/dpi/elfloader.cc',
                'hardware/deps/cva6/common/local/util/ex_trace_item.svh',
                'hardware/deps/cva6/common/local/util/instr_trace_item.svh'):
        supplement(rel)
    copy(BASE / 'elfloader.o', out / 'elfloader.o', meta[str(BASE / 'elfloader.o')],
         'pinned-prebuilt-DPI-object')
    for name in ('loan.sv', 'fma.sv'):
        src = BASE / 'inputs' / name
        copy(src, inputs / name, tb_pins[str(src)], 'pinned-template-monitor')
    copy(Path(__file__), inputs / 'build_rtl.py', sha(__file__), 'frozen-worker')

    hooks = {
        'hardware/tb/ara_commit_monitor.sv': ('COMMIT_TRACE=%s', 'VECTOR_TRACE=%s'),
        'hardware/tb/llm_perf_monitor.sv': ('[LLM_PERF]',),
        'verification/uvm/ara_acc_contract_monitor.sv': ('ARA_CONTRACT_TRACE_LIMIT=%d', '[ARA_CONTRACT]'),
        'verification/uvm/ara_cvxif_uvm_pkg.sv': ('ARA_UVM_TRACE_LIMIT=%d',),
    }
    for rel, tokens in hooks.items():
        text = (source / rel).read_text()
        require(all(token in text for token in tokens), 'Missing trace/PERF hook: ' + rel)

    # DC ordering is retained; only macro blackboxes are omitted. Behavioral
    # SRAM and simulation-only modules follow; VCS resolves module references.
    compiled = [str(p.relative_to(DC_SOURCE)) for p in design
                if not p.is_relative_to(DC_SOURCE / 'backend/blackbox')]
    compiled = list(dict.fromkeys([*compiled, *SUPPORT]))
    inc = [source / p.relative_to(DC_SOURCE) for p in includes]
    inc.append(source / 'hardware/deps/cva6/common/local/util')
    for p in inc:
        require(p.is_dir(), 'Missing frozen include directory: ' + str(p))
    lines = ['+define+' + d for d in sorted(functional | ADD)]
    lines += ['+incdir+' + str(p) for p in dict.fromkeys(inc)]
    lines += [str(source / rel) for rel in compiled]
    (out / 'sources.f').write_text('\n'.join(lines) + '\n')
    oldplan = read(BASE / 'plan.json')
    command = [arg.replace(str(BASE), str(out)) for arg in oldplan['command']]
    # This selector already comes verbatim from the DC filelist.
    command = [arg for arg in command if arg != '+define+ARA_SHARED_SIMD_MUL']
    require('-R' not in command and '-top' in command and 'ara_tb' in command,
            'Unexpected template invocation')
    config = dict(oldplan['configuration'], config='power_eval_dc_870cadb9_all_on',
                  sim_l2_bytes=1048576)
    (out / 'sim/simulator.conf').write_text(''.join(f'{k}={v}\n' for k, v in sorted(config.items())))
    dc_compiled = {rel: source_map[rel] for rel in compiled if rel in source_map}
    receipt = dict(
        schema='power-eval-dc-matched-rtl-v1', dc_attempt=str(DC), revision=REVISION,
        dc_source_fingerprint=digest(source_map), dc_source_files=source_map,
        compiled_dc_fingerprint=digest(dc_compiled), compiled_dc_files=dc_compiled,
        adapter_journal_sha256=dc_pins[str(DC / 'dc_port_defaults.json')],
        adapter_files=12, dc_source_bytes_changed=0, current_rtl_used=False,
        fpga_gate_overlays_used=False, source_origins=origins,
        dc_defines=sorted(definitions), removed_defines=sorted(REMOVE),
        rtl_defines=sorted(functional | ADD), added_defines=sorted(ADD),
        memory=dict(bytes=1048576, width_bits=128, words=65536,
                    dc_banks=8, dc_bank_words=8192, behavioral_module='tc_sram',
                    preload_path='ara_tb.dut.i_ara_soc.i_dram.init_val'),
        scope='DC source identity with behavioral SRAM, not RTL/GLS equivalence or power acceptance',
        interface=dict(top='ara_tb', clock_period_ns=1, preload='+PRELOAD=/absolute/program.elf',
                       testcase='+TESTCASE=name', exit='exit[0]; exit >> 1 == 0 and SUCCESS log required',
                       runtime_arguments=['-no_save', '+NO_FSDB', '+NO_INSTR_TRACE',
                                          '+COMMIT_TRACE=/absolute/run/commit.csv',
                                          '+VECTOR_TRACE=/absolute/run/vector.csv',
                                          '+ARA_CONTRACT_TRACE_LIMIT=2000000',
                                          '+ARA_UVM_TRACE_LIMIT=2000000'],
                       perf_report='llm_perf_report_<TESTCASE>.log; [LLM_PERF] records',
                       required_gates=['SUCCESS log with no fatal/error/assertion failures',
                                       'independent numerical/work/guard checker PASS',
                                       'nonempty commit/vector traces matching ELF and image',
                                       'independent UVM DUT protocol proof: events/backend/AXI/read/write',
                                       'zero contract exceptions/protocol_errors/outstanding',
                                       'PERF counters consistent with selected program ROI'],
                       dpi=['read_elf', 'get_section', 'read_section'],
                       dpi_object_sha256=sha(out / 'elfloader.o')),
        caveats=[
            'Behavioral SRAM replaces macro configuration; no gate delays, macro power, or SDF.',
            'Removing SYNTHESIS enables simulation/debug/assertion code; no equivalence claim.',
            'Pinned SV read_section returns byte but C++ returns void; return is discarded; unchanged.',
            'No CPU commit-stage or FPGA gate overlay from the template is applied.',
            'TB permits high-window stack alias; ELF preload must fit low 1 MiB.',
            'External runner must impose timeout and independently check results; exit code alone is insufficient.',
        ],
        campaign=dict(max_rtl_prechecks=4, rtl_prechecks_run=0, subsequent_gls_programs=4,
                      program_selection='owned by campaign; not dispatched by builder'))
    save(out / 'rtl-receipt.json', receipt)
    plan = dict(command=command, environment=oldplan['environment'], configuration=config,
                cwd=str(out / 'sim'), compile_seconds=7200, automatic_retry=False,
                dependency_template=str(BASE), dc_attempt=str(DC),
                receipt_sha256=sha(out / 'rtl-receipt.json'), compilation_authorized=False)
    save(out / 'plan.json', plan)
    # Ready command only: service directly owns the frozen worker, which waits
    # for VCS. A short launcher with detached children must not own this job.
    worker = ['/usr/bin/python3', str(inputs / 'build_rtl.py'), 'execute',
              '--output', str(out), '--authorize-compile']
    service = ['systemd-run', '--user', '--unit=' + out.name, '--property=Type=exec',
               '--property=RuntimeMaxSec=7800',
               '--property=StandardOutput=append:' + str(out / 'service.stdout.log'),
               '--property=StandardError=append:' + str(out / 'service.stderr.log'), *worker]
    save(out / 'ready-command.json', dict(vcs=command, service=service,
                                        shell=shlex.join(service), launched=False))
    pins = {str(p): sha(p) for p in out.rglob('*') if p.is_file()}
    pins.update({str(p): h for p, h in ANCHORS.items()})
    save(out / 'source-pins.json', pins)
    verify(pins)
    save(out / 'status.json', dict(state='PREPARED_NOT_COMPILED', cases_run=0))
    return receipt


def execute(out, authorized):
    require(authorized, 'Compilation requires explicit --authorize-compile')
    require(Path(__file__).resolve() == out / 'inputs/build_rtl.py', 'Use frozen worker')
    require(not (out / 'attempt.json').exists(), 'No retry in this output')
    pins, plan = read(out / 'source-pins.json'), read(out / 'plan.json')
    verify(pins)
    with (out / 'attempt.json').open('x') as stream:
        json.dump(dict(pid=os.getpid(), started=time.time()), stream)
    report = dict(state='FAIL', cases_run=0, scope='Compile only; no functional/power acceptance')
    try:
        with (out / 'compile.log').open('x') as stream:
            with subprocess.Popen(plan['command'], cwd=plan['cwd'], env=plan['environment'],
                                  stdout=stream, stderr=subprocess.STDOUT) as proc:
                save(out / 'status.json', dict(state='VCS_COMPILING', child_pid=proc.pid))
                try:
                    rc = proc.wait(timeout=plan['compile_seconds'])
                except BaseException:
                    proc.kill()
                    proc.wait()
                    raise
        require(rc == 0, 'VCS exit ' + str(rc))
        require(not re.search(r'(?m)^\s*(?:Error-|Fatal-|Error:|Fatal:)',
                              (out / 'compile.log').read_text(errors='replace')), 'VCS errors')
        verify(pins)
        image = {str(p): sha(p) for p in (out / 'sim/simv.daidir').rglob('*') if p.is_file()}
        image[str(out / 'sim/simv')] = sha(out / 'sim/simv')
        save(out / 'image-pins.json', image)
        report.update(state='DC_MATCHED_RTL_BUILT_NOT_EXECUTED', image_pins=image,
                      rtl_receipt_sha256=plan['receipt_sha256'])
    except Exception as exc:
        report['error'] = repr(exc)
    save(out / 'build.json', report)
    save(out / 'status.json', dict(state=report['state'], finished=time.time()))
    print(json.dumps(report))
    return int(report['state'] == 'FAIL')


def self_test():
    assert parse_filelist('+define+A\n+define+A\n+incdir+/tmp\n/tmp/a.sv\n/tmp/a.sv')[0] == {'A'}
    assert len(parse_filelist('/tmp/a.sv\n/tmp/a.sv')[2]) == 1
    try:
        parse_filelist('-f live.f')
    except ValueError:
        pass
    else:
        raise AssertionError('Nested filelist accepted')
    assert digest({'a': 1, 'b': 2}) == digest({'b': 2, 'a': 1})
    assert 'ARA_SHARED_SIMD_MUL=1' not in REMOVE
    assert 8 * 8192 * 128 // 8 == 1048576
    try:
        execute(Path('/nonexistent'), False)
    except ValueError:
        pass
    else:
        raise AssertionError('Unauthorized execution accepted')
    print('HOST_SELF_TEST_PASS (no EDA invoked)')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'check', 'execute', 'self-test'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--authorize-compile', action='store_true')
    args = parser.parse_args()
    if args.action == 'self-test':
        self_test()
        return 0
    require(args.output is not None, '--output is required')
    out = args.output.resolve()
    require(out.parent == OUT and out.name.startswith('power_rtl_20261117_'), 'Wrong output scope')
    if args.action == 'execute':
        return execute(out, args.authorize_compile)
    require(not args.authorize_compile, 'Authorization only applies to execute')
    if args.action == 'prepare':
        receipt = prepare(out)
        print(json.dumps(dict(state='PREPARED_NOT_COMPILED', output=str(out),
                              dc_source_fingerprint=receipt['dc_source_fingerprint'])))
    else:
        verify(read(out / 'source-pins.json'))
        print('PIN_CHECK_PASS (no EDA invoked)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
