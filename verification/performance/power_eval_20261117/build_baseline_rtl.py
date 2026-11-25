#!/usr/bin/env python3
"""Freeze the reconstructed no-QBS baseline and prepare, but do not run, VCS.

Historical source byte identity is UNPROVEN. Only a later explicitly authorized
execute of the frozen worker can compile. No action dispatches simulations,
synthesis, GLS, coverage, SAIF conversion, or power analysis.
"""

import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path('/home/wangwy/openproject/ara_dsa')
N = ROOT.parent / 'ara_dsa_no_qbs_pulp_eval'
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
DEFAULT_OUT = OUT / 'power_rtl_20261117_baseline_01'
BASE = OUT / 'enablement_soc_resident_deployment_20261112_022423'
BASE_PIN_SHA = '6f72deab767889eee7d2de0126c51721063da5970805884e683c2c7631e7cd46'
TOOL_UVM = Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/etc/uvm-1.2')
REVISION = 'd0c7d62d3be3c6c05f320252b95d65f0ca0a323a'
SYN = Path('backend/syn/ara_soc/v1-dc')
DC_FLIST = Path('backend/flist/ara_soc_dc.f')
SIM_FLIST = Path('hardware/build_pulp_vector_eval/vcs/bender_script_default')
EXPECTED_ARTIFACTS = {
    'ara_soc_dc.v': '113e08053dab899b1e2a646e936218068d8cfbffb80c26b0b3a92a5d21364d7b',
    'ara_soc_dc.ddc': '2eea3c4a4ac10dcaac37d62514d1d6dcc43f916c93b48ecb11838cf51f3e45d5',
}
RTL_DIFF_SHA = '4adb6f8930b29547cf8ce0abe396d43404c88fd0948e0a74469ee5716eec7425'
REMOVE = {
    'SYNTHESIS', 'TARGET_SYNTHESIS', 'TARGET_SRAM_BLACKBOX', 'TARGET_SRAM_MC',
    'TARGET_TECH_CELLS_GENERIC_EXCLUDE_TC_SRAM', 'HPDCACHE_ASSERT_OFF',
}
ADD = {'FOR_VERIFY', 'TARGET_NOTSYNTHESIS', 'SIM_L2_SIZE_BYTES=1048576'}
UVM = tuple('verification/uvm/' + name + '.sv' for name in (
    'ara_cvxif_if', 'ara_cvxif_uvm_pkg', 'ara_acc_contract_monitor', 'ara_cvxif_dut_bind'))
BUILT = 'RECONSTRUCTED_BASELINE_RTL_BUILT_NOT_EXECUTED'
TB = Path('hardware/tb/ara_tb.sv')
INCLUDE = re.compile(r'^\s*`include\s+"([^"\n]+)"', re.MULTILINE)
INACTIVE_PITON = re.compile(
    r'(?m)^`ifdef PITON_ARIANE\n(?:`include "(?:l15|define)\.tmp\.h"\n)+`endif')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, data):
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')


def verify(pins):
    for name, expected in pins.items():
        require(sha(name) == expected, 'Input drift: ' + str(name))


def git(*args):
    return subprocess.check_output(
        ['git', '-C', str(N), *args], env=dict(os.environ, GIT_OPTIONAL_LOCKS='0'),
        timeout=120)


def parse_filelist(text):
    defines, includes, sources = set(), [], []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('//'):
            continue
        if line.startswith('+define+'):
            defines.update(line[8:].split('+'))
        elif line.startswith('+incdir+'):
            includes.extend(Path(p) for p in line[8:].split('+'))
        else:
            require(line.startswith('/') and len(shlex.split(line)) == 1,
                    'Unsupported filelist entry: ' + line)
            sources.append(Path(line))
    require(all(p.is_absolute() for p in includes), 'Relative include path')
    require(all(re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*(?:=[A-Za-z_0-9]+)?', d)
                for d in defines), 'Unsupported define')
    return defines, list(dict.fromkeys(includes)), list(dict.fromkeys(sources))


