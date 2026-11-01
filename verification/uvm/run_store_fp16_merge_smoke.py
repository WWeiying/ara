#!/usr/bin/env python3
"""Bounded post-integration checks using frozen pre-integration ELF inputs."""
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('source_worktree', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--frozen-inputs', type=Path,
                        help='Reuse CASE/input.elf from a previous frozen smoke run')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    image, source, out = (p.resolve() for p in
                          (args.image, args.source_worktree, args.output))
    out.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, PYTHONPATH=str(root / 'verification'))
    subprocess.run(['python3', '-m', 'ara_verify.vcs_source_manifest', '--check',
                    '--output', str(image / 'sim/vcs_source_manifest.json')],
                   cwd=root, env=env, check=True)
    cases = {
        'axpy': source / 'verification/out/store-fp16-image-20260926-04/work/input.elf',
        'csr': source / 'verification/out/vec-fp-csr-order-20260926-02/inputs/vec_fp_csr_order.elf',
        'div_mask': source / 'verification/out/vfdiv-mask-flags-20260926-01/inputs/vfdiv_mask_flags.elf',
        'store_fault': source / 'verification/out/store-fp16-regress-20260926-04/inputs/vstore_axi_error.elf',
        'store_bursts': root / 'apps/bin/rv64uv-ara-vstore_axi_error_bursts',
        'mask_illegal': root / 'apps/bin/rv64uv-ara-vmask_dest_overlap_illegal',
        'group_illegal': root / 'apps/bin/rv64uv-ara-vregister_group_illegal',
    }
    if args.frozen_inputs:
        frozen_root = args.frozen_inputs.resolve()
        expected_hashes = json.loads((frozen_root / 'input_sha256.json').read_text())
        cases = {name: frozen_root / name / 'input.elf' for name in cases}
        for name, elf in cases.items():
            if hashlib.sha256(elf.read_bytes()).hexdigest() != expected_hashes[name]:
                raise ValueError(f'Frozen input digest mismatch: {name}')
    frozen = {}
    for name, elf in cases.items():
        case = out / name
        case.mkdir()
        shutil.copy2(elf, case / 'input.elf')
        frozen[name] = hashlib.sha256((case / 'input.elf').read_bytes()).hexdigest()
    (out / 'input_sha256.json').write_text(json.dumps(frozen, indent=2) + '\n')

    def run(name):
        case = out / name
        simv = image / 'sim/simv'
        with (case / 'console.log').open('w') as log:
            rc = subprocess.run(['timeout', '--foreground', '600', str(simv),
                '-no_save', '-l', 'run.vcs.log', f'+PRELOAD={case / "input.elf"}',
                '+NO_FSDB', f'+VECTOR_TRACE={case / "vector_trace.csv"}',
                '+ARA_CONTRACT_TRACE_LIMIT=100000', '+ARA_UVM_TRACE_LIMIT=100000'],
                cwd=case, stdout=log, stderr=subprocess.STDOUT).returncode
        text = (case / 'run.vcs.log').read_text(errors='replace')
        ok = rc == 0 and not re.search(r'^FAIL(?:[ :]|$)|FAILED|Fatal:|Error:', text, re.M)
        if name != 'axpy':
            ok &= 'PASSED' in text
        if name == 'csr':
            ok &= 'vec_fp_csr_order: 21 cases, 762 checks, traps=2' in text
        if name == 'div_mask':
            ok &= 'vfdiv_mask_flags: 52 cases, 1612 checks' in text
        report = case / 'uvm_result.json'
        checked = subprocess.run(['python3', '-m', 'ara_verify.uvm_dut',
            '--require-events', '--require-backend', '--vector-trace', 'vector_trace.csv',
            '--log', 'run.vcs.log', '--simv', str(simv), '--elf', 'input.elf',
            '--output', str(report)], cwd=case, env=env, capture_output=True, text=True)
        (case / 'checker.log').write_text(checked.stdout + checked.stderr)
        ok &= checked.returncode == 0 and report.is_file() and json.loads(report.read_text())['status'] == 'PASS'
        ok &= hashlib.sha256((case / 'input.elf').read_bytes()).hexdigest() == frozen[name]
        cycles = re.search(r'\[PERF\] total_cycles\s*:\s*(\d+)', text)
        result = {'name': name, 'status': 'PASS' if ok else 'FAIL', 'returncode': rc,
                  'cycles': int(cycles[1]) if cycles else None}
        print(json.dumps(result), flush=True)
        return result

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        for future in concurrent.futures.as_completed([pool.submit(run, n) for n in cases]):
            results.append(future.result())
            (out / 'summary.json').write_text(json.dumps(results, indent=2) + '\n')
    passed = len(results) == len(cases) and all(r['status'] == 'PASS' for r in results)
    (out / 'completion.json').write_text(json.dumps({'status': 'PASS' if passed else 'FAIL',
        'expected_tests': len(cases), 'finished_tests': len(results)}, indent=2) + '\n')
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
