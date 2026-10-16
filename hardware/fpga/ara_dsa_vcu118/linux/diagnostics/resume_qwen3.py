"""Inspect the existing foreground hash job, then resume that same job."""
import argparse
import json
from pathlib import Path
import re
import sys
import time


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--software', type=Path, required=True)
    p.add_argument('--observe-only', action='store_true')
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(a.software))
    import host_load as host
    data = bytearray()
    report = dict(state='attaching_existing_job', passed=False, restarted=False)
    start = time.monotonic()
    def save():
        report['elapsed_seconds'] = time.monotonic() - start
        (a.out / 'report.json').write_text(json.dumps(report, indent=2)+'\n')
        (a.out / 'uart.bin').write_bytes(data)
    try:
        with host.serial_module().Serial('COM6', 115200, timeout=.3, rtscts=False, dsrdtr=False) as port:
            def receive(pattern, seconds):
                begin = len(data)
                deadline = time.monotonic() + seconds
                while time.monotonic() < deadline:
                    chunk = port.read(4096)
                    if chunk:
                        data.extend(chunk)
                        print(chunk.decode(errors='replace'), end='', flush=True)
                    save()
                    match = re.search(pattern, data[begin:])
                    if match:
                        return match
                raise RuntimeError('Observation timeout; do not restart guest job')
            def send(command):
                for b in command.encode():
                    port.write(bytes([b]))
                    time.sleep(.02)
            if not a.observe_only:
                port.write(b'\x1a')
                receive(rb'(?:^|[\r\n])[^\r\n]*# $', 20)
                send("jobs -l; for p in $(pidof sha256sum); do echo HASH_PID=$p; cat /proc/$p/fdinfo/*; done; echo HASH_INSPECT_DONE\n")
                receive(rb'(?:^|[\r\n])HASH_INSPECT_DONE[\r\n]', 30)
                if b'Stopped' not in data:
                    raise RuntimeError('No stopped job confirmed; manual inspection required')
                report['state'] = 'resumed_existing_job'
                send("fg; rc=$?; printf '\\nQWEN3_RESUMED_DONE:%s\\n' \"$rc\"\n")
            else:
                report['state'] = 'observing_existing_job_no_commands_sent'
            done = receive(rb'(?:^|[\r\n])QWEN3_(?:RESUMED_)?DONE:(\d+)[\r\n]', 7200)
            report['exit_code'] = int(done[1])
            tokens = re.search(rb'main: decoded (\d+) tokens in ([\d.]+) s, speed: ([\d.]+) t/s', data)
            if tokens:
                report.update(decoded_tokens=int(tokens[1]), inference_seconds=float(tokens[2]),
                              reported_tokens_per_second=float(tokens[3]))
            report['passed'] = bool(report['exit_code'] == 0 and tokens and int(tokens[1]) > 0)
            report['state'] = 'completed' if report['passed'] else 'failed'
    except Exception as exc:
        report.update(state='needs_inspection', error=str(exc))
    finally:
        save()
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
