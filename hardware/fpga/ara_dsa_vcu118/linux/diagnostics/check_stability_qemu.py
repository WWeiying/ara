"""Validate matrix commands on the hash-pinned Linux/rootfs reference."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import pexpect
from linux_stability import validate
from linux_stability_matrix import matrix, PROFILES, process_case, REMAINING_PROCESS_CASES


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image', type=Path, required=True)
    p.add_argument('--initramfs', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--extended-build', type=Path)
    p.add_argument('--remaining-process', action='store_true')
    a = p.parse_args()
    if a.remaining_process and a.extended_build:
        p.error('Select only one reference suite')
    initrd_hash = '4c1f196a90cbba5cd73af81712c526067ab8e83efb7d303cbde829528f4e3b25'
    if a.extended_build:
        build = json.loads((a.extended_build/'build.json').read_text())
        if build['state'] != 'built_needs_reference' or build['base_sha256'] != initrd_hash:
            raise ValueError('Unexpected extended build')
        initrd_hash = build['outputs']['initramfs.cpio']['sha256']
    for path, digest in ((a.image, '716aef49389b25a0a3f4deac47de0bb69467a10f1057041cecd0f0621fbbf285'),
                         (a.initramfs, initrd_hash)):
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('Wrong reference image: '+str(path))
    a.out.mkdir(parents=True, exist_ok=False)
    sdk = Path('/home/wangwy/openproject/cva6/cva6-sdk')
    command = [str(sdk/'buildroot/output/host/bin/qemu-system-riscv64'),
               '-machine', 'virt', '-cpu', 'rv64,v=true,vlen=1024,elen=64',
               '-smp', '1', '-m', '2G', '-no-reboot', '-display', 'none',
               '-monitor', 'none', '-serial', 'stdio',
               '-bios', str(sdk/'install64_qemu/fw_dynamic.bin'),
               '-kernel', str(a.image), '-initrd', str(a.initramfs),
               '-append', 'console=ttyS0,115200 earlycon=sbi loglevel=7 rdinit=/init unaligned_scalar_speed=unsupported unaligned_vector_speed=unsupported']
    report = dict(passed=False, scope='command_oracle_reference_not_FPGA_acceptance', results=[])
    profiles = PROFILES
    planner = lambda work, profile: matrix(work, profile, 3)
    if a.remaining_process:
        profiles = REMAINING_PROCESS_CASES
        planner = lambda work, profile: process_case(work, profile, 3)
        report.update(suite='isolated_remaining_process', reduced_reference_load=True)
        report['tool_hashes'] = {name: hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest()
                                for name in ('linux_stability.py', 'linux_stability_matrix.py',
                                             'check_stability_qemu.py')}
    if a.extended_build:
        from extended_stability import PROFILES as profiles, extended_plan, result_status
        planner = lambda work, profile: extended_plan(work, profile, reference=True)
        report.update(initramfs_sha256=initrd_hash, reduced_reference_load=True)
        report['tool_hashes'] = {name: hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest()
                                for name in ('extended_stability.py', 'linux_stability.py',
                                             'linux_stability_matrix.py', 'check_stability_qemu.py')}
    child = None
    try:
        with (a.out/'uart.txt').open('w') as log:
            child = pexpect.spawn(command[0], command[1:], encoding='utf-8', timeout=120)
            child.logfile = log
            child.expect('/ # ')
            for profile in profiles:
                work = '/tmp/matrix_'+profile
                for i,(name,cmd,timeout,kind) in enumerate(planner(work, profile)):
                    token = f'QREF_{profile}_{i}'
                    start = time.monotonic()
                    child.sendline(f"( set -e; {cmd} ); printf '\\n%s:%s\\n' {token} \"$?\"")
                    child.expect(r'(?:\r|\n)'+token+r':([0-9]+)[\r\n]', timeout=timeout)
                    code = int(child.match.group(1))
                    output = child.before
                    report['results'].append(dict(profile=profile, name=name, exit_code=code,
                                                   seconds=time.monotonic()-start, output=output))
                    if a.extended_build:
                        status = result_status(code, kind, output, work)
                        if status != 'passed':
                            raise ValueError('Reference unsupported: '+name)
                    else:
                        if code:
                            raise RuntimeError(f'{profile}/{name}: exit {code}')
                        validate(kind, output, work)
                    report['results'][-1]['passed'] = True
                    child.expect('/ # ')
                    print('PASS', profile, name, flush=True)
                    (a.out/'report.json').write_text(json.dumps(report, indent=2))
            report['passed'] = True
    except Exception as exc:
        report['error'] = str(exc)
        print('FAILED', exc, flush=True)
    finally:
        if child is not None:
            child.close(force=True)
        (a.out/'report.json').write_text(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
