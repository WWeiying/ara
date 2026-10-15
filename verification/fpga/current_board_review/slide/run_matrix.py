#!/usr/bin/env python3
"""Bounded, snapshotted VCS MASKU/SLDU byte-oracle matrix; one simulator invocation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
SCALAR = bytes.fromhex('1032547698badcfe')


def matrix():
    """Only requests dispatched to the backend, LMUL=1 and undisturbed mask/tail."""
    cases = []
    for sew in range(4):
        aggregate, vlmax = 32 >> sew, 128 >> sew
        for vl in (2 * aggregate, 2 * aggregate + 1):
            operations = [(0, 1, 1), (1, 1, 1)]
            for down in (0, 1):
                offsets = [0, 1, 3, aggregate, aggregate + 1]
                if down:
                    offsets += [vlmax - 1, vlmax]
                operations += [(down, 0, offset) for offset in offsets]
            for start in (0, 1, aggregate, vl - 1):
                for down, scalar, offset in operations:
                    for predicate in ('on', 'off', 'alternating', 'sparse'):
                        for bp in (0, 1):
                            cases.append(dict(id=len(cases), sew=sew, start=start, vl=vl,
                                              down=down, scalar=scalar, offset=offset,
                                              predicate=predicate, bp=bp))
    # Append so the original masked IDs/data remain comparable to sealed runs.
    # Omitted vm means zero. Unmasked cases deliberately supply no mask operands.
    for sew in range(4):
        aggregate = 32 >> sew
        vl = 2 * aggregate + 1
        for start in (0, 1, aggregate, vl - 1):
            for down, scalar, offset in ((0, 1, 1), (1, 1, 1), (0, 0, 3), (1, 0, 3)):
                cases.append(dict(id=len(cases), sew=sew, start=start, vl=vl,
                                  down=down, scalar=scalar, offset=offset,
                                  predicate='off', bp=1, vm=1))
    return cases


def oracle(case):
    """Pure architectural element arithmetic; no physical/DUT layout functions."""
    c = case
    size = 1 << c['sew']
    source = bytes(1 + ((b * 73 + c['id'] * 19) % 251) for b in range(128))
    predicate = [c['predicate'] == 'on' or
                 (c['predicate'] == 'alternating' and i % 2 == 0) or
                 (c['predicate'] == 'sparse' and i in
                  {0, c['start'], (32 >> c['sew']) + 1, c['vl'] - 1})
                 for i in range(256)]
    writes = [0] * 128
    expected = bytearray(128)
    for element in range(c['start'], c['vl']):
        if ((not c.get('vm', 0) and not predicate[element]) or
                (not c['down'] and not c['scalar'] and element < c['offset'])):
            continue
        if c['scalar'] and element == (c['vl'] - 1 if c['down'] else 0):
            value = SCALAR[:size]
        else:
            src_element = element + c['offset'] if c['down'] else element - c['offset']
            assert src_element >= 0
            value = source[src_element * size:(src_element + 1) * size]
            if src_element >= 128 // size:
                value = bytes(size)
        begin = element * size
        expected[begin:begin + size] = value
        writes[begin:begin + size] = [1] * size
    return source, expected, writes, sum(int(p) << i for i, p in enumerate(predicate))


def run_bounded(command, out, env, logfile, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError('Overall VCS build/run deadline expired')
    with (out / logfile).open('w') as log:
        process = subprocess.Popen(command, cwd=out, env=env, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            return process.wait(timeout=remaining)
        except BaseException:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--rtl-root', type=Path, default=ROOT,
                        help='RTL/dependency source tree to snapshot; TB/oracle remain current')
    parser.add_argument('--controls-only', action='store_true', help='Only vstart=0')
    parser.add_argument('--case', type=int, help='One stable matrix case id')
    parser.add_argument('--trace-case', type=int, default=-1)
    parser.add_argument('--compare', type=Path, help='Prior passing output directory for cycle comparison')
    parser.add_argument('--timeout', type=int, default=240, choices=range(180, 301),
                        metavar='180..300', help='Overall compile + simulation seconds (default 240)')
    args = parser.parse_args()
    cases = [c for c in matrix() if (not args.controls_only or c['start'] == 0)
             and (args.case is None or c['id'] == args.case)]
    if not cases:
        parser.error('No selected cases')
    out, rtl_root = args.out.resolve(), args.rtl_root.resolve()
    out.mkdir(parents=True, exist_ok=False)
    pins = {}
    start_time = time.monotonic()
    status = dict(state='STARTED', rtl_root=str(rtl_root), controls_only=args.controls_only,
                  selected_cases=len(cases), results=[])

    def snapshot(path, root=rtl_root):
        data = (root / path).read_bytes()
        dst = out / path
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
        pins[path] = hashlib.sha256(data).hexdigest()
        return str(dst)

    try:
        packages = ['hardware/deps/common_cells/src/cf_math_pkg.sv',
                    'hardware/deps/axi/src/axi_pkg.sv',
                    'hardware/deps/cva6/core/include/config_pkg.sv',
                    'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
                    'hardware/deps/cva6/core/include/riscv_pkg.sv',
                    'hardware/include/rvv_pkg.sv',
                    'hardware/deps/fpnew/src/fpnew_pkg.sv', 'hardware/include/ara_pkg.sv']
        files = packages + [f'hardware/deps/common_cells/src/{name}.sv' for name in
                            ['spill_register_flushable', 'spill_register', 'lzc',
                             'popcount', 'delta_counter', 'fifo_v3']]
        files += ['hardware/src/sldu/p2_stride_gen.sv', 'hardware/src/sldu/sldu_op_dp.sv',
                  'hardware/src/sldu/sldu.sv', 'hardware/src/masku/masku_operands.sv',
                  'hardware/src/masku/masku.sv']
        sources = [snapshot(path) for path in files]
        for directory in ('hardware/include/ara', 'hardware/deps/common_cells/include/common_cells'):
            for path in sorted((rtl_root / directory).glob('*.svh')):
                snapshot(str(path.relative_to(rtl_root)))
        sources.append(snapshot(str((HERE / 'mask_slide_matrix_tb.sv').relative_to(ROOT)), ROOT))
        snapshot(str(Path(__file__).resolve().relative_to(ROOT)), ROOT)
        (out / 'cases.json').write_text(json.dumps(cases, indent=2) + '\n')
        with (out / 'vectors.txt').open('w') as vectors:
            vectors.write(f'{len(cases)}\n')
            for case in cases:
                src, expected, writes, predicate = oracle(case)
                vectors.write(' '.join(str(case[k]) for k in
                                      ('id', 'sew', 'start', 'vl', 'down', 'scalar', 'offset', 'bp')))
                vectors.write(f' {case.get("vm", 0)} {predicate:064x}\n')
                for b in range(128):
                    vectors.write(f'{src[b]:02x} {expected[b]:02x} {writes[b]}\n')
        for name in ('cases.json', 'vectors.txt'):
            pins[name] = hashlib.sha256((out / name).read_bytes()).hexdigest()
        (out / 'pins.json').write_text(json.dumps(pins, indent=2) + '\n')
        vcs = '/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1'
        env = dict(os.environ, VCS_HOME=vcs, SNPSLMD_LICENSE_FILE='27000@t7920')
        env['PATH'] = vcs + '/bin:' + env['PATH']
        compile_cmd = ['vcs', '-full64', '-sverilog', '-timescale=1ns/1ps',
                       '-top', 'mask_slide_matrix_tb',
                       '+incdir+' + str(out / 'hardware/deps/common_cells/include'),
                       '+incdir+' + str(out / 'hardware/include'), *sources,
                       '-o', str(out / 'simv'), '-l', str(out / 'compile.log')]
        sim_cmd = [str(out / 'simv'), '-no_save', '+VECTORS=' + str(out / 'vectors.txt'),
                   f'+TRACE_CASE={args.trace_case}']
        (out / 'command.json').write_text(json.dumps(dict(compile=compile_cmd, simulate=sim_cmd), indent=2) + '\n')
        deadline = start_time + args.timeout
        print(f'Compiling {len(cases)} cases from snapshot {out}', flush=True)
        rc = run_bounded(compile_cmd, out, env, 'compile.console.log', deadline)
        if rc:
            raise RuntimeError(f'VCS compilation failed: {rc}; see compile.console.log')
        print('Running single matrix simulation', flush=True)
        rc = run_bounded(sim_cmd, out, env, 'matrix.log', deadline)
        log = (out / 'matrix.log').read_text()
        for line in log.splitlines():
            if line.startswith('MATRIX_RESULT '):
                status['results'].append({k: int(v) for k, v in
                                          (item.split('=') for item in line.split()[1:])})
        status['exit'] = rc
        status['first_failure'] = next((line for line in log.splitlines()
                                        if line.startswith('MATRIX_FAIL ')), None)
        status['state'] = 'PASS' if (rc == 0 and len(status['results']) == len(cases)
                                    and f'MASK_SLIDE_MATRIX_PASS cases={len(cases)}' in log) else 'FAIL'
        if args.compare and status['state'] == 'PASS':
            previous = json.loads((args.compare / 'status.json').read_text())
            if previous['state'] != 'PASS':
                raise ValueError('Comparison requires a passing baseline')
            old_cases = {c['id']: c for c in json.loads((args.compare / 'cases.json').read_text())}
            old_results = {r['id']: r for r in previous['results']}
            comparisons = []
            for case, result in zip(cases, status['results']):
                if case['start'] != 0 or old_cases.get(case['id']) != case:
                    continue
                old = old_results[case['id']]
                comparisons.append(dict(id=case['id'], before=old['slide_cycles'],
                                        after=result['slide_cycles'],
                                        delta=result['slide_cycles']-old['slide_cycles']))
            (out / 'comparison.json').write_text(json.dumps(comparisons, indent=2) + '\n')
            status['comparison'] = dict(cases=len(comparisons),
                                        changed=sum(c['delta'] != 0 for c in comparisons))
    except Exception as exc:
        status.update(state='ERROR', error=repr(exc))
    finally:
        drift = [p for p, digest in pins.items()
                 if hashlib.sha256((out / p).read_bytes()).hexdigest() != digest]
        if drift:
            status.update(state='ERROR', snapshot_drift=drift)
        status['elapsed_seconds'] = round(time.monotonic()-start_time, 3)
        (out / 'status.json').write_text(json.dumps(status, indent=2) + '\n')
    print(json.dumps({k: v for k, v in status.items() if k != 'results'}, indent=2))
    print(f'Checked {len(status["results"])} / {len(cases)} cases; evidence: {out}')
    return 0 if status['state'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
