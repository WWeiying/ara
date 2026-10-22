"""Finite linked leaf CFG/taint proof, not architectural execution."""
import importlib.util
from pathlib import Path
import collections
import re
import struct
_spec=importlib.util.spec_from_file_location('sealed_elf_reader',Path(__file__).resolve().parent.parent/'software01/closed_audit03.py')
old=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(old)
require,sign,MASK=old.require,old.sign,old.MASK

class Leaf:
    def __init__(self,functions,symbols,elf):
        self.functions=functions;self.symbols=symbols;self.segments=[]
        startup=functions['_start'][:2]
        require(startup[0]['op']=='auipc' and startup[0]['args'].startswith('gp,') and startup[1]['op']=='addi' and startup[1]['args'].startswith('gp,gp,'),'Exact linked startup GP setup')
        gp=startup[0]['pc']+sign((int(startup[0]['args'].split(',')[1],0)<<12)&0xffffffff,32)
        gp+=int(startup[1]['args'].split('#')[0].strip().split(',')[-1],0)
        require(gp==symbols['__global_pointer$'],'GP derived from actual startup instructions and linked symbol')
        gp_writers=[x['pc'] for rows in functions.values() for x in rows if x['args'].split(',')[0]=='gp' and x['op'] not in ('sd','sw','sb','beq','bne','blt','bge','bltu','bgeu')]
        require(gp_writers==[x['pc'] for x in startup],'No other compiled GP writers')
        self.gp=gp
        h=struct.unpack_from('<16sHHIQQQIHHHHHH',elf)
        for n in range(h[10]):
            kind,flags,off,va,pa,filesz,memsz,align=struct.unpack_from('<IIQQQQQQ',elf,h[5]+n*h[9])
            if kind==1:self.segments.append((va,elf[off:off+filesz],memsz))
    def initial(self,addr,size):
        for va,data,memsz in self.segments:
            if va<=addr and addr+size<=va+memsz:
                return int.from_bytes(data[addr-va:addr-va+size].ljust(size,b'\0'),'little')
        raise ValueError('Unknown ELF memory '+hex(addr))
    def walk(self,name,arg,output=None):
        code={x['pc']:x for x in self.functions[name]};pc=min(code);seen=set();regs={'zero':(0,set()),'a0':(arg,{'ARG'}),'sp':(0x90000000,{'SP'}),'gp':(self.gp,{'GP'})}
        stack={};writes={};events=[];branches=[];counts=collections.Counter()
        def get(r):
            require(r in regs,'Unknown leaf register '+r+' at '+hex(pc));return regs[r]
        def put(r,value,taints):
            if r!='zero':regs[r]=(value&MASK,taints)
        def address(expr):
            m=re.fullmatch(r'(-?\d+)\((\w+)\)',expr);require(m is not None,'Memory operand '+expr)
            base,t=get(m[2]);require(type(base) is int,'Opaque address');return (base+int(m[1]))&MASK,t
        def kind(addr,size):
            s=self.symbols
            if 0x8ffff000<=addr<0x90000100:return 'STACK'
            for tag,sym,length in [('OUT','out',520),('ID','e32m4_expected_ids',107730),('GOLD','e32m4_expected_blocks',144128),
                ('MASK','mask',128),('A','a',512),('B','b',512),('FP','fp_inputs',32)]:
                if s[sym]<=addr and addr+size<=s[sym]+length:return tag
            return 'ROM'
        while True:
            require(pc in code and pc not in seen and len(seen)<1000,'Finite acyclic scalar CFG '+name+' '+hex(pc));seen.add(pc)
            x=code[pc];op=x['op'];args=x['args'].split('#')[0].strip();parts=[v.strip() for v in args.split(',')] if args else []
            nxt=pc+(4 if x['insn']&3==3 else 2);counts[op]+=1
            if op=='ret':break
            if op in ('ld','lw','lwu','lhu','lbu'):
                rd,expr=parts;size={'ld':8,'lw':4,'lwu':4,'lhu':2,'lbu':1}[op];addr,taint=address(expr);k=kind(addr,size)
                require(not (name.startswith('e32m4_packed') and ('OUT' in taint or 'GOLD' in taint)),'Cache address depends on result data')
                if k=='STACK':require((addr,size) in stack,'Restore initialized stack slot');v,t=stack[(addr,size)]
                elif k=='OUT' and output is not None:
                    off=addr-self.symbols['out'];v=int.from_bytes(output[off:off+size],'little');t={'OUT'}
                else:
                    v=sum(writes.get(addr+i,(self.initial(addr+i,1)))<<(8*i) for i in range(size));t={k}
                if op=='lw':v=sign(v,32)&MASK
                regs[rd]=(v,t);events.append(dict(pc=hex(pc),op=op,kind=k,address=addr,size=size,value=v if type(v)is int else None))
            elif op in ('sd','sw','sb'):
                rs,expr=parts;size={'sd':8,'sw':4,'sb':1}[op];addr,taint=address(expr);k=kind(addr,size)
                if rs not in regs:
                    require(k=='STACK' and re.fullmatch(r's\d+',rs),'Only ABI saves may carry opaque entry values');regs[rs]=('caller:'+rs,{'CALLER'})
                v,t=get(rs)
                if k=='STACK':stack[(addr,size)]=(v,t)
                else:
                    require(type(v)is int,'Known business store value')
                    for i in range(size):writes[addr+i]=(v>>(8*i))&255
                events.append(dict(pc=hex(pc),op=op,kind=k,address=addr,size=size,value=(v&((1<<(8*size))-1)) if type(v)is int else None))
            elif op=='beq':
                left,right,target=parts;lv,lt=get(left);rv,rt=get(right)
                if name.startswith('e32m4_packed'):require((lt|rt)=={'ID'} or (lt=={'OUT'} and rt=={'GOLD'}),'Only tag or actual/gold pair BEQ')
                taken=lv==rv;dest=int(target.split()[0],16);branches.append(dict(pc=hex(pc),taken=taken,taint=sorted(lt|rt),left=left,right=right,left_value=lv,right_value=rv,sticky=regs['a0'][0]))
                if taken:nxt=dest
            elif op=='j':nxt=int(parts[0].split()[0],16)
            elif op=='li':put(parts[0],int(parts[1],0),set())
            elif op=='auipc':put(parts[0],pc+sign((int(parts[1],0)<<12)&0xffffffff,32),set())
            elif op=='mv':regs[parts[0]]=get(parts[1])
            elif op in ('addi','andi','slli'):
                rd,rs,imm=parts;v,t=get(rs);i=int(imm,0);put(rd,v+i if op=='addi' else v&i if op=='andi' else v<<i,t)
            elif op in ('add','sub','or'):
                rd,l,r=parts;lv,lt=get(l);rv,rt=get(r);put(rd,lv+rv if op=='add' else lv-rv if op=='sub' else lv|rv,lt|rt)
            elif op=='sext.w':
                rd,rs=parts;v,t=get(rs);put(rd,sign(v&0xffffffff,32),t)
            elif op in ('snez','zext.b'):
                rd,rs=parts;v,t=get(rs);put(rd,int(v!=0) if op=='snez' else v&255,t)
            else:raise ValueError('Unsupported scalar leaf opcode '+op+' '+hex(pc))
            pc=nxt
        return dict(instructions=len(seen),pcs=sorted(seen),events=events,branches=branches,op_counts=dict(counts),return_value=regs.get('a0',(None,None))[0])

