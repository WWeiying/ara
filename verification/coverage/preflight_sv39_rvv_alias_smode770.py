"""S-mode successor: preserve the reviewed oracle, not the invalid MPRV routing assumption."""
import argparse
import inspect
import re
from pathlib import Path
import preflight_sv39_rvv_alias770 as prior

ROOT,OUT,life,require=prior.ROOT,prior.OUT,prior.life,prior.require
APP=ROOT/'apps/riscv-tests/isa/rv64uv/vsv39_rvv_alias_smode_ring.c'


def exception_gate(trace,symbols):
    lines=[line for line in trace.splitlines() if 'exception ' in line]
    require(len(lines)==48,'Exact48 supervisor returns, no unexpected exception')
    for line in lines:
        m=re.search(r'exception trap_supervisor_ecall, epc (0x[0-9a-f]+)\s*$',line)
        require(m is not None and int(m[1],16)==symbols['alias_s_ecall'],'Exact ECALL cause/PC')


def validate(commits,symbols):
    result=prior.validate(commits,symbols)
    entries=[c for c in commits if c.pc==symbols['alias_machine_return']]
    require(len(entries)==48 and all(list(c.gpr_writes.values())==[9] for c in entries),
            'Every machine handler independently reads cause9')
    targets=[c for c in commits if c.pc in (symbols['alias_store_site'],symbols['alias_load_site'])]
    require(all(c.vector_sew==64 and c.vector_vl==8 and c.vector_vstart==0 and c.vector_lmul=='m1'
                for c in targets),'Exact VL8/SEW64/LMUL1, no large AVL')
    result.update(expected_supervisor_ecalls=48,target_effective_privilege='S, not MPRV-only')
    return result


def prepare(out,existing=False):
    text=inspect.getsource(prior.prepare)
    replacements={
      "'hardware/deps/cva6/core/acc_dispatcher.sv']":"'hardware/deps/cva6/core/acc_dispatcher.sv','hardware/deps/cva6/core/cva6.sv','hardware/deps/cva6/core/csr_regfile.sv']",
      'addr,store,ara,pkg,acc=texts':'addr,store,ara,pkg,acc=texts[:5]\n    require(".acc_mmu_en_i          (enable_translation_csr_ex)" in texts[5] and "en_ld_st_translation_o = en_ld_st_translation_q;" in texts[6],"Frozen separate translation-enable paths")',
      "'test_preflight_sv39_rvv_alias770.py'":"'test_preflight_sv39_rvv_alias_smode770.py'",
      "require('exception ' not in (out/'spike.trace').read_text(),'Unexpected Spike exception')":"exception_gate((out/'spike.trace').read_text(),symbols)",
      "status='INDEPENDENT_SPIKE_FULL_VRF_MEMORY_PTE_CSR_PREFLIGHT_PASS_NOT_DUT'":"status='S_MODE_INDEPENDENT_SPIKE_FULL_VRF_MEMORY_PTE_CSR_PREFLIGHT_PASS_NOT_DUT'",
      "pins=life.merge_pins(pins,{str(p):life.digest(p) for p in out.iterdir() if p.is_file()})":"pins=life.merge_pins(pins,{str(p):life.digest(p) for p in out.iterdir() if p.is_file()})\n    pins=life.merge_pins(pins,{str(Path(prior.__file__)):life.digest(Path(prior.__file__))})"
    }
    for old,new in replacements.items():
        require(text.count(old)==1,'Exact inherited preflight substitution');text=text.replace(old,new)
    namespace=dict(vars(prior));namespace.update(APP=APP,__file__=__file__,prior=prior,
        exception_gate=exception_gate,validate=validate,
        SYMBOLS=prior.SYMBOLS+('alias_machine_return','alias_s_entry','alias_s_ecall','alias_resume'))
    exec(compile(text,__file__,'exec'),namespace)
    namespace['prepare'](out,existing)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--check-existing',action='store_true');a=p.parse_args()
    prepare(a.output.resolve(),a.check_existing)
