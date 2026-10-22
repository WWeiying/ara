"""Host/integer byte oracle + real Sv39/RVV software-adapter Spike, not custom ISA."""
import argparse
import json
from pathlib import Path
import struct
import subprocess
from io import BytesIO
from elftools.elf.elffile import ELFFile
import preflight_akv_tile_range_capture as prior
import review_akv_canonical_alias794 as static

old=prior.old
ROOT,OUT,sha,require,save=old.ROOT,old.OUT,old.sha,old.require,old.save
APP=ROOT/'apps/riscv-tests/isa/rv64uv/vakv_canonical_alias794.c'
HOST_CHECKS,DUT_CHECKS=4241,4247
WORDS=[0x00b5205b,0x0005345b,0x0005385b,0x00053c5b,0x0000505b]
NAMES=['tohost','num_failed','g75_result','entropy_seed','entropy_snapshots','entropy_csrs','entropy_descriptors',
       'akva_pages','akva_root','akva_mid','akva_leaf','akva_saved','akva_restored','akva_traps','akva_trap_count','akva_va','akva_phase',
       'akva_handler','akva_ecall','akva_s_entry','akva_resume']


def page_bytes(s):
    return b''.join(struct.pack('<Q',int.from_bytes(old.source_bytes()[s*256+64+(i-8)*8:s*256+64+(i-7)*8],'little')
        if 8<=i<24 else 0x6969696969696969^(s<<32)^i) for i in range(512))


def frame(p):
    payload=bytearray(old.frame(0)[64:-64])
    if p:
        for s,r in enumerate((8,16,24)): payload[r*128:(r+1)*128]=page_bytes(s)[64:192]
    return struct.pack('<8Q',*(0xc100+p*16+i for i in range(8)))+payload+struct.pack('<8Q',*(0xc200+p*16+i for i in range(8)))


def page_tables(sym):
    root=[0]*512; mid=[[0]*512 for _ in range(2)]; leaf=[[0]*512 for _ in range(2)]
    def pte(a,flags): return (a>>12<<10)|flags
    root[2]=pte(0x80000000,0xcf)
    for phase in range(2):
        for stream,va in enumerate(static.ALIASES[phase]):
            root[va>>30&511]=pte(sym['akva_mid']+phase*4096,1)
            mid[phase][va>>21&511]=pte(sym['akva_leaf']+phase*4096,1)
            leaf[phase][va>>12&511]=pte(sym['akva_pages']+stream*4096,0xc7)
    return {'akva_root':struct.pack('<512Q',*root),'akva_mid':struct.pack('<1024Q',*(mid[0]+mid[1])),
            'akva_leaf':struct.pack('<1024Q',*(leaf[0]+leaf[1]))}


def translate(memory,satp,va):
    require(static.canonical(va) and satp>>60==8,'Canonical Sv39 enabled')
    table=(satp&((1<<44)-1))<<12
    for level in (2,1,0):
        addr=table+8*(va>>(12+level*9)&511)
        require(all(addr+i in memory for i in range(8)),'Complete PTE bytes')
        pte=int.from_bytes(bytes(memory[addr+i] for i in range(8)),'little')
        require(pte&1 and not(pte&4 and not pte&2) and not pte>>54,'Valid PTE, no reserved bits')
        if pte&0xe:
            require(pte&0xc2==0xc2 and not pte&0x10 and not pte&8,'Supervisor read/write non-executable payload, A/D set')
            pa=(pte>>10&((1<<44)-1))<<12
            require(pa&((1<<(12+level*9))-1)==0,'Aligned superpage')
            return pa|(va&((1<<(12+level*9))-1))
        table=(pte>>10&((1<<44)-1))<<12
    raise ValueError('No leaf')


def expected(sym):
    out={'g75_result':struct.pack('<2I',DUT_CHECKS,0),'num_failed':bytes(4),'tohost':struct.pack('<Q',1),
        'entropy_seed':struct.pack('<8Q',*(0xa100+i for i in range(8)))+old.frame(0)[64:-64]+struct.pack('<8Q',*(0xa200+i for i in range(8))),
        'akva_pages':b''.join(page_bytes(s) for s in range(3)),
        'entropy_snapshots':b''.join(frame(p) for p in range(4))+bytes(2*4224),
        'entropy_csrs':struct.pack('<24Q',*([21,0,64,8,2,1]*4))+bytes(12*8),
        'entropy_descriptors':b''.join(old.descriptor([v+64 for v in phase],128) for phase in static.ALIASES)+bytes(64),
        'akva_traps':struct.pack('<6Q',*([9,sym['akva_ecall'],0]*2)),
        'akva_trap_count':struct.pack('<Q',2),'akva_phase':struct.pack('<I',1),
        'akva_va':struct.pack('<6Q',*(static.ALIASES[0]+static.ALIASES[1]))}
    out.update(page_tables(sym)); return out


