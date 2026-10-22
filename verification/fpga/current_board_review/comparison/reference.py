#!/usr/bin/env python3
"""Bounded Spike self-oracle checks, never a VCS or Linux-original acceptance."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, '/home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/integration')
from prepare import ROOT, check, save, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--programs', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--spike', type=Path,
                        default=Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike'))
    parser.add_argument('--case', action='append')
    args = parser.parse_args()
    programs = json.loads((args.programs / 'programs.json').read_text())
    if programs['backend'] != 'spike-htif':
        raise ValueError('refuse SoC UART/exit ELF on Spike')
    prepared = Path(programs['prepared'])
    check(prepared)
    if sha(prepared / 'provenance.json') != programs['provenance_sha256']:
        raise ValueError('prepared identity changed')
    args.out.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(ROOT / 'verification'))
    from ara_verify.spike_probe import check_spike_vstart, probe_paths
    cc, source = probe_paths(ROOT)
    probe = check_spike_vstart(args.spike, cc, args.out / 'vstart_probe', source)
    if probe['status'] != 'PASS':
        raise ValueError('Spike does not support the required nonzero-vstart semantics')
    results = []
    for name in args.case or list(programs['programs']):
        case = programs['programs'][name]
        elf = Path(case['path'])
        if sha(elf) != case['sha256']:
            raise ValueError('ELF drift: ' + name)
        command = [str(args.spike.resolve()), '--isa=rv64gcv_zvfh_zvl1024b', '-m2', str(elf)]
        start = time.monotonic()
        with (args.out / (name + '.log')).open('w') as log:
            try:
                process = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=15)
                rc = process.returncode
            except subprocess.TimeoutExpired:
                rc = None
        results.append(dict(name=name, command=command, elf_sha256=sha(elf), returncode=rc,
                            status='PASS' if rc == 0 else 'FAIL', elapsed_s=time.monotonic()-start))
    save(args.out / 'reference.json', dict(scope='ported C/fixture self-oracles on Spike HTIF',
         not_original_program_acceptance=True, not_rtl_comparison=True,
         spike=dict(path=str(args.spike.resolve()), sha256=sha(args.spike)),
         provenance_sha256=programs['provenance_sha256'], results=results,
         status='PASS' if all(r['status'] == 'PASS' for r in results) else 'FAIL'))
    print(json.dumps(results, indent=2))
    return int(any(r['status'] != 'PASS' for r in results))


if __name__ == '__main__':
    raise SystemExit(main())