def validate_defines(defines):
    require({'NR_LANES=4', 'VLEN=1024', 'ARIANE_ACCELERATOR_PORT=1',
             'TARGET_CV64A6_IMAFDCV_SV39'} <= defines, 'Wrong baseline configuration')
    require(not any(re.search(r'QBS|AKV|IDEAL|SHARED|PITON', d) for d in defines),
            'Unexpected accelerator/ideal/shared selector')
    for key, expected in (('NR_LANES', '4'), ('VLEN', '1024')):
        require({d for d in defines if d.split('=')[0] == key} == {key + '=' + expected},
                'Conflicting parameter: ' + key)


def tb_supplement(text):
    # These are TB-only changes. Keep the preserved historical file untouched.
    require('`ifndef ARA_NO_FSDB' not in text and 'repeat (5) @(posedge clk);' not in text,
            'TB supplement already applied')
    start = '    if (!$test$plusargs("NO_FSDB")) begin\n'
    stop = '      $fsdbDumpvars("+all");\n    end\n'
    require(text.count(start) == text.count(stop) == 1, 'Unknown baseline FSDB hook')
    text = text.replace(start, '`ifndef ARA_NO_FSDB\n' + start)
    text = text.replace(stop, stop + '`endif\n')
    finish = '      $finish(exit >> 1);'
    require(text.count(finish) == 1, 'Unknown baseline EOC hook')
    text = text.replace(finish, '      repeat (5) @(posedge clk);\n' + finish)
    return text


def validate_decoder(source):
    package = (source / 'hardware/deps/cva6/core/include/ariane_pkg.sv').read_text()
    decoder = (source / 'hardware/src/cva6_accel_first_pass_decoder.sv').read_text()
    require(re.search(r'localparam\s+REG_ADDR_SIZE\s*=\s*5\s*;', package),
            'Baseline must retain ordinary 32-register decoding')
    require('riscv::OpcodeVec:' in decoder and 'instr_scalar.rtype.rs1' in decoder,
            'Missing ordinary RVV decoder')
    require(not re.search(r'QBS|AKV|OpcodeCustom|OPCODE_CUSTOM', decoder),
            'Unexpected custom decoder')
    require(not re.search(r'QBS|AKV', (source / 'hardware/src/ara_dispatcher.sv').read_text()),
            'Unexpected custom Ara dispatcher')
    return dict(gpr_count=32, register_address_bits=5, custom_qbs_akv_decode=False,
                decoder_sha256=sha(source / 'hardware/src/cva6_accel_first_pass_decoder.sv'))


def include_closure(sources, includes):
    """Freeze full include directories plus transitively referenced local headers."""
    files = set(sources)
    for folder in includes:
        require(folder.is_dir(), 'Missing include directory: ' + str(folder))
        files.update(p for p in folder.rglob('*') if p.is_file())
    # VCS searches its working directory and explicit -I paths, not the host's
    # source tree. Include source parents to make relative header lookup explicit.
    search = list(dict.fromkeys([*includes, *(p.parent for p in sources)]))
    pending, scanned, edges = list(sources), set(), []
    while pending:
        p = pending.pop()
        if p in scanned or p.suffix not in ('.sv', '.svh', '.v', '.vh', '.h'):
            continue
        scanned.add(p)
        text = p.read_text(errors='strict')
        # The preserved CVA6 package has two generated OpenPiton headers that
        # do not exist in this configuration. Recognize only this exact block;
        # all other missing/nonliteral includes still fail closed.
        for block in INACTIVE_PITON.findall(text):
            edges.append(dict(source=str(p), inactive_guard='PITON_ARIANE',
                              includes=INCLUDE.findall(block), candidates=[]))
            text = text.replace(block, '')
        for line in text.splitlines():
            if re.match(r'^\s*`include\b', line):
                require(INCLUDE.match(line), 'Nonliteral include needs explicit inventory: ' + str(p))
        for name in INCLUDE.findall(text):
            header = Path(name)
            require(not header.is_absolute() and '..' not in header.parts,
                    'Unsafe include: ' + name)
            matches = [d / name for d in search if (d / name).is_file()]
            require(matches, 'Unresolved include ' + name + ' in ' + str(p))
            # Freeze every candidate, so ambiguous include precedence is visible.
            edges.append(dict(source=str(p), include=name, candidates=list(map(str, matches))))
            for found in matches:
                files.add(found)
                if found not in scanned:
                    pending.append(found)
    return files, search, edges


