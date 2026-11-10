#!/usr/bin/env python3
"""Directed production seeded Q4/M8 + FIFO16 + real multiplier lender gate."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
import run_matrix as tools

HERE = Path(__file__).resolve().parent
ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = tools.OUT
ACCEPTED = OUT/'stage2_matrix_queue_vcs_20261109_01'
OWN = ('run_seeded_coop.py', 'seeded_coop_vectors.c', 'seeded_coop_scenarios.svh', 'test_seeded_coop.py')
SCHEMA = 'seq seeded success fault source_words seed_rows enq deq maxq held_next updates flags'.split()


def bench_source(original, scenarios):
    anchor = '  initial begin : run_tests\n'
    if original.count(anchor) != 1 or scenarios.count('// BEGIN ROUTINES\n') != 1:
        raise ValueError('Directed fixture boundary changed')
    prefix, main = original.split(anchor)
    declarations, rest = main.split("    clk = 1'b0;", 1)
    initialization = "    clk = 1'b0;" + rest.split('    if (!$value$plusargs("QBS_COMMAND_VECTOR_FILE', 1)[0]
    ports, routines = scenarios.split('// BEGIN ROUTINES\n')
    changes = (
        ('  qbs_engine_composed #(\n', ports+'\n  qbs_engine_composed #(\n    .SeedRestoreEnable(1\'b1),\n'),
        ('.command_seed_i                  (1\'b0)', '.command_seed_i                  (command_seed)'),
        ('.seed_lane_valid_i               (\'0)', '.seed_lane_valid_i               (seed_lane_valid)'),
        ('.seed_lane_ready_o               ()', '.seed_lane_ready_o               (seed_lane_ready)'),
        ('.seed_lane_data_i                (\'{default:\'0})', '.seed_lane_data_i                (seed_lane_data)'),
        ('  assign ldu_result_final_gnt = ldu_result_req;',
         '  assign ldu_result_final_gnt = (delayed_final | ldu_result_req) &\n'
         '      {4{first_write && final_wait == 0 && cycles%5 == 0}};'))
    adapted = prefix
    for old, new in changes: adapted = tools.once(adapted, old, new)
    restored = adapted
    for old, new in reversed(changes): restored = tools.once(restored, new, old)
    if restored != prefix:
        raise ValueError('Canonical numerical/VRF checker changed')
    return adapted+routines+'\n'+anchor+declarations+initialization+'    run_directed_seeded();\n  end\nendmodule\n'


def check_log(text):
    if re.search(r'(?im)^\s*(?:Fatal:|Error:|Error-|FATAL)|Assertion failed', text):
        raise ValueError('Simulator/assertion failure')
    rows = []
    for line in text.splitlines():
        if line.startswith('SEEDED_COMMAND '):
            parts = [p.split('=') for p in line.split()[1:]]
            if any(len(p) != 2 or not p[1].isdigit() for p in parts):
                raise ValueError('Malformed command ledger')
            row = {k:int(v) for k,v in parts}
            if len(parts) != len(row) or set(row) != set(SCHEMA):
                raise ValueError('Missing/extra/duplicate command field')
            rows.append(row)
    if [r['seq'] for r in rows] != [1,2,3,4,5,6,8]:
        raise ValueError('Missing/duplicate/out-of-order directed commands')
    success_work = {1:128, 2:256, 3:256, 4:80, 6:256, 8:256}
    for r in rows:
        seq = r['seq']; seeded = int(seq != 1)
        if (r['seeded'], r['success'], r['fault'], r['source_words']) != (seeded,int(seq != 5),int(seq == 5),32*seeded):
            raise ValueError('Wrong seeded/terminal/source accounting')
        if r['seed_rows'] != (0 if seq == 1 else 8 if seq == 4 else 16):
            raise ValueError('Raw seed rows missing or duplicated')
        if r['enq'] != r['deq'] or not 1 <= r['maxq'] <= 16:
            raise ValueError('FIFO did not drain or was not exercised')
        if seq in success_work and (r['updates'] != success_work[seq] or
                                    r['enq'] != success_work[seq] or r['flags'] != int(seq != 1)):
            raise ValueError('Wrong ordered numerical/flag work')
    if rows[0]['held_next'] == 0:
        raise ValueError('No next request held across a nonempty older queue')
    reset = re.findall(r'^SEEDED_RESET seq=7 enq=(\d+) deq=(\d+) flushed=(\d+) source_words=32$', text, re.M)
    if len(reset) != 1 or not (int(reset[0][0])-int(reset[0][1]) == int(reset[0][2]) > 0):
        raise ValueError('Reset did not flush queued seeded work')
    terminal = 'SEEDED_PASS success=6 faults=1 resets=1 commands=8 oracle=original_qbs_ref scope=component_not_isa'
    if text.splitlines().count(terminal) != 1:
        raise ValueError('Missing/duplicate terminal')
    lender = re.findall(r'^STAGE2_MATRIX_LENDERS_DONE commands=7 native_issues=(\d+) loan_issues=(\d+) loan_returns=(\d+) reset_commands=1 reset_flushed=(\d+) latency=3 instances=4 scope=engine_not_soc$', text, re.M)
    if len(lender) != 1:
        raise ValueError('Missing actual real-multiplier lender closure')
    native, issued, returned, flushed = map(int,lender[0])
    if native != issued or issued != returned+flushed or returned < 5120:
        raise ValueError('Actual lender accounting')
    # Preserve the existing FIFO payload shadow/order/first-block monitor, including its terminal ledger.
    qdone = re.findall(r'^STAGE2_QUEUE_DONE commands=7 enq=(\d+) deq=(\d+) resets=1 reset_flushed=(\d+) depth=16$', text, re.M)
    if len(qdone) != 1 or int(qdone[0][0]) != int(qdone[0][1])+int(qdone[0][2]):
        raise ValueError('Original queue shadow ledger missing/unclosed')
    return dict(commands=rows, reset_flushed=int(reset[0][2]), native_issues=native,
                actual_lender_issues=issued, actual_lender_returns=returned,
                lender_reset_flushed=flushed, numerical_checker='canonical unmodified VRF checker',
                oracle='unmodified qbs_ref monolithic K1/3/5/7; dynamic retired-prefix seeds',
                scope='component only; modeled Lane seed source, no ISA/VMFPU/SoC/performance acceptance')


def prepare(out):
    if out.parent != OUT or out.exists() or not shutil.which('vcs'):
        raise ValueError('Unique direct signoff output and host VCS required')
    report = json.loads((ACCEPTED/'report.json').read_text())
    if report['state'] != 'PASS' or not report['source_image_post_match']:
        raise ValueError('Frozen dependency receipt is not accepted')
    accepted_pins = json.loads((ACCEPTED/'source-pins.json').read_text())
    out.mkdir(); snapshot = out/'inputs'; pins = {}
    def copy(source, destination, expected=None):
        h = tools.sha(source)
        if expected is not None and h != expected: raise ValueError('Frozen dependency drift: '+str(source))
        destination.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source,destination)
        if tools.sha(destination) != h: raise ValueError('Snapshot race')
        pins[str(source)] = pins[str(destination)] = h
    for name in ('report.json','source-pins.json','sources.f'):
        pins[str(ACCEPTED/name)] = tools.sha(ACCEPTED/name)
    lines = []
    for line in (ACCEPTED/'sources.f').read_text().splitlines():
        if line.startswith('+incdir+'):
            folder = Path(line[len('+incdir+'):]).relative_to(ACCEPTED/'inputs')
            lines.append('+incdir+'+str(snapshot/folder)); continue
        source = Path(line)
        if source in (ACCEPTED/'matrix_tb.sv', ACCEPTED/'matrix_engine.sv'): continue
        rel = source.relative_to(ACCEPTED/'inputs')
        if str(rel).startswith('hardware/deps/'):
            copy(source,snapshot/rel,accepted_pins[str(source)])
        else:
            copy(ROOT/rel,snapshot/rel)
        lines.append(str(snapshot/rel))
    for name, h in accepted_pins.items():
        source = Path(name)
        if source.is_relative_to(ACCEPTED/'inputs'):
            rel = source.relative_to(ACCEPTED/'inputs')
            if str(rel).startswith(('hardware/deps/common_cells/include/','hardware/deps/axi/include/')):
                copy(source,snapshot/rel,h)
    shared = Path('hardware/include/shared_reader_types.svh'); copy(ROOT/shared,snapshot/shared)
    for rel in ('apps/common/qbs_abi.h','verification/qbs/qbs_ref.c','verification/qbs/qbs_ref.h',
                'verification/qbs/qbs_command_vectors.c'):
        copy(ROOT/rel,snapshot/rel)
    local = snapshot/HERE.relative_to(ROOT)
    for name in (*OWN,'run_matrix.py'): copy(HERE/name,local/name)
    copy(ACCEPTED/'matrix_engine.sv',out/'matrix_engine.sv',accepted_pins[str(ACCEPTED/'matrix_engine.sv')])
    original = (ACCEPTED/'matrix_tb.sv').read_text()
    pins[str(ACCEPTED/'matrix_tb.sv')] = tools.sha(ACCEPTED/'matrix_tb.sv')
    if pins[str(ACCEPTED/'matrix_tb.sv')] != accepted_pins[str(ACCEPTED/'matrix_tb.sv')]:
        raise ValueError('Canonical bench drift')
    (out/'seeded_tb.sv').write_text(bench_source(original,(local/'seeded_coop_scenarios.svh').read_text()))
    lines += [str(out/'matrix_engine.sv'),str(out/'seeded_tb.sv')]
    (out/'sources.f').write_text('\n'.join(lines)+'\n')
    deadline = time.monotonic()+180
    cc = shutil.which('cc'); vcs = shutil.which('vcs')
    tools.command([cc,'-O2','-std=c11','-Wall','-Wextra','-Wno-unused-function','-ffp-contract=off',
        '-frounding-math','-I'+str(snapshot/'apps/common'),local/'seeded_coop_vectors.c',
        snapshot/'verification/qbs/qbs_ref.c','-lm','-o',out/'oracle'],out,out/'oracle-build.log',deadline)
    tools.command([out/'oracle',out/'vectors.txt'],out,out/'oracle-run.log',deadline)
    tools.command([sys.executable,'-B',local/'test_seeded_coop.py'],out,out/'host-tests.log',deadline,60)
    tools.save(out/'selection.json',dict(vcs=vcs,local=str(local),timeout_seconds=900,
        compile_timeout_seconds=600,simulation_timeout_seconds=180,cooperative=1,fifo_depth=16,
        configurations=1,successes=6,faults=1,resets=1,production_modified=False,
        baseline_live_pins_inherited=False,scope='directed seeded component, not ISA/VMFPU/SoC'))
    for p in (Path(vcs).resolve(),Path(cc).resolve(),Path(sys.executable).resolve(),*out.iterdir()):
        if p.is_file(): pins[str(p)] = tools.sha(p)
    tools.verify(pins); tools.save(out/'source-pins.json',pins)
    tools.save(out/'prepared.json',dict(state='PREPARED_NOT_EXECUTED',source_pins_sha256=tools.sha(out/'source-pins.json'),
        frozen_runner=str(local/'run_seeded_coop.py')))
    print('SEEDED_PREPARED '+str(out),flush=True)


def execute(out):
    config = json.loads((out/'selection.json').read_text())
    if Path(__file__).resolve() != Path(config['local'])/'run_seeded_coop.py' or (out/'report.json').exists():
        raise ValueError('Frozen single-attempt worker required')
    pins = json.loads((out/'source-pins.json').read_text()); work = out/'work'; work.mkdir()
    deadline = time.monotonic()+config['timeout_seconds']
    report = dict(state='FAIL',retries=0,scope=config['scope'],owner_pid=os.getpid(),
        owner_cgroup=Path('/proc/self/cgroup').read_text(),source_pins_sha256=tools.sha(out/'source-pins.json'))
    try:
        tools.verify(pins)
        argv = [config['vcs'],'-full64','-sverilog','-timescale=1ns/1ps','-j4','+lint=TFIPC-L',
            '+define+STAGE2_COOPERATIVE_WAVES=1','+define+STAGE2_QUEUE_DEPTH=16',
            '-top','qbs_engine_tb','-o','simv','-f',out/'sources.f']
        tools.save(work/'compile-command.json',list(map(str,argv)))
        tools.save(out/'status.json',dict(state='COMPILING',pid=os.getpid()))
        print('SEEDED_COMPILING',flush=True)
        tools.command(argv,work,work/'compile.log',deadline,600)
        image = tools.image_pins(work); tools.save(work/'image-pins.json',image)
        tools.verify(pins)
        tools.save(out/'status.json',dict(state='SIMULATING',pid=os.getpid()))
        print('SEEDED_SIMULATING',flush=True)
        tools.command([work/'simv','-no_save','+QBS_FUNCTIONAL_ONLY','+SEEDED_VECTOR='+str(out/'vectors.txt')],
            work,work/'run.log',deadline,180)
        report['checks'] = check_log((work/'run.log').read_text())
        tools.verify(pins); tools.verify(image)
        report.update(state='PASS',source_image_post_match=True,numerical_checked=True,
            flags_checked=True,real_multipliers=4,queue_depth=16)
        tools.save(out/'source-pins-after.json',pins)
    except Exception as error: report['error'] = str(error)
    report['artifacts'] = {str(p):tools.sha(p) for p in work.glob('*') if p.is_file()}
    tools.save(out/'report.json',report); tools.save(out/'status.json',dict(state=report['state'],error=report.get('error')))
    print('SEEDED_'+report['state']+' '+str(out/'report.json'),flush=True)
    return int(report['state'] != 'PASS')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--output',type=Path,required=True); p.add_argument('--execute',action='store_true')
    a = p.parse_args()
    if a.execute: raise SystemExit(execute(a.output.resolve()))
    prepare(a.output.resolve())
