#!/usr/bin/env python3
"""Wait on result-file filesystem events, then run one independent pair audit."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import time

from audit import digest, require


def terminal(run):
    path = run/'result.json'
    if not path.exists(): return False
    state = json.loads(path.read_text()).get('state')
    require(state != 'FAIL', 'Worker failed: '+str(run))
    require(state == 'PASS', 'Unexpected terminal state: '+str(state))
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--wide', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); roots = [r.resolve(strict=True) for r in (args.base, args.wide)]
    require(not args.output.exists(), 'Fresh collection output required')
    helper = Path(__file__).with_name('collect_projection_native.py')
    helper_sha = digest(helper)
    libc = ctypes.CDLL(None, use_errno=True)
    libc.inotify_init1.argtypes = [ctypes.c_int]; libc.inotify_init1.restype = ctypes.c_int
    libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
    libc.inotify_add_watch.restype = ctypes.c_int
    fd = libc.inotify_init1(os.O_CLOEXEC | os.O_NONBLOCK)
    require(fd >= 0, 'inotify unavailable')
    try:
        # Install watches BEFORE testing existence, so a completion cannot be missed.
        for root in roots:
            require(libc.inotify_add_watch(fd, os.fsencode(root), 0x8 | 0x80 | 0x100) >= 0, 'Watch failed')
        deadline = time.monotonic()+11400
        print(json.dumps(dict(state='WAITING_FOR_RESULT_EVENTS', pid=os.getpid(),
                              roots=list(map(str, roots)), collector_sha256=helper_sha)), flush=True)
        while not all([terminal(root) for root in roots]):
            remaining = deadline-time.monotonic(); require(remaining > 0, 'Completion deadline reached')
            ready, _, _ = select.select([fd], [], [], remaining)
            require(bool(ready), 'Completion deadline reached')
            os.read(fd, 65536)  # Wake only on filesystem events; no timed polling.
        require(digest(helper) == helper_sha, 'Collector changed while waiting')
        subprocess.run([sys.executable, '-B', helper, '--base', roots[0], '--wide', roots[1],
                        '--output', args.output], check=True, timeout=600)
        print('COLLECTION_COMPLETE', flush=True)
    finally: os.close(fd)


if __name__ == '__main__': main()
