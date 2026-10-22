#!/usr/bin/env python3
"""Prepare one authentic e8/m4/op3 prefix; host and bounded Spike only."""
import difflib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT.parent))
import prepare_batch as base
import prepare_stall_prefix2 as old
from audit_accepted8 import instructions, archived_window, OBJDUMP
from prepare_successor import SPIKE, symbol
from reference_check import NAME, model, audit_trace, require, prefix
from scope import *

C = base.CAMPAIGN
PART = C/'rvv_permute_partitions01'
ORIGINAL = SOURCE_LABEL
SOURCE = C/'rvv_small_gather02/rvv_small_gather_restart_e16_m1_ops0/original.c'
EXPECTED_ELF = ORIGINAL_ELF_SHA
MAX_LOG = FILE_BYTES


def save(path, value):
    require(not path.exists(), 'No overwrite: '+str(path))
    base.save(path,value)


def host_shim(gold):
    array = old.array
    arrays = array('gold_data',gold['input'],'uint8_t')
    arrays += array('gold_indices',gold['indices'],'uint8_t')
    arrays += array('gold_indices16',gold['indices16'],'uint16_t')
    arrays += array('gold_vl',[r['vl'] for r in gold['rows']],'unsigned long')
    arrays += array('gold_start',[r['vstart'] for r in gold['rows']],'unsigned long')
    arrays += array('gold_masks',[v for r in gold['rows'] for v in r['predicate']])
    arrays += array('gold_output',[v for r in gold['rows'] for v in r['output']],'uint8_t')
    text = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
