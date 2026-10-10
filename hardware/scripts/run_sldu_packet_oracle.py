#!/usr/bin/env python3
"""Compile and run the SLDU packet oracle with an existing Ara VCS filelist."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--filelist', type=Path, required=True,
                        help='bender_script_default from a complete four-lane build')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--count', type=int, default=1200)
    parser.add_argument('--vcs', default='vcs')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    out = args.out.resolve()
    if out.exists():
        parser.error('choose a new output directory to preserve evidence')
    if args.count <= 0:
        parser.error('count must be positive')
    original = args.filelist.resolve().read_text()
    if '+define+ARA_RED_EXACT_GLOBAL_4LANE' not in original:
        parser.error('filelist must enable the global exact backend')
    compiler = shutil.which(args.vcs)
    if not compiler:
        parser.error('VCS executable was not found')
    out.mkdir(parents=True)
    # ara_tb contains compilation-unit tasks with hierarchical references to
    # the full SoC. They cannot be elaborated under this standalone top.
    filelist = out / 'filelist'
    filelist.write_text('\n'.join(line for line in original.splitlines()
                                 if '/hardware/tb/' not in line and
                                 '+define+FOR_VERIFY' not in line) + '\n')
    tb = root / 'hardware/tb/sldu_packet_oracle_tb.sv'
    generator = root / 'hardware/scripts/gen_sldu_packet_oracle.py'
    vectors = out / 'vectors.txt'
    commands = [
        [sys.executable, str(generator), '--output', str(vectors), '--count', str(args.count)],
        [compiler, '-full64', '-sverilog', '-timescale=1ns/1ps', '+define+SIMULATION',
         '-top', 'sldu_packet_oracle_tb', '-f', str(filelist), str(tb),
         '-Mdir=csrc', '-o', str(out / 'simv')],
        [str(out / 'simv'), '-no_save', '+VECTOR_FILE=' + str(vectors)],
    ]
    manifest = {'commands': commands, 'requested_cases': args.count, 'pass': False}
    for command, name in zip(commands, ['generate', 'compile', 'run']):
        with (out / (name + '.log')).open('w') as log:
            result = subprocess.run(command, cwd=out, stdout=log, stderr=subprocess.STDOUT, timeout=300)
        manifest[name + '_returncode'] = result.returncode
        (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        if result.returncode:
            sys.exit(f'{name} failed; see {out / (name + ".log")}')
    output = (out / 'run.log').read_text()
    manifest['failures'] = re.findall(r'^.*(?:Error:|Fatal:|\bFAIL\b|started at .*failed at).*$', output, re.M)
    manifest['pass'] = not manifest['failures'] and f'PASS: {args.count} SLDU packet cases' in output
    inputs = [tb, generator, root / 'hardware/scripts/gen_exact_reduction_oracle.py',
              root / 'hardware/src/sldu/sldu.sv',
              root / 'hardware/src/lane/fp32_exact_reduction_finalize.sv',
              filelist, vectors, out / 'simv']
    manifest['sha256'] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'{"PASS" if manifest["pass"] else "FAIL"}: {args.count} SLDU packet cases; {out}')
    sys.exit(0 if manifest['pass'] else 1)


if __name__ == '__main__':
    main()
