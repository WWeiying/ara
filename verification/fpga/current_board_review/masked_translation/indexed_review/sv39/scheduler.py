"""Fixed-group fail-fast scheduling; no new work is dispatched after first failure."""
from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED
import os
from pathlib import Path
import signal
import threading


def identity(pid):
    try:
        fields=(Path('/proc')/str(pid)/'stat').read_text().rsplit(') ',1)[1].split()
        return int(fields[1]),int(fields[2]),fields[19]
    except (FileNotFoundError,ProcessLookupError): return None


def cancel_process(process):
    if process.poll() is not None: return
    identities={}
    for path in Path('/proc').iterdir():
        if path.name.isdigit():
            ident=identity(int(path.name))
            if ident: identities[int(path.name)]=ident
    owned={process.pid}
    while True:
        added={pid for pid,(ppid,_,_) in identities.items() if ppid in owned}-owned
        if not added: break
        owned.update(added)
    process.terminate()
    def enforce():
        for pid in sorted(owned,reverse=True):
            old=identities.get(pid); now=identity(pid)
            if old is None or now is None or now[2]!=old[2]: continue
            try:
                if old[1]==pid: os.killpg(pid,signal.SIGKILL)
                else: os.kill(pid,signal.SIGKILL)
            except ProcessLookupError: pass
    timer=threading.Timer(10,enforce); timer.daemon=True; timer.start()


class Abort:
    def __init__(self):
        self.lock=threading.RLock(); self.reason=None; self.active={}

    def launch(self,key,factory):
        with self.lock:
            if self.reason is not None: raise ValueError('Queue cancelled before launch')
            process=factory(); self.active[key]=process
            return process

    def remove(self,key):
        with self.lock: self.active.pop(key,None)

    def stop(self,reason):
        with self.lock:
            if self.reason is None: self.reason=reason
            for process in list(self.active.values()): cancel_process(process)


def run_groups(groups,jobs,run_one,abort):
    if not 1<=jobs<=4: raise ValueError('NF7 jobs must be 1..4')
    pending=list(groups); results={}
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        running={}
        def dispatch():
            with abort.lock:
                while pending and len(running)<jobs and abort.reason is None:
                    group=pending.pop(0)
                    running[pool.submit(run_one,group,abort)]=group
        dispatch()
        while running:
            completed,_=wait(running,return_when=FIRST_COMPLETED)
            # Process the whole completed batch before admitting any more work.
            for future in completed:
                group=running.pop(future)
                try: result=future.result()
                except Exception as error: result=dict(status='FAIL',error=str(error))
                results[group]=result
                if result.get('status')!='PASS': abort.stop(dict(group=group,result=result))
            dispatch()
    for group in pending: results[group]=dict(status='CANCELLED_NOT_LAUNCHED')
    return results
