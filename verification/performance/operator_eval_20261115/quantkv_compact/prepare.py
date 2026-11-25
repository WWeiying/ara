#!/usr/bin/env python3
"""Prepare only Q4/Q8 compact successors; never execute or stop simulators."""
import argparse
import difflib
import hashlib
import os
from pathlib import Path
import re
import shlex
import shutil
import struct
import subprocess
import sys

sys.dont_write_bytecode=True
from contract import HERE,ROOT,OUT,ELF_READER,ancestor,captured,require,sha,read,save,verify,module,elf_blob
from driver import derive,roi_source

OWN=('contract.py','driver.py','compare.h','prepare.py','check.py','test_compact.py','test_compare.c','README.md')


def audit_compare(helper):
    require('vle8.v' in helper and ('vmseq.vv' in helper or 'vmsne.vv' in helper) and
            'vfirst.m' in helper and 'e8,m8' in helper,'Missing bytewise RVV/VLA compare')
    require(not re.search(r'\b(?:mul|divu?|remu?|fence|csrrw[i]?|csrrs[i]?\s+x0,|csrrc[i]?)\b',helper) and
            not re.search(r'\s(?:fadd|fmul|fdiv|fcvt|vf(?!irst\.))[a-z0-9.]*\s',helper),
            'Compare changes flags/state or retains scalar hash')


