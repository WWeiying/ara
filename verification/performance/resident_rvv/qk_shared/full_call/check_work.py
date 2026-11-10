"""Exact resident work and VRF write accounting, separate from numerical checks."""
import csv
import importlib.util
from pathlib import Path
import re

ROOT = Path('/home/wangwy/openproject/ara_dsa')
spec = importlib.util.spec_from_file_location('resident_qk_geometry',
    ROOT/'verification/performance/resident_rvv/qk_shared/geometry.py')
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)
require = g.require


def order(kind):
    require(kind in ('smoke','abba'), 'Invalid full-call kind')
    return (1,) if kind == 'smoke' else (0,1,1,0)


def commands(kind):
    return [dict(mode=mode, tokens=t, heads=2, dimension=128, base=0)
            for arm in order(kind) if arm for t in (64,64,9) for mode in ('QK','PV')]


def geometry(c):
    t,h,d = (c[k] for k in ('tokens','heads','dimension'))
    if c['mode']=='QK':
        lanes = g.layout(t,h)
        writes = [{w['address']:w['byte_enable'] for w in lane['writes']} for lane in lanes]
        fma = [len(w)*d for w in writes]
        counts = dict(tokens=t, dimensions=d, heads=h, query_base=c['base'],
            source_words=0, seed_words=sum(map(len,writes)), coefficients=d*min(t,4),
            value_words=d*sum((lane['elements']+3)//4 for lane in lanes),
            result_words=sum(map(len,writes)), final_acks=sum(map(len,writes)),
            query_reads=d//16*h, columns=d//4)
        counts['active']=(1<<min(t,4))-1
        elements = [lane['elements'] for lane in lanes]
        opcode, eew, vl = 0x0605705b,2,128
    else:
        writes = [{8*head+word:255 for head in range(h) for word in range(d//16)} for _ in range(4)]
        fma = [d//16*h*t]*4
        counts = dict(control=t-1|(h-1)<<6|{64:0,128:1,96:2}[d]<<7,
            tokens=t, words=d//16, heads=h, source_words=96, seed_words=4*d//16*h,
            coefficients=4*t, value_words=4*t*d//16, result_words=4*d//16*h,
            final_acks=4*d//16*h, row_reads=t*d//16)
        elements=[d//4]*4
        opcode,eew,vl=0x0485705b,1,256
    return dict(counts=counts,writes=writes,fma=fma,elements=elements,
                opcode=opcode,eew=eew,vl=vl)


def parse_fields(text):
    parts=text.split()
    require(parts and all(re.fullmatch(r'[a-z_]+=[0-9]+', p) for p in parts),
            'Malformed resident fields')
    pairs=[p.split('=') for p in parts]
    require(len(set(k for k,v in pairs))==len(pairs), 'Duplicate resident field')
    return {k:int(v,2 if k=='active' else 10) for k,v in pairs}


def performance(text, kind):
    expected=commands(kind)
    records=[]
    lanes={}
    for line in text.splitlines():
        if not line.startswith('[RESIDENT_'):
            continue
        match=re.fullmatch(r'\[RESIDENT_(QK|PV)_(LANE|PERF)\] (.+)',line)
        require(match is not None,'Unknown resident probe')
        mode,category,fields=match.groups()
        require(len(records)<len(expected),'Extra resident command')
        c=expected[len(records)]
        require(mode==c['mode'],'Resident mode/order mismatch')
        shape=geometry(c)
        r=parse_fields(fields)
        if category=='LANE':
            keys=set('lane vid tokens elements heads issued returned writes flags error'.split())
            if mode=='QK': keys.add('dimensions')
            require(set(r)==keys,'Lane field contract mismatch')
            lane=r['lane']
            require(lane in range(4) and lane not in lanes and shape['writes'][lane],
                    'Duplicate/inactive lane completion')
            want=dict(tokens=c['tokens'],elements=shape['elements'][lane],heads=c['heads'],
                      issued=shape['fma'][lane],returned=shape['fma'][lane],
                      writes=len(shape['writes'][lane]),error=0)
            if mode=='QK': want['dimensions']=c['dimension']
            require(all(r[k]==v for k,v in want.items()) and r['vid'] in range(8) and
                    r['flags'] in range(32),'Lane arithmetic accounting mismatch')
            lanes[lane]=r
            continue
        require(set(r)==set(shape['counts'])|{'seq','vid','cycles','error','flags'},
                'Terminal field contract mismatch')
        require(all(r[k]==v for k,v in shape['counts'].items()) and
                r['seq']==len(records)+1 and r['vid'] in range(8) and
                r['cycles']>0 and r['error']==0,'Terminal shape/work mismatch')
        require(set(lanes)=={l for l in range(4) if shape['writes'][l]},
                'Missing active lane completion')
        flags=0
        for lane in lanes.values():
            require(lane['vid']==r['vid'],'Lane/terminal VID mismatch')
            flags |= lane['flags']
        require(flags==r['flags'],'Lane/terminal flags mismatch')
        records.append(dict(mode=mode,terminal=r,lanes=lanes))
        lanes={}
    require(len(records)==len(expected) and not lanes,'Incomplete resident work')
    return records


def signatures(kind):
    result=[]
    for arm in order(kind):
        for t in (64,64,9):
            result += [0x0605705b,0x0485705b] if arm else (
                [0x0205745b]*32 + [0x0205345b if i%2==0 else 0x0205355b for i in range(t)])
    return result


def vector_writes(path,kind):
    expected=commands(kind)
    rows=[]
    instructions=[]
    epoch=0
    previous=-1
    live=None
    with Path(path).open(newline='') as stream:
        reader=csv.DictReader(stream)
        required=set('cycle event arch_seq vid lane source insn use_vd vd eew vl vstart addr be wdata nr_lanes vlen_bits'.split())
        require(reader.fieldnames is not None and required<=set(reader.fieldnames) and
                len(reader.fieldnames)==len(set(reader.fieldnames)),'Invalid vector trace columns')
        for r in reader:
            require(None not in r and all(v is not None for v in r.values()),'Malformed trace row')
            cycle=int(r['cycle'])
            require(cycle>=previous and r['nr_lanes']=='4' and r['vlen_bits']=='1024',
                    'Trace cycle/configuration changed')
            previous=cycle
            event=r['event']
            if event=='config':
                require(epoch==0 and cycle==0 and not rows and live is None,'Unexpected trace reset')
                epoch+=1
                continue
            require(epoch==1 and event in ('alloc','write','done') and
                    re.fullmatch(r'[0-9a-fA-F]{8}',r['insn']) is not None,'Unknown trace event')
            insn=int(r['insn'],16)
            if event=='alloc' and insn&0x707f in (0x305b,0x705b): instructions.append(insn)
            if insn&0x707f!=0x705b or insn>>25 not in (2,3): continue
            if event=='alloc':
                require(live is None and len(rows)<len(expected),'Overlapping/extra resident allocation')
                shape=geometry(expected[len(rows)])
                require(insn==shape['opcode'],'Resident instruction mismatch')
                live=dict(arch_seq=int(r['arch_seq']),vid=int(r['vid']),begin=cycle,
                          shape=shape,writes={})
                require(live['arch_seq']>0 and live['vid'] in range(8),'Invalid allocation identity')
            require(live is not None and live['arch_seq']==int(r['arch_seq']) and
                    live['vid']==int(r['vid']),'Unowned resident event')
            shape=live['shape']
            require(insn==shape['opcode'] and tuple(int(r[k]) for k in
                    ('use_vd','vd','eew','vl','vstart'))==(1,0,shape['eew'],shape['vl'],0),
                    'Resident internal metadata mismatch')
            if event=='write':
                lane,addr=int(r['lane']),int(r['addr'])
                require(lane in range(4) and addr in shape['writes'][lane] and
                        int(r['be'],16)==shape['writes'][lane][addr] and int(r['source'])==4 and
                        re.fullmatch(r'[0-9a-fA-F]{16}',r['wdata']) is not None,
                        'Illegal resident architectural write')
                require((lane,addr) not in live['writes'],'Duplicate resident architectural write')
                live['writes'][lane,addr]=cycle
            if event=='done':
                require(set(live['writes'])=={(l,a) for l in range(4) for a in shape['writes'][l]},
                        'Incomplete resident architectural writes')
                rows.append(dict(vid=live['vid'],arch_seq=live['arch_seq'],begin=live['begin'],
                                 end=cycle,writes=len(live['writes'])))
                live=None
    require(epoch==1 and live is None and len(rows)==len(expected),'Incomplete resident trace')
    require(instructions==signatures(kind),'Wrong original/candidate replay work or order')
    return rows


def check(path,text,kind):
    perf=performance(text,kind)
    writes=vector_writes(path,kind)
    require(all(p['terminal']['vid']==w['vid'] and p['terminal']['result_words']==w['writes']
                for p,w in zip(perf,writes)),'Probe/architectural evidence mismatch')
    return dict(commands=len(perf),performance=perf,architectural_writes=writes,
                numerical_checked=False,protocol_checked=False)
