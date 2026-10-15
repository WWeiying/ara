"""Unexecuted static draft: original e32/m2 full5985, exact source FP table."""
import hashlib
import importlib.util
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
ARCH=Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_extended04')
CAP=64
SEW=32
CALLS=5985
PHYSICAL_BYTES=256
OUTPUT_BYTES=264
EXPECTED_WORDS=33
SOURCE_PINS={
    str(ARCH/'overlay/opt/ara-tests/rvv_matrix_e32_m2'):'978310da20bf437709dae962164491c1f1e8bea6acb9b62ba7a0dbe01c621c3c',
    str(ARCH/'rvv_matrix_e32_m2.S'):'f5a921e6cbb233c4e22f5431cfa198da50e8910d2644c66dd444b908cedebf07',
    str(ARCH/'e32/operations.h'):'2b3cce9dcdaaa6bc6e556ae4d2c013325ed48c473858c1984751c867a58f4b7b',
    str(HERE.parents[1]/'recovery22/rvv_matrix_e32_m2'):'978310da20bf437709dae962164491c1f1e8bea6acb9b62ba7a0dbe01c621c3c',
    str(HERE.parents[1]/'recovery22/reconstructed_oracle.c'):'7483f9dfde7012f7b800314fe1765f8cee9836fbcfbdc16fc641554397884e91',
    str(HERE.parents[1]/'full_small2_prepare01/model.py'):'bbd2a83eb3629e93e3a7744c38aa6b7742f1f8a2afe3e6a995d76cc453dc4ef6',
}

def require(ok,why):
    if not ok:raise ValueError(why)

def source_contract():
    for path,digest in SOURCE_PINS.items():
        require(hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,'Source drift '+path)
    text=(ARCH/'e32/operations.h').read_text()
    require(re.search(r'^#define OPERATION_COUNT 35$',text,re.M),'Original35 operations')
    kinds=[int(x) for x in re.search(r'^#define OPERATION_KINDS (.*)$',text,re.M)[1].split(',')]
    names=re.findall(r'"([^"]+)"',re.search(r'^#define OPERATION_NAMES (.*)$',text,re.M)[1])
    require(kinds==[0]*19+[1,1,1,2,3,0]+[0]*10 and len(names)==35,'Original names/kinds')
    inputs_text=text.split('fp_inputs[8] = {',1)[1].split('};',1)[0]
    table_text=text.split('fp_expected[10][64] = {',1)[1].split('};',1)[0]
    values=lambda s:[int(x,16) for x in re.findall(r'UINT64_C\(0x([0-9a-f]+)\)',s)]
    fp_inputs,flat=values(inputs_text),values(table_text)
    require(len(fp_inputs)==8 and len(flat)==640 and all(0<=x<2**32 for x in fp_inputs+flat),'Exact32bit source table')
    spec=importlib.util.spec_from_file_location('accepted_e32_integer_model',HERE.parents[1]/'full_small2_prepare01/model.py')
    integer_model=importlib.util.module_from_spec(spec);spec.loader.exec_module(integer_model)
    return kinds,names,fp_inputs,[flat[i*64:(i+1)*64] for i in range(10)],integer_model.integer

def selected(mode,i):
    return mode==0 or (mode==1 and i%2==1) or (mode==2 and i%7==2)

def generate():
    kinds,names,fp_inputs,fp_expected,integer=source_contract()
    seeds,rows=[],[]
    for seed in range(3):
        rng=0x937ad68de41c725f^seed
        a,b=[],[]
        for i in range(CAP):
            rng^=(rng<<13)&((1<<64)-1);rng^=rng>>7;rng^=(rng<<17)&((1<<64)-1)
            x,y=rng&0xffffffff,(rng>>19)&0xffffffff
            if i%8==0:x=y=0
            elif i%8==1:x,y=0xffffffff,1
            elif i%8==2:x,y=0x80000000,0xffffffff
            elif i%8==3:y=32
            a.append(x);b.append(y)
        seeds.append(dict(a=list(a),b=list(b),rng_final=rng))
        for op in range(len(names)):
            for li,vl in enumerate((0,1,2,3,CAP//2,CAP-1,CAP)):
                for mode in range(3):
                    mask=[0]*128
                    for i in range(CAP):
                        if selected(mode,i):mask[i//8]|=1<<(i%8)
                    for si in range(3 if kinds[op]==0 else 1):
                        start=(0,vl//2,vl if vl<CAP else CAP-1)[si]
                        # This happens for EVERY FP trial, including VL0/no-op.
                        if op>=25:
                            a=[fp_inputs[(i+seed)%8] for i in range(CAP)]
                            b=[fp_inputs[(3*i+seed)%8] for i in range(CAP)]
                        out=[91]*CAP
                        if op==22:
                            if vl:out[0]=(b[0]+sum(a[i] for i in range(vl) if selected(mode,i)))&0xffffffff
                        elif op==23:
                            packed=[a[i] for i in range(vl) if selected(mode,i)]
                            out[:len(packed)]=packed
                        else:
                            for i in range(start,vl):
                                if not selected(mode,i):continue
                                if op<19:out[i]=integer(op,a[i],b[i],32)
                                elif op==19:
                                    if i>=2:out[i]=a[i-2]
                                elif op==20:out[i]=a[i+2] if i+2<CAP else 0
                                elif op==21:out[i]=a[b[i]] if b[i]<CAP else 0
                                elif op==24:out[i]=a[i]
                                else:out[i]=fp_expected[op-25][((i+seed)%8)*8+(3*i+seed)%8]
                        raw=b''.join(x.to_bytes(4,'little') for x in [91]+out+[91])
                        words=[int.from_bytes(raw[i:i+8],'little') for i in range(0,len(raw),8)]
                        require(len(raw)==OUTPUT_BYTES and len(words)==EXPECTED_WORDS,'Exact264 bytes/33words')
                        rows.append(dict(ordinal=len(rows)+1,seed=seed,op=op,name=names[op],li=li,vl=vl,
                            mode=mode,si=si,start=start,a=list(a),b=list(b),mask=mask,
                            expected=out,words=words,input_phase='fp_every_call' if op>=25 else 'integer_seed',
                            fresh_input_required=op>=25 or (op==0 and li==mode==si==0)))
    require(len(rows)==CALLS and sum(r['op']>=25 for r in rows)==1890,'Original5985/FP1890 scope')
    require(all(r['mask'][8:]==[0]*120 for r in rows),'Softwaremask128/actualvlm8')
    return seeds,rows

# No command entry point: this draft is not executed at the static-only stage.