def build(output,kind):
    output=Path(output).absolute(); old=ancestor(kind)
    require(output==output.resolve() and output.parent==OUT.resolve() and not output.exists() and
        re.fullmatch('operator_quantkv_compact_prepare_20261115_[A-Za-z0-9_.-]+',output.name),'Fresh owned output')
    original=read(old/'build.json'); inherited=read(old/'source-pins.json')
    require(original['state']=='BUILT_NOT_EXECUTED' and original['fixture']['kind']==kind and
        original['sdk_commit']=='dbe2b78817ef45b912444afcb85ad6e01a2be135' and original['sdk_overlays']=={} and
        sha(old/'source-pins.json')==original['source_pins_sha256'],'Frozen ancestor identity')
    verify(inherited); verify(original['artifacts'])
    for k in ('CPATH','C_INCLUDE_PATH','CPLUS_INCLUDE_PATH','LIBRARY_PATH','LD_PRELOAD','LD_LIBRARY_PATH',
              'GCC_EXEC_PREFIX','COMPILER_PATH','CFLAGS','LDFLAGS'):
        require(not os.environ.get(k),'Compiler environment injection: '+k)
    output.mkdir(); inputs=output/'inputs'; inputs.mkdir()
    pins=dict(inherited); commands=[]
    env=dict(PATH='/usr/bin:/bin',HOME=str(output),LC_ALL='C',PYTHONDONTWRITEBYTECODE='1')
    report=dict(state='FAIL',schema='quantkv-compact-v1',rtl_executed=False,target_executed=False,performance_measured=False)
    def pin(p):
        p=Path(p).resolve(strict=True); h=sha(p)
        require(str(p) not in pins or pins[str(p)]==h,'Input conflict: '+str(p)); pins[str(p)]=h
    def run(label,argv):
        argv=list(map(str,argv)); r=subprocess.run(argv,cwd=output,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
        (output/(label+'.log')).write_bytes(r.stdout); commands.append(dict(label=label,argv=argv,returncode=r.returncode))
        require(r.returncode==0,label+': '+r.stdout[-1800:].decode(errors='replace')); return r.stdout.decode()
    try:
        for p in (old/'build.json',old/'commands.json',old/'source-pins.json',Path(sys.executable),ELF_READER): pin(p)
        for name in OWN: pin(HERE/name); shutil.copyfile(HERE/name,inputs/name)
        shutil.copyfile(ELF_READER,inputs/'elf_reader.py')
        reader=module(inputs/'elf_reader.py','quantkv_build_elf')
        oldraw=Path(original['elf']).read_bytes(); parsed=reader.contract(oldraw)
        data=captured(kind,pin); payload=b''.join(data.values()); count=len(payload)
        require(count==(763904 if kind=='q4_0' else 894976),'Complete fixture byte count')
        begin=parsed['symbols']['fixture_begin']['address']; end=parsed['symbols']['fixture_end']['address']
        require(end-begin==count and elf_blob(oldraw,parsed,'fixture_begin',count)==payload,'Original ELF/capture layout')
        frozen=inputs/'ancestor'; shutil.copytree(old/'inputs',frozen)
        source=(old/'inputs/quant_main.c').read_text(); candidate=derive(source)
        (inputs/'quant_main.c').write_text(candidate)
        (output/'driver.patch').write_text(''.join(difflib.unified_diff(source.splitlines(True),candidate.splitlines(True),
            fromfile=str(old/'inputs/quant_main.c'),tofile=str(inputs/'quant_main.c'))))
        (inputs/'expected.bin').write_bytes(payload)
        constants=(0x514b4331,1,int(kind=='q4_0'),count,8,128,136,16,20,1024,64,384,
                   struct.unpack('<I',struct.pack('<f',2e-5))[0],0x3db504f3,0x00010100)
        asm=(old/'inputs/data.S').read_text().replace(str(old/'inputs'),str(frozen))
        asm+='\n.section .rodata.quantkv_expected,"a",@progbits\n.balign 64\n.global quantkv_expected_begin\nquantkv_expected_begin:\n'
        asm+='.incbin "'+str(inputs/'expected.bin')+'"\n.global quantkv_expected_end\nquantkv_expected_end:\n'
        asm+='.balign 8\n.global quantkv_contract\nquantkv_contract:\n.quad '+','.join(hex(v) for v in constants)+'\n'
        (inputs/'data.S').write_text(asm)
        (inputs/'fixture.h').write_text(f'#define QUANTKV_BYTES {count}u\n')
        # Retain the independently audited ELF contract without adding ROI instructions.
        candidate=candidate.replace('int main(void) {','int main(void) {\n  extern const uint64_t quantkv_contract[];\n  __asm__ volatile("" :: "r"(quantkv_contract) : "memory");',1)
        (inputs/'quant_main.c').write_text(candidate)
        (output/'driver.patch').write_text(''.join(difflib.unified_diff(source.splitlines(True),candidate.splitlines(True),
            fromfile=str(old/'inputs/quant_main.c'),tofile=str(inputs/'quant_main.c'))))
        require(roi_source(candidate)==roi_source(source),'ROI source drift')
        olddis=(old/'objdump.log').read_text(); lines=olddis.splitlines()
        excerpt=[]
        for line in lines:
            m=re.match(r'\s*([0-9a-f]+):',line)
            if m and any(a<=int(m[1],16)<b for a,b in ((0x800018e8,0x800018fa),(0x80001c02,0x80001c5a),
                                                       (0x80002024,0x80002038),(0x800003f2,0x80000410))): excerpt.append(line)
        (output/'ancestor-hotspots.dis').write_text('\n'.join(excerpt)+'\n')
        save(output/'diagnosis.json',dict(ancestor_elf_sha256=original['elf_sha256'],roi_markers=original['main_roi_toggle_pcs'],
            fnv_loop_pcs=[0x800018e8,0x80001c2c,0x80002024],all_fnv_loops_outside_roi=True,
            original_full_fixture_hashes=9,fixture_bytes=count,new_full_byte_comparisons=5,
            user_reported_progress=dict(cycle=19551101,order=12977228,pc='0x80001c2c..0x80001c38',
                byte_pointer='0x80030563..0x80030567',sample_bytes=108,sample_cycles=795),
            q4_projected_fnv_cycles=9*763904*795/108,projection_not_new_measurement=True,
            printf_finding='Earlier transient reverse-output stage; s7 is a stack byte pointer, not a digit count. No current printf hang established.',
            no_new_simulation=True,live_logs_pinned=False))
        recipe=[r for r in read(old/'commands.json') if '-c' in r['argv']]; objects=[]
        for i,r in enumerate(recipe):
            argv=[v.replace(str(old/'inputs'),str(frozen)) for v in r['argv']]
            si=argv.index('-c')+1
            if argv[si]==str(frozen/'quant_main.c'): argv[si]=str(inputs/'quant_main.c')
            if argv[si]==str(frozen/'data.S'): argv[si]=str(inputs/'data.S')
            argv.insert(1,'-I'+str(inputs)); si,oi=argv.index('-c')+1,argv.index('-o')+1
            obj=output/f'{i:02d}.o'; argv[oi]=str(obj); cc=Path(argv[0]); pin(cc)
            dep=output/f'{i:02d}.d'; deps=[v for j,v in enumerate(argv) if j not in (si-1,oi-1,oi)]+['-M','-MF',str(dep)]
            run(f'deps-{i:02d}',deps)
            for name in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]): pin(name)
            run(f'compile-{i:02d}',argv); objects.append(obj)
        require(len(objects)==13,'Ancestor compile recipe')
        original_link=next(r['argv'] for r in read(old/'commands.json') if r['label']=='link')
        link=[v.replace(str(old),str(output)).replace(str(output/'inputs'),str(frozen)) for v in original_link if not v.endswith('.o')]
        link[link.index('-Wl,--gc-sections'):link.index('-Wl,--gc-sections')]=list(map(str,objects))
        elf=output/'prefill.elf'; link[link.index('-o')+1]=str(elf); run('link',link)
        objdump=cc.with_name(cc.name.replace('gcc','objdump')); pin(objdump)
        dis=run('objdump',[objdump,'-d','-M','no-aliases,numeric',elf]); raw=elf.read_bytes(); parsed=reader.contract(raw)
        ranges={name:reader.extent(parsed,name) for name in ('main','quantkv_compare_bytes','qbs_native_execute_command','printf_')}
        a,b=ranges['quantkv_compare_bytes']; helper='\n'.join(line for line in dis.splitlines()
            for m in [re.match(r'\s*([0-9a-f]+):',line)] if m and a<=int(m[1],16)<b)
        audit_compare(helper)
        require('extensions_quant_hash' not in dis,'Old FNV helper retained')
        (output/'compare.dis').write_text(helper+'\n')
        first,last=ranges['main']; markers=sorted(pc for pc,w in parsed['words'].items() if first<=pc<last and w==0xc0002073)
        reads=sorted(pc for pc,w in parsed['words'].items() if first<=pc<last and w&0xfffff07f==0xc0002073 and w!=0xc0002073)
        require(len(markers)==len(reads)==2 and markers[0]<reads[0]<reads[1]<markers[1],'ROI sites/order')
        require(elf_blob(raw,parsed,'quantkv_expected_begin',count)==payload and
            parsed['symbols']['quantkv_expected_end']['address']-parsed['symbols']['quantkv_expected_begin']['address']==count and
            elf_blob(raw,parsed,'fixture_begin',count)==payload and
            parsed['symbols']['fixture_end']['address']<=parsed['symbols']['quantkv_expected_begin']['address'],'Independent complete expected copy')
        require(elf_blob(raw,parsed,'quantkv_contract',len(constants)*8)==struct.pack('<15Q',*constants),'ELF constants')
        offset=struct.unpack_from('<Q',raw,32)[0]; size,n=struct.unpack_from('<HH',raw,54)
        segments=[struct.unpack_from('<IIQQQQQQ',raw,offset+i*size) for i in range(n)]
        require(all(0x80000000<=p[3] and p[3]+p[6]<0x80ff0000 for p in segments if p[0]==1 and p[6]),'ELF outside 16MiB simulation RAM')
        for p in inputs.rglob('*'):
            if p.is_file(): pin(p)
        verify(pins); save(output/'source-pins.json',pins)
        report.update(state='BUILT_NOT_EXECUTED',kind=kind,ancestor=str(old),elf=str(elf),elf_sha256=sha(elf),fixture_bytes=count,
            constants=list(constants),elf_ranges=ranges,roi_marker_pcs=markers,roi_read_pcs=reads,
            roi_source_sha256=hashlib.sha256(roi_source(source).encode()).hexdigest(),
            source_pins_sha256=sha(output/'source-pins.json'),post_pins_match=True,
            scope='Same real quantKV SDK ABBA arithmetic; complete expected-byte and all1024 numerical checks outside ROI',
            actual_ggml_dispatch=False,runtime_admission=False)
    except Exception as exc: report['error']=str(exc)
    save(output/'commands.json',commands)
    report['artifacts']={str(p):sha(p) for p in output.rglob('*') if p.is_file()}; save(output/'build.json',report)
    if report['state']=='BUILT_NOT_EXECUTED':
        pins.update({str(output/'build.json'):sha(output/'build.json'),str(elf):sha(elf)})
        save(output/'run-source-pins.json',pins)
        save(output/'manifest.json',dict(cases=[dict(id='qwen3_'+kind+'_quantkv_compact_q16_19_kv0',category='quantkv_support',
            elf=str(elf),elf_sha256=sha(elf),source_pins=str(output/'run-source-pins.json'),timeout_seconds=10800,
            plusargs=['+QBS_PERF'],checker=[str(Path(sys.executable).resolve()),'-B',str(inputs/'check.py'),'--build',str(output),
                '--run','{run}','--log','{log}','--result','{result}'])]))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--kind',choices=('q4_0','q8_0'),required=True); p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); r=build(a.output,a.kind)
    print({k:r[k] for k in ('state','error','elf') if k in r}); raise SystemExit(r['state']!='BUILT_NOT_EXECUTED')
