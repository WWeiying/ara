#!/usr/bin/env python3
"""Freeze existing accepted reference metadata; never execute or reparse it."""
import sys
sys.dont_write_bytecode=True
import prepare as p

def main():
    r=p.HERE/'reference01';status=p.read(r/'status.json');execution=p.read(r/'execution.json')
    p.require(status['status']=='REFERENCE_CHECKER_PASS_NOT_DUT' and execution['returncode']==0 and
              not execution['timeout'] and p.read(r/'wrapper_wait.json')['actual_wait_exit_code']==0,'Terminal evidence')
    p.require(0<status['firmware_commits']<1500000 and status['scalar_checks']==17275 and
              len(status['retry_mrets'])==1 and status['htif']==[1],'Exact scope')
    p.require([x['values'] for x in status['targets']]==[[127],[166]] and
              status['traps'][0][0]=='trap_store_page_fault','Not accepted store reference')
    pins=p.read(r/'input_pins.json');p.checkpins(pins)
    p.require(p.sha(r/'spike.trace')==status['raw_sha256'],'Raw drift')
    own={str(f):p.sha(f) for f in p.HERE.rglob('*') if f.is_file() and f.name!='READY.json'}
    pins.update(own);p.checkpins(pins)
    ready=dict(status='PREPARED_HOST_REFERENCE_PASS_PENDING_INDEPENDENT_REVIEW_NOT_DUT',
               source_name=p.NAME,reference_invocations=1,source_cases=1,parent96_accepted=False,
               linux_signal_equivalence=False,host_negative_controls=p.read(p.HERE/'host_final01.json')['negative_count'],
               firmware_commit_format_records=status['firmware_commits'],scalar_checks=17275,
               original_helper_instructions=10,original_helper_entries=1,target_attempts=2,
               spike_helper_records_including_partial_fault=11,
               full_oracle=dict(output_elements=64,guards=2,memory_bytes=8192,
                                checkpoints=4,refill_halfwords=2048,prefix_before_repair=127,
                                prefix_poison=36,retry_store=166),
               axi_b_channel_measured=False,
               soc_elf=str(p.OUT/'soc.elf'),soc_elf_sha256=p.sha(p.OUT/'soc.elf'),
               spike_elf_sha256=p.sha(p.OUT/'spike.elf'),
               source_proof_sha256=p.sha(p.OUT/'source_proof.json'),
               reference_result_sha256=p.sha(r/'status.json'),
               execution_sha256=p.sha(r/'execution.json'),
               pins=pins,pin_count=len(pins),pins_unchanged=True,
               no_reference_retry=True,no_DUT_launch=True,no_RTL_or_image_build=True)
    p.save(p.HERE/'READY.json',ready)
    print('READY',p.sha(p.HERE/'READY.json'),'pins',len(pins),'NO_DUT')

if __name__=='__main__':main()
