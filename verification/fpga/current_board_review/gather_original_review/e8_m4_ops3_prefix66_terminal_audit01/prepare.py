"""Freeze a conditional offline audit plan; no terminal/active case CSV is inspected."""
import ast
import shlex
import sys

sys.dont_write_bytecode=True
from support import *
from wait_terminal import worker_identity


def main():
    require(not (HERE/'prepared.json').exists(),'Fresh preparation only')
    plan=static_gate()
    for name in ('support.py','audit.py','wait_terminal.py','prepare.py'):
        ast.parse((HERE/name).read_text(),filename=name)
    code_pins={str(HERE/name):sha(HERE/name) for name in
               ('support.py','audit.py','wait_terminal.py','prepare.py','PLAN.md')}
    code_pins[str(TRANSPORT)]=TRANSPORT_SHA
    for name in ('replay.py','checker.py','newscope.py'):
        path=W/name;code_pins[str(path)]=plan['pins'][str(path)]
    code_pins[str(P/'plan.json')]=PLAN_SHA
    code_pins[str(P/'launch.json')]=sha(P/'launch.json')
    code_pins[str(W/'parent_review.json')]=AUTH_SHA
    save(HERE/'prepared.json',dict(status='PREPARED_CONDITIONAL_TERMINAL_AUDIT_NOT_STARTED',
        source_plan_sha256=PLAN_SHA,parent_review_sha256=AUTH_SHA,code_pins=code_pins,
        worker_pid=WORKER_PID,worker_identity=worker_identity(),reported_simv_pid=1586551,
        wait_seconds=6600,audit_seconds=900,event_service_outer_seconds=7800,
        csv_parses_authorized=1,audit_attempts=1,retries=0,first_failure_stop=True,
        outputs=dict(wait=str(HERE/'wait01'),terminal=str(HERE/'terminal01')),
        terminal_reads=0,active_CSV_reads=0,live_case_logs_read=0,Host_or_DUT_or_reference_runs=0,
        preparation_validation='AST syntax, exact static pins/source/metadata; existing Host55 reused, not rerun'))
    digest=sha(HERE/'prepared.json')
    command=['systemd-run','--user','--unit=ara-gather-e8m4-vi31-prefix66-m6-audit01.service',
        '--property=RuntimeMaxSec=7800','--property=KillMode=control-group','--property=Restart=no',
        '--property=WorkingDirectory='+str(HERE),
        '--property=StandardOutput=append:'+str(HERE/'event_service.log'),
        '--property=StandardError=append:'+str(HERE/'event_service.log'),
        '/usr/bin/python3','-B',str(HERE/'wait_terminal.py'),'--authorize-event-wait','--prepared-sha256',digest]
    save(HERE/'event_command.json',dict(status='PROPOSED_WAIT_FOR_MAIN_REVIEW_NOT_STARTED',
        prepared_sha256=digest,command=command,service_command=shlex.join(command),
        worker_unit_unchanged=UNIT,new_DUT_or_reference_runs=False))
    print('PREPARED_CONDITIONAL_TERMINAL_AUDIT_NOT_STARTED',digest,flush=True)


if __name__=='__main__':main()
