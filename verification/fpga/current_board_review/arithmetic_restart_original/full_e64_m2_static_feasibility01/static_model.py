"""Static source/model inventory only; no Host, compiler, Spike or DUT."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
HERE=Path(__file__).resolve().parent
PARENT=HERE.parent
ARCH=Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_extended04')
ELF=ARCH/'overlay/opt/ara-tests/rvv_matrix_e64_m2'
ASM=ARCH/'rvv_matrix_e64_m2.S'
HEADER=ARCH/'e64/operations.h'
REC=PARENT/'recovery22'
CAP,SEW,VLEN_BYTES,LMUL=32,64,128,2
CHECKED_BYTES=(CAP+2)*8
MASK64=(1<<64)-1
def require(ok,why):
    if not ok:raise ValueError(why)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def occurrences(raw,needle):
    result=[];index=raw.find(needle)
    while index>=0:
        result.append(index);index=raw.find(needle,index+1)
    return result
def load_segments(raw):
    require(raw[:6]==b'\x7fELF\x02\x01','ELF64 little endian')
    offset=struct.unpack_from('<Q',raw,32)[0]
    size,count=struct.unpack_from('<HH',raw,54)
    result=[]
    for index in range(count):
        kind,flags,off,va,pa,filesz,memsz,align=struct.unpack_from('<IIQQQQQQ',raw,offset+index*size)
        if kind==1:
            require(off+filesz<=len(raw) and filesz<=memsz,'Actual LOAD boundaries')
            result.append(dict(offset=off,vaddr=va,filesz=filesz,memsz=memsz,flags=flags))
    return result
def location(raw,values,segments,code_bound_vaddr=None):
    needle=b''.join(value.to_bytes(8,'little') for value in values)
    hits=occurrences(raw,needle)
    if code_bound_vaddr is None:
        require(len(hits)==1,'Original exact bit table must match ELF uniquely')
        offset=hits[0]
    else:
        bound=[hit for hit in hits for s in segments if s['offset']<=hit and
            hit+len(needle)<=s['offset']+s['filesz'] and
            s['vaddr']+hit-s['offset']==code_bound_vaddr]
        require(len(bound)==1,'Input table must match the exact original code-bound address')
        offset=bound[0]
    mapped=[s['vaddr']+offset-s['offset'] for s in segments
        if s['offset']<=offset and offset+len(needle)<=s['offset']+s['filesz']]
    require(len(mapped)==1,'Entire unique bit table must belong to file-backed LOAD')
    return dict(words=len(values),bytes=len(needle),file_offset=offset,vaddr=mapped[0],
        bytes_sha256=hashlib.sha256(needle).hexdigest(),whole_ELF_occurrences=len(hits),
        code_bound_vaddr=code_bound_vaddr)
def tables():
    text=HEADER.read_text()
    require(re.search(r'#define OPERATION_COUNT\s+35\b',text),'Actual35 ops')
    kinds=[int(x.strip()) for x in re.search(r'^#define OPERATION_KINDS\s+(.+)$',text,re.M)[1].split(',')]
    require(kinds==[0]*19+[1,1,1,2,3,0]+[0]*10,'Original restart trial kinds')
    inputs_text=re.search(r'fp_inputs\[8\]\s*=\s*\{(.*?)\};',text,re.S)[1]
    expected_text=re.search(r'fp_expected\[10\]\[64\]\s*=\s*\{(.*?)\};',text,re.S)[1]
    constants=lambda s:[int(v,16) for v in re.findall(r'UINT64_C\(0x([0-9a-fA-F]+)\)',s)]
    inputs,expected=constants(inputs_text),constants(expected_text)
    require(len(inputs)==8 and len(expected)==640,'Exact64-bit source table dimensions')
    return kinds,inputs,expected
def helpers(raw):
    dis=REC/'rvv_matrix_e64_m2_decode/original.dis'
    rows=[(int(m[1],16),int(m[2],16),m[3].strip()) for m in
        re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+([^\n]+)',dis.read_text(),re.M)]
    starts=[i for i,x in enumerate(rows) if x[1]==0x019772d7]
    common=[0x019772d7,0x02057407,0x0205f807,0x02067c07,0x02b78007,
        0x0196f2d7,0x4e1d,0x00881073,None,0x00802573,0x019772d7,0x02067c27,0x8082]
    windows=[]
    asm=ASM.read_text()
    for index in starts:
        window=rows[index:index+13]
        if len(window)!=13 or any(w is not None and window[j][1]!=w for j,w in enumerate(common)):continue
        op=len(windows)
        source=asm.split('op_'+str(op)+':\n',1)[1].split('.global',1)[0].strip().splitlines()
        require(len(source)==13 and source[8].split()[0]==window[8][2].split()[0],'Actual opcode/source order')
        for left,right in zip(window,window[1:]):
            require(right[0]-left[0]==(4 if left[1]&3==3 else 2),'Contiguous original helper')
        code=b''.join(insn.to_bytes(4 if insn&3==3 else 2,'little') for _,insn,_ in window)
        hits=occurrences(raw,code)
        require(len(hits)==1 and len(code)==48,'Unique48-byte fullhelper in original ELF')
        windows.append(dict(op=op,pc=window[0][0],target_pc=window[8][0],target_insn=window[8][1],
            target_mnemonic=window[8][2].split()[0],instructions=13,bytes=48,
            whole_ELF_occurrences=len(hits),file_offset=hits[0],bytes_sha256=hashlib.sha256(code).hexdigest()))
    require(len(windows)==35,'Original35 fullhelper windows')
    capacity=b'\xfd\x52'+(0x0192f557).to_bytes(4,'little')+b'\x82\x80'
    require(len(occurrences(raw,capacity))==1,'Actual original capacity helper bytes')
    vector_configs=[insn>>20&0x7ff for _,insn,_ in rows if insn&127==0x57 and (insn>>12)&7==7]
    require(len(vector_configs)==106 and set(vector_configs)=={0x19},'Actual e64/m2 vtype')
    require(not re.search(r'\b(?:fflags|fcsr|frm)\b',asm),'No invented FP flag/rounding oracle')
    return windows
def generate(kinds,inputs,fp_bits):
    # Only integer semantics are borrowed; the imported host-float fp() is never used.
    module_spec=importlib.util.spec_from_file_location('sealed_integer_only',
        PARENT/'full_e16_mf4_prepare01/model.py')
    integer=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(integer)
    selected=integer.selected
    rows=[];blocks=[];lookup={};rng_final=[];fp_calls=0;stream=hashlib.sha256()
    first_fp=[];last_seed=[];gather={}
    for seed in range(3):
        rng=0x937ad68de41c725f^seed;a=[];b=[]
        for i in range(CAP):
            rng^=(rng<<13)&MASK64;rng^=rng>>7;rng^=(rng<<17)&MASK64
            x,y=rng,rng>>19
            if i%8==0:x=y=0
            elif i%8==1:x,y=MASK64,1
            elif i%8==2:x,y=1<<63,MASK64
            elif i%8==3:y=64
            a.append(x);b.append(y)
        rng_final.append(rng)
        for op in range(35):
            for li,vl in enumerate((0,1,2,3,16,31,32)):
                for mode in range(3):
                    for si in range(3 if kinds[op]==0 else 1):
                        start=(0,vl//2,vl if vl<CAP else CAP-1)[si]
                        if op>=25:
                            # Every FP call refreshes both arrays, including identical calls.
                            a=[inputs[(i+seed)%8] for i in range(CAP)]
                            b=[inputs[(i*3+seed)%8] for i in range(CAP)]
                            fp_calls+=1
                        out=[0x5b]*CAP
                        if op==22:
                            if vl:out[0]=(b[0]+sum(a[i] for i in range(vl) if selected(mode,i)))&MASK64
                        elif op==23:
                            packed=[a[i] for i in range(vl) if selected(mode,i)]
                            out[:len(packed)]=packed
                        else:
                            for i in range(start,vl):
                                if not selected(mode,i):continue
                                if op<19:out[i]=integer.integer(op,a[i],b[i],SEW)
                                elif op==19:
                                    if i>=2:out[i]=a[i-2]
                                elif op==20:out[i]=a[i+2] if i+2<CAP else 0
                                elif op==21:
                                    out[i]=a[b[i]] if b[i]<CAP else 0
                                    if seed==0 and vl==CAP and mode==0:gather[str(i)]=dict(index=b[i],result=out[i])
                                elif op==24:out[i]=a[i]
                                else:out[i]=fp_bits[(op-25)*64+((i+seed)%8)*8+(i*3+seed)%8]
                        raw=b''.join(value.to_bytes(8,'little') for value in [0x5b]+out+[0x5b])
                        require(len(raw)==272,'Full34 u64 output words')
                        indices=[]
                        for offset in range(0,len(raw),64):
                            value=int.from_bytes(raw[offset:offset+64],'little')
                            if value not in lookup:lookup[value]=len(blocks);blocks.append(value)
                            indices.append(lookup[value])
                        require(len(indices)==5 and blocks[indices[-1]]<1<<128,'Last block has only16 valid bytes')
                        row=dict(ordinal=len(rows)+1,seed=seed,op=op,li=li,mode=mode,si=si,vl=vl,start=start,indices=indices)
                        rows.append(row)
                        stream.update(raw)
                        if op==25 and li==mode==si==0:first_fp.append(dict(row))
                        if op==34 and li==6 and mode==2 and si==2:last_seed.append(dict(row))
    require(len(rows)==5985 and fp_calls==1890,'Fulloriginal35ops, not typed16 full4095')
    masks=[bytes(sum(1<<(i%8) for i in range(j*8,min(j*8+8,CAP))
        if selected(mode,i)) for j in range(128)) for mode in range(3)]
    require(all(mask[4:]==bytes(124) for mask in masks),'Actualvlm4/fullmask128 upperzero')
    require(gather['2']['index']==MASK64 and gather['2']['result']==0,'ActualCAP32 gather OOB')
    return dict(rows=rows,blocks=blocks,fp_calls=fp_calls,rng_final=rng_final,first_fp_calls=first_fp,
        last_calls_each_seed=last_seed,full_output_order_sha256=stream.hexdigest(),
        mask_sha256=hashlib.sha256(b''.join(masks)).hexdigest(),gather_CAP32_witness=gather['2'])
def main():
    require(sha(ELF)=='1ac38feec918ada897841aef50bc5edc0b1d713f39b2193d89157f7d31a2e436','Exact archived original ELF')
    require(sha(ASM)=='6ed7c2a8e26c4d3b65fd2850bd6091a3077aabbd770cb2b4268341716aa95e94','Exact original assembly')
    require(sha(HEADER)=='bae4c627a4db226bd6a4a41601950aaf1401819933e9f568ce210a7c54922062','Exact original FP header')
    recovery=json.loads((REC/'report.json').read_text())
    identity=next(x for x in recovery['results'] if x['name']=='rvv_matrix_e64_m2')
    require(identity['exact_elf_equal'] and identity['disassembly_equal'] and sha(REC/'rvv_matrix_e64_m2')==sha(ELF),'Binary-equivalent original source evidence')
    raw=ELF.read_bytes();segments=load_segments(raw);kinds,inputs,fp_bits=tables()
    fp_table=location(raw,fp_bits,segments)
    code={int(m[1],16):int(m[2],16) for m in re.finditer(
        r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s',
        (REC/'rvv_matrix_e64_m2_decode/original.dis').read_text(),re.M)}
    input_address_code={0x103d0:0x67c5,0x103d6:0x26078793,0x103de:0xfcbe,
        0x1048a:0x7566,0x10494:0x97aa,0x10496:0x2c07b783,
        0x104a8:0x7566,0x104ae:0x97aa,0x104b0:0x2c07b783}
    require(all(code[pc]==insn for pc,insn in input_address_code.items()),
        'Original LUI/ADDI/stack120/indexed704 input table address chain')
    input_vaddr=0x11000+0x260+0x2c0
    fp_inputs=location(raw,inputs,segments,input_vaddr)
    fp_inputs['original_address_code']=input_address_code
    windows=helpers(raw);g=generate(kinds,inputs,fp_bits);count=len(g['blocks'])
    sources=[ELF,ASM,HEADER,REC/'report.json',REC/'reconstructed_oracle.c',REC/'rvv_matrix_e64_m2',
        REC/'rvv_matrix_e64_m2_decode/original.dis',PARENT/'full_e16_mf4_prepare01/model.py',Path(__file__).resolve(),
        PARENT/'full_e64_m1_optimized_compile01/READY.json',
        PARENT/'full_e64_m1_o2_vcs_m7_plan01/prepared01/complete.json']
    report=dict(status='STATIC_SOURCE_MODEL_FEASIBLE_NOT_COMPILED_NOT_TESTED',identity=identity,
        source_C_bytes_recovered=False,binary_equivalent_reconstruction=True,
        scope=dict(SEW=64,LMUL='m2',CAP=32,vtype=0x19,calls=5985,integer_calls=4095,FP_calls=1890,
            results=5985*32,guards=5985*2,vstart=5985,helper_instructions=5985*13,
            physical_registers_each_group=2,physical_register_bytes=128,physical_group_bytes=256,
            groups=dict(a=[8,9],b=[16,17],vd=[24,25]),checked_output_bytes=272,
            complete_u64_words=34,complete_read_bytes_each=8,partial_u32_reads=0,
            last_block_valid_bytes=16,last_block_result_offset=256,last_block_guard_offset=264,
            sentinel='000000000000005b',physical_a_bytes=8192,physical_b_bytes=8192,physical_out_bytes=8208,
            initialized_a_b_bytes_each=256,physical_mask_bytes=128,vlm_read_bytes=4,upper_mask_zero_bytes=124),
        fp64=dict(source='Exact640 original header uint64 bit patterns uniquely matched in original ELF',
            fp_table=fp_table,fp_inputs=fp_inputs,host_float_evaluation=False,
            refresh_calls=1890,words_each_refresh=64,refresh_word_stores=1890*64,refresh_bytes=1890*64*8,
            refresh_order='For every FP call, i0..31: a[i] then b[i], before fresh output/helper; never deduplicate identical refreshes',
            nextseed='After op34, restart actual original seed RNG and all32 integer inputs before next op0',
            fflags_oracle='Original C/header/helpers have no explicit fflags/frm oracle; preserve context without adding acceptance claims'),
        model=dict(dictionary_blocks=count,max_index=count-1,uint16_index_fits=count<=65536,
            dictionary_bytes=count*64,indices_bytes=5985*5*2,mask_bytes=384,original_FP_header_bytes=5120+64,
            proposed_ROM_bytes=count*64+5985*5*2+384+5120+64,flat_bytes=5985*34*8,
            flat_exceeds_1MiB=5985*34*8>1048576,full_output_order_sha256=g['full_output_order_sha256'],
            mask_sha256=g['mask_sha256'],seed_rng_final=g['rng_final'],
            first_FP_calls=g['first_fp_calls'],last_call_each_seed=g['last_calls_each_seed'],
            gather_CAP32_witness=g['gather_CAP32_witness']),
        helpers=windows,static_native_or_firmware_runs=0,Host_runs=0,compile_runs=0,reference_runs=0,DUT_runs=0,
        authorization='Static source/model proposal only; no stage execution admitted',
        source_pins={str(path):sha(path) for path in sources})
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
