"""Capture loader failures without reset, ptrace patches, or a new bitstream."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import uuid


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elf', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--serial-wheel', type=Path)
    p.add_argument('--port', default='COM6')
    p.add_argument('--qemu', action='store_true')
    p.add_argument('--selftest', action='store_true')
    p.add_argument('--metadata-core', action='store_true')
    p.add_argument('--metadata-trace', action='store_true')
    p.add_argument('--saved-core', help='Read an existing core without rerunning the failure')
    p.add_argument('--cancel-incomplete-upload', action='store_true',
                   help='Cancel only this observer\'s known unfinished shell heredoc')
    p.add_argument('--rounds', type=int, default=200, choices=range(1, 1001))
    p.add_argument('--seconds', type=int, default=180)
    p.add_argument('--image', type=Path)
    p.add_argument('--initramfs', type=Path)
    a = p.parse_args()
    if a.metadata_trace and (a.metadata_core or a.saved_core or a.selftest):
        p.error('Select only metadata tracing')
    if a.metadata_core and (a.selftest or a.cancel_incomplete_upload):
        p.error('Core collection cannot be combined with tracer recovery/selftest')
    if a.saved_core and (a.metadata_core or a.selftest or a.cancel_incomplete_upload):
        p.error('Select only saved core collection')
    payload = a.elf.read_bytes()
    if not payload.startswith(b'\x7fELF') or not 0 < len(payload) <= 32768:
        p.error('Small statically linked RV64 tracer required')
    a.out.mkdir(parents=True, exist_ok=False)
    report = dict(passed=False, reset=False, bitstream_changed=False,
                  scope='ptrace_observation_changes_scheduling_not_hardware_acceptance',
                  elf_sha256=hashlib.sha256(payload).hexdigest(), rounds=a.rounds,
                  qemu=a.qemu, selftest=a.selftest, state='connecting')
    data = bytearray()
    console = None
    tag = uuid.uuid4().hex[:12]
    guest = '/tmp/ara_loader_observer_'+tag

    def save():
        (a.out/'report.json').write_text(json.dumps(report, indent=2)+'\n')

    try:
        if a.qemu:
            import pexpect
            for path, digest in (
                (a.image, '716aef49389b25a0a3f4deac47de0bb69467a10f1057041cecd0f0621fbbf285'),
                (a.initramfs, '4c1f196a90cbba5cd73af81712c526067ab8e83efb7d303cbde829528f4e3b25'),
            ):
                if path is None or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                    raise ValueError('Wrong original kernel/rootfs reference')
            sdk = Path('/home/wangwy/openproject/cva6/cva6-sdk')
            command = [str(sdk/'buildroot/output/host/bin/qemu-system-riscv64'),
                       '-machine', 'virt', '-cpu', 'rv64,v=true,vlen=1024,elen=64',
                       '-smp', '1', '-m', '2G', '-no-reboot', '-display', 'none',
                       '-monitor', 'none', '-serial', 'stdio',
                       '-bios', str(sdk/'install64_qemu/fw_dynamic.bin'),
                       '-kernel', str(a.image), '-initrd', str(a.initramfs),
                       '-append', 'console=ttyS0,115200 earlycon=sbi loglevel=7 rdinit=/init unaligned_scalar_speed=unsupported unaligned_vector_speed=unsupported']
            console = pexpect.spawn(command[0], command[1:], timeout=.2)
            def read():
                try:
                    return console.read_nonblocking(4096, timeout=.2)
                except pexpect.TIMEOUT:
                    return b''
            send = console.send
        else:
            if a.serial_wheel:
                sys.path.insert(0, str(a.serial_wheel))
            import serial
            console = serial.Serial(a.port, 115200, timeout=.2, write_timeout=5,
                                    rtscts=False, dsrdtr=False)
            read = lambda: console.read(4096)
            send = console.write
        with (a.out/'uart.bin').open('wb') as log:
            def receive(pattern, seconds):
                start = len(data)
                deadline = time.monotonic()+seconds
                while time.monotonic() < deadline:
                    chunk = read()
                    if chunk:
                        data.extend(chunk)
                        log.write(chunk)
                        log.flush()
                        match = re.search(pattern, data[start:])
                        if match:
                            return match
                raise TimeoutError('No expected response; no further commands or resets')

            def line(value):
                save()
                wire = value.encode('ascii')+b'\n'
                if a.qemu:
                    send(wire)
                else:
                    for b in wire:
                        send(bytes([b]))
                        time.sleep(.02)

            if a.qemu:
                receive(rb'/ # ', 120)
            elif a.cancel_incomplete_upload:
                send(b'\x03')
                receive(rb'/ # ', 20)
            line("printf '\\n%s\\n' READY_"+tag)
            receive(rb'(?:^|[\r\n])READY_'+tag.encode()+rb'[\r\n]', 20)
            if a.saved_core:
                from capture_metadata_core import collect_saved
                collect_saved(line, receive, report, a.out, a.saved_core)
                return 0 if report['passed'] else 1
            if a.metadata_core:
                from capture_metadata_core import run
                run(line, receive, report, data, a.out, tag, a.rounds, a.seconds)
                return 0 if report['passed'] else 1
            report['state'] = 'uploading'; save()
            line("base64 -d > "+guest+" <<'OBS_EOF'")
            receive(rb'> $', 20)
            encoded = base64.b64encode(payload)
            for offset in range(0, len(encoded), 64):
                # Bound each terminal input line; PS2 acknowledges consumption.
                line(encoded[offset:offset+64].decode('ascii'))
                receive(rb'> $', 20)
            line('OBS_EOF')
            receive(rb'/ # ', 30)
            line(f"sha256sum {guest}")
            receive(report['elf_sha256'].encode()+rb'\s+'+guest.encode()+rb'[\r\n]', 30)
            line(f"chmod +x {guest}; printf 'probe\\n' > /tmp/ara_loader_probe_input")
            receive(rb'/ # ', 20)
            report['state'] = 'testing'; save()
            if a.metadata_trace:
                from linux_stability_matrix import process_case
                work='/tmp/ara_metadata_trace_'+tag
                command=list(process_case(work,'metadata',a.rounds))[1][1]
                command='set -e; mkdir '+work+'; '+command
                report.update(scope='original_metadata_with_ptrace_fork_exec_stops',
                              work=work, command=command)
                line(guest+" --command '"+command.replace("'", "'\"'\"'")+"'")
            else:
                line(guest+(' --selftest' if a.selftest else ' '+str(a.rounds)))
            m = receive(rb'(?:^|[\r\n])(TRACE_PASS|TRACE_SELFTEST_OK|TRACE_HOLDING|TRACE_TREE_FAILED)[^\r\n]*[\r\n]', a.seconds)
            report['state'] = m[1].decode()
            expected = b'TRACE_SELFTEST_OK' if a.selftest else b'TRACE_PASS'
            from linux_stability import has_kernel_fault
            report['kernel_fault_reported'] = has_kernel_fault(data.decode(errors='replace'))
            report['passed'] = m[1] == expected and not report['kernel_fault_reported']
            report['fault_child_retained'] = m[1] == b'TRACE_HOLDING'
    except Exception as exc:
        report['error'] = str(exc)
    finally:
        if console is not None:
            console.close()
        (a.out/'uart.txt').write_text(data.decode(errors='replace'))
        save()
        print(json.dumps(report), flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
