"""Static ELF/source/table/sequence audit only; no generated program executes."""
import ast,collections,hashlib,json,re,struct
from pathlib import Path
HERE=Path(__file__).resolve().parent;OLD=HERE.parent/'full_e8_m8_block_unrolled01'
def require(ok,msg):
    if not ok:raise ValueError(msg)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def save(p,obj):
    with p.open('x') as f:json.dump(obj,f,indent=2);f.write('\n')
class ELF:
    def __init__(self,p):
        self.raw=p.read_bytes();h=struct.unpack_from('<16sHHIQQQIHHHHHH',self.raw)
        require(h[0][:6]==b'\x7fELF\x02\x01' and h[2]==243,'ELF64 little endian RISC-V')
        self.loads=[]
        for i in range(h[10]):
            kind,flags,off,va,pa,fs,ms,align=struct.unpack_from('<IIQQQQQQ',self.raw,h[5]+i*h[9])
            if kind==1:self.loads.append((va,self.raw[off:off+fs],ms))
        sections=[struct.unpack_from('<IIQQQQIIQQ',self.raw,h[6]+i*h[11]) for i in range(h[12])]
        self.symbols={}
        for s in sections:
            if s[1]!=2:continue
            st=sections[s[6]];strings=self.raw[st[4]:st[4]+st[5]]
            for off in range(s[4],s[4]+s[5],s[9]):
                name,info,other,section,value,size=struct.unpack_from('<IBBHQQ',self.raw,off)
                text=strings[name:].split(b'\0',1)[0].decode()
                if text:self.symbols[text]=(value,size)
    def bytes(self,a,size):
        for va,data,mem in self.loads:
            if va<=a and a+size<=va+len(data):return data[a-va:a-va+size]
        raise ValueError('Not initialized ELF file bytes '+hex(a))
