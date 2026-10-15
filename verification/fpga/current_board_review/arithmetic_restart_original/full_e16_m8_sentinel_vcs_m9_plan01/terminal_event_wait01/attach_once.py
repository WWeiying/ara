"""Attach one inotify observer, independent of the DUT service control group."""
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;WORKER=HERE.parent;OUT=WORKER/'prepared01'
HELPER=WORKER.parents[1]/'wait_terminal.py'
UNIT='ara-e16-m8-sentinel-terminal-event01.service'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    with p.open('x') as f:
        json.dump(v,f,indent=2);f.flush();os.fsync(f.fileno())
def main():
    assert sha(OUT/'plan.json')=='0a2820506439278384569a58f72b76fcb72ae5276f4f302ba6a31f0c65a6335e'
    assert json.loads((OUT/'startup_observation.json').read_text())['exitcollector_attached']
    assert HELPER.is_file()
    command=['systemd-run','--user','--unit='+UNIT,'--property=RuntimeMaxSec=13900',
        '--property=KillMode=control-group','--property=Restart=no',
        '--property=WorkingDirectory='+str(HERE),'--property=StandardOutput=append:'+str(HERE/'waiter.log'),
        '--property=StandardError=append:'+str(HERE/'waiter.log'),
        '--property=ExecStopPost='+sys.executable+' -B '+str(HERE/'exit_receipt.py'),
        sys.executable,'-B',str(HELPER),str(OUT/'collector_exit.json'),'--timeout','13800']
    save(HERE/'request.json',dict(command=command,unit=UNIT,plan_sha256=sha(OUT/'plan.json'),
        event_target=str(OUT/'collector_exit.json'),helper_sha256=sha(HELPER),helper=str(HELPER),
        startup_observation_sha256=sha(OUT/'startup_observation.json'),
        pins={str(p):sha(p) for p in (Path(__file__).resolve(),HERE/'exit_receipt.py',HELPER)},
        observer_timeout_s=13800,simulation_budget_extended=False,
        role='INOTIFY_EVENT_ONLY_NOT_DUT_ACCEPTANCE',active_CSV_reads=0,no_auto_retry=True,no_auto_audit=True))
    runtime=Path('/run/user')/str(os.getuid())
    env=dict(os.environ,XDG_RUNTIME_DIR=str(runtime),DBUS_SESSION_BUS_ADDRESS='unix:path='+str(runtime/'bus'))
    start=time.monotonic();timed=False
    with (HERE/'submission.log').open('x') as log:
        child=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT)
        try:rc=child.wait(timeout=30)
        except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
        save(HERE/'submission.json',dict(actual_wait_returncode=rc,pid=child.pid,
            elapsed_s=time.monotonic()-start,timed_out=timed,retries=0))
    assert rc==0 and not timed,'Observer submission failed; no retry'
    q=subprocess.run(['systemctl','--user','show',UNIT,
        '--property=Id,ActiveState,SubState,MainPID,ExecStart,ExecStopPost,ControlGroup,RuntimeMaxUSec'],
        env=env,text=True,capture_output=True,timeout=10)
    props=dict(line.split('=',1) for line in q.stdout.splitlines() if '=' in line)
    assert q.returncode==0 and props.get('ActiveState')=='active' and int(props.get('MainPID','0'))>0
    save(HERE/'attached.json',dict(status='INOTIFY_ATTACHED_NO_DUT_POLLING',actual_query_returncode=q.returncode,
        properties=props,event_target=str(OUT/'collector_exit.json'),target_is_metadata=True,
        no_raw_or_reference_reads=True,no_auto_acceptance=True,simulation_budget_extended=False))
    print('EVENT_WAITER_ATTACHED',props['MainPID'],UNIT,flush=True)
if __name__=='__main__':main()
