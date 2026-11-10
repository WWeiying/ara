"""Finite architectural fixtures. No model import or host attention emulation."""
from fractions import Fraction
import hashlib
import json
import struct

OPS = {
    "full": (6, 0, 0, 10, 11), "refill": (6, 1, 0, 0, 10),
    "release": (5, 0, 0, 0, 0), "v1full": (2, 0, 0, 10, 11),
    "v1refill": (2, 1, 0, 0, 10),
    "row64": (3, 0, 0, 10, 0), "row96": (3, 2, 0, 10, 0),
    "row128": (3, 1, 0, 10, 0), "column": (7, 0, 0, 10, 0),
    "panel": (7, 1, 0, 10, 0), "qk": (7, 3, 0, 10, 0),
    "pv": (7, 2, 0, 10, 8), "bad_rd": (7, 3, 2, 10, 0),
    "bad_source": (7, 2, 0, 10, 4), "alias": (7, 2, 8, 10, 8),
    "bad_full": (6, 0, 1, 10, 11), "info": (4, 0, 10, 10, 0),
}
OP_NAMES = tuple(OPS)
INIT = dict(none=0, layout=1, numeric=2, rounding=3, q_snan=4)
FAULT = dict(none=0, reserved=1, overflow=2, q_cross_ram=3, v_mmio=4,
             v_ram_tail=5, descriptor_mmio=6, alignment=7, d256=8)


def instruction(op):
    f3, f7, rd, rs1, rs2 = OPS[op]
    return f7 << 25 | rs2 << 20 | rs1 << 15 | f3 << 12 | rd << 7 | 0x5b


def control(d, t, h, base=0):
    return t - 1 | (h - 1) << 6 | {64: 0, 128: 1, 96: 2}[d] << 7 | base << 9


def fpbits(value, width):
    # All finite fixtures are exactly representable dyadics, not rounded host math.
    return int.from_bytes(struct.pack('<e' if width == 16 else '<f', float(value)), 'little')


def fnv(data):
    value = 14695981039346656037
    for byte in data:
        value = ((value ^ byte) * 1099511628211) & ((1 << 64) - 1)
    return value


def canary():
    return b''.join(struct.pack('<I', (0x3f000001 + 0x10203 * i) & 0xffffffff)
                    for i in range(1024))


def payload(kind):
    values = [0x3800] * 128 + [0x3c00] * 128 + [x for _ in range(64) for x in (0x3000, 0x3400)]
    if kind == 1:
        values = [0x3c00] * 256 + [0x1000] * 128
    elif kind == 2:
        values[64:256] = [0x7c01] * 192
        values[257::2] = [0x7c01] * 64
    elif kind == 3:
        values[:128] = [0x7e01] * 128
    return b''.join(struct.pack('<H', x) for x in values)


