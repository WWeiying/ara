"""Transfer and run the small indexed-load control/overlap test on existing Linux."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import sys
import time

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--software', type=Path, required=True)
p.add_argument('--elf', type=Path, required=True)
p.add_argument('--out', type=Path, required=True)
p.add_argument('--exit-only', action='store_true', help='For a test that reports all checks through its exit code')
a = p.parse_args()
payload = a.elf.read_bytes()
if not payload.startswith(b'\x7fELF') or len(payload) > 32768:
    raise ValueError('Expected ELF of at most 32 KiB')
a.out.mkdir(parents=True, exist_ok=False)
sys.path.insert(0, str(a.software))
import host_load
data = bytearray()
report = dict(passed=False, sha256=hashlib.sha256(payload).hexdigest())
try:
    with host_load.serial_module().Serial('COM6', 115200, timeout=.2) as port:
        def send(s):
            for byte in s.encode():
                port.write(bytes([byte]))
                time.sleep(.02)
        def receive(pattern, seconds):
            start = len(data)
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                data.extend(port.read(4096))
                m = re.search(pattern, data[start:])
                if m:
                    return m
            raise TimeoutError('Observation deadline; guest not interrupted')
        port.write(b'\x03')
        time.sleep(1)
        send("\nprintf '\\nINDEX_%s\\n' READY\n")
        receive(rb'\r?\nINDEX_READY\r?\n', 15)
        send("base64 -d > /tmp/indexed_overlap <<'INDEX_EOF'\n")
        enc = base64.b64encode(payload)
        for offset in range(0, len(enc), 64):
            send((enc[offset:offset+64] + b'\n').decode())
        send("INDEX_EOF\n")
        time.sleep(.5)
        send("h=$(sha256sum /tmp/indexed_overlap); "
             f"[ \"${{h%% *}}\" = {report['sha256']} ] && "
             "chmod +x /tmp/indexed_overlap && /tmp/indexed_overlap; "
             "r=$?; printf '\\nINDEX_DONE:%s\\n' \"$r\"\n")
        m = receive(rb'\r?\nINDEX_DONE:(\d+)\r?\n', 90)
        report['exit_code'] = int(m[1])
        report['control_ok'] = b'CONTROL_OK' in data
        report['overlap_ok'] = b'OVERLAP_OK' in data
        report['passed'] = report['exit_code'] == 0 and report['control_ok'] and report['overlap_ok']
        if a.exit_only:
            report['passed'] = report['exit_code'] == 0
        report['verification'] = 'exit_code' if a.exit_only else 'exit_code_and_control_overlap_markers'
except Exception as exc:
    report['error'] = str(exc)
finally:
    (a.out / 'uart.bin').write_bytes(data)
    (a.out / 'report.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report))
