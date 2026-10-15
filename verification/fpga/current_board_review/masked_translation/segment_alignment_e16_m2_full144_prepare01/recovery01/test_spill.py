import copy
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
import model as m
from prepare import code
from spill_guard import StoreGuard

def main():
    s=json.loads((HERE.parent/'software01/spike.symbols.json').read_text())
    c=code((HERE.parent/'software01/spike.dis').read_text())
    actual=dict(value=0,regs={0:0,2:0x800fff30},
                desc=dict(kind='write',size=8,base=2,register=8,offset=176),
                pc=0x8000044e,mode=3,current=-1,address=0x800fffe0,symbols=s,code=c)
    guard=StoreGuard();guard.check(**copy.deepcopy(actual))
    m.require(len(guard.evidence)==1,'Actual unknown initial s0 full-width spill')
    changes=[dict(pc=0x80000450),dict(mode=1),dict(current=0),dict(address=0x800fffe8),
             dict(value=None),dict(value=1<<64),dict(regs={0:0,2:0x800fff30,8:1})]
    for key,val in [('size',4),('base',3),('register',10),('offset',168),('kind','read')]:
        d=actual['desc'].copy();d[key]=val;changes.append(dict(desc=d))
    for change in changes:
        args=copy.deepcopy(actual);args.update(change)
        try:StoreGuard().check(**args)
        except ValueError:pass
        else:raise ValueError('Negative accepted '+str(change))
    print(json.dumps(dict(status='HOST_SPILL_GUARD_PASS',actual_positive=1,negatives=len(changes))))

if __name__=='__main__':main()