def cases(mode=0):
    program = []
    def add(label, op, *, init='none', d=64, length=65, rows=8, a=0, b=0,
            fault='none', mutate=0, t=1, h=1, base=0, frm=0, start=0,
            off=0, vill=0, cause=0, layer='ok', tval=0, expected=None,
            flags=0, payload_kind=0, context=True, active_tokens=64, tile=0):
        word = instruction(op)
        c = dict(id=len(program), label=label, op=op, insn=word, init=INIT[init],
                 d=d, length=length, rows=rows, a=a, b=b, fault=FAULT[fault], mutate=mutate,
                 t=t, h=h, base=base, frm=frm, vstart=start, off=off, vill=vill,
                 cause=cause, layer=layer, tval=word if layer in ('front', 'decode') else tval,
                 expected_flags=flags, payload_kind=payload_kind,
                 context=context, active_tokens=active_tokens, tile=tile)
        prepared = bytearray(canary())
        prepared[1024:1792] = payload(payload_kind)
        c['outside_hash'] = fnv(prepared[512:])
        if expected is None:
            expected = [int.from_bytes(prepared[i:i+4], 'little') for i in range(0, 512, 4)]
            c['width'] = 32
            c['active'] = False
        else:
            c['width'] = 16 if op == 'pv' else 32
            c['active'] = op in ('qk', 'pv') and not cause
        c['expected'] = expected
        program.append(c)
        return c

    def layout(op, d, stream, index, tokens=64, tile=0, changed=False, **kw):
        raw = bytearray(canary()[:512])
        count = d if op.startswith('row') else tokens
        columns = 4 if op == 'panel' else 1
        for column in range(columns):
            for i in range(count):
                row, dim = ((index if stream == 0 else tile+index), i) if op.startswith('row') else (tile+i, index+column)
                value = ((0x2000 + row*128 + dim) if stream == 0 else
                         (0x3000 + row*33 + dim) if stream == 1 else (0x4000 + row*19 + dim))
                if changed and stream and row == 64:
                    value = 0x5000 + stream*256 + dim
                at = i*2 if op.startswith('row') else column*128+i*2
                struct.pack_into('<H', raw, at, value)
        return add(kw.pop('label'), op, d=d, a=(index << 2 | stream) if op.startswith('row') else
                   index | (128 if stream == 2 else 0), expected=list(struct.unpack('<128I', raw)),
                   active_tokens=tokens, tile=tile, **kw)

    if mode == 2:
        add('akv_disabled_info', 'info', a=0, cause=2, layer='decode', context=False)
        add('akv_disabled_full', 'full', init='layout', cause=2, layer='decode', context=False)
        return program
    if mode == 1:
        add('resident_off_full', 'full', init='numeric', d=64, length=1, active_tokens=1)
        add('resident_disabled', 'qk', a=control(64,1,1), cause=2, layer='decode', active_tokens=1)
        raw=bytearray(canary()[:512]);struct.pack_into('<64H',raw,0,*([0x3c00]*64))
        add('resident_off_context_retained', 'row64', a=0, expected=list(struct.unpack('<128I',raw)), active_tokens=1)
        add('resident_off_release','release',context=False,active_tokens=1)
        return program

    for index in range(5):
        add('info_'+str(index), 'info', a=index, off=3, frm=5, start=7,
            context=False, active_tokens=0)
    add('full_layout', 'full', init='layout', d=96, rows=8)
    layout('row96',96,0,7,label='query_snapshot',mutate=7)
    layout('row96',96,1,0,label='key_snapshot')
    layout('panel',96,1,92,label='panel_snapshot')
    layout('column',96,2,95,label='v_column_snapshot')
    add('refill_retains_q_descriptor','refill',a=64,d=96,mutate=8,active_tokens=1,tile=64)
    layout('row96',96,0,7,tokens=1,tile=64,label='refill_old_query')
    layout('panel',96,1,92,tokens=1,tile=64,changed=True,label='refill_panel_tail')
    add('release','release',d=96,context=False,active_tokens=1,tile=64)
    add('released_replay','row96',cause=2,layer='backend',context=False,active_tokens=1,tile=64)
    add('v1_full','v1full',init='layout',length=9,rows=2,d=64,active_tokens=8)
    add('v1_refill','v1refill',a=8,active_tokens=1,tile=8)
    layout('row64',64,2,0,tokens=1,tile=8,label='v1_value_row')
    add('v1_release','release',context=False,active_tokens=1,tile=8)
    add('recovery_full','full',init='layout',d=64)
    for label,fault in [('bad_descriptor','reserved'),('overflow','overflow'),('no_d256','d256'),
                        ('descriptor_mmio','descriptor_mmio'),('payload_mmio','v_mmio'),
                        ('cross_ram','q_cross_ram')]:
        memory = fault in ('descriptor_mmio','v_mmio','q_cross_ram')
        tval = 0x81000000 if fault=='q_cross_ram' else 0x10000000 if memory else 0
        add(label,'full',init='layout',fault=fault,cause=5 if memory else 2,
            layer='memory' if memory else 'backend',tval=tval,context=False)
        add(label+'_poisoned','row64',cause=2,layer='backend',context=False)
        add(label+'_recover','full',init='layout')
    add('refill_ram_full','full',init='layout',fault='v_ram_tail',d=64)
    add('refill_ram_fault','refill',a=64,cause=5,layer='memory',tval=0x81000000,
        context=False,active_tokens=1,tile=64)
    add('refill_ram_poisoned','row64',cause=2,layer='backend',context=False,active_tokens=1,tile=64)
    add('refill_ram_recover','full',init='layout')
    add('refill_bad_range','refill',a=65,cause=2,layer='backend',context=False)
    add('refill_range_poisoned','row64',cause=2,layer='backend',context=False)
    add('refill_range_recover','full',init='layout')
    add('front_full_align','full',fault='alignment',cause=2,layer='front')
    layout('row64',64,0,0,label='front_full_same_context')
    add('front_full_rd','bad_full',cause=2,layer='front')
    layout('row64',64,0,0,label='bad_encoding_same_context',off=1,frm=5)

    def numeric(label,d,t,h,base=0,**kw):
        qk=[fpbits(Fraction(d,64)*(1 if (base+head)%2==0 else 2),32)
            for head in range(h) for _ in range(t)]
        pv=[fpbits(Fraction(1,2)+Fraction(t,64) if head==0 else 1+Fraction(t,32),16)
            for head in range(h) for _ in range(d)]
        add(label+'_full','full',init='numeric',d=d,length=t,active_tokens=t)
        add(label+'_qk','qk',a=control(d,t,h,base),d=d,t=t,h=h,base=base,
            expected=qk,active_tokens=t,**kw)
        add(label+'_pv','pv',a=control(d,t,h),d=d,t=t,h=h,expected=pv,active_tokens=t)
    for index,(d,t,h,base) in enumerate([(64,1,1,7),(96,2,2,6),(128,3,1,5),(64,17,2,4),(128,64,2,0)]):
        numeric('shape_'+str(index),d,t,h,base,vill=int(index==1))
    add('negative_full','full',init='numeric',d=96,length=2,active_tokens=2)
    good=control(96,2,2,6)
    for label,op,a,kw in [
        ('bad_dimension','qk',control(64,2,2,6),{}),
        ('overshoot','qk',control(96,3,2,6),{}),
        ('bad_base','qk',control(96,2,2,7),{}),
        ('bad_control','qk',good|(1<<12),{}),
        ('bad_rd','bad_rd',good,{}),('bad_source','bad_source',control(96,2,2),{}),
        ('alias','alias',control(96,2,2),{}),('bad_frm','qk',good,{'frm':5}),
        ('bad_start','qk',good,{'start':1}),('fs_off','qk',good,{'off':1}),
        ('vs_off','qk',good,{'off':2})]:
        layer='backend' if label in ('bad_dimension','overshoot') else 'decode' if label in ('bad_start','fs_off','vs_off') else 'front'
        add(label,op,a=a,d=96,t=2,h=2,base=6,cause=2,layer=layer,active_tokens=2,**kw)
        expected=[fpbits(Fraction(96,64)*(1 if h==0 else 2),32) for h in range(2) for _ in range(2)]
        add(label+'_next_good','qk',a=good,d=96,t=2,h=2,base=6,expected=expected,active_tokens=2)
    add('nan_full','full',init='q_snan',d=64,length=1,active_tokens=1)
    add('qk_inactive_snan','qk',a=control(64,1,1,6),d=64,base=6,
        expected=[fpbits(1,32)],active_tokens=1)
    add('qk_active_snan','qk',a=control(64,1,1,7),d=64,base=7,
        expected=[0x7fc00000],flags=16,active_tokens=1)
    add('pv_inactive_snan','pv',a=control(64,1,1),d=64,payload_kind=2,
        expected=[fpbits(Fraction(33,64),16)]*64,active_tokens=1)
    add('pv_active_snan','pv',a=control(64,1,2),d=64,h=2,payload_kind=2,
        expected=[fpbits(Fraction(33,64),16)]*64+[0x7e00]*64,flags=16,active_tokens=1)
    add('pv_qnan','pv',a=control(64,1,1),d=64,payload_kind=3,
        expected=[0x7e00]*64,active_tokens=1)
    add('rounding_full','full',init='rounding',d=64,length=1,active_tokens=1)
    for rm in range(5):
        add('round_'+str(rm),'pv',a=control(64,1,1),d=64,frm=rm,payload_kind=1,
            expected=[0x3c01 if rm in (3,4) else 0x3c00]*64,flags=1,active_tokens=1)
    add('final_release','release',context=False,active_tokens=1)
    return program


