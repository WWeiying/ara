"""Freeze and run public-port MASK RAW tests with three real RTL modules."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--rtl-root', type=Path, default=ROOT)
    args = parser.parse_args()
    out = args.out.resolve()
    if not out.is_relative_to(HERE):
        parser.error('output must remain in mask_raw/')
    out.mkdir(parents=True, exist_ok=False)
    snap = out / 'snapshot'
    root = args.rtl_root.resolve()
    cc = 'hardware/deps/common_cells'
    cv = 'hardware/deps/cva6/core/include'
    sources = [f'{cc}/src/cf_math_pkg.sv', 'hardware/deps/axi/src/axi_pkg.sv',
               f'{cv}/config_pkg.sv', f'{cv}/cv64a6_imafdcv_sv39_config_pkg.sv',
               f'{cv}/riscv_pkg.sv', 'hardware/include/rvv_pkg.sv',
               'hardware/deps/fpnew/src/fpnew_pkg.sv', 'hardware/include/ara_pkg.sv']
    sources += [f'{cc}/src/{s}.sv' for s in ('spill_register_flushable',
                'spill_register', 'stream_register', 'lzc', 'popcount', 'fifo_v3',
                'rr_arb_tree', 'delta_counter', 'counter')]
    sources += ['hardware/src/common_cells_compat/fall_through_register_v1.sv',
                'hardware/src/ara_sequencer.sv', 'hardware/src/lane/lane_sequencer.sv',
                'hardware/src/lane/operand_requester.sv']
    extras = ['hardware/src/ara.sv', 'hardware/src/lane/lane.sv']
    extras += [str(p.relative_to(root)) for folder in
               (root / cc / 'include', root / 'hardware/include') for p in folder.rglob('*.svh')]
    pins = {}
    for rel in sources + extras:
        dest = snap / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / rel, dest)
        pins[rel] = sha(dest)
    types = []
    for rel, names in [('hardware/src/lane/lane.sv',
                        ('operand_request_cmd_t', 'operand_queue_cmd_t', 'vfu_operation_t')),
                       ('hardware/src/ara.sv', ('ara_req_t', 'ara_resp_t'))]:
        text = (snap / rel).read_text()
        for name in names:
            matches = re.findall(r'typedef struct packed \{[^}]*\} ' + name + ';', text)
            if len(matches) != 1:
                raise ValueError('type extraction failed: ' + name)
            types.append(matches[0])
    (snap / 'local_types.svh').write_text('\n'.join(types) + '\n')
    shutil.copyfile(HERE / 'mask_raw_tb.sv', snap / 'mask_raw_tb.sv')
    shutil.copyfile(Path(__file__), out / 'runner_snapshot.py')
    save(out / 'sources.json', pins)
    save(out / 'provenance.json', dict(rtl_root=str(root), testbench_sha256=sha(snap / 'mask_raw_tb.sv'),
        types_sha256=sha(snap / 'local_types.svh'), no_internal_injection=True,
        real_rtl=['ara_sequencer', 'lane_sequencer', 'operand_requester'],
        modeled=['dispatcher stimulus', 'LDU writeback timing/completion', 'VRF storage',
                 'always-ready operand queue sinks', 'non-target FU readiness']))
    command = ['vcs', '-full64', '-sverilog', '-timescale=1ns/1ps',
               '+incdir+' + str(snap / cc / 'include'),
               '+incdir+' + str(snap / 'hardware/include'), '+incdir+' + str(snap),
               '-top', 'mask_raw_tb', *[str(snap / s) for s in sources],
               str(snap / 'mask_raw_tb.sv'), '-o', str(out / 'simv'), '-l', 'compile.log']
    save(out / 'compile-command.json', command)
    save(out / 'status.json', dict(state='FROZEN', rtl_status='NOT_RUN'))
    print('FROZEN ' + str(out), flush=True)
    with (out / 'compile.console.log').open('w') as log:
        proc = subprocess.run(command, cwd=out, stdout=log, stderr=subprocess.STDOUT, timeout=300)
    if proc.returncode:
        save(out / 'status.json', dict(state='COMPILE_FAIL', returncode=proc.returncode))
        return 2
    command = [str(out / 'simv'), '-l', 'run.log']
    save(out / 'run-command.json', command)
    with (out / 'console.log').open('w') as log:
        proc = subprocess.run(command, cwd=out, stdout=log, stderr=subprocess.STDOUT, timeout=60)
    text = (out / 'run.log').read_text()
    records = [dict(pair.split('=', 1) for pair in line.split()[1:])
               for line in text.splitlines() if line.startswith('RESULT ')]
    integrity = (proc.returncode == 0 and 'HARNESS_COMPLETE mask_raw' in text and
                 'WAR_CONTROL PASS' in text and 'Fatal:' not in text and len(records) == 22 and
                 all(sha(snap / rel) == value for rel, value in pins.items()))
    failed = [r['case'] for r in records if int(r['errors']) or int(r['class_errors'])]
    status = dict(state='COMPLETE' if integrity else 'HARNESS_FAIL',
                  rtl_status='FAIL' if failed or not integrity else 'PASS',
                  cases=len(records), failing_cases=failed, records=records,
                  war_control_pass='WAR_CONTROL PASS' in text,
                  producer_is_modeled=True, soc_reproduction_claim=False,
                  source_hashes_unchanged=all(sha(snap / rel) == value for rel, value in pins.items()))
    save(out / 'status.json', status)
    print(json.dumps({k: v for k, v in status.items() if k != 'records'}), flush=True)
    return 0 if integrity and not failed else 1


if __name__ == '__main__':
    raise SystemExit(main())
