#!/usr/bin/env python3
"""Pinned original VL127 source port; replay only the sealed final03 image."""
import argparse
import csv
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'integration'
sys.path.insert(0, str(BASE))
import prepare
import run as checked

CAMPAIGN = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01')
NAME = 'extension_overlap_vl127'
ORIGINAL = 'rvv_trace_extension_single_e16_m2_vf2'
SOURCE = CAMPAIGN / 'rvv_extension_single01' / ORIGINAL
PARENT = Path('/tmp/current-board-integration-fast01/prepared')
IMAGE = Path('/home/wangwy/fpga_runs/current_board_integration_final03/campaign/image')
CC = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
SPIKE = Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
PINS = {
    'scenario.c': 'bcd4f3aec5436bf846429ccb8fef9d2207f07f6ecf6b0efeb0a37b7b3b923e2c',
    'scenario.S': '9235360ef269649313c2a1ba84450b438fb07d3f056383194e11d574c4472152',
    'operations.h': '77e550d26e7c8e01e20cce92d373727f6077612f3247745042471508a67a9cac',
}
MANIFEST_SHA = '1869f1087e9f01698af4f5b1304c015a3ea76ea36024effe512db8fae8fc8ef6'
LINUX_SHA = '46e4a83a8ee93456229cfdd04acb9cb0e3d31dcd67d62a7af8af2f503f4cf9e5'
MARKER = 'RVV_EXTENSION_PASS sew=16 cases=1 errors=0'
SYSTEM = 'ara_tb.dut.i_ara_soc.i_system'
ARA = SYSTEM + '.i_ara'


def inside(path):
    path = path.resolve()
    if not path.is_relative_to(HERE):
        raise ValueError('all outputs must stay under extension_overlap/')
    return path


def profile():
    names = ['ara_tb.clk', SYSTEM + '.i_ara_commit_monitor.cycle_q']
    names += [ARA + '.i_dispatcher.' + n for n in (
        'acc_req_i', 'acc_resp_o', 'verify_active_insn_q', 'verify_front_active_q',
        'state_q', 'state_d', 'csr_vl_q', 'csr_vtype_q', 'csr_vstart_q',
        'ara_req', 'backend_req', 'backend_valid', 'ara_req_valid_o',
        'ara_req_ready_i', 'ara_req_o', 'ara_idle_i', 'sldu_idle_i',
        'eew_q[24]', 'eew_q[25]', 'eew_valid_q', 'reshuffle_req_q',
        'reshuffle_req_d', 'legal_widen_overlap', 'masked_widen_layout_conflict',
        'source_snapshot_valid_q', 'source_snapshot_resolves_widen',
        'rs_lmul_cnt_q', 'rs_lmul_cnt_limit_q', 'vs_buffer_q',
        'eew_old_buffer_q', 'eew_new_buffer_q')]
    names += [ARA + '.i_sequencer.' + n for n in (
        'vinsn_running_q', 'verify_vinsn_done', 'pe_req_o', 'pe_req_valid_o',
        'global_hazard_table_o')]
    names += [ARA + '.i_sldu.' + n for n in ('state_q', 'pe_req_i', 'pe_req_valid_i')]
    for lane in (0, 3):
        names += [ARA + f'.gen_lanes[{lane}].i_lane.i_operand_requester.' + n
                  for n in ('state_q', 'requester_metadata_q',
                            'operand_request_valid_i', 'source_lifetime_active',
                            'lane_operand_req', 'operand_gnt')]
    return names


def build(out):
    parent = prepare.check(PARENT)
    manifest = SOURCE.parent / 'manifest.json'
    linux = SOURCE.parent / 'overlay/opt/ara-tests' / ORIGINAL
    if prepare.sha(manifest) != MANIFEST_SHA or prepare.sha(linux) != LINUX_SHA:
        raise ValueError('original manifest/ELF drift')
    for name, digest in PINS.items():
        if prepare.sha(SOURCE / name) != digest:
            raise ValueError('original source drift: ' + name)
    out.mkdir(parents=True, exist_ok=False)
    prepared = out / 'prepared'
    original = prepared / NAME / 'original'
    original.mkdir(parents=True)
    for name in PINS:
        shutil.copyfile(SOURCE / name, original / name)
    shutil.copyfile(manifest, original / 'manifest.json')
    for name in ('startup.S', 'runtime.c', 'replay.ld'):
        shutil.copyfile(PARENT / name, prepared / name)
    (original.parent / 'case.c').write_text(prepare.adapt(
        (original / 'scenario.c').read_text(), NAME))
    provenance = dict(schema_version=1, vlen=1024, nr_lanes=4,
        scope='original-source single port, not original Linux ELF replay',
        source=str(SOURCE), linux_elf=str(linux), linux_elf_sha256=LINUX_SHA,
        manifest_sha256=MANIFEST_SHA, source_sha256=PINS,
        parent_provenance_sha256=prepare.sha(PARENT / 'provenance.json'),
        parent_runtime_sha256={n: parent['files'][n]
                              for n in ('startup.S', 'runtime.c', 'replay.ld')},
        helper_sha256={n: prepare.sha(BASE / n) for n in ('prepare.py', 'run.py')},
        cases=[dict(id=NAME, assembly='scenario.S', include_combined=True,
                    defines=['SEW=16', 'FACTOR=2', 'DEST_REGS=2',
                             'SOURCE_REGS=1', 'OP_COUNT=4'])])
    provenance['files'] = {str(p.relative_to(prepared)): prepare.sha(p)
                           for p in prepared.rglob('*') if p.is_file()}
    prepare.save(prepared / 'provenance.json', provenance)
    prepare.save(out / 'bounded_profile.json', dict(signals=profile(),
        max_window_ns=2000, scope='same-image targeted follow-up only',
        first_run_probes=['COMMIT_TRACE', 'VECTOR_TRACE']))
    prepare.EXTENSIONS = [NAME]
    prepare.ORACLE_MARKERS[NAME] = MARKER
    for backend in ('soc', 'spike'):
        prepare.compile_programs(prepared, out / backend, CC, backend == 'spike')
    reference(out)


