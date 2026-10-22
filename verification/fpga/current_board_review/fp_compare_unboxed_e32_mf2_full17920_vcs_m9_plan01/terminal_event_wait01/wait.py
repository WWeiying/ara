"""One bounded inotify wait; terminal metadata only, never CSV/raw or live progress."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import select
import struct
import time

HERE=Path(__file__).resolve().parent
OUT=HERE.parent/'prepared02'
PLAN='e230c67ff420185006d31b479f861406a6be1f4047201a605508cd1c190cc3fe'
EVENT='terminal_event.json'

def save(name,value):
    with (HERE/name).open('x') as f:
        json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
def read(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def require(ok,why):
    if not ok:raise ValueError(why)

def main():
    start=time.monotonic();fd=-1;answer=dict(status='NOT_ACCEPTED',DUT_rerun=False,CSV_raw_reads=0)
    try:
        require(sha(OUT/'plan.json')==PLAN,'Exact launched plan')
        libc=ctypes.CDLL(None,use_errno=True)
        libc.inotify_init1.argtypes=[ctypes.c_int];libc.inotify_init1.restype=ctypes.c_int
        libc.inotify_add_watch.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_uint32]
        libc.inotify_add_watch.restype=ctypes.c_int
        fd=libc.inotify_init1(os.O_CLOEXEC|os.O_NONBLOCK)
        require(fd>=0,'inotify_init1 failed')
        wd=libc.inotify_add_watch(fd,os.fsencode(OUT),0x8|0x80)
        require(wd>=0,'inotify_add_watch failed')
        save('armed.json',dict(status='WAITING_FOR_TERMINAL_EVENT',pid=os.getpid(),plan_sha256=PLAN,
            event=str(OUT/EVENT),watch_installed_before_initial_exists_check=True,
            deadline_s=13800,started=time.time(),progress_polling=False))
        found=(OUT/EVENT).exists()
        deadline=start+13800
        while not found:
            remaining=deadline-time.monotonic()
            require(remaining>0,'Bounded event wait expired; no acceptance or retry')
            ready,_,_=select.select([fd],[],[],remaining)
            require(bool(ready),'Bounded event wait expired; no terminal event')
            data=os.read(fd,65536);offset=0
            while offset<len(data):
                _,mask,_,length=struct.unpack_from('iIII',data,offset)
                name=data[offset+16:offset+16+length].split(b'\0',1)[0].decode()
                offset+=16+length
                require(not(mask&0x4000),'inotify queue overflow; fail closed')
                if name==EVENT and mask&(0x8|0x80):found=True
        event=read(OUT/EVENT);wait=read(OUT/'collector.wait.json')
        service=read(OUT/'service_exit.json')
        report_path=OUT/'collector_result.json'
        report=read(report_path) if report_path.is_file() else None
        child_path=OUT/'replay/tests/fp_compare_unboxed_e32_mf2_full17920/child_outcome.unvalidated.json'
        child=read(child_path) if child_path.is_file() else None
        answer.update(plan_sha256=PLAN,terminal_event=event,actual_service_exit=service,
            actual_collector_wait=wait,actual_child_outcome=child,
            collector_status=report.get('status') if report else None,
            scope=report.get('scope') if report else None,owner_contract=report.get('owner_contract') if report else None)
        require(event['collector_wait_sha256']==sha(OUT/'collector.wait.json'),'Collector wait identity')
        require(event['collector_result_sha256']==sha(report_path),'Collector result identity')
        require(event['status']=='TERMINAL_COLLECTOR_ACCEPTED' and event['timed_out'] is False,
                'Producer stop hook did not accept collector')
        require(type(wait['actual_wait_exit'])is int and wait['actual_wait_exit']==0 and wait['timed_out'] is False,
                'Actual numeric collector wait0 required')
        require(service['kind']=='ACTUAL_SYSTEMD_EXEC_STOP_POST' and service['SERVICE_RESULT']=='success' and
                service['EXIT_CODE']=='exited' and service['EXIT_STATUS']=='0','Actual main service exit0 required')
        require(report['status']=='PASS_FULL17920_FP32_M9_METADATA_COLLECTED_NOT_LINUX' and
                report['plan_sha256']==PLAN and report['pins_unchanged'] is True,'Exact full collector acceptance')
        require(child is not None and type(child['returncode'])is int and child['returncode']==0 and
                child['timed_out'] is False and child['failure_seen'] is False,'Actual simulator numeric0')
        require(report['actual_simulator_wait']==child and report['service_exit']==service,'Matching actual outcomes')
        require(sha(OUT/'plan.json')==PLAN,'Terminal plan unchanged')
        answer.update(status='TERMINAL_COLLECTOR_ACCEPTED_METADATA_ONLY',collector_result_sha256=sha(report_path),
                      collector_wait_sha256=sha(OUT/'collector.wait.json'),service_exit_sha256=sha(OUT/'service_exit.json'),
                      independent_CSV_parse=False,original_Linux_closed=False)
    except BaseException as error:
        answer['error']=repr(error)
    finally:
        if fd>=0:os.close(fd)
    answer.update(finished=time.time(),elapsed_s=time.monotonic()-start)
    save('notification.json',answer)
    print(json.dumps(answer),flush=True)
    return int(answer['status']!='TERMINAL_COLLECTOR_ACCEPTED_METADATA_ONLY')

if __name__=='__main__':raise SystemExit(main())
