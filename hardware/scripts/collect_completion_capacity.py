#!/usr/bin/env python3
"""Check complete functional results and read-only RCE/ordered demand traces."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from run_reduction_audit import classify


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    args=parser.parse_args()
    root=args.directory.resolve()
    source=json.loads((root/'source_manifest.json').read_text())
    for name,digest in source['sources'].items():
        assert sha(Path(name))==digest,'Source changed: '+name
    report=json.loads((root/'regression/manifest.json').read_text())
    assert report['state']=='COMPLETE' and len(report['tests'])==1
    test=report['tests'][0]
    assert test['app']=='perf_rce_ordered_capacity' and test['pass']
    assert sha(Path(report['simulator']))==report['simulator_sha256']
    assert sha(root/'regression/inputs'/test['app'])==test['elf_sha256']==source['elf_sha256']
    log=root/'regression'/test['app']/'stdout.log'
    text=log.read_text()
    checked=dict(test);classify(checked,text);assert checked['pass']
    windows=re.findall(r'COMPLETION_CAPACITY vl=(\d+) pairs=32 cycles=(\d+) PASS',text)
    assert len(windows)==4 and {int(vl) for vl,_ in windows}=={1,4,8,16}
    events=re.findall(r'\[AREA_COMPLETION\] cycle=(\d+) ordered=([\da-fA-F]+) fired=([\da-fA-F]+) rce=(\d+) rce_fire=(\d+) rce_wait=(\d+)',text)
    assert events and len({int(row[0]) for row in events})==len(events)
    counts=dict(ordered_requests=0,ordered_fires=0,rce_requests=0,rce_fires=0,
                simultaneous_request_cycles=0,ordered_during_rce_wait=0)
    for cycle,ordered,fired,rce,fire,waiting in events:
        ordered,fired=int(ordered,16),int(fired,16)
        rce,fire,waiting=map(int,(rce,fire,waiting))
        assert ordered<16 and fired&~ordered==0 and fire<=rce
        counts['ordered_requests']+=bin(ordered).count('1')
        counts['ordered_fires']+=bin(fired).count('1')
        counts['rce_requests']+=rce;counts['rce_fires']+=fire
        counts['simultaneous_request_cycles']+=bool(ordered) and bool(rce)
        counts['ordered_during_rce_wait']+=bool(ordered) and bool(waiting)
    summaries=re.findall(r'\[AREA_COMPLETION_SUMMARY\] (.*)',text)
    assert len(summaries)==1
    summary={key:int(value) for key,value in re.findall(r'(\w+)=(\d+)',summaries[0])}
    assert counts==summary and counts['ordered_fires']>0 and counts['rce_fires']>0
    result={'complete':True,'cycles':{vl:int(cycles) for vl,cycles in windows},
            'counters':counts,'log_sha256':sha(log),'elf_sha256':test['elf_sha256'],
            'scope':'Whole-program demand profiling on independent existing backends',
            'limits':'Request overlap and pipeline occupancy do not quantify a proposed shared backend latency or prove safe sharing; no hardware was shared in this run.'}
    (root/'comparison.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
