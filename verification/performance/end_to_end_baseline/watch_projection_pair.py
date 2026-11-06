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


def collector_path(full):
    require(type(full) is bool, 'Explicit collector scope required')
    return Path(__file__).with_name('collect_full_projection.py' if full else 'collect_projection_native.py')


def wait_for_results(roots, timeout=11400):
    roots = [Path(root).absolute() for root in roots]
    require(len(roots) == 2 and roots[0] != roots[1] and
            all(root == root.resolve() and root.parent.is_dir() for root in roots), 'Result roots')
    libc = ctypes.CDLL(None, use_errno=True)
    libc.inotify_init1.argtypes = [ctypes.c_int]; libc.inotify_init1.restype = ctypes.c_int
    libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
    libc.inotify_add_watch.restype = ctypes.c_int
    libc.inotify_rm_watch.argtypes = [ctypes.c_int, ctypes.c_int]
    libc.inotify_rm_watch.restype = ctypes.c_int
    fd = libc.inotify_init1(os.O_CLOEXEC | os.O_NONBLOCK)
    require(fd >= 0, 'inotify unavailable')
    try:
        mask = 0x8 | 0x80 | 0x100
        parents = {}
        # Parent watches also cover workers that have not created their run dirs.
        for parent in {root.parent for root in roots}:
            watch = libc.inotify_add_watch(fd, os.fsencode(parent), mask)
            require(watch >= 0, 'Parent watch failed'); parents[parent] = watch
        watched = set(); deadline = time.monotonic()+timeout
        while True:
            for root in roots:
                if root.exists() and root not in watched:
                    require(root.is_dir() and root == root.resolve(), 'Aliased result directory')
                    require(libc.inotify_add_watch(fd, os.fsencode(root), mask) >= 0, 'Result watch failed')
                    watched.add(root)
            # Check AFTER installing watches: already-completed workers are safe too.
            if len(watched) == 2:
                for parent, watch in tuple(parents.items()):
                    require(libc.inotify_rm_watch(fd, watch) == 0, 'Parent watch removal failed')
                    del parents[parent]
            if all([terminal(root) if root in watched else False for root in roots]): return
            remaining = deadline-time.monotonic(); require(remaining > 0, 'Completion deadline reached')
            ready, _, _ = select.select([fd], [], [], remaining)
            require(bool(ready), 'Completion deadline reached')
            os.read(fd, 65536)  # Wake only on filesystem events; no timed polling.
    finally: os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--wide', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--full', action='store_true', help='Full Q/K/V output dimensions, not the N128 prefix')
    args = parser.parse_args(); roots = [r.absolute() for r in (args.base, args.wide)]
    require(not args.output.exists(), 'Fresh collection output required')
    helper = collector_path(args.full); helper_sha = digest(helper)
    print(json.dumps(dict(state='WAITING_FOR_RESULT_EVENTS', pid=os.getpid(),
                          roots=list(map(str, roots)), collector_sha256=helper_sha)), flush=True)
    wait_for_results(roots)
    require(digest(helper) == helper_sha, 'Collector changed while waiting')
    subprocess.run([sys.executable, '-B', helper, '--base', roots[0], '--wide', roots[1],
                    '--output', args.output], check=True, timeout=600)
    print('COLLECTION_COMPLETE', flush=True)


if __name__ == '__main__': main()
