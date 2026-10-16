"""Build pinned upstream stress tools and append tools to the unchanged rootfs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
SDK = Path('/home/wangwy/openproject/cva6/cva6-sdk')
BASE_HASH = '4c1f196a90cbba5cd73af81712c526067ab8e83efb7d303cbde829528f4e3b25'
DTB_HASH = 'a78f2160a4e1a7191df2f4ca4b012a9145b394ac6e9883031b2e0b94565157ef'
ARCHIVES = {
    'stress-ng': ('stress-ng-0.20.00', 'fe9e5161ac186c6ada22963251ff701fe3275fac2c5b87bdb59c4cab08aaeaae'),
    'memtester': ('memtester-4.7.1', 'e427de663f7bd22d1ebee8af12506a852c010bd4fcbca1e0e6b02972d298b5bb'),
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--vendor', type=Path, required=True)
    p.add_argument('--base', type=Path, required=True)
    p.add_argument('--dtb', type=Path, required=True)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    report = dict(state='building', pid=os.getpid(), base_sha256=BASE_HASH,
                  dtb_base_sha256=DTB_HASH, commands=[], sources={}, outputs={})

    def save():
        (a.out/'build.json').write_text(json.dumps(report, indent=2)+'\n')

    def run(cmd, cwd=a.out, data=None):
        report['commands'].append([str(x) for x in cmd])
        save()
        with (a.out/'build.log').open('ab') as log:
            subprocess.run(cmd, cwd=cwd, input=data, stdout=log, stderr=log, check=True)

    try:
        if digest(a.base) != BASE_HASH or digest(a.dtb) != DTB_HASH:
            raise ValueError('Original rootfs/DTB identity mismatch')
        prefix = str(SDK/'buildroot/output/host/bin/riscv64-buildroot-linux-gnu-')
        cc = prefix+'gcc'
        flags = ['-O2', '-march=rv64gc', '-mabi=lp64d', '-fno-tree-vectorize', '-fno-tree-slp-vectorize']
        vendor = a.out/'vendor'
        vendor.mkdir()
        for name, (directory, expected) in ARCHIVES.items():
            archive = a.vendor/(directory+'.tar.gz')
            if digest(archive) != expected:
                raise ValueError('Upstream archive hash mismatch: '+name)
            report['sources'][name] = dict(archive=str(archive), sha256=expected)
            with tarfile.open(archive) as tar:
                for member in tar.getmembers():
                    path = Path(member.name)
                    if path.is_absolute() or '..' in path.parts or not (member.isfile() or member.isdir()):
                        raise ValueError('Unexpected archive entry: '+member.name)
                tar.extractall(vendor)
        stress = vendor/ARCHIVES['stress-ng'][0]
        run(['make', '-j4', 'CC='+cc, 'CXX='+prefix+'g++', 'PRESERVE_CFLAGS=1',
             'CFLAGS='+' '.join(flags), 'CXXFLAGS='+' '.join(flags),
             'LDFLAGS=-latomic', 'STATIC=1'], stress)
        mem = vendor/ARCHIVES['memtester'][0]
        (mem/'conf-cc').write_text(cc+' '+' '.join(flags)+' -DTEST_NARROW_WRITES\n')
        (mem/'conf-ld').write_text(cc+' -static\n')
        run(['make', '-j2'], mem)
        overlay = a.out/'overlay'
        binary = overlay/'opt/ara-tests'
        binary.mkdir(parents=True)
        for name, directory in [('stress-ng', stress), ('memtester', mem)]:
            shutil.copy2(directory/name, binary/name)
            shutil.copy2(directory/'COPYING', binary/(name+'.COPYING'))
        rvv = REPO/'verification/linux/userspace'
        src = [rvv/'rvv_linux_smoke.c', rvv/'rvv_linux_state.S', rvv/'custom_caps.c']
        report['sources']['rvv'] = {str(x): digest(x) for x in src}
        run([cc, *flags, '-static', '-Wall', '-Wextra', '-Werror', *src,
             '-o', binary/'rvv_linux_smoke'])
        for name in ['stress-ng', 'memtester', 'rvv_linux_smoke']:
            run([prefix+'strip', binary/name])
            run([prefix+'readelf', '-h', '-l', binary/name])
        # Record actual AMO/LR-SC instructions, not an assumption from the tool name.
        with (a.out/'stress-ng.dump').open('wb') as stream:
            subprocess.run([prefix+'objdump', '-d', binary/'stress-ng'], stdout=stream, check=True)
        text = (a.out/'stress-ng.dump').read_text()
        report['atomic_opcodes_present'] = {op: op in text for op in ('amoadd.', 'lr.', 'sc.')}
        if not all(report['atomic_opcodes_present'].values()):
            raise ValueError('Missing expected atomic instruction families')
        for file in binary.iterdir():
            if file.name in ('stress-ng', 'memtester', 'rvv_linux_smoke'):
                file.chmod(0o755)
        names = sorted(str(x.relative_to(overlay)) for x in overlay.rglob('*'))
        if any(not name.startswith('opt') for name in names):
            raise ValueError('Overlay may only add /opt/ara-tests')
        with (a.out/'overlay.cpio').open('wb') as stream:
            subprocess.run(['cpio', '--null', '-o', '--format=newc', '--owner=0:0'], cwd=overlay,
                           input=('\0'.join(names)+'\0').encode(), stdout=stream, check=True)
        with (a.out/'initramfs.cpio').open('wb') as stream:
            for file in (a.base, a.out/'overlay.cpio'):
                with file.open('rb') as source:
                    shutil.copyfileobj(source, stream)
        shutil.copy2(a.dtb, a.out/'ara_vcu118.dtb')
        end = 0x88000000+(a.out/'initramfs.cpio').stat().st_size
        if end >= 0x90000000:
            raise ValueError('Unexpectedly large test overlay')
        run(['fdtput', '-t', 'x', a.out/'ara_vcu118.dtb', '/chosen', 'linux,initrd-end', '0', f'{end:x}'])
        report.update(state='built_needs_reference', initrd_end=end,
                      overlay_entries=names, base_prefix_unchanged=True)
        for name in ['initramfs.cpio', 'ara_vcu118.dtb', 'overlay.cpio']:
            report['outputs'][name] = dict(sha256=digest(a.out/name), bytes=(a.out/name).stat().st_size)
        report['binaries'] = {x.name: digest(x) for x in binary.iterdir() if x.is_file()}
    except Exception as exc:
        report.update(state='failed', error=str(exc))
        raise
    finally:
        save()


if __name__ == '__main__':
    main()
