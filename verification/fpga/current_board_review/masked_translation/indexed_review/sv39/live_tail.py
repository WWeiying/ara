"""Event-driven append reader; no periodic simulation or service polling."""
import ctypes
import os
from pathlib import Path
import select
import subprocess
import threading


class DirectoryEvents:
    def __init__(self,root):
        self.root=Path(root); self.watched=set()
        self.lib=ctypes.CDLL(None,use_errno=True)
        self.lib.inotify_init1.argtypes=[ctypes.c_int]
        self.lib.inotify_add_watch.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_uint32]
        self.fd=self.lib.inotify_init1(os.O_NONBLOCK|os.O_CLOEXEC)
        if self.fd<0: raise OSError(ctypes.get_errno(),'inotify_init1')
        self.refresh()

    def refresh(self):
        # Recursive discovery closes the create-before-watch race for nested artifacts.
        for p in [self.root,*self.root.rglob('*')]:
            if not p.is_dir() or p in self.watched: continue
            if self.lib.inotify_add_watch(self.fd,os.fsencode(p),0x2|0x8|0x80|0x100)<0:
                raise OSError(ctypes.get_errno(),'inotify_add_watch')
            self.watched.add(p)

    def drain(self):
        while True:
            try:
                if not os.read(self.fd,65536): break
            except BlockingIOError: break
        self.refresh()

    def close(self): os.close(self.fd)


def wait_append(process,events,path,on_line,on_failure):
    """Consume only complete lines on filesystem events; child exit wakes via pipe."""
    done_r,done_w=os.pipe2(os.O_CLOEXEC)
    def reaper():
        process.wait()
        os.write(done_w,b'x')
    thread=threading.Thread(target=reaper,daemon=True); thread.start()
    stream=None; partial=''; failure=None
    def consume(final=False):
        nonlocal stream,partial
        if stream is None and Path(path).exists(): stream=Path(path).open()
        if stream is None: return
        text=partial+stream.read()
        lines=text.split('\n'); partial=lines.pop()
        for line in lines: on_line(line)
        if final and partial: raise ValueError('Incomplete final CSV row')
    try:
        consume()
        while True:
            ready,_,_=select.select([events.fd,done_r],[],[])
            if events.fd in ready:
                events.drain(); consume()
            if done_r in ready:
                consume(final=True); break
    except Exception as error:
        failure=error
        on_failure(error)
        if process.poll() is None: process.terminate()
        try: process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            # A sealed runner normally cancels its simv process group on SIGTERM.
            # The independent service's cgroup hard limit remains the final backstop.
            process.kill(); process.wait()
    finally:
        thread.join(timeout=1)
        if stream: stream.close()
        os.close(done_r); os.close(done_w); events.close()
    if failure: raise failure
    return process.returncode
