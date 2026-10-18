#!/usr/bin/env python3
"""Freeze and verify exact-reduction area candidates against the pre-change RTL."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--reference', default='13dfca21955dfd4e05905e92e4afaff7b7b579b6')
    parser.add_argument('--vcs', default='vcs')
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--collision-forward', action='store_true', help='Enable candidate in independent numerical oracle')
    parser.add_argument('--compact-segments', action='store_true', help='Compare 32-bit exponent windows against the original representation')
    parser.add_argument('--direct-bin-read', action='store_true')
    parser.add_argument('--wide-segments', action='store_true')
    parser.add_argument('--cases', type=int, default=300, help='Accumulator differential transactions')
    parser.add_argument('--reference-accumulator', type=Path, help='Frozen accumulator RTL instead of git version for accumulator equivalence')
    parser.add_argument('--block', action='append', choices=['finalize','accum','oracle'], help='Run selected blocks; default all')
    args = parser.parse_args()
    if args.cases <= 0:
        parser.error('--cases must be positive')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    reference = subprocess.check_output(
        ['git', 'rev-parse', args.reference + '^{commit}'], cwd=root, text=True).strip()
    jobs = []
    for name, top, marker in (
        ('finalize', 'exact_finalize_equivalence_tb', 'EXACT_FINALIZE_EQUIVALENCE_PASS cases=56736'),
        ('accum', 'exact_update_equivalence_tb', f'EXACT_UPDATE_EQUIVALENCE_PASS cases={args.cases} configs=12'),
        ('oracle', 'fp_exact_reduction_oracle_tb', 'PASS: exact integer oracle (900 '),
    ):
        if args.block and name not in args.block:
            continue
        directory = out / name
        directory.mkdir()
        modules = [name] if name != 'oracle' else ['accum', 'finalize']
        sources = []
        for suffix in modules:
            module = 'fp32_exact_reduction_' + suffix
            path = Path('hardware/src/lane') / (module + '.sv')
            shutil.copy2(root / path, directory / path.name)
            sources.append(path.name)
            if name != 'oracle':
                original = subprocess.check_output(
                    ['git', 'show', reference + ':' + str(path)], cwd=root, text=True)
                if suffix == 'accum' and args.reference_accumulator:
                    original = args.reference_accumulator.read_text()
                original, count = re.subn(r'\bmodule\s+' + module + r'\b',
                                          'module ' + module + '_reference', original)
                if count != 1:
                    raise ValueError('Expected one reference module')
                (directory / 'reference.sv').write_text(original)
                sources.insert(0, 'reference.sv')
        shutil.copy2(root / 'hardware/tb' / (top + '.sv'), directory / (top + '.sv'))
        sources.append(top + '.sv')
        defines, runtime = [], []
        if name == 'accum':
            runtime.append('+TEST_CASES=' + str(args.cases))
        if name == 'oracle':
            vector = 'fp_exact_reduction_oracle_vectors.mem'
            shutil.copy2(root / 'hardware/tb' / vector, directory / vector)
            defines = ['+define+ARA_RED_SHARED_FINALIZE_EXTRACT',
                       '+define+ARA_RED_SHARED_EXACT_UPDATE',
                       '+define+ARA_RED_SHARED_EXACT_NORMALIZE']
            runtime = ['+VECTOR_FILE=' + vector]
        if args.collision_forward:
            defines.append('+define+ARA_RED_EXACT_COLLISION_FORWARD=1')
        if args.compact_segments:
            defines.append('+define+ARA_RED_COMPACT_EXACT_SEGMENTS=1')
        if args.direct_bin_read:
            defines.append('+define+ARA_RED_EXACT_DIRECT_BIN_READ=1')
        if args.wide_segments:
            defines.append('+define+ARA_RED_WIDE_EXACT_SEGMENTS=1')
        if name == 'accum' and args.reference_accumulator and not args.wide_segments:
            defines.append('+define+ARA_RED_TEST_STRICT_EXACT_PAYLOAD=1')
        command = [args.vcs, '-full64', '-sverilog', '-timescale=1ns/1ps',
                   *defines, *sources, '-top', top, '-o', 'simv']
        manifest = {'reference_commit': reference, 'command': command,
                    'reference_accumulator_override': str(args.reference_accumulator.resolve()) if args.reference_accumulator else None,
                    'runtime_arguments': runtime, 'required_marker': marker,
                    'sources': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in directory.iterdir() if p.suffix in ('.sv', '.mem')}}
        (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        jobs.append((directory, command, runtime, marker, manifest))
    if args.prepare_only:
        print('Prepared: ' + str(out))
        return
    for directory, command, runtime, marker, manifest in jobs:
        for stage, cmd in [('compile', command), ('run', ['./simv', *runtime])]:
            path = directory / (stage + '.log')
            with path.open('w') as log:
                process = subprocess.run(cmd, cwd=directory, stdout=log,
                                         stderr=subprocess.STDOUT, timeout=1200)
            output = path.read_text(errors='replace')
            failures = re.findall(r'^.*(?:Fatal:|Error:|Error-\[|\bFAIL\b|started at .*failed at).*$',
                                  output, re.M)
            good = process.returncode == 0 and not failures and (stage == 'compile' or marker in output)
            manifest[stage] = {'returncode': process.returncode, 'pass': good,
                               'failures': failures, 'log_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
            (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
            if not good:
                raise SystemExit('Failed: ' + str(path))
        print('PASS ' + directory.name, flush=True)


if __name__ == '__main__':
    main()