def validate_memory(memory,sym):
    for name,data in expected(sym).items():
        addr=sym[name]
        require(all(addr+i in memory for i in range(len(data))),'Full known oracle region '+name)
        require(bytes(memory[addr+i] for i in range(len(data)))==data,'Independent oracle differs '+name)
    before=bytes(memory[sym['akva_saved']+i] for i in range(64))
    after=bytes(memory[sym['akva_restored']+i] for i in range(64))
    require(before==after,'All machine CSRs restored')
    saved=struct.unpack('<8Q',before);require(saved[1]==0 and saved[0]&0x20088==0,'Bare/MIE/MPIE/MPRV starting contract')
    mappings=[];satp=(8<<60)|(sym['akva_root']>>12)
    for phase in range(2):
        for stream in range(3):
            va=static.ALIASES[phase][stream]+64; pa=sym['akva_pages']+stream*4096+64
            require(translate(memory,satp,va)==pa and translate(memory,satp,va+127)==pa+127,'Complete samePA payload extent')
            mappings.append(dict(phase=phase,stream=stream,va=va,pa=pa,size=128))
    return mappings


def trace_memory(commits):
    result={}
    for c in commits:
        for address,value in c.memory_accesses:
            if value is None:continue
            op=c.instruction&127; f3=c.instruction>>12&7
            if op==0x23:
                require(f3<=3,'Exact scalar store width');size=1<<f3
            else:
                require(op==0x27 and c.instruction&~((31<<15)|(31<<7))==0x02005027,'Only exact unmasked VSE16 snapshot stores')
                size=2
            require(0x80000000<=address and address+size<=0x80200000,'Every runtime store including stack within2MiB')
            for i in range(size):result[address+i]=value>>(8*i)&255
    return result


