"""Bounded Linux directory events, never periodic simulation polling."""
import ctypes
import os
from pathlib import Path
import select
import time

def wait_terminal(directory, timeout):
    directory=Path(directory)
    lib=ctypes.CDLL(None,use_errno=True)
    lib.inotify_init1.argtypes=[ctypes.c_int]
    lib.inotify_add_watch.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_uint32]
    fd=lib.inotify_init1(os.O_CLOEXEC|os.O_NONBLOCK)
    if fd<0:raise OSError(ctypes.get_errno(),'inotify_init1')
    try:
        # Register before checking existence to avoid a missed completion race.
        if lib.inotify_add_watch(fd,os.fsencode(directory),0x8|0x80|0x400|0x800)<0:
            raise OSError(ctypes.get_errno(),'inotify_add_watch')
        deadline=time.monotonic()+timeout
        while not all((directory/n).is_file() for n in ('complete.json','service_exit.json')):
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('Missing real terminal or actual systemd exit; no acceptance')
            readable,_,_=select.select([fd],[],[],remaining)
            if not readable:raise TimeoutError('Terminal file-event deadline; no retry')
            os.read(fd,65536)
        return True
    finally:os.close(fd)
