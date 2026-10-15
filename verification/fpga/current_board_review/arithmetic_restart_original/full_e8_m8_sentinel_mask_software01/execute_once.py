"""One short-host/dual-compile sequence and bounded linked CFG; no ELF execution."""
import json,subprocess,sys,time,hashlib
from pathlib import Path
HERE=Path(__file__).resolve().parent
def save(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2);f.write('\n')
def run(name,command,seconds):
    save(HERE/(name+'_command.json'),dict(command=command,timeout_s=seconds,code_sha256=hashlib.sha256(Path(command[2]).read_bytes()).hexdigest()))
    start=time.monotonic();timed=False
    with (HERE/(name+'.log')).open('x') as f:
        child=subprocess.Popen(command,cwd=HERE,stdout=f,stderr=subprocess.STDOUT)
        try:rc=child.wait(timeout=seconds)
        except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
        save(HERE/(name+'_execution.json'),dict(returncode=rc,pid=child.pid,elapsed_s=time.monotonic()-start,timed_out=timed,retries=0))
    if rc or timed:raise SystemExit(rc if not timed else 124)
if len(sys.argv)!=2:raise SystemExit('Exact independent source review hash required')
run('preparation',[sys.executable,'-B',str(HERE/'prepare_once.py'),sys.argv[1]],300)
run('cfg',[sys.executable,'-B',str(HERE/'linked_cfg_cost.py')],600)
