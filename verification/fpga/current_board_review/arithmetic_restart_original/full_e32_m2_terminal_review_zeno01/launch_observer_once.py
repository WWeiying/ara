"""Submit one independent observer service; never touches DUT services."""
import json,os,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
UNIT='ara-e32m2-e64m2-terminal-observer-zeno01.service'
def save(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2);f.write('\n')
runtime=Path('/run/user')/str(os.getuid())
if not (runtime/'bus').is_socket():raise ValueError('Actual user bus unavailable')
env=dict(os.environ,XDG_RUNTIME_DIR=str(runtime),DBUS_SESSION_BUS_ADDRESS='unix:path='+str(runtime/'bus'))
command=['systemd-run','--user','--unit='+UNIT,'--property=RuntimeMaxSec=13200',
    '--property=KillMode=control-group','--property=Restart=no','--property=WorkingDirectory='+str(HERE),
    '--property=StandardOutput=append:'+str(HERE/'observer_service.log'),
    '--property=StandardError=append:'+str(HERE/'observer_service.log'),
    sys.executable,'-B',str(HERE/'observe_terminals.py')]
save(HERE/'observer_launch_command.json',dict(command=command,observer_only=True,no_simulation_budget_extension=True,no_retry=True))
start=time.monotonic()
with (HERE/'observer_submission.log').open('x') as stream:
    child=subprocess.Popen(command,env=env,stdout=stream,stderr=subprocess.STDOUT)
    rc=child.wait(timeout=30)
    save(HERE/'observer_submission_exit.json',dict(actual_wait_returncode=rc,pid=child.pid,elapsed_s=time.monotonic()-start))
if rc!=0:raise SystemExit(rc)
query=subprocess.run(['systemctl','--user','show',UNIT,'--property=Id,ActiveState,SubState,MainPID,ControlGroup,ExecStart,RuntimeMaxUSec,Restart'],
    env=env,text=True,capture_output=True,timeout=10)
save(HERE/'observer_service_confirmation.json',dict(actual_query_returncode=query.returncode,
    properties=dict(line.split('=',1) for line in query.stdout.splitlines() if '=' in line),
    stderr=query.stderr,CPU_queries=0,CSV_reads=0,only_observer_service=True))
print(query.stdout)
raise SystemExit(query.returncode)

