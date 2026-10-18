#!/usr/bin/env python3
"""Exercise real shared fpnew arithmetic, ownership and backpressure for 1/2 units."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True, help='Frozen shared-ordered SoC build with dependencies')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--completion-client', action='store_true', help='Also exercise a fifth FP64 completion client')
    parser.add_argument('--compact-ordered-backend', action='store_true')
    parser.add_argument('--static-ordered-arbiter', action='store_true')
    parser.add_argument('--legacy-module', type=Path, help='Frozen pre-change module for cycle-by-cycle equivalence')
    parser.add_argument('--candidate-module', type=Path, help='Override candidate shared_ordered_adder source')
    parser.add_argument('--extra-source', type=Path, action='append', default=[],
                        help='Additional source before the candidate (repeatable, ordered)')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    reference = args.reference.resolve()
    lines = (reference / 'filelist').read_text().splitlines()
    # SoC testbench compilation-unit tasks contain absolute ara_tb XMRs and
    # cannot be elaborated under a standalone unit top. Keep the real RTL/libs.
    lines = [line for line in lines if not line.endswith((
        '/ara_tb.sv', '/ara_testharness.sv', '/vrf_perf_monitor.sv', '/ordered_area_profile.sv'))]
    tb = out / 'shared_ordered_adder_tb.sv'
    shutil.copy2(root / 'hardware/tb' / tb.name, tb)
    # Use current candidate module with reference's exact library dependencies.
    module = out / 'shared_ordered_adder.sv'
    candidate = args.candidate_module or root / 'hardware/src/reduction' / module.name
    shutil.copy2(candidate, module)
    indices = [i for i, line in enumerate(lines) if line.endswith('/' + module.name)]
    if len(indices) != 1:
        raise ValueError('reference must contain one shared ordered module')
    extras = []
    for index, source in enumerate(args.extra_source):
        frozen = out / f'extra_{index}_{source.name}'
        shutil.copy2(source, frozen)
        extras.append(str(frozen))
    lines[indices[0]:indices[0]+1] = extras + [str(module)]
    lines.append(str(tb))
    if args.legacy_module:
        legacy = out / 'shared_ordered_adder_legacy.sv'
        original = args.legacy_module.read_text()
        assert original.count('module shared_ordered_adder ') == 1
        legacy.write_text(original.replace('module shared_ordered_adder ', 'module shared_ordered_adder_legacy ', 1))
        lines.append(str(legacy))
    (out / 'filelist').write_text('\n'.join(lines) + '\n')
    command = json.loads((reference / 'source_manifest.json').read_text())['command']
    command[command.index('-top')+1] = 'shared_ordered_adder_tb'
    command[command.index('-f')+1] = str(out / 'filelist')
    if args.completion_client:
        command.append('+define+ARA_RED_TEST_COMPLETION_CLIENT=1')
    if args.compact_ordered_backend:
        command.append('+define+ARA_RED_COMPACT_ORDERED_BACKEND=1')
    if args.static_ordered_arbiter:
        command.append('+define+ARA_RED_STATIC_ORDERED_ARBITER=1')
    if args.legacy_module:
        command.append('+define+ARA_RED_TEST_LEGACY_EQUIVALENCE=1')
    manifest = {'command': command, 'candidate_module': str(candidate.resolve()),
                'extra_sources': [str(source.resolve()) for source in args.extra_source], 'sources': {p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
                                             for p in lines if p.startswith('/') and Path(p).is_file()}}
    for stage, cmd in [('compile', command), ('run', ['./simv', '-no_save'])]:
        logpath = out / (stage + '.log')
        with logpath.open('w') as log:
            process = subprocess.run(cmd, cwd=out, stdout=log, stderr=subprocess.STDOUT, timeout=600)
        text = logpath.read_text(errors='replace')
        errors = re.findall(r'^.*(?:Error-|Error:|Fatal:|\bFAIL\b|started at .*failed at).*$', text, re.M)
        passed = process.returncode == 0 and not errors and (stage == 'compile' or
                  ('SHARED_ORDERED_ADDER_PASS' in text and text.count('SHARED_ORDERED_CASE_PASS') == (4 if args.completion_client else 2)))
        manifest[stage] = {'pass': passed, 'returncode': process.returncode, 'errors': errors,
                           'log_sha256': hashlib.sha256(logpath.read_bytes()).hexdigest()}
        (out / 'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
        if not passed:
            raise SystemExit('Failed: '+str(logpath))
    print((out / 'run.log').read_text())


if __name__ == '__main__':
    main()
