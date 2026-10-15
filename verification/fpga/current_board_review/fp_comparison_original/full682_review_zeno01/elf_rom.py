"""Additional actual-ELF ROM/layout inspection; no binary execution."""
import json
from pathlib import Path
import re
import struct
import review_artifacts as r
def main():
    root=r.SOURCE;table=(root/'run01/tables.h').read_text()
    rows=r.initializer(table,'input_rows[][128]');cases=r.initializer(table,'packed_cases[682]')
    expected_rows=b''.join(struct.pack('<128Q',*x) for x in rows)
    expected_cases=b''.join(struct.pack('<8H64B64B',*(x[:8]+x[8]+x[9])) for x in cases)
    proofs={}
    for backend in ('soc','spike'):
        image=r.elf(root/f'run01/{backend}.elf')
        text=(root/f'run01/{backend}_nm.log').read_text()
        symbols={name:int(addr,16) for addr,kind,name in re.findall(r'^([0-9a-f]+)\s+(\w)\s+(\S+)$',text,re.M)}
        r.demand(r.at(image,symbols['input_rows'],len(expected_rows))==expected_rows,'Actual input ROM '+backend)
        r.demand(r.at(image,symbols['packed_cases'],len(expected_cases))==expected_cases,'Actual packed predicates ROM '+backend)
        r.demand(symbols['a']%8==symbols['b']%8==0,'Aligned 64-bit input writes')
        r.demand(symbols['a']-symbols['b']==2048,'Full original 1024-halfword B allocation retained')
        r.demand(symbols['__bss_end']>=symbols['a']+2048,'Full original A allocation retained')
        r.demand(symbols['__stack_top']==0x800ffff0 and symbols['__bss_end']<symbols['__stack_top']-65536,'Original 64KiB stack reserve')
        def bss(addr,n):
            return any(va+filesz<=addr and addr+n<=va+memsz for va,off,filesz,memsz in image[1])
        r.demand(bss(symbols['a'],2048) and bss(symbols['b'],2048),'Both full arrays zero-fill ELF BSS')
        proofs[backend]=dict(input_rom_bytes=len(expected_rows),predicate_rom_bytes=len(expected_cases),
          input_rom_exact=True,predicate_rom_exact=True,full_input_arrays_BSS=True,
          a=hex(symbols['a']),b=hex(symbols['b']),bss_end=hex(symbols['__bss_end']),stack_top=hex(symbols['__stack_top']))
    parent=(r.CASE/'original/parent.c').read_text()
    prefix=(r.CASE/'original/prefix.c').read_text()
    synthesized=parent.replace('        ++cases;\n','        ++cases;\n        if(cases==682)goto prefix_done;\n',1)
    synthesized=synthesized.replace('    text(errors ? "RVV_FP_COMPARE_FAIL', 'prefix_done:\n    text(errors ? "RVV_FP_COMPARE_FAIL',1)
    r.demand(synthesized==prefix,'Parent->682 prefix ONLY after-oracle stop added')
    r.save(r.HERE/'elf_rom.json',dict(status='STATIC_ELF_ROM_AND_PREFIX_PASS',backends=proofs,
      parent_to_prefix_only_after_oracle_stop=True,source_pins_unchanged=all(r.sha(p)==h for p,h in r.read(root/'pins.json').items())))
    print('STATIC_ELF_ROM_AND_PREFIX_PASS',proofs)
if __name__=='__main__':main()

