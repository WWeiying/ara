#!/usr/bin/env python3
"""NF2-specific artifacts, runtime identity and scalar-oracle observer."""
import re
from pathlib import Path
import sys
sys.dont_write_bytecode=True
import reference as ref
import csv_check
from scope import HERE, RUNTIME_ID as NAME, CASES, require
REF=HERE
sys.path.insert(0,str(HERE.parents[2]/'gather_repair05'))
import regression as common
read,sha=common.read,common.sha
READY_SHA='d427f9c9846e0c59d9374efb6fbae020df08c8f6a4472ce740e05ddf4306aa2f'
VETO=re.compile(common.BAD.pattern+r'|NF2_REMAINING4_SV39_FAIL|BOARD_REPLAY_MISMATCH|\b(?:FAIL|FAILED|ABORT|MISMATCH)\b',re.I)

def runtime_case(case):
    require(case['id']==NAME and case['historical_names']==[c['historical_name'] for c in CASES],
            'Runtime/historical source scope')
    return dict(case,original_name=NAME)

def specification():
    s=read(ref.OUT/'soc.symbols.json')
    code={str(int(m[1],16)):int(m[2],16) for m in
          re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s', (ref.OUT/'soc.dis').read_text(),re.M)}
    require(code[str(s['mx_segment_load'])]==0x20055c07 and
            code[str(s['mx_segment_store'])]==0x20055c27 and 'tohost' not in s,
            'Wrong original target or Spike ELF')
    return dict(symbols=s,code=code,cases=CASES,checks=3567,output_halfwords=128,guards=2,memory_bytes=8192)

def artifacts(result,case,ledger,spec,validator):
    common.check_artifacts(result,runtime_case(case),ledger)
    root=result.artifact_dir
    child=read(root/'child_outcome.unvalidated.json')
    require(child['name']==NAME and child['returncode']==result.returncode==0 and
            child['elapsed_s']==result.elapsed_s and child['architectural_acceptance'] is False and
            child['command_sha256']==sha(root/'command.json'),'Unvalidated child outcome differs')
    for p in (root/'console.log',root/'work/run.vcs.log'):
        require(not VETO.search(p.read_text()),'Raw failure veto: '+str(p))
    require((root/'console.log').read_text().count('NF2_REMAINING4_SV39_PASS')==1,'Exact firmware marker')
    report=csv_check.analyze(root/'commit_trace.csv',spec['symbols'],spec['code'])
    require(report['status']=='NF2_CSV_ORACLE_PASS',str(report))
    report.update(scope='Four original selected singles in real Sv39, not Linux signal-frame/full-parent acceptance',
                  raw_child_outcome='child_outcome.unvalidated.json',
                  child_outcome_sha256=sha(root/'child_outcome.unvalidated.json'))
    return report
