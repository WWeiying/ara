"""Expose hidden legacy initramfs tests without resetting the running board."""
import argparse
import json
from pathlib import Path
import re
import sys
import time
import uuid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--guest-directory', required=True)
    parser.add_argument('--expose', action='store_true')
    parser.add_argument('--inspect-view')
    parser.add_argument('--source-directory')
    args = parser.parse_args()
    if not re.fullmatch(r'/tmp/width_[0-9a-f]{12}', args.guest_directory):
        raise ValueError('Invalid guest directory')
    args.out.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, r'D:\fpga_runs\ara_dual_linux_memory_20261006_01\tools\software')
    import host_load
    token = 'PRELOAD_' + uuid.uuid4().hex[:12]
    commands = ['cat /proc/mounts', 'cat /init', 'ls -ld ' + args.guest_directory]
    if args.inspect_view:
        if not re.fullmatch(r'/mnt/rvv_preload_[0-9a-f]{12}', args.inspect_view):
            raise ValueError('Invalid root view')
        commands = ['cat /proc/mounts', f'ls -la {args.inspect_view}/tmp',
                    'dmesg | grep -i -e initrd -e initramfs -e unpack',
                    'hexdump -C /sys/firmware/devicetree/base/chosen/linux,initrd-end']
    if args.expose:
        # A nonrecursive root bind reveals files beneath the /tmp submount.
        view = '/mnt/rvv_preload_' + uuid.uuid4().hex[:12]
        commands = [f'mkdir -p {view}', f'mount -o bind / {view}',
                    f'test -d {view}{args.guest_directory}',
                    f'cp -a {view}{args.guest_directory} /tmp/',
                    f'umount {view}', f'rmdir {view}',
                    f'ls {args.guest_directory} | wc -l']
    if args.source_directory:
        if args.source_directory != '/opt/rvv-preload/' + args.guest_directory.rsplit('/', 1)[1]:
            raise ValueError('Invalid preload source')
        commands = [f'test -d {args.source_directory}',
                    f'cp -a {args.source_directory} /tmp/',
                    f'ls {args.guest_directory} | wc -l']
    command = ' && '.join(commands) if args.expose or args.source_directory else '; '.join(commands)
    line = f"( {command} ); printf '\\n%s:%s\\n' {token} \"$?\"\n"
    data = bytearray()
    result = dict(board_reset=False, rtl_modified=False, guest_directory=args.guest_directory)
    try:
        with host_load.serial_module().Serial('COM6', 115200, timeout=.2) as port:
            for byte in line.encode('ascii'):
                port.write(bytes([byte])); time.sleep(.02)
            deadline = time.monotonic() + 60
            pattern = re.compile(rb'[\r\n]' + token.encode() + rb':(\d+)[\r\n]')
            while time.monotonic() < deadline:
                data.extend(port.read(4096))
                match = pattern.search(data)
                if match:
                    result['exit_code'] = int(match[1])
                    break
            else:
                raise TimeoutError('No shell completion; scene preserved')
    except Exception as exc:
        result['error'] = str(exc)
    finally:
        (args.out / 'uart.bin').write_bytes(data)
        (args.out / 'report.json').write_text(json.dumps(result, indent=2) + '\n')
    print(data.decode(errors='replace'))
    return 0 if result.get('exit_code') == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
