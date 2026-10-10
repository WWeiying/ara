"""R2 full byte oracle and frozen721 reconciliation; VILL diagnostics do not qualify lower-EMUL targets."""
import argparse
from collections import Counter
from fractions import Fraction
import json
from pathlib import Path
import re
import struct
import subprocess

import build_narrow_reject_r1_cached_preflight as prior

old, life, require = prior.original, prior.life, prior.require
ROOT, OUT, LLVM, SPIKE = prior.ROOT, prior.OUT, prior.LLVM, prior.SPIKE
NAME = 'vmemory_emul_r2_boundary_reject'
APP = ROOT/'apps/riscv-tests/isa/rv64uv'/ (NAME+'.c')
BASE = OUT/'akv-column-boundary-offline-admitted-721-20261006-01'
BASE_SEAL = 'eda7720583e3232e97cd4486d7790a678abc108018f6acbd56d0b1c287e20c8b'
PREVIOUS = OUT/'narrow-reject-r1-cached-preflight-719-20261006-01'
PREVIOUS_SEAL = 'd84184ea823564af4af9475bc6d31c25f7cb7a2de9429b45751ef4633b080d28'
SPIKE_SOURCE = Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/riscv/vector_unit.cc')
CHECKS = 4229
BAD_WORDS = [0x02050407,0x02050427,0x02057427]
VTYPES = [1<<63,1<<63,3]
VLS = [0,0,4]
PAIRS = [('gmr_bad_%02d'%n,w) for n,w in enumerate(BAD_WORDS)] + [
    ('gmr_load_0',0x02050407),('gmr_store_0',0x02050427),
    ('gmr_load_1',0x02057407),('gmr_store_1',0x02057427),
    ('gmr_load_2',0x02050407),('gmr_store_2',0x02050427)]
SYMBOLS = ('tohost','g75_result','num_failed','trap_fail','gmr_ledger','gmr_post','gmr_restore','gmr_traps',
           'gmr_cfg','gmr_legal','gmr_dump','gmr_input','gmr_output','gmr_handler','gmr_handler_end',
           'gmr_init_begin','gmr_init_end') + tuple(n for n,_ in PAIRS)
STATUS = 'R2_HOST_SPIKE_FULL_PREFLIGHT_PASS_PARTIAL_TARGET_HOLD_NOT_VCS'


def input_bytes(which):
    return bytes(((0x20,0x60,0xa0)[which]+i*(11,7,3)[which])&255 for i in range(128))


def expected_register(reg, phase):
    data = bytearray((reg*29+i*13+((i>>3)^reg)*7+0x35)&255 for i in range(128))
    if reg == 8:
        if phase == 1: data[:4] = input_bytes(0)[:4]
        if phase >= 2: data[:32] = input_bytes(1)[:32]
        if phase == 6: data[:4] = input_bytes(2)[:4]
    return bytes(data)


def emul_proof():
    rows=[]
    for sew in (8,16,32,64):
        for exponent in range(-3,4):
            lmul=Fraction(2)**exponent
            if sew > min(lmul,1)*64: continue
            for eew in (8,16,32,64):
                emul=lmul*eew/sew
                require(emul >= Fraction(1,8), 'Unexpected legal-vtype EMUL underflow')
                rows.append(dict(sew=sew,lmul=str(lmul),eew=eew,emul=str(emul)))
    require(len(rows)==88, 'Legal ELEN64 combinations differ')
    return dict(ELEN=64,minimum_EEW=8,legal_vtype_memory_combinations=rows,
                lower_bound='LMUL >= SEW/ELEN implies EMUL >= EEW/ELEN >= 1/8',
                original_lower_context='e64,mf8 is VILL; VL0, not a legal-vtype EMUL-underflow trigger',
                no_waiver_generated=True, upper_context=dict(sew=8,lmul=8,eew=64,emul=64))


def reconcile(bits, targets):
    require(len(bits['tests'])==len(set(bits['tests']))==721, 'Not exact721')
    result=[]
    for t in targets:
        row=bits['metrics'][t['metric']][t['scope']]; i=t['point']['raw_index']
        require((row['width'],row['checksum'])==(t['bitmap_width'],t['metric_checksum']), '721 target shape drift')
        hit=bool(int(row['bits'],16)&(1<<(row['width']-1-i)))
        require(not hit, 'Original R2 target no longer zero')
        eligible=(t['metric'],i) in (('line',1308),('branch',362))
        result.append(dict(**t,hit721=hit,scope_status='UPPER_EMUL_CANDIDATE_NOT_MEASURED' if eligible else
                           'HOLD_LOWER_EMUL_NOT_PROVEN_BY_VILL_CONTEXT',
                           expected_case=2 if eligible else None))
    require(Counter(t['metric'] for t in result)==Counter(line=3,branch=3), 'Not original six R2 targets')
    return result


