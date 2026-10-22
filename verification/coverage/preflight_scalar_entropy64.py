"""Bounded RV64 integer/memory reference only; no VCS, OR or gain claim."""
import argparse
import json
from pathlib import Path
import subprocess
import build_gap98_preflight as build
import run_gap95_simulation as life

ROOT, OUT, need = life.ROOT, life.OUT, build.require
APP = ROOT/'apps/riscv-tests/isa/rv64uv/vscalar_entropy64.c'
TEMPLATE = OUT/'gap99-csr-satp-mprv-preflight-707-20261006-01/compile-command.json'
BOOK = OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
BOOK_SHA = '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'
MASK = (1<<64)-1
GUARD = 0x5a3c719de4b208f6


def words(phase,lane):
    need(phase in range(3) and lane in range(8),'Bounded matrix index')
    x = 0xaaaaaaaaaaaaaaaa if phase==1 else 0x5555555555555555
    n=7*lane
    x=((x<<n)|(x>>(64-n)))&MASK if n else x
    return [GUARD,*[x^(0x0101010101010101*w) for w in range(1,7)],GUARD]


def gold(phase,lane):
    w=words(phase,lane); x,y=w[1],w[2]|1
    return [(x+y)&MASK,(x-y)&MASK,x^y,(x*y)&MASK,x//y,x%y,(x*y)>>64,x&y]


def validate(commits,symbols):
    need(commits and not any(c.vector_writes or c.pc==symbols['trap_fail'] for c in commits),
         'Unexpected vector write or trap')
    writes={a:v for c in commits for a,v in c.memory_accesses if v is not None}
    def read(base,index):
        address=symbols[base]+8*index
        need(address in writes,'Missing complete observed word: '+base)
        return writes[address]
    for phase in range(3):
        for lane in range(8):
            need([read('entropy_results',(phase*8+lane)*8+op) for op in range(8)]==gold(phase,lane),
                 'Independent integer operation oracle differs')
    for lane in range(8):
        need([read('entropy_memory',8*lane+w) for w in range(8)]==words(2,lane),
             'Complete final memory/guards differ')
    need([read('entropy_csrs',i) for i in range(6)]==[read('entropy_csrs',i+6) for i in range(6)],
         'Complete CSR preservation differs')
    need([writes.get(symbols['g75_result']),writes.get(symbols['g75_result']+4),
          writes.get(symbols['num_failed']),writes.get(symbols['tohost'])]==[390,0,0,1],
         'Complete390 checks/success terminal required')
    return dict(instructions=len(commits),gpr_writes=sum(len(c.gpr_writes) for c in commits),
                checks=390,result_words=192,memory_words=64,csr_values=12)


def prepare(out):
    need(out.parent==OUT and not out.exists(),'Fresh reference output only')
    book=life.read_bound(BOOK,BOOK_SHA)
    rels=['hardware/deps/cva6/core/'+name for name in
          ('scoreboard.sv','issue_read_operands.sv','load_unit.sv','store_unit.sv','ariane_regfile_ff.sv',
           'cache_subsystem/wt_dcache_wbuffer.sv','cache_subsystem/wt_dcache_mem.sv')]
    pins={str(BOOK):BOOK_SHA,**{str(ROOT/r):book[str(ROOT/r)] for r in rels}}
    command=json.loads(TEMPLATE.read_bytes())
    old=str(ROOT/'apps/riscv-tests/isa/rv64uv/vgap99_csr_satp_mprv.c')
    need(command.count(old)==1,'Exact mature scalar build template')
    command=[str(APP) if a==old else str(out/'input.elf') if a.endswith('/input.elf') else a for a in command]
    files=[APP,TEMPLATE,Path(__file__).resolve(),Path(__file__).with_name('test_preflight_scalar_entropy64.py'),
           Path(command[0]),build.LLVM/'llvm-readelf',build.SPIKE,
           ROOT/'verification/tests/gap75_start.S',ROOT/'verification/tests/gap75.ld',
           Path(build.__file__).resolve(),Path(life.__file__).resolve()]
    for folder in ('apps/riscv-tests/isa/macros/vector','apps/riscv-tests/env','apps/common'):
        files.extend(p for p in (ROOT/folder).rglob('*') if p.is_file())
    pins=life.merge_pins(pins,{str(p):life.digest(p) for p in files});life.check(pins)
    out.mkdir();life.save(out/'input-pins.json',pins)
    try:
        life.save(out/'compile-command.json',command)
        with (out/'build.log').open('x') as stream:
            subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=120)
        elf=out/'input.elf'
        symbols={n:build._elf_symbol(elf,build.LLVM/'llvm-readelf',n) for n in
                 ('tohost','num_failed','g75_result','trap_fail','entropy_results','entropy_memory','entropy_csrs')}
        need(symbols['entropy_memory']%64==0 and all(0x80000000<=a<0xa0000000 for a in symbols.values()),
             'Aligned ordinary DRAM only')
        command=[str(build.SPIKE),'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0',
                 '-m0x80000000:0x20000000','-l','--log-commits',str(elf)]
        life.save(out/'spike-command.json',command)
        with (out/'spike.trace').open('x') as stream:
            subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=120)
        counts=validate(build.parse_spike_commits(out/'spike.trace'),symbols)
        need('exception ' not in (out/'spike.trace').read_text(),'No reference exceptions')
        life.check(pins)
        outputs={str(p):life.digest(p) for p in out.iterdir() if p.is_file()}
        q=dict(status='INTEGER64_MEMORY_SPIKE_PREFLIGHT_PASS_NOT_RTL',input_pins=pins,output_pins=outputs,
               symbols=symbols,counts=counts,RTL_changed=False,VCS_launched=False,coverage_admitted=False,
               potential_MDA_gain=None,ordinary_binary_data_already_covered_directions=6144,
               phase_contract='A/complement/A; eight ordinary cache lines, eight operations per lane',
               future_runtime_budget_seconds=600)
        life.save(out/'preflight.json',q)
        print(json.dumps(dict(output=str(out),seal=life.digest(out/'preflight.json'),counts=counts)),flush=True)
    except Exception as e:
        life.save(out/'failure.json',dict(reason=str(e),coverage_admitted=False));raise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    prepare(p.parse_args().output.resolve())