FIXTURE
#define CAPACITY 512
#define MASK_STORAGE 128
#define CALL_BOUND 66
extern const uint16_t *host_indices16(void);
static unsigned calls, injected;
static const char *negative="none";
static void demand(int x) { if(!x)exit(90); }
unsigned long capacity(void) { return CAPACITY; }
long replay_write(long n,long fd,long ptr,long len) {
  demand(n==64 && fd==1 && len>=0);
  return (long)fwrite((const void *)ptr,1,(size_t)len,stdout);
}
static unsigned long mock(unsigned op,const void *a,const void *b,void *c,
    unsigned long vl,unsigned long cap,const void *m,unsigned long scalar,unsigned long start) {
  demand(op==3 && calls<CALL_BOUND && cap==CAPACITY && scalar==0);
  unsigned j=calls++;
  demand(vl==gold_vl[j] && start==gold_start[j]);
  demand(!memcmp(a,gold_data,CAPACITY) && !memcmp(b,gold_indices,CAPACITY));
  demand(!memcmp(host_indices16(),gold_indices16,CAPACITY*sizeof(uint16_t)));
  demand(!memcmp(m,gold_masks+j*MASK_STORAGE,MASK_STORAGE));
  uint8_t *d=c;
  demand(d[-1]==91 && d[CAPACITY]==91);
  for(unsigned i=0;i<CAPACITY;++i)demand(d[i]==91);
  memcpy(d,gold_output+j*CAPACITY,CAPACITY);
  if(!injected && strcmp(negative,"none")) {
    long at=-2;
    if(!strcmp(negative,"guard0"))at=-1;
    if(!strcmp(negative,"guard1"))at=CAPACITY;
    if(!strcmp(negative,"prestart") && start && start<vl)at=0;
    if(!strcmp(negative,"tail") && start<vl && vl<CAPACITY)at=(long)vl;
    if(!strcmp(negative,"active") || !strcmp(negative,"inactive"))
      for(unsigned i=(unsigned)start;i<vl;++i) {
        int pick=(((const unsigned char *)m)[i/8]>>(i%8))&1;
        if((pick && !strcmp(negative,"active")) || (!pick && !strcmp(negative,"inactive"))) {
          at=(long)i; break;
        }
      }
    if(!strcmp(negative,"vstart")) { injected=1; return 1; }
    if(at>=-1) { d[at]^=1; injected=1; }
  }
  return 0;
}
FUNCTIONS
extern int IDENTITY_main(void);
int main(int argc,char **argv) {
  if(argc==2)negative=argv[1];
  int rc=IDENTITY_main();
  demand(calls==CALL_BOUND && (!strcmp(negative,"none") || injected));
  printf("HOST_PREFIX_CALLS=%u INJECTED=%u\n",calls,injected);
  return rc;
}
'''
    funcs = '\n'.join('unsigned long op_%d(const void *a,const void *b,void *c,unsigned long d,'
        'unsigned long e,const void *f,unsigned long g,unsigned long h){return mock(%d,a,b,c,d,e,f,g,h);}'
        % (i,i) for i in range(21))
    text = text.replace('#define CAPACITY 512', '#define CAPACITY '+str(CAP))
    text = text.replace('#define MASK_STORAGE 128', '#define MASK_STORAGE '+str(PREDICATE_BYTES))
    text = text.replace('#define CALL_BOUND 66', '#define CALL_BOUND '+str(BOUND))
    return text.replace('FIXTURE',arrays).replace('FUNCTIONS',funcs).replace('IDENTITY',NAME)


def host_check(prepared, gold):
    folder=OUT/'host'
    folder.mkdir()
    source=(prepared/NAME/'case.c').read_text()
    csr='__asm__ volatile("csrr %0,vlenb":"=r"(max_start));'
    require(source.count(csr)==1,'Host vlenb adaptation drift')
    (folder/'original_host.c').write_text(source.replace(csr,'max_start='+str(VLENB)+';')+
        '\nconst uint16_t *host_indices16(void) { return indices16; }\n')
    (folder/'shim.c').write_text(host_shim(gold))
    cc=Path('/usr/bin/gcc').resolve(strict=True)
    command=[str(cc),'-std=c99','-O2','-Wall','-Wextra','-Werror','-fno-tree-vectorize',
        '-DSEW=8','-DRESTART_PERMUTATIONS=1','-DPERMUTE_OP_MASK=8',
        '-I'+str(prepared/NAME/'original'),str(folder/'original_host.c'),str(folder/'shim.c'),
        '-o',str(folder/'prefix.host')]
    with (folder/'compile.log').open('x') as stream:
        subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=30)
    tests=[]
    for injection in ('none','active','prestart','inactive','tail','guard0','guard1','vstart'):
        run=subprocess.run([str(folder/'prefix.host'),injection],capture_output=True,text=True,timeout=15)
        log=folder/(injection+'.log')
        log.write_text(run.stdout+run.stderr)
        rc=0 if injection=='none' else 1
        marker='RVV_GATHER_PREFIX_'+('PASS' if rc==0 else 'FAIL')+' sew=8 cases=66 errors='
        require(run.returncode==rc and marker in run.stdout and 'HOST_PREFIX_CALLS=66' in run.stdout,
                'Host oracle did not detect injection '+injection)
        tests.append(dict(injection=injection,status='PASS',returncode=run.returncode,log_sha256=base.sha(log)))
    save(folder/'host_gate.json',dict(status='HOST_ONE_POSITIVE_SEVEN_NEGATIVES_PASS',tests=tests,
        command=command,compiler_sha256=base.sha(cc),scope='Original C oracle with independent Python setup/result fixtures'))


def static_validate(source, assembly):
    require(base.sha(SOURCE)==ORIGINAL_C_SHA, 'Original source hash drift')
    for declaration in ('static word input[1024],indices[1024],output[1026];',
                        'static uint16_t indices16[1024];',
                        'static uint8_t predicate[128];'):
        require(declaration in source, 'Physical source storage differs')
    require('for(unsigned i=0;i<128;++i)predicate[i]=0;' in source,
            'Original complete predicate clear missing')
    require('vsetvli a0,t0,e8,m4,tu,mu' in assembly, 'Capacity shape wrong')
    require(assembly.count('vrgather.vi v24,v8,31,v0.t')==1, 'Original VI31 helper missing')
    require(base.sha(PART/ORIGINAL/'operations.S')==ASSEMBLY_SHA, 'Original assembly drift')
    require(SETUP_VALUES==2178 and RESULT_CHECKS==33792 and GUARD_CHECKS==132
            and HELPER_INSTRUCTIONS==858 and ORACLE_LOADS==33924, 'Scope constants wrong')
    adapted_probe=prefix(source,BOUND)
    before=source[source.index('    for(unsigned seed='):source.index('            ++cases;\n')]
    after=adapted_probe[adapted_probe.index('    for(unsigned seed='):
                        adapted_probe.index('            ++cases;\n')]
    require(before==after, 'Original loops/RNG/setup/oracle changed')
    require('syscall3(94,errors ? 1:0,0,0);for(;;){}' in adapted_probe, 'Original exit lost')
    return dict(status='STATIC_ORIGINAL_LOOP_INSERTION_ONLY',
                unselected_loops_shortened=False, empty_enumeration_iterations_retained=True,
                physical_predicate_bytes=PREDICATE_BYTES, logical_mask_bytes=CAP//8,
                initialized_input_indices_elements=CAP, unused_static_array_tails_audited=False)


def original_rebuild(original):
    folder=OUT/'original_linux_rebuild'
    folder.mkdir()
    gcc=(base.ROOT/'install/riscv-gcc/bin/riscv64-unknown-elf-gcc').resolve(strict=True)
    rebuilt=folder/(SOURCE_LABEL+'.elf')
    command=[str(gcc),'-Os','-march=rv64gcv','-mabi=lp64d','-nostdlib','-static',
        '-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-tree-vectorize',
        '-fno-tree-slp-vectorize','-msmall-data-limit=0','-Wl,--build-id=none','-Wl,-s',
        '-Wall','-Wextra','-Werror','-DSEW=8','-DRESTART_PERMUTATIONS=1',
        '-I'+str(original),'-DPERMUTE_OP_MASK=8',
        str(original/'scenario.c'),str(original/'operations.S'),'-o',str(rebuilt)]
    with (folder/'compile.log').open('x') as stream:
        subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=30)
    equal=base.sha(rebuilt)==EXPECTED_ELF
    readelf=gcc.with_name(gcc.name.replace('gcc','readelf'))
    comments={}
    for label,p in [('archive',original/'original_linux.elf'),('rebuilt',rebuilt)]:
        comments[label]=subprocess.check_output([str(readelf),'-p','.comment',str(p)],text=True)
    proof=dict(status='PRE_ADAPTER_UNMODIFIED_SOURCE_BINARY_COMPARISON',
        original_linux_elf_sha256=EXPECTED_ELF, rebuilt_sha256=base.sha(rebuilt),
        entire_original_linux_binary_rebuild_proven=equal, command=command,
        compiler=str(gcc),compiler_sha256=base.sha(gcc),compiler_comments=comments,
        claim='BYTE_IDENTICAL' if equal else 'NOT_BYTE_IDENTICAL_NO_BINARY_EQUIVALENCE_CLAIM',
        source_and_original_assembly_unchanged=True, completed_before_adapter=True)
    save(OUT/'pre_adapter_binary_proof.json',proof)
    return proof


def main():
    require(not (OUT/'prepared').exists() and not (OUT/'preparation_error.json').exists(),
            'Fresh preparation only; no retries or overwrite')
    os.environ['CCACHE_DISABLE']='1'
    from test_prepare import validate
    source=SOURCE.read_text()
    assembly=(PART/ORIGINAL/'operations.S').read_text()
    static=static_validate(source,assembly)
    tests=validate(source)
    save(OUT/'static_validation.json',dict(**static,tests=tests))
    manifest=old.read(PART/'manifest.json')
    case,=[x for x in manifest['cases'] if x['name']==ORIGINAL]
    record,=[x for x in old.read(C/'stall_family_triage02/triage.json')['cases'] if x['name']==ORIGINAL]
    require(case['sew']==SEW and case['lmul']==LMUL and case['operation_ids']==[3]
            and case['configurations']==2688 and case['sha256']==EXPECTED_ELF==record['elf_sha256'],
            'Wrong authentic source child')
    require(manifest['source_sha256']['permutation_oracle.c']==ORIGINAL_C_SHA,
            'Archived source manifest identity')
    report=Path(record['report'])
    original_elf=PART/'release/binaries'/ORIGINAL
    require(record['last_trial'] is None and base.sha(report)==record['report_sha256']
            and base.sha(original_elf)==base.sha(report.parent/ORIGINAL)==EXPECTED_ELF,
            'Original archived scene/ELF differs')
    baseline_files=[SOURCE,original_elf,report,report.parent/ORIGINAL,
        PART/'manifest.json',PART/'parent_mapping.json',C/'stall_family_triage02/triage.json',
        PART/ORIGINAL/'operations.S',PART/ORIGINAL/'operations.h',
        OUT.parent/'gather_recovery168_tuple_dedup01.md',
        OUT.parent/'gather_unknown_stall_recovery01.md',
        OUT.parent/'prepare_batch.py',OUT.parent/'audit_accepted8.py',
        OUT.parent/'prepare_successor.py',OUT.parent/'prepare_stall_prefix2.py',
        OUT.parent/'e8_m8_ops3_prefix66_prepare01/prepare_prefix.py',
        OUT.parent/'e8_m8_ops3_prefix66_prepare01/reference_check.py',
        OUT.parent/'stall_prefix2_03/reference/reference.json',
        OUT.parent/'stall_prefix2_03/gather_prefix_e8_m4_ops1.host_expected.json',
        base.INTEGRATION/'prepare.py',SPIKE,
        (base.ROOT/'install/riscv-gcc/bin/riscv64-unknown-elf-gcc').resolve(strict=True)]
    baseline_files += [base.INTEGRATION/f for f in ('runtime.c','startup.S','replay.ld')]
    baseline_files += [OUT/f for f in ('prepare_prefix.py','reference_check.py','scope.py','test_prepare.py')]
    pins={str(p):base.sha(p) for p in baseline_files}
    save(OUT/'baseline_pins.json',pins)
    prepared=OUT/'prepared'
    original=prepared/NAME/'original'
    original.mkdir(parents=True)
    shutil.copyfile(SOURCE,original/'scenario.c')
    for f in ('operations.S','operations.h'):
        shutil.copyfile(PART/ORIGINAL/f,original/f)
    shutil.copyfile(original_elf,original/'original_linux.elf')
    save(original/'case.json',dict(source_label=SOURCE_LABEL,case=case,archived_stall=record))
    binary=original_rebuild(original)
    sys.path.insert(0,str(base.INTEGRATION))
    from prepare import adapt
    adapted=adapt(source,NAME)
    port=prefix(adapted,BOUND)
    start='    for(unsigned seed='
    anchor='            ++cases;\n'
    require(adapted[adapted.index(start):adapted.index(anchor)+len(anchor)]==
            port[port.index(start):port.index(anchor)+len(anchor)],
            'Original loops/setup/oracle/statistics changed')
    (prepared/NAME/'case.c').write_text(port)
    diffdir=OUT/'source_diffs'
    diffdir.mkdir()
    for label,before,after in [('adapter',source,adapted),('prefix',adapted,port)]:
        (diffdir/(label+'.diff')).write_text(''.join(difflib.unified_diff(
            before.splitlines(True),after.splitlines(True),fromfile=label+'_before',tofile=label+'_after')))
    for f in ('runtime.c','startup.S','replay.ld'):
        shutil.copyfile(base.INTEGRATION/f,prepared/f)
    gold=model()
    save(OUT/'host_expected.json',gold)
    scope=dict(source_label=SOURCE_LABEL,runtime_id=NAME,sew=SEW,lmul=LMUL,
        vlenb=VLENB,capacity=CAP,calls=BOUND,predecessors=BOUND-1,endpoint=ENDPOINT,
        ordered_tuples=[r['tuple'] for r in gold['rows']],
        physical_predicate_bytes=PREDICATE_BYTES,logical_mask_bytes=CAP//8,
        setup_values_per_call=SETUP_VALUES,setup_bytes_per_call=SETUP_BYTES,
        fullcap_results=RESULT_CHECKS,guards=GUARD_CHECKS,oracle_loads=ORACLE_LOADS,
        helper_instruction_count=HELPER_INSTRUCTIONS,
        entire_original_linux_binary_rebuild_proven=binary['entire_original_linux_binary_rebuild_proven'],
        binary_proof_sha256=base.sha(OUT/'pre_adapter_binary_proof.json'),
        original_stopped_tuple=None,exact_historical_stall_reproduction=False,
        linux_execution=False,full2688_child=False,no_DUT=True)
    save(OUT/'scope.json',scope)
    spec=dict(id=NAME,source_label=SOURCE_LABEL,operation=3,assembly='operations.S',
        original_case=case,original_linux_elf_sha256=EXPECTED_ELF,
        defines=['SEW=8','RESTART_PERMUTATIONS=1','PERMUTE_OP_MASK=8'],
        pass_markers=[f'BOARD_CASE_PASS {NAME}','BOARD_REPLAY_PASS',
                      'RVV_GATHER_PREFIX_PASS sew=8 cases=66 errors=0'])
    provenance=dict(cases=[spec],vlen=1024,nr_lanes=4,
        scope='Original first66 calls; returned numeric scope, not unknown stall/Linux/fullchild',
        source_label=SOURCE_LABEL,runtime_id=NAME,
        files={str(p.relative_to(prepared)):base.sha(p) for p in prepared.rglob('*') if p.is_file()})
    save(prepared/'provenance.json',provenance)
    print('STATIC_VALIDATED; pre-adapter byte-identical='+str(binary['entire_original_linux_binary_rebuild_proven']),flush=True)
    host_check(prepared,gold)
    base.HERE=OUT
    soc=base.build(prepared,provenance,'soc')[NAME]
    spike=base.build(prepared,provenance,'spike')[NAME]
    routine=instructions(Path(soc['path']),NAME+'_op_3')
    archived=archived_window(original/'original_linux.elf',routine)
    spike_routine=instructions(Path(spike['path']),NAME+'_op_3')
    require(len(routine)==13 and [r['insn'] for r in routine]==[r['insn'] for r in spike_routine],
            'All13 original assembly encodings differ')
    require(archived[8]['pc']==record['last_pc']==0x1063e and routine[8]['insn']=='308fbc57'
            and 'e8,m4' in routine[0]['text'], 'Archived target PC/shape/opcode drift')
    proof=dict(status='ORIGINAL_SOURCE_AND13_ASM_VERIFIED',source_label=SOURCE_LABEL,runtime_id=NAME,
        original_c_sha256=base.sha(SOURCE),original_linux_elf_sha256=EXPECTED_ELF,
        soc_elf=soc,spike_elf=spike,original_routine=archived,
        soc_routine=routine,spike_routine=spike_routine,
        entire_original_linux_binary_rebuild_proven=binary['entire_original_linux_binary_rebuild_proven'],
        original_stopped_tuple=None)
    save(OUT/'source_elf_proof.json',proof)
    reference=OUT/'reference'
    reference.mkdir()
    logaddr,_=symbol(Path(spike['path']),'replay_log',OBJDUMP)
    debug=reference/'spike.cmd'
    debug.write_text(f'rs {MAX_RETIRED}\nstr {logaddr:x}\nquit\n')
    command=[str(SPIKE),'-d','--debug-cmd='+str(debug),'--isa=rv64gcv_zvl1024b','-m2',
        '--log-commits','--log='+str(reference/'commits.log'),spike['path']]
    limits=dict(seconds=WALL_SECONDS,instructions=MAX_RETIRED,file_bytes=FILE_BYTES,
                comparable_cap512_reference='stall_prefix2_03/reference/reference.json',
                comparable_retired=[2148472,2280966],comparable_calls=98,
                claim='fixed budget, not DUT runtime prediction')
    save(reference/'command.json',dict(command=command,**limits))
    def limit_log():
        resource.setrlimit(resource.RLIMIT_FSIZE,(FILE_BYTES,FILE_BYTES))
    print('HOST8_PASS + BOTH_ELFS13_ASM_MATCH; SPIKE_ONCE_START',flush=True)
    begin=time.monotonic()
    with (reference/'spike.log').open('x') as stream:
        run=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,
            timeout=WALL_SECONDS,preexec_fn=limit_log)
    elapsed=time.monotonic()-begin
    save(reference/'execution.json',dict(returncode=run.returncode,elapsed_s=elapsed,command=command,
        retries=0,spike_launches=1,validated=False))
    require(run.returncode==0,'Spike actual nonzero')
    require((reference/'commits.log').stat().st_size<FILE_BYTES,'Raw file bound exhausted')
    audit_begin=time.monotonic()
    measured=audit_trace(reference/'commits.log',Path(spike['path']),gold)
    audit_seconds=time.monotonic()-audit_begin
    (reference/'runtime.log').write_text(measured['reconstructed_console'])
    save(reference/'reference.json',dict(**measured,elapsed_s=elapsed,returncode=run.returncode,
        raw_audit_seconds=audit_seconds,source_label=SOURCE_LABEL,runtime_id=NAME,
        spike_sha256=base.sha(SPIKE),commit_sha256=base.sha(reference/'commits.log'),
        commit_bytes=(reference/'commits.log').stat().st_size,limits=limits,retries=0))
    for p,digest in pins.items():
        require(base.sha(Path(p))==digest,'Baseline changed: '+p)
    ready=dict(status='ACCEPTED_SOURCE_REFERENCE_ONLY_NOT_DUT',**scope,
        soc_elf=soc,spike_elf=spike,source_proof_sha256=base.sha(OUT/'source_elf_proof.json'),
        reference_sha256=base.sha(reference/'reference.json'),
        actual_firmware_retired=measured['firmware_retired_to_htif_store'],
        actual_spike_elapsed_s=elapsed,actual_reference_raw_bytes=(reference/'commits.log').stat().st_size,
        actual_vlenb=VLENB,actual_capacity=CAP,host_positive=1,host_negative=7,
        baseline_pins_unchanged=True,raw_reference_parses=1,spike_launches=1,
        no_VCS=True,no_RTL=True)
    ready['pins']={str(p):base.sha(p) for p in sorted(OUT.rglob('*'))
                   if p.is_file() and p.name!='READY.json'}
    save(OUT/'READY.json',ready)
    print(ready['status'],json.dumps({k:ready[k] for k in
        ['actual_firmware_retired','actual_spike_elapsed_s','actual_reference_raw_bytes']}),flush=True)


if __name__=='__main__':
    try:
        main()
    except Exception as error:
        if not (OUT/'preparation_error.json').exists():
            save(OUT/'preparation_error.json',dict(status='PREPARATION_STOPPED_NOT_DUT',
                error=repr(error),retry=False))
        raise