def elf_bytes(blob,address,size):
    elf=ELFFile(BytesIO(blob));matches=[s for s in elf.iter_segments() if s['p_type']=='PT_LOAD' and s['p_vaddr']<=address and address+size<=s['p_vaddr']+s['p_filesz']]
    require(len(matches)==1,'Unique file-backed opcode');s=matches[0];off=address-s['p_vaddr'];return s.data()[off:off+size]


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);out=p.parse_args().output.absolute()
    require(out.parent==OUT and not out.exists(),'Exclusive preflight')
    review=static.review()
    paths=[APP,old.APP,Path(__file__).resolve(),Path(static.__file__),Path(__file__).with_name('test_akv_canonical_alias794.py'),
        ROOT/'apps/common/akv_abi.h',ROOT/'apps/common/string.c',ROOT/'verification/tests/gap75_start.S',ROOT/'verification/tests/gap75.ld',
        old.shared.LLVM/'clang',old.shared.LLVM/'ld.lld',old.shared.LLVM/'llvm-objdump',old.shared.SPIKE,Path('/usr/bin/cc').resolve()]
    paths+=old.parser_dependencies()+[Path(old.__file__),Path(prior.__file__)]
    pins=old.shared.merge_pins(review['input_pins'],{str(f):sha(f) for f in paths});old.shared.check(pins);out.mkdir()
    def run(cmd,name,timeout=120):
        cmd=list(map(str,cmd));save(out/(name+'-command.json'),cmd)
        with (out/(name+'.stdout')).open('x') as so,(out/(name+'.stderr')).open('x') as se:subprocess.run(cmd,stdout=so,stderr=se,timeout=timeout,check=True)
    try:
        include='-I'+str(ROOT/'apps/common')
        run(['/usr/bin/cc','-O2','-DAKV_ENTROPY_SOFTWARE','-DAKV_ENTROPY_HOST',include,APP,'-o',out/'host'],'host-build')
        run([out/'host'],'host',30)
        require((out/'host.stdout').read_text()==f'AKV_ALIAS checks={HOST_CHECKS} errors=0\n','Host independent fulloracle')
        flags=['--target=riscv64-unknown-elf','-march=rv64gv_zfh_zvfh','-mabi=lp64d','-mcmodel=medany','-mno-relax','-msmall-data-limit=0','-O2',
            '-fno-vectorize','-fno-slp-vectorize','-ffreestanding','-fno-builtin','-mno-implicit-float','-fuse-ld=lld','-nostdlib',
            '-ffunction-sections','-fdata-sections','-Wl,--gc-sections',include,'-T'+str(ROOT/'verification/tests/gap75.ld'),ROOT/'verification/tests/gap75_start.S']
        for name,extra in [('input',[]),('software',['-DAKV_ENTROPY_SOFTWARE'])]:
            run([old.shared.LLVM/'clang',*flags,*extra,APP,ROOT/'apps/common/string.c','-o',out/(name+'.elf')],name+'-build')
        sym=old.symbols(out/'input.elf',NAMES+['akva_site_'+str(i) for i in range(5)]);sw=old.symbols(out/'software.elf',NAMES)
        for name,symbols in [('input',sym),('software',sw)]:
            blob=(out/(name+'.elf')).read_bytes();elf=ELFFile(BytesIO(blob))
            require(all(0x80000000<=s['p_paddr'] and s['p_paddr']+s['p_memsz']<0x80200000-8192 for s in elf.iter_segments() if s['p_type']=='PT_LOAD'),'Compiled2MiB ELF/BSS/stack separation')
        require(sha(out/'input.elf') not in json.loads((static.BASE/'admission-manifest.json').read_bytes())['input_pins'].values(),'No794 historical ELF hash duplicate')
        run([old.shared.LLVM/'llvm-objdump','-d',out/'input.elf'],'disassembly')
        for i,w in enumerate(WORDS): require(elf_bytes((out/'input.elf').read_bytes(),sym['akva_site_'+str(i)],4)==w.to_bytes(4,'little'),'Exact custom encodings')
        run([old.shared.SPIKE,'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0','-l','--log-commits',out/'software.elf'],'spike',180)
        cs=list(old.shared.parse_spike_commits(out/'spike.stderr'));mem=trace_memory(cs)
        with (out/'software.elf').open('rb') as f:
            elf=ELFFile(f)
            for seg in elf.iter_segments():
                if seg['p_type']=='PT_LOAD':
                    for i,v in enumerate(seg.data()+bytes(seg['p_memsz']-seg['p_filesz'])): mem.setdefault(seg['p_vaddr']+i,v)
        mappings=validate_memory(mem,sw)
        text=(out/'spike.stderr').read_text();traps=[]
        import re
        for m in re.finditer(r'^core\s+0:\s+exception\s+(trap_\w+),\s+epc\s+(0x[0-9a-f]+)\s*$',text,re.M):traps.append((m[1],int(m[2],16)))
        # This Spike build omits exception tval text; validate_memory independently
        # checks the handler's complete cause/PC/mtval records, including mtval=0.
        require(traps==[('trap_supervisor_ecall',sw['akva_ecall'])]*2,'Two precise cause9 S-ecall/PC owners with checked handler tval')
        require([v for c in cs for a,v in c.memory_accesses if a==sw['tohost'] and v is not None]==[1],'Unique terminal tohost1')
        validation=dict(status='SOFTWARE_ADAPTER_FULL_GOLD_PASS_NOT_NATIVE_CUSTOM',checks=DUT_CHECKS,host_checks=HOST_CHECKS,
            retired_instructions=len(cs),ecalls=2,VA_PA=mappings,full_VRF_frames=4,full_VRF_bytes=16384,source_guard_page_bytes=12288,
            native_custom_executed=False,full_native_scalar_qualified=False)
        save(out/'validation.json',validation);save(out/'target-review.json',review);old.shared.check(pins)
        save(out/'preflight-manifest.json',dict(status='AKV_CANONICAL_ALIAS794_PREFLIGHT_PASS_NOT_VCS',baseline=794,baseline_seal=static.BASE_SHA,
            input_elf=str(out/'input.elf'),software_elf=str(out/'software.elf'),symbols=sym,software_symbols=sw,
            pins=pins,output_pins={str(f):sha(f) for f in out.iterdir()},validation=validation,
            expected_commands=10,expected_ecalls=2,dut_checks=DUT_CHECKS,timeout_s=600,
            software_reference_is_not_native_Spike=True,EDA_launched=False,coverage_admitted=False))
        print(json.dumps(dict(output=str(out),seal=sha(out/'preflight-manifest.json'),validation=validation)))
    except Exception as exc:save(out/'failure.json',dict(status='PREFLIGHT_HOLD',reason=str(exc)));raise


if __name__=='__main__':main()
