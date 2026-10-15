#!/usr/bin/env python3
"""Run small observer Host, freeze inputs and print a future command. No attach."""
import ast
import json
import shlex
import subprocess
import sys
import time
from pathlib import Path
import terminal as t

HERE = Path(__file__).resolve().parent
OLD = HERE.parent/'full_e32_mf2_terminal_audit01/terminal.py'


def main():
    t.need(not (HERE/'pins.json').exists() and not (HERE/'host01.json').exists(), 'Fresh preparation only')
    for path,digest in ((t.RUN/'plan.json',t.PLAN_SHA),(t.RUN/'launch.json',t.LAUNCH_SHA),
                        (t.ENTRY,t.ENTRY_SHA),(t.WORK/'parent_review.json',t.PARENT_SHA),
                        (OLD,'7851a871f98589bf2bffd3fdb6388c14feb227c5473a8388c6ff92b5a7a5233e'),
                        (t.GENERIC,'b5751d25426ba78893c52359519d3b6f1df6bc9c77eb341c91cdca1ff75b506a')):
        t.need(t.sha(path) == digest, 'Reviewed input identity: '+str(path))
    def function(path,name):
        return ast.dump(next(n for n in ast.parse(path.read_text()).body
                            if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name == name))
    for name in ('one_pass','HashLines','outcome_gate','wait_fd','publish_success'):
        t.need(function(OLD,name) == function(HERE/'terminal.py',name), 'Mature adapter drift: '+name)
    command = [sys.executable,'-B',str(HERE/'test_gates.py')]
    t.save(HERE/'host_command.json',dict(command=command,timeout_s=60))
    started = time.monotonic()
    timed = False
    with (HERE/'host01.log').open('x') as log:
        child = subprocess.Popen(command,cwd=HERE,stdout=log,stderr=subprocess.STDOUT)
        try:
            rc = child.wait(timeout=60)
        except subprocess.TimeoutExpired:
            timed = True
            child.kill()
            rc = child.wait()
    t.save(HERE/'host_process_exit.json',dict(returncode=rc,timed_out=timed,
           elapsed_s=time.monotonic()-started,pid=child.pid,attempt=1))
    t.need(rc == 0 and not timed,'Observer Host failed; no retry')
    host = t.read(HERE/'host01.json')
    t.need(host['status'] == 'PASS_NEW_GATES_ONLY' and host['tests'] == 8 and host['failures'] == 0,
           'Incomplete observer Host')
    t.verify(host['pins'])
    pins = dict(t.read(t.RUN/'plan.json')['pins'])
    pins.update(t.read(t.ENTRY)['evidence_pins'])
    paths = [HERE/n for n in ('terminal.py','test_gates.py','prepare.py','host_command.json',
                              'host01.json','host01.log','host_process_exit.json')]
    paths += [OLD,t.GENERIC,t.RUN/'plan.json',t.RUN/'launch.json',t.ENTRY,t.WORK/'parent_review.json']
    for path in paths:
        value = t.sha(path)
        t.need(str(path) not in pins or pins[str(path)] == value,'Conflicting pin: '+str(path))
        pins[str(path)] = value
    t.save(HERE/'pins.json',pins)
    digest = t.sha(HERE/'pins.json')
    command = [sys.executable,'-B',str(HERE/'terminal.py'),'--authorize-event-worker','--pins-sha256',digest]
    service = ['systemd-run','--user','--unit=ara-arithmetic-e16-mf4-terminal-audit01.service',
               '--property=RuntimeMaxSec=15600','--property=KillMode=control-group','--property=Restart=no',
               '--property=WorkingDirectory='+str(HERE),
               '--property=StandardOutput=append:'+str(HERE/'service.log'),
               '--property=StandardError=append:'+str(HERE/'service.log'),*command]
    t.save(HERE/'READY.json',dict(status='FROZEN_CONDITIONAL_WAITER_NOT_STARTED',
           pins_sha256=digest,pin_count=len(pins),command=command,service_command=shlex.join(service),
           worker_pid=t.PID,worker_unit=t.UNIT,worker_plan_sha256=t.PLAN_SHA,
           worker_parent_sha256=t.PARENT_SHA,worker_entry_sha256=t.ENTRY_SHA,
           wait_seconds=t.WAIT_SECONDS,audit_child_seconds=t.AUDIT_SECONDS,observer_service_seconds=15600,
           observer_bound_does_not_extend_DUT=True,
           condition='Worker exited; whole1 COMPLETE/PASS/noabort/retry0; numeric simulator exit0; empty cgroup',
           future_full_CSV_parses=1,preparation_active_CSV_reads=0,waiter_started=False,
           DUT_reference_build_runs=0,full_source_Host_runs=0,host_tests=8,host_actual_exit=rc,
           required_calls=4095,required_results=65520,required_guards=8190,
           required_vstarts=4095,required_helper_instructions=53235,
           service_exit_status='Historical worker service exit not inferred from PIDFD'))
    print('FROZEN_NOT_STARTED READY_SHA='+t.sha(HERE/'READY.json')+' PINS_SHA='+digest,flush=True)


if __name__ == '__main__':
    main()