def prepare(out, jobs):
    require(1 <= jobs <= 4, 'Host VCS jobs must be 1..4')
    require(not out.exists(), 'Output must be fresh; no overwrite or automatic retry')
    require(git('rev-parse', 'HEAD').decode().strip() == REVISION, 'Baseline HEAD drift')
    rtl_diff = git('diff', '--no-ext-diff', '--', 'hardware/src')
    require(hashlib.sha256(rtl_diff).hexdigest() == RTL_DIFF_SHA, 'Audited RTL delta drift')
    dirty = git('diff', '--binary', '--no-ext-diff', 'HEAD', '--')
    status = git('status', '--porcelain=v1', '--untracked-files=no')
    dc_def, dc_inc, design = parse_filelist((N / DC_FLIST).read_text())
    sim_def, sim_inc, simulation = parse_filelist((N / SIM_FLIST).read_text())
    validate_defines(dc_def)
    validate_defines(sim_def)
    require({'SYNTHESIS', 'TARGET_SRAM_MC', 'TARGET_SYNTHESIS'} <= dc_def,
            'Synthesis configuration incomplete')
    blackboxes = {p for p in design if p.is_relative_to(N / 'backend/blackbox')}
    require(len(blackboxes) == 5, 'Unexpected macro inventory')
    require(set(design) - blackboxes <= set(simulation), 'Simulation omits baseline design')
    functional = (dc_def - REMOVE) | ADD
    require((sim_def - functional) <= {
        'TARGET_ARA_TEST', 'TARGET_CVA6_TEST', 'TARGET_VERILATOR'}, 'Unexpected simulation selectors')
    # Retain the old recipe's package/module order and all its simulation support.
    functional |= sim_def - {'TARGET_VERILATOR'}
    validate_defines(functional)
    require(not functional & REMOVE, 'Leaked synthesis/macro selector')
    for name, expected in EXPECTED_ARTIFACTS.items():
        require(sha(N / SYN / 'outputs' / name) == expected, 'Baseline artifact drift: ' + name)
    require(sha(BASE / 'source-pins.json') == BASE_PIN_SHA, 'Pinned support inventory drift')
    support_pins = read(BASE / 'source-pins.json')
    support_files = [BASE / 'plan.json', BASE / 'elfloader.o',
                     *(BASE / 'source' / rel for rel in UVM)]
    verify({str(p): support_pins[str(p)] for p in support_files})
    old_plan = read(BASE / 'plan.json')
    files, include_dirs, edges = include_closure(
        list(dict.fromkeys([*design, *simulation])),
        list(dict.fromkeys([*dc_inc, *sim_inc, TOOL_UVM / 'src', TOOL_UVM / 'verdi'])))
    for p in files:
        require(p.is_relative_to(N) or p.is_relative_to(TOOL_UVM),
                'Source outside inventoried roots: ' + str(p))
    metadata = [Path('Bender.yml'), Path('Bender.lock'), Path('hardware/Makefile'),
                Path('config/default.mk'), DC_FLIST, SIM_FLIST,
                Path('backend/flist/ara_soc.f'), Path('backend/flist/defines.temp'),
                SYN / 'global_scripts/dc.tcl', SYN / 'global_scripts/synopsys_dc.setup.gui',
                SYN / 'global_scripts/synopsys_dc.setup.env', SYN / 'local_scripts/ara_soc.sdc',
                SYN / 'run/dc.out.4', SYN / 'run/ara_soc.svf.4', SYN / 'run/filenames.log',
                SYN / 'reports/qor.rpt', SYN / 'outputs/ara_soc_dc.sdc']
    files.update(N / rel for rel in metadata)
    files.update(N / SYN / 'outputs' / name for name in EXPECTED_ARTIFACTS)

    out.mkdir(parents=True)
    source, inputs, supplement = out / 'source', out / 'inputs', out / 'supplement'
    inputs.mkdir()
    supplement.mkdir()
    (out / 'sim/incremental_db').mkdir(parents=True)
    origins = {}

    def copy(src, dst, role, expected=None):
        before, info = sha(src), src.stat()
        require(expected is None or before == expected, 'Input identity mismatch: ' + str(src))
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        require(sha(src) == sha(dst) == before, 'Input changed while freezing: ' + str(src))
        origins[str(dst.relative_to(out))] = dict(
            origin=str(src), resolved_origin=str(src.resolve()), sha256=before,
            size=info.st_size, mtime_ns=info.st_mtime_ns, role=role)

    def frozen_path(p):
        if p.is_relative_to(N):
            return source / p.relative_to(N)
        require(p.is_relative_to(TOOL_UVM), 'Unknown frozen root: ' + str(p))
        return source / 'tool-support/uvm-1.2' / p.relative_to(TOOL_UVM)

    for p in sorted(files):
        copy(p, frozen_path(p), 'reconstructed-baseline-input' if p.is_relative_to(N)
             else 'VCS-UVM-tool-header-support')
    (inputs / 'dirty.patch').write_bytes(dirty)
    (inputs / 'rtl-only.patch').write_bytes(rtl_diff)
    (inputs / 'git-status.txt').write_bytes(status)
    require(git('diff', '--binary', '--no-ext-diff', 'HEAD', '--') == dirty,
            'Dirty tree changed during freeze')
    for rel in UVM:
        p = BASE / 'source' / rel
        copy(p, source / rel, 'pinned-passive-protocol-supplement', support_pins[str(p)])
    copy(BASE / 'elfloader.o', out / 'elfloader.o', 'pinned-prebuilt-DPI-object',
         support_pins[str(BASE / 'elfloader.o')])
    copy(BASE / 'plan.json', inputs / 'support-plan.json', 'pinned-host-environment-reference',
         support_pins[str(BASE / 'plan.json')])
    copy(BASE / 'source-pins.json', inputs / 'support-source-pins.json',
         'support-provenance-reference', BASE_PIN_SHA)
    # Preserve DPI source evidence without using the newer template's RTL/types.
    for rel in ('hardware/tb/dpi/elfloader.cc',
                'hardware/deps/cva6/corev_apu/tb/dpi/elfloader.cc'):
        p = BASE / 'source' / rel
        copy(p, supplement / rel, 'pinned-DPI-source-reference', support_pins[str(p)])
    copy(Path(__file__).resolve(), inputs / 'build_baseline_rtl.py', 'frozen-worker')

    original_tb = (source / TB).read_text()
    new_tb = tb_supplement(original_tb)
    (supplement / 'ara_tb.sv').write_text(new_tb)
    (inputs / 'tb-supplement.patch').write_text(''.join(difflib.unified_diff(
        original_tb.splitlines(keepends=True), new_tb.splitlines(keepends=True),
        fromfile='source/' + str(TB), tofile='supplement/ara_tb.sv')))
    decoder = validate_decoder(source)
    for rel, tokens in {
        'hardware/tb/ara_commit_monitor.sv': ('COMMIT_TRACE=%s', 'VECTOR_TRACE=%s'),
        'hardware/tb/llm_perf_monitor.sv': ('[LLM_PERF]',),
        'hardware/tb/ara_tb.sv': ('perf_time_q', 'hw_cnt_en_o', 'L2SizeBytes = 1 << 20;'),
        'hardware/src/ara_sequencer.sv': ('verify_vinsn_alloc', 'verify_vinsn_done'),
    }.items():
        require(all(t in (source / rel).read_text() for t in tokens), 'Missing hook: ' + rel)
    compiled = [supplement / 'ara_tb.sv' if p == N / TB else source / p.relative_to(N)
                for p in simulation]
    include_dirs = list(dict.fromkeys(frozen_path(p) for p in include_dirs))
    require(all(p.is_dir() for p in include_dirs), 'Unfrozen include directory')
    lines = ['+define+' + d for d in sorted(functional)]
    lines += ['+incdir+' + str(p) for p in include_dirs]
    lines += list(map(str, compiled))
    (out / 'sources.f').write_text('\n'.join(lines) + '\n')
    command = [old_plan['command'][0], '-full64', '-sverilog', '+v2k',
               '-Mlib=./incremental_db', '-Mupdate', '-j' + str(jobs), '-lca',
               '+nospecify', '+notimingchecks', '+lint=TFIPC-L', '+vpi', '+lint=PCWM',
               '+error+30', '-ntb_opts', 'uvm-1.2', '-top', 'ara_tb',
               '-timescale=1ns/100fs', '+define+SIMULATION', '+define+no_warning',
               '+define+ARA_NO_FSDB', '+define+ARA_VERIFY_UVM_CVXIF',
               '-f', str(out / 'sources.f'), str(out / 'elfloader.o'),
               *(str(source / rel) for rel in UVM), '-l', 'comp.vcs.log']
    require('-R' not in command, 'Simulation dispatch forbidden')
    config = dict(schema_version=1, config='reconstructed_no_qbs_c910_baseline',
                  nr_lanes=4, vlen=1024, sim_l2_bytes=1048576, qbs_enabled=0,
                  akv_enabled=0, akv_v2_enabled=0, ideal_dispatcher=0,
                  shared_simd_multiplier=0, shared_fma=0)
    (out / 'sim/simulator.conf').write_text(''.join(f'{k}={v}\n' for k, v in sorted(config.items())))
    frozen = {str(p.relative_to(source)): sha(p) for p in source.rglob('*') if p.is_file()}
    receipt = dict(
        schema='power-eval-reconstructed-baseline-rtl-v1', revision=REVISION,
        baseline_source_root=str(N), historical_byte_identity='UNPROVEN',
        reconstructed=True, historically_sealed=False, rtl_design_bytes_changed=0,
        source_fingerprint=digest(frozen), source_files=frozen, source_origins=origins,
        rtl_diff_sha256=sha(inputs / 'rtl-only.patch'), dirty_patch_sha256=sha(inputs / 'dirty.patch'),
        artifact_hashes={name: sha(source / SYN / 'outputs' / name) for name in EXPECTED_ARTIFACTS},
        synthesis_filelist=str(source / DC_FLIST), simulation_recipe=str(source / SIM_FLIST),
        compiled_sources=list(map(str, compiled)), include_search=list(map(str, include_dirs)),
        dc_defines=sorted(dc_def), rtl_defines=sorted(functional), decoder=decoder,
        support_template=str(BASE), newer_template_design_or_types_used=False,
        support_roles=['passive UVM/contract monitors', 'DPI object/source', 'host VCS environment'],
        tb=dict(origin=str(N / TB), selected=str(supplement / 'ara_tb.sv'),
                reason='Corresponding baseline hierarchy, counters, preload and trace types',
                original_sha256=sha(source / TB), supplement_sha256=sha(supplement / 'ara_tb.sv'),
                changes=['Compile-time FSDB exclusion', 'Five-cycle monitor drain before EOC']),
        memory=dict(bytes=1048576, width_bits=128, words=65536, dc_banks=8,
                    dc_bank_words=8192, behavioral_module='tc_sram',
                    preload_path='ara_tb.dut.i_ara_soc.i_dram.init_val'),
        interface=dict(top='ara_tb', clock_period_ns=1, preload='+PRELOAD=/absolute/program.elf',
                       testcase='+TESTCASE=name', runtime_arguments=[
                           '-no_save', '+NO_FSDB', '+COMMIT_TRACE=/absolute/run/commit.csv',
                           '+VECTOR_TRACE=/absolute/run/vector.csv',
                           '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000'],
                       perf_report='llm_perf_report_<TESTCASE>.log',
                       required_gates=['Independent per-case numeric/work/guard PASS',
                                       'Core SUCCESS and no fatal/error/assertion failures',
                                       'Nonempty ELF/image-matched commit and vector traces',
                                       'Independent per-case protocol PASS with events/backend/AXI/read/write',
                                       'Zero contract exceptions, protocol_errors and outstanding',
                                       'Ordinary RVV execution only; no QBS/AKV/custom opcodes',
                                       'ELF/preload and stack bounds checked against 1 MiB',
                                       'Explicit ROI markers and counters consistent with workload']),
        campaign=dict(max_parallel=4, cases_run=0, dispatches_prechecks=False),
        scope='Reconstructed baseline RTL compile only; not sealed historical identity, equivalence, or power acceptance',
        caveats=['No synthesis-time source hashes survived; mtimes and paths are corroboration only.',
                 'Snapshot includes current preserved dependency/header bytes, not historically proven bytes.',
                 'SYNTHESIS/macro selectors removed; behavioral SRAM and FOR_VERIFY probes enabled.',
                 'Passive monitors imported from pinned newer support; compatibility is not compile-proven yet.',
                 'Old CVA6 instruction tracer remains unchanged; NO_INSTR_TRACE is not promised.',
                 'DPI object reused unchanged; SV read_section byte/C++ void return mismatch remains.',
                 'Only successor precheck runner may accept this reconstruction with explicit acknowledgement.'])
    save(out / 'include-closure.json', edges)
    save(out / 'rtl-receipt.json', receipt)
    save(out / 'precheck-contract.json', dict(
        allowed_build_state=BUILT, requires_explicit_reconstruction_acceptance=True,
        historical_byte_identity='UNPROVEN', max_parallel=4,
        required_gates=receipt['interface']['required_gates'], cases_run=0))
    plan = dict(command=command, environment=old_plan['environment'], configuration=config,
                cwd=str(out / 'sim'), compile_seconds=7200, host_jobs=jobs,
                compilation_authorized=False, automatic_retry=False,
                receipt_sha256=sha(out / 'rtl-receipt.json'))
    save(out / 'plan.json', plan)
    worker = ['/usr/bin/python3', '-B', str(inputs / 'build_baseline_rtl.py'), 'execute',
              '--output', str(out), '--authorize-compile', '--acknowledge-reconstruction']
    service = ['systemd-run', '--user', '--unit=' + out.name, '--property=Type=exec',
               '--property=KillMode=control-group', '--property=CPUQuota=400%',
               '--property=RuntimeMaxSec=7800',
               '--property=StandardOutput=append:' + str(out / 'service.stdout.log'),
               '--property=StandardError=append:' + str(out / 'service.stderr.log'), *worker]
    save(out / 'ready-command.json', dict(service=service, shell=shlex.join(service),
                                        vcs=command, launched=False))
    # The execution identity is self-contained. Live origins are provenance, not
    # future execution inputs; never force a consumer to use changing dependencies.
    pins = {str(p): sha(p) for p in out.rglob('*') if p.is_file()}
    save(out / 'source-pins.json', pins)
    verify(pins)
    verify({entry['origin']: entry['sha256'] for entry in origins.values()})
    save(out / 'status.json', dict(state='PREPARED_NOT_COMPILED', cases_run=0,
                                  historical_byte_identity='UNPROVEN'))
    return receipt


