#!/usr/bin/env python3
"""Metadata/hash-only finalization; never reference/DUT execution or raw reparse."""
import sys
sys.dont_write_bytecode=True
import prepare as p
from newscope import CAP,LMUL,CHECKS

def main():
    h=p.HERE;r=h/'reference01';s=p.read(r/'status.json');e=p.read(r/'execution.json')
    p.require(s['status']=='REFERENCE_CHECKER_PASS_NOT_DUT' and s['pins_unchanged'],'Reference status')
    p.require(e['returncode']==0 and not e['timeout'] and e['elapsed_s']<=120,'Actual child wait')
    p.require(p.read(r/'executor_wait.json')['observed_executor_wait_exit_code']==0,'Actual executor wait')
    for k,v in dict(cases=16,faults=12,scalar_checks=CHECKS,
                    helper_entries=16,output_elements=16*CAP,output_guards=32,memory_words=16384,returned_vstart=16).items():
        p.require(s[k]==v,'Incomplete original scope '+k)
    p.require(len(s['checkpoints'])==72 and len(s['retry_mrets'])==12 and s['refills']==list(range(8,16)),'Ledger')
    pins=p.read(r/'input_pins.json');p.pinscheck(pins)
    p.require(p.sha(r/'spike.trace')==s['raw_sha256'],'Raw drift')
    pins.update({str(f):p.sha(f) for f in h.rglob('*') if f.is_file() and '__pycache__' not in f.parts})
    p.save(h/'evidence_pins.json',pins);p.pinscheck(pins)
    ready=dict(status='SOURCE_AND_REFERENCE_READY_NOT_DUT',independent_agent_acceptance=False,
      original_name=p.NAME,scope=dict(cases=16,continuous=True,cap=CAP,vl=8,sew=64,lmul=LMUL,
        faults=12,output_elements=1024,output_guards=32,memory_words=16384,returned_vstart=16),
      soc_elf=str(p.OUT/'soc.elf'),soc_elf_sha256=p.sha(p.OUT/'soc.elf'),
      spike_elf=str(p.OUT/'spike.elf'),spike_elf_sha256=p.sha(p.OUT/'spike.elf'),
      reference_status=str(r/'status.json'),reference_status_sha256=p.sha(r/'status.json'),
      execution_sha256=p.sha(r/'execution.json'),actual_child_returncode=0,executor_wait_exit_code=0,
      firmware_instructions=s['firmware_commits'],reference_seconds=e['elapsed_s'],
      scalar_checks=s['scalar_checks'],host=p.read(p.OUT/'host_tests.json'),
      evidence_pins=str(h/'evidence_pins.json'),evidence_pins_sha256=p.sha(h/'evidence_pins.json'),pin_count=len(pins),
      future_dut_image='/home/wangwy/fpga_runs/current_board_memory_candidate07/campaign/image',
      current_worktree_is_not_image_snapshot=True,linux_signal_equivalence=False,historical_linux_stall_closed=False,
      dut_launched=False,rtl_modified=False)
    p.save(h/'READY.json',ready)
    print(dict(status=ready['status'],pins=len(pins),ready_sha256=p.sha(h/'READY.json'),
               reference_status_sha256=ready['reference_status_sha256'],soc_elf_sha256=ready['soc_elf_sha256']))
if __name__=='__main__':main()

