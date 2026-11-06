#!/usr/bin/env python3
"""Recheck completed native pairs and extract per-command diagnostic activity."""
import argparse
import json
from pathlib import Path
import re

from audit import digest,require,verify_pins
from check_output_native import check_log

PHASES=('setup','activation','weight','compute','overlap','drain',
        'scheduler','commit','fault','terminal')


def activity(text,q4):
    rows=[]; pending=None; command=None
    for line in text.splitlines():
        if line.startswith('OUTPUT_NATIVE_BEGIN '):
            require(pending is None,'Nested ROI')
            m=re.fullmatch(r'OUTPUT_NATIVE_BEGIN trial=(\d+) candidate=([01])',line)
            require(m is not None,'Malformed ROI')
            pending=tuple(map(int,m.groups()));command=None
        elif line.startswith('[QBS_PERF] '):
            require(pending is not None and command is None,'Unpaired/duplicate QBS command')
            command={}
            for field in line.split()[1:]:
                key,sep,value=field.partition('=')
                require(sep and key not in command and value.isdecimal(),'Malformed QBS field')
                command[key]=int(value)
        elif line.startswith('OUTPUT_NATIVE_RESULT '):
            require(pending is not None and command is not None,'Missing command/ROI')
            trial,candidate=pending
            expected=dict(seq=trial+1,m=2,n=20,vlen=1024,lanes=4,success=1,
                          fault=0,validation_fault=0,read_fault=0,
                          weight_bytes=20*(72 if q4 else 136),activation_bytes=272,
                          useful_pairs=5120)
            require(all(command.get(k)==v for k,v in expected.items()),'QBS work/identity mismatch')
            require(sum(command.get('phase_'+name+'_cycles',-1000000) for name in PHASES)==
                    command.get('busy_cycles'),'QBS phase accounting mismatch')
            require(trial==len(rows) and candidate==(0,1,1,0)[trial],'Wrong ABBA mapping')
            rows.append(dict(trial=trial,candidate=candidate,counters=command));pending=None
    require(pending is None and len(rows)==4,'Incomplete activity')
    return rows


def collect(root):
    root=Path(root).resolve(strict=True)
    result=json.loads((root/'result.json').read_text())
    require(result.get('state')=='PASS' and result.get('performance_measured') is True and
            result.get('independent_protocol_checked') is True,'Run not accepted')
    pins=json.loads((root/'source-pins.json').read_text());verify_pins(pins)
    build=Path(json.loads((root/'status.json').read_text())['build'])
    receipt=json.loads((build/'build.json').read_text())
    q4=int(receipt['kind']=='q4_0')
    golden=(Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')/
        'quant-prefill-capture-20261028-01'/receipt['kind']/'prefill/block/kqv_out-0.bin')
    require(pins.get(str(golden))==digest(golden),'Golden not in run pins')
    text=(root/'work/run.vcs.log').read_text()
    measured=check_log(text,golden.read_bytes(),q4)
    require(measured==result['measured'],'Measured result differs from raw replay')
    # The original independent checker also validates log/trace/ELF/image identity.
    from run_output_native import accepted
    accepted.protocol(root/'work',receipt['elf_sha256'],result['image'])
    rows=activity(text,q4)
    for row,trial in zip(rows,measured['trials']):
        require(row['counters']['busy_cycles']<=trial['cycles'],'Inconsistent cycle domains')
        row['qbs_busy_per_call_cycle']=row['counters']['busy_cycles']/trial['cycles']
    return dict(kind=receipt['kind'],measured=measured,activity=rows,
                log_sha256=digest(root/'work/run.vcs.log'),
                run_receipt_sha256=digest(root/'result.json'),source_pins_rechecked=len(pins),
                scope='Same-image complete call; activity is diagnostic, not additive stall attribution')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--q4',type=Path,required=True);p.add_argument('--q8',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    require(not a.output.exists(),'Refuse to overwrite evidence')
    reports=[collect(a.q4),collect(a.q8)]
    require([r['kind'] for r in reports]==['q4_0','q8_0'],'Wrong pair')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(dict(state='PAIRED_NATIVE_CALLS_PASS',reports=reports,
                                      whole_model=False),indent=2)+'\n')


if __name__=='__main__':main()