def execute(out, authorized, acknowledged):
    require(authorized and acknowledged,
            'Require --authorize-compile and --acknowledge-reconstruction')
    require(Path(__file__).resolve() == out / 'inputs/build_baseline_rtl.py', 'Use frozen worker')
    require(not (out / 'attempt.json').exists(), 'No retry in this output')
    pins, plan = read(out / 'source-pins.json'), read(out / 'plan.json')
    verify(pins)
    require(1 <= plan['host_jobs'] <= 4, 'Host compile budget')
    require('-R' not in plan['command'], 'Simulation dispatch forbidden')
    with (out / 'attempt.json').open('x') as stream:
        json.dump(dict(pid=os.getpid(), started=time.time(), acknowledged_reconstruction=True), stream)
    report = dict(state='FAIL', cases_run=0, historical_byte_identity='UNPROVEN',
                  scope='Reconstructed compile only; no functional, GLS or power acceptance')
    try:
        with (out / 'compile.log').open('x') as stream:
            with subprocess.Popen(plan['command'], cwd=plan['cwd'], env=plan['environment'],
                                  stdout=stream, stderr=subprocess.STDOUT,
                                  start_new_session=True) as proc:
                save(out / 'status.json', dict(state='VCS_COMPILING', child_pid=proc.pid))
                try:
                    rc = proc.wait(timeout=plan['compile_seconds'])
                except BaseException:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                    raise
        require(rc == 0, 'VCS exit ' + str(rc))
        require(not re.search(r'(?m)^\s*(?:Error-|Fatal-|Error:|Fatal:)',
                              (out / 'compile.log').read_text(errors='replace')), 'VCS errors')
        verify(pins)
        image = {str(p): sha(p) for p in (out / 'sim/simv.daidir').rglob('*') if p.is_file()}
        require(image, 'Missing VCS image sidecars')
        image[str(out / 'sim/simv')] = sha(out / 'sim/simv')
        save(out / 'image-pins.json', image)
        report.update(state=BUILT, image_pins=image, rtl_receipt_sha256=plan['receipt_sha256'])
    except Exception as exc:
        report['error'] = repr(exc)
    save(out / 'build.json', report)
    save(out / 'status.json', dict(state=report['state'], finished=time.time()))
    print(json.dumps(report))
    return int(report['state'] == 'FAIL')


