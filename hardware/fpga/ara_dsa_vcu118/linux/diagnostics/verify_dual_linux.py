"""Check Linux memory visibility and actual DDR2-backed user pages on COM6."""
import argparse
import json
from pathlib import Path
import re
import sys
import time


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--software', type=Path, required=True)
    p.add_argument('--probes', type=Path, required=True)
    p.add_argument('--vivado', required=True)
    a = p.parse_args()
    sys.path.insert(0, str(a.software))
    import host_load as host
    from host_transport import VivadoTransport
    a.out.mkdir(parents=True, exist_ok=False)
    report = dict(passed=False, scope='64 MiB user allocation, not full-capacity memory test')
    data = bytearray()
    try:
        with VivadoTransport(a.out / 'transport', vivado=a.vivado, probes=a.probes) as t, \
                host.serial_module().Serial('COM6', 115200, timeout=.2, rtscts=False, dsrdtr=False) as port:
            report['before'] = host.capture_snapshot(t)
            if report['before']['identity']['caps'] != 3:
                raise RuntimeError('Expected dual-DDR hardware')
            port.write(b'\n')
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                data.extend(port.read(4096))
                if re.search(rb'(?:^|[\r\n])[^\r\n]*# $', data):
                    break
            else:
                raise RuntimeError('No shell prompt')
            command = "cat /proc/iomem; cat /proc/meminfo; /ddr_pages; printf '\\nDUAL_PAGES_RC:%s\\n' \"$?\"\n"
            report['command'] = command
            for byte in command.encode('ascii'):
                port.write(bytes([byte]))
                time.sleep(.02)
            start = time.monotonic()
            while time.monotonic() - start < 480:
                chunk = port.read(4096)
                if chunk:
                    data.extend(chunk)
                    print(chunk.decode('ascii', errors='replace'), end='', flush=True)
                    (a.out / 'uart.bin').write_bytes(data)
                done = re.search(rb'(?:^|[\r\n])DUAL_PAGES_RC:(\d+)[\r\n]', data)
                if done:
                    report['exit_code'] = int(done[1])
                    break
            else:
                raise RuntimeError('Memory probe timeout; leave board running for diagnosis')
            report['seconds'] = time.monotonic() - start
            report['after'] = host.capture_snapshot(t)
            text = data.decode('ascii', errors='replace')
            mem = re.search(r'MemTotal:\s+(\d+) kB', text)
            pages = re.search(r'DDR_PAGES bytes=(\d+) page_size=(\d+) ddr1=(\d+) ddr2=(\d+) outside=(\d+) data_verified=1', text)
            report['memtotal_kib'] = int(mem[1]) if mem else None
            report['pages'] = dict(zip(('bytes', 'page_size', 'ddr1', 'ddr2', 'outside'),
                                      map(int, pages.groups()))) if pages else None
            report['traffic_delta'] = {bank: {key: report['after'][bank][key]-report['before'][bank][key]
                for key in ('ar_count', 'aw_count', 'r_bytes', 'w_bytes')}
                for bank in ('ddr1', 'ddr2')}
            report['passed'] = bool(report['exit_code'] == 0 and mem and int(mem[1]) > 3 * 1024 * 1024
                and pages and int(pages[4]) > 0 and int(pages[5]) == 0
                and all(report['after'][bank]['error_count'] == 0 for bank in ('ddr1', 'ddr2'))
                and report['traffic_delta']['ddr2']['r_bytes'] > 0
                and report['traffic_delta']['ddr2']['w_bytes'] > 0)
    except Exception as exc:
        report['error'] = str(exc)
    finally:
        (a.out / 'uart.bin').write_bytes(data)
        (a.out / 'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print('\nDUAL_LINUX_PASSED', report['passed'], flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
