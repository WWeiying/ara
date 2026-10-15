"""Seal software/reference evidence and measured-cost projections; never run DUT."""
from pathlib import Path
from prepare import HERE,PARENT,SHAPES,read,save,sha,require,CAP

def main():
    p=SHAPES[0];root=HERE/p['id'];out=root/'reference01'
    proof=read(root/'sourceproof.json');result=read(out/'reference.json')
    execution=read(out/'execution.json');audit=read(out/'audit_process_exit.json')
    for record in (execution,audit):
        require(type(record['returncode']) is int and record['returncode']==0
                and record['timeout'] is False,'Actual reference and full-audit exits')
    expected=dict(status='FULL_ORIGINAL_REFERENCE_PASS_NOT_DUT',shape=p['id'],calls=4095,
        results=131040,guards=8190,vstart_checks=4095,helper_instructions=53235,
        capacity_calls=1,source_full_order=True,partitioned=False,vlenb=128,vlenb_reads=1,full_raw_parses=1)
    require(all(result[k]==v for k,v in expected.items()),'Full original reference scope')
    model=read(root/'model.json');calls=result['call_ledger']
    require(len(calls)==len(model)==4095,'Full call ledger')
    for call,gold in zip(calls,model):
        require(all(call[k]==gold[k] for k in ('ordinal','op','seed','vl','mode','vstart'))
                and call['reads']==list(range(CAP+2)) and call['returned_vstart']==0,
                'Every original call/order/result/guard')
    require(proof['original_sha256']=='da5d08b60f2b68567aea7254fc3c3ab1ce8c14369e5f473b384fa91248fce823',
            'Exact original e8mf4 identity')
    pins=dict(read(HERE/'bound.json')['pins'])
    for path,digest in pins.items():require(sha(path)==digest,'Bound input drift '+path)
    proxies=[]
    definitions=[('M6_e8_mf8',PARENT/'full_small2_vcs_m6_plan01/prepared01/replay/tests/arithmetic_full_e8_mf8',
                  PARENT/'full_small2_e8_offline_recovery_audit01/run01/TERMINAL.json'),
                 ('M6_e16_mf4',PARENT/'full_e16_mf4_vcs_m6_plan01/prepared01/replay/tests/arithmetic_full_e16_mf4',
                  PARENT/'full_e16_mf4_terminal_audit01/run01/TERMINAL.json'),
                 ('M7_e64_m1_O2',PARENT/'full_e64_m1_o2_vcs_m7_plan01/prepared01/replay/tests/arithmetic_full_e64_m1',
                  PARENT/'full_e64_m1_o2_vcs_m7_plan01/prepared01/complete.json')]
    for label,case,authority in definitions:
        receipt=read(case/'child_outcome.unvalidated.json');trace=read(case/'trace_summary.json')
        require(type(receipt['returncode']) is int and receipt['returncode']==0 and trace['status']=='VALID',
                'Actual sizing-proxy child/trace outcome')
        elapsed=receipt['elapsed_s'];rate=trace['retire_count']/elapsed
        projected=result['firmware_through_htif']/rate
        proxies.append(dict(label=label,authority=str(authority),authority_sha256=sha(authority),
            retired=trace['retire_count'],elapsed_s=elapsed,retired_per_s=rate,
            projected_sim_s=projected,with20percent_and300s_validation=projected*1.2+300,
            estimate_not_M9_measurement=True))
        for f in (authority,case/'child_outcome.unvalidated.json',case/'trace_summary.json'):
            pins[str(f)]=sha(f)
    image=Path('/home/wangwy/fpga_runs/current_board_memory_candidate09/campaign/image/image.json')
    require(sha(image)=='48d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a','Target M9 identity')
    pins[str(image)]=sha(image)
    handoff=PARENT.parent/'memory_candidate09_build/BUILD_HANDOFF01.md';pins[str(handoff)]=sha(handoff)
    for f in HERE.rglob('*'):
        if f.is_file() and f.name not in ('READY.json','evidence_pins.json'):pins[str(f)]=sha(f)
    save(HERE/'evidence_pins.json',pins)
    worst=max(x['with20percent_and300s_validation'] for x in proxies)
    ready=dict(status='HOST_SPIKE_FULL_E8_MF4_CAP32_PASS_NOT_DUT',shape=p['id'],cap=CAP,
        source_C_bytes_recovered=False,binary_equivalent_original_reconstruction=True,
        original_linux_sha256=proof['original_sha256'],soc_sha256=proof['backends']['soc']['sha256'],
        spike_sha256=proof['backends']['spike']['sha256'],full_original_calls=4095,
        result_elements=131040,guards=8190,vstart_checks=4095,helper_instructions=53235,
        physical_arrays=dict(a=1024,b=1024,out=1026,mask_bytes=128),
        host_positive=1,host_negative=8,actual_reference_exit=execution,actual_reference_audit_exit=audit,
        firmware_through_htif=result['firmware_through_htif'],full_raw_parses=1,reference_attempts=1,
        evidence_pins=str(HERE/'evidence_pins.json'),evidence_pins_sha256=sha(HERE/'evidence_pins.json'),
        pins=len(pins),cost_proxies=proxies,limit_s=10800,conservative_projected_s=worst,
        budget_decision='HOLD_COST_OVER_3H' if worst>10800 else 'PLAUSIBLE_UNMEASURED_M9_REQUIRES_REVIEW',
        target_image_sha256=sha(image),DUT_started=False,DUT_accepted=False,reference_reruns=0,
        fflags_oracle='Original has no explicit fflags oracle; none invented',
        scope='Complete original4095 source-port history, not original Linux execution')
    save(HERE/'READY.json',ready)
    print(ready['status'],ready['budget_decision'],ready['firmware_through_htif'],sha(HERE/'READY.json'),flush=True)

if __name__=='__main__':main()
