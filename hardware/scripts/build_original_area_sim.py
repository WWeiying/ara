#!/usr/bin/env python3
"""Compile the prepared original-area RTL with the same SoC simulation environment.

Uses frozen synthesis RTL, but simulation dependencies/testbench from an existing
validated build. Records both sources; does not run synthesis or waive failures.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
from run_reduction_audit import sha256


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepared', type=Path, required=True)
    p.add_argument('--reference', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    prepared, reference, out = [x.resolve() for x in (args.prepared, args.reference, args.out)]
    manifest = json.loads((prepared / 'manifest.json').read_text())
    assert manifest['profile'] == 'original_30c6971b'
    ref = json.loads((reference / 'source_manifest.json').read_text())
    for path, digest in ref['sources'].items():
        assert sha256(Path(path)) == digest, path
    originals = {}
    for record in manifest['frozen_files']:
        assert sha256(prepared / record['snapshot']) == record['sha256']
        path = record.get('original', '')
        if str(prepared / 'workspace/hardware') + '/' in path:
            originals[Path(path).name] = prepared / record['snapshot']
    assert 'ara.sv' in originals and 'ara_pkg.sv' in originals
    out.mkdir(parents=True, exist_ok=False)
    rtl = out / 'rtl'
    rtl.mkdir()
    for name, source in originals.items():
        shutil.copy2(source, rtl / name)
    include_root = rtl / 'include'
    include_root.mkdir()
    for record in manifest['frozen_files']:
        prefix = str(prepared / 'workspace/hardware/include') + '/'
        original = record.get('original', '')
        if original.startswith(prefix):
            target = include_root / original[len(prefix):]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(prepared / record['snapshot'], target)
    removed = {'ara_rce_pkg.sv', 'fp32_exact_reduction_accum.sv',
               'fp32_exact_reduction_finalize.sv', 'reduction_completion_engine.sv',
               'shared_ordered_adder.sv', 'ordered_area_profile.sv'}
    # Read-only counters bound to RCE/internal signals absent in the original.
    # Architectural testbench and RTL assertions remain enabled.
    removed.update({'reduction_stall_profile.sv', 'reduction_throughput_profile.sv'})
    lines = []
    for line in (reference / 'filelist').read_text().splitlines():
        if line.startswith('+define+ARA_RED_'):
            continue
        if line.startswith('+incdir+') and line.endswith('/hardware/include'):
            line = '+incdir+' + str(include_root)
        elif line.startswith('/'):
            name = Path(line).name
            if name in removed:
                continue
            if name in originals:
                line = str(rtl / name)
        lines.append(line)
    filelist = out / 'filelist'
    filelist.write_text('\n'.join(lines) + '\n')
    command = ref['command'].copy()
    command[command.index('-f') + 1] = str(filelist)
    provenance = {'command': command, 'prepared': str(prepared),
                  'prepared_manifest_sha256': sha256(prepared / 'manifest.json'),
                  'sources': {line: sha256(Path(line)) for line in lines if line.startswith('/')},
                  'headers': {str(f): sha256(f) for f in include_root.rglob('*') if f.is_file()},
                  'note': 'Original RTL plus recorded CSR overlay; same simulation environment; not a correctness claim'}
    (out / 'source_manifest.json').write_text(json.dumps(provenance, indent=2) + '\n')
    with (out / 'compile.stdout.log').open('w') as log:
        result = subprocess.run(command, cwd=out, stdout=log, stderr=subprocess.STDOUT)
    (out / 'build_status.json').write_text(json.dumps({'returncode': result.returncode,
        'simulator_present': (out / 'simv').exists()}) + '\n')
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