def verify_elf(blob, symbols):
    require(blob[:6]==b'\x7fELF\x02\x01','Not ELF64 LE')
    h=struct.unpack_from('<HHIQQQIHHHHHH',blob,16)
    require(h[:3]==(2,243,1) and h[10]==64 and h[5]+h[11]*64<=len(blob),'ELF header')
    require(len({symbols[n] for n,_ in PAIRS})==9,'Aliased fault/legal PCs')
    for name,word in PAIRS:
        pc,owners=symbols[name],[]
        require(pc%4==0,'Opcode alignment')
        for i in range(h[11]):
            sec=struct.unpack_from('<IIQQQQIIQQ',blob,h[5]+i*64)
            if sec[1]==1 and sec[2]&4 and sec[3]<=pc and pc+4<=sec[3]+sec[5]:
                owners.append(struct.unpack_from('<I',blob,sec[4]+pc-sec[3])[0])
        require(owners==[word],'Exact R2 executable opcode differs: '+name)


def signatures(read, s):
    require(read('g75_result',width=4)==CHECKS and read('g75_result',4,4)==read('num_failed',width=4)==0,
            'Software check count/failures differ')
    restore=[read('gmr_restore',i*8) for i in range(12)]
    require(all(restore[i]==restore[i+1] for i in range(0,12,2)) and restore[0]==s['trap_fail'] and
            restore[2]==0 and 0x80100000<=restore[4]<0x80200000 and restore[4]%16==0 and restore[6:]==[0]*6,
            'Full context restore differs')
    sp=restore[4]
    for n,w in enumerate(BAD_WORDS):
        require([read('gmr_ledger',(n*12+i)*8) for i in range(12)] ==
                [2,s['gmr_bad_%02d'%n],w,VLS[n],VTYPES[n],0,5,n+1,0x2222,1,117,sp], 'Precise trap ledger differs')
        require([read('gmr_post',(n*9+i)*8) for i in range(9)] ==
                [0x1111,0x2222,1,sp,0,VLS[n],VTYPES[n],5,117], 'Post-mret state differs')
        require([read('gmr_cfg',(n*3+i)*8) for i in range(3)]==[VLS[n],VTYPES[n],0], 'Actual pre-fault VILL/VL contract differs')
        require([read('gmr_legal',(n*3+i)*8) for i in range(3)]==[4,24 if n==0 else 0,0], 'Legal boundary config differs')
        for name in ('gmr_input','gmr_output'):
            actual=b''.join(read(name,(n*18+w)*8).to_bytes(8,'little') for w in range(18))
            body=input_bytes(n)
            if name=='gmr_output':
                active=32 if n==1 else 4
                body=body[:active]+b'\xcc'*(128-active)
            require(actual==b'\xa5'*8+body+b'\xa5'*8, 'Complete input/output guards/body differ')
    require(read('gmr_traps')==3,'Not exactly3 traps')
    for phase in range(7):
        for reg in range(32):
            actual=b''.join(read('gmr_dump',((phase*32+reg)*18+w)*8).to_bytes(8,'little') for w in range(18))
            require(actual==b'\xa5'*8+expected_register(reg,phase)+b'\xa5'*8,'Full VRF/guard mismatch phase=%d reg=%d'%(phase,reg))


