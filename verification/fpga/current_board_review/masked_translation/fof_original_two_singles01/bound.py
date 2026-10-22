"""Pin the completed software/Host artifacts and finite successful-path bound."""
from pathlib import Path
import re
import prepare as p

def main():
    p.require(not (p.HERE/'STATIC_BOUND.json').exists(),'Fresh bound only')
    host=p.read(p.HERE/'host01/execution.json')
    p.require(host['actual_wait_returncode']==0 and host['status']=='HOST_PASS_NOT_DUT','Actual Host exit')
    cases={}
    for sew in p.CASES:
        d=p.HERE/'software01'/f'e{sew}'
        p.verify(p.read(d/'input_pins.json'))
        text=(d/'spike.dis').read_text();code=p.o.disassemble(text);s=p.read(d/'spike.symbols.json')
        labels=[(int(m[1],16),m[2]) for m in re.finditer(r'^([0-9a-f]+) <([^>]+)>:',text,re.M)]
        counts={name:sum(a<=pc<(labels[i+1][0] if i+1<len(labels) else max(code)+4) for pc in code)
                for i,(a,name) in enumerate(labels)}
        p.require(counts['check_state']==(141 if sew==8 else 121) and counts['check']==27 and
                  counts['fx_trap']==(109 if sew==8 else 110),'Reviewed compiled sizes drift')
        terms=dict(state_scans=5430*counts['check_state'],scalar_checks=p.o.spec_values(sew)['checks']*counts['check'],
                   startup=((s['__bss_end']-s['__bss_start'])//8+1)*5,
                   main_initialization=(2560+8+4+130+16+10+5)*16,
                   trap_scaffolding=21*counts['fx_trap'],other=20000)
        upper=sum(terms.values());p.require(upper<1500000,'Static reference bound insufficient')
        cases[str(sew)]=dict(upper_instructions=upper,terms=terms,compiled_function_lengths=counts,
                            spike_elf_sha256=p.sha(d/'spike.elf'),soc_elf_sha256=p.sha(d/'soc.elf'),
                            slow273_plus20_DUT_seconds=upper/273*1.2,estimate_not_guarantee=True)
    files=[x for x in p.HERE.iterdir() if x.is_file()]
    files += [x for x in (p.HERE/'software01').rglob('*') if x.is_file()]
    files += [x for x in (p.HERE/'host01').rglob('*') if x.is_file()]
    pins={str(x):p.sha(x) for x in files}
    p.save(p.HERE/'STATIC_BOUND.json',dict(admit_once=True,instruction_limit=1500000,timeout_s=120,
                                        raw_bytes=256*1024**2,cases=cases,pins=pins,no_DUT=True))
    print({k:v['upper_instructions'] for k,v in cases.items()})

if __name__=='__main__':main()
