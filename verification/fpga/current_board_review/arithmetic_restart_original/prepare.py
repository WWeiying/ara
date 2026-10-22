#!/usr/bin/env python3
"""Freeze bounded, binary-reconstructed original RVV-02 prefixes; no DUT launch."""
import argparse
import difflib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('alias_port_helpers', HERE.parent / 'mask_alias_original/port.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
sha, save, run, require = helper.sha, helper.save, helper.run, helper.require
CAMP, SOURCE, CC, SPIKE, ISA = helper.CAMP, helper.SOURCE, helper.CC, helper.SPIKE, helper.ISA
ARCH = CAMP / 'rvv_extended04'
RECOVERY = HERE / 'recovery22'
SHAPES = ((8,'m4',512,56,'measured_e8_m4_trace'),
          (8,'m8',1024,38,'stalled_shape_predicted_trial'),
          (16,'m8',512,56,'stalled_shape_predicted_trial'),
          (8,'m2',256,56,'historically_passed_shape_control'),
          (16,'m4',256,56,'historically_passed_shape_control'))


def parts():
    return [dict(id=f'arithmetic_e{s}_{m}_prefix{n}', original=f'rvv_matrix_e{s}_{m}',
                 sew=s,lmul=m,cap=c,configurations=n,first_trial=0,last_trial=n-1,
                 provenance_status=status, target='vadd.vv v24,v8,v16,v0.t', opcode='00880c57',
                 last_tuple=dict(seed=0,op=0,vl=512 if c>=512 else 256,mode=0,
                                 vstart=256 if c>=512 else 128))
            for s,m,c,n,status in SHAPES]


def replace(s, old, new):
    require(s.count(old)==1,'Unexpected source shape: '+old)
    return s.replace(old,new)


def runtime_adapt(s):
    begin,end=s.index('static long syscall3('),s.index('static void text(')
    s=s[:begin]+'extern long replay_write(long,long,long,long);\n#define syscall3 replay_write\n'+s[end:]
    begin,end=s.index('static void finish('),s.index('static int64_t signed_word(')
    s=s[:begin]+s[end:]
    s=replace(s,'void probe_main(void)', 'int arithmetic_main(void)')
    s=replace(s,'finish(2);','return 2;')
    s=replace(s,'finish(errors ? 1:0);','return errors ? 1:0;')
    s=s[:s.index('__asm__(".global _start')]
    # TRACE_OP0 is disabled in this original base matrix. Keep no unhandled service.
    s=replace(s,'syscall3(29,1,0x5409,1);','/* Optional Linux tty drain absent in bare metal. */')
    require('ecall' not in s and 'finish(' not in s,'Unadapted service')
    return s


def bound(s, count):
    s=replace(s,'                    ++checks;',
              f'                    ++checks;\n                    if(checks=={count}) goto prefix_complete;')
    return replace(s,'    text(errors ? "RVV_MATRIX_FAILED',
                     'prefix_complete:\n    text(errors ? "RVV_MATRIX_FAILED')


def marker(p):
    return (f'RVV_MATRIX_PASS sew={p["sew"]} vlmax={p["cap"]} cases={p["configurations"]}'
            f' elements={p["cap"]*p["configurations"]} errors=0 seeds=3 guard_tail_mask_vstart=checked')


def pins_and_identity(out):
    pins={}
    def pin(path,expected=None):
        digest=sha(path)
        require(expected is None or digest==expected,'Identity mismatch: '+str(path))
        pins[str(path)]=digest
    manifest=json.loads((ARCH/'manifest.json').read_text())
    recovery=json.loads((RECOVERY/'report.json').read_text())
    require(len(manifest['cases'])==len(recovery['results'])==22,'Wrong original shape inventory')
    require(all(r['exact_elf_equal'] and r['disassembly_equal'] for r in recovery['results']),
            'Original full binaries not reconstructed')
    pin(RECOVERY/'reconstructed_oracle.c',recovery['reconstructed_c_sha256'])
    for path in (RECOVERY/'report.json',HERE/'recover.py',HERE/'prepare.py',HERE/'host_model.c',
                 SOURCE/'build.py',SOURCE/'ISSUES.md',ARCH/'manifest.json',ARCH/'transfer_manifest.json',
                 CAMP/'HARDWARE_FINDINGS.md',CC,SPIKE,Path(helper.__file__),Path(helper.prepare.__file__)):
        pin(path)
    for directory,names in ((ARCH,('report.json','m8_report.json','resume02_report.json','resume03_report.json',
                                  'reference_512.json','reference_1024.json','snapshot_1.json','snapshot_2.json',
                                  'm8_snapshot_1.json','m8_snapshot_2.json')),
                            (CAMP/'rvv_trace02',('manifest.json','report.json','uart.bin','rvv_matrix_e8_m4.S'))):
        for name in names: pin(directory/name)
    spec=importlib.util.spec_from_file_location('surviving_original_generator',SOURCE/'build.py')
    generator=importlib.util.module_from_spec(spec); spec.loader.exec_module(generator)
    original22=[]
    for entry in manifest['cases']:
        name=entry['name']; elf=ARCH/'overlay/opt/ara-tests'/name
        assembly=ARCH/(name+'.S'); header=ARCH/f'e{entry["sew"]}'/'operations.h'
        pin(elf,entry['sha256']); pin(RECOVERY/name,entry['sha256']); pin(assembly); pin(header)
        pin(Path(entry['command'][0]))
        require(generator.assembly(entry['sew'],entry['lmul'])==assembly.read_text(),
                'Surviving generator assembly drift: '+name)
        original22.append(dict(**entry,assembly=str(assembly),assembly_sha256=sha(assembly),
                               original_elf=str(elf),header_sha256=sha(header),
                               full_elf_byte_reconstructed=True))
    trace=CAMP/'rvv_trace02'
    traced=json.loads((trace/'manifest.json').read_text())['cases'][0]
    pin(trace/'overlay/opt/ara-tests'/traced['name'],traced['sha256'])
    require((trace/'rvv_matrix_e8_m4.S').read_bytes()==(ARCH/'rvv_matrix_e8_m4.S').read_bytes(),
            'Trace uses different assembly')
    uart=(trace/'uart.bin').read_bytes().decode(errors='replace')
    trials=re.findall(r'RVV_TRIAL seed=(\d+) vl=(\d+) mask=(\d+) vstart=(\d+) completed=(\d+)',uart)
    require(len(trials)==56 and trials[-1]==('0','512','0','256','55'),'Trace provenance mismatch')
    save(out/'original_identity.json',dict(original22=original22,trace_elf=traced,trace_trials=trials,
         source_bytes_recovered=False,original_source_sha256=manifest['source_sha256'],
         reconstructed_c_sha256=sha(RECOVERY/'reconstructed_oracle.c'),
         reconstruction_proof='All 22 complete Linux ELF bytes equal archived SHA256; no execution implied',
         generator_bytes_recovered=False,generator_assembly_equal_all22=True))
    return pins


def expected(p):
    cap,sew=p['cap'],p['sew']; mod=(1<<sew)-1; m64=(1<<64)-1
    rng=0x937ad68de41c725f; a=[]; b=[]
    for i in range(cap):
        rng^=(rng<<13)&m64; rng^=rng>>7; rng^=(rng<<17)&m64
        x,y=rng&mod,(rng>>19)&mod
        if i%8==0: x=y=0
        elif i%8==1: x,y=mod,1
        elif i%8==2: x,y=1<<(sew-1),mod
        elif i%8==3: y=sew
        a.append(x); b.append(y)
    rows=[]; tuples=[]
    data=b''.join(x.to_bytes(sew//8,'little') for x in a+b)
    old=b''.join((0x5b).to_bytes(sew//8,'little') for _ in range(cap+2))
    for vl in (0,1,2,3,cap//2,cap-1,cap):
        for mode in range(3):
            mask=bytearray(128)
            for i in range(cap):
                if mode==0 or (mode==1 and i%2) or (mode==2 and i%7==2): mask[i//8]|=1<<(i%8)
            h=helper.fnv(data+mask+old)
            for start in (0,vl//2,vl if vl<cap else cap-1):
                n=len(rows); rows.append(f'CALL {n} 0 {vl} {start} {h:016x}')
                tuples.append(dict(trial=n,seed=0,op=0,vl=vl,mode=mode,vstart=start,input_fnv64=f'{h:016x}'))
    return rows[:p['configurations']],tuples[:p['configurations']]


def host(prepared,out,ps):
    directory=out/'host'; directory.mkdir(); positives=[]; negatives=[]
    for p in ps:
        name=p['id']; case=prepared/name; want,tuples=expected(p)
        save(directory/(name+'.inputs.json'),tuples)
        for mode,source in (('prefix',case/'case.c'),('full_capture',case/'runtime_only.c')):
            exe=directory/(name+'.'+mode)
            cmd=['/usr/bin/cc','-O2','-Wall','-Wextra','-Werror',f'-DSEW={p["sew"]}',
                 f'-DCAP={p["cap"]}',f'-DCOUNT={p["configurations"]}','-I'+str(case/'original')]
            if mode=='full_capture':cmd.append('-DFULL_CAPTURE=1')
            run(cmd+[source,HERE/'host_model.c','-o',exe],directory/(exe.name+'.compile.log'))
            log=directory/(exe.name+'.log');run([exe],log)
            text=log.read_text(); rows=[s for s in text.splitlines() if s.startswith('CALL ')]
            require(rows==want,'Input or operation order mismatch: '+name+' '+mode)
            require('RVV_MATRIX_FAIL' not in text and f'HOST_END calls={p["configurations"]} injected=0 result=0' in text,
                    'Host original oracle failure')
            if mode=='prefix':require(marker(p) in text,'Host completion missing')
            positives.append(dict(name=name,mode=mode,calls=len(rows),status='PASS'))
        for mutation,label in enumerate(('active','prestart','maskedoff','tail','left_guard','right_guard',
                                          'vstart_low','vstart_high'),1):
            log=directory/(name+'.negative_'+label+'.log')
            run([directory/(name+'.prefix'),str(mutation)],log,expected=1)
            text=log.read_text()
            require('RVV_MATRIX_FAIL' in text and 'injected=1 result=1' in text,'Oracle failed to reject '+label)
            negatives.append(dict(name=name,mutation=label,rejected=True))
    save(directory/'status.json',dict(status='HOST_PASS_NOT_VECTOR_EXECUTION',positive=positives,negative=negatives))


def build(prepared,out,ps):
    flags=['-Os','-march=rv64gcv','-mabi=lp64d','-mcmodel=medany','-ffreestanding','-fno-builtin',
           '-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize','-msmall-data-limit=0',
           '-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror','-nostdlib','-static',
           '-Wl,--build-id=none','-Wl,--gc-sections','-T',prepared/'replay.ld']
    for backend in ('soc','spike'):
        directory=out/backend;directory.mkdir();entries={}
        for p in ps:
            name=p['id'];case=prepared/name;elf=directory/(name+'.elf')
            cmd=[CC,*flags,f'-DSEW={p["sew"]}','-I'+str(case/'original')]
            if backend=='spike':cmd.append('-DSPIKE_REFERENCE=1')
            cmd += [case/'case.c',case/'original/scenario.S',case/'main.c',prepared/'startup.S',prepared/'runtime.c',
                    '-lgcc','-o',elf]
            run(cmd,directory/(name+'.compile.log'))
            run([CC.with_name('riscv64-unknown-elf-objdump'),'-d',elf],directory/(name+'.dis'))
            nm=subprocess.check_output([CC.with_name('riscv64-unknown-elf-nm'),'-n',elf],text=True,timeout=15)
            symbols={m[3]:int(m[1],16) for m in re.finditer(r'^([0-9a-f]+)\s+(\w)\s+(\S+)$',nm,re.M)}
            require(symbols['__bss_end']<0x800f0000,'Runtime memory bound')
            save(directory/(name+'.symbols.json'),symbols)
            dis=(directory/(name+'.dis')).read_text()
            body=dis.split('<op_0>:\n')[1].split('\n\n')[0]
            match=re.search(r'^\s*([0-9a-f]+):\s+00880c57\s+vadd.vv\s+v24,v8,v16,v0.t',body,re.M)
            require(match is not None,'Original target opcode missing')
            entries[name]=dict(path=str(elf),sha256=sha(elf),cases=[name],configurations=p['configurations'],
                               target_pc=int(match[1],16),target_opcode=p['opcode'],
                               pass_markers=[marker(p),f'ARITHMETIC_PREFIX_PASS {name} trials={p["configurations"]}',
                                             f'BOARD_CASE_PASS {name}','BOARD_REPLAY_PASS'])
        save(directory/'programs.json',dict(schema_version=1,backend='vcs-soc' if backend=='soc' else 'spike-htif',
             programs=entries,prepared=str(prepared),provenance_sha256=sha(prepared/'provenance.json'),
             compiler=dict(path=str(CC),sha256=sha(CC)),vcs_started=False))


def reference(out,ps):
    directory=out/'reference';directory.mkdir(); results=[]
    sys.path.insert(0,str(helper.ROOT/'verification'))
    from ara_verify.spike_probe import check_spike_vstart,probe_paths
    cc,source=probe_paths(helper.ROOT)
    probe=check_spike_vstart(SPIKE,cc,directory/'vstart_probe',source)
    require(probe['status']=='PASS','Unsupported Spike vstart')
    for p in ps:
        name=p['id'];elf=out/'spike'/(name+'.elf')
        symbols=json.loads((out/'spike'/(name+'.symbols.json')).read_text())
        commands=directory/(name+'.cmd')
        commands.write_text(f'until pc 0 {symbols["replay_exit"]:x}\nreg 0 a0\nreg 0 minstret\nreg 0 mcycle\nstr {symbols["replay_log"]:x}\nrs\n')
        log=directory/(name+'.log')
        seconds=run([SPIKE,'-d','--debug-cmd='+str(commands),'--isa='+ISA,'-m2',elf],log,timeout=120)
        text=log.read_text(); values=re.findall(r'^0x([0-9a-f]{16})$',text,re.M)
        require(len(values)==3 and int(values[0],16)==0,'Spike exit/counter failure')
        entries=json.loads((out/'spike/programs.json').read_text())['programs']
        for token in entries[name]['pass_markers']:require(text.count(token)==1,'Reference marker: '+token)
        require(not re.search(r'FAIL|TRAP|Error|FATAL',text),'Reference raw failure')
        results.append(dict(name=name,status='PASS',configurations=p['configurations'],
                            instructions_to_replay_exit=int(values[1],16),elapsed_s=seconds,
                            isa=ISA,elf_sha256=sha(elf),log_sha256=sha(log)))
    save(directory/'status.json',dict(status='SPIKE_PASS_NOT_DUT',results=results))
    return results


def main(out):
    out=out.resolve();require(out.is_relative_to(HERE) and out!=HERE and not out.exists(),'Fresh owned output required')
    out.mkdir();ps=parts();pins=pins_and_identity(out)
    prepared=out/'prepared';prepared.mkdir()
    # Reuse the already accepted immutable bare-metal startup/runtime verbatim.
    parent=HERE.parent/'mask_alias_original/bounded01/prepared'
    helper.prepare.check(parent)
    for name in ('startup.S','runtime.c','replay.ld'):
        shutil.copyfile(parent/name,prepared/name);pins[str(parent/name)]=sha(parent/name)
    recovered=(RECOVERY/'reconstructed_oracle.c').read_text();runtime=runtime_adapt(recovered)
    for p in ps:
        name=p['id'];case=prepared/name;original=case/'original';original.mkdir(parents=True)
        shutil.copyfile(ARCH/(p['original']+'.S'),original/'scenario.S')
        shutil.copyfile(ARCH/f'e{p["sew"]}'/'operations.h',original/'operations.h')
        shutil.copyfile(RECOVERY/'reconstructed_oracle.c',original/'reconstructed_oracle.c')
        (case/'runtime_only.c').write_text(runtime)
        source=bound(runtime,p['configurations']);(case/'case.c').write_text(source)
        for label,old,new in (('runtime_adaptation',recovered,runtime),('prefix',runtime,source)):
            (case/(label+'.diff')).write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),
                                                                       fromfile='before',tofile='after')))
        (case/'main.c').write_text('\n'.join([
            'extern int arithmetic_main(void);','extern void replay_text(const char *);',
            'extern volatile unsigned long replay_case;','int main(void) { unsigned long vlenb;',
            '__asm__ volatile("csrr %0,vlenb":"=r"(vlenb));',
            'if(vlenb!=128) { replay_text("BOARD_REPLAY_VLEN_FAIL\\n"); return 90; }','replay_case=1;',
            f'replay_text("BOARD_CASE_BEGIN {name}\\n");','int result=arithmetic_main();',
            f'if(result) {{ replay_text("BOARD_CASE_FAIL {name}\\n"); return result; }}',
            f'replay_text("ARITHMETIC_PREFIX_PASS {name} trials={p["configurations"]}\\nBOARD_CASE_PASS {name}\\nBOARD_REPLAY_PASS\\n");',
            'return 0;','}'])+'\n')
    save(out/'input_pins.json',pins)
    save(prepared/'provenance.json',dict(schema_version=1,cases=ps,vlen=1024,nr_lanes=4,
          scope='Original contiguous prefixes; binary-reconstructed source, not full Linux replay',
          original_identity_sha256=sha(out/'original_identity.json'),input_pins_sha256=sha(out/'input_pins.json'),
          files={str(p.relative_to(prepared)):sha(p) for p in prepared.rglob('*') if p.is_file()}))
    try:
        host(prepared,out,ps);build(prepared,out,ps);results=reference(out,ps)
        for path,digest in pins.items():require(sha(Path(path))==digest,'Input drift: '+path)
        helper.prepare.check(prepared)
        status=dict(status='READY_5_ORIGINAL_PREFIXES_HOST_SPIKE_NOT_DUT',results=results,
                    soc_programs=str(out/'soc/programs.json'),soc_programs_sha256=sha(out/'soc/programs.json'),
                    original_full_matrices_executed=False,VCS_launched=False,RTL_modified=False)
        save(out/'status.json',status);print(json.dumps(status,indent=2))
    except Exception as error:
        save(out/'failure.json',dict(status='NOT_PASS',error=str(error)));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
    main(parser.parse_args().out)
