"""One restored-signal final decision; never a late-aborted record with exit0."""
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


def failed(terminal,abort):
    abort.set();terminal.update(status='NOT_ACCEPTED_LATE_ABORT',aborted=True)


def publish(out,terminal,abort,expires):
    signals={signal.SIGINT,signal.SIGTERM}
    previous=signal.pthread_sigmask(signal.SIG_BLOCK,signals)
    temporary=out/'complete.pending.json';target=out/'complete.json'
    try:
        if target.exists():raise ValueError('No terminal overwrite')
        terminal['aborted']=abort.is_set()
        write_json(temporary,terminal)
        with abort.lock:
            if abort.is_set() or signal.sigpending() & signals or time.monotonic()>=expires:
                failed(terminal,abort);write_json(temporary,terminal,mode='w')
            os.replace(temporary,target)
    finally:
        # Pending handlers still affect the open latch. In particular a signal
        # arriving inside rename must not be discarded by premature closure.
        signal.pthread_sigmask(signal.SIG_SETMASK,previous)
    with abort.lock:
        # Freeze the cancellation flags at one explicit point after restoring
        # handlers. A handler that already set abort cannot be lost between a
        # conditional read and latch closure; post-seal cancellation is later.
        abort.closed=True
        if abort.is_set() or time.monotonic()>=expires:
            threading.Event.set(abort)
            if terminal['status']!='NOT_ACCEPTED_LATE_ABORT':
                terminal.update(status='NOT_ACCEPTED_LATE_ABORT',aborted=True)
                try:
                    write_json(temporary,terminal);os.replace(temporary,target)
                except BaseException:
                    # An unpublishable correction must not leave candidate PASS.
                    target.unlink(missing_ok=True)
                    raise
        # Before worker exit, its return status and the atomically visible final
        # record agree. Any candidate visible earlier requires actual worker0.
    # Only file fsync+atomic visibility are claimed, not directory power-loss
    # durability; there is no new fallible directory IO after the decision.
