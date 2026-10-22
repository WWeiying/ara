#!/usr/bin/env python3
"""Full original mask-alias programs: pinned adaptation, host/Spike only."""
import argparse
import difflib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'integration'
sys.path.insert(0,str(BASE))
import prepare

ROOT=prepare.ROOT
CAMP=Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01')
SOURCE=Path('/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix')
ARCH=CAMP/'rvv_mask_logic_restart01'
PARENT=Path('/tmp/current-board-integration-fast01/prepared')
CC=Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
SPIKE=Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
SHAPES=((8,'m4',512),(8,'m8',1024),(16,'m8',512))
NAMES=tuple(f'rvv_masks_alias_restart_e{s}_{m}' for s,m,c in SHAPES)
ISA='rv64gcv_zvl1024b'
MASK64=(1<<64)-1
sha=prepare.sha
save=prepare.save


def require(ok,why):
    if not ok: raise ValueError(why)


def run(cmd,log,timeout=90,expected=0):
    save(Path(str(log)+'.command.json'),list(map(str,cmd)))
    started=time.monotonic()
    with log.open('x') as stream:
        result=subprocess.run(list(map(str,cmd)),stdout=stream,stderr=subprocess.STDOUT,timeout=timeout)
    require(result.returncode==expected,f'{log.name}: exit {result.returncode}, expected {expected}')
    return time.monotonic()-started


def provenance():
    manifest=json.loads((ARCH/'manifest.json').read_text())
    transfer=json.loads((CAMP/'rvv_additions36/transfer_manifest.json').read_text())
    triage=json.loads((CAMP/'stall_family_triage02/triage.json').read_text())
    pins={}
    def pin(p,digest=None):
        actual=sha(p); require(digest is None or actual==digest,'Source/artifact drift: '+str(p)); pins[str(p)]=actual
    pin(ARCH/'manifest.json','c27b18089d4b7f75359f4e9fefecad120183382b2763c4047d785fd77f9f1aff')
    pin(ARCH/'transfer_manifest.json','742e4fcfa3b4dcd3d326fcf5a2f56979502aecc2ea1a6e066ee9eef1542913a4')
    release=json.loads((ARCH/'transfer_manifest.json').read_text())
    require(all(release[k]==v for k,v in manifest.items()),'Source/release manifest metadata differs')
    for n in ('reference_512.json','reference_1024.json'):
        pin(ARCH/n)
        historical=json.loads((ARCH/n).read_text())
        require(historical['manifest_sha256']==sha(ARCH/'manifest.json'),'Historical reference source binding differs')
    for p in (CAMP/'rvv_additions36/transfer_manifest.json',CAMP/'stall_family_triage02/triage.json',CAMP/'stall_family_triage02/ledger.json'):
        pin(p)
    for name,digest in manifest['source_sha256'].items(): pin(SOURCE/name,digest)
    pin(SOURCE/'build.py'); pin(ARCH/'operations.h')
    spec=importlib.util.spec_from_file_location('original_mask_generator',SOURCE/'masks.py')
    sys.path.insert(0,str(SOURCE)); generator=importlib.util.module_from_spec(spec); spec.loader.exec_module(generator)
    records=[]
    for name,(sew,lmul,cap) in zip(NAMES,SHAPES):
        entry=next(c for c in manifest['cases'] if c['name']==name)
        delivered=next(c for c in transfer['cases'] if c['name']==name)
        old=next(c for c in triage['cases'] if c['name']==name)
        require(entry['sha256']==delivered['sha256']==old['elf_sha256'],'Original ELF identity disagreement')
        assembly=ARCH/(name+'.S'); pin(assembly)
        require(assembly.read_text()==generator.assembly(sew,lmul,aliases=True,restart=True),'Generated assembly differs from archive')
        for elf in (CAMP/'rvv_additions36/binaries'/name,ARCH/'overlay/opt/ara-tests'/name): pin(elf,entry['sha256'])
        pin(Path(old['report']),old['report_sha256'])
        dis=subprocess.check_output([str(CC.with_name('riscv64-unknown-elf-objdump')),'-d',old['binary']],text=True,timeout=15)
        require(re.search(rf'^\s*{old["last_pc"]:x}:\s+66882457\s+vmand\.mm\s+v8,v8,v16',dis,re.M),'Archived target decode differs')
        records.append(dict(name=name,sew=sew,lmul=lmul,cap=cap,original=entry,measured=old,
            source_assembly=str(assembly),original_elf=old['binary'],configurations=5376,
            last_print=dict(vl=512,vstart=256,seed=0,raw_op=0,mode=0,trial=1,
                            zero_based_trial=97 if cap==512 else 65,
                            qualifier='Tuple inferred from unique print condition and source loop, not internal acceptance'),
            internal_root_cause_proven=False,original_linux_replayed=False))
    return dict(files=pins,cases=records,source_manifest=manifest)


