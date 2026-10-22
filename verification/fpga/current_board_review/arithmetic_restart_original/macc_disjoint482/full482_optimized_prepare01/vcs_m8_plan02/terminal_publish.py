"""Short terminal linearization, following the accepted M6 terminal latch."""
import json
import os
import signal
import threading
import time


class TerminalAbort(threading.Event):
    def __init__(self):
        super().__init__();self.lock=threading.RLock();self.closed=False

    def set(self):
        with self.lock:
            if not self.closed:super().set()


def write_json(path,data,mode='x'):
    with path.open(mode) as stream:
        json.dump(data,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())


def publish(out,terminal,abort,expires):
    signals={signal.SIGINT,signal.SIGTERM}
    previous=signal.pthread_sigmask(signal.SIG_BLOCK,signals)
    temporary=out/'complete.pending.json';target=out/'complete.json'
    try:
        if target.exists():raise ValueError('No terminal overwrite')
        terminal['aborted']=abort.is_set()
        write_json(temporary,terminal)
        # JSON and all checker/hash work precede the short decision. A delayed
        # callback cannot conceal absolute expiry. The latch closes at rename.
        with abort.lock:
            if abort.is_set() or signal.sigpending() & signals or time.monotonic()>=expires:
                abort.set();terminal.update(status='NOT_ACCEPTED_LATE_ABORT',aborted=True)
                write_json(temporary,terminal,mode='w')
            os.replace(temporary,target)
            abort.closed=True
            directory=os.open(out,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(directory)
            finally:os.close(directory)
    finally:signal.pthread_sigmask(signal.SIG_SETMASK,previous)
