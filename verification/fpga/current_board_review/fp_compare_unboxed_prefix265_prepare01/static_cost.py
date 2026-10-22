#!/usr/bin/env python3
"""Pin the actual compiled source loops before the sole reference execution."""
from software_prepare import HERE,read,save,sha,NAME
from strict import specification
from model import require
from pathlib import Path
def main():
    proof=read(HERE/'source_elf_proof.json');elf=Path(proof['spike_elf']['path']);s=specification(elf,True)
    body=s['functions'][NAME+'_main'];codes={r['insn'] for r in body}
    require({'08000693','08200713','10900793','00e60023','00f69023','fef71f23','00c68023'}<=codes,'Compiled lengths/stores/prefix guard')
    require(len(body)<400,'Source routine unexpectedly larger')
    blocks=[dict(name='mask128',iterations=128,per_iteration_upper=12),dict(name='a_b16',iterations=16,per_iteration_upper=40),
        dict(name='output130',iterations=130,per_iteration_upper=8),dict(name='oracle16',iterations=16,per_iteration_upper=64),
        dict(name='call_outer_flags_guards',iterations=1,per_iteration_upper=500)]
    upper=265*sum(b['iterations']*b['per_iteration_upper'] for b in blocks)+100000
    require(upper<2000000,'Static reference boundary insufficient')
    save(HERE/'static_cost.json',dict(status='STATIC_COMPILED_BUDGET_FITS',spike_elf_sha256=sha(elf),blocks=blocks,
        calls=265,upper_instructions=upper,max_steps=2000000,max_bytes=268435456,seconds=120,
        explanation='Compiled -Os scalar loops: mask <=10 ops; a/b <=32; output4; bit oracle <=40 plus transfer. Rounded allowances and100k startup/output margin. No new dynamic measurement.',
        diagnostic_failure_stops_acceptance=True,retries=0))
    print('STATIC_COMPILED_BUDGET_FITS',upper)
if __name__=='__main__':main()
