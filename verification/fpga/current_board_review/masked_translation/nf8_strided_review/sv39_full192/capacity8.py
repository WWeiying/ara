"""One-shot reserved-capacity admission. Never changes external processes."""
from pathlib import Path
import os
import re
import time
from support import ref
require=ref.base.require
NF7_UNIT='ara-indexed-nf7-candidate02-06.service'

RESERVES=dict(nf7=2,parent38=4,gather=4,whole=6)

def accounting(processes,reserved_units,available):
    require(set(reserved_units)=={'parent38','gather','whole'},'All parent reservation units required')
    units=dict(nf7=NF7_UNIT,**reserved_units)
    require(len(set(units.values()))==4 and all(re.fullmatch(r'ara-[A-Za-z0-9_-]+[.]service',u) for u in units.values()),
            'Exact distinct reservation units required')
    require(available>=32*1024**3,'MemAvailable below32GiB; refuse without waiting')
    buckets={name:[] for name in units}; other=[]
    for p in processes:
        parts=[x for line in p['cgroup'].splitlines() for x in line.split('/') if x]
        matched=[name for name,unit in units.items() if unit in parts]
        require(len(matched)<=1,'Ambiguous nested reservation ownership')
        if matched: buckets[matched[0]].append(p)
        else: other.append(p)
    total=len(other)+sum(max(len(buckets[n]),r) for n,r in RESERVES.items())+8
    require(total<=24,'Other + reserved NF7/38/gather/whole + own8 exceeds24')
    return dict(other=other,owners=buckets,reserves=RESERVES,units=units,own_reserved=8,
                total_live_plus_reserved=total,cap=24,mem_available_bytes=available)

def snapshot_process(proc):
    comm=(proc/'comm').read_text().strip()
    argv=(proc/'cmdline').read_bytes().split(bytes([0]))
    potential=comm=='simv' or bool(argv[0]) and Path(os.fsdecode(argv[0])).name=='simv'
    if not potential: return None
    cgroup=(proc/'cgroup').read_text()
    exe=(proc/'exe').resolve(strict=True); cwd=(proc/'cwd').resolve(strict=True)
    require(exe.name=='simv','Suspicious simv identity mismatch')
    return dict(pid=int(proc.name),comm=comm,exe=str(exe),cwd=str(cwd),
                argv=[os.fsdecode(x) for x in argv if x],cgroup=cgroup)

def actual(reserved_units):
    memory=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
    available=int(memory['MemAvailable'].split()[0])*1024
    processes=[]
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit(): continue
        try:
            entry=snapshot_process(proc)
            if entry is not None: processes.append(entry)
        except (FileNotFoundError,ProcessLookupError): continue
        # Permission failures remain fatal for potentially relevant processes.
    result=accounting(processes,reserved_units,available)
    result.update(observed_unix=time.time(),one_shot=True)
    return result
