#!/usr/bin/env python3
"""Explicit-image successor runner; never mutate sealed predecessor helpers."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import re
import sys
import threading

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('replay_base',HERE/'run.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image',required=True,type=Path)
    p.add_argument('--prepared',required=True,type=Path)
    p.add_argument('--out',required=True,type=Path)
    p.add_argument('--jobs',type=int,choices=range(1,9),default=4)
    p.add_argument('--timeout',type=int,default=600)
    p.add_argument('--case',action='append',help='Explicit subset; omitted means the complete prepared set')
    p.add_argument('--baseline-dispatcher',action='store_true',help='Allow only the intentionally older dispatcher in a sealed A/B baseline')
    a=p.parse_args();out=a.out.resolve()
    assert out.is_relative_to(HERE) and not out.exists() and 0<a.timeout<=10800
    out.mkdir(parents=True)
    plan=json.loads((a.prepared/'prepared.json').read_text())
    for group in ('files','pins'):
        for path,digest in plan[group].items(): assert base.sha(path)==digest,path
    spec=importlib.util.spec_from_file_location('integration_runtime',base.RUNTIME/'run.py')
    runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)
    ledger=json.loads((a.image/'image.json').read_text());snapshot=Path(ledger['snapshot'])
    frozen=runtime.sealed(snapshot)
    assert base.sha(snapshot/'snapshot.json')==ledger['snapshot_sha256']
    for path,digest in ledger['files'].items():assert base.sha(path)==digest,path
    build=Path(ledger['simv']).parent
    assert base.sha(build/'simulator.conf')==ledger['configuration_sha256']
    assert base.sha(build/'vcs_source_manifest.json')==ledger['manifest_sha256']
    sys.path.insert(0,str(frozen/'verification'))
    from ara_verify.vcs_source_manifest import collect
    compiled=json.loads((build/'vcs_source_manifest.json').read_text())
    assert collect(Path(compiled['filelist']),frozen,[Path(p) for p in compiled['extra_sources']])==compiled['files']
    live=json.loads((snapshot/'snapshot.json').read_text())['live_source_sha256']
    differences={}
    for path,digest in live.items():
        if Path(path).is_relative_to(base.ROOT/'hardware/src') or Path(path).is_relative_to(base.ROOT/'hardware/deps'):
            actual=base.sha(path)
            if actual!=digest:
                assert a.baseline_dispatcher and Path(path)==base.ROOT/'hardware/src/ara_dispatcher.sv',path
                differences[path]=dict(frozen=digest,current=actual)
    selected=a.case or list(plan['programs'])
    assert len(set(selected))==len(selected) and set(selected)<=set(plan['programs'])
    base.save(out/'identity.json',dict(image=ledger,prepared=str(a.prepared),
         prepared_sha256=base.sha(a.prepared/'prepared.json'),runner_sha256=base.sha(Path(__file__)),
         intentionally_older_dispatcher=differences,selected=selected))
    stopped=threading.Event()
    def execute(item):
        name,entry=item
        if stopped.is_set():return dict(name=name,status='CANCELLED',reason='Earlier focused failure')
        dest=out/name;dest.mkdir()
        elf=Path(entry['directory'])/'soc.elf';assert base.sha(elf)==entry['elf_sha256']
        r=base.command([ledger['simv'],'-no_save','-l','run.vcs.log','+ntb_random_seed=1',
             '+PRELOAD='+str(elf),'+TESTCASE='+name,'+NO_FSDB'],dest,'vcs',timeout=a.timeout,env=runtime.environment())
        log=(dest/'vcs.log').read_text(errors='replace')
        bad=re.findall(r'(?:RVV_FP_COMPARE_(?:FAIL|DETAIL|CAPACITY_FAIL)|FP_BIT|BOARD_REPLAY_(?:TRAP|SERVICE_FAIL)|Fatal:|Error:)[^\r\n]*',log)
        r.update(name=name,status='PASS' if r['returncode']==0 and not bad and
                 all(marker in log for marker in entry['pass_markers']) and
                 'Core Test *** SUCCESS ***' in log else 'NOT_PASS',diagnostics=bad)
        if r['status']!='PASS':stopped.set()
        base.save(dest/'result.json',r);print(json.dumps(r),flush=True)
        return r
    with ThreadPoolExecutor(max_workers=a.jobs) as pool:
        results=list(pool.map(execute,[(name,plan['programs'][name]) for name in selected]))
    for path,digest in ledger['files'].items():assert base.sha(path)==digest,path
    base.save(out/'results.json',dict(results=results,planned=len(selected),
        passed=sum(r['status']=='PASS' for r in results),scope=plan['scope']))
    return int(any(r['status']!='PASS' for r in results))


if __name__=='__main__':raise SystemExit(main())
