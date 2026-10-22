#!/usr/bin/env python3
"""Pinned matrix row22 software derivative; one sealed-final04 replay, no RTL build."""
import argparse
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
from adapter import HERE, CC, SPIKE, ARA, SYSTEM, prepare, checked, inside

SOURCE = HERE / 'matrix01/prepared'
SHAPE = 'extension_e32_m4_vf4'
NAME = 'extension_trial22'
IMAGE = Path('/home/wangwy/fpga_runs/current_board_integration_final04/campaign/image')
MARKER = 'EXTENSION_MATRIX_PASS sew=32 factor=4 cases=1 errors=0'


def build(out):
    original = prepare.check(SOURCE)
    out.mkdir(parents=True, exist_ok=False)
    prepared = out / 'prepared'
    dest = prepared / NAME / 'original'
    dest.mkdir(parents=True)
    for name in ('startup.S', 'runtime.c', 'replay.ld'):
        shutil.copyfile(SOURCE / name, prepared / name)
    for name in ('source.S', 'scenario.S'):
        shutil.copyfile(SOURCE / SHAPE / 'original' / name, dest / name)
    shutil.copyfile(SOURCE / SHAPE / 'case.c', dest.parent / 'case.c')
    rows = json.loads((SOURCE / SHAPE / 'original/cases.json').read_text())
    row = rows[22]
    assert row == dict(label='last_nonoverlapping_destination_element', op=2,
                       mode=0, start=0, vl=96, unmasked=0, seed=0)
    header = '#define EXPECTED_CAP 128\nstatic const struct trial trials[] = {\n    {'
    header += ', '.join(str(row[k]) for k in ('op', 'mode', 'start', 'vl', 'unmasked', 'seed'))
    (dest / 'test_cases.h').write_text(header + '},\n};\n')
    case = next(c.copy() for c in original['cases'] if c['id'] == SHAPE)
    case.update(id=NAME, cases=[row])
    case['defines'] = [d.replace(SHAPE + '_main', NAME + '_main') for d in case['defines']]
    provenance = dict(schema_version=1, vlen=1024, nr_lanes=4, cases=[case],
        source_provenance_sha256=prepare.sha(SOURCE / 'provenance.json'),
        original_matrix_row=22, printed_local_trial=0,
        scope='single same-source row; prior21 rows omitted, not full-matrix acceptance',
        driver_and_assembly_unchanged=True, full_byte_tail_guard_oracle_preserved=True)
    provenance['files'] = {str(p.relative_to(prepared)): prepare.sha(p)
                           for p in prepared.rglob('*') if p.is_file()}
    prepare.save(prepared / 'provenance.json', provenance)
    prepare.EXTENSIONS = [NAME]
    prepare.ORACLE_MARKERS[NAME] = MARKER
    for backend in ('spike', 'soc'):
        prepare.compile_programs(prepared, out / backend, CC, backend == 'spike')
    elf = out / 'spike' / (NAME + '.elf')
    nm = subprocess.check_output([str(CC.with_name('riscv64-unknown-elf-nm')), str(elf)], text=True)
    symbols = {n: a for a, _, n in (line.split() for line in nm.splitlines())}
    cmd = out / 'spike.cmd'
    cmd.write_text('until pc 0 ' + symbols['replay_exit'] + '\nreg 0 a0\nstr '
                   + symbols['replay_log'] + '\nrs\n')
    command = [str(SPIKE), '-d', '--debug-cmd=' + str(cmd), '--isa=rv64gcv_zvl1024b', '-m2', str(elf)]
    with (out / 'spike.log').open('w') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=30)
    passed = result.returncode == 0 and MARKER in (out / 'spike.log').read_text()
    prepare.save(out / 'reference.json', dict(status='PASS' if passed else 'FAIL',
        command=command, row=row, original_row=22, source_provenance=provenance,
        spike_log_sha256=prepare.sha(out / 'spike.log'),
        elf_sha256={b: prepare.sha(out / b / (NAME + '.elf')) for b in ('soc', 'spike')}))
    assert passed, 'No RTL run authorized before Spike passes'
    print('SPIKE_PASS original row22; local printed trial0', flush=True)