def validate(commits,s,trace):
    pcs=[s['gmr_bad_%02d'%n] for n in range(3)]
    events=re.findall(r'exception ([^,\n]+), epc (0x[0-9a-fA-F]+)',trace)
    require([(n,int(pc,16)) for n,pc in events]==[('trap_illegal_instruction',pc) for pc in pcs] and
            trace.count('exception ')==3,'Not exact ordered3 illegal traps')
    require(not any(c.pc in (*pcs,s['trap_fail']) for c in commits),'Fault/fatal handler retired')
    memory,terminal,handlerstores,vectorcommits={},[],[],[]
    handlers=[c for c in commits if s['gmr_handler']<=c.pc<s['gmr_handler_end']]
    require(sum(c.pc==s['gmr_handler'] for c in handlers)==3,'Handler entry count')
    for c in commits:
        handler=s['gmr_handler']<=c.pc<s['gmr_handler_end']
        for a,v in c.memory_accesses:
            if v is None:continue
            width=old.shared.store_width(c.instruction)
            require(0<=v<1<<(8*width),'Scalar store width mismatch')
            memory.update({a+i:(v>>(8*i))&255 for i in range(width)})
            if a==s['tohost']:terminal.append(v)
            if handler:handlerstores.append((a,width))
        if c.vector_writes:vectorcommits.append(c)
    def read(name,offset=0,width=8):
        a=s[name]+offset
        require(all(a+i in memory for i in range(width)),'Missing observed bytes: '+name)
        return int.from_bytes(bytes(memory[a+i] for i in range(width)),'little')
    require(terminal==[1],'Missing/repeated/nonPASS terminal')
    signatures(read,s)
    allowed=Counter({(s['gmr_ledger']+i*8,8):1 for i in range(36)})
    allowed[s['gmr_traps'],8]=3
    require(Counter(handlerstores)==allowed,'Handler exact39 stores differ')
    require(all(not c.vector_writes and not c.fpr_writes and set(c.gpr_writes)<={5,6,7} and
                set(c.csr_writes)<={0x300,0x340,0x341} for c in handlers),'Protected handler side effects')
    initial=[c for c in vectorcommits if s['gmr_init_begin']<=c.pc<s['gmr_init_end']]
    require(len(initial)==32 and [list(c.vector_writes) for c in initial]==[[r] for r in range(32)],'Initial32 registers differ')
    require(all(c.vector_writes[r]==int.from_bytes(expected_register(r,0),'little') for r,c in enumerate(initial)), 'Initial seed writes differ')
    rest=[c for c in vectorcommits if c not in initial]
    require([c.pc for c in rest]==[s['gmr_load_%d'%n] for n in range(3)],'Unexpected/absent legal vector write')
    for phase,c in zip((1,2,6),rest):
        require(8 in c.vector_writes and set(c.vector_writes)<=set(range(8,16)) and
                all(v==int.from_bytes(expected_register(r,phase),'little') for r,v in c.vector_writes.items()),
                'Legal boundary/recovery vector bytes differ')
    return dict(status='R2_FULL_HOST_SPIKE_ORACLE_PASS_NOT_DUT',checks=CHECKS,snapshots=7,illegal_traps=3,
                ordered_fault_pcs=pcs,actual_prefault_vtypes=VTYPES,actual_prefault_vls=VLS,
                VILL_diagnostics_not_lower_EMUL_evidence=2,valid_vtype_EMUL_overflow_rejection=1,
                legal_EMUL_boundaries=['1/8','8'],handler_store_words=39,observed_vrf_bytes=28672,
                vrf_guard_bytes=3584,memory_buffer_bytes=864,vector_write_instructions=35,
                illegal_vector_writes=0,context_restored=True,coverage_admitted=False)


def baseline():
    manifest=life.read_bound(BASE/'admission-manifest.json',BASE_SEAL)
    pins=life.merge_pins(manifest['output_pins'],{str(BASE/'admission-manifest.json'):BASE_SEAL})
    life.check(pins)
    bits=json.loads((BASE/'combined-bits.json').read_text())
    require((BASE/'combined-inputs.txt').read_text().splitlines()==[str(old.review.VDB),*bits['tests']], '721 prefix/order differs')
    report=life.read_bound(old.REVIEW,old.REVIEW_SEAL)
    targets=reconcile(bits,report['candidates'][1]['zero_targets'])
    elfpins={p:h for p,h in json.loads((BASE/'evidence-pins.json').read_text()).items() if p.endswith('.elf')}
    return life.merge_pins(pins,elfpins),targets,elfpins


