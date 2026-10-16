"""Export confirmed numerical reductions, reauditing immutable evidence first."""
import argparse
import json
from pathlib import Path
import shutil
from trace_masks import sha
from audit_slide import audit as audit_slide, require
from audit_redspecial import audit as audit_redspecial


def select_confirmed(manifest, proof):
    cases = {c['name']: c for c in manifest['cases']}
    require(len(cases) == len(manifest['cases']), 'Duplicate manifest case')
    selected = []
    seen = set()
    for row in proof['cases']:
        require(row['name'] not in seen, 'Duplicate audit case')
        seen.add(row['name'])
        require(row['name'] in cases, 'Audit case missing from manifest')
        if row.get('confirmed') is True:
            require(row['original_name'] == cases[row['name']]['original_name'], 'Wrong ancestor')
            selected.append((cases[row['name']], row))
    require(selected, 'No confirmed reductions')
    return selected


def export(entries, out):
    prepared = []
    for root, proof_dir, original in entries:
        manifest = json.loads((root / 'manifest.json').read_text())
        proof = json.loads((proof_dir / 'symptoms.json').read_text())
        names = [c['name'] for c in manifest['cases']]
        if all(n.startswith('rvv_small_fp_redspecial_') for n in names):
            audit = audit_redspecial
        elif all(n.startswith(('rvv_small_slide_', 'rvv_prefix_slide_', 'rvv_small_gather_')) for n in names):
            audit = audit_slide
        else:
            raise ValueError('Unsupported audit schema; do not silently weaken verification')
        recalculated = audit(root, original, proof_dir / 'sampled_report.json')
        require(proof == recalculated, 'Stored audit differs from current evidence')
        prepared.append((root, proof_dir, original, manifest, select_confirmed(manifest, proof)))
    require(len({p[0].name for p in prepared}) == len(prepared), 'Duplicate export group')
    out.mkdir(exist_ok=False)
    index = dict(scope='Incremental board-confirmed numerical reductions; NOT all historical failures',
                 complete_historical_coverage=False, internal_rtl_root_cause_proven=False, groups=[])
    for root, proof_dir, original, manifest, selected in prepared:
        group = out / root.name; group.mkdir()
        shutil.copy2(root / 'manifest.json', group / 'source_manifest.json')
        shutil.copy2(proof_dir / 'symptoms.json', group / 'symptoms.json')
        shutil.copy2(proof_dir / 'sampled_report.json', group / 'board_report.json')
        shutil.copy2(original, group / 'original_report.json')
        rows = []
        for case, evidence in selected:
            name = case['name']; target = group / name; target.mkdir()
            shutil.copy2(root / 'binaries' / name, target / 'scenario.elf')
            for file in case['scenario_sources']:
                path = Path(file)
                require(path.name == file and file not in ('.', '..'), 'Unsafe source filename')
                shutil.copy2(root / name / file, target / file)
            rebuilt = root / name / 'original_rebuilt.elf'
            if not rebuilt.exists():
                rebuilt = root / (case['original_name'] + '.original.elf')
            shutil.copy2(rebuilt, target / 'original.elf')
            (target / 'case.json').write_text(json.dumps(dict(case=case, evidence=evidence), indent=2) + '\n')
            rows.append(dict(name=name, original_name=case['original_name'],
                             configurations=case['configurations'], role=case['scenario_role']))
        index['groups'].append(dict(name=root.name, cases=rows))
    index['exported_cases'] = sum(len(g['cases']) for g in index['groups'])
    (out / 'index.json').write_text(json.dumps(index, indent=2) + '\n')
    (out / 'README.txt').write_text(
        'Incremental board-confirmed reproducer handoff\n\n'
        'Only confirmed numerical reductions are included. Other families and pending cases remain open.\n'
        'Each directory contains source, assembly, reduced ELF, rebuilt original ELF and case evidence.\n'
        'Group reports retain original and reduced measured symptoms and scope limitations.\n'
        'These are Linux userspace ELFs. Do not launch them unchanged in a bare-metal VCS harness.\n'
        'Port the archived setup, vectors, target call sequence and oracle into the existing testbench.\n'
        'Use the measured VLEN1024 and case-specific SEW/LMUL/VL/vstart/mask. Preserve setup instructions.\n'
        'Keep short multi-call sequences intact; isolated calls may not reproduce sequence-dependent errors.\n'
        'A matching board symptom is not proof of an internal RTL root cause or a completed repair.\n')
    hashes = {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    (out / 'hashes.json').write_text(json.dumps(hashes, indent=2) + '\n')
    return index


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--entry', nargs=3, type=Path, action='append', required=True,
                   metavar=('ROOT', 'AUDIT_DIR', 'ORIGINAL_REPORT'))
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    result = export(a.entry, a.out)
    print(json.dumps(dict(out=str(a.out), exported_cases=result['exported_cases'])))


if __name__ == '__main__':
    main()
