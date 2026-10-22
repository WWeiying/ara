#!/usr/bin/env python3
"""M7 preparation defaults to read-only verification; execution needs authorization."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration')
OLD = Path('/home/wangwy/fpga_runs/current_board_memory_candidate06')
OUT = Path('/home/wangwy/fpga_runs/current_board_memory_candidate07')
HELPER = ROOT / 'verification/fpga/current_board_review/integration/run.py'
ALLOWED = ('hardware/src/vlsu/vldu.sv', 'hardware/src/vlsu/vstu.sv')
PINS = {
    OLD / 'frozen/snapshot.json': '3cba2d3a6a10c76cb4a2ee0098e3a3755e76b5903920b8b09b0fdadd2999f438',
    OLD / 'campaign/image/image.json': 'a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0',
    OLD / 'campaign/image/_build/vcs/vcs_source_manifest.json': 'adb00217bf26f29467b42e1115b42412ecc59f63a8cf8826822d5df147d0fb3a',
    HELPER: 'c1c3804dbe36fa981ea7b6cbcfa5d7b69fb793b2a14c37831fb96e866f2d2a78',
    HELPER.with_name('prepare.py'): 'c8852599c65e0a0812a7dc77dc365eb40398252867a29b226f34d758e5c56cf8',
}


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def baseline():
    for path, digest in PINS.items():
        require(sha(path) == digest, 'identity drift: ' + str(path))
    snap = read(OLD / 'frozen/snapshot.json')
    require(len(snap['files']) == 539 and len(snap['live_source_sha256']) == 537,
            'M6 snapshot count')
    for name, digest in snap['files'].items():
        path = Path(snap['root']) / name
        require(not path.is_symlink() and sha(path) == digest and not path.stat().st_mode & 0o222,
                'M6 frozen drift: ' + name)
    require(len(read(OLD / 'campaign/image/_build/vcs/vcs_source_manifest.json')['files']) == 453,
            'M6 compiled count')
    return snap


def live_check(snap, approved):
    changes = {str(Path(name).relative_to(ROOT)) for name, digest in
               snap['live_source_sha256'].items() if sha(Path(name)) != digest}
    require(changes <= set(ALLOWED), 'unapproved live changes: ' + repr(sorted(changes)))
    if approved:
        require(changes == set(ALLOWED), 'expected both approved VLDU/VSTU changes')
        for name, digest in approved.items():
            require(len(digest) == 64 and all(c in '0123456789abcdef' for c in digest),
                    'invalid approved SHA256: ' + name)
            require(sha(ROOT / name) == digest, 'approved source SHA drift: ' + name)
    return sorted(changes)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--approved-vldu-sha256')
    p.add_argument('--approved-vstu-sha256')
    p.add_argument('--authorize-freeze-and-build', action='store_true')
    args = p.parse_args()
    snap = baseline()
    values = (args.approved_vldu_sha256, args.approved_vstu_sha256)
    require(all(values) or not any(values), 'supply both final approved hashes or neither')
    approved = dict(zip(ALLOWED, values)) if all(values) else {}
    changes = live_check(snap, approved)
    require(not OUT.exists() and not OUT.is_symlink(), 'candidate07 output already exists; no retry/reuse')
    if not args.authorize_freeze_and_build:
        print('PREPARATION_CHECK_PASS; allowed changes=' + repr(changes) +
              '; final SHA not bound unless supplied; no output, Bender, EDA or DUT launched')
        return
    require(approved, 'both final parent-approved VLDU/VSTU hashes required')
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    OUT.mkdir(exist_ok=False)
    subprocess.run([sys.executable, '-B', str(HELPER), 'snapshot', '--out', str(OUT / 'frozen'),
                    '--authorize-freeze'], cwd=ROOT, env=env, check=True)
    new = read(OUT / 'frozen/snapshot.json')
    require(new['settings'] == snap['settings'] and set(new['files']) == set(snap['files']),
            'snapshot membership/config drift')
    expected = dict(snap['live_source_sha256'])
    expected.update({str(ROOT / name): digest for name, digest in approved.items()})
    require(new['live_source_sha256'] == expected, 'snapshot differs from approved M6 successor')
    for name, digest in new['files'].items():
        if name not in ('frozen.filelist', 'hardware/bender', *ALLOWED):
            require(digest == snap['files'][name], 'unexpected frozen change: ' + name)
    oldroot, newroot = snap['root'], new['root']
    for name in ('frozen.filelist', 'hardware/bender'):
        require((Path(newroot) / name).read_text() ==
                (Path(oldroot) / name).read_text().replace(oldroot, newroot), 'relocation drift: ' + name)
    (OUT / 'campaign').mkdir()
    subprocess.run([sys.executable, '-B', str(HELPER), 'build-image', '--snapshot', str(OUT / 'frozen'),
                    '--out', str(OUT / 'campaign/image'), '--authorize-build'],
                   cwd=ROOT, env=env, check=True)
    old_manifest = read(OLD / 'campaign/image/_build/vcs/vcs_source_manifest.json')
    manifest = read(OUT / 'campaign/image/_build/vcs/vcs_source_manifest.json')
    expected_records = []
    for record in old_manifest['files']:
        record = dict(record)
        record['path'] = record['path'].replace(str(OLD), str(OUT))
        if record['path'] == manifest['filelist']:
            old_text = Path(old_manifest['filelist']).read_text()
            require(Path(record['path']).read_text() == old_text.replace(str(OLD), str(OUT)),
                    'compiled filelist relocation drift')
            record['sha256'] = sha(Path(record['path']))
        elif record['path'] in {str(Path(newroot) / n) for n in ALLOWED}:
            record['sha256'] = approved[str(Path(record['path']).relative_to(newroot))]
        expected_records.append(record)
    require(len(manifest['files']) == 453 and manifest['files'] == expected_records,
            'compiled manifest differs from approved successor')
    require((OUT / 'campaign/image/_build/vcs/simulator.conf').read_bytes() ==
            (OLD / 'campaign/image/_build/vcs/simulator.conf').read_bytes(), 'compiled config drift')
    baseline()
    with (OUT / 'BUILD_ACCEPTED.json').open('x') as stream:
        json.dump(dict(status='BUILD_ONLY_NOT_DUT_PASS', approved_source_sha256=approved,
                       snapshot_sha256=sha(OUT / 'frozen/snapshot.json'),
                       image_sha256=sha(OUT / 'campaign/image/image.json'), sources=539, compiled=453), stream, indent=2)
    print('BUILD_ACCEPTED; no DUT execution')


if __name__ == '__main__':
    main()
