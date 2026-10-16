"""Export confirmed flag failures with immutable original binaries and provenance."""
import argparse
import json
from pathlib import Path
import shutil
from audit_fp_compare import audit
from audit_slide import require
from export_verified import select_confirmed
from trace_masks import sha


def original_binary(campaign, case):
    matches = [p for p in campaign.glob('*/manifest.json')
               if sha(p) == case['original_manifest_sha256']]
    require(len(matches) == 1, 'Missing or ambiguous original manifest')
    path = matches[0]
    old = json.loads(path.read_text())
    rows = [c for c in old['cases'] if c['name'] == case['original_name']]
    require(len(rows) == 1 and rows[0]['sha256'] == case['original_elf_sha256'],
            'Original manifest identity differs')
    binary = path.parent/'overlay/opt/ara-tests'/case['original_name']
    require(sha(binary) == case['original_elf_sha256'], 'Original binary changed')
    return path, binary


def export(root, proof_dir, campaign, out):
    manifest = json.loads((root/'manifest.json').read_text())
    checked = audit(root, proof_dir/'sampled_report.json')
    require(checked == json.loads((proof_dir/'symptoms.json').read_text()),
            'Stored audit differs')
    selected = select_confirmed(manifest, checked)
    prepared = []
    for case, row in selected:
        for name in (case['name'], case['original_name'], *case['scenario_sources']):
            require(Path(name).name == name and name not in ('.', '..'), 'Unsafe filename')
        prepared.append((case, row, original_binary(campaign, case)))
    out.mkdir(exist_ok=False)
    for source, name in ((root/'manifest.json', 'source_manifest.json'),
                         (root/'original_board_report.json', 'original_board_report.json'),
                         (proof_dir/'sampled_report.json', 'single_board_report.json'),
                         (proof_dir/'symptoms.json', 'symptoms.json')):
        shutil.copy2(source, out/name)
    for case, row, (old_manifest, old_binary) in prepared:
        target = out/case['name']; target.mkdir()
        shutil.copy2(old_manifest, target/'original_manifest.json')
        shutil.copy2(old_binary, target/'original.elf')
        shutil.copy2(root/'binaries'/case['name'], target/'scenario.elf')
        for file in case['scenario_sources']:
            shutil.copy2(root/case['name']/file, target/file)
        (target/'case.json').write_text(json.dumps(dict(case=case, evidence=row), indent=2)+'\n')
    index = dict(exported_cases=len(prepared),
                 unresolved=[r for r in checked['cases'] if not r['confirmed']],
                 original_c_source_equivalence_proven=False,
                 internal_rtl_root_cause_proven=False, complete_historical_coverage=False)
    (out/'index.json').write_text(json.dumps(index, indent=2)+'\n')
    (out/'README.txt').write_text(
        'Board-confirmed floating-point comparison fflags reproducers\n\n'
        'Only exact measured stimulus/fflags matches are exported. Unresolved cases remain open.\n'
        'original.elf is the archived binary, not a rebuilt substitute.\n'
        'scenario.c is the current reconstructed oracle; original C equivalence is unproven.\n'
        'Assembly, input fixtures and explicit expected/actual flags accompany each case.\n'
        'These are Linux userspace ELFs, not drop-in bare-metal VCS programs.\n'
        'Preserve measured VLEN1024, SEW/LMUL, VL, masks, operands, aliasing and sticky fflags.\n'
        'Internal RTL cause and vector data equivalence are not established by this flag match.\n')
    hashes = {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    (out/'hashes.json').write_text(json.dumps(hashes, indent=2)+'\n')
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('root', 'proof-dir', 'campaign', 'out'):
        parser.add_argument('--'+key, type=Path, required=True)
    args = parser.parse_args()
    result = export(args.root, args.proof_dir, args.campaign, args.out)
    print('EXPORTED', result['exported_cases'], 'UNRESOLVED', len(result['unresolved']))


if __name__ == '__main__':
    main()
