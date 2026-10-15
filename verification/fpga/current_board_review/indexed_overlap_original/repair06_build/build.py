#!/usr/bin/env python3
"""M6 preparation defaults to read-only verification; execution needs authorization."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration')
OLD = Path('/home/wangwy/fpga_runs/current_board_memory_candidate05')
OUT = Path('/home/wangwy/fpga_runs/current_board_memory_candidate06')
HELPER = ROOT / 'verification/fpga/current_board_review/integration/run.py'
PINS = {
    OLD / 'frozen/snapshot.json': '0fb492aebe246deeeacf312b387d0813837afe4b023e53e5fe5d584bca5c0dbf',
    OLD / 'campaign/image/image.json': '9349bdae91e72706ffbb22ad20a7f62795215a5263b1ec0cc4e4837fc21d1500',
    OLD / 'campaign/image/_build/vcs/vcs_source_manifest.json': 'f050c1e6420537d7e562bb82056a439f10d17bede8dfe89100b2f71f638368c0',
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
            'M5 snapshot count')
    for name, digest in snap['files'].items():
        path = Path(snap['root']) / name
        require(not path.is_symlink() and sha(path) == digest and not path.stat().st_mode & 0o222,
                'M5 frozen drift: ' + name)
    require(len(read(OLD / 'campaign/image/_build/vcs/vcs_source_manifest.json')['files']) == 453,
            'M5 compiled count')
    return snap


def live_check(snap, dispatcher, approved):
    changes = []
    for name, digest in snap['live_source_sha256'].items():
        if sha(Path(name)) != digest:
            changes.append(str(Path(name).relative_to(ROOT)))
    if approved is None:
        require(not changes, 'unapproved live changes: ' + repr(changes))
        return
    require(changes == [dispatcher], 'expected only approved dispatcher: ' + repr(changes))
    path = ROOT / dispatcher
    require(sha(path) == approved, 'dispatcher SHA does not match parent approval')
    before = (Path(snap['root']) / dispatcher).read_text()
    marker = '        // Mask out duplicate requests for the same architectural operand.\n'
    old = '              reduction_source_overlap_reshuffle,\n'
    require(before.count(marker) == 1 and before.count(old) == 1, 'M5 patch anchor mismatch')
    expected = before.replace(marker,
        "        // Indexed-load offsets can share vd's base but not its EEW. Keep\n"
        '        // their normalization before the source snapshot and vd conversion.\n' + marker)
    expected = expected.replace(old,
        '              reduction_source_overlap_reshuffle || indexed_load_groups_overlap,\n')
    require(path.read_text() == expected, 'expected only parent one-line repair plus two comments')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dispatcher', choices=['hardware/src/ara_dispatcher.sv'],
                   default='hardware/src/ara_dispatcher.sv')
    p.add_argument('--approved-dispatcher-sha256')
    p.add_argument('--authorize-freeze-and-build', action='store_true')
    args = p.parse_args()
    snap = baseline()
    live_check(snap, args.dispatcher, args.approved_dispatcher_sha256)
    require(not OUT.exists() and not OUT.is_symlink(), 'candidate06 output already exists; no retry/reuse')
    if not args.authorize_freeze_and_build:
        print('PREPARATION_CHECK_PASS; no output, Bender, EDA or DUT launched')
        return
    require(args.approved_dispatcher_sha256 is not None, 'parent-approved dispatcher SHA required')
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    OUT.mkdir(exist_ok=False)
    subprocess.run([sys.executable, '-B', str(HELPER), 'snapshot', '--out', str(OUT / 'frozen'),
                    '--authorize-freeze'], cwd=ROOT, env=env, check=True)
    new = read(OUT / 'frozen/snapshot.json')
    require(new['settings'] == snap['settings'] and set(new['files']) == set(snap['files']),
            'snapshot membership/config drift')
    expected = dict(snap['live_source_sha256'])
    expected[str(ROOT / args.dispatcher)] = args.approved_dispatcher_sha256
    require(new['live_source_sha256'] == expected, 'snapshot differs from approved M5 successor')
    for name, digest in new['files'].items():
        if name not in ('frozen.filelist', 'hardware/bender', args.dispatcher):
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
        elif record['path'] == str(Path(newroot) / args.dispatcher):
            record['sha256'] = args.approved_dispatcher_sha256
        expected_records.append(record)
    require(len(manifest['files']) == 453 and manifest['files'] == expected_records,
            'compiled manifest differs from approved successor')
    require((OUT / 'campaign/image/_build/vcs/simulator.conf').read_bytes() ==
            (OLD / 'campaign/image/_build/vcs/simulator.conf').read_bytes(), 'compiled config drift')
    baseline()
    with (OUT / 'BUILD_ACCEPTED.json').open('x') as stream:
        json.dump(dict(status='BUILD_ONLY_NOT_DUT_PASS', dispatcher_sha256=args.approved_dispatcher_sha256,
                       snapshot_sha256=sha(OUT / 'frozen/snapshot.json'),
                       image_sha256=sha(OUT / 'campaign/image/image.json'), sources=539, compiled=453), stream, indent=2)
    print('BUILD_ACCEPTED; no DUT execution')


if __name__ == '__main__':
    main()
