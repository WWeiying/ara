"""Small tile-range fixture preflight; software adapter is not custom Spike ISA."""
import argparse
import json
from pathlib import Path
import struct
import subprocess
from types import FunctionType

import build_akv_descriptor_entropy_preflight as old

ROOT, OUT, require, save = old.ROOT, old.OUT, old.require, old.save
APP = ROOT/'apps/riscv-tests/isa/rv64uv/vakv_tile_range_capture.c'
WORDS = [0x00b5205b]*4 + [0x0005345b, 0x0000505b]
INDICES = [0xffffffffffffffff, 2, 1, 0]
SW_CHECKS, DUT_CHECKS = 3864, 3872
NAMES = ['tohost','g75_result','num_failed','trap_fail','entropy_seed','entropy_sources',
         'entropy_descriptors','entropy_snapshots','entropy_csrs','entropy_status',
         'entropy_scan','entropy_trap_count','entropy_semantic_error','tile_observed_indices']


def expected(sym):
    seed = struct.pack('<8Q', *(0xa100+i for i in range(8))) + old.frame(0)[64:-64] + struct.pack('<8Q', *(0xa200+i for i in range(8)))
    bases = [sym['entropy_sources']+s*256+64 for s in range(3)]
    return {'tohost':struct.pack('<Q',1), 'g75_result':struct.pack('<2I',SW_CHECKS,0),
        'num_failed':bytes(4), 'entropy_seed':seed, 'entropy_sources':old.source_bytes(),
        'entropy_snapshots':b''.join(old.frame(p) for p in range(6)),
        'entropy_descriptors':old.descriptor(bases,128)*3,
        'entropy_csrs':struct.pack('<36Q',*([21,0,64,8,2,1]*6)),
        'entropy_status':struct.pack('<6I',1,1,1,0,0,0),
        'entropy_scan':struct.pack('<12I',*([512,0]*6)),
        'entropy_trap_count':struct.pack('<Q',3),
        'entropy_semantic_error':struct.pack('<I',11),
        'tile_observed_indices':struct.pack('<4Q',*INDICES)}


def validate_memory(mem, sym):
    for name, wanted in expected(sym).items():
        addr = sym[name]
        require(all(addr+i in mem for i in range(len(wanted))), 'Missing bytes: '+name)
        require(bytes(mem[addr+i] for i in range(len(wanted))) == wanted, 'Oracle differs: '+name)


