"""Software-only reference for one mixed FMA/DIV/FCLASS arbitration case."""
import argparse
import json
from pathlib import Path
import subprocess

import run_scalar_fpu_backpressure as prior

life, build, old = prior.life, prior.build, prior.old
ROOT = life.ROOT
APP = ROOT / 'apps/riscv-tests/isa/rv64uv/scalar_fpu_fma_arbiter792.c'
BASE = life.OUT / 'scalar-misalign-offline-admitted792-agent-20261008-01'
BASE_SHA = '0aadd9e4fa71a5a582830a043fedc67669b0f53cea866a1b8147a5526c8f81f4'
C_VALUES = (0x5555555555555555, 0xaaaaaaaaaaaaaaaa)
DEST = (5,6,10,11,12,13,14,15,16,17,7,28,29,30,5,6,7,28,29,30)


def validate(commits, symbols):
    commits = list(commits)
    writes = {a:v for c in commits for a,v in c.memory_accesses if v is not None}
    assert all(c.instruction & 3 == 3 for c in commits), 'No-C reference required'
    assert not any(c.vector_writes or c.pc == symbols['trap_fail'] for c in commits)
    for b, expected in enumerate(C_VALUES):
        start, end = symbols['arb_batch%d'%b], symbols['arb_end%d'%b]
        operations = [c for c in commits if start <= c.pc < end]
        assert len(operations) == 25 and [c.pc for c in operations] == list(range(start,end,4))
        div = operations[0]
        assert div.instruction & 0x7f == 0x53 and div.instruction >> 25 == 0x0d
        assert (div.instruction >> 12) & 7 == 0
        assert (div.instruction >> 15) & 31 == 3 and (div.instruction >> 20) & 31 == 4
        assert div.fpr_writes == {31:0x3ff0000000000000}
        fmas = []
        classes = []
        for c in operations[1:]:
            w = c.instruction
            if w & 0x7f == 0x43:
                assert (w >> 25) & 3 == 1 and (w >> 12) & 7 == 0
                assert (w >> 15) & 31 == 0 and (w >> 20) & 31 == 1 and w >> 27 == 2
                fmas.append(c)
            else:
                assert w & 0x7f == 0x53 and w >> 25 == 0x71 and (w >> 12) & 7 == 1
                assert (w >> 15) & 31 == 2 and (w >> 20) & 31 == 0
                classes.append(c)
        assert len(fmas) == 20 and len(classes) == 4
        for c, dest in zip(fmas, DEST):
            assert (c.instruction >> 7) & 31 == dest and c.fpr_writes == {dest:expected}
        for c, dest in zip(classes, (5,6,7,28)):
            assert (c.instruction >> 7) & 31 == dest and c.gpr_writes == {dest:(64 if b == 0 else 2)}
        assert [writes.get(symbols['arb_observed']+168*b+8*i) for i in range(21)] == [expected]*20+[0x3ff0000000000000]
        assert [writes.get(symbols['arb_class']+32*b+8*i) for i in range(4)] == [64 if b == 0 else 2]*4
    csr = [writes.get(symbols['arb_csr']+8*i) for i in range(5)]
    assert csr[0] is not None and csr == [csr[0],0,0,0,csr[0]]
    assert [writes.get(symbols['g75_result']),writes.get(symbols['g75_result']+4),
            writes.get(symbols['num_failed']),writes.get(symbols['tohost'])] == [56,0,0,1]
    return old.architecture.reference_counts(commits, symbols)


def prepare(out):
    assert not out.exists()
    baseline = life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    assert baseline['coverage_admitted'] is True
    book = life.read_bound(old.BUILD/'build-source-pins.json',old.SOURCE_SHA)
    pins = {str(BASE/'admission-manifest.json'):BASE_SHA,
            str(old.BUILD/'build-source-pins.json'):old.SOURCE_SHA}
    sources = ('hardware/deps/cva6/core/fpu_wrap.sv',
        'hardware/deps/cva6/core/include/ariane_pkg.sv',
        'hardware/deps/fpnew/src/fpnew_top.sv',
        'hardware/deps/fpnew/src/fpnew_opgroup_block.sv',
        'hardware/deps/fpnew/src/fpnew_fma.sv',
        'hardware/deps/common_cells/src/rr_arb_tree.sv')
    for rel in sources:
        p = ROOT/rel
        assert life.digest(p) == book[str(p)]
        pins[str(p)] = book[str(p)]
    cmd = json.loads(old.TEMPLATE.read_bytes())
    cmd = [str(APP) if x.endswith('/vgap99_csr_satp_mprv.c') else str(out/'input.elf')
           if x.endswith('/input.elf') else '-march=rv64gv_zfh_zvfh'
           if x.startswith('-march=') else x for x in cmd]
    for p in (APP,Path(__file__).resolve(),old.TEMPLATE,Path(cmd[0]),build.SPIKE,
              build.LLVM/'llvm-readelf',build.LLVM/'llvm-objdump',
              ROOT/'verification/tests/gap75_start.S',ROOT/'verification/tests/gap75.ld'):
        pins[str(p)] = life.digest(p)
    life.check(pins)
    out.mkdir()
    life.save(out/'compile-command.json',cmd)
    with (out/'build.log').open('x') as f:
        subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=120)
    symbols = {s:build._elf_symbol(out/'input.elf',build.LLVM/'llvm-readelf',s)
               for s in ('tohost','trap_fail','g75_result','num_failed','arb_observed',
                         'arb_class','arb_csr','arb_batch0','arb_batch1','arb_end0','arb_end1')}
    with (out/'input.disasm').open('x') as f:
        subprocess.run([str(build.LLVM/'llvm-objdump'),'-d',str(out/'input.elf')],stdout=f,check=True,timeout=30)
    spike = [str(build.SPIKE),'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu',
             '--pmpregions=0','-l','--log-commits',str(out/'input.elf')]
    life.save(out/'spike-command.json',spike)
    with (out/'spike.trace').open('x') as f:
        subprocess.run(spike,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=120)
    counts = validate(build.parse_spike_commits(out/'spike.trace'),symbols)
    life.check(pins)
    for p in out.iterdir():
        pins[str(p)] = life.digest(p)
    life.save(out/'preflight.json',dict(status='SPIKE_FMA_DIV_CLASS_EXACT_PASS_ARBITRATION_UNPROVEN',
        baseline=792,baseline_seal=BASE_SHA,pins=pins,symbols=symbols,counts=counts,
        checks=56,FMA=40,DIV=2,FCLASS=8,flags=0,RTL_changed=False,EDA_started=False,
        runtime_gate='FMA-tagged valid&&!ready, capture operand_c, stable STALL, exact retirement; no guarantee from software PASS'))
    print(out,life.digest(out/'preflight.json'),counts)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    prepare(p.parse_args().output.resolve())
