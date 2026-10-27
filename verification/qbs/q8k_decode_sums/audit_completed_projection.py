#!/usr/bin/env python3
"""Archive functional timing without relabeling a truncated-event UVM run PASS."""
import argparse
import json
from pathlib import Path
import sys
from check_projection_pair import check

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'verification/qbs'))
from run_half_scale_soc import atomic_json,hashes,digest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True)
    args=p.parse_args(); run=args.run.resolve(strict=True)
    pins=json.loads((run/'manifest.json').read_text())
    if hashes(map(Path,pins))!=pins: raise ValueError('Input drift')
    report=json.loads((run/'soc/uvm_result.json').read_text())
    expected=['UVM event trace is incomplete or disagrees with summary',
              'contract event trace is incomplete or disagrees with summary',
              'UVM backend VID event trace is incomplete',
              'UVM and independent backend VID events disagree']
    if report['issues']!=expected or report['status']!='FAIL': raise ValueError('Different UVM issue scope')
    c=report['contract_counts']; b=report['backend_counts']
    if (c['protocol_errors'] or c['exceptions'] or c['outstanding'] or
        c['requests']!=c['responses'] or b['allocations']!=b['completions'] or b['aborted']):
        raise ValueError('Unclosed protocol/backend activity')
    for kind in ('read','write'):
        counts=report['axi_'+kind+'_counts']
        if counts['pending'] or counts['aborted']: raise ValueError('Pending/aborted AXI')
    text=(run/'soc/work/run.vcs.log').read_text()
    if 'UVM_ERROR :    0' not in text or 'UVM_FATAL :    0' not in text:
        raise ValueError('UVM errors or incomplete ending')
    if report['vector_trace_sha256']!=digest(run/'soc/work/vector_trace.csv'):
        raise ValueError('Vector evidence drift')
    golden=json.loads((run/'golden.json').read_text())
    if golden['state']!='PASS': raise ValueError('Missing golden')
    trials=check(text,golden['trials'])
    original=sum(t['total'] for t in trials if not t['candidate'])
    candidate=sum(t['total'] for t in trials if t['candidate'])
    result=dict(state='FUNCTIONAL_TIMING_COMPLETE_EVENT_AUDIT_INCOMPLETE',
        formal_uvm_status='FAIL',trials=trials,original_cycles=original,candidate_cycles=candidate,
        speedup=original/candidate,cycle_reduction=1-candidate/original,
        log_sha256=digest(run/'soc/work/run.vcs.log'),
        scope='Captured complete projection only; original failure is preserved, not full event signoff')
    output=run/'functional-timing-audit.json'
    if output.exists(): raise ValueError('Audit output already exists')
    atomic_json(output,result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