def info(index):
    return [1|1<<8|64<<16|8<<24|8<<32|1<<40|15<<48,
            0x5b|2<<8|3<<11|4<<14|5<<17|6<<20,
            2|64<<8|8<<16|6<<24|127<<32|1<<40,
            0x5b|6<<8|7<<11|128<<16|1<<24,0][index]


def emit(directory,mode):
    rows=cases(mode);gold=[];header=['#ifndef GATE_FIXTURE_H','#define GATE_FIXTURE_H',
        '#include <stdint.h>',
        'typedef struct { unsigned op,init,d,length,rows,fault,mutate,t,h,base,frm,vstart,off,vill,cause,width,active,payload; uint64_t a,b,tval,outside; unsigned begin,count; } gate_case;',
        '#define GATE_CASES '+str(len(rows)), '#define GATE_MODE '+str(mode)]
    def array(name,data):
        header.append('static const unsigned char '+name+'[] __attribute__((aligned(64))) = {'+
                      ','.join(str(x) for x in data)+'};')
    array('gate_initial',canary())
    for n in range(4):array('gate_payload_'+str(n),payload(n))
    header.append('static const unsigned char *const gate_payloads[]={gate_payload_0,gate_payload_1,gate_payload_2,gate_payload_3};')
    header.append('static const gate_case gate_cases[]={')
    for c in rows:
        begin=len(gold);gold+=c['expected']
        fields=[OP_NAMES.index(c['op'])]+[int(c[k]) for k in ('init','d','length','rows','fault','mutate','t','h','base','frm','vstart','off','vill','cause','width','active','payload_kind')]
        header.append('{'+','.join(map(str,fields))+','+','.join('UINT64_C('+str(c[k])+')' for k in ('a','b','tval','outside_hash'))+f',{begin},{len(c["expected"])}'+'},')
    header+=['};','static const uint32_t gate_golden[]={'+','.join(hex(x)+'u' for x in gold)+'};','#endif']
    (directory/'fixture.h').write_text('\n'.join(header)+'\n')
    manifest=dict(schema='stage5-akv-directed-v1',mode=mode,cases=rows,
                  synthetic_directed=True,arithmetic_oracle='exact dyadics + IEEE midpoint/canonical-NaN rules',
                  qemu_executed=False)
    (directory/'expected.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    return manifest