def reference(out):
    prepare.check(out / 'prepared')
    references = {}
    for backend in ('soc', 'spike'):
        dis = (out / backend / (NAME + '.dis')).read_text()
        matches = re.findall(r'^\s*([0-9a-f]+):\s+49932c57\s+vzext\.vf2', dis, re.M)
        if len(matches) != 1:
            raise ValueError('target opcode missing or ambiguous')
        references[backend] = dict(target_pc='0x' + matches[0],
            elf_sha256=prepare.sha(out / backend / (NAME + '.elf')),
            disassembly_sha256=prepare.sha(out / backend / (NAME + '.dis')))
    symbols = subprocess.check_output([str(CC.with_name(CC.name.removesuffix('gcc') + 'nm')),
        str(out / 'spike' / (NAME + '.elf'))], text=True)
    addresses = {name: address for address, _, name in
                 (line.split() for line in symbols.splitlines())}
    debug = out / 'reference_debug.cmd'
    debug.write_text('\n'.join([
        'until pc 0 ' + references['spike']['target_pc'][2:],
        'pc 0', 'insn 0', 'reg 0 vl', 'reg 0 vtype', 'reg 0 vstart',
        'until pc 0 ' + addresses['replay_exit'],
        'reg 0 a0', 'str ' + addresses['replay_log'], 'rs', '']) )
    command = [str(SPIKE), '-d', '--debug-cmd=' + str(debug),
               '--isa=rv64gcv_zvl1024b', '-m2',
               str(out / 'spike' / (NAME + '.elf'))]
    began = time.monotonic()
    with (out / 'spike_checked.log').open('w') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=30)
    log = (out / 'spike_checked.log').read_text()
    passed = result.returncode == 0 and MARKER in log and 'BOARD_REPLAY_PASS' in log
    reference = dict(status='PASS' if passed else 'FAIL', command=command,
        returncode=result.returncode, elapsed_s=time.monotonic()-began,
        spike_sha256=prepare.sha(SPIKE), programs=references,
        log_sha256=prepare.sha(out / 'spike_checked.log'), full_original_oracle_preserved=True)
    prepare.save(out / 'reference_checked.json', reference)
    print(json.dumps(reference, indent=2))
    if not passed:
        raise RuntimeError('Spike did not pass; no SoC launch allowed')


def validate(build_dir, out):
    reference = json.loads((build_dir / 'reference_checked.json').read_text())
    if reference['status'] != 'PASS':
        raise ValueError('Spike reference not passing')
    for backend, record in reference['programs'].items():
        if prepare.sha(build_dir / backend / (NAME + '.elf')) != record['elf_sha256']:
            raise ValueError('reference/program drift')
    checked.run_programs(SimpleNamespace(image=IMAGE, programs=build_dir / 'soc',
        case=[NAME], jobs=1, timeout=180, execute=False, out=out))
    return json.loads((IMAGE / 'image.json').read_text())


def summarize(out):
    with (out / 'commit_trace.csv').open() as stream:
        rows = list(csv.DictReader(stream))
    targets = [r for r in rows if r['insn'] == '49932c57']
    counts = {e: sum(r['event'] == e for r in targets)
              for e in ('arch_start', 'cvx_req', 'uop_alloc', 'uop_done', 'retire')}
    retired = [r for r in rows if r['event'] == 'retire']
    with (out / 'vector_trace.csv').open() as stream:
        vector = [r for r in csv.DictReader(stream)
                  if r['insn'] == '49932c57' and r['event'] in ('alloc', 'done')]
    summary = dict(target_events=counts, first_target=targets[:1],
                   first_retire=retired[:1], last_retire=retired[-1:],
                   target_first_events=targets[:12], target_last_events=targets[-6:],
                   vector_first_events=vector[:16], vector_last_events=vector[-6:])
    prepare.save(out / 'trace_summary.json', summary)
    return summary


