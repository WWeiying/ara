import copy
import json
from pathlib import Path
import tempfile
import vcs
import dut_check as d

tests=[]
def rejects(name,fn):
    try:fn()
    except (ValueError,FileExistsError):tests.append(name);return
    raise AssertionError('Accepted negative '+name)

receipt=dict(returncode=0,elapsed_s=1,timed_out=False,failure_seen=False,abort_set=False)
vcs.receipt_ok(receipt,900)
for key,value in [('returncode',False),('returncode',None),('returncode',1),('elapsed_s',901),
                  ('elapsed_s',float('nan')),('timed_out',True),('failure_seen',True),('abort_set',True)]:
    bad=dict(receipt);bad[key]=value
    rejects(key+repr(value),lambda: vcs.receipt_ok(bad,900))
spec=json.loads((vcs.HERE/'reference_load_m01/soc.spec.json').read_text())
c=d.Checker(spec,False,False)
row={k:'0' for k in d.c.FIELDS};row.update(event='retire',order='1',pc=f'{spec["symbols"]["_start"]:x}')
rejects('retiregap',lambda:c.row(row))
row.update(event='cvx_resp',order='0')
rejects('unowned_CVX',lambda:d.Checker(spec,False,False).row(row))
row.update(event='uop_done',insn=f'{c.target:x}')
rejects('unowned_target_done',lambda:d.Checker(spec,False,False).row(row))
rejects('incomplete_lifecycle',lambda:d.Checker(spec,False,False).finish())
with tempfile.TemporaryDirectory() as tmp:
    p=Path(tmp)/'terminal.json';vcs.save(p,dict(status='ERROR'))
    rejects('exclusive_terminal',lambda:vcs.save(p,dict(status='PASS')))
    assert json.loads(p.read_text())==dict(status='ERROR')
vcs.save(vcs.HERE/'host_worker01.json',dict(passed=True,negative_rejections=tests,
       worker_sha256=vcs.sha(Path(vcs.__file__)),checker_sha256=vcs.sha(Path(d.__file__)),test_sha256=vcs.sha(Path(__file__))))
print(json.dumps(tests))
