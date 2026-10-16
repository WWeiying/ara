"""Bounded progress experiment, not a replacement for the original acceptance test."""
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
    p.add_argument('--probes', type=Path, required=True)
    p.add_argument('--vivado', required=True)
    p.add_argument('--iterations', type=int, default=10)
    p.add_argument('--original', action='store_true', help='No per-iteration prints; observe up to 600s')
    a = p.parse_args()
    if not 1 <= a.iterations <= 200:
        p.error('Iterations must be 1..200')
    sys.path.insert(0, str(a.software))
    import host_load as host
    from host_transport import VivadoTransport
    a.out.mkdir(parents=True, exist_ok=False)
    report = dict(diagnostic_only=True, reset=False, iterations=a.iterations,
                  progress=[], snapshots=[], original_acceptance_passed=False)
    data = bytearray()
    def save():
        (a.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        (a.out / 'uart.bin').write_bytes(data)
    try:
        with VivadoTransport(a.out / 'transport', vivado=a.vivado, probes=a.probes) as t, \
                host.serial_module().Serial('COM6', 115200, timeout=.2, rtscts=False, dsrdtr=False) as port:
            report['snapshots'].append(host.capture_snapshot(t))
            port.write(b'\n')
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                data.extend(port.read(4096))
                if re.search(rb'(?:^|[\r\n])[^\r\n]*[#$] $', data):
                    break
            else:
                raise RuntimeError('No initial shell prompt; nothing launched')
            command = (f"( set -e; n=0; while [ $n -lt {a.iterations} ]; do "
                       'test "$(printf abc | cat | wc -c)" -eq 3; n=$((n+1)); '
                       "printf '\\nPIPE_DIAG_STEP:%s\\n' \"$n\"; done ); "
                       "printf '\\nPIPE_DIAG_DONE:%s\\n' \"$?\"\n")
            if a.original:
                from linux_stability_matrix import matrix
                original = next(s[1] for s in matrix('/tmp/unused', 'process', a.iterations)
                                if s[0] == 'pipes')
                command = "( set -e; " + original + "); printf '\\nPIPE_DIAG_DONE:%s\\n' \"$?\"\n"
                report['original_command'] = original
            report['command'] = command
            report['state'] = 'running'
            start = time.monotonic()
            for byte in command.encode('ascii'):
                port.write(bytes([byte]))
                time.sleep(.02)
            sent = time.monotonic()
            report['command_tx_seconds'] = sent - start
            next_sample = sent
            while time.monotonic() - sent < (600 if a.original else 300):
                data.extend(port.read(4096))
                for m in re.finditer(rb'(?:^|[\r\n])PIPE_DIAG_STEP:(\d+)[\r\n]', data):
                    n = int(m[1])
                    if not any(row['iteration'] == n for row in report['progress']):
                        row = dict(iteration=n, seconds=time.monotonic()-sent)
                        report['progress'].append(row)
                        print('PROGRESS', row, flush=True)
                done = re.search(rb'(?:^|[\r\n])PIPE_DIAG_DONE:(\d+)[\r\n]', data)
                if done:
                    report.update(state='completed', exit_code=int(done[1]), seconds=time.monotonic()-sent)
                    break
                if time.monotonic() >= next_sample:
                    snap = host.capture_snapshot(t)
                    report['snapshots'].append(snap)
                    print('SNAPSHOT', snap['core'], flush=True)
                    next_sample = time.monotonic() + 30
                save()
            else:
                report.update(state='diagnostic_timeout', seconds=time.monotonic()-sent)
            report['snapshots'].append(host.capture_snapshot(t))
    except Exception as exc:
        report.update(state='error', error=str(exc))
    finally:
        save()
    print(report['state'], a.out, flush=True)


if __name__ == '__main__':
    main()
