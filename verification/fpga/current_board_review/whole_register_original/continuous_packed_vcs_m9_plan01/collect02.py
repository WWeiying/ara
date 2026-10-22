"""Once-after-exit metadata collector; no simulation or CSV semantic replay."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
sys.dont_write_bytecode=True
import replay02 as r
from checker import read,sha,require,common

def main(out):
    require(out.resolve().parent==r.HERE,'Owned terminal output')
    result=dict(status='NOT_ACCEPTED',scope='Full continuous1134 whole source-port and366 exclusions, not Linux/partitions',started=time.time(),
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
                [report[k] for k in ('calls','exclusions','output_byte_checks','fresh_input_stores',
                                     'fresh_output_stores','output_word_reads','vstart_reads','helper_instructions')] ==
                [1134,366,1233792,145152,154224,154224,2268,21366] and
                report['full_order'] is True and report['partitioned'] is False and report['raw_exit']==0 and
                report['full_csv_passes']==1, 'Full continuous original1134 strict scope')
        owners=report['owners']
        require([owners[k] for k in ('payload_requests','required_staging_readback','required_nonempty_targets',
                                     'allowed_empty_targets','required_owners','live_at_end')] ==
                [4536,3402,864,270,4266,0] and
                owners['all_uop_allocs']==owners['all_uop_dones']>0, 'Actual full whole payload owners')
        require(report['actual_numeric_outcome_sha256']==sha(root/'child_outcome.unvalidated.json') and
                report['raw_sha256']==sha(root/'commit_trace.csv'), 'Single-pass source/actual outcome binding')
        require(read(root/'trace_summary.json')==dict(status='VALID',**report['generic']),
                'One-pass generic and strict trace report agreement')
        common.base.verify_pins(plan['pins']);common.base.verify_pins(end['evidence_pins']);common.base.verify_pins(end['approval_pins'])
        require(read(root/'trace_summary.json')['status']=='VALID','Generic full trace checker')
        result.update(status='PASS_CONTINUOUS1134_M9_METADATA_COLLECTED_NOT_LINUX',plan_sha256=digest,
            complete_sha256=sha(out/'complete.json'),service_exit_sha256=sha(out/'service_exit.json'),
            actual_service=service,actual_child=raw,strict_sha256=sha(root/'strict_original.json'),
            csv_sha256=sha(root/'commit_trace.csv'),calls=1134,exclusions=366,output_byte_checks=1233792,vstart_reads=2268,
            fresh_input_stores=145152,fresh_output_stores=154224,output_word_reads=154224,
            retired=report['retired'],rows=report['rows'],owners=owners,
            input_pins=len(plan['pins']),evidence_pins=len(end['evidence_pins']),pins_unchanged=True)
    except Exception as error:
        result['firstcause']=f'{type(error).__name__}: {error}'
    result['finished']=time.time();r.durable(out/'collector_result.json',result)
    return int(result['status']!='PASS_CONTINUOUS1134_M9_METADATA_COLLECTED_NOT_LINUX')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    raise SystemExit(main(p.parse_args().out))
