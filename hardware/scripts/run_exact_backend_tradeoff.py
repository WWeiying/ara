#!/usr/bin/env python3
"""Freeze and run exact-family and representation ablations with one ELF.

exact_off disables the entire exact family, including its communication and
overlap controls. It does NOT isolate the arithmetic accumulator alone.
banked removes only exponent segmentation; exact rounding/protocol stay on.
"""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def exact_off_define(line):
    """Remove exact-family controls and their dependent forwarding options."""
    name = line.split('=')[0]
    return name.startswith('+define+ARA_RED_') and (
        'EXACT' in name or name in {
            '+define+ARA_RED_CHAIN_BYPASS_4LANE',
            '+define+ARA_RED_SHARED_FORWARD_CAPTURE',
            '+define+ARA_RED_ROOT_ONLY_RESULT_CACHE',
            '+define+ARA_RED_PRUNE_LEGACY_FP_STREAM',
            '+define+ARA_RED_SHARED_FINALIZE_EXTRACT',
        })


def main():
    root = Path(__file__).resolve().parents[2]
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--jobs', type=int, default=2)
    p.add_argument('--prepare-only', action='store_true')
    a = p.parse_args()
    if a.jobs < 1:
        p.error('jobs must be positive')
    reference, out = a.reference.resolve(), a.out.resolve()
    manifest = json.loads((reference / 'source_manifest.json').read_text())
    for name, digest in manifest['sources'].items():
        if sha(Path(name)) != digest:
            raise ValueError('Reference source changed: ' + name)
    out.mkdir(parents=True, exist_ok=False)
    elf_dir = out / 'elfs'
    elf_dir.mkdir()
    app = 'perf_exact_backend_tradeoff'
    shutil.copy2(root / 'apps/bin' / app, elf_dir / app)
    shutil.copy2(root / 'apps' / app / 'main.c', out / 'benchmark.c')
    files, lines = {}, []
    def freeze(source):
        source = Path(source)
        target = out / 'frozen' / str(source).lstrip('/')
        if str(source) not in files:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            files[str(source)] = {'snapshot': str(target), 'sha256': sha(target)}
        return target
    for line in (reference / 'filelist').read_text().splitlines():
        if line.startswith('/'):
            # Read-only observers require optional exact-internal state.
            if Path(line).name in {'reduction_stall_profile.sv', 'reduction_throughput_profile.sv', 'ordered_area_profile.sv'}:
                continue
            line = str(freeze(line))
        elif line.startswith('+incdir+'):
            paths = []
            for name in line[len('+incdir+'):].split('+'):
                inc = Path(name)
                target = out / 'frozen' / str(inc).lstrip('/')
                target.mkdir(parents=True, exist_ok=True)
                for source in inc.rglob('*'):
                    if source.is_file() and source.suffix in {'.svh', '.vh', '.h', '.sv', '.v'}:
                        freeze(source)
                paths.append(str(target))
            line = '+incdir+' + '+'.join(paths)
        lines.append(line)
    modes = {}
    for mode in ['full', 'banked', 'exact_off']:
        selected = lines.copy()
        if mode == 'banked':
            selected = [s for s in selected if not s.startswith('+define+ARA_RED_EXACT_SEGMENTED_4LANE')]
        elif mode == 'exact_off':
            selected = [s for s in selected if not exact_off_define(s)]
        directory = out / mode
        directory.mkdir()
        filelist = directory / 'filelist'
        filelist.write_text('\n'.join(selected) + '\n')
        command = manifest['command'].copy()
        command[command.index('-f') + 1] = str(filelist)
        modes[mode] = {'command': command, 'defines': [s for s in selected if s.startswith('+define+ARA_RED_')]}
    config = {'reference': str(reference), 'sources': files, 'modes': modes,
              'apps': [app], 'elf_sha256': sha(elf_dir / app),
              'scope': 'full vs exact_off is exact-family benefit; full vs banked is representation benefit; simulation cycles, not Fmax or area'}
    (out / 'configuration.json').write_text(json.dumps(config, indent=2) + '\n')
    if a.prepare_only:
        return
    def run(mode):
        directory = out / mode
        with (directory / 'compile.log').open('w') as log:
            subprocess.run(modes[mode]['command'], cwd=directory, stdout=log, stderr=subprocess.STDOUT, check=True)
        audit = [sys.executable, str(root / 'hardware/scripts/run_reduction_audit.py'),
                 '--elf-dir', str(elf_dir),
                 '--sim', str(directory / 'simv'), '--out', str(directory / 'regression'),
                 '--jobs', '1', '--timeout', '3600', *config['apps']]
        with (directory / 'audit.log').open('w') as log:
            subprocess.run(audit, cwd=root, stdout=log, stderr=subprocess.STDOUT, check=True)
        print(mode + ' complete', flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.jobs) as pool:
        futures = [pool.submit(run, mode) for mode in modes]
        for future in futures:
            future.result()


if __name__ == '__main__':
    main()
