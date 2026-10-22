#!/usr/bin/env python3
"""Wait for a Linux filesystem event; file appearance is NOT DUT acceptance."""
import argparse
import ctypes
import os
from pathlib import Path
import select
import struct
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("terminal", type=Path)
    parser.add_argument("--timeout", type=float, default=21600)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("timeout must be positive")
    target = args.terminal.absolute()
    libc = ctypes.CDLL(None, use_errno=True)
    libc.inotify_init1.argtypes = [ctypes.c_int]
    libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
    fd = libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
    if fd < 0:
        raise OSError(ctypes.get_errno(), "inotify_init1")
    try:
        # Watch before checking existence, so an atomic publication cannot be missed.
        if libc.inotify_add_watch(fd, os.fsencode(target.parent), 0x08 | 0x80) < 0:
            raise OSError(ctypes.get_errno(), "inotify_add_watch", str(target.parent))
        deadline = time.monotonic() + args.timeout
        print("WATCHING " + str(target), flush=True)
        while not target.is_file():
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([fd], [], [], remaining)[0]:
                print("OBSERVATION_TIMEOUT_NOT_JOB_TERMINAL", flush=True)
                return 2
            data = os.read(fd, 65536)
            offset = 0
            while offset < len(data):
                _, _, _, size = struct.unpack_from("iIII", data, offset)
                name = os.fsdecode(data[offset + 16:offset + 16 + size].split(b"\0", 1)[0])
                offset += 16 + size
                if name == target.name and target.is_file():
                    break
        print("FILE_APPEARED_NOT_ACCEPTED " + str(target), flush=True)
        return 0
    finally:
        os.close(fd)


if __name__ == "__main__":
    raise SystemExit(main())
