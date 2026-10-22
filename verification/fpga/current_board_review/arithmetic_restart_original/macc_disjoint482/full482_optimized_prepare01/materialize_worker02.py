"""Finite terminal-only successor; keep the reviewed first worker/plan immutable."""
import difflib
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
OLD=HERE/'vcs_m8_plan01';NEW=HERE/'vcs_m8_plan02'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def replace(text,before,after):
    assert text.count(before)==1,before
    return text.replace(before,after)


def main():
    assert sha(OLD/'replay.py')=='806ffd79323272be404fbbb58b2b438d89ef16ced78ddf71c8efd77a859da47b'
    assert sha(OLD/'prepared01/plan.json')=='2e4be5e555d14eac74877535733783ad0970eefdd376328678d3e5a837236897'
    source=(OLD/'replay.py').read_text();target=source
    target=replace(target,'import checker as c\n','import checker as c\nimport terminal_publish\n')
    target=replace(target,"host=read(HERE/'host02.json')","host=read(HERE/'host03.json')")
    target=replace(target,"    ledger,repo,_,pins=image_gate();ready,bound=source_gate();pins.update(bound)",
        "    proof=read(HERE/'successor_proof.json')\n"
        "    require(proof['old_plan_sha256']=='2e4be5e555d14eac74877535733783ad0970eefdd376328678d3e5a837236897', 'Exact preserved blocked plan')\n"
        "    common.base.verify_pins(proof['old_input_pins'])\n"
        "    ledger,repo,_,pins=image_gate();ready,bound=source_gate();pins.update(bound)\n"
        "    pins.update(proof['old_input_pins']);pins[str(HERE/'successor_proof.json')]=sha(HERE/'successor_proof.json')")
    for a,b in (("HERE/'host02.json'","HERE/'host03.json'"),
            ("HERE/'host_final02/execution.json'","HERE/'host_terminal03/execution.json'"),
            ("HERE/'host_final02/stdout.log'","HERE/'host_terminal03/stdout.log'"),
            ("HERE/'host_final02/stderr.log'","HERE/'host_terminal03/stderr.log'")):
        target=replace(target,a,b)
    target=replace(target,'cases=plan[\'cases\'];abort,done=threading.Event(),threading.Event()',
        "cases=plan['cases'];abort,done=terminal_publish.TerminalAbort(),threading.Event()")
    target=replace(target,'deadline=threading.Timer(WORKER,abort.set);deadline.daemon=True',
        'expires=time.monotonic()+WORKER\n    deadline=threading.Timer(WORKER,abort.set);deadline.daemon=True')
    target=replace(target,"            deadline.cancel();done.set();thread.join(timeout=2)\n"
        "            if abort.is_set() and terminal['status']==PASS:terminal['status']='NOT_ACCEPTED_LATE_ABORT'\n"
        "            terminal['finished']=time.time();save(out/'complete.json',terminal)",
        "            deadline.cancel();deadline.join();done.set();thread.join(timeout=2)\n"
        "            if thread.is_alive():abort.set()\n"
        "            terminal['finished']=time.time()\n"
        "            terminal_publish.publish(out,terminal,abort,expires)")
    import ast
    ast.parse(target)
    NEW.mkdir(exist_ok=False)
    for name in ('checker.py','reset_profile.json'):
        (NEW/name).write_bytes((OLD/name).read_bytes())
    (NEW/'replay.py').write_text(target)
    (NEW/'worker_delta.diff').write_text(''.join(difflib.unified_diff(source.splitlines(True),target.splitlines(True),
        fromfile=str(OLD/'replay.py'),tofile=str(NEW/'replay.py'))))
    oldpins=dict(json.loads((OLD/'prepared01/plan.json').read_text())['pins'])
    for path in (OLD/'prepared01/plan.json',OLD/'prepared01/ready.json',OLD/'prepared01/dryrun_gate.json',
            OLD/'host02.json',OLD/'host_final02/execution.json',OLD/'host_final02/stdout.log',OLD/'host_final02/stderr.log'):
        oldpins[str(path)]=sha(path)
    proof=dict(status='TERMINAL_ONLY_SUCCESSOR_NOT_DUT',old_plan_sha256=sha(OLD/'prepared01/plan.json'),
        old_input_pins=oldpins,old_checker_sha256=sha(OLD/'checker.py'),new_checker_sha256=sha(NEW/'checker.py'),
        old_host_tests=21,old_host_actual_child_returncode=0,
        materializer_sha256=sha(Path(__file__)),delta_sha256=sha(NEW/'worker_delta.diff'))
    assert proof['old_checker_sha256']==proof['new_checker_sha256']
    (NEW/'successor_proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    print('MATERIALIZED_TERMINAL_ONLY_SUCCESSOR',NEW)


if __name__=='__main__':main()