def replay(build_dir, out):
    reference = json.loads((build_dir / 'reference.json').read_text())
    assert reference['status'] == 'PASS'
    assert prepare.sha(build_dir / 'soc' / (NAME + '.elf')) == reference['elf_sha256']['soc']
    out.mkdir(parents=True, exist_ok=False)
    checked.run_programs(SimpleNamespace(image=IMAGE, programs=build_dir / 'soc',
        case=[NAME], jobs=1, timeout=180, execute=False, out=out / 'preflight'))
    ledger = json.loads((IMAGE / 'image.json').read_text())
    shutil.copyfile(build_dir / 'soc' / (NAME + '.elf'), out / 'input.elf')
    names = [SYSTEM + '.i_ara_commit_monitor.cycle_q']
    names += [ARA + '.i_dispatcher.' + n for n in (
        'state_q', 'state_d', 'arch_decode', 'decode_blocked', 'acc_req_i', 'acc_resp_o',
        'csr_vl_q', 'csr_vtype_q', 'csr_vstart_q', 'ara_req', 'ara_req_idle',
        'ara_req_committed', 'ara_req_d', 'ara_req_valid_d', 'ara_req_o', 'ara_req_valid_o',
        'ara_req_ready_i', 'ara_store_accepted_i', 'ara_resp_valid', 'ara_idle_i', 'sldu_idle_i',
        'backend_req', 'backend_valid', 'layout_req', 'maintenance_req', 'maintenance_valid',
        'reshuffle_req_q', 'reshuffle_req_d', 'rs_lmul_cnt_q', 'rs_lmul_cnt_d',
        'rs_lmul_cnt_limit_q', 'rs_lmul_cnt_limit_d', 'reshuffle_vs1_base_q',
        'reshuffle_vs1_limit_q', 'reshuffle_eew_vs1_q', 'rs_mask_request_q',
        'is_vstore', 'pending_seg_mem_op_q', 'vs_buffer_q', 'eew_old_buffer_q',
        'eew_new_buffer_q', 'eew_q[24]', 'eew_valid_q')]
    names += [ARA + '.i_sequencer.' + n for n in (
        'pe_req_o', 'pe_req_valid_o', 'pe_resp_i', 'pe_req_ready_i',
        'addrgen_ack_i', 'memory_store_completed_q', 'ara_resp_valid_o',
        'vinsn_running_q', 'verify_vinsn_done')]
    prepare.save(out / 'profile.json', dict(signals=names, window_ns=[0, 40000],
        debug_plusarg_target_filtered=True, purpose='bounded single-row dispatch/maintenance and store completion'))
    tcl = ['onerror {quit}', 'set fid [dump -file selected.fsdb -type FSDB]']
    tcl += ['dump -add {' + n + '} -aggregates -fid $fid' for n in names]
    tcl += ['run -absolute 40000ns', 'dump -disable -fid $fid', 'dump -flush $fid',
            'puts "TRIAL22_CAPTURE_BOUNDARY_40000NS"', 'run', 'quit']
    (out / 'capture.tcl').write_text('\n'.join(tcl) + '\n')
    command = ['/usr/bin/nice', '-n', '10', ledger['simv'], '-no_save',
        '-ucli', '-do', str(out / 'capture.tcl'), '-l', 'run.vcs.log',
        '+ntb_random_seed=1', '+PRELOAD=' + str(out / 'input.elf'), '+TESTCASE=' + NAME,
        '+NO_FSDB', '+ARA_DEBUG_RESHUFFLE', '+COMMIT_TRACE=' + str(out / 'commit_trace.csv'),
        '+VECTOR_TRACE=' + str(out / 'vector_trace.csv')]
    prepare.save(out / 'command.json', dict(command=command, timeout_s=180,
        image_ledger_sha256=prepare.sha(IMAGE / 'image.json'),
        simv_sha256=prepare.sha(Path(ledger['simv'])), elf_sha256=prepare.sha(out / 'input.elf')))
    start = time.monotonic()
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
    text = (out / 'console.log').read_text()
    status = dict(returncode=rc, timed_out=timed_out, elapsed_s=time.monotonic()-start,
        oracle_pass=rc == 0 and MARKER in text and 'BOARD_REPLAY_PASS' in text,
        no_rtl_build=True, no_rtl_edits=True, full_matrix_not_replayed=True)
    prepare.save(out / 'status.json', status)
    print(json.dumps(status), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['build', 'replay'])
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--build', type=Path)
    args = parser.parse_args()
    if args.mode == 'build':
        build(inside(args.out))
    else:
        replay(inside(args.build), inside(args.out))


if __name__ == '__main__':
    main()
