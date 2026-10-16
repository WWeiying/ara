"""Freeze a reference-validated board suite without touching the live campaign."""
import argparse
import json
from pathlib import Path
import shutil
from build_extended_suite import digest, BASE_HASH, DTB_HASH
from extended_stability import PROFILES, DEFERRED, extended_plan

HERE = Path(__file__).resolve().parent
SCRIPTS = ('linux_stability.py', 'linux_stability_matrix.py', 'extended_stability.py',
           'check_stability_qemu.py', 'check_linux_console.py', 'test_mmu_board.ps1',
           'run_independent_stability.ps1', 'queue_extended_stability.ps1',
           'test_extended_queue.ps1', 'test_independent_stability.ps1',
           'register_extended_queue.ps1')


def verify_reference(build, reference, here=HERE):
    if (build['state'] != 'built_needs_reference' or build['base_sha256'] != BASE_HASH
            or build['dtb_base_sha256'] != DTB_HASH or not build['base_prefix_unchanged']):
        raise ValueError('Wrong test image base')
    if not reference['passed'] or not reference['reduced_reference_load']:
        raise ValueError('No passing reduced-load reference')
    if reference['initramfs_sha256'] != build['outputs']['initramfs.cpio']['sha256']:
        raise ValueError('Reference rootfs mismatch')
    for name in ('extended_stability.py', 'linux_stability.py', 'linux_stability_matrix.py',
                 'check_stability_qemu.py'):
        if reference['tool_hashes'].get(name) != digest(here/name):
            raise ValueError('Reference source changed: '+name)
    expected = [(p, n) for p in PROFILES for n, *_ in extended_plan('/tmp/ref', p, True)]
    actual = [(r['profile'], r['name']) for r in reference['results'] if r.get('passed')]
    if actual != expected:
        raise ValueError('Incomplete reference inventory')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    a = parser.parse_args()
    build = json.loads((a.build/'build.json').read_text())
    reference = json.loads(a.reference.read_text())
    verify_reference(build, reference)
    for name in ('initramfs.cpio', 'ara_vcu118.dtb'):
        if digest(a.build/name) != build['outputs'][name]['sha256']:
            raise ValueError('Build output changed: '+name)
    a.out.mkdir(parents=True, exist_ok=False)
    for name in SCRIPTS:
        shutil.copy2(HERE/name, a.out/name)
    for name in ('initramfs.cpio', 'ara_vcu118.dtb', 'build.json'):
        shutil.copy2(a.build/name, a.out/name)
    shutil.copy2(a.reference, a.out/'reference_report.json')
    coverage = dict(deferred=DEFERRED, profiles={
        p: dict(groups=len(list(extended_plan('/tmp/board', p))),
                steps=[n for n, *_ in extended_plan('/tmp/board', p)]) for p in PROFILES},
        reboot_iterations=20, soak24h_requires_prior_pass=True,
        upstream_exec_omitted_reason='Upstream rejects root; existing exec_loader regression runs 1000 iterations')
    (a.out/'coverage.json').write_text(json.dumps(coverage, indent=2)+'\n')
    inventory = [dict(Path=p.name, SHA256=digest(p)) for p in sorted(a.out.iterdir())]
    (a.out/'frozen.json').write_text(json.dumps(inventory, indent=2)+'\n')
    print('FROZEN', a.out)
    print('GROUPS', {p: coverage['profiles'][p]['groups'] for p in PROFILES})


if __name__ == '__main__':
    main()
