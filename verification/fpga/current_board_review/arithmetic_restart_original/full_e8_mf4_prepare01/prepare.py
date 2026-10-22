#!/usr/bin/env python3
"""Full original e8 mf4 software only; reference is a separately gated step."""
import argparse
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
sys.dont_write_bytecode=True
from model import rows,require,fp,FP,CAP
HERE=Path(__file__).resolve().parent
PARENT=HERE.parent
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module;spec.loader.exec_module(module);return module
_local_prepare=sys.modules.pop('prepare',None)
old=load('immutable_arithmetic_prefix_prepare',PARENT/'prepare.py')
if _local_prepare is not None:sys.modules['prepare']=_local_prepare
CC,SPIKE,ARCH,REC=old.CC,old.SPIKE,old.ARCH,old.RECOVERY
ISA='rv64gcv_zvl1024b'
SHAPES=[dict(id='rvv_matrix_e8_mf4',sew=8,lmul='mf4',cap=CAP,calls=4095,steps=40000000,raw_bytes=6*1024**3)]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def save(p,data):
    with Path(p).open('x') as stream:json.dump(data,stream,indent=2);stream.write('\n')
def run(command,log,expect=0,timeout=90):
    command=list(map(str,command));record=dict(command=command,timeout_s=timeout)
    if log.exists():
        require(read(str(log)+'.command.json')==record and read(str(log)+'.exit.json')['returncode']==expect,
                'Existing software command is incomplete or differs; no automatic retry')
        return
    save(str(log)+'.command.json',record)
    start=time.monotonic()
    with log.open('x') as stream:result=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,timeout=timeout)
    save(str(log)+'.exit.json',dict(returncode=result.returncode,elapsed_s=time.monotonic()-start))
    require(result.returncode==expect,f'{log}: rc{result.returncode} expected{expect}')
