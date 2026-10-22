"""Narrow fresh service successor; the admitted worker/checker are unchanged."""
import shlex
from scope import *
import replay as original

OLD_PLAN_SHA='54f4fbbac1603f1742cbb6d6ad090aee20a9609f9d2efed2dc1c29dd85b0bbdd'
WORKER_SHA='88d7d1472f9475f6a678b7e2e3c114816cc49cb72acf255cb20a0a9adf95f4ac'

def contract():
    return dict(RemainAfterExit=False,Type='exec',stop_timeout_s=300,
        exit_hook=str(HERE/'exit_hook02.py'),exit_hook_sha256=sha(HERE/'exit_hook02.py'),
        collector=str(HERE/'collect02.py'),collector_sha256=sha(HERE/'collect02.py'),
        collector_bound_s=180,auto_after_main_exit=True,original_worker_sha256=WORKER_SHA)

def main():
    require(sha(HERE/'prepared01/plan.json')==OLD_PLAN_SHA and sha(HERE/'replay.py')==WORKER_SHA,
            'Preserved original plan/worker')
    out=HERE/'prepared02';base_save=original.durable
    def save(path,data):
        if path==out/'plan.json': data=dict(data,service_terminal_contract=contract())
        if path==out/'ready.json':
            data=dict(data);argv=list(data['service_argv'])
            old='--property=RemainAfterExit=yes'
            require(argv.count(old)==1,'Exact one old RemainAfterExit property')
            argv[argv.index(old)]='--property=RemainAfterExit=no'
            old_hook='--property=ExecStopPost='+shlex.join([sys.executable,'-B',str(HERE/'exit_hook.py'),'--out',str(out)])
            require(argv.count(old_hook)==1,'Exact previous exit hook')
            index=argv.index(old_hook)
            argv[index]='--property=ExecStopPost='+shlex.join([sys.executable,'-B',str(HERE/'exit_hook02.py'),'--out',str(out)])
            argv.insert(index,'--property=TimeoutStopSec=300')
            data.update(service_argv=argv,service_command=shlex.join(argv),service_terminal_contract=contract(),
                        predecessor_blocked_plan_sha256=OLD_PLAN_SHA)
        base_save(path,data)
    original.durable=save
    try: original.prepare(out)
    finally: original.durable=base_save
    original.dryrun(out,sha(out/'plan.json'))

if __name__=='__main__':main()
