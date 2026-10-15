"""Validate only the three original line-numbered capacity records."""
import re
def require(ok,msg):
    if not ok:raise ValueError(msg)
def validate(text,expected):
    require(len(text.encode())<=65536,'Bounded focused witness')
    rows=[]
    pattern=re.compile(r'^(\d+):core\s+0:\s+(\d+)\s+(0x[0-9a-f]+)\s+\((0x[0-9a-f]+)\)(.*)$')
    for line in text.splitlines():
        m=pattern.fullmatch(line);require(m is not None,'Exact focused record schema')
        rows.append((int(m[1]),int(m[2]),int(m[3],16),int(m[4],16),m[5]))
    require(len(rows)==3,'Capacity exactly three records, no missing/duplicate')
    require([r[2:4] for r in rows]==[(r['pc'],r['insn']) for r in expected],'Capacity PC/code/order')
    require([r[0] for r in rows]==list(range(rows[0][0],rows[0][0]+3)),'Original consecutive retirement line window')
    require(all(r[1]==3 for r in rows),'Original M-mode capacity context')
    values=[]
    for index,row in enumerate(rows):
        rest=row[4]
        rd=re.findall(r'\bx\s*(\d+)\s+(0x[0-9a-f]+)',rest)
        csrs=re.findall(r'\bc\d+_(\w+)\s+(0x[0-9a-f]+)',rest)
        residue=re.sub(r'\bx\s*\d+\s+0x[0-9a-f]+','',rest)
        residue=re.sub(r'\bc\d+_\w+\s+0x[0-9a-f]+','',residue)
        require(not residue.strip(),'No extra capacity memory/vector/context effects')
        if index==0:
            require(rd==[('5','0xffffffffffffffff')] and not csrs,'Capacity li t0=-1 actual rd only')
        elif index==1:
            require(len(rd)==1 and int(rd[0][0])==10 and int(rd[0][1],16)==512,'Capacity actual a0=512')
            require(len(csrs)==len({name for name,_ in csrs}),'No duplicate capacity CSR')
            state={name:int(value,16) for name,value in csrs}
            require(set(state)<=set(('vl','vtype','vstart')) and state.get('vl')==512
                and state.get('vtype')==11 and ('vstart' not in state or state['vstart']==0),'Actual VL512/VTYPE11 and legal delta')
            values.append(state)
        else:require(not rd and not csrs and not rest.strip(),'Capacity ret has no extra side effects')
    return dict(status='CAPACITY3_FOCUSED_ACCEPTED',PCs=[hex(r[2]) for r in rows],
        codes=[hex(r[3]) for r in rows],original_lines=[r[0] for r in rows],counts=[1,1,1],
        contiguous_original_retirement_window=True,t0='0xffffffffffffffff',a0=512,VL=512,VTYPE=11,
        actual_CSR_delta=values[0],ret_no_side_effects=True)
