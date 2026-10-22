"""Freeze the exact reference entry once; no execution."""
from pathlib import Path
from context import HERE,SOFT,read,sha,save,require,artifacts
from owner_contract import ledger
def main():
    require(not (HERE/'entry.json').exists(),'One sealed entry')
    review=HERE.parent/'full_e64_m2_software_review01/SOFTWARE02_REVIEW.json'
    require(sha(review)=='8fd6df1a970b8acf07d8fb34d95d6ae21cc5ff70cb93c8a9380f4199961b730c' and read(review)['status']=='NO_BLOCKER_SOFTWARE02_HOST_COMPILED_CFG','Actual independent software review')
    pins=read(SOFT/'audit_artifacts02/pins.json')
    for p,h in pins.items():require(sha(p)==h,'Frozen artifacts '+p)
    info=read(SOFT/'audit_artifacts02/RESULT.json');require(info['positive_path_conservative_upper']<=3000000 and info['net_saving']>=75000,'Actual fullCFG')
    require(read(HERE/'host_receipt.json')['actual_exit_code']==0,'Actual small Host exit')
    owners=ledger();save(HERE/'source_owner_contract.json',dict(status='SOURCE_ELIGIBILITY_NOT_DUT_PROTOCOL_ACCEPTANCE',rows=owners,target_required=sum(r['target_required'] for r in owners),setup_memory_required=len(owners)*5))
    tools=[Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike'),review,SOFT/'audit_artifacts02/RESULT.json',SOFT/'audit_artifacts02/execution_receipt.json',SOFT/'audit_artifacts02/pins.json',HERE.parent/'full_e64_m2_software_review01/SOFTWARE02_REVIEW.md']
    for p in tools:pins[str(p)]=sha(p)
    for p in HERE.iterdir():
        if p.is_file():pins[str(p)]=sha(p)
    save(HERE/'entry.json',dict(status='SEALED_PENDING_EXACT_INDEPENDENT_REFERENCE_ENTRY_REVIEW',scope=dict(SEW=64,LMUL='m2',CAP=32,vtype=25,calls=5985,ops=35,results=191520,guards=11970,vstart=5985,helper_instructions=77805,output_reads=203490,checked_bytes=272,FP_calls=1890,FP_stores=120960,physical_registers=2,physical_bytes=256,physical_mask_bytes=128,vlm_bytes=4),limits=dict(rs=4000000,quit=True,Spike_wall_s=120,raw_bytes=768*1024**2,audit_wall_s=600,firmware_target=3000000),one_attempt=True,reference_requires_exact_review=True,DUT_authorized=False,pins=pins))
    print(sha(HERE/'entry.json'),flush=True)
if __name__=='__main__':main()
