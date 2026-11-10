#!/usr/bin/env python3
"""Strict directed guest/architectural trace audit, not an RTL timing checker."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def require(ok,message):
    if not ok:raise ValueError(message)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):
    def pairs(rows):
        value={}
        for k,v in rows:require(k not in value,'Duplicate JSON key');value[k]=v
        return value
    return json.loads(Path(p).read_text(),object_pairs_hook=pairs)
def fields(text,keys,hexes=(),prefixed=False):
    values={}
    for token in text.split():
        require(token.count('=')==1,'Malformed record')
        k,v=token.split('=');require(k in keys and k not in values,'Unknown/duplicate field')
        expression=r'0x[0-9a-fA-F]+' if k in hexes and prefixed else r'[0-9a-fA-F]+' if k in hexes else r'[0-9]+'
        require(re.fullmatch(expression,v),'Malformed unsigned field')
        values[k]=int(v,16 if k in hexes else 10)
    require(set(values)==set(keys),'Missing field')
    return values


SCHEMAS=dict(START='mode cases',ADDRESS='descriptor q k v',
    CASE='id pc a b fcsr vcsr vstart vl vtype traps errors',
    TRAP='id pc cause tval mstatus',INFO='id index value mstatus',
    OUT='id index bits',MEMORY='id outside errors',RVV='errors',DONE='mode cases traps errors')
HEXES=set('descriptor q k v pc a b vtype tval mstatus value bits outside'.split())
TRACE=dict(info='index result',begin='seq pc insn rs1 rs2 frm fflags',
           read='seq pc address bytes',end='seq pc status fflags valid tile tokens tval')
TRACE_HEX=set('result pc insn rs1 rs2 address tval'.split())


def guest(text,manifest,binding):
    records=[]
    for line in text.splitlines():
        if line.startswith('GATE_'):
            parts=line.split(' ',1);tag=parts[0][5:]
            require(len(parts)==2 and tag in SCHEMAS,'Unknown/malformed guest record')
            records.append((tag,fields(parts[1],SCHEMAS[tag].split(),HEXES)))
        else:
            require(not re.search(r'(?i)fatal|segmentation|assertion|could not|failed|GATE_',line),'Guest/transport failure')
    index=0
    def take(tag):
        nonlocal index
        require(index<len(records) and records[index][0]==tag,'Missing/duplicate/out-of-order '+tag)
        value=records[index][1];index+=1;return value
    cases=manifest['cases'];mode=manifest['mode']
    require(take('START')==dict(mode=mode,cases=len(cases)),'Wrong guest/mode')
    address=take('ADDRESS');expected_address={short:binding['addresses'][long] for short,long in
        [('descriptor','descriptor'),('q','queries'),('k','keys'),('v','values')]}
    require(address==expected_address,'ELF/data address identity')
    calls=[];traps=0;outputs=0
    for c in cases:
        r=take('CASE');pc=binding['pcs'][c['op']]['pc'];a,b=c['a'],c['b']
        if c['op'] in ('full','v1full','bad_full'):
            a=0x10000000 if c['fault']==6 else address['descriptor']+int(c['fault']==7)
        want=dict(id=c['id'],pc=pc,a=a,b=b,fcsr=c['frm']*32+(8|c['expected_flags']),
                  vcsr=5,vstart=c['vstart'],vl=0,vtype=(1<<63) if c['vill'] else 0xc0,
                  traps=int(c['cause']!=0),errors=0)
        require(r==want,'Case/CSR/control/terminal mismatch: '+c['label'])
        if c['cause']:
            trap=take('TRAP');traps+=1
            require({k:trap[k] for k in ('id','pc','cause','tval')}==
                    dict(id=c['id'],pc=pc,cause=c['cause'],tval=c['tval']),'Real trap PC/cause/tval')
            if c['off']&1:require(trap['mstatus']&0x6000==0,'FSoff not exercised')
            if c['off']&2:require(trap['mstatus']&0x600==0,'VSoff not exercised')
        if c['op']=='info' and not c['cause']:
            info=take('INFO')
            word=[1|1<<8|64<<16|8<<24|8<<32|1<<40|15<<48,
                  0x5b|2<<8|3<<11|4<<14|5<<17|6<<20,
                  2|64<<8|8<<16|6<<24|127<<32|1<<40,
                  0x5b|6<<8|7<<11|128<<16|1<<24,0][c['a']]
            require(info['id']==c['id'] and info['index']==c['a'] and info['value']==word and
                    info['mstatus']&0x6600==0,'Scalar discovery/capability contract')
        for i,bits in enumerate(c['expected']):
            require(take('OUT')==dict(id=c['id'],index=i,bits=bits),'Output/sentinel mismatch: '+c['label'])
            outputs+=1
        require(take('MEMORY')==dict(id=c['id'],outside=c['outside_hash'],errors=0),'Outside-group/source guard')
        calls.append(r)
    require(take('RVV')==dict(errors=0),'Ordinary RVV postlude')
    require(take('DONE')==dict(mode=mode,cases=len(cases),traps=traps,errors=0) and index==len(records),
            'Unique complete terminal')
    return dict(cases=len(cases),traps=traps,output_records=outputs,csr_guards_checked=True),calls,address


def trace_rows(text):
    rows=[]
    for line in text.splitlines():
        if 'akv_arch_' not in line:continue
        m=re.search(r'\bakv_arch_(\w+)\s+(.+)$',line)
        require(m and m[1] in TRACE,'Unknown/malformed AKV trace')
        rows.append((m[1],fields(m[2],TRACE[m[1]].split(),TRACE_HEX,prefixed=True)))
    return rows


def architectural(text,manifest,binding,calls,address):
    rows=trace_rows(text);cursor=0;sequence=0;ctx=None;memory_faults=0;reads=0;resident=0
    def take(tag):
        nonlocal cursor
        require(cursor<len(rows) and rows[cursor][0]==tag,'Missing/extra trace '+tag)
        value=rows[cursor][1];cursor+=1;return value
    for c,call in zip(manifest['cases'],calls):
        if c['layer']=='decode':continue
        if c['op']=='info':
            r=take('info');require(r['index']==c['a'],'INFO order');continue
        sequence+=1;r=take('begin');pc=binding['pcs'][c['op']]['pc']
        source1=(c['insn']>>15)&31;source2=(c['insn']>>20)&31
        scalar1=call['a'] if source1 else 0
        # PV's rs2 encoding names a vector source, not a scalar dependency.
        # The adapter's unused GPR argument is not an architectural input.
        scalar2=r['rs2'] if c['op'] in ('pv','bad_source','alias') else call['a'] if source2==10 else call['b'] if source2==11 else 0
        require(r==dict(seq=sequence,pc=pc,insn=c['insn'],rs1=scalar1,rs2=scalar2,frm=c['frm'],fflags=8),
                'Real helper opcode/PC/control/FRM/sticky mismatch')
        expected=[]
        full=c['op'] in ('full','v1full') and c['layer']!='front'
        refill=c['op'] in ('refill','v1refill') and c['layer']=='ok'
        refill_fault=c['op']=='refill' and c['layer']=='memory'
        if full:
            if c['fault']!=6:expected.append((address['descriptor'],64))
            if c['fault'] not in (1,2,6,8):
                ctx=dict(d=c['d'],rows=c['rows'],length=c['length'],v2=c['op']=='full',
                         v=0x80ffc000 if c['fault']==5 else 0x10000000 if c['fault']==4 else address['v'])
                if c['fault']!=3:
                    expected += [(address['q']+i*256,c['d']*2) for i in range(c['rows'])]
                    expected += [(address['k']+(c['b']+i)*256,c['d']*2) for i in range(c['active_tokens'])]
                    if c['fault']!=4:expected += [(ctx['v']+(c['b']+i)*256,c['d']*2) for i in range(c['active_tokens'])]
        elif refill or refill_fault:
            require(ctx is not None,'REFILL lacks a preceding snapshot')
            expected += [(address['k']+(c['a']+i)*256,ctx['d']*2) for i in range(c['active_tokens'])]
            if not refill_fault:expected += [(ctx['v']+(c['a']+i)*256,ctx['d']*2) for i in range(c['active_tokens'])]
        for addr,size in expected:
            require(take('read')==dict(seq=sequence,pc=pc,address=addr,bytes=size),'RAM read/snapshot/REFILL contract')
            reads+=1
        if c['layer']=='memory':
            # The real memory callback throws: never synthesize a missing END.
            require(cursor==len(rows) or rows[cursor][0]!='end','Memory fault fabricated a terminal END')
            memory_faults+=1;continue
        end=take('end');status=1 if c['cause'] else 0
        require(end==dict(seq=sequence,pc=pc,status=status,fflags=c['expected_flags'],valid=int(c['context']),
                         tile=c['tile'],tokens=c['active_tokens'],tval=c['tval'] if status else 0),
                'Actual completion/state/local flags/tval mismatch: '+c['label'])
        resident+=int(c['op'] in ('qk','pv') and not c['cause'])
    require(cursor==len(rows),'Extra/orphan architectural event')
    return dict(helper_calls=sequence,ram_reads=reads,memory_callback_faults=memory_faults,
                successful_resident=resident,real_no_end_faults_checked=True)


def check(build,mode,log,trace):
    directory=Path(build).resolve(strict=True);receipt=read(directory/'build.json')
    require(receipt['state']=='DIRECTED_GUESTS_BUILT_NOT_EXECUTED' and receipt['post_pins_match'] is True,'Unaccepted firmware')
    require(sha(directory/'source-pins.json')==receipt['source_pins_sha256'],'Pin inventory identity')
    for path,digest in {**read(directory/'source-pins.json'),**receipt['artifacts']}.items():
        require(sha(path)==digest,'Firmware/source artifact drift: '+path)
    actual={str(p) for p in directory.rglob('*') if p.is_file() and p!=directory/'build.json'}
    require(actual==set(receipt['artifacts']),'Firmware artifact membership')
    variant=next(x for x in receipt['variants'] if x['mode']==mode);manifest=read(variant['expected'])
    require(sha(variant['elf'])==variant['elf_sha256'] and sha(variant['expected'])==variant['expected_sha256'],'ELF/oracle identity')
    numerical,calls,address=guest(Path(log).read_text(),manifest,variant)
    work=architectural(Path(trace).read_text(),manifest,variant,calls,address)
    return dict(state='DIRECTED_GUEST_ARCHITECTURE_CHECKED',numerical=numerical,work=work,
                qemu_image_checked=False,service_owner_checked=False,rtl_timing=False,
                elf_sha256=variant['elf_sha256'],log_sha256=sha(log),trace_sha256=sha(trace))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--build',type=Path,required=True);p.add_argument('--mode',type=int,choices=(0,1,2),required=True)
    p.add_argument('--log',type=Path,required=True);p.add_argument('--trace',type=Path,required=True)
    a=p.parse_args();print(json.dumps(check(a.build,a.mode,a.log,a.trace),indent=2,sort_keys=True))