def verify(out,seal):
    pre=life.read_bound(out/'preflight-manifest.json',seal)
    require(pre['status']==STATUS and pre['case']==NAME and pre['baseline_tests']==721 and
            not pre['vcs_started'] and not pre['coverage_admitted'] and not pre['rtl_changed'],'R2 contract differs')
    life.check(pre['pins'])
    _,targets,_=baseline();require(pre['targets']==targets and pre['emul_proof']==emul_proof(),'Scope/proof differs')
    s={n:old.shared._elf_symbol(out/'input.elf',LLVM/'llvm-readelf',n) for n in SYMBOLS}
    require(s==pre['symbols'],'ELF symbols differ');verify_elf((out/'input.elf').read_bytes(),s)
    commits=old.shared.parse_spike_commits(out/'spike.trace')
    require(validate(commits,s,(out/'spike.trace').read_text())==pre['validation'] and
            old.strict.reference_counts(commits,s)==pre['reference_counts'],'Full actual Spike replay differs')
    return pre


def build(out):
    require(out.parent==OUT and out.resolve()==out and not out.exists(),'Fresh direct output required')
    prev=life.read_bound(PREVIOUS/'preflight-manifest.json',PREVIOUS_SEAL);life.check(prev['pins'])
    basepins,targets,elfpins=baseline()
    paths=[APP,ROOT/'verification/tests/memory_emul_r2_reference.h',ROOT/'verification/tests/memory_emul_r2_host.c',
           Path(__file__).resolve(),Path(__file__).with_name('test_memory_emul_r2_preflight.py'),SPIKE_SOURCE,
           Path('/usr/bin/cc'),Path('/usr/bin/cc').resolve()]
    pins=life.merge_pins(prev['pins'],basepins)
    pins=life.merge_pins(pins,{str(PREVIOUS/'preflight-manifest.json'):PREVIOUS_SEAL})
    pins=life.merge_pins(pins,{str(p):life.digest(p) for p in paths});life.check(pins)
    command=json.loads((PREVIOUS/'compile-command.json').read_text())
    require(command.count(str(prior.APP))==command.count(str(PREVIOUS/'input.elf'))==1,'Sealed compile template differs')
    command=[str(APP) if x==str(prior.APP) else str(out/'input.elf') if x==str(PREVIOUS/'input.elf') else x for x in command]
    require(command[0]==str(LLVM/'clang') and not any('ZCC' in x or 'Terapines' in x for x in command),'Forbidden compiler')
    out.mkdir();life.save(out/'input-pins.json',pins)
    try:
        host=['/usr/bin/cc','-std=c11','-Wall','-Wextra','-Werror',str(ROOT/'verification/tests/memory_emul_r2_host.c'),'-o',str(out/'host-reference')]
        life.save(out/'host-command.json',host)
        with (out/'host.log').open('x') as log:
            subprocess.run(host,check=True,timeout=60,stdout=log,stderr=subprocess.STDOUT)
            subprocess.run([str(out/'host-reference')],check=True,timeout=10,stdout=log,stderr=subprocess.STDOUT)
        require((out/'host.log').read_text().startswith('R2_BYTE_ORACLE_PASS snapshots=7 traps=3 checks=4229 vrfbytes=28672 bufferbytes=864'),'Host oracle failed')
        life.save(out/'compile-command.json',command)
        with (out/'compile.log').open('x') as log:subprocess.run(command,check=True,timeout=120,stdout=log,stderr=subprocess.STDOUT)
        s={n:old.shared._elf_symbol(out/'input.elf',LLVM/'llvm-readelf',n) for n in SYMBOLS}
        verify_elf((out/'input.elf').read_bytes(),s)
        h=life.digest(out/'input.elf')
        require(h not in elfpins.values(),'Duplicate721 ELF')
        life.save(out/'elf-dedup.json',dict(baseline_tests=721,baseline_elf_pins=len(elfpins),input_elf_sha256=h,
                                          duplicate_elf=False,instruction_word_match_is_not_context_identity=True))
        spike=[str(SPIKE),'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0','-l','--log-commits',str(out/'input.elf')]
        life.save(out/'spike-command.json',spike)
        with (out/'spike.stdout').open('x') as stdout,(out/'spike.trace').open('x') as trace:
            subprocess.run(spike,check=True,timeout=180,stdout=stdout,stderr=trace)
        commits=old.shared.parse_spike_commits(out/'spike.trace')
        result=validate(commits,s,(out/'spike.trace').read_text());counts=old.strict.reference_counts(commits,s)
        life.save(out/'spike-validation.json',result);life.save(out/'target-reconciliation721.json',targets)
        proof=emul_proof();life.save(out/'emul-contract-proof.json',proof)
        life.check(pins);pins=life.merge_pins(pins,{str(p):life.digest(p) for p in out.iterdir() if p.is_file()})
        pre=dict(status=STATUS,case=NAME,baseline_tests=721,baseline_manifest_seal=BASE_SEAL,input_elf=str(out/'input.elf'),
                 pins=pins,symbols=s,validation=result,reference_counts=counts,targets=targets,emul_proof=proof,
                 lower_EMUL_targets_qualified=False,ordinary_upper_EMUL_candidate_count=2,
                 requested_three_contexts_preserved=True,old_image_files_checked=66,vcs_started=False,
                 coverage_admitted=False,rtl_changed=False,ZCC_executed=False,measured_raw_increment=None,
                 full_DUT_diff_executed=False,exclusions_generated=False,historical_failure_artifacts_modified=False,
                 launch_policy='No launch authorized. Parent review must acknowledge VILL0 diagnostics and 4 held lower targets; only upper-store line1308/branch362 have an ordinary valid-vtype trigger.',
                 source_chain='Frozen vsetvli1698..1704 validates LMUL>=SEW/ELEN; memory EMUL4213/4477 and sign-transition checks4224/4488 reject overflow. Memory base aligned and accessible, nf/mop/rs2 zero, vm1, v8 group-aligned.',
                 full_scalar_vector_diff_entry='build_memory_emul_r2_preflight.py compare')
        life.save(out/'preflight-manifest.json',pre)
        print(json.dumps(dict(output=str(out),seal=life.digest(out/'preflight-manifest.json'),elf_sha256=h,
                              scalar_instructions=counts['matched_instructions'],validation=result,target_candidates=2,target_hold=4)))
    except Exception as error:
        life.save(out/'failure.json',dict(status='R2_PREFLIGHT_FAILED_NOT_VCS',reason=str(error)));raise


