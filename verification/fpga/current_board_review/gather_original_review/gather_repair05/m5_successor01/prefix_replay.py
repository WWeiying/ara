#!/usr/bin/env python3
"""Same two authentic98 prefixes after exact focused acceptance; no retry/build."""
import argparse
import csv
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
GATHER = HERE.parent.parent
sys.path.insert(0,str(GATHER))


def module(name,path):
    spec = importlib.util.spec_from_file_location(name,path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


focus = module('m5_focus_runner',HERE/'replay.py')
raw = module('original98_csv_gate',GATHER/'stall_prefix2_launch02/checker.py')
sha,read,save,require = focus.sha,focus.read,focus.save,focus.require
integration = focus.integration


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--focus-acceptance-sha256',required=True)
    parser.add_argument('--execute',action='store_true')
    args = parser.parse_args()
    require(args.execute,'Prepare only; execution flag required')
    acceptance = HERE/'focused01/acceptance.json'
    require(sha(acceptance)==args.focus_acceptance_sha256,'Focused acceptance identity mismatch')
    accepted = read(acceptance)
    require(accepted['status']=='PASS_M5_FOCUS2_FULL514_ORIGIN0_CONTROL_IDENTICAL','Focused acceptance not PASS')
    plan = read(HERE/'prefix_plan.json')
    image_sha = accepted['image']['image_sha256']
    admitted = focus.image_check(read(HERE/'focus_plan.json'),image_sha)
    entries = read(Path(plan['programs'])/'programs.json')['programs']
    for case in plan['cases']:
        require(sha(Path(entries[case['name']]['path']))==entries[case['name']]['sha256']==case['elf_sha256'], 'Original98 ELF changed')
    out = Path(plan['output'])
    out.mkdir(exist_ok=False)
    save(out/'plan.json',plan)
    # Own2 + Tesla48 reserve4; classify its cgroup once to avoid double-counting actuals.
    resources = focus.resources()
    resources['scope']='Prefix2; Whole59 terminal, no old reservations'
    resources['future_tesla48_reserve']=4
    counted = sum('ara-m5-regression48' in process['cgroup'] or 'ara-memory-candidate05-regression' in process['cgroup']
                  for process in resources['live'])
    resources['total_with_future48']=resources['total']+max(0,4-counted)
    require(resources['total_with_future48']<=24,'Prefix2 plus future48 cap exceeded')
    save(out/'admission.json',dict(resources=resources,image=admitted,
         focus_acceptance_sha256=args.focus_acceptance_sha256))
    ledger = read(Path(plan['image'])/'image.json')
    integration.framework(Path(ledger['snapshot'])/'sources')
    import ara_verify.runner as engine
    engine.FAIL_RE = re.compile(engine.FAIL_RE.pattern+'|'+raw.VETO.pattern,engine.FAIL_RE.flags)
    original = engine.RegressionRunner._run_test
    checked = {}

    def strict(self,test,image):
        result = original(self,test,image)
        if result.status=='PASS':
            try:
                case = next(case for case in plan['cases'] if case['name']==test.name)
                raw.console_gate((result.artifact_dir/'console.log').read_text(),test.name)
                require(sha(result.artifact_dir/'input.elf')==case['elf_sha256'],'Private original98 ELF changed')
                with (result.artifact_dir/'commit_trace.csv').open() as stream:
                    checked[test.name]=raw.retirement(csv.DictReader(stream),case,raw.source.prep.model(case['operation']))
                save(result.artifact_dir/'fulloracle98_gate.json',checked[test.name])
            except Exception as error:
                result.status,result.reason='FAIL',str(error)
        if result.status!='PASS':
            self.cancel_event.set()
        return result

    engine.RegressionRunner._run_test=strict
    started = time.time()
    rc = integration.run_programs(SimpleNamespace(image=Path(plan['image']),programs=Path(plan['programs']),
        out=out/'replay',case=[case['name'] for case in plan['cases']],jobs=2,timeout=9000,execute=True))
    focus.image_check(read(HERE/'focus_plan.json'),image_sha)
    for case in plan['cases']:
        require(sha(Path(entries[case['name']]['path']))==case['elf_sha256'],'ELF changed during run')
    passed = rc==0 and set(checked)=={case['name'] for case in plan['cases']}
    save(out/'complete.json',dict(status='PASS_TWO_AUTHENTIC98_PREFIXES_M5' if passed else 'NOT_ACCEPTED',
        runner_returncode=rc,results=read(out/'replay/summary.json'),checked=checked,
        elapsed_s=time.time()-started,focus_acceptance_sha256=args.focus_acceptance_sha256,
        image=admitted,retries=0,original_stopped_tuple=None,exact11_failure_reproduction=False,
        full_parent_closure=False,original_linux_elf_replay=False))
    return 0 if passed else 1


if __name__=='__main__':
    env=integration.environment()
    os.environ.clear()
    os.environ.update(env)
    sys.exit(main())
