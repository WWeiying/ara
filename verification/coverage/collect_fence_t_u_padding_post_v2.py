"""Case-specific scalar NO_TRAFFIC policy; retain errors, no admission override."""
import argparse
import inspect
import json
from pathlib import Path
import re

import collect_fence_t_u_padding_post as old

ROOT, OUT, require = old.ROOT, old.OUT, old.require
PREDECESSOR_SHA = '3cf24ee8d61e55178e2fa13d23d9048f078bab713cc89da620fee679bc8667e1'
UVM = ROOT/'verification/uvm/ara_cvxif_uvm_pkg.sv'
UVM_SHA = '9b342fa6837abfd9b35cea81fdf841ae86f56008e5cc5d51a58b3c4128924420'
POLICY = ROOT/'verification/coverage/audit_uvm_no_traffic_719.py'
POLICY_SHA = 'c37a9ffbefdcfffd4e1e8cd7e9f4731596ba09663d211d63e0700929a210b37e'
EXPECTED_ERRORS = {
    'CVXIF/NO_TRAFFIC': (504, 'uvm_test_top.env.scoreboard', 'scoreboard observed no complete CVXIF traffic'),
    'VID/NO_TRAFFIC': (630, 'uvm_test_top', 'real Ara program did not allocate a backend vid'),
}
COUNT_MESSAGES = {
    'AXI/STALL_COUNT': 'ar=0 r=0 aw=0 w=0 b=0 hold_checks=0',
    'CVXIF/COUNT': 'observed requests=0 responses=0 aborted=0 reused=0 immediate=0',
    'VID/COUNT': 'allocations=0 completions=0 aborted=0 max_live=0',
    'AXI/READ_COUNT': 'ar=0 r_beats=0 completed=0 aborted=0 pending=0 max_pending=0',
    'AXI/WRITE_COUNT': 'aw=0 w_beats=0 w_bursts=0 matched=0 b=0 aborted=0 pending=0 max_pending=0',
}
CONTRACT = '[ARA_CONTRACT] requests=0 responses=0 exceptions=0 mmu_request_cycles=0 protocol_errors=0 outstanding=0 req_stalled=0 resp_stalled=0'


def policy_log(text):
    errors, counts, summary, actual = [], {}, {}, dict(INFO=0,WARNING=0,ERROR=0,FATAL=0)
    for number,line in enumerate(text.splitlines(),1):
        summed=re.fullmatch(r'UVM_(INFO|WARNING|ERROR|FATAL)\s*:\s*(\d+)\s*',line)
        if summed:
            require(summed[1] not in summary, 'Duplicate UVM severity summary')
            summary[summed[1]]=int(summed[2]);continue
        event=re.match(r'^UVM_(INFO|WARNING|ERROR|FATAL)\s+(?!:)',line)
        if not event:continue
        severity=event[1];actual[severity]+=1
        if severity in ('ERROR','FATAL'):
            matched=re.fullmatch(r'UVM_ERROR (.+)\((\d+)\) @ (\d+): (\S+) \[([^\]]+)\] (.*)',line)
            require(matched is not None and matched[5] in EXPECTED_ERRORS, 'Unexpected/malformed UVM error or fatal')
            tag=matched[5];coordinate,component,message=EXPECTED_ERRORS[tag]
            require(matched[1]==str(UVM) and int(matched[2])==coordinate and
                    matched[4]==component and matched[6]==message, 'NO_TRAFFIC identity/message differs')
            errors.append(dict(line=number,text=line,tag=tag,severity='ERROR'))
        for tag,message in COUNT_MESSAGES.items():
            token='['+tag+'] '
            if token in line:
                require(severity=='INFO' and tag not in counts and line.endswith(token+message),
                        'Nonzero/missing-field/duplicate protocol counter: '+tag)
                counts[tag]=message
    require(len(errors)==2 and {e['tag'] for e in errors}==set(EXPECTED_ERRORS), 'Not exactly two expected errors')
    require(counts==COUNT_MESSAGES, 'Incomplete protocol counts')
    require(set(summary)==set(actual) and all(summary[k]==actual[k] for k in ('ERROR','FATAL','WARNING'))
            and summary['ERROR']==2 and summary['FATAL']==summary['WARNING']==0,
            'UVM summary/actual errors differ')
    lines=text.splitlines()
    require(lines.count(CONTRACT)==1 and sum(l.startswith('[ARA_CONTRACT]') for l in lines)==1,
            'Missing/extra/nonzero ARA contract counters')
    require(lines.count('Core Test *** SUCCESS *** (tohost = 0)')==1, 'Missing/duplicate CoreSUCCESS')
    return dict(classification='EXPECTED_SCALAR_POLICY_MISMATCH_EXACT_TWO_NOT_UVM_ZERO',
                actual_UVM_errors=2, actual_UVM_fatals=0, errors=errors,
                zero_counter_records=counts, contract=CONTRACT, summary=summary,
                actual_report_lines_by_severity=actual,
                INFO_count_note='Reporting-server INFO header may not be included in its own printed INFO total; all actual ERROR/FATAL/WARNING totals are exact-checked',
                protocol_liveness_qualified=False, require_contract_promoted=False)


