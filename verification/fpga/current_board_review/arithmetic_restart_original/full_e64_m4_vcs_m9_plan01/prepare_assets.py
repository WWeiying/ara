"""Read only actual linked SoC inputs; complete line-local disassembly parser."""
import importlib.util
import json
from pathlib import Path
import re
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
REF=HERE.parent/'full_e64_m4_block_prepare01/reference_entry01'
SOFT=REF.parent/'software02'
def save(p,x):
    with p.open('x') as f:json.dump(x,f,indent=2);f.write('\n')
def main():
    spec=json.loads((REF/'soc_spec.json').read_text())
    modspec=importlib.util.spec_from_file_location('linked_filebytes',REF.parent/'compiled_audit03/inspect.py')
    audit=importlib.util.module_from_spec(modspec);modspec.loader.exec_module(audit)
    raw=(SOFT/'soc/program.elf').read_bytes();code={};asm={}
    for line in (SOFT/'soc/program.dis').read_text().splitlines():
        m=re.fullmatch(r'[ \t]*([0-9a-f]+):[ \t]+([0-9a-f]{4}|[0-9a-f]{8})[ \t]+([a-zA-Z0-9_.]+)(?:[ \t]+(.*))?',line)
        if not m:continue
        pc=int(m[1],16);insn=int(m[2],16);size=len(m[2])//2
        assert pc not in code and audit.u.filebytes(raw,pc,size)==insn.to_bytes(size,'little')
        code[pc]=insn;asm[pc]=dict(insn=insn,op=m[3],args=(m[4] or '').split('#')[0].strip())
    old={int(k):v for k,v in spec['code'].items()}
    assert all(code.get(p)==v for p,v in old.items())
    added=sorted(set(code)-set(old));assert added==[0x80001c72,0x80001caa,0x8000237e]
    assert [asm[p]['op'] for p in added]==['auipc','auipc','addi']
    spec.update(code={str(p):v for p,v in code.items()},asm={str(p):v for p,v in asm.items()},
        complete_instruction_map=True,previous_missing_failure_pcs=added,
        failure_pcs=sorted(set(added+[v for k,v in spec['symbols'].items() if k.startswith('failure') or k in ('trap_entry','replay_trap') ])))
    save(HERE/'soc_spec.json',spec)
    import checker as c
    authority=HERE.parent/'full_e8_mf4_o2_vcs_m9_successor02/reset_profile.json'
    profile=c.read(authority);profile.update(allowed_shape=c.SHAPE,original_soc_elf_sha256=c.ELF_SHA,
        original_linux_elf_sha256='c8e9bad5a0247cb63c9b908a316b5b0f775b242984e187d66f1aa7b3137720f6',
        authority_sha256=c.sha(authority),reference_bound_sha256=c.READY_SHA)
    save(HERE/'reset_profile.json',profile);save(HERE/'owner_contract.json',c.owner_contract())
    print('OWN_COMPLETE_SOC_SPEC',len(code),[hex(p) for p in added],c.owner_contract())
if __name__=='__main__':main()
