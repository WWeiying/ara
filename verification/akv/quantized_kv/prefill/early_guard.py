"""Fail fast on unexpected architectural exceptions in this no-fault benchmark."""
import os
import re
import signal
import threading


def failure(line):
    if '[ARA_CONTRACT_TRACE]' not in line:
        return None
    if re.search(r'\bresp=1/1 fire=1\b.*\bexc=1\b', line):
        return 'unexpected_architectural_exception'
    match=re.search(r'\berrors=([0-9a-fA-F]+)\b',line)
    if match and int(match[1],16):
        return 'contract_monitor_error'
    return None


class EarlyGuard:
    def __init__(self,owner,log,save):
        self.owner,self.log,self.save=owner,log,save
        self.stop=threading.Event()
        self.thread=threading.Thread(target=self.watch,daemon=True)
    def __enter__(self):
        self.thread.start()
        return self
    def __exit__(self,*_):
        self.stop.set();self.thread.join()
    def watch(self):
        offset=0;pending=''
        while not self.stop.wait(0.5):
            if not self.log.exists(): continue
            with self.log.open(errors='replace') as stream:
                stream.seek(offset);pending+=stream.read();offset=stream.tell()
            lines=pending.split('\n');pending=lines.pop()
            for line in lines:
                reason=failure(line)
                if reason:
                    self.save(self.owner.out/'early-failure.json',dict(reason=reason,line=line))
                    pid=self.owner.state.get('child_pid')
                    if pid and self.owner.state.get('state')=='RUNNING':
                        try: os.kill(pid,signal.SIGTERM)
                        except ProcessLookupError: pass
                    return