def evaluate(console, trace, metadata, blob, sites, vcs_log):
    first, second = policy_log(console), policy_log(vcs_log)
    require(first['summary']==second['summary'] and first['zero_counter_records']==second['zero_counter_records'],
            'Console/VCS policy mismatch')
    symbols={s['Symbol']['Name']['Name']:s['Symbol'] for s in metadata['Symbols']}
    rows=old.oracle.parse_padding_trace(trace,symbols['padding_u_ecall']['Value'])
    for row in rows:
        word=row['insn'];op=word&127;funct3=(word>>12)&7
        require(op not in (0x57,0x2b,0x5b,0x7b) and
                not (op in (7,0x27) and funct3 not in (2,3)), 'Unexpected vector/custom backend retirement')
        require(op!=0x0b or word==0x0b, 'Noncanonical FENCE.T/custom0 retirement')
    result=old.evaluate(console,trace,metadata,blob,sites)
    result.update(scalar_policy=dict(console=first,vcs_log=second,
                  all_retired_records_checked=len(rows), vector_retirements=0,
                  cvx_backend_events=0, UVM_errors_preserved=True,
                  source_sha256=UVM_SHA, policy_reference=str(POLICY),
                  policy_reference_diagnostic_only=True),
                  status='SCOPED_SCALAR_FUNCTIONAL_RETIREMENT_PASS_WITH_TWO_UVM_POLICY_ERRORS_NOT_ADMITTED')
    result.update(case_specific_scalar_qualifier=True, UVM_clean=False,
                  generic_UVM_override=False, admissibility_decided=False)
    return result


def collector():
    require(old.sha(Path(old.__file__))==PREDECESSOR_SHA, 'Frozen collector drift')
    require(old.sha(UVM)==UVM_SHA and old.sha(POLICY)==POLICY_SHA, 'Frozen UVM/diagnostic source differs')
    sourcepins_path=OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
    sourcepins=json.loads(sourcepins_path.read_bytes())
    require(sourcepins[str(UVM)]==UVM_SHA, 'UVM is not compiled-image source')
    source=inspect.getsource(old.collect)
    before="(build/'input.elf').read_bytes(), plan['proof']['sites'])"
    after="(build/'input.elf').read_bytes(), plan['proof']['sites'], paths[1].read_text())"
    require(source.count(before)==1, 'Exact VCS log argument boundary differs')
    source=source.replace(before,after)
    before='    output.mkdir()'
    after="""    extra_pins={str(Path(old.__file__)):PREDECESSOR_SHA,str(UVM):UVM_SHA,str(POLICY):POLICY_SHA,
                str(ROOT/'verification/coverage/test_collect_fence_t_u_padding_post_v2.py'):
                sha(ROOT/'verification/coverage/test_collect_fence_t_u_padding_post_v2.py')}
    for path,digest in extra_pins.items():require(sha(path)==digest,'Successor dependency drift: '+path)
    result['collector_pins'].update(extra_pins)
    output.mkdir()"""
    require(source.count(before)==1, 'Exact additive pin boundary differs')
    source=source.replace(before,after)
    namespace=dict(old.collect.__globals__,evaluate=evaluate,old=old,UVM=UVM,UVM_SHA=UVM_SHA,
                   POLICY=POLICY,POLICY_SHA=POLICY_SHA,PREDECESSOR_SHA=PREDECESSOR_SHA,__file__=__file__)
    exec(compile(source,__file__+':scoped-policy-only','exec'),namespace)
    return namespace['collect']


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--execution',type=Path,required=True)
    parser.add_argument('--execution-sha256',required=True)
    args=parser.parse_args()
    collector()(args.output.absolute(),args.execution.absolute(),args.execution_sha256)