def marker(p):return f'RVV_MATRIX_PASS sew={p["sew"]} vlmax={CAP} cases={p["calls"]} elements={CAP*p["calls"]} errors=0 seeds=3 guard_tail_mask_vstart=checked'
def disassemble(elf,out):
    run([CC.with_name('riscv64-unknown-elf-objdump'),'-d',elf],out)
    code={int(m[1],16):int(m[2],16) for m in re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s',out.read_text(),re.M)}
    text=subprocess.check_output([str(CC.with_name('riscv64-unknown-elf-nm')),'-n',str(elf)],text=True,timeout=20)
    symbols={m[2]:int(m[1],16) for m in re.finditer(r'^([0-9a-f]+)\s+\w\s+(\S+)$',text,re.M)}
    return code,symbols
def routine(code,symbols,name):
    pc=symbols[name];result=[]
    while len(result)<40:
        insn=code[pc];result.append(dict(pc=pc,insn=insn))
        if insn in (0x8082,0x00008067):return result
        pc+=4 if insn&3==3 else 2
    raise ValueError('Unbounded original routine')
def archived_window(code,window):
    want=[i['insn'] for i in window];ordered=sorted(code);matches=[]
    for pc in ordered:
        start=pc;found=[]
        for insn in want:
            if code.get(pc)!=insn:break
            found.append(dict(pc=pc,insn=insn));pc+=4 if insn&3==3 else 2
        else:matches.append(found)
    require(len(matches)==1,'Exact original helper window must match uniquely in stripped ELF')
    return matches[0]
def prerequisites():
    pins={}
    def pin(path,expected=None):
        actual=sha(path);require(expected is None or actual==expected,'Input drift '+str(path));pins[str(path)]=actual
    terminal=PARENT/'candidate04_plan01';complete=read(terminal/'complete.json')
    pin(PARENT/'TERMINAL_AUDIT01.md');pin(terminal/'complete.json','fbae6e7375e75ebd2fe6c098ab535514c7eb602181f30290f84676d078e81903')
    pin(terminal/'plan.json','34b4caf0f0810a3194449e58bc337b9cadb93d4a31847f70dc871b16c209e0b4')
    pin(terminal/'replay/run.json','12a7a6468e1a218e3f064603529615ecf2f2333af40031139b80171a0e32d5e1')
    pin(terminal/'replay/summary.json','7296b13e74c1cb283e7be8e5ddd68f16a1413e3cc06b2086a6b358cf7dc0a111')
    runmeta=read(terminal/'replay/run.json');summary=read(terminal/'replay/summary.json')
    require(complete['status']=='PASS_5_ARITHMETIC_PREFIXES_CANDIDATE04' and complete['pins_unchanged'] is True and
            runmeta['status']=='COMPLETE' and runmeta['status_counts']=={'PASS':5} and len(summary)==5,'Actual prefix5 terminal')
    for measured,s in zip(complete['results'],summary):
        require(s['name']==measured['name'] and s['status']==measured['status']=='PASS' and type(s['returncode']) is int and
                s['returncode']==measured['returncode']==0 and not s['reason'],'Prefix actual numeric0/results')
        root=terminal/'replay/tests'/s['name'];pin(root/'input.elf',measured['elf_sha256']);pin(root/'console.log',measured['console_sha256'])
        require('BOARD_REPLAY_PASS' in (root/'console.log').read_text(),'Prefix raw completion')
    pin(REC/'report.json','b11efd30ec97318d8d4cb37468ae39fea7085f6235fd79a68589e2a6455b8266')
    recovery=read(REC/'report.json');pin(REC/'reconstructed_oracle.c',recovery['reconstructed_c_sha256'])
    pin(ARCH/'manifest.json','6cabb1e462113d3e4c26b29622c6abcfba7cbedbc52fe7b3bfc860678b8a8ce6')
    manifest=read(ARCH/'manifest.json');require(len(recovery['results'])==len(manifest['cases'])==22,'Original22 identity')
    for c in manifest['cases']:
        rebuilt=next(x for x in recovery['results'] if x['name']==c['name'])
        require(rebuilt['exact_elf_equal'] and rebuilt['disassembly_equal'],'Missing reconstruction proof')
        for path in (REC/c['name'],ARCH/'overlay/opt/ara-tests'/c['name']):pin(path,c['sha256'])
    for p in (PARENT/'prepare.py',Path(old.helper.__file__),Path(old.helper.prepare.__file__),CC,SPIKE):pin(p)
    save(HERE/'prerequisites.json',dict(status='PREFIX5_TERMINAL_ACCEPTED_RECOVERY22_BYTES_VERIFIED',pins=pins,
        original_C_bytes_recovered=False,reconstructed_C_sha256=sha(REC/'reconstructed_oracle.c'),
        prefix_DUT_image='candidate04',prefix_calls=262,new_DUT_acceptance=False,
        CSV_reaudit=False,independent_terminal_report=str(PARENT/'TERMINAL_AUDIT01.md')))
    return pins
def prepare(resume=False):
    require(resume or not (HERE/'prerequisites.json').exists(),'No overwrite or automatic retry')
    pins=read(HERE/'prerequisites.json')['pins'] if resume else prerequisites()
    for path,digest in pins.items():require(sha(path)==digest,'Preflight pin drift '+path)
    runtime=HERE/'runtime';runtime.mkdir(exist_ok=resume)
    for name in ('startup.S','runtime.c','replay.ld'):
        source=PARENT.parent/'mask_alias_original/bounded01/prepared'/name
        if (runtime/name).exists():require(sha(runtime/name)==sha(source),'Runtime copy drift')
        else:shutil.copyfile(source,runtime/name)
        pins[str(source)]=sha(source)
    original=(REC/'reconstructed_oracle.c').read_text();adapted=old.runtime_adapt(original)
    require('prefix_complete' not in adapted and adapted.count('++checks;')==1,'No shortened loops')
    for p in SHAPES:
        root=HERE/p['id'];root.mkdir(exist_ok=resume);(root/'original').mkdir(exist_ok=resume)
        for src,dst in ((REC/'reconstructed_oracle.c','reconstructed_oracle.c'),(ARCH/(p['id']+'.S'),'scenario.S'),
                        (ARCH/f'e{p["sew"]}'/'operations.h','operations.h')):
            if (root/'original'/dst).exists():require(sha(root/'original'/dst)==sha(src),'Original copy drift')
            else:shutil.copyfile(src,root/'original'/dst)
            pins[str(src)]=sha(src)
        def emit(path,text):
            if path.exists():require(path.read_text()==text,'Generated source drift '+str(path))
            else:path.write_text(text)
        emit(root/'case.c',adapted)
        emit(root/'runtime.diff',''.join(difflib.unified_diff(original.splitlines(True),adapted.splitlines(True),fromfile='recovered',tofile='runtime_only')))
        emit(root/'main.c','extern int arithmetic_main(void);\nextern void replay_text(const char *);\n'
            'int main(void) { unsigned long n; __asm__ volatile("csrr %0,vlenb":"=r"(n));\n'
            'if(n!=128){replay_text("BOARD_REPLAY_VLEN_FAIL\\n");return 90;}\n'
            f'replay_text("BOARD_CASE_BEGIN {p["id"]}\\n");\nint r=arithmetic_main();\n'
            f'if(r){{replay_text("BOARD_CASE_FAIL {p["id"]}\\n");return r;}}\n'
            f'replay_text("ARITHMETIC_FULL_PASS {p["id"]}\\nBOARD_REPLAY_PASS\\n");return 0;}}\n')
        gold=rows(p['sew'])
        if (root/'model.json').exists():require(read(root/'model.json')==gold,'Model drift')
        else:save(root/'model.json',gold)
        if p['sew']==32:
            text=(root/'original/operations.h').read_text().split('fp_expected[10][64] = {')[1]
            archived=[int(x,16) for x in re.findall(r'UINT64_C\(0x([0-9a-f]+)\)',text)]
            require(archived==[fp(op,a,b) for op in range(25,35) for a in FP for b in FP],'Independent full FP table mismatch')
        host=root/'host';host.mkdir(exist_ok=resume)
        entries=['{'+f'{g["op"]},{g["vl"]},{g["vstart"]},UINT64_C({g["input_fnv64"]}),'+
                 '{'+','.join(str(v)+'u' for v in g['expected'])+'}}' for g in gold]
        emit(host/'host_rows.h',f'#define COUNT {len(gold)}\nstruct row {{ unsigned op,vl,start; uint64_t hash; word out[{CAP}]; }};\n'
            'static const struct row expected_rows[COUNT]={\n'+',\n'.join(entries)+'\n};\n')
        run(['/usr/bin/cc','-O2','-Wall','-Wextra','-Werror',f'-DSEW={p["sew"]}','-I'+str(root/'original'),
             '-I'+str(host),root/'case.c',HERE/'host_model.c','-o',host/'model'],host/'compile.log')
        run([host/'model'],host/'positive.log')
        require(marker(p) in (host/'positive.log').read_text(),'Full Host oracle marker')
        for mutation in range(1,10 if p['sew']==32 else 9):
            run([host/'model',str(mutation)],host/f'negative{mutation}.log',expect=1)
            require('injected=1 result=1' in (host/f'negative{mutation}.log').read_text(),'Missed oracle counterexample')
        originalelf=ARCH/'overlay/opt/ara-tests'/p['id'];oc,os=disassemble(originalelf,root/'original/program.dis')
        proof=dict(original_elf=str(originalelf),original_sha256=sha(originalelf),case=p,backends={},
            original_C_bytes_recovered=False,byte_equivalent_original_reconstruction=True,
            full_order_preserved=True,partitioned=False)
        for backend in ('soc','spike'):
            directory=root/backend;directory.mkdir(exist_ok=resume);elf=directory/'program.elf'
            flags=['-Os','-march=rv64gcv','-mabi=lp64d','-mcmodel=medany','-ffreestanding','-fno-builtin',
                '-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize','-msmall-data-limit=0',
                '-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror','-nostdlib','-static',
                '-Wl,--build-id=none','-Wl,--gc-sections','-T',runtime/'replay.ld',f'-DSEW={p["sew"]}',
                '-I'+str(root/'original')]
            if backend=='spike':flags.append('-DSPIKE_REFERENCE=1')
            run([CC,*flags,root/'case.c',root/'original/scenario.S',root/'main.c',runtime/'startup.S',runtime/'runtime.c','-lgcc','-o',elf],directory/'compile.log')
            code,symbols=disassemble(elf,directory/'program.dis')
            if (directory/'symbols.json').exists():require(read(directory/'symbols.json')==symbols,'ELF symbols drift')
            else:save(directory/'symbols.json',symbols)
            helpers={name:routine(code,symbols,name) for name in ['capacity']+[f'op_{i}' for i in range(25 if p['sew']<32 else 35)]}
            for name,window in helpers.items():
                before=archived_window(oc,window)
                require([i['insn'] for i in window]==[i['insn'] for i in before],'Original helper encoding drift '+name)
                require(len(window)==(3 if name=='capacity' else 13),'Original helper length')
            proof['backends'][backend]=dict(elf=str(elf),sha256=sha(elf),helpers=helpers,symbols=symbols,
                all_helper_instructions_equal_original=True,code={str(pc):insn for pc,insn in code.items()})
        proof['original_stripped_ELF_window_matching']=True
        save(root/'sourceproof.json',proof)
    save(HERE/'input_pins.json',pins)
    for path,digest in pins.items():require(sha(path)==digest,'Input changed '+path)
    save(HERE/'software_status.json',dict(status='HOST_COMPILED_NOT_REFERENCE_NOT_DUT',cases=SHAPES,
         host_positive=1,host_negative=8,full_calls=4095,full_results=131040,full_guards=8190,
         reference_started=False))
    print('HOST_COMPILED_NOT_REFERENCE_NOT_DUT',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--resume-after-stripped-original',action='store_true')
    prepare(parser.parse_args().resume_after_stripped_original)
