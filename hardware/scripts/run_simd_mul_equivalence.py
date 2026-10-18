#!/usr/bin/env python3
"""Freeze and compare simd_mul cycle behavior against pre-change git RTL."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, default=root / 'hardware/build/static_legacy_soc_v1/scalar')
    parser.add_argument('--out', type=Path, help='Must not already exist; default is a unique timestamp directory')
    parser.add_argument('--git-reference', default='HEAD')
    parser.add_argument('--timeout', type=int, default=1800)
    args = parser.parse_args()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    out = (args.out or root / 'hardware/build' / ('simd_mul_equivalence_unit_' + stamp)).resolve()
    out.mkdir(parents=True, exist_ok=False)
    ref = args.reference.resolve()
    source_manifest = ref / 'source_manifest.json'
    shutil.copy2(Path(__file__), out / Path(__file__).name)
    shutil.copy2(source_manifest, out / 'reference_source_manifest.json')
    shutil.copy2(ref / 'filelist', out / 'reference_filelist')
    lines = (ref / 'filelist').read_text().splitlines()
    excluded = ('/ara_tb.sv', '/ara_testharness.sv', '/vrf_perf_monitor.sv', '/ordered_area_profile.sv')
    lines = [line for line in lines if not line.endswith(excluded)]
    reference_commit = subprocess.check_output(['git', 'rev-parse', args.git_reference + '^{commit}'], cwd=root, text=True).strip()
    original = subprocess.check_output(['git', 'show', reference_commit + ':hardware/src/lane/simd_mul.sv'], cwd=root, text=True)
    original, count = re.subn(r'\bmodule\s+simd_mul\b', 'module simd_mul_reference', original)
    if count != 1:
        raise ValueError('Expected one reference module')
    original = re.sub(r'\bendmodule\s*:\s*simd_mul\b', 'endmodule : simd_mul_reference', original)
    (out / 'reference.sv').write_text(original)
    for source in (root / 'hardware/src/lane/simd_mul.sv', root / 'hardware/tb/simd_mul_equivalence_tb.sv'):
        frozen = out / source.name
        shutil.copy2(source, frozen)
        lines = [line for line in lines if not line.endswith('/' + source.name)]
        lines.append(str(frozen))
    lines.append(str(out / 'reference.sv'))
    filelist = out / 'filelist'
    filelist.write_text('\n'.join(lines) + '\n')
    command = list(json.loads(source_manifest.read_text())['command'])
    command[command.index('-top')+1] = 'simd_mul_equivalence_tb'
    command[command.index('-f')+1] = str(filelist)
    sources = {line: digest(Path(line)) for line in lines if Path(line).is_absolute() and Path(line).is_file()}
    # Freeze hashes of include files as well as explicit compilation units.
    includes = {}
    for line in lines:
        if line.startswith('+incdir+'):
            for directory in line[len('+incdir+'):].split('+'):
                for path in Path(directory).rglob('*'):
                    if path.is_file() and path.suffix in ('.svh', '.vh', '.h', '.sv'):
                        includes[str(path)] = digest(path)
    command_files = {arg: digest(Path(arg)) for arg in command
                     if Path(arg).is_absolute() and Path(arg).is_file()}
    manifest = {'command_files': command_files, 'reference': str(ref), 'reference_manifest_sha256': digest(source_manifest),
                'command': command, 'sources': sources, 'includes': includes,
                'runner_sha256': digest(Path(__file__)), 'reference_commit': reference_commit,
                'configurations': 24, 'cycles_per_configuration': 20288}
    run = ['./simv', '-no_save']
    manifest['run_command'] = run
    def save():
        (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    save()
    print(str(out), flush=True)
    for stage, cmd in [('compile', command), ('run', run)]:
        logpath = out / (stage + '.log')
        timed_out = False
        with logpath.open('w') as log:
            try:
                process = subprocess.run(cmd, cwd=out, stdout=log, stderr=subprocess.STDOUT, timeout=args.timeout)
                returncode = process.returncode
            except subprocess.TimeoutExpired:
                returncode = None
                timed_out = True
        text = logpath.read_text(errors='replace')
        errors = re.findall(r'^.*(?:Error-|Error:|Fatal:|\bFAIL\b|SIMD_MUL_FAIL|started at .*failed at).*$', text, re.M)
        passed = returncode == 0 and not errors and not timed_out
        if stage == 'run':
            passed = passed and 'SIMD_MUL_EQUIVALENCE_PASS configs=24 cycles_per_config=20288' in text and text.count('SIMD_MUL_CASE_PASS') == 24
        manifest[stage] = {'pass': passed, 'returncode': returncode, 'timeout': timed_out,
                           'errors': errors, 'log_sha256': digest(logpath)}
        save()
        if not passed:
            raise SystemExit('Failed; preserved log: ' + str(logpath))
    changed = [path for path, value in {**sources, **includes, **command_files}.items() if digest(Path(path)) != value]
    manifest['dependencies_unchanged'] = not changed
    manifest['changed_dependencies'] = changed
    save()
    if changed:
        raise SystemExit('Dependencies changed during run: ' + repr(changed))
    print((out / 'run.log').read_text())


if __name__ == '__main__':
    main()
