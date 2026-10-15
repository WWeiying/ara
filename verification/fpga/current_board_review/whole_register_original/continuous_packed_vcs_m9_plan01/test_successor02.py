"""Narrow JSON-roundtrip correction; no repeated oracle/Host matrix."""
import ast
import subprocess
import sys
import time
import checker as c
import replay02 as r

def definitions(path):
    return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(path.read_text()).body
            if isinstance(n,(ast.FunctionDef,ast.ClassDef))}

def main():
    names=('TerminalAbort','write_json','failed','publish','monitored_with_outcome','checked_runner','service_identity','owner_gate')
    a,b=definitions(c.HERE/'replay.py'),definitions(c.HERE/'replay02.py')
    c.require(all(a[n]==b[n] for n in names),'Reviewed lifecycle functions changed')
    for n in ('host02.json','host_worker02.json'):
        report=c.read(c.HERE/n);c.require(report['status']=='PASS_HOST_ONLY','Prior actual Host')
        c.common.base.verify_pins(report['pins'])
    receipts=[]
    for wrong in (False,True):
        code="import json; import replay02 as r; p=r.read(r.HERE/'prepared01/plan.json'); p['pins'][str(r.HERE/'replay02.py')]=r.sha(r.HERE/'replay02.py'); "
        if wrong:code+="p['specs']['whole_all']['targets']['0']+=4; "
        code+="r.validate(p,r.IMAGE); print('JSON_ROUNDTRIP_ACCEPTED')"
        command=[sys.executable,'-B','-c',code];began=time.monotonic()
        p=subprocess.Popen(command,cwd=c.HERE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        out,err=p.communicate(timeout=60)
        receipts.append(dict(command=command,pid=p.pid,returncode=p.returncode,elapsed_s=time.monotonic()-began,stdout=out,stderr=err,wrong_spec=wrong))
        c.require(p.returncode==(1 if wrong else 0),'Actual JSON schema gate outcome')
        if wrong:c.require('Actual ELF specs drift' in err,'Negative rejected for wrong reason')
    pins={str(c.HERE/n):c.sha(c.HERE/n) for n in ('replay02.py','collect02.py','exit_hook02.py','launch_once02.py','test_successor02.py','host02.json','host_worker02.json')}
    c.save(c.HERE/'host_successor02.json',dict(status='PASS_HOST_ONLY',tests=3,failures=0,pins=pins,
           actual_children=receipts,lifecycle_definitions_bytecode_ast_identical=list(names),full_host_reruns=0))
    print('SUCCESSOR_SCHEMA_HOST_PASS',flush=True)

if __name__=='__main__':main()
