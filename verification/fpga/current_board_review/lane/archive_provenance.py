"""Freeze original board records separately from reduced current-RTL results."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
CAMPAIGN = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01')
REPRO = Path('/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix/repro')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    files = {}

    def archive(source, relative):
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        files[relative] = dict(source=str(source), sha256=sha(target))

    for name in ('ALL_FAILURE_REVIEW.md', 'STALL_TRIAGE.md'):
        archive(REPRO / name, name)
    for name in ('lane_sequencer.sv', 'manifest.json'):
        archive(CAMPAIGN / 'rvv_stall_archived_rtl' / name, 'deployed/' + name)
    triage = json.loads((CAMPAIGN / 'stall_family_triage02/triage.json').read_text())
    selected = [r for r in triage['cases'] if r['name'] in (
        'rvv_masks_scalar_restart_e8_m4', 'rvv_fixed_restart_e16_m8',
        'rvv_integer_macc_accumulators_restart_e16_m8', 'rvv_masks_alias_restart_e8_m4')]
    for record in selected:
        for key, expected in (('binary', 'elf_sha256'), ('report', 'report_sha256')):
            source = Path(record[key])
            assert sha(source) == record[expected]
            archive(source, record['name'] + '/' + ('original.elf' if key == 'binary' else 'board_report.json'))
    (out / 'stall_records.json').write_text(json.dumps(selected, indent=2) + '\n')
    small = CAMPAIGN / 'rvv_small_masks02'
    manifest = json.loads((small / 'manifest.json').read_text())
    records = [r for r in manifest['cases'] if r['name'] in (
        'rvv_small_masks_scalar_restart_e64_m1', 'rvv_small_masks_scalar_restart_e32_m1')]
    for record in records:
        for name, expected in record['scenario_sources'].items():
            source = small / record['name'] / name
            assert sha(source) == expected
            archive(source, record['name'] + '/' + name)
        source = small / 'binaries' / record['name']
        assert sha(source) == record['sha256']
        archive(source, record['name'] + '/single.elf')
        source = CAMPAIGN / 'rvv_additions35/binaries' / record['original_name']
        assert sha(source) == record['original_elf_sha256']
        archive(source, record['name'] + '/original.elf')
    archive(small / 'prefix_board_report.json', 'compare_prefix_board_report.json')
    (out / 'compare_records.json').write_text(json.dumps(records, indent=2) + '\n')
    index = dict(
        scope='Archived evidence, not current-RTL full-program closure',
        files=files, triage_source=str(CAMPAIGN / 'stall_family_triage02/triage.json'),
        triage_sha256=sha(CAMPAIGN / 'stall_family_triage02/triage.json'),
        small_manifest_sha256=sha(small / 'manifest.json'),
        archive=str(out), stall_records=selected, compare_records=records)
    (out / 'manifest.json').write_text(json.dumps(index, indent=2) + '\n')
    (HERE / 'provenance.json').write_text(json.dumps(index, indent=2) + '\n')
    print('Archived', len(files), 'files')


if __name__ == '__main__':
    main()