def convert_capture(out, start_ns, window_ns):
    command_data = json.loads((out / 'command.json').read_text())
    if command_data['window_ns'] != [start_ns, start_ns + window_ns]:
        raise ValueError('conversion must retain the captured window')
    # Selecting one element exports the entire unpacked EEW array. Selecting
    # both elements duplicates declarations and fails in this Verdi release.
    selected = [n for n in profile() if not n.endswith('.eew_q[25]')]
    command = [str(checked.VERDI / 'platform/linux64/bin/fsdb2vcd'),
        'selected.fsdb', '-o', 'selected_once.vcd', '-bt', f'{start_ns}ns',
        '-et', f'{start_ns + window_ns}ns', '-compacttree', '-s']
    command += ['/' + n.replace('.', '/') for n in selected]
    prepare.save(out / 'convert_once_command.json', command)
    env = dict(checked.environment(),
        LD_LIBRARY_PATH=str(checked.VERDI / 'etc/lib/libstdc++/linux64'))
    with (out / 'convert_once.log').open('w') as log:
        subprocess.run(command, cwd=out, env=env, stdout=log,
                       stderr=subprocess.STDOUT, check=True, timeout=60)


def replay(build_dir, out, start_ns=None, window_ns=1000):
    out.mkdir(parents=True, exist_ok=False)
    ledger = validate(build_dir, out / 'validate_before')
    elf = out / 'input.elf'
    shutil.copyfile(build_dir / 'soc' / (NAME + '.elf'), elf)
    command = ['/usr/bin/nice', '-n', '10', ledger['simv'], '-no_save',
               '-l', 'run.vcs.log', '+ntb_random_seed=1', '+PRELOAD=' + str(elf),
               '+TESTCASE=' + NAME, '+NO_FSDB',
               '+COMMIT_TRACE=' + str(out / 'commit_trace.csv'),
               '+VECTOR_TRACE=' + str(out / 'vector_trace.csv')]
    signals = json.loads((build_dir / 'bounded_profile.json').read_text())['signals']
    if start_ns is not None:
        if start_ns < 0 or not 1 <= window_ns <= 2000:
            raise ValueError('capture must be a nonnegative, <=2000ns window')
        tcl = ['onerror {quit}', 'set fid [dump -file selected.fsdb -type FSDB]']
        tcl += ['dump -add {' + n + '} -aggregates -fid $fid' for n in signals]
        tcl += ['dump -disable -fid $fid', f'run -absolute {start_ns}ns',
                'dump -enable -fid $fid', f'run -absolute {start_ns + window_ns}ns',
                'dump -disable -fid $fid', 'dump -flush $fid', 'quit']
        (out / 'capture.tcl').write_text('\n'.join(tcl) + '\n')
        command[4:4] = ['-ucli', '-do', str(out / 'capture.tcl')]
    prepare.save(out / 'command.json', dict(command=command, cwd=str(out),
        timeout_s=180, elf_sha256=prepare.sha(elf),
        image_ledger_sha256=prepare.sha(IMAGE / 'image.json'),
        profile_sha256=prepare.sha(build_dir / 'bounded_profile.json'),
        window_ns=None if start_ns is None else [start_ns, start_ns + window_ns]))
    began = time.monotonic()
    timed_out = False
    with (out / 'console.log').open('w') as log:
        process = subprocess.Popen(command, cwd=out, env=checked.environment(),
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            rc = process.wait(timeout=180)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                rc = process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                rc = process.wait()
    elapsed = time.monotonic() - began
    validate(build_dir, out / 'validate_after')
    log = (out / 'console.log').read_text()
    status = dict(returncode=rc, elapsed_s=elapsed, timed_out=timed_out,
        oracle_pass=MARKER in log and 'BOARD_REPLAY_PASS' in log,
        bounded_capture=start_ns is not None, no_rtl_build=True, no_rtl_edits=True)
    prepare.save(out / 'status.json', status)
    summary = summarize(out)
    if start_ns is not None:
        convert_capture(out, start_ns, window_ns)
    print(json.dumps(dict(status=status, summary=summary), indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['build', 'reference', 'replay', 'capture', 'convert'])
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--build', type=Path)
    parser.add_argument('--start-ns', type=int)
    parser.add_argument('--window-ns', type=int, default=1000)
    args = parser.parse_args()
    if args.command == 'build':
        build(inside(args.out))
    elif args.command == 'reference':
        reference(inside(args.out))
    elif args.command == 'convert':
        convert_capture(inside(args.out), args.start_ns, args.window_ns)
    else:
        if args.command == 'capture' and args.start_ns is None:
            parser.error('capture requires --start-ns from first-run evidence')
        replay(inside(args.build), inside(args.out),
               args.start_ns if args.command == 'capture' else None, args.window_ns)


if __name__ == '__main__':
    main()