def fnv(data,h=14695981039346656037):
    for b in data: h=((h^b)*1099511628211)&MASK64
    return h


def host_expected(sew,cap):
    rows=[]; index=0
    for seed in range(3):
        rng=0xc274caf34727a125^seed; a=[]; b=[]; mask=(1<<sew)-1
        for i in range(cap):
            rng^=(rng<<13)&MASK64; rng^=rng>>7; rng^=(rng<<17)&MASK64
            a.append(rng&mask); b.append(a[-1] if i%8==0 else (rng>>19)&mask)
        data=b''.join(x.to_bytes(sew//8,'little') for x in a+b)
        h=fnv(data); digests={m:fnv(bytes([m])*128,h) for m in (255,0,170,36)}
        for op in range(16):
            for vl in (0,1,2,3,cap//2,cap-1,cap):
                for mode in (255,0,170,36):
                    for start in (1,vl//2,vl if vl<=1023 else cap-1,cap-1):
                        rows.append(f'CALL {index} {op} {vl} {start} {digests[mode]:016x}'); index+=1
    require(index==5376,'Wrong full matrix size')
    return rows


def host_checks(prepared,out):
    host=out/'host'; host.mkdir(); results=[]
    for name,(sew,lmul,cap) in zip(NAMES,SHAPES):
        case=prepared/name
        text=(case/'case.c').read_text()
        needle='__asm__ volatile("csrr %0,vlenb":"=r"(max_start));'
        require(text.count(needle)==1,'Unrecognized host-only CSR stub')
        (host/(name+'.c')).write_text(text.replace(needle,'max_start=128; /* host model only */'))
        exe=host/name
        cmd=['/usr/bin/cc','-O2','-Wall','-Wextra','-Werror',f'-DSEW={sew}',f'-DCAP={cap}',
             '-DRESTART_MASKS=1','-DALIASES=1','-DSCALAR_FORMS=0','-DCARRY_FORMS=0','-DCOMPARISON_ALIASES=0',
             '-I'+str(case/'original'),host/(name+'.c'),HERE/'host_mock.c','-o',exe]
        run(cmd,host/(name+'.compile.log'))
        expected=host_expected(sew,cap)
        for policy in range(3):
            log=host/(name+f'.policy{policy}.log'); seconds=run([exe,str(policy)],log)
            text=log.read_text(); rows=[x for x in text.splitlines() if x.startswith('CALL ')]
            require(rows==expected,'Host invocation/input digest differs '+name)
            require(f'RVV_MASK_PASS sew={sew} cases=5376 errors=0' in text and 'HOST_END calls=5376 injected=0 result=0' in text,'Missing full host oracle completion')
            results.append(dict(name=name,tail_policy=policy,calls=len(rows),elapsed_s=seconds,status='PASS'))
    negative=[]
    for mutation,label in enumerate(('active_result','prestart','no_body','forbidden_tail','guard','returned_vstart'),1):
        log=host/(f'negative_{label}.log'); run([host/NAMES[0],'0',str(mutation)],log,expected=1)
        require('RVV_MASK_FAIL' in log.read_text() and 'HOST_END calls=5376 injected=1 result=1' in log.read_text(),'Original oracle failed to reject '+label)
        negative.append(dict(name=label,rejected=True))
    result=dict(status='HOST_PASS_NOT_RTL',full_matrix_runs=results,negative_oracle=negative,
                limitation='Scalar models cross-check original C oracle/input/order; not vector execution')
    save(host/'status.json',result); return result


def build(prepared,out):
    flags=['-Os','-march=rv64gcv','-mabi=lp64d','-mcmodel=medany','-ffreestanding','-fno-builtin',
           '-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize','-msmall-data-limit=0',
           '-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror','-nostdlib','-static',
           '-Wl,--build-id=none','-Wl,--gc-sections','-T',prepared/'replay.ld']
    for backend in ('soc','spike'):
        directory=out/backend; directory.mkdir(); entries={}
        for name,(sew,lmul,cap) in zip(NAMES,SHAPES):
            case=prepared/name; elf=directory/(name+'.elf')
            cmd=[CC,*flags,f'-DSEW={sew}','-DRESTART_MASKS=1','-DALIASES=1','-DSCALAR_FORMS=0',
                 '-DCARRY_FORMS=0','-DCOMPARISON_ALIASES=0','-I'+str(case/'original')]
            if backend=='spike': cmd+=['-DSPIKE_REFERENCE=1']
            cmd += [case/'case.c',case/'original/scenario.S',case/'main.c',prepared/'startup.S',prepared/'runtime.c','-lgcc','-o',elf]
            run(cmd,directory/(name+'.compile.log'))
            run([CC.with_name('riscv64-unknown-elf-objdump'),'-d',elf],directory/(name+'.dis'))
            nm=subprocess.check_output([str(CC.with_name('riscv64-unknown-elf-nm')),'-n',str(elf)],text=True,timeout=15)
            symbols={m[3]:int(m[1],16) for m in re.finditer(r'^([0-9a-f]+)\s+(\w)\s+(\S+)$',nm,re.M)}
            require(symbols['__bss_end']<0x800f0000,'ELF exceeds immutable runtime memory boundary')
            save(directory/(name+'.symbols.json'),symbols)
            entries[name]=dict(path=str(elf),sha256=sha(elf),cases=[name],configurations=5376,
                pass_markers=[f'RVV_MASK_PASS sew={sew} cases=5376 errors=0',f'BOARD_CASE_PASS {name}','BOARD_REPLAY_PASS'])
        save(directory/'programs.json',dict(schema_version=1,backend='vcs-soc' if backend=='soc' else 'spike-htif',
            programs=entries,prepared=str(prepared),provenance_sha256=sha(prepared/'provenance.json'),
            compiler=dict(path=str(CC),sha256=sha(CC)),vcs_started=False))


def spike_checks(out):
    directory=out/'reference'; directory.mkdir(); results=[]
    sys.path.insert(0,str(ROOT/'verification'))
    from ara_verify.spike_probe import check_spike_vstart,probe_paths
    probe_cc,probe_source=probe_paths(ROOT)
    probe=check_spike_vstart(SPIKE,probe_cc,directory/'vstart_probe',probe_source)
    require(probe['status']=='PASS','Spike lacks required vstart semantics')
    for name,(sew,lmul,cap) in zip(NAMES,SHAPES):
        elf=out/'spike'/(name+'.elf'); s=json.loads((out/'spike'/(name+'.symbols.json')).read_text())
        cmdfile=directory/(name+'.cmd')
        cmdfile.write_text(f'until pc 0 {s["replay_exit"]:x}\nreg 0 a0\nreg 0 minstret\nreg 0 mcycle\nstr {s["replay_log"]:x}\nrs\n')
        cmd=[SPIKE,'-d','--debug-cmd='+str(cmdfile),'--isa='+ISA,'-m2',elf]
        log=directory/(name+'.log'); seconds=run(cmd,log,timeout=180)
        text=log.read_text(); values=re.findall(r'^0x([0-9a-f]{16})$',text,re.M)
        require(len(values)==3 and int(values[0],16)==0,'Missing debug completion/retired counter values')
        require(f'RVV_MASK_PASS sew={sew} cases=5376 errors=0' in text and 'BOARD_REPLAY_PASS' in text,'Full original oracle not complete')
        require('BOARD_REPLAY_TRAP' not in text and 'RVV_MASK_FAIL' not in text,'Unexpected architectural failure')
        require('RVV_MASK_TRIAL vl=512 vstart=256' in text,'Historical printed boundary not visited')
        results.append(dict(name=name,status='PASS',configurations=5376,elapsed_s=seconds,isa=ISA,
            instructions_to_replay_exit=int(values[1],16),spike_cycles_to_replay_exit=int(values[2],16),
            elf_sha256=sha(elf),log_sha256=sha(log),command=list(map(str,cmd))))
    save(directory/'status.json',dict(status='SPIKE_FULL_ORIGINAL_SOURCE_PASS_NOT_DUT',results=results,
        total_configurations=16128,original_linux_replayed=False,VCS_launched=False))
    return results


def main(out):
    out=out.resolve(); require(out.is_relative_to(HERE) and out!=HERE and not out.exists(),'Fresh owned output required')
    evidence=provenance(); parent=prepare.check(PARENT)
    for p in [Path(__file__),HERE/'host_mock.c',BASE/'prepare.py',BASE/'run.py',CC.resolve(),SPIKE,
              ROOT/'verification/ara_verify/spike_probe.py',ROOT/'verification/tests/spike_vstart_probe.c']:
        if p.exists(): evidence['files'][str(p)]=sha(p)
    for n in ('startup.S','runtime.c','replay.ld'): evidence['files'][str(PARENT/n)]=sha(PARENT/n)
    out.mkdir(); prepared=out/'prepared'; prepared.mkdir()
    save(out/'original_provenance.json',evidence)
    for n in ('startup.S','runtime.c','replay.ld'): shutil.copyfile(PARENT/n,prepared/n)
    records=[]
    for name,(sew,lmul,cap) in zip(NAMES,SHAPES):
        case=prepared/name; original=case/'original'; original.mkdir(parents=True)
        shutil.copyfile(SOURCE/'mask_oracle.c',original/'mask_oracle.c')
        shutil.copyfile(SOURCE/'masks.py',original/'masks.py')
        shutil.copyfile(ARCH/'operations.h',original/'operations.h')
        shutil.copyfile(ARCH/(name+'.S'),original/'scenario.S')
        old=(original/'mask_oracle.c').read_text(); adapted=prepare.adapt(old,'ma_original')
        (case/'case.c').write_text(adapted)
        (case/'adaptation.diff').write_text(''.join(difflib.unified_diff(old.splitlines(True),adapted.splitlines(True),fromfile='original/mask_oracle.c',tofile='case.c')))
        (case/'main.c').write_text('\n'.join(['extern int ma_original_main(void);','extern void replay_text(const char *);',
            'extern volatile unsigned long replay_case;','int main(void) { unsigned long vlenb;',
            '__asm__ volatile("csrr %0,vlenb" : "=r"(vlenb));',
            'if(vlenb!=128) { replay_text("BOARD_REPLAY_VLEN_FAIL\\n"); return 90; }','replay_case=1;',
            f'replay_text("BOARD_CASE_BEGIN {name}\\n");','int status=ma_original_main();',
            f'if(status) {{ replay_text("BOARD_CASE_FAIL {name}\\n"); return status; }}',
            f'replay_text("BOARD_CASE_PASS {name}\\nBOARD_REPLAY_PASS\\n");','return 0;','}'])+'\n')
        records.append(dict(id=name,configurations=5376,sew=sew,lmul=lmul,cap=cap,full_original_loops=True))
    save(prepared/'provenance.json',dict(schema_version=1,cases=records,scope='Full original-source math matrices; not original Linux binaries',
        parent_runtime_sha256={n:parent['files'][n] for n in ('startup.S','runtime.c','replay.ld')},
        original_provenance_sha256=sha(out/'original_provenance.json'),
        files={str(p.relative_to(prepared)):sha(p) for p in prepared.rglob('*') if p.is_file()}))
    try:
        host_checks(prepared,out); build(prepared,out); results=spike_checks(out)
        for p,digest in evidence['files'].items(): require(sha(Path(p))==digest,'Input drift after reference: '+p)
        prepare.check(prepared)
        save(out/'status.json',dict(status='READY_HOST_SPIKE_PASS_NOT_DUT',results=results,configurations_per_elf=5376,
            soc_programs=str(out/'soc/programs.json'),VCS_launched=False,RTL_modified=False,
            source_pins_verified=len(evidence['files'])))
        print(json.dumps(dict(status='READY_HOST_SPIKE_PASS_NOT_DUT',results=results,soc_programs=str(out/'soc/programs.json')),indent=2))
    except Exception as error:
        save(out/'failure.json',dict(status='PREPARATION_NOT_PASS',error=str(error))); raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--out',type=Path,required=True)
    main(p.parse_args().out)
