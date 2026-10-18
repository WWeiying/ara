#!/usr/bin/env python3
"""Bounded host VCS comparison of HEAD addrgen and frozen current RTL."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = Path('/home/wangwy/fpga_runs/ara_linux_canonical_rootcause_20261017/recorded_repro')
DEFAULT_OUT = ROOT / 'verification/out/addrgen-virtual-address-20261017-01'
PACKAGES = ['cf_math_pkg.sv', 'axi_pkg.sv', 'fpnew_pkg.sv', 'config_pkg.sv',
            'cv64a6_imafdcv_sv39_config_pkg.sv', 'build_config_pkg.sv',
            'riscv_pkg.sv', 'ariane_pkg.sv', 'rvv_pkg.sv', 'ara_pkg.sv']
MODULES = ['fifo_v3.sv', 'lfsr.sv', 'spill_register_flushable.sv', 'lzc.sv',
           'cva6_tlb.sv', 'cva6_shared_tlb.sv', 'cva6_mmu.sv', 'cva6_ptw.sv',
           'pmp.sv', 'pmp_entry.sv', 'pmp_data_if.sv', 'addrgen.sv']


def source_map(log, root=ROOT):
    """Use recorded compile ordering, but resolve only current source trees."""
    result = {}
    for raw in re.findall(r"Parsing design file '([^']+)'", log):
        name = Path(raw).name
        if name not in PACKAGES + MODULES:
            continue
        if '/rtl/ara/hardware/' in raw:
            rel = 'hardware/' + raw.split('/rtl/ara/hardware/', 1)[1]
        elif '/rtl/' in raw:
            rel = 'hardware/deps/' + raw.split('/rtl/', 1)[1]
        else:
            continue
        result[name] = root / rel
    missing = set(PACKAGES + MODULES) - result.keys()
    if missing:
        raise ValueError(f'Missing recorded source entries: {sorted(missing)}')
    return [result[name] for name in PACKAGES + MODULES]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n')


def run_wait(argv, cwd, name, timeout):
    """One typed command, OS wait, bounded process group; never simulation polling."""
    import signal
    start = time.time()
    write_json(cwd / f'{name}.command.json', {
        'argv': argv, 'cwd': str(cwd), 'timeout_seconds': timeout,
        'wait': 'subprocess.Popen.wait(timeout), OS waitpid',
        'started_unix': start,
        'tool_environment': {k: v for k, v in os.environ.items()
                             if any(s in k for s in ('VCS', 'SNPS', 'LM_LICENSE'))},
    })
    with (cwd / f'{name}.log').open('w') as log:
        proc = subprocess.Popen(argv, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True)
        timed_out = False
        try:
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(proc.pid, signal.SIGKILL)
            rc = proc.wait()
    result = {'returncode': rc, 'timed_out': timed_out,
              'elapsed_seconds': time.time() - start, 'pid': proc.pid,
              'wait_completed': True}
    write_json(cwd / f'{name}.wait.json', result)
    if rc or timed_out:
        raise RuntimeError(f'{name} failed: {result}; see {cwd / (name + ".log")}')
    return result


def parse_cases(log, count=10):
    rows = []
    for line in log.splitlines():
        if line.startswith('CASE_PASS '):
            rows.append({key: int(value) for key, value in re.findall(r'(\w+)=(\d+)', line)})
    if len(rows) != count or 'ADDRGEN_VIRTUAL_ADDRESS_PASS' not in log:
        raise ValueError('Missing strict simulation completion or case results')
    return sorted(rows, key=lambda row: (row['kind'], row['width']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT)
    parser.add_argument('--compile-log', type=Path, default=EVIDENCE / 'compile.log')
    parser.add_argument('--vcs', default=shutil.which('vcs'))
    parser.add_argument('--neighbors', action='store_true', help='Run eight adjacent-boundary cases on current RTL')
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    result = {'status': 'started', 'scope': 'host addrgen + current MMU; controlled DTLB; no Linux/SoC',
              'limits': ['No PTW walk coverage; any PTW request is fatal',
                         'PLEN56 to AXI48 physical-address overflow remains outside this fix',
                         'Not full regression or board validation; no prior RTL coverage reused']}
    write_json(out / 'result.json', result)
    try:
        frozen = out / 'inputs'
        frozen.mkdir()
        shutil.copy2(args.compile_log, frozen / 'recorded_compile.log')
        shutil.copy2(EVIDENCE / 'canonical_tb.sv', frozen / 'recorded_canonical_tb.sv')
        sources = source_map(args.compile_log.read_text())
        includes = ['hardware/include', 'hardware/deps/common_cells/include',
                    'hardware/deps/axi/include', 'hardware/deps/cva6/core/include']
        for rel in includes:
            shutil.copytree(ROOT / rel, frozen / rel)
        mapped = []
        for src in sources:
            dst = frozen / src.relative_to(ROOT)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            mapped.append(dst)
        tb = frozen / 'addrgen_virtual_address_tb.sv'
        shutil.copy2(Path(__file__).with_name(tb.name), tb)
        shutil.copy2(__file__, frozen / Path(__file__).name)
        baseline = frozen / 'head_addrgen.sv'
        baseline.write_bytes(subprocess.check_output(
            ['git', 'show', 'HEAD:hardware/src/vlsu/addrgen.sv'], cwd=ROOT))
        (out / 'parent_addrgen.diff').write_bytes(subprocess.check_output(
            ['git', 'diff', '--', 'hardware/src/vlsu/addrgen.sv'], cwd=ROOT))
        manifest = {'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip(),
                    'source_map': [{'original_current': str(a), 'frozen': str(b)}
                                   for a, b in zip(sources, mapped)],
                    'sha256': {str(p.relative_to(out)): digest(p)
                               for p in frozen.rglob('*') if p.is_file()}}
        write_json(out / 'inputs.json', manifest)
        result['neighbors'] = args.neighbors
        for variant in (('current',) if args.neighbors else ('baseline', 'current')):
            work = out / variant
            work.mkdir()
            selected = [baseline if variant == 'baseline' and p.name == 'addrgen.sv' else p
                        for p in mapped]
            argv = [args.vcs, '-full64', '-sverilog', '-timescale=1ns/1ps',
                    '-top', 'addrgen_virtual_address_tb', '-o', str(work / 'simv')]
            if variant == 'baseline':
                argv += ['+define+BASELINE']
            if args.neighbors:
                argv += ['+define+NEIGHBORS']
            argv += ['+incdir+' + str(frozen / rel) for rel in includes]
            argv += [str(p) for p in selected] + [str(tb)]
            (work / 'sources.f').write_text('\n'.join(str(p) for p in selected) + '\n' + str(tb) + '\n')
            run_wait(argv, work, 'compile', 180)
            run_wait([str(work / 'simv')], work, 'run', 30)
            result[variant] = parse_cases((work / 'run.log').read_text(), 8 if args.neighbors else 10)
        # Controls must keep the original handshake latency.
        for key in (() if args.neighbors else ((0, 64), (1, 48))):
            before = next(r for r in result['baseline'] if (r['kind'], r['width']) == key)
            after = next(r for r in result['current'] if (r['kind'], r['width']) == key)
            if before != after:
                raise ValueError(f'Control cycle regression: {before} != {after}')
        result['status'] = 'pass'
    except Exception as error:
        result['status'] = 'fail'
        result['error'] = str(error)
        raise
    finally:
        write_json(out / 'result.json', result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
