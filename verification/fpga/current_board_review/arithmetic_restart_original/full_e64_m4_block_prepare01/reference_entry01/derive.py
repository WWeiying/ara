"""Derive each backend from its own linked ELF/disassembly, never copy PCs."""
import importlib.util
import sys
sys.dont_write_bytecode=True
from context import *
path=HERE.parent/'compiled_audit03/inspect.py'
spec=importlib.util.spec_from_file_location('linked_e64m4',path)
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
u=mod.u

def main():
    proof=read(SOFT/'proof.json');result=read(HERE.parent/'compiled_audit03/RESULT.json')
    require(result['all_equal_whole_CFG_upper']==2863981,'Exact approved compiled cost')
    for backend in ('soc','spike'):
        root=SOFT/backend;c=u.assembly(root/'program.dis');symbols=read(root/'symbols.json');elf=(root/'program.elf').read_bytes()
        require(sha(root/'program.elf')==proof['backends'][backend]['sha256'],'Own actual ELF identity')
        body={p:x for p,x in c.items() if symbols['arithmetic_main']<=p<symbols['capacity']}
        def one(op,arg):
            found=[p for p,x in body.items() if x['op']==op and x['args']==arg]
            require(len(found)==1,'Unique actual seed site '+op+' '+arg);return found[0]
        seed={key:one('sd',arg) for key,arg in dict(b='a4,0(a3)',a='a5,0(a1)',
            a0='zero,0(a1)',b0='zero,0(a3)',a1='a0,0(a1)',b1='a6,0(a3)',
            a2='t1,0(a1)',b2='a0,0(a3)',b3='s0,0(a3)').items()}
        info=result['compiled'][backend];masks={}
        for mode,path in info['mask_paths'].items():
            events=[];selected=iter(path['bits']);state=[0]*128;load=None
            for textpc in path['pcs']:
                p=int(textpc,16);x=c[p]
                if x['op']=='lbu':load=p
                elif x['op']=='sd':events.append(dict(pc=p,offset=8*len(events),width=8,value=0,load=None))
                elif x['op']=='sb':
                    bit=next(selected);offset=bit//8;previous=state[offset];state[offset]|=1<<(bit%8)
                    require(load is not None,'Actual preceding selected LBU')
                    events.append(dict(pc=p,offset=offset,width=1,value=state[offset],load=load,previous=previous));load=None
            require(len(events)==16+len(path['bits']),'Full mask schedule')
            masks[mode]=dict(pcs=[int(p,16) for p in path['pcs']],events=events)
        fp={}
        for seedno,path in info['FP_paths'].items():
            fp[seedno]=dict(pcs=[int(p,16) for p in path['pcs']],stores=[dict(e,pc=int(e['pc'],16)) for e in path['FP_writes']],
                loads=[dict(e,pc=int(e['pc'],16)) for e in path['FP_inputs']])
        cmp=info['comparator'];cmp=dict(cmp)
        cmp['all_equal_pcs']=[int(p,16) for p in cmp['all_equal_pcs']]
        cmp['initial_zero']=int(cmp['initial_zero'],16)
        for key in ('loads','ids','sites'):
            cmp[key]=[{k:(int(v,16) if k in ('pc','beq','li','join') else v) for k,v in e.items()} for e in cmp[key]]
        for p,x in c.items():require(u.filebytes(elf,p,u.nxt(c,p)-p)==x['insn'].to_bytes(u.nxt(c,p)-p,'little'),'Actual instruction bytes')
        save(HERE/(backend+'_spec.json'),dict(backend=backend,elf=str(root/'program.elf'),elf_sha256=sha(root/'program.elf'),symbols=symbols,
            code={str(p):x['insn'] for p,x in c.items()},asm={str(p):x for p,x in c.items()},helpers=proof['backends'][backend]['helpers'],
            seed_pc=seed,mask_paths=masks,FP_paths=fp,comparator=cmp,output_stores=[int(p,16) for p in info['output66_stores']],
            main_frame=info['main_frame'],vtype=26,capacity=64,physical_registers_per_group=4,output_bytes=528,
            HTIF=backend=='spike',scope='SOURCE_REFERENCE_SPEC_NOT_DUT_ACCEPTANCE'))
    for backend in ('soc','spike'):artifacts(backend)
    print('OWN_SOC_AND_REFERENCE_SPECS_DERIVED')
if __name__=='__main__':main()
