#!/usr/bin/env python3
"""Run the sparse exact RCE window protocol and integer-oracle test using a frozen SoC list."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--filelist', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--vcs', default='vcs')
    parser.add_argument('--mode', choices=['legacy', 'compact', 'mixed'], default='mixed')
    parser.add_argument('--seed-fold', action='store_true')
    parser.add_argument('--seed-receive', type=int, choices=[0,1], default=1)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    frozen = out / 'rtl'
    frozen.mkdir()
    additions = [root / ('hardware/' + name) for name in [
        'include/ara_rce_pkg.sv', 'src/lane/fp32_exact_reduction_finalize.sv',
        'src/reduction/reduction_completion_engine.sv',
        'src/reduction/shared_scalar_fp_add.sv', 'src/reduction/shared_ordered_adder.sv',
        'tb/rce_exact_window_tb.sv']]
    replaced = {p.name for p in additions}
    lines = [s for s in args.filelist.resolve().read_text().splitlines()
             if '/hardware/tb/' not in s and '+define+FOR_VERIFY' not in s
             and Path(s).name not in replaced
             and not s.startswith('+define+ARA_RED_RCE_EXACT_SEED_RECEIVE')]
    pkg_pos = next(i for i, s in enumerate(lines) if Path(s).name == 'ara_pkg.sv') + 1
    for source in additions:
        shutil.copy2(source, frozen / source.name)
    lines.insert(pkg_pos, str(frozen / additions[0].name))
    lines += [str(frozen / p.name) for p in additions[1:]]
    lines.insert(0, '+define+ARA_RED_RCE_EXACT_DECOUPLE=1')
    fl = out / 'filelist'
    fl.write_text('\n'.join(lines) + '\n')
    shutil.copy2(__file__, out / 'runner.py')
    generator = root / 'hardware/scripts/gen_rce_exact_window.py'
    vectors = out / 'vectors.txt'
    shutil.copy2(generator, out / generator.name)
    subprocess.run(['python', str(generator), '--output', str(vectors), '--mode', args.mode, '--seed-receive', str(args.seed_receive)] + (['--seed-fold'] if args.seed_fold else []), check=True)
    if args.seed_receive:
        lines.insert(0, '+define+ARA_RED_RCE_EXACT_SEED_RECEIVE=1')
    fl.write_text('\n'.join(lines) + '\n')
    commands = [
        [args.vcs, '-full64', '-sverilog', '-timescale=1ns/1ps', '+define+SIMULATION',
         '-assert', 'svaext', '-top', 'rce_exact_window_tb', '-f', str(fl),
         '-Mdir=csrc', '-o', str(out / 'simv')],
        [str(out / 'simv'), '-no_save', '+VECTOR_FILE=' + str(vectors), '+EXPECT_CASES=' + str(len(vectors.read_text().splitlines())), '+SEED_FOLD=' + str(int(args.seed_fold))]]
    manifest = {'mode': args.mode, 'seed_receive': args.seed_receive, 'commands': commands, 'pass': False,
                'oracle_sha256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in [generator, root / 'hardware/scripts/gen_exact_reduction_oracle.py', vectors]},
                'source_sha256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in sorted(frozen.iterdir())}}
    for stage, command in zip(['compile', 'run'], commands):
        log = out / (stage + '.log')
        with log.open('w') as stream:
            proc = subprocess.run(command, cwd=out, stdout=stream, stderr=subprocess.STDOUT,
                                  timeout=300)
        body = log.read_text(errors='replace')
        failures = re.findall(r'^.*(?:Error-|Error:|Fatal:|\bFAIL\b|failed at).*$', body, re.M)
        manifest[stage] = {'returncode': proc.returncode, 'failures': failures}
        (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        if proc.returncode or failures:
            raise SystemExit('Failed: ' + str(log))
    manifest['pass'] = 'RCE_EXACT_WINDOW_PASS' in body
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(body)
    if not manifest['pass']:
        raise SystemExit('Missing pass marker')


if __name__ == '__main__':
    main()
