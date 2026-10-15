"""Freeze completed two-single preparation without executing references or DUT."""
import json
from pathlib import Path
import prepare as p

def main():
    p.require(not (p.HERE/'READY.json').exists(),'Fresh readiness seal only')
    bound=p.read(p.HERE/'STATIC_BOUND.json');p.verify(bound['pins'])
    p.require(p.read(p.HERE/'host01/execution.json')['actual_wait_returncode']==0,'Original Host process')
    p.require(p.read(p.HERE/'recovery01/host01/execution.json')['actual_wait_returncode']==0,'Recovery Host process')
    prefix=p.read(p.HERE/'recovery01/startup_prefix.json');p.verify(prefix['pins'])
    p.require(prefix['status']=='PASS_BOUNDED_STARTUP_IDENTITY' and
              all(c['completion_zero_writes']==1 for c in prefix['cases']),'Actual startup identity')
    external={};cases=[]
    for sew,folder in ((8,'audit_e8_01'),(64,'reference_e64_01')):
        software=p.HERE/'software01'/f'e{sew}';r=p.HERE/'recovery01'/folder
        inputs=p.read(software/'input_pins.json');p.verify(inputs);external.update(inputs)
        inputs=p.read(r/'input_pins.json');p.verify(inputs);external.update(inputs)
        result=p.read(r/'status.json');execution=result['execution'];cfg=p.o.spec_values(sew)
        p.require(result['status']=='REFERENCE_CHECKER_PASS_NOT_DUT' and result['pins_unchanged'] and
                  type(execution['actual_wait_returncode']) is int and execution['actual_wait_returncode']==0 and
                  not execution['timeout'] and execution['elapsed_s']<=120 and execution['raw_bytes']<256*1024**2 and
                  result['commits']<1500000 and result['scalar_checks']==cfg['checks'] and
                  result['helper_entries']==result['target_attempts']==1 and result['htif']==[1], 'Complete two references')
        p.require(p.sha(result['raw_path'])==result['raw_sha256'],'Original raw identity')
        proof=p.read(software/'source_proof.json')
        for backend in ('soc','spike'):
            p.require(p.sha(software/(backend+'.elf'))==proof['backend'][backend]['sha256'],'Final ELF identity')
        cases.append(dict(sew=sew,scenario=p.CASES[sew]['scenario'],original_name=p.CASES[sew]['name'],
                          source_proof=str(software/'source_proof.json'),source_proof_sha256=p.sha(software/'source_proof.json'),
                          soc_elf=str(software/'soc.elf'),soc_elf_sha256=p.sha(software/'soc.elf'),
                          spike_elf=str(software/'spike.elf'),spike_elf_sha256=p.sha(software/'spike.elf'),
                          reference_result=str(r/'status.json'),reference_result_sha256=p.sha(r/'status.json'),
                          actual_wait_returncode=0,firmware_records=result['firmware_commits'],
                          scalar_checks=result['scalar_checks'],raw_path=result['raw_path'],raw_sha256=result['raw_sha256'],
                          original_helper_instructions=11,capacity_instructions=3,
                          physical_output_elements=130,physical_mask_bytes=16,source_words=4,
                          undefined_final_output_indices=[5,6,7,8] if sew==8 else []))
    files=[f for f in p.HERE.rglob('*') if f.is_file() and '__pycache__' not in f.parts]
    pins={**external,**{str(f):p.sha(f) for f in files}}
    p.verify(pins)
    p.save(p.HERE/'READY.json',dict(status='HOST_REFERENCE_EXECUTOR_PASS_PENDING_REVIEW_NOT_DUT',cases=cases,
        actual_isa=p.ISA,reference_invocations=2,reference_invocations_per_case=1,no_reference_retry=True,
        bound=dict(instructions=1500000,seconds=120,raw_bytes=256*1024**2),
        original_e8_checker_error_preserved=True,successor_checker=str(p.HERE/'recovery01/observer.py'),
        source_cases=2,original8_ELF_closure=False,Linux_signal_equivalence=False,
        no_RTL_edit=True,no_RTL_build=True,no_DUT_launch=True,pins=pins,pin_count=len(pins),
        independent_review_pending=True,main_review_before_any_DUT=True))
    print('READY',p.sha(p.HERE/'READY.json'),'pins',len(pins),flush=True)

if __name__=='__main__':main()
