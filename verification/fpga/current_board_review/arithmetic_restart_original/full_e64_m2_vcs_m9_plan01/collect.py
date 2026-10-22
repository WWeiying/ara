"""Independent after-exit metadata collector; no semantic CSV reparse."""
import argparse
import os
from pathlib import Path
import time
import checker as c
import replay as r

def collect(out):
    c.require(out.resolve().parent==c.HERE,'Own exact terminal output')
    result=dict(status='NOT_ACCEPTED',pid=os.getpid(),started=time.time(),csv_semantic_reparses=0,
        scope='Original e64/m2 full5985 source port, not original Linux stall closure')
    try:
        service=c.read(out/'service_exit.json')
        c.require([service[k] for k in ('SERVICE_RESULT','EXIT_CODE','EXIT_STATUS')]==['success','exited','0'],'Actual whole service exit0')
        plan=c.read(out/'plan.json');digest=c.sha(out/'plan.json');r.validate(plan,r.IMAGE)
        end=c.read(out/'complete.json')
        c.require(end['status']==r.PASS and end['plan_sha256']==digest and end['aborted'] is False and
            end['pins_unchanged'] is True and type(end['retries'])is int and end['retries']==0,'Whole producer actual PASS/noabort/pins')
        c.require(len(end['results'])==1,'One source single only')
        child=end['results'][0];case=plan['cases'][0]
        c.require(child['name']==case['id'] and child['status']=='PASS' and type(child['returncode'])is int and
            child['returncode']==0 and not child['reason'] and 0<child['elapsed_s']<=10800,'Actual DUT child status')
        root=out/'replay/tests'/case['id'];raw=c.read(root/'child_outcome.unvalidated.json')
        c.require(type(raw['returncode'])is int and raw['returncode']==0 and raw['timed_out'] is False and
            raw['failure_seen'] is False and raw['cancelled'] is False and raw['elapsed_s']==child['elapsed_s'],
            'Actual monitor outcome before postchecks')
        report=c.read(root/'strict_original.json');strict=report['strict'];generic=report['generic'];owners=report['owner_coverage']
        c.require(strict['status']=='FULL5985_ACTUAL_RVFI_ACCEPTED_NOT_LINUX' and
            [strict[k] for k in ('calls','results','guards','returned_vstart_zero','helper_instructions','packed_output_reads')]==
                [5985,191520,11970,5985,77805,203490] and strict['routine_counts']==[5985]*13,
            'Actual full65/source/guard/vstart/helper ledger')
        c.require(strict['fresh_output_bytes_each_call']==272 and strict['full_order'] and not strict['partitioned'],'Full original fresh output/history')
        c.require(report['strict_csv_parses']==1 and (strict['rows'],strict['retired'],strict['last_cycle'])==
            (generic['rows'],generic['retire_count'],generic['last_cycle']) and generic['cvx_exception_count']==0,'Strict/generic same closed CSV')
        contract=c.owner_contract()
        c.require([owners[k] for k in ('compulsory_memory_owners','required_target_owners','required_op24_memory_targets')]==
            [contract[k] for k in ('compulsory_memory_owners','required_target_owners','required_op24_memory_targets')] and
            owners['minimum_required_owners']==contract['compulsory_memory_owners']+contract['required_target_owners'] and
            owners['optional_slideup_targets']==contract['optional_slideup_targets'],
            'Actual model-derived necessary owners')
        c.require(strict['typed_sentinel']=='000000000000005b' and strict['tail_read_bytes']==0 and
            strict['physical_registers_each_group']==2 and strict['vtype']==25,'Actual typed16 scope')
        c.require(generic['backend_uop_alloc_count']==generic['backend_uop_done_count']>0 and
            generic['cvx_request_count']==generic['cvx_response_count']>0,'Complete real protocol')
        c.common.base.verify_pins(plan['pins']);c.common.base.verify_pins(end['evidence_pins']);c.common.base.verify_pins(end['approval_pins'])
        c.require(c.sha(root/'commit_trace.csv')==report['actual_csv_sha256'] and c.read(root/'trace_summary.json')['status']=='VALID',
            'Closed raw hash and frozen generic VALID')
        result.update(status='ACCEPTED_M9_ORIGINAL_E64_M2_FULL5985_NOT_LINUX',plan_sha256=digest,
            complete_sha256=c.sha(out/'complete.json'),actual_service=service,actual_monitor=raw,
            strict_report_sha256=c.sha(root/'strict_original.json'),csv_sha256=report['actual_csv_sha256'],
            calls=5985,results=191520,guards=11970,vstart_zero=5985,helper_instructions=77805,
            packed_output_reads=203490,required_memory_helpers=29925,required_targets=contract['required_target_owners'],required_op24_targets=117,
            pins_pre_post_unchanged=True,original_Linux_historical_stall_closed=False)
    except BaseException as error:result['firstcause']=f'{type(error).__name__}: {error}'
    result['finished']=time.time();r.durable(out/'collector_result.json',result)
    return int(result['status']!='ACCEPTED_M9_ORIGINAL_E64_M2_FULL5985_NOT_LINUX')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    raise SystemExit(collect(parser.parse_args().out))