class HostTests(unittest.TestCase):
    def test_filelist(self):
        d, inc, src = parse_filelist('+define+A\n+define+A\n+incdir+/tmp\n/tmp/a.sv\n/tmp/a.sv')
        self.assertEqual((d, inc, src), ({'A'}, [Path('/tmp')], [Path('/tmp/a.sv')]))
        for bad in ('-f live.f', 'relative.sv', '+incdir+relative', '+define+A;bad'):
            with self.assertRaises(ValueError):
                parse_filelist(bad)

    def test_configuration(self):
        good = {'NR_LANES=4', 'VLEN=1024', 'ARIANE_ACCELERATOR_PORT=1',
                'TARGET_CV64A6_IMAFDCV_SV39'}
        validate_defines(good)
        for extra in ('ARA_QBS_ENABLE=0', 'ARA_AKV_ENABLE=1', 'IDEAL_DISPATCHER', 'NR_LANES=8'):
            with self.assertRaises(ValueError):
                validate_defines(good | {extra})

    def test_supplement_is_tb_only(self):
        old = ('    if (!$test$plusargs("NO_FSDB")) begin\n'
               '      $fsdbDumpvars("+all");\n    end\n      $finish(exit >> 1);')
        new = tb_supplement(old)
        self.assertIn('`ifndef ARA_NO_FSDB', new)
        self.assertIn('repeat (5) @(posedge clk);', new)
        with self.assertRaises(ValueError):
            tb_supplement(new)

    def test_include_closure(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / 'inc').mkdir()
            (root / 'a.sv').write_text('`include "b.svh"\n')
            (root / 'inc/b.svh').write_text('`include "c.svh"\n')
            (root / 'inc/c.svh').write_text('// header\n')
            files, _, edges = include_closure([root / 'a.sv'], [root / 'inc'])
            self.assertEqual(len(files), 3)
            self.assertEqual(len(edges), 2)
            (root / 'a.sv').write_text('`include "missing.svh"\n')
            with self.assertRaises(ValueError):
                include_closure([root / 'a.sv'], [root / 'inc'])
            (root / 'a.sv').write_text('`include `DYNAMIC_HEADER\n')
            with self.assertRaises(ValueError):
                include_closure([root / 'a.sv'], [root / 'inc'])

    def test_no_eda_without_authorization(self):
        for flags in ((False, False), (True, False), (False, True)):
            with self.assertRaises(ValueError):
                execute(Path('/nonexistent'), *flags)
        for jobs in (0, 5):
            with self.assertRaises(ValueError):
                prepare(Path('/nonexistent'), jobs)
        self.assertNotEqual(BUILT, 'DC_MATCHED_RTL_BUILT_NOT_EXECUTED')
        self.assertEqual(8 * 8192 * 128 // 8, 1048576)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'check', 'execute', 'self-test'))
    parser.add_argument('--output', type=Path, default=DEFAULT_OUT)
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--authorize-compile', action='store_true')
    parser.add_argument('--acknowledge-reconstruction', action='store_true')
    args = parser.parse_args()
    if args.action == 'self-test':
        require(not args.authorize_compile, 'No EDA authorization for host tests')
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(HostTests))
        return int(not result.wasSuccessful())
    out = args.output.resolve()
    require(out.parent == OUT and re.fullmatch(r'power_rtl_20261117_baseline_[0-9]+', out.name),
            'Wrong output scope')
    if args.action == 'execute':
        return execute(out, args.authorize_compile, args.acknowledge_reconstruction)
    require(not args.authorize_compile and not args.acknowledge_reconstruction,
            'Compile flags only apply to execute')
    if args.action == 'prepare':
        receipt = prepare(out, args.jobs)
        print(json.dumps(dict(state='PREPARED_NOT_COMPILED', output=str(out),
                              source_fingerprint=receipt['source_fingerprint'],
                              historical_byte_identity='UNPROVEN')))
    else:
        verify(read(out / 'source-pins.json'))
        print('PIN_CHECK_PASS (no EDA invoked)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
