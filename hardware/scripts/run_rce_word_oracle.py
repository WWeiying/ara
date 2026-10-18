#!/usr/bin/env python3
"""Compile/test the actual RCE with source/ELF-style provenance and fail-closed logs."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--filelist', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--count', type=int, default=2640)
    p.add_argument('--fp64', action='store_true', help='FP64 add completion oracle')
    p.add_argument('--shared-completion', action='store_true', help='RCE shares an adder with four contending clients')
    p.add_argument('--seed-feedback', action='store_true', help='Also exercise the optional FP64 seed-feedback path')
    p.add_argument('--vector-seed', type=lambda s: int(s, 0))
    p.add_argument('--schedule-seed', type=lambda s: int(s, 0))
    p.add_argument('--hold-cycles', type=int, default=0)
    p.add_argument('--stress-seed-tuple', action='store_true')
    p.add_argument('--vcs', default='vcs')
    args = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    out = args.out.resolve()
    if out.exists() or not 100 <= args.count <= 20000 or not 0 <= args.hold_cycles <= 1024:
        p.error('use a new directory, 100..20000 cases and 0..1024 hold cycles')
    out.mkdir(parents=True)
    original = args.filelist.resolve().read_text().splitlines()
    # Keep dependency ordering, remove full-SoC TB hierarchy, inject new sources
    # so an immutable baseline filelist can be used before top-level integration.
    additions = [root/'hardware/include/ara_rce_pkg.sv',
                 root/'hardware/src/reduction/reduction_completion_engine.sv',
                 root/'hardware/tb/reduction_completion_engine_tb.sv']
    if args.shared_completion:
        if not args.fp64:
            p.error('shared completion requires --fp64')
        additions.append(root/'hardware/src/reduction/shared_ordered_adder.sv')
    # Accept both SoC lists and a previous frozen module list without
    # redeclaring an obsolete package/module after the current sources.
    replaced_names = {source.name for source in additions}
    lines = [s for s in original if '/hardware/tb/' not in s and
             '+define+FOR_VERIFY' not in s and Path(s).name not in replaced_names]
    package_positions = [i for i,s in enumerate(lines) if Path(s).name=='ara_pkg.sv']
    if len(package_positions)!=1:
        raise ValueError('Expected one ara_pkg.sv in reference filelist')
    pkg_pos = package_positions[0] + 1
    frozen = out/'rtl'; frozen.mkdir()
    for source in additions:
        shutil.copy2(source, frozen/source.name)
    lines.insert(pkg_pos, str(frozen/additions[0].name))
    lines += [str(frozen/a.name) for a in additions[1:]]
    if args.fp64:
        lines.insert(0, '+define+ARA_RED_RCE_FP64_SUM=1')
    if args.shared_completion:
        lines[:0]=['+define+ARA_RED_SHARED_RCE_ADD=1','+define+ARA_RED_TEST_SHARED_COMPLETION=1']
    if args.seed_feedback:
        lines.insert(0,'+define+ARA_RED_RCE_FP64_SEED_FEEDBACK=1')
    fl = out/'filelist'; fl.write_text('\n'.join(lines)+'\n')
    vectors = out/'vectors.txt'
    generator = root/'hardware/scripts'/('gen_rce_fp64_oracle.py' if args.fp64 else 'gen_rce_word_oracle.py')
    shutil.copy2(generator, out/generator.name)
    generator = out/generator.name
    shutil.copy2(Path(__file__), out/'runner.py')
    commands = [[sys.executable, str(generator), '--output', str(vectors), '--count', str(args.count)],
                [args.vcs,'-full64','-sverilog','-timescale=1ns/1ps','+define+SIMULATION',
                 '-assert','svaext','-top','reduction_completion_engine_tb',
                 '-f',str(fl),'-Mdir=csrc','-o',str(out/'simv')],
                [str(out/'simv'),'-no_save','+VECTOR_FILE='+str(vectors)]]
    if args.vector_seed is not None:
        commands[0] += ['--seed', str(args.vector_seed)]
    if args.schedule_seed is not None:
        commands[2] += ['+SCHEDULE_SEED='+str(args.schedule_seed)]
    commands[2] += ['+HOLD_CYCLES='+str(args.hold_cycles)]
    if args.stress_seed_tuple:
        commands[2] += ['+STRESS_SEED_TUPLE']
    sources = {Path(s) for s in lines if s.startswith('/') and Path(s).is_file()}
    for line in lines:
        if line.startswith('+incdir+'):
            for directory in line[len('+incdir+'):].split('+'):
                sources.update(p for p in Path(directory).rglob('*')
                               if p.is_file() and p.suffix in ('.sv', '.svh', '.v', '.vh'))
    sources.update([generator, fl, out/'runner.py'])
    source_hashes = {str(s):hashlib.sha256(s.read_bytes()).hexdigest() for s in sorted(sources)}
    manifest = {'commands':commands, 'pass':False, 'count':args.count,
                'input_sha256':source_hashes,
                'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()}
    for command,name in zip(commands,['generate','compile','run']):
        with (out/(name+'.log')).open('w') as log:
            result = subprocess.run(command,cwd=out,stdout=log,stderr=subprocess.STDOUT,timeout=300)
        manifest[name+'_returncode'] = result.returncode
        (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        if result.returncode:
            sys.exit(f'{name} failed: {out/(name+".log")}')
    log = (out/'run.log').read_text()
    failures = re.findall(r'^.*(?:Error:|Fatal:|\bFAIL\b|failed at).*$' ,log,re.M)
    manifest.update(failures=failures,pass_marker=f'PASS: {args.count} RCE word cases')
    drift = [s for s, h in source_hashes.items() if hashlib.sha256(Path(s).read_bytes()).hexdigest() != h]
    manifest['source_drift'] = drift
    manifest['pass'] = not failures and not drift and manifest['pass_marker'] in log
    manifest['sha256'] = {str(s):hashlib.sha256(s.read_bytes()).hexdigest()
                          for s in sorted(sources)+[vectors,out/'simv',out/'run.log']}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(log)
    sys.exit(0 if manifest['pass'] else 1)


if __name__ == '__main__':
    main()
