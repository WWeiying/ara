#!/usr/bin/env python3
"""Prepare one authentic e8/m8/op3 prefix; host and bounded Spike only."""
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
from reference_check import NAME, model, audit_trace, require, MAX_RETIRED, prefix

C = base.CAMPAIGN
PART = C/'rvv_permute_partitions01'
ORIGINAL = 'rvv_permute_restart_e8_m8_ops3'
SOURCE = C/'rvv_small_gather02/rvv_small_gather_restart_e16_m1_ops0/original.c'
EXPECTED_ELF = 'ef3a7ff6d6dc48a7e5f20adbb7954490c08c7cbbdcd03afe9bbd4859dee7580c'
MAX_LOG = 768*1024*1024


def save(path, value):
    require(not path.exists(), 'No overwrite: '+str(path))
    base.save(path,value)


def host_shim(gold):
    array = old.array
    arrays = array('gold_data',gold['input'],'uint8_t')
    arrays += array('gold_indices',gold['indices'],'uint8_t')
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
static unsigned calls, injected;
static const char *negative="none";
static void demand(int x) { if(!x)exit(90); }
unsigned long capacity(void) { return 1024; }
long replay_write(long n,long fd,long ptr,long len) {
  demand(n==64 && fd==1 && len>=0);
  return (long)fwrite((const void *)ptr,1,(size_t)len,stdout);
}
static unsigned long mock(unsigned op,const void *a,const void *b,void *c,
    unsigned long vl,unsigned long cap,const void *m,unsigned long scalar,unsigned long start) {
  demand(op==3 && calls<66 && cap==1024 && scalar==0);
  unsigned j=calls++;
  demand(vl==gold_vl[j] && start==gold_start[j]);
  demand(!memcmp(a,gold_data,1024) && !memcmp(b,gold_indices,1024));
  demand(!memcmp(m,gold_masks+j*128,128));
  uint8_t *d=c;
  demand(d[-1]==91 && d[1024]==91);
  for(unsigned i=0;i<1024;++i)demand(d[i]==91);
  memcpy(d,gold_output+j*1024,1024);
  if(!injected && strcmp(negative,"none")) {
    long at=-2;
    if(!strcmp(negative,"guard0"))at=-1;
    if(!strcmp(negative,"guard1"))at=1024;
    if(!strcmp(negative,"prestart") && start && start<vl)at=0;
    if(!strcmp(negative,"tail") && start<vl && vl<1024)at=(long)vl;
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
  demand(calls==66 && (!strcmp(negative,"none") || injected));
  printf("HOST_PREFIX_CALLS=%u INJECTED=%u\n",calls,injected);
  return rc;
}
'''
    funcs = '\n'.join('unsigned long op_%d(const void *a,const void *b,void *c,unsigned long d,'
        'unsigned long e,const void *f,unsigned long g,unsigned long h){return mock(%d,a,b,c,d,e,f,g,h);}'
        % (i,i) for i in range(21))
    return text.replace('FIXTURE',arrays).replace('FUNCTIONS',funcs).replace('IDENTITY',NAME)


def host_check(prepared, gold):
    folder=OUT/'host'
    folder.mkdir()
    source=(prepared/NAME/'case.c').read_text()
    csr='__asm__ volatile("csrr %0,vlenb":"=r"(max_start));'
    require(source.count(csr)==1,'Host vlenb adaptation drift')
    (folder/'original_host.c').write_text(source.replace(csr,'max_start=128;'))
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


def main():
    require(not (OUT/'prepared').exists(),'Fresh preparation only; no retry/overwrite')
    os.environ['CCACHE_DISABLE']='1'
    manifest=old.read(PART/'manifest.json')
    case,=[x for x in manifest['cases'] if x['name']==ORIGINAL]
    record,=[x for x in old.read(C/'stall_family_triage02/triage.json')['cases'] if x['name']==ORIGINAL]
    require(case['sew']==8 and case['lmul']=='m8' and case['operation_ids']==[3] and
            case['configurations']==2688 and case['sha256']==EXPECTED_ELF==record['elf_sha256'],'Wrong source child')
    require(base.sha(SOURCE)==manifest['source_sha256']['permutation_oracle.c']==
            'b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca','Original C identity')
    report=Path(record['report'])
    require(base.sha(report)==record['report_sha256'] and record['last_trial'] is None,'Original report identity')
    original_elf=PART/'release/binaries'/ORIGINAL
    require(base.sha(original_elf)==base.sha(report.parent/ORIGINAL)==EXPECTED_ELF,'Original ELF/scene differs')
    old_ref=old.read(OUT.parent/'stall_prefix2_03/reference/reference.json')
    require(old_ref['spike_sha256']==base.sha(SPIKE),'Spike changed from accepted restart reference')
    baseline_files=[SOURCE, original_elf, report, report.parent/ORIGINAL, PART/'manifest.json',
        PART/'parent_mapping.json',C/'stall_family_triage02/triage.json',
        PART/ORIGINAL/'operations.S',PART/ORIGINAL/'operations.h',
        OUT.parent/'prepare_stall_prefix2.py',OUT.parent/'prepare_batch.py',
        OUT.parent/'audit_accepted8.py', OUT.parent/'prepare_successor.py',
        OUT.parent/'stall_prefix2_03/reference/reference.json',
        OUT.parent/'gather_repair05/m5_successor01/prefix_terminal_audit01/audit.json',
        OUT.parent/'gather_repair05/m5_successor01/prefix_vcs_candidate05_01/complete.json',
        base.INTEGRATION/'prepare.py',SPIKE,Path(__file__),OUT/'reference_check.py']
    baseline_files += [p for p in (OUT.parent/'e16_m8_ops1_prefix98_prepare01').rglob('*') if p.is_file()]
    for folder in ('e8_m8_ops1_prefix66_prepare01','e16_m8_ops3_prefix98_prepare01'):
        baseline_files += [p for p in (OUT.parent/folder).rglob('*') if p.is_file()]
    baseline_files += [OUT/'audit_reference.py', OUT.parent/'NEXT_GATHER_STALL_PLAN.md']
    baseline_files += [base.INTEGRATION/f for f in ('runtime.c','startup.S','replay.ld')]
    pins={str(p):base.sha(p) for p in baseline_files}
    save(OUT/'baseline_pins.json',pins)
    prepared=OUT/'prepared'
    original=prepared/NAME/'original'
    original.mkdir(parents=True)
    shutil.copyfile(SOURCE,original/'scenario.c')
    for f in ('operations.S','operations.h'):
        shutil.copyfile(PART/ORIGINAL/f,original/f)
    shutil.copyfile(original_elf,original/'original_linux.elf')
    save(original/'case.json',dict(case=case,archived_stall=record))
    sys.path.insert(0,str(base.INTEGRATION))
    from prepare import adapt
    source=SOURCE.read_text()
    adapted=adapt(source,NAME)
    port=prefix(adapted,66)
    anchor='            ++cases;\n'
    require(adapted[adapted.index('    for(unsigned seed='):adapted.index(anchor)+len(anchor)]==
            port[port.index('    for(unsigned seed='):port.index(anchor)+len(anchor)],'Original loop/setup/oracle changed')
    (prepared/NAME/'case.c').write_text(port)
    diffdir=OUT/'source_diffs'
    diffdir.mkdir()
    for label,before,after in (('adapter',source,adapted),('prefix',adapted,port)):
        (diffdir/(label+'.diff')).write_text(''.join(difflib.unified_diff(before.splitlines(True),
            after.splitlines(True),fromfile=label+'_before',tofile=label+'_after')))
    for f in ('runtime.c','startup.S','replay.ld'):
        shutil.copyfile(base.INTEGRATION/f,prepared/f)
    gold=model()
    save(OUT/'host_expected.json',gold)
    spec=dict(id=NAME,operation=3,assembly='operations.S',original_case=case,
        original_linux_elf_sha256=EXPECTED_ELF,defines=['SEW=8','RESTART_PERMUTATIONS=1','PERMUTE_OP_MASK=8'],
        pass_markers=[f'BOARD_CASE_PASS {NAME}','BOARD_REPLAY_PASS','RVV_GATHER_PREFIX_PASS sew=8 cases=66 errors=0'])
    provenance=dict(cases=[spec],vlen=1024,nr_lanes=4,scope='Original child first66 calls; not full/Linux/exact-stall acceptance',
        files={str(p.relative_to(prepared)):base.sha(p) for p in prepared.rglob('*') if p.is_file()})
    save(prepared/'provenance.json',provenance)
    host_check(prepared,gold)
    base.HERE=OUT
    soc=base.build(prepared,provenance,'soc')[NAME]
    spike=base.build(prepared,provenance,'spike')[NAME]
    routine=instructions(Path(soc['path']),NAME+'_op_3')
    archived=archived_window(original/'original_linux.elf',routine)
    spike_routine=instructions(Path(spike['path']),NAME+'_op_3')
    require(len(routine)==13 and [r['insn'] for r in routine]==[r['insn'] for r in spike_routine], 'Full original asm differs')
    require(archived[8]['pc']==record['last_pc']==0x1063e and routine[8]['insn']=='308fbc57','Archived target PC/opcode drift')
    save(OUT/'source_elf_proof.json',dict(status='ORIGINAL_SOURCE_AND13_ASM_VERIFIED',
        original_c_sha256=base.sha(SOURCE),original_linux_elf_sha256=EXPECTED_ELF,
        soc_elf=soc,spike_elf=spike,original_routine=archived,soc_routine=routine,spike_routine=spike_routine,
        entire_original_linux_binary_rebuild_proven=False,original_stopped_tuple=None))
    reference=OUT/'reference'
    reference.mkdir()
    logaddr,_=symbol(Path(spike['path']),'replay_log',OBJDUMP)
    debug=reference/'spike.cmd'
    debug.write_text(f'rs {MAX_RETIRED}\nstr {logaddr:x}\nquit\n')
    command=[str(SPIKE),'-d','--debug-cmd='+str(debug),'--isa=rv64gcv_zvl1024b','-m2',
             '--log-commits','--log='+str(reference/'commits.log'),spike['path']]
    save(reference/'command.json',dict(command=command,seconds=120,instructions=MAX_RETIRED,file_bytes=MAX_LOG))
    def limit_log():
        resource.setrlimit(resource.RLIMIT_FSIZE,(MAX_LOG,MAX_LOG))
    start=time.monotonic()
    with (reference/'spike.log').open('x') as stream:
        run=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,timeout=120,preexec_fn=limit_log)
    elapsed=time.monotonic()-start
    save(reference/'execution.json',dict(returncode=run.returncode,elapsed_s=elapsed,command=command))
    require(run.returncode==0,'Spike nonzero')
    measured=audit_trace(reference/'commits.log',Path(spike['path']),gold)
    (reference/'runtime.log').write_text(measured['reconstructed_console'])
    save(reference/'reference.json',dict(**measured,elapsed_s=elapsed,returncode=run.returncode,
        spike_sha256=base.sha(SPIKE),commit_sha256=base.sha(reference/'commits.log'),
        commit_bytes=(reference/'commits.log').stat().st_size,limits=dict(seconds=120,retired=MAX_RETIRED,bytes=MAX_LOG)))
    for p,digest in pins.items():
        require(base.sha(Path(p))==digest,'Baseline changed: '+p)
    save(OUT/'preparation_complete.json',dict(status='HOST_SPIKE_PREPARED_PENDING_OFFLINE_AUDIT_NOT_DUT',
        name=NAME,calls=66,soc_elf=soc,spike_elf=spike,reference_sha256=base.sha(reference/'reference.json'),
        original_stopped_tuple=None,full_child_pass=False,full_parent_pass=False,linux_replay=False,
        baseline_pins_unchanged=True,vcs_started=False,rtl_modified=False))
    print('HOST_SPIKE_PREPARED_PENDING_OFFLINE_AUDIT_NOT_DUT',measured['firmware_retired_to_htif_store'],flush=True)


if __name__=='__main__':
    try:
        main()
    except Exception as error:
        save(OUT/'preparation_error.json',dict(status='PREPARATION_STOPPED_NOT_DUT',error=repr(error),retry=False))
        raise
