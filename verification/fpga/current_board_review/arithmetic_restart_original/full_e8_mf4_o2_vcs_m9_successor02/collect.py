"""Once-after-exit metadata collector; no simulation or CSV semantic replay."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
sys.dont_write_bytecode=True
import replay as r
from checker import read,sha,require,common

def main(out):
    require(out.resolve().parent==r.HERE,'Owned terminal output')
    result=dict(status='NOT_ACCEPTED',scope='Full4095 cap32 source-port, not Linux/all22',started=time.time(),
                pid=os.getpid(),csv_semantic_reparses=0)
    try:
        service=read(out/'service_exit.json')
        require([service[k] for k in ('SERVICE_RESULT','EXIT_CODE','EXIT_STATUS')]==['success','exited','0'],
                'Actual systemd result/exit not success/exited/0')
        plan=read(out/'plan.json');digest=sha(out/'plan.json');r.validate(plan,r.IMAGE)
        end=read(out/'complete.json')
        require(end['status']==r.PASS and end['plan_sha256']==digest and end['aborted'] is False and
                end['pins_unchanged'] is True and type(end['retries']) is int and end['retries']==0,
                'Producer not full PASS/noabort/noretry/pins')
        require(len(end['results'])==1,'Exact one full program')
        case=plan['cases'][0];child=end['results'][0]
        require(child['name']==case['id'] and child['status']=='PASS' and type(child['returncode']) is int and
                child['returncode']==0 and not child['reason'] and 0<child['elapsed_s']<=r.CASE_BOUND,'Actual producer child')
        root=out/'replay/tests'/case['id'];raw=read(root/'child_outcome.unvalidated.json')
        require(type(raw['returncode']) is int and raw['returncode']==0 and raw['timed_out'] is False and
                raw['failure_seen'] is False and raw['cancelled'] is False and raw['elapsed_s']==child['elapsed_s'],
                'Durable simulator outcome')
        report=read(root/'strict_original.json')
        require(report['status']=='FULL_ORIGINAL_RVFI_ACCEPTED' and
                [report[k] for k in ('calls','results','guards','vstart_checks','helper_instructions')]==
                [4095,131040,8190,4095,53235] and report['full_order'] is True and report['partitioned'] is False,
                'Full strict checker scope')
        owners=report['memory_owners']
        require(owners['memory_requests']==20664 and owners['required_nonempty_helpers']==20475 and
                owners['required_active_memory_targets']==117 and
                owners['all_uop_allocs']==owners['all_uop_dones']>0 and owners['live_at_end']==0,'Actual full helper owners')
        common.base.verify_pins(plan['pins']);common.base.verify_pins(end['evidence_pins']);common.base.verify_pins(end['approval_pins'])
        require(read(root/'trace_summary.json')['status']=='VALID','Generic full trace checker')
        result.update(status='PASS_FULL4095_M9_METADATA_COLLECTED_NOT_LINUX',plan_sha256=digest,
            complete_sha256=sha(out/'complete.json'),service_exit_sha256=sha(out/'service_exit.json'),
            actual_service=service,actual_child=raw,strict_sha256=sha(root/'strict_original.json'),
            csv_sha256=sha(root/'commit_trace.csv'),calls=4095,results=131040,guards=8190,vstart_checks=4095,
            retired=report['retired'],rows=report['rows'],memory_owners=owners,
            input_pins=len(plan['pins']),evidence_pins=len(end['evidence_pins']),pins_unchanged=True)
    except Exception as error:
        result['firstcause']=f'{type(error).__name__}: {error}'
    result['finished']=time.time();r.durable(out/'collector_result.json',result)
    return int(result['status']!='PASS_FULL4095_M9_METADATA_COLLECTED_NOT_LINUX')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    raise SystemExit(main(p.parse_args().out))