def compare(out,seal,dut,destination):
    pre=verify(out,seal);require(not destination.exists(),'Fresh comparison required')
    scalar=old.strict.spike_trace.compare_commit_prefix(out/'spike.trace',dut/'commit_trace.csv',0x80000000,
                     terminal_tohost_address=0x80001000,rvfi_store_data_layout='unshifted')
    old.strict.scalar_exact(scalar,pre['reference_counts'])
    vector=old.strict.compare_vector_commits(out/'spike.trace',dut/'commit_trace.csv',dut/'vector_trace.csv',0x80000000)
    for k,v in dict(status='PASS',compared_instructions=35,skipped_unknown_bytes=0,non_bit_exact_instructions=0,
                   unobservable_instructions=0,incomplete_requests=[],unretired_requests=[],first_mismatch=None).items():
        require(vector.get(k)==v,'Full vector gate differs: '+k)
    records=vector['instructions']
    require(len(records)==35 and all(r['status']=='PASS' and r['unknown_write_bytes']==r['skipped_unknown_bytes']==
            r['mismatch_count']==0 for r in records) and all(r['compared_bytes']==128 for r in records[:32]) and
            all(records[32+n]['compared_bytes']>=width for n,width in enumerate((4,32,4))) and
            len(vector['trapped_requests'])==len(set(vector['trapped_requests']))==3,'Incomplete vector byte/trap population')
    life.save(destination,dict(status='R2_FULL_SCALAR_VECTOR_DIFF_PASS_NOT_ADMISSION',scalar=scalar,vector=vector,
                  preflight_seal=seal,pins={str(dut/n):life.digest(dut/n) for n in ('commit_trace.csv','vector_trace.csv')},
                  coverage_admitted=False,lower_EMUL_targets_qualified=False))
    print('R2_FULL_DIFF_PASS_NOT_ADMISSION')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('build','verify','compare'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');p.add_argument('--dut',type=Path)
    p.add_argument('--comparison',type=Path);a=p.parse_args()
    require((a.mode!='build')==bool(a.seal),'Replay requires fixed seal')
    if a.mode=='build':build(a.output.absolute())
    elif a.mode=='verify':verify(a.output.absolute(),a.seal);print('VERIFY_PASS R2/full7/full3/4229/721 PARTIAL_TARGET_HOLD NO_VCS')
    else:
        require(a.dut and a.comparison,'Existing DUT traces and fresh comparison required')
        compare(a.output.absolute(),a.seal,a.dut.absolute(),a.comparison.absolute())


if __name__=='__main__':main()
