#!/usr/bin/env python3
"""Fresh raw-reference/source audit plus small corrupted-trace negative fixtures."""
import copy
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
from reference_check import HERE, NAME, model, audit_trace, require, prefix
sys.path.insert(0,str(HERE.parent))
import prepare_batch as base
import prepare_stall_prefix2 as old


def read(p):
    return json.loads(p.read_text())


def main():
    out=HERE/'audit01'
    require(not out.exists(),'Fresh audit only')
    out.mkdir()
    baseline=read(HERE/'baseline_pins.json')
    for p,d in baseline.items():
        require(base.sha(Path(p))==d,'Baseline pin changed: '+p)
    proof=read(HERE/'source_elf_proof.json')
    ready=read(HERE/'preparation_complete.json')
    require(ready['name']==NAME and ready['calls']==112 and not ready['vcs_started'],'Wrong preparation scope')
    original=HERE/'prepared'/NAME/'original'
    sys.path.insert(0,str(base.INTEGRATION))
    from prepare import adapt
    require((HERE/'prepared'/NAME/'case.c').read_text()==prefix(adapt((original/'scenario.c').read_text(),NAME),112),
            'Source port not exact wrapper plus reviewed112 stop')
    require(base.sha(original/'scenario.c')==proof['original_c_sha256'] and
            base.sha(original/'original_linux.elf')==proof['original_linux_elf_sha256'],'Original source identity')
    for backend in ('soc','spike'):
        elf=proof[backend+'_elf']
        require(base.sha(Path(elf['path']))==elf['sha256'],'ELF drift')
        require([r['insn'] for r in proof[backend+'_routine']]==[r['insn'] for r in proof['original_routine']],
                '13 original assembly instructions differ')
    gold=model()
    require(gold==read(HERE/'host_expected.json'),'Model/setup digest drift')
    host=read(HERE/'host/host_gate.json')
    require(len(host['tests'])==12 and all(t['status']=='PASS' for t in host['tests']), 'Host12 incomplete')
    for row in host['tests']:
        require(base.sha(HERE/'host'/(row['injection']+'.log'))==row['log_sha256'],'Host log drift')
    elf=Path(proof['spike_elf']['path'])
    trace=HERE/'reference/commits.log'
    reference=read(HERE/'reference/reference.json')
    raw=audit_trace(trace,elf,gold)
    require(all(reference[k]==v for k,v in raw.items()),'Raw reference differs from recorded result')
    require(base.sha(trace)==reference['commit_sha256'],'Raw trace pin changed')
    require(reference['returncode']==0 and reference['elapsed_s']<120,'Reference budget/exit')

    # Small fixtures end at the first scalar output read; never run Spike again.
    output=int(raw['addresses']['output'],16)
    source=int(raw['addresses']['input'],16)
    target=proof['spike_routine'][8]['pc']
    csr=proof['spike_routine'][9]['pc']
    pattern=re.compile(r'core\s+0:\s+\d\s+(0x[0-9a-f]+)\s+\((0x[0-9a-f]+)\)(.*)')
    lines=[]
    with trace.open() as stream:
        for line in stream:
            lines.append(line)
            m=pattern.match(line)
            if m and int(m[2],16)&127==3 and re.search(r'\bmem\s+0x0*'+format(output+1,'x')+r'\s*$',m[3]):
                break
    require(len(lines)<200000 and len(lines)>10,'Negative prefix not bounded/found')
    bad_result=list(lines)
    bad_result[-1]=re.sub(r'(\bx\d+\s+)0x[0-9a-f]+',r'\g<1>0x000000000001005b',bad_result[-1],count=1)
    bad_target=list(lines)
    bad_vi31=list(lines)
    bad_vx0=list(lines)
    bad_csr=list(lines)
    missing=[]
    for i,line in enumerate(lines):
        m=pattern.match(line)
        if m:
            pc,code,rest=int(m[1],16),int(m[2],16),m[3]
            if pc==target:
                bad_target[i]=line.replace(m[2],'0x30803c56',1)
                bad_vi31[i]=line.replace(m[2],'0x308fbc57',1)
                bad_vx0[i]=line.replace(m[2],'0x308e4c57',1)
            if pc==csr:
                bad_csr[i]=re.sub(r'(\bx10\s+)0x[0-9a-f]+',r'\g<1>0x0000000000000001',line,count=1)
            write=re.search(r'\bmem\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s*$',rest)
            if write and code&127==35:
                address=int(write[1],16)
                width=1<<((code>>12)&7)
                if address < source+1 and address+width > source:
                    continue
        missing.append(line)
    require(len(missing)<len(lines),'No initialization removed')
    fixtures=(('wrong_byte',bad_result,'Output mismatch'),
              ('target_encoding',bad_target,'13asm order/encoding'),
              ('wrong_vi31_encoding',bad_vi31,'13asm order/encoding'),
              ('wrong_vx0_encoding',bad_vx0,'13asm order/encoding'),
              ('nonzero_vstart',bad_csr,'vstart did not reset'),
              ('missing_source_bytes',missing,'Missing initialized source bytes'),
              ('missing_oracle',lines[:-1],'Incomplete calls/asm/oracle/exit'))
    negatives=[]
    for name,rows,reason in fixtures:
        path=out/(name+'.trace')
        path.write_text(''.join(rows))
        try:
            audit_trace(path,elf,gold)
        except ValueError as error:
            require(reason in str(error), 'Negative rejected for wrong reason: '+name+': '+str(error))
            negatives.append(dict(name=name,status='REJECTED_AS_EXPECTED',reason=str(error),sha256=base.sha(path)))
        else:
            raise ValueError('Corrupted trace accepted: '+name)
    retired=raw['firmware_retired_to_htif_store']
    estimate=dict(reference_retired=retired,measured_vcs_for_this_case=False,
        reused_m5_prefix_retired_per_second_range=[683,687],
        m5_rate_estimate_seconds=[retired/687,retired/683],
        conservative_historical_rate=273,conservative_seconds=retired/273,
        conservative_plus20percent_seconds=retired/273*1.2,
        expected_under3hours=retired/273*1.2<10800,
        automatic_vcs_timeout_or_launch_authorized=False)
    for p,d in baseline.items():
        require(base.sha(Path(p))==d,'Baseline changed during audit: '+p)
    audit=dict(status='PASS_ONE_AUTHENTIC112_E8M8_OP2_PREFIX_RAW_REFERENCE_NOT_DUT',
        exact_calls=112,fullcap_checks=114688,guards=224,returned_vstart=112,asm_retire_counts=[112]*13,
        setup_values_per_call=4226,original_tuple_endpoint=gold['rows'][-1]['tuple'],
        original_stopped_tuple=None,original_child_calls=2688,full_child_acceptance=False,
        host_positive=1,host_negative=11,raw_trace_negative_results=negatives,
        source_and_raw_trace_rechecked=True,baseline_pins_unchanged=True,reference=raw,
        instruction_cost=estimate,source_proof_sha256=base.sha(HERE/'source_elf_proof.json'),
        auditor_sha256=base.sha(Path(__file__)),no_vcs=True,no_rtl_changes=True)
    base.save(out/'audit.json',audit)
    print(audit['status'],json.dumps(estimate),flush=True)


if __name__=='__main__':
    main()
