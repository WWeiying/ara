#!/usr/bin/env python3
"""M8 preparation defaults to read-only verification; execution needs authorization."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration')
OLD = Path('/home/wangwy/fpga_runs/current_board_memory_candidate07')
OUT = Path('/home/wangwy/fpga_runs/current_board_memory_candidate08')
HELPER = ROOT / 'verification/fpga/current_board_review/integration/run.py'
ALLOWED = ('hardware/src/vlsu/addrgen.sv',)
PINS = {
    OLD / 'frozen/snapshot.json': '716324501ac1e5243a4dbe15fd7ad925c47e61d2b40c039f1241b065f9e0ea61',
    OLD / 'campaign/image/image.json': 'e807e9243071ae078305ffa818f35c2902b33606fd20730fd6fe844a0924b7ba',
    OLD / 'campaign/image/_build/vcs/vcs_source_manifest.json': 'cc1aade5c86b4254601e5120d5063fe7460e63e718b0117ce004dd53a25d652c',
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
            'M7 snapshot count')
    for name, digest in snap['files'].items():
        path = Path(snap['root']) / name
        require(not path.is_symlink() and sha(path) == digest and not path.stat().st_mode & 0o222,
                'M7 frozen drift: ' + name)
    require(len(read(OLD / 'campaign/image/_build/vcs/vcs_source_manifest.json')['files']) == 453,
            'M7 compiled count')
    return snap


def live_check(snap, approved):
    changes = {str(Path(name).relative_to(ROOT)) for name, digest in
               snap['live_source_sha256'].items() if sha(Path(name)) != digest}
    require(changes <= set(ALLOWED), 'unapproved live changes: ' + repr(sorted(changes)))
    if approved:
        require(changes == set(ALLOWED), 'expected only approved AddrGen change')
        for name, digest in approved.items():
            require(len(digest) == 64 and all(c in '0123456789abcdef' for c in digest),
                    'invalid approved SHA256: ' + name)
            require(sha(ROOT / name) == digest, 'approved source SHA drift: ' + name)
    old = (Path(snap['root']) / ALLOWED[0]).read_text()
    before = "            if (en_ld_st_translation_i && ((state_q != ADDRGEN_IDX_OP) || idx_vaddr_valid_q)) begin : translation_req"
    after = """            // A locally rejected index must not acquire the shared MMU: its
            // request would vanish before CVA6 could issue the translation.
            if (en_ld_st_translation_i &&
                ((state_q != ADDRGEN_IDX_OP) ||
                 (idx_vaddr_valid_q &&
                  !is_addr_error(idx_final_vaddr_q, axi_addrgen_q.vew[1:0])))) begin : translation_req"""
    require(old.count(before) == 1 and
            (ROOT / ALLOWED[0]).read_text() == old.replace(before, after),
            'not the exact reviewed AddrGen delta')
    require(sha(ROOT / ALLOWED[0]) ==
            '1cc40e2669e310ae25e23f5c9ee1f7ee493dc1ac990d70d8b8122f47e93742b2',
            'reviewed AddrGen hash drift')
    return sorted(changes)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--approved-addrgen-sha256')
    p.add_argument('--authorize-freeze-and-build', action='store_true')
    args = p.parse_args()
    snap = baseline()
    values = (args.approved_addrgen_sha256,)
    require(all(values) or not any(values), 'supply the final approved hash or none')
    approved = dict(zip(ALLOWED, values)) if all(values) else {}
    changes = live_check(snap, approved)
    require(not OUT.exists() and not OUT.is_symlink(), 'candidate08 output already exists; no retry/reuse')
    if not args.authorize_freeze_and_build:
        print('PREPARATION_CHECK_PASS; allowed changes=' + repr(changes) +
              '; final SHA not bound unless supplied; no output, Bender, EDA or DUT launched')
        return
    require(approved, 'final parent-approved AddrGen hash required')
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    OUT.mkdir(exist_ok=False)
    subprocess.run([sys.executable, '-B', str(HELPER), 'snapshot', '--out', str(OUT / 'frozen'),
                    '--authorize-freeze'], cwd=ROOT, env=env, check=True)
    new = read(OUT / 'frozen/snapshot.json')
    require(new['settings'] == snap['settings'] and set(new['files']) == set(snap['files']),
            'snapshot membership/config drift')
    expected = dict(snap['live_source_sha256'])
    expected.update({str(ROOT / name): digest for name, digest in approved.items()})
    require(new['live_source_sha256'] == expected, 'snapshot differs from approved M7 successor')
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
