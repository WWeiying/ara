"""Audited macro-literal extraction, integer mathematics and independent SoftFloat."""
import copy
import re
import struct
from contract import NARROW,WIDE,require,load,fnv


def literals(text):
    values=[x.strip() for x in text.split(',')]
    require(all(re.fullmatch(r'(?:0x[0-9a-fA-F]+|[0-9]+)[uUlL]*',x) for x in values),
            'Nonliteral reviewed ISA operand')
    return [int(re.sub('[uUlL]+$','',x),0) for x in values]


def reviewed(text,op):
    # Only the finite, reviewed TEST_CASE1 macro grammar is accepted. Unknown
    # syntax, nonliteral input or a changed operation fails preparation.
    start=re.search(r'void TEST_CASE1\([^)]*\)\s*\{',text)
    require(start is not None,'Reviewed TEST_CASE1 missing')
    body=text[start.end():text.index('}',start.end())]
    body=re.sub(r'//[^\n]*|/\*.*?\*/','',body,flags=re.S)
    token=re.compile(r'VSET\((.*?)\);|VLOAD_(8|16|32|64)\((.*?)\);|'
        r'asm volatile\("([^"]+)"\);|VCMP_[IU](8|16|32|64)\((.*?)\);',re.S)
    sew,registers,pending,rows=None,{},None,[]
    for m in token.finditer(body):
        if m[1] is not None:
            fields=[x.strip() for x in m[1].split(',')]
            require(fields[0]=='16' and fields[2]=='m1','Reviewed VL/LMUL changed')
            sew=int(fields[1].removeprefix('e'))
        elif m[2]:
            register,values=m[3].split(',',1)
            registers[register.strip()]=(int(m[2]),literals(values))
        elif m[4]:
            match=re.fullmatch(re.escape(op)+r'\.vv (v\d+), (v\d+), (v\d+)',m[4])
            require(match is not None,'Reviewed operation changed: '+m[4])
            dest,a,b=match.groups()
            require(sew is not None and registers[a][0]==registers[b][0]==sew,
                    'Reviewed input widths')
            width=2*sew if op in WIDE else sew
            seed=registers.get(dest,(width,[0]*16))[1]
            pending=dict(op=op,sew=sew,width=width,a=registers[a][1],b=registers[b][1],
                         seed=seed,vl=16,restart=0,masked=False,frm=0,initial_flags=8,
                         provenance='archived reviewed TEST_CASE1')
        else:
            require(pending is not None and int(m[5])==pending['width'],'Reviewed compare width')
            _,_,values=m[6].split(',',2)
            gold=literals(values)
            require(all(len(pending[k])==16 for k in ('a','b','seed')) and len(gold)==16,
                    'Reviewed vector length changed')
            pending['reviewed_gold']=gold;rows.append(pending);pending=None
    require(len(rows)==(3 if op in WIDE or op.startswith('vf') else 4) and pending is None,
            'Incomplete reviewed ISA macro extraction: '+op)
    return rows


def signed(x,width): return x-(1<<width) if x>>(width-1) else x


def integer(op,width,a,b,c):
    mask=(1<<width)-1
    sa,sb=signed(a,width),signed(b,width)
    product=sa*sb
    if op in ('vmulhu','vwmulu','vwmaccu'): product=a*b
    if op in ('vmulhsu','vwmulsu','vwmaccsu'): product=sa*b
    if op=='vmulh': return (product>>width)&mask
    if op=='vmulhu': return (product>>width)&mask
    if op=='vmulhsu': return (product>>width)&mask
    if op in ('vmacc','vwmacc','vwmaccu','vwmaccsu'): product+=c
    if op=='vmadd': product=a*c+b
    if op=='vnmsac': product=c-a*b
    if op=='vnmsub': product=b-a*c
    return product&((1<<(2*width if op in WIDE else width))-1)


