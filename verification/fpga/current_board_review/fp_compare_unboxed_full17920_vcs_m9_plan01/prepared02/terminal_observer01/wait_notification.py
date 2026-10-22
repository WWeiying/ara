"""Single foreground filesystem wait to ensure terminal notification is consumed."""
import json
from pathlib import Path
import subprocess
import time

HERE = Path(__file__).resolve().parent
G = HERE.parents[2]
DEADLINE = 1792024000.28614 + 13200 + 300 + 180


def main():
    timeout = max(1, DEADLINE-time.time())
    cmd = ['/usr/bin/python3', '-B', str(G/'wait_terminal.py'),
           str(HERE/'notification.json'), '--timeout', str(timeout)]
    with (HERE/'notification_wait.command.json').open('x') as f:
        json.dump(dict(command=cmd,started_at=time.time(),CSV_reads=0,simulator_queries=0),f,indent=2)
    start = time.monotonic()
    child = subprocess.run(cmd,text=True,capture_output=True,timeout=timeout+15)
    with (HERE/'notification_wait.receipt.json').open('x') as f:
        json.dump(dict(actual_wait_exit=child.returncode,elapsed_s=time.monotonic()-start,
                       stdout=child.stdout,stderr=child.stderr),f,indent=2)
    print(child.stdout,flush=True)
    if child.returncode:
        print(child.stderr,flush=True)
        return child.returncode
    print((HERE/'notification.json').read_text(),flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
