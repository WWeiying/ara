#!/usr/bin/env python3
"""M9 preparation defaults to read-only verification; execution needs authorization."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import resource

ROOT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration')
OLD = Path('/home/wangwy/fpga_runs/current_board_memory_candidate08')
OUT = Path('/home/wangwy/fpga_runs/current_board_memory_candidate09')
HELPER = ROOT / 'verification/fpga/current_board_review/integration/run.py'
ALLOWED = ('hardware/src/vlsu/addrgen.sv',)
PINS = {
    OLD / 'frozen/snapshot.json': '8e0ada736b61d0b3ce5dc482e3d85078048d4f81fa0633cba8c340573e02a3be',
    OLD / 'campaign/image/image.json': 'bd27bf6f7bb90b2b05c4546faaed8a8e32b8e545c182167fef72c170e40bdfd0',
    OLD / 'campaign/image/_build/vcs/vcs_source_manifest.json': '43a113535b7501c0c64d0e8ac7be142f19efe3f2ffde1635cb050060df6e8531',
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
            'M8 snapshot count')
    for name, digest in snap['files'].items():
        path = Path(snap['root']) / name
        require(not path.is_symlink() and sha(path) == digest and not path.stat().st_mode & 0o222,
                'M8 frozen drift: ' + name)
    require(len(read(OLD / 'campaign/image/_build/vcs/vcs_source_manifest.json')['files']) == 453,
            'M8 compiled count')
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
    require(sha(Path(snap['root']) / ALLOWED[0]) ==
            '1cc40e2669e310ae25e23f5c9ee1f7ee493dc1ac990d70d8b8122f47e93742b2',
            'M8 original AddrGen hash drift')
    require(sha(ROOT / ALLOWED[0]) ==
            '3736b64136ebbf5629dadb0037457279f9bb91307356c468c9677d321c8c51c5',
            'exact approved M9 AddrGen hash drift')
    return sorted(changes)


def checked(command, **kwargs):
    started = time.monotonic()
    result = subprocess.run(command, **kwargs)
    record = dict(command=command, actual_child_returncode=result.returncode,
                  elapsed_s=time.monotonic()-started, actual_process_waited=True)
    with (OUT / ('snapshot_process.json' if 'snapshot' in command else 'build_process.json')).open('x') as stream:
        json.dump(record, stream, indent=2)
        stream.flush(); os.fsync(stream.fileno())
    result.check_returncode()


def resources():
    conflicts=[]
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit(): continue
        try:
            comm=(proc/'comm').read_text().strip()
            if comm in ('vcs', 'vcs1', 'vlogan', 'vcselab'):
                conflicts.append(dict(pid=int(proc.name),comm=comm,
                    command=(proc/'cmdline').read_bytes().replace(b'\\0',b' ').decode(errors='replace')))
        except FileNotFoundError: continue
    require(not conflicts, 'Existing EDA build conflict: '+repr(conflicts))
    memory=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
    available=int(memory['MemAvailable'].split()[0])*1024
    require(available>=32*1024**3,'Less than32GiB available')
    disk=os.statvfs(OUT.parent)
    require(disk.f_bavail*disk.f_frsize>=10*1024**3,'Less than10GiB disk available')
    return dict(memory_available_bytes=available,disk_available_bytes=disk.f_bavail*disk.f_frsize,
                cpu_count=os.cpu_count(),loadavg=os.getloadavg(),build_conflicts=conflicts)


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
    require(not OUT.exists() and not OUT.is_symlink(), 'candidate09 output already exists; no retry/reuse')
    if not args.authorize_freeze_and_build:
        print('PREPARATION_CHECK_PASS; allowed changes=' + repr(changes) +
              '; final SHA not bound unless supplied; no output, Bender, EDA or DUT launched')
        return
    require(approved, 'final parent-approved AddrGen hash required')
    admission=resources()
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    OUT.mkdir(exist_ok=False)
    with (OUT / 'admission.json').open('x') as stream:
        json.dump(admission,stream,indent=2)
    checked([sys.executable, '-B', str(HELPER), 'snapshot', '--out', str(OUT / 'frozen'),
                    '--authorize-freeze'], cwd=ROOT, env=env)
    new = read(OUT / 'frozen/snapshot.json')
    require(new['settings'] == snap['settings'] and set(new['files']) == set(snap['files']),
            'snapshot membership/config drift')
    expected = dict(snap['live_source_sha256'])
    expected.update({str(ROOT / name): digest for name, digest in approved.items()})
    require(new['live_source_sha256'] == expected, 'snapshot differs from approved M8 successor')
    for name, digest in new['files'].items():
        if name not in ('frozen.filelist', 'hardware/bender', *ALLOWED):
            require(digest == snap['files'][name], 'unexpected frozen change: ' + name)
    oldroot, newroot = snap['root'], new['root']
    for name in ('frozen.filelist', 'hardware/bender'):
        require((Path(newroot) / name).read_text() ==
                (Path(oldroot) / name).read_text().replace(oldroot, newroot), 'relocation drift: ' + name)
    (OUT / 'campaign').mkdir()
    checked([sys.executable, '-B', str(HELPER), 'build-image', '--snapshot', str(OUT / 'frozen'),
                    '--out', str(OUT / 'campaign/image'), '--authorize-build'],
                   cwd=ROOT, env=env)
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
    started=time.monotonic()
    rc=0
    try:
        main()
    except BaseException:
        rc=1
        raise
    finally:
        if '--authorize-freeze-and-build' in sys.argv:
            usage=resource.getrusage(resource.RUSAGE_CHILDREN)
            receipt=dict(actual_worker_result=rc,elapsed_s=time.monotonic()-started,
                child_user_s=usage.ru_utime,child_system_s=usage.ru_stime,
                child_max_rss_kib=usage.ru_maxrss,pid=os.getpid(),no_DUT=True)
            with Path(__file__).with_name('worker_result01.json').open('x') as stream:
                json.dump(receipt,stream,indent=2);stream.flush();os.fsync(stream.fileno())