def disassembly(p):
    result={};name=None
    for line in p.read_text().splitlines():
        m=re.match(r'^([0-9a-f]+) <([^>]+)>:',line)
        if m:name=m[2];result[name]=[];continue
        m=re.match(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+(\S+)\s*(.*)',line)
        if m and name:result[name].append(dict(pc=int(m[1],16),insn=int(m[2],16),op=m[3],args=m[4].split('#')[0].strip()))
    return result
def success_cfg(rows):
    code={r['pc']:r for r in rows};pc=min(code);visited=[]
    while True:
        require(pc in code and pc not in visited,'Acyclic old comparison success CFG')
        r=code[pc];visited.append(pc)
        if r['op']=='ret':break
        if r['op'] in ('beq','beqz'):pc=int(r['args'].split(',')[-1].split()[0],16)
        elif r['op']=='j':pc=int(r['args'].split()[0],16)
        else:
            require(r['op'] not in ('jal','jalr','bge','blt','bgeu','bltu','bnez'),'Unexpected comparator control')
            pc+=4 if r['insn']&3==3 else 2
    return [code[p] for p in visited]
def main():
    proof=read(OLD/'proof.json');ready=read(OLD/'READY.json');seq=read(OLD/'sequence.json')
    require(ready['status']=='REFERENCE_FULL4095_PASS_SOFTWARE_ONLY_NOT_DUT' and ready['calls']==4095
        and ready['results']==4193280 and ready['guards']==8190 and ready['actual_reference_rc']==ready['actual_audit_rc']==0,'Actual old source/reference scope')
    require(sha(OLD/'reference01/result.json')==ready['reference_sha256'],'Old accepted result metadata identity; no raw read')
    require(proof['identity']['exact_elf_equal'] and proof['identity']['original_sha256']==
        'ee9874270f50735cb04da599bb477d3d9da2bbeba0e77cbec9e1eb1ea0f8310f'
        and proof['full_order_calls']==4095 and proof['original_fallback_verbatim'],'Original full shape/fallback')
    for name,h in proof['unchanged_from_previous'].items():require(sha(OLD/name)==h,'Preserved original source/table '+name)
    tree=ast.parse((OLD/'model.py').read_text())
    cap=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign)
        and any(isinstance(x,ast.Name) and x.id=='CAP' for x in n.targets))
    require(cap==1024 and len(seq)==4095,'Actual CAP and source cardinality')
    kinds=[0]*19+[1,1,1,2,3,0];i=0
    for seed in range(3):
        for op in range(25):
            for li,vl in enumerate((0,1,2,3,512,1023,1024)):
                for mode in range(3):
                    for si in range(3 if kinds[op]==0 else 1):
                        r=seq[i];start=(0,vl//2,vl if vl<1024 else 1023)[si]
                        require([r[k] for k in ('ordinal','seed','op','li','mode','si','vl','start')]==
                            [i+1,seed,op,li,mode,si,vl,start],'Exact original chronological context')
                        i+=1
    table=(OLD/'dictionary.h').read_text().split('static const uint16_t expected_indices',1)[0]
    words=[int(v,16) for v in re.findall(r'UINT64_C\(0x([0-9a-f]+)\)',table)]
    require(len(words)%8==0 and words[:8]==[0x5b5b5b5b5b5b5b5b]*8,'Source ID0 is eight full byte5b words')
    zero=[sum(r['indices'][b]==0 for r in seq) for b in range(16)];z=sum(zero)
    zeros_by_seed=[sum(r['indices'][b]==0 for r in seq if r['seed']==s for b in range(16)) for s in range(3)]
    zeros_by_op=[sum(r['indices'][b]==0 for r in seq if r['op']==op for b in range(16)) for op in range(25)]
    tail_zero=sum(r['indices'][16]==0 for r in seq)
    require(tail_zero==0,'Partial2B dictionary block is not full64B sentinel')
    result_backends={}
    for backend in ('soc','spike'):
        root=OLD/backend;elf=ELF(root/'program.elf')
        require(sha(root/'program.elf')==proof['backends'][backend]['sha256'],'Actual linked '+backend+' ELF')
        functions=disassembly(root/'program.dis')
        for rows in functions.values():
            for r in rows:
                width=4 if r['insn']&3==3 else 2
                require(int.from_bytes(elf.bytes(r['pc'],width),'little')==r['insn'],'Actual disassembly instruction byte')
        symbols=read(root/'symbols.json')
        require(all(elf.symbols[n][0]==symbols[n] for n in ('expected_dictionary','expected_indices','physical_masks')),'ELF symtab identity')
        addr,size=elf.symbols['expected_dictionary']
        require(size==8*len(words) and elf.bytes(addr,size)==struct.pack('<'+'Q'*len(words),*words),'Whole source dictionary equals linked bytes')
        addr,size=elf.symbols['expected_indices'];require(size==4095*34,'Full uint16 ID matrix size')
        ids=elf.bytes(addr,size)
        require(all(list(struct.unpack_from('<17H',ids,34*j))==r['indices'] for j,r in enumerate(seq)),'All4095 actual linked ID rows')
        addr,size=elf.symbols['physical_masks'];require(size==384,'Original three full128B predicate inputs')
        masks=elf.bytes(addr,size)
        require(masks==bytes(sum(1<<(i%8) for i in range(j*8,j*8+8)
            if mode==0 or mode==1 and i%2==1 or mode==2 and i%7==2) for mode in range(3) for j in range(128)),'Actual full mask byte table')
        helpers=proof['backends'][backend]['helpers']
        require(len(helpers['capacity'])==3 and len(helpers)==26
            and all(len(w)==13 for n,w in helpers.items() if n!='capacity'),'Original3+325 helper code windows')
        require((helpers['capacity'][1]['insn']>>20)&0x7ff==3,'Actual vtype3 e8/m8')
        cmp=next(v for n,v in functions.items() if n.startswith('packed_mismatch'))
        path=success_cfg(cmp);counts=collections.Counter(r['op'] for r in path)
        require(len(path)==451,'Actual old451-instruction equal-output leaf')
        tail=[r for r in path if r['op']=='lhu' and re.search(r'\(gp\)',r['args'])]
        require(len(tail)==1 and symbols['__global_pointer$']+int(tail[0]['args'].split(',')[1].split('(')[0])==symbols['out']+1024,'Actual final output LHU2B at offset1024')
        result_backends[backend]=dict(elf_sha256=sha(root/'program.elf'),comparator_PC=hex(cmp[0]['pc']),
            success_leaf_instructions=len(path),success_leaf_op_counts=dict(counts),tail_LHU=tail[0],
            dictionary_bytes=8*len(words),dictionary_blocks=len(words)//8,full_ID_rows=4095,
            original_helper_code_instructions=328,static_success_not_execution=True)
    output=dict(status='STATIC_ARTIFACT_AUDIT_ONLY_NOT_SOFTWARE_READY',scope=dict(SEW=8,LMUL='m8',CAP=1024,vtype=3,
        calls=4095,results=4193280,guards=8190,returned_vstart=4095,helper_retirements=53235,
        physical_registers_each_group=8,physical_input_bytes_each=1024,mask_bytes=128,
        checked_output_bytes=1026,whole_output_words=128,tail_bytes=2,actual_output_reads=528255,
        mask_groups=1575,mask_stores_per_group=16,all_mask_bits_used=True),
        ID0=dict(eight_words=[hex(v) for v in words[:8]],full_block_positions=4095*16,
            zero_positions=z,nonzero_positions=4095*16-z,by_block=zero,by_seed=zeros_by_seed,by_op=zeros_by_op,
            tail_zero_positions=tail_zero,removable_gold_LD_opportunity=8*z,
            retained_gold_LD_if_exact_specialization=4095*129-8*z,retained_ID_LHU=4095*17),
        backends=result_backends,old_reference_firmware=ready['firmware'],
        old_reference_metadata_sha256=ready['reference_sha256'],
        candidate_linked_cost_not_measured=True,no_Host_compile_reference_DUT=True,
        pins={str(p):sha(p) for p in [Path(__file__).resolve()]+[OLD/n for n in ('READY.json','proof.json','case.c','packed.h',
            'model.py','sequence.json','dictionary.h','seed_inputs.json','original/scenario.S','original/operations.h',
            'soc/program.elf','soc/program.dis','soc/symbols.json','spike/program.elf','spike/program.dis','spike/symbols.json',
            'reference01/result.json','static_cost02.json','static_cost02.py')]})
    save(HERE/'ARTIFACT_AUDIT.json',output)
    print('STATIC_AUDIT',sha(HERE/'ARTIFACT_AUDIT.json'),'ID0',z,'goldLD opportunity',8*z)
if __name__=='__main__':main()