def finish(row,sf=None):
    row=copy.deepcopy(row);gold=list(row['seed']);flags=row['initial_flags']
    for i in range(row['restart'],row['vl']):
        if row['masked'] and i%2==0: continue
        a,b,c=(row[k][i] for k in ('a','b','seed'))
        if row['op'].startswith('vf'):
            sign=1<<(row['sew']-1)
            if row['op'] in ('vfnmacc','vfnmsac'): a^=sign
            if row['op'] in ('vfmsac','vfnmacc'): c^=sign
            gold[i],f=sf.evaluate('fma',row['sew'],row['sew'],row['frm'],a,b,c)
            flags|=f
        else: gold[i]=integer(row['op'],row['sew'],a,b,c)
    row.update(gold=gold,initial_fcsr=(row['frm']<<5)|row['initial_flags'],expected_fcsr=(row['frm']<<5)|flags,
               natural_flags=flags&~row['initial_flags'],expected_vcsr=5)
    raw=b''.join(x.to_bytes(row['width']//8,'little') for x in gold)
    row['output_hash']=fnv(raw+b'\xa5'*(256-len(raw)))
    return row


def integer_cases(archive):
    result=[]
    for op in (*NARROW,*WIDE):
        for row in reviewed((archive/'apps/riscv-tests/isa/rv64uv'/f'{op}.c').read_text(),op):
            checked=finish(row)
            require(checked['gold']==row['reviewed_gold'],'Independent integer/reviewed gold mismatch: '+op)
            result.append(checked)
    for original in (next(r for r in result if r['op']=='vmul' and r['sew']==64),
                     next(r for r in result if r['op']=='vwmacc' and r['sew']==32)):
        result.append(finish(dict(original,vl=13,restart=1,masked=True,
            provenance=original['provenance']+'; deterministic mask/tail/restart successor')))
    return result


def float_cases(archive):
    path=archive/'verification/fpnew_upstream_20261009/oracle.py'
    module=load(path,'coexist_independent_softfloat');sf=module.SoftFloat()
    result=[]
    for row in reviewed((archive/'apps/riscv-tests/isa/rv64uv/vfmacc.c').read_text(),'vfmacc'):
        checked=finish(row,sf)
        require(checked['gold']==row['reviewed_gold'],'Independent FP/reviewed gold mismatch')
        result.append(checked)
    for width,frac,exponent in ((16,10,5),(32,23,8),(64,52,11)):
        one=((1<<(exponent-1))-1)<<frac;minimum=1<<frac
        inf=((1<<exponent)-1)<<frac;sign=1<<(width-1)
        triples=[(one,one,one|sign),(one+1,one-1,one|sign),
            (minimum,one-1,1),(minimum|sign,one-1,sign|1),
            (inf-1,one+(1<<frac),0),(1,minimum,0),
            (inf,0,one),(inf,one,inf|sign),
            (inf|1,one,0),(inf|(1<<(frac-1)),one,0),
            (0,one,sign),(sign,one,sign),
            (minimum-1,one+1,1),(minimum+1,one-1,sign|1),
            (3*(minimum>>2),one-1,minimum>>2),(one|sign,one,one)]
        for op,rm,masked in (('vfmacc',0,False),('vfnmacc',3,False),('vfmsac',0,True)):
            row=dict(op=op,sew=width,width=width,a=[x[0] for x in triples],
                b=[x[1] for x in triples],seed=[x[2] for x in triples],
                vl=13 if masked else 16,restart=1 if masked else 0,masked=masked,
                frm=rm,initial_flags=8,provenance='Directed subset of reviewed SoftFloat FMA boundary families')
            result.append(finish(row,sf))
    return result,module


def handoff_reference(module):
    sf=module.SoftFloat();qk=[];pv=[];qflags=pflags=0
    for h in range(2):
        scores=[]
        for t in range(3):
            dot=0
            for d in range(64):
                q=sf.evaluate('cast',16,32,0,0x1000+h*0x200+d)[0]
                k=sf.evaluate('cast',16,32,0,0x2000+t*0x200+d)[0]
                dot,flags=sf.evaluate('fma',32,32,0,q,k,dot);qflags|=flags
            scores.append(dot)
        qk.extend(scores)
        for d in range(64):
            acc=0
            for t in range(3):
                acc,flags=sf.evaluate('fma',16,16,0,0x3c00,0x3000+t*0x200+d,acc)
                pflags|=flags
            pv.append(acc)
    return dict(qk=qk,pv=pv,qk_flags=qflags,pv_flags=pflags,
        qbs=[0x43800000,0x44000000,0x44400000]+[0]*29,
        qk_fmas=384,pv_fmas=384)