def validate(commits, sym):
    require(commits and len(commits)<=100000 and not any(c.vector_writes or c.pc==sym['trap_fail'] for c in commits), 'Unexpected software execution')
    validate_memory(old.reuse.memory(commits),sym)
    terminal=[v for c in commits for a,v in c.memory_accesses if a==sym['tohost'] and v is not None]
    require(terminal==[1], 'Unique successful terminal')
    return dict(status='SOFTWARE_ADAPTER_PASS_NOT_NATIVE_CUSTOM',instructions=len(commits),checks=SW_CHECKS,
                full_VRF_frames=6,full_VRF_bytes=24576,CSR_bytes=288,semantic_TILE_RANGE=11,
                native_custom_executed=False,full_native_scalar_qualified=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    out=parser.parse_args().output.absolute()
    require(out.parent==OUT and not out.exists() and out.resolve()==out,'Fresh output required')
    deps=[APP,old.APP,Path(__file__),Path(__file__).with_name('test_preflight_akv_tile_range_capture.py'),
          ROOT/'apps/common/akv_abi.h',ROOT/'apps/common/string.c',ROOT/'verification/tests/gap75_start.S',
          ROOT/'verification/tests/gap75.ld',Path(old.__file__),*old.parser_dependencies(),
          old.shared.LLVM/'clang',old.shared.LLVM/'ld.lld',old.shared.LLVM/'llvm-objdump',old.shared.SPIKE,Path('/usr/bin/cc').resolve()]
    book_path=old.BUILD/'build-source-pins.json'
    book=json.loads(book_path.read_bytes())
    pins={str(p):old.sha(p) for p in deps+[book_path]}
    for rel in ['hardware/src/vlsu/akv/akv_engine.sv','hardware/include/akv_pkg.sv','hardware/src/vlsu/vlsu.sv']:
        p=ROOT/rel; require(old.sha(p)==book[str(p)],'Frozen source drift: '+rel); pins[str(p)]=book[str(p)]
    old.shared.check(pins); out.mkdir()
    def run(cmd,name,timeout=120):
        cmd=list(map(str,cmd)); save(out/(name+'-command.json'),cmd)
        with (out/(name+'.stdout')).open('x') as stdout,(out/(name+'.stderr')).open('x') as stderr:
            subprocess.run(cmd,stdout=stdout,stderr=stderr,timeout=timeout,check=True)
    try:
        include='-I'+str(ROOT/'apps/common')
        run(['/usr/bin/cc','-O2','-fno-tree-vectorize','-DAKV_ENTROPY_SOFTWARE','-DAKV_ENTROPY_HOST',include,APP,'-o',out/'host'],'host-build')
        run([out/'host'],'host',30)
        require((out/'host.stdout').read_text()==f'AKV_TILE_RANGE checks={SW_CHECKS} errors=0\n','Host oracle failure')
        flags=['--target=riscv64-unknown-elf','-march=rv64gv_zfh_zvfh','-mabi=lp64d','-mcmodel=medany',
               '-mno-relax','-msmall-data-limit=0','-O2','-fno-vectorize','-fno-slp-vectorize','-ffreestanding',
               '-fno-builtin','-mno-implicit-float','-fuse-ld=lld','-nostdlib','-ffunction-sections','-fdata-sections',
               '-Wl,--gc-sections',include,'-T'+str(ROOT/'verification/tests/gap75.ld'),ROOT/'verification/tests/gap75_start.S']
        for name,extra in [('input',[]),('software',['-DAKV_ENTROPY_SOFTWARE'])]:
            run([old.shared.LLVM/'clang',*flags,*extra,APP,ROOT/'apps/common/string.c','-o',out/(name+'.elf')],name+'-build')
        sw=old.symbols(out/'software.elf',NAMES)
        native=old.symbols(out/'input.elf',[n for n in NAMES if n!='entropy_semantic_error']+['tile_handler','tile_fault_pcs']+['tile_site_'+str(i) for i in range(6)])
        # Reuse the exact ELF scanner, changing only the pinned fixture's opcodes/site names.
        g=dict(old.native_sites.__globals__,WORDS=WORDS)
        scanner=FunctionType(old.native_sites.__code__,g)
        translated=dict(native,**{'entropy_site_'+str(i):native['tile_site_'+str(i)] for i in range(6)})
        sites=scanner((out/'input.elf').read_bytes(),translated)
        for i,s in enumerate(sites): s['fault']=i<3
        run([old.shared.LLVM/'llvm-objdump','-d',out/'input.elf'],'disassembly')
        run([old.shared.SPIKE,'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0','-l','--log-commits',out/'software.elf'],'spike',180)
        validation=validate(old.shared.parse_spike_commits(out/'spike.stderr'),sw)
        oracle=dict(indices=INDICES,native_sites=sites,trap_pcs=[native['tile_site_'+str(i)] for i in range(3)],cause=2,tval=0,
            rejected_FULL=dict(descriptor_AR_allowed=True,payload_AR=0,VRF_writes=0,error=11),
            recovery_FULL=dict(tile=0,Q_bytes=128,K_bytes=128,V_bytes=128),LOAD_VRF_bytes=128,
            required_native_probes=['command_fire','command_tile_start_i:64','requested_tile_start_q:64',
                'validation_error_q','context_ready_q','read_range_fire','read_range_vaddr','read_range_bytes'],
            capture_requires_preedge_input_and_postedge_requested_not_software_index_signature=True,
            native_protocol_and_architecture_still_pending=True)
        save(out/'spike-validation.json',validation); save(out/'oracle.json',oracle)
        old.shared.check(pins)
        pins.update({str(p):old.sha(p) for p in out.iterdir()})
        save(out/'preflight-manifest.json',dict(status='AKV_TILE_RANGE_SOFTWARE_PREFLIGHT_PASS_NOT_VCS',pins=pins,
            input_elf=str(out/'input.elf'),software_elf=str(out/'software.elf'),symbols=native,software_symbols=sw,
            validation=validation,oracle=oracle,dut_checks=DUT_CHECKS,dut_commands=6,dut_traps=3,
            timeout_seconds=600,EDA_launched=False,coverage_admitted=False,software_reference_is_not_native_Spike=True,
            full_native_protocol_qualified=False,historical_ELF_dedup_pending=True))
        print(json.dumps(dict(output=str(out),seal=old.sha(out/'preflight-manifest.json'),validation=validation)),flush=True)
    except Exception as exc:
        save(out/'failure.json',dict(status='PREFLIGHT_FAILED',reason=str(exc))); raise


if __name__=='__main__': main()
