#!/usr/bin/env python3
"""Prepare one exact FP32 entry and short synthetic tests; never run Spike."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
SOFTWARE=ROOT/'software01'


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def main():
    gen=load('fp32_generator_definition',SOFTWARE/'generate.py')
    sha,save,require=gen.sha,gen.save,gen.require
    require(not(HERE/'spec.json').exists() and not(HERE/'ENTRY.json').exists(),'Exclusive entry preparation')
    review=ROOT/'source_review01/LINKED_RESULT_REVIEW.json'
    require(sha(review)=='6162b716aa243ac5f5ffba3b15c622436a7ca863d08d8859db5b479bab710946','Actual independent artifact acceptance')
    actual=json.loads(review.read_text())
    require(actual['status']=='ACCEPT_COMPILED_CONDITIONAL_COST_LT_3M' and not actual['blockers'],'Artifact/cost decision')
    parser=load('sealed_disassembly_reader',ROOT.parent/'fp_compare_unboxed_full17920_prepare01/compile01/inspect_linked.py')
    parser.RUN=SOFTWARE/'execution01'
    d,code,func,sym,sizes=parser.parse('spike')
    require(sha(d/'program.elf')=='9b6f3e8fa391514816fc6731aeb8b9628d374fbe5f0e1ccb85fb6a2e929e1254','Exact new FP32 ELF')
    lower=json.loads((SOFTWARE/'linked_cfg01/spike.json').read_text())
    require(lower['whole_positive_upper']<3000000 and lower['all_body_PCs_partitioned'],'Complete accepted positive cost')
    opaque=[]
    for name in (gen.NAME+'_main','main'):
        for row in func[name]:
            if row['op']=='jal':break
            if row['op']=='sd' and '(sp)' in row['args'] and row['args'].split(',')[0] not in ('ra','zero'):
                opaque.append(row['pc'])
    failures={int(p,16) for p in lower['zero_positive_execution_PCs']}
    # Actual wrapper capacity/case/service failure branches, not old FP16 PCs.
    for lo,hi in [(0x80000054,0x80000064),(0x80000768,0x80000774),
                  (0x80000796,0x800007a4),(0x80000854,0x80000868)]:
        failures.update(p for p in code if lo<=p<=hi)
    failures.update(r['pc'] for r in func['replay_trap'])
    prelude=[r['pc'] for name in ('_start','main') for r in func[name]
             if int(r['insn'],16)&127==0x73 and (int(r['insn'],16)>>12)&7]
    require(len(prelude)==6 and prelude[-1]==0x8000075c,'Actual six bootstrap CSR sites')
    spec=dict(elf=str(d/'program.elf'),elf_sha256=sha(d/'program.elf'),symbols=sym,sizes=sizes,
         code=code,helpers=[func['op_'+str(i)] for i in range(10)],capacity=func['capacity'],
         stores=lower['fresh_stores'],input_loads=lower['input_LD_sites'],
         record_load=0x800003f2,output_read=0x8000026e,caller_record_check=0x80000260,
         caller_flags_check=0x8000026a,exit_store=0x8000007a,park=0x8000007e,
         prelude=prelude,opaque_initial_spills=opaque,failure_pcs=sorted(failures),
         BSS_bytes=sym['__bss_end']-sym['__bss_start'],SEW=32,capacity_elements=16,
         vtype=23,physical_group=1,input_bytes=64,input_backing_bytes=4096,
         mask_bytes=128,output_initialized_bytes=130,output_oracle_bytes=4,
         expected_helper_memory_instructions=89600,expected_nonempty_targets=15360,
         owner_scope='Reference helper instruction qualification, not DUT request/completion trace')
    from checker import elf_image,word,DECODER
    image=elf_image(d/'program.elf')
    for pc,row in code.items():require(word(image,pc,len(row['insn'])//2)==int(row['insn'],16),'Full code/ELF equality')
    require(code[spec['caller_record_check']]['text']=='ld t0,56(sp)' and
            code[spec['caller_flags_check']]['text']=='or a4,a4,t0','Actual live ABI check sites')
    require(code[spec['exit_store']]['text']=='sd a0,0(t0)' and code[spec['park']]['insn']=='a001','Actual finite endpoint/pure park')
    save(HERE/'spec.json',spec)
    pins=json.loads((SOFTWARE/'linked_cfg01/inputs_after.json').read_text())
    pins.update(json.loads((SOFTWARE/'generated01/artifact_pins.json').read_text()))
    pins.update(json.loads((SOFTWARE/'generated01/inputs_after.json').read_text()))
    spike=Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
    for p in [review,SOFTWARE/'READY.json',SOFTWARE/'REPORT.md',DECODER,HERE/'spec.json',spike,*HERE.glob('*.py')]:
        pins[str(p)]=sha(p)
    prior=ROOT.parent/'fp_compare_unboxed_full17920_prepare01/reference_entry02'
    for name in ('checker.py','execute_once.py','audit_once.py','test_checker.py'):
        pins[str(prior/name)]=sha(prior/name)
    pins[str(HERE/'README.md')]=sha(HERE/'README.md')
    require(all(sha(Path(p))==h for p,h in pins.items()),'Fresh reviewed source/tool identity')
    command=[sys.executable,'-B',str(HERE/'test_checker.py')]
    save(HERE/'host.command.json',command)
    t=time.monotonic()
    with (HERE/'host.log').open('x') as log:
        p=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
        try:rc=p.wait(timeout=120);timed=False
        except subprocess.TimeoutExpired:p.kill();rc=p.wait();timed=True
    save(HERE/'host.wait.json',dict(actual_wait_exit=rc,timed_out=timed,elapsed_s=time.monotonic()-t,
                                   log_sha256=sha(HERE/'host.log')))
    require(type(rc) is int and rc==0 and not timed,'Short checker Host failure; preserve and stop')
    for p in [HERE/'host.command.json',HERE/'host.log',HERE/'host.wait.json']:
        pins[str(p)]=sha(p)
    require(all(sha(Path(p))==h for p,h in pins.items()),'Entry preparation input drift')
    save(HERE/'input_pins.json',pins)
    save(HERE/'ENTRY.json',dict(status='PREPARED_FP32_ENTRY_PENDING_AVERROES_AND_SEPARATE_PARENT_ADMISSION',
         input_pins_sha256=sha(HERE/'input_pins.json'),spec_sha256=sha(HERE/'spec.json'),
         checker_sha256=sha(HERE/'checker.py'),host_wait_sha256=sha(HERE/'host.wait.json'),
         reference_executor_sha256=sha(HERE/'execute_once.py'),spike=str(spike),isa='rv64gcv_zfh_zvfh_zvl1024b',
         debug_command='rs 4000000\nquit\n',reference_seconds=120,raw_limit_bytes=768*1024*1024,
         audit_seconds=600,firmware_limit=3000000,unique_reference_attempt=True,unique_closed_raw_audit=True,
         retry=False,automatic_VCS=False,reference_executed=False,DUT_executed=False,
         scope=dict(calls=17920,result_bits=286720,guard_values=35840,flags=17920,vstarts=17920,
                    helpers=326144,capacity_instructions=3,fresh_stores=878080,input_LD=286720,
                    output_LWU=17920,record_LD=2240,raw_FPR_moves=10752),
         launch_gate='Averroes exact entry NO_BLOCKER plus separate parent reference authorization; neither currently supplied',
         command='python3 -B '+str(HERE/'execute_once.py')+' --review ACTUAL_REVIEW_JSON --review-sha256 ACTUAL_SHA --parent-authorization ACTUAL_PARENT_JSON --parent-authorization-sha256 ACTUAL_PARENT_SHA'))
    print('FP32_REFERENCE_ENTRY_PREPARED_NOT_EXECUTED',sha(HERE/'ENTRY.json'),flush=True)


if __name__=='__main__':main()
