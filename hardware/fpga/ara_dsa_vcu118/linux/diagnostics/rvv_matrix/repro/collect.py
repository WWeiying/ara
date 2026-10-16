"""Freeze failure inventories, deployed RTL and reproducer evidence for handoff."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import tarfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign', type=Path, required=True)
    parser.add_argument('--compiled', type=Path, required=True)
    parser.add_argument('--source-package', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    inventories = [('original', 'rvv_inventory105'),
                   ('fp_move_extension_children', 'rvv_partition_inventory57'),
                   ('permutation_children', 'rvv_permute_partition_inventory69')]
    report = dict(scope='Separate inventories, overlapping parent/child identities are not additive bugs',
                  board_paused=True, interrupted_case='rvv_permute_restart_e16_m2_ops16',
                  confirmed_terminal_through_recovery=200, inventories={}, cases=[], sources={})
    checked = set()
    for scope, folder in inventories:
        path = args.campaign / folder / 'inventory.json'
        inventory = json.loads(path.read_text())
        report['sources'][str(path)] = digest(path)
        for filename, sha in inventory['source_sha256'].items():
            if (filename, sha) not in checked:
                if digest(Path(filename)) != sha:
                    raise ValueError('Evidence hash mismatch: ' + filename)
                checked.add((filename, sha))
        report['inventories'][scope] = dict(planned=inventory['planned'], counts=inventory['counts'])
        for case in inventory['cases']:
            if case['status'] != 'passed':
                report['cases'].append(dict(scope=scope, **case))
    report['verified_source_hashes'] = len(checked)
    (args.out / 'failure_inventory.json').write_text(json.dumps(report, indent=2) + '\n')
    with (args.out / 'failure_cases.tsv').open('w', newline='') as stream:
        writer = csv.writer(stream, delimiter='\t')
        writer.writerow(['scope', 'name', 'status', 'sha256', 'evidence'])
        for case in report['cases']:
            evidence = sorted({p for paths in case['evidence'].values() for p in paths})
            writer.writerow([case['scope'], case['name'], case['status'], case['sha256'], ';'.join(evidence)])

    archived_manifest = args.campaign / 'rvv_stall_archived_rtl/manifest.json'
    source_manifest = json.loads(archived_manifest.read_text())
    expected = {x['file']: x['source_sha256'] for x in source_manifest['source_hashes_before_integration']}
    sources = {
        'ara_dispatcher.sv': args.campaign / 'rvv_new_findings_archived_rtl/ara_dispatcher.sv',
        'addrgen.sv': args.campaign / 'rvv_new_findings_archived_rtl/addrgen.sv',
        'lane_sequencer.sv': args.campaign / 'rvv_stall_archived_rtl/lane_sequencer.sv',
        'masku.sv': args.campaign / 'rvv_stall_archived_rtl/masku.sv',
        'operand_requester.sv': args.campaign / 'rvv_stall_archived_rtl/operand_requester.sv',
        'sldu.sv': args.source_package / 'rtl/ara/hardware/src/sldu/sldu.sv',
        'vmfpu.sv': args.source_package / 'rtl/ara/hardware/src/lane/vmfpu.sv',
    }
    deployed = args.out / 'deployed_rtl'
    deployed.mkdir()
    for name, source in sources.items():
        matches = [sha for path, sha in expected.items() if Path(path).name == name]
        if matches != [digest(source)]:
            raise ValueError('Deployed RTL identity mismatch: ' + name)
        shutil.copyfile(source, deployed / name)
    shutil.copyfile(archived_manifest, deployed / 'manifest.json')

    reference = json.loads((args.compiled / 'reference_1024.json').read_text())
    manifest_path = args.compiled / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    if reference['manifest_sha256'] != digest(manifest_path) or not reference['passed']:
        raise ValueError('Reference does not validate this manifest')
    if {r['name'] for r in reference['results']} != {c['name'] for c in manifest['cases']}:
        raise ValueError('Incomplete reference case set')
    here = Path(__file__).parent
    for name, sha in manifest['source_sha256'].items():
        if digest(here / name) != sha:
            raise ValueError('Compiled source changed: ' + name)
    for name in ('build.py', 'scenario.c', 'collect.py', 'README.md'):
        shutil.copyfile(here / name, args.out / name)
    for name in ('ISSUES.md', 'COVERAGE_GAPS.md'):
        shutil.copyfile(here.parent / name, args.out / name)
    for name in ('manifest.json', 'reference_1024.json', 'reference_1024.log'):
        shutil.copyfile(args.compiled / name, args.out / name)
    shutil.copytree(args.compiled / 'overlay/opt/ara-tests', args.out / 'binaries')
    asm_dir = args.out / 'assembly'
    asm_dir.mkdir()
    for case in manifest['cases']:
        if digest(args.out / 'binaries' / case['name']) != case['sha256']:
            raise ValueError('ELF hash mismatch: ' + case['name'])
        for suffix in ('.S', '.dis'):
            shutil.copyfile(args.compiled / (case['name'] + suffix), asm_dir / (case['name'] + suffix))
    evidence_dir = args.out / 'board_evidence'
    evidence_dir.mkdir()
    for folder in ('rvv_additions06', 'rvv_additions07', 'rvv_trace02',
                   'rvv_recovery08_197/terminal_scene', 'rvv_recovery08_198/terminal_scene',
                   'rvv_recovery08_199/terminal_scene', 'rvv_recovery08_200/terminal_scene'):
        source_dir = args.campaign / folder
        source = source_dir / ('board_report.json' if folder.startswith('rvv_additions') else 'report.json')
        if not source.exists():
            raise FileNotFoundError(source)
        data = json.loads(source.read_text())
        excerpt = dict(source=str(source), sha256=digest(source),
                       results=data.get('results'), progress_diagnosis=data.get('progress_diagnosis'))
        (evidence_dir / (folder.replace('/', '_') + '.json')).write_text(json.dumps(excerpt, indent=2) + '\n')
    hashes = {str(p.relative_to(args.out)): digest(p) for p in sorted(args.out.rglob('*')) if p.is_file()}
    (args.out / 'hashes.json').write_text(json.dumps(hashes, indent=2) + '\n')
    archive = args.out.with_suffix('.tgz')
    with tarfile.open(archive, 'x:gz') as stream:
        stream.add(args.out, arcname=args.out.name)
    print(json.dumps(dict(archive=str(archive), sha256=digest(archive),
                          records=len(report['cases']), verified_sources=len(checked))))


if __name__ == '__main__':
    main()
