#!/usr/bin/env python3
"""Software-only original265 preparation. Reference execution is a separate gate."""
import difflib
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/'comparison_alias_original'))
import prepare19 as base
from model import NAME, CAP, BOUND, model, require
sha = base.prepare.sha
def save(p, v):
    p.write_text(json.dumps(v, indent=2)+'\n')
def read(p):
    return json.loads(p.read_text())
CAMP = base.CAMP
ARCH = CAMP/'rvv_fp_comparisons_unboxed_v24_unmasked_01'
OLD = CAMP/'rvv_additions46/binaries/rvv_fp_compare_unboxed_unmasked_e16_mf4'
SOURCE = Path('/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix/fp_compare_oracle.c')
OLD_CC = Path('/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/host/bin/riscv64-buildroot-linux-gnu-gcc')
OBJDUMP = base.CC.with_name('riscv64-unknown-elf-objdump')
DEFS = ['SEW=16','UNMASKED_COMPARISONS=1','UNBOXED_COMPARISONS=1','RESTART_COMPARISONS=0','DESTINATION_KIND=0']
ISA = 'rv64gcv_zfh_zvfh_zvl1024b'
def disassemble(elf):
    txt = subprocess.check_output([str(OBJDUMP), '-d', str(elf)], text=True)
    code = {}
    functions = {}
    current = None
    for line in txt.splitlines():
        m = re.match(r'^([0-9a-f]+) <([^>]+)>:',line)
        if m:
            current=m[2]; functions[current]=[]
        m = re.match(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+(.*)',line)
        if m:
            row=dict(pc=int(m[1],16),insn=m[2],text=m[3])
            code[m[1]]=row
            if current: functions[current].append(row)
    nm=subprocess.check_output([str(base.CC.with_name('riscv64-unknown-elf-nm')),'-n',str(elf)],text=True)
    symbols={m[3]:int(m[1],16) for l in nm.splitlines() if (m:=re.match(r'^(\w+)\s+(\w)\s+(.+)$',l))}
    return dict(code=code,functions=functions,symbols=symbols,elf_sha256=sha(elf)),txt

def main():
    out=HERE/'software'
    require(not out.exists(),'Fresh software output only')
    pins={}
    def pin(p, expected=None):
        digest=sha(p); require(expected is None or digest==expected,'Identity: '+str(p)); pins[str(p)]=digest
    pin(SOURCE,'03cc50313dee7cda6476658bbe025409617242c06cd06cdaff8d83d2812e9bad')
    pin(OLD,'404b2c0bb8f9224dc5e281ad1ef83faee238dec1989b26b36d7dbc12e4c3b152')
    pin(ARCH/'manifest.json','13a460255abd3e2349c8a6108c3ed5f2a9174dc30648d347d7e7fb3900c0a489')
    pin(CAMP/'rvv_recovery08_11/terminal_scene/report.json','78feb29c49c69ee6d4e6dd7803a3bccf8d8c88566b10cbbfd639f630c1cda3e1')
    for p in (Path(base.__file__),Path(base.prepare.__file__),base.CC.resolve(),OLD_CC.resolve(),base.SPIKE,OBJDUMP,Path('/usr/bin/gcc').resolve(),HERE/'prepare.py',HERE/'model.py'):
        pin(p)
    out.mkdir(); original=out/'original'; original.mkdir()
    shutil.copyfile(SOURCE,original/'parent.c')
    for name,path,digest in (
        ('scenario.S',ARCH/'rvv_fp_compare_unboxed_unmasked_e16_mf4.S','33abaa5c662a3780ac82ea631fec6909a035ccbb6b9d656896ce0cb356808bbe'),
        ('operations.h',ARCH/'e16/operations.h','cd0e50739a57ccd54ead1092113528d6535ec62468e8fe4863dbb64fbf2fee64'),
        ('fixtures.h',ARCH/'e16/fixtures.h','5664c1a4546bb402fe64ef190ca8e4910efa21fc35daea5229a187377eba7cb1')):
        pin(path,digest); shutil.copyfile(path,original/name)
    defs=['-D'+d for d in DEFS]
    flags=['-Os','-march=rv64gcv','-mabi=lp64d','-nostdlib','-static','-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize','-msmall-data-limit=0','-Wl,--build-id=none','-Wall','-Wextra','-Werror']
    base.command([OLD_CC,*flags,'-Wl,-s',*defs,'-I'+str(original),original/'parent.c',original/'scenario.S','-o',out/'original_rebuilt.elf'],out/'original_rebuild.log')
    require(sha(out/'original_rebuilt.elf')==sha(OLD),'Original parent not byte identical')
    source=SOURCE.read_text(); point='        ++cases;\n    }\n'
    require(source.count(point)==1,'Prefix boundary')
    prefix=source.replace(point,'        ++cases;\n        if(cases==265)goto prefix_done;\n    }\nprefix_done:\n')
    port=base.adapt(prefix,NAME)
    oracle=source[source.index('        if((uint32_t)status)'):source.index('        ++cases;')]
    require(oracle in port,'Full original oracle changed')
    (out/'prefix.c').write_text(prefix); (out/'case.c').write_text(port)
    for label,a,b in [('prefix',source,prefix),('wrapper',prefix,port)]:
        (out/(label+'.diff')).write_text(''.join(difflib.unified_diff(a.splitlines(True),b.splitlines(True),fromfile=label+'_before',tofile=label+'_after')))
    for n in ('startup.S','runtime.c','replay.ld'):
        pin(base.BASE/n); shutil.copyfile(base.BASE/n,out/n)
    maintext='extern void replay_text(const char*);\nextern int '+NAME+'_main(void);\nint main(void){unsigned long vb;__asm__ volatile("csrr %0,vlenb":"=r"(vb));if(vb!=128){replay_text("BOARD_REPLAY_VLEN_FAIL\\n");return 90;}\nreplay_text("BOARD_CASE_BEGIN '+NAME+'\\n");\nif('+NAME+'_main()){replay_text("BOARD_CASE_FAIL '+NAME+'\\n");return 1;}replay_text("BOARD_CASE_PASS '+NAME+'\\nBOARD_REPLAY_PASS\\n");return 0;}\n'
    (out/'main.c').write_text(maintext)
    proof=dict(original_elf=dict(path=str(OLD),sha256=sha(OLD)),original_rebuild_byte_identical=True,
               source_sha256=sha(SOURCE),oracle_sha256=hashlib.sha256(oracle.encode()).hexdigest(),defines=DEFS,
               calls=265,predecessors=264,capacity=16,result_bits=4240,guards=530,actual_isa=ISA,
               scope='Original first265, not17920 parent or Linux execution')
    for backend in ('soc','spike'):
        dest=HERE/backend; dest.mkdir()
        elf=dest/(NAME+'.elf')
        extra=['-DSPIKE_REFERENCE=1'] if backend=='spike' else []
        base.command([base.CC,*flags,'-mcmodel=medany','-ffunction-sections','-fdata-sections','-Wl,--gc-sections','-T',out/'replay.ld',*defs,*extra,'-I'+str(original),out/'case.c',original/'scenario.S',out/'main.c',out/'startup.S',out/'runtime.c','-lgcc','-o',elf],dest/'compile.log')
        spec,txt=disassemble(elf); (dest/'program.dis').write_text(txt); save(dest/'elf.json',spec)
        entry=dict(path=str(elf),sha256=sha(elf),cases=[NAME],pass_markers=['RVV_FP_COMPARE_PASS sew=16 cases=265 errors=0','BOARD_CASE_PASS '+NAME,'BOARD_REPLAY_PASS'])
        save(dest/'programs.json',dict(programs={NAME:entry},backend=backend))
        proof[backend+'_elf']=entry
        require([len(spec['functions']['op_'+str(i)]) for i in range(10)]==[17]*4+[19]*6,'Original17/19 helper lengths')
        # The original helper region is relocatable and contains no external calls.
        oldtxt=subprocess.check_output([str(OBJDUMP),'-d',str(OLD)],text=True)
        oldcodes={int(m[1],16):m[2] for m in re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+',oldtxt,re.M)}
        starts=[0x10540+64*i for i in range(4)]+[0x10640+72*i for i in range(6)]
        for i,start in enumerate(starts):
            rows=spec['functions']['op_'+str(i)]; pc=start
            for r in rows:
                require(oldcodes[pc]==r['insn'],'Actual original helper bytes'); pc+=len(r['insn'])//2
        require([r['insn'] for r in spec['functions']['capacity']]==['52fd','00e2f557','8082'],'Capacity bytes')
    save(HERE/'model.json',model()); save(HERE/'source_elf_proof.json',proof)
    save(HERE/'baseline_pins.json',pins)
    print('SOFTWARE_COMPILED_ORIGINAL_BYTE_IDENTICAL_REFERENCE_NOT_RUN')
if __name__=='__main__': main()
