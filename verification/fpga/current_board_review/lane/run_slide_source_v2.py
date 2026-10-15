"""Bounded single-process VCS matrix: real lane sequencer/requester/SLDU."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--baseline', action='store_true')
    p.add_argument('--frozen', type=Path)
    a = p.parse_args()
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    snap = out / 'snapshot'
    common = 'hardware/deps/common_cells'
    cva6 = 'hardware/deps/cva6/core/include'
    sources = [f'{common}/src/cf_math_pkg.sv', 'hardware/deps/axi/src/axi_pkg.sv',
               f'{cva6}/config_pkg.sv', f'{cva6}/cv64a6_imafdcv_sv39_config_pkg.sv',
               f'{cva6}/riscv_pkg.sv', 'hardware/include/rvv_pkg.sv',
               'hardware/deps/fpnew/src/fpnew_pkg.sv', 'hardware/include/ara_pkg.sv']
    sources += [f'{common}/src/{s}.sv' for s in ('spill_register_flushable', 'spill_register',
                'stream_register', 'lzc', 'popcount', 'fifo_v3', 'rr_arb_tree')]
    sources += ['hardware/src/common_cells_compat/fall_through_register_v1.sv',
                'hardware/src/lane/lane_sequencer.sv', 'hardware/src/lane/operand_requester.sv',
                'hardware/src/sldu/p2_stride_gen.sv', 'hardware/src/sldu/sldu_op_dp.sv',
                'hardware/src/sldu/sldu.sv']
    extras = ['hardware/src/lane/lane.sv']
    extras += [str(f.relative_to(ROOT)) for d in
               (ROOT / common / 'include', ROOT / 'hardware/include') for f in d.rglob('*.svh')]
    pins = {}
    for rel in sources + extras:
        source = a.frozen / rel if a.frozen else ROOT / rel
        if rel.endswith('/lane_sequencer.sv'):
            source = ROOT / rel
        dest = snap / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        pins[rel] = sha(dest)
    lane = (snap / 'hardware/src/lane/lane.sv').read_text()
    types = [re.search(r'typedef struct packed \{[^}]*\} ' + name + ';', lane)[0]
             for name in ('operand_request_cmd_t', 'operand_queue_cmd_t', 'vfu_operation_t')]
    (snap / 'lane_types.svh').write_text('\n'.join(types) + '\n')
    shutil.copyfile(HERE / 'slide_source_v2_tb.sv', snap / 'slide_source_v2_tb.sv')
    shutil.copyfile(Path(__file__), out / 'runner_snapshot.py')
    (out / 'sources.json').write_text(json.dumps(pins, indent=2) + '\n')
    command = ['vcs', '-full64', '-sverilog', '-timescale=1ns/1ps', '-debug_access+all',
               '+incdir+' + str(snap / common / 'include'), '+incdir+' + str(snap / 'hardware/include'),
               '+incdir+' + str(snap), '-top', 'slide_source_v2_tb',
               *[str(snap / s) for s in sources], str(snap / 'slide_source_v2_tb.sv'),
               '-o', str(out / 'simv'), '-l', 'compile.log']
    (out / 'compile-command.json').write_text(json.dumps(command, indent=2) + '\n')
    with (out / 'compile.console.log').open('w') as log:
        subprocess.run(command, cwd=out, stdout=log, stderr=subprocess.STDOUT, timeout=300, check=True)
    command = [str(out / 'simv'), '-l', 'run.log', '+WAVE', f'+BASELINE={int(a.baseline)}']
    (out / 'run-command.json').write_text(json.dumps(command, indent=2) + '\n')
    with (out / 'console.log').open('w') as log:
        proc = subprocess.run(command, cwd=out, stdout=log, stderr=subprocess.STDOUT, timeout=90)
    text = (out / 'run.log').read_text()
    records = [{k: int(v, 16 if k in ('actual', 'expected') else 10)
                for k, v in (pair.split('=') for pair in line.split()[1:])}
               for line in text.splitlines() if line.startswith('RESULT ')]
    passing = proc.returncode == 0 and 'PASS slide_source_v2' in text and 'Fatal:' not in text
    passing &= len(records) == 41 and all(sha(snap / p) == h for p, h in pins.items())
    if a.frozen:
        before = json.loads((a.frozen.parent / 'sources.json').read_text())
        changed = [p for p in pins if pins[p] != before[p]]
        passing &= changed == ['hardware/src/lane/lane_sequencer.sv']
        passing &= sha(snap / 'slide_source_v2_tb.sv') == sha(a.frozen / 'slide_source_v2_tb.sv')
    else:
        changed = []
    status = dict(status='PASS' if passing else 'FAIL', baseline=a.baseline, records=records,
                  expected_failures=sum(bool(r['expected_bug']) for r in records),
                  passed_controls=sum(not r['expected_bug'] for r in records),
                  changed_sources=changed, lane_sha256=pins['hardware/src/lane/lane_sequencer.sv'],
                  testbench_sha256=sha(snap / 'slide_source_v2_tb.sv'),
                  log_sha256=sha(out / 'run.log'), original_board_closure=False)
    (out / 'status.json').write_text(json.dumps(status, indent=2) + '\n')
    print(json.dumps({k:v for k,v in status.items() if k != 'records'}), flush=True)
    if not passing:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
