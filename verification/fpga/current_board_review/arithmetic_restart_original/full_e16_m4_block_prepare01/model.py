"""Original SEW16/CAP256/LMUL4 full4095, exact64-byte value blocks."""
import importlib.util
from pathlib import Path
SEW,CAP,CALLS,WORD_BYTES,CHECKED_BYTES=16,256,4095,2,516
GROUPS,VTYPE=9,10
KINDS=[0]*19+[1,1,1,2,3,0]
spec=importlib.util.spec_from_file_location('immutable_integer_arithmetic',
    Path(__file__).resolve().parent.parent/'full_e16_mf4_prepare01/model.py')
integer_model=importlib.util.module_from_spec(spec);spec.loader.exec_module(integer_model)
integer,selected=integer_model.integer,integer_model.selected
def words(values):return b''.join(value.to_bytes(2,'little') for value in values)

def generate():
    seeds,rows,dictionary,lookup=[],[],[],{}
    for seed in range(3):
        rng=0x937ad68de41c725f^seed;a=[];b=[]
        for i in range(CAP):
            rng^=(rng<<13)&((1<<64)-1);rng^=rng>>7;rng^=(rng<<17)&((1<<64)-1)
            x,y=rng&65535,(rng>>19)&65535
            if i%8==0:x=y=0
            elif i%8==1:x,y=65535,1
            elif i%8==2:x,y=32768,65535
            elif i%8==3:y=16
            a.append(x);b.append(y)
        seeds.append(dict(a=a,b=b,rng_final=rng))
        for op in range(25):
            for li,vl in enumerate((0,1,2,3,128,255,256)):
                for mode in range(3):
                    for si in range(3 if KINDS[op]==0 else 1):
                        start=(0,vl//2,vl if vl<CAP else CAP-1)[si]
                        out=[91]*CAP
                        if op==22:
                            if vl:out[0]=(b[0]+sum(a[i] for i in range(vl) if selected(mode,i)))&65535
                        elif op==23:
                            packed=[a[i] for i in range(vl) if selected(mode,i)];out[:len(packed)]=packed
                        else:
                            for i in range(start,vl):
                                if not selected(mode,i):continue
                                if op<19:out[i]=integer(op,a[i],b[i],16)
                                elif op==19:
                                    if i>=2:out[i]=a[i-2]
                                elif op==20:out[i]=a[i+2] if i+2<CAP else 0
                                elif op==21:out[i]=a[b[i]] if b[i]<CAP else 0
                                elif op==24:out[i]=a[i]
                        raw=words([91]+out+[91]);assert len(raw)==CHECKED_BYTES
                        indices=[]
                        for offset in range(0,CHECKED_BYTES,64):
                            value=int.from_bytes(raw[offset:offset+64],'little')
                            if value not in lookup:lookup[value]=len(dictionary);dictionary.append(value)
                            indices.append(lookup[value])
                        assert len(indices)==9
                        rows.append(dict(ordinal=len(rows)+1,seed=seed,op=op,li=li,mode=mode,si=si,vl=vl,start=start,indices=indices))
    masks=[bytes(sum(1<<(i%8) for i in range(j*8,min(j*8+8,CAP)) if selected(mode,i)) for j in range(128)) for mode in range(3)]
    assert len(rows)==4095 and len(dictionary)<65536 and all(not any(mask[32:]) for mask in masks)
    return seeds,rows,dictionary,masks

def headers(seeds,rows,dictionary,masks):
    table='#include <stdint.h>\n#define FULL_CALLS 4095u\n'
    table+='static const uint64_t expected_dictionary[] __attribute__((aligned(64)))={\n'+',\n'.join(
        'UINT64_C(0x%016x)'%((block>>shift)&((1<<64)-1)) for block in dictionary for shift in range(0,512,64))+'\n};\n'
    table+='static const uint16_t expected_indices[4095][9]={\n'+',\n'.join('{'+','.join(map(str,r['indices']))+'}' for r in rows)+'\n};\n'
    table+='static const uint8_t physical_masks[3][128]={\n'+',\n'.join('{'+','.join(map(str,mask))+'}' for mask in masks)+'\n};\n'
    host='struct fixture_row {unsigned seed,op,vl,mode,start;};\nstatic const struct fixture_row fixture_rows[4095]={\n'
    host+=',\n'.join('{'+','.join(str(r[k]) for k in ('seed','op','vl','mode','start'))+'}' for r in rows)+'\n};\n'
    for name in ('a','b'):
        host+=f'static const uint16_t fixture_{name}[3][256]={{\n'+',\n'.join('{'+','.join(map(str,s[name]))+'}' for s in seeds)+'\n};\n'
    return table,host

def packed_header():
    text='/* Typed0x005b, exact516-byte footprint; no output typed-pointer cast. */\n'
    text+='static uint64_t raw_word(const uint8_t *p){uint64_t v;__builtin_memcpy(&v,p,8);return v;}\n'
    text+='static void initialize_output(uint8_t *p){const uint64_t v=UINT64_C(0x005b005b005b005b);\n'
    text+=''.join(f'__builtin_memcpy(p+{offset},&v,8);\n' for offset in range(0,512,8))
    text+='const uint32_t tail=UINT32_C(0x005b005b);__builtin_memcpy(p+512,&tail,4);}\n'
    text+='static void initialize_mask(uint8_t *p,unsigned mode){for(unsigned i=0;i<16;++i)__builtin_memcpy(p+8*i,physical_masks[mode]+8*i,8);}\n'
    text+='static unsigned packed_mismatch(const uint8_t *p,uint64_t ordinal){const uint16_t *ids=expected_indices[ordinal];\n'
    for block in range(8):
        text+=f'{{const uint64_t *expected=expected_dictionary+8*(unsigned)ids[{block}];\n'
        text+=''.join(f'if(raw_word(p+{block*64+8*j})!=expected[{j}])return 1;\n' for j in range(8))+'}\n'
    text+='uint32_t tail;__builtin_memcpy(&tail,p+512,4);return tail!=(uint32_t)expected_dictionary[8*(unsigned)ids[8]];}\n'
    return text
