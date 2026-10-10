#!/usr/bin/env python3
"""Isolated actual-module VCS tests; no SoC build, coverage merge or registry edits."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BACKUP = Path('/tmp/ara-signoff-upstream-before-20261009.tgz')
COMMON = ('cf_math_pkg onehot_to_bin delta_counter counter fifo_v3 spill_register_flushable '
          'spill_register lzc rr_arb_tree id_queue stream_register stream_fork '
          'stream_fork_dynamic stream_join_dynamic stream_join stream_arbiter_flushable '
          'stream_arbiter stream_to_mem mem_to_banks_detailed').split()
AXI = ('axi_pkg axi_demux_id_counters axi_cut axi_demux_simple axi_err_slv axi_multicut '
       'axi_burst_splitter_gran axi_burst_splitter axi_to_detailed_mem axi_atop_filter').split()


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def save(p, value):
    p.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', choices=('baseline', 'current'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cases', nargs='+', type=int)
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    inputs = out/'inputs'; inputs.mkdir()
    shutil.copy2(HERE/'axi_audit_tb.sv', inputs/'axi_audit_tb.sv')
    shutil.copy2(__file__, inputs/'run.py')
    pins = {str(HERE/'axi_audit_tb.sv'): sha(HERE/'axi_audit_tb.sv'), str(Path(__file__).resolve()): sha(__file__)}
    sources = []
    for name in COMMON:
        p = ROOT/'hardware/deps/common_cells/src'/f'{name}.sv'
        sources.append(p); pins[str(p)] = sha(p)
    with tarfile.open(BACKUP) as backup:
        for name in AXI:
            rel = f'hardware/deps/axi/src/{name}.sv'
            p = ROOT/rel
            data = backup.extractfile(rel).read() if args.source=='baseline' else p.read_bytes()
            target = inputs/f'{name}.sv'; target.write_bytes(data)
            pins[str(target)] = sha(target)
            if args.source=='current': pins[str(p)] = sha(p)
            sources.append(target)
    for dep in ('axi', 'common_cells'):
        for p in (ROOT/'hardware/deps'/dep/'include').rglob('*'):
            if p.is_file(): pins[str(p)] = sha(p)
    save(out/'pins.json', pins)
    vcs = shutil.which('vcs')
    if not vcs: raise RuntimeError('VCS not in PATH')
    command = [vcs, '-full64', '-sverilog', '-timescale=1ns/1ps',
               '+incdir+'+str(ROOT/'hardware/deps/axi/include'),
               '+incdir+'+str(ROOT/'hardware/deps/common_cells/include'),
               *map(str,sources), str(HERE/'axi_audit_tb.sv'), '-top', 'axi_audit_tb',
               '-o', str(out/'simv'), '-Mdir='+str(out/'csrc')]
    save(out/'compile-command.json', command)
    start = time.monotonic()
    with (out/'compile.log').open('w') as log:
        proc = subprocess.run(command, cwd=out, stdout=log, stderr=subprocess.STDOUT, timeout=300)
    if proc.returncode: raise RuntimeError('VCS compile failed: '+str(out/'compile.log'))
    cases = args.cases or list(range(16))+[100+mode*10+limit for mode in range(6) for limit in range(1,5)]
    rows = []
    def run_case(case):
        logpath = out/f'case-{case}.log'
        work = out/f'work-{case}'; work.mkdir()
        cmd = [str(out/'simv'), '-no_save', f'+CASE={case}']
        t = time.monotonic()
        with logpath.open('w') as log:
            try:
                proc = subprocess.run(cmd, cwd=work, stdout=log, stderr=subprocess.STDOUT, timeout=30)
                rc = proc.returncode
            except subprocess.TimeoutExpired:
                rc = 124
        text = logpath.read_text()
        passed = rc==0 and text.count('AUDIT_PASS ')==1 and 'Fatal' not in text
        return dict(case=case, status='PASS' if passed else ('TIMEOUT' if rc==124 else 'FAIL'), returncode=rc,
                   seconds=time.monotonic()-t, log=str(logpath), sha256=sha(logpath))
    with ThreadPoolExecutor(max_workers=max(1,args.jobs)) as pool:
        for future in as_completed([pool.submit(run_case, case) for case in cases]):
            row = future.result(); rows.append(row)
            print(f'{args.source} {row["case"]}: {row["status"]}', flush=True)
            save(out/'summary.json', dict(source=args.source, rows=rows, total=len(cases),
                 passed=sum(r['status']=='PASS' for r in rows), complete=False))
    for path, digest in pins.items():
        if sha(path)!=digest: raise RuntimeError('Input changed: '+path)
    save(out/'summary.json', dict(source=args.source, rows=rows, total=len(cases),
         passed=sum(r['status']=='PASS' for r in rows), complete=True,
         seconds=time.monotonic()-start, backup=str(BACKUP), backup_sha256=sha(BACKUP)))


if __name__=='__main__':
    main()
