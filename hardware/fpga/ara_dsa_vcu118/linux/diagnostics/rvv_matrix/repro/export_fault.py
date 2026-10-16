"""Export measured replay singles with their three-way control evidence."""
import argparse
import json
from pathlib import Path
import shutil
from audit_fault_controls import audit as audit_controls
from audit_fault_single import audit as audit_single
from audit_slide import require
from trace_masks import sha


def export(root, controls, proof_dir, original_report, out):
    manifest = json.loads((root / 'manifest.json').read_text())
    require(sha(controls / 'manifest.json') == manifest['controls_manifest_sha256'],
            'Control manifest changed')
    checked = audit_single(root, proof_dir / 'sampled_report.json')
    require(checked == json.loads((proof_dir / 'symptoms.json').read_text()),
            'Single audit differs from evidence')
    control_proof = audit_controls(controls, original_report, root / 'measured_report.json')
    require(len(control_proof['cases']) == 3 and
            all(c['aggregate_original_symptom_matches'] for c in control_proof['cases']),
            'Three-way aggregate agreement missing')
    selected = [r for r in checked['cases'] if r['confirmed']]
    require(selected, 'No confirmed single trials')
    cases = {c['name']: c for c in manifest['cases']}
    cm = json.loads((controls / 'manifest.json').read_text())
    for c in list(cases.values()) + cm['cases']:
        require(Path(c['name']).name == c['name'] and c['name'] not in ('.', '..'),
                'Unsafe case name')
        for file in c.get('scenario_sources', {}):
            require(Path(file).name == file and file not in ('.', '..'), 'Unsafe filename')
    out.mkdir(exist_ok=False)
    evidence = out / 'evidence'; evidence.mkdir()
    for source, name in ((root / 'manifest.json', 'single_manifest.json'),
                         (controls / 'manifest.json', 'controls_manifest.json'),
                         (root / 'measured_report.json', 'controls_board_report.json'),
                         (original_report, 'original_board_report.json'),
                         (proof_dir / 'sampled_report.json', 'single_board_report.json'),
                         (proof_dir / 'symptoms.json', 'single_symptoms.json')):
        shutil.copy2(source, evidence / name)
    (evidence / 'control_symptoms.json').write_text(json.dumps(control_proof, indent=2) + '\n')
    for source_root, members, group_name in (
            (controls, cm['cases'], 'controls'),
            (root, [cases[r['name']] for r in selected], 'singles')):
        group = out / group_name; group.mkdir()
        for c in members:
            target = group / c['name']; target.mkdir()
            shutil.copy2(source_root / 'binaries' / c['name'], target / 'scenario.elf')
            source_dir = source_root / c.get('source_directory', c['name'])
            for file in c.get('scenario_sources', {}):
                shutil.copy2(source_dir / file, target / file)
            (target / 'case.json').write_text(json.dumps(c, indent=2) + '\n')
    index = dict(exported_cases=len(selected), original_failure_equivalence_proven=False,
                 internal_rtl_root_cause_proven=False, complete_historical_coverage=False,
                 scope='Exact single-trial signatures versus current full trace; old original aggregate only',
                 cases=selected)
    (out / 'index.json').write_text(json.dumps(index, indent=2) + '\n')
    (out / 'README.txt').write_text(
        'Board-confirmed fault-replay single trials\n\n'
        'Each single preserves its measured full-trace trigger and fault signature.\n'
        'The unchanged old original, current baseline and current trace agree only in aggregate.\n'
        'Old-original per-trial equivalence and internal RTL root cause remain unproven.\n'
        'These Linux userspace programs depend on mmap, mprotect/munmap and SIGSEGV recovery.\n'
        'They are not drop-in bare-metal VCS programs. Preserve page permissions, vector mask,\n'
        'VL/vtype/vstart, fault address, trap PC, handler replay and the post-replay oracle.\n'
        'Use board VLEN1024; do not replace the protected page with ordinary mapped RAM.\n'
        'Controls include the immutable original ELF and reconstructed current source separately.\n')
    hashes = {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    (out / 'hashes.json').write_text(json.dumps(hashes, indent=2) + '\n')
    return index


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('root', 'controls', 'proof-dir', 'original-report', 'out'):
        p.add_argument('--' + key, required=True, type=Path)
    a = p.parse_args()
    result = export(a.root, a.controls, a.proof_dir, a.original_report, a.out)
    print('EXPORTED', result['exported_cases'])


if __name__ == '__main__':
    main()
