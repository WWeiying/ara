"""Small static source/ELF inventory and integer budget arithmetic only."""
import hashlib,json,re,struct
from pathlib import Path
HERE=Path(__file__).resolve().parent;A=HERE.parent
C=Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_extended04')
elf=C/'overlay/opt/ara-tests/rvv_matrix_e64_m8';asm=C/'rvv_matrix_e64_m8.S';header=C/'e64/operations.h'
dis=A/'recovery22/rvv_matrix_e64_m8_decode/original.dis';oracle=A/'recovery22/reconstructed_oracle.c'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def check(ok,msg):
    if not ok:raise ValueError(msg)
raw=elf.read_bytes();text=header.read_text();assembly=asm.read_text()
check(sha(elf)=='85a3dec84feba1068e1e27033f1f475c91df66dc88192dbaecdf44bf6b4df60b','Original ELF identity')
check(sha(asm)=='42c2fc99c38d1a37bad7b1def3833a3440a9d93de9b2ce69eb601b0b5368da10','Assembly identity')
check(sha(header)=='bae4c627a4db226bd6a4a41601950aaf1401819933e9f568ce210a7c54922062','Original header')
recover=json.loads((A/'recovery22/report.json').read_text())
identity=next(x for x in recover['results'] if x['name']=='rvv_matrix_e64_m8')
check(identity['exact_elf_equal'] and identity['disassembly_equal'] and sha(A/'recovery22/rvv_matrix_e64_m8')==sha(elf),'Byte-equivalent reconstruction')
kinds=[int(x) for x in re.search(r'^#define OPERATION_KINDS (.+)$',text,re.M)[1].split(',')]
check(len(kinds)==35 and kinds.count(0)==30,'35 original ops/kinds')
rows=[(int(m[1],16),int(m[2],16),m[3]) for m in re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+([^\n]+)',dis.read_text(),re.M)]
common=[0x01b772d7,0x02057407,0x0205f807,0x02067c07,0x02b78007,0x01b6f2d7,0x4e1d,0x00881073,None,0x00802573,0x01b772d7,0x02067c27,0x8082]
helpers=[]
for i in range(len(rows)-12):
    w=rows[i:i+13]
    if any(v is not None and w[j][1]!=v for j,v in enumerate(common)):continue
    n=len(helpers);lines=assembly.split('op_'+str(n)+':\n')[1].split('.global')[0].strip().splitlines()
    check(len(lines)==13 and lines[8].split()[0]==w[8][2].split()[0],'Actual helper source order')
    code=b''.join(x.to_bytes(4 if x&3==3 else 2,'little') for _,x,_ in w)
    check(len(code)==48 and raw.count(code)==1,'Unique actual helper byte sequence')
    helpers.append(dict(op=n,pc=w[0][0],target_pc=w[8][0],target_insn=w[8][1],bytes_sha256=hashlib.sha256(code).hexdigest()))
check(len(helpers)==35,'All35 helpers')
check(raw.count(b'\xfd\x52'+(0x01b2f557).to_bytes(4,'little')+b'\x82\x80')==1,'Actual capacity m8')
configs=[insn>>20&2047 for _,insn,_ in rows if insn&127==87 and insn>>12&7==7]
check(len(configs)==106 and set(configs)=={27},'Actual vtype0x1b')
phoff=struct.unpack_from('<Q',raw,32)[0];ents,num=struct.unpack_from('<HH',raw,54)
segments=[struct.unpack_from('<IIQQQQQQ',raw,phoff+i*ents) for i in range(num)]
def table(name,count,address=None):
    pattern=r'fp_inputs\[8\]\s*=\s*\{(.*?)\};' if name=='inputs' else r'fp_expected\[10\]\[64\]\s*=\s*\{(.*?)\};'
    values=[int(v,16) for v in re.findall(r'UINT64_C\(0x([0-9a-fA-F]+)\)',re.search(pattern,text,re.S)[1])]
    check(len(values)==count,'Exact bit table count')
    data=b''.join(v.to_bytes(8,'little') for v in values);hits=[];at=raw.find(data)
    while at>=0:
        for kind,flags,off,va,pa,fs,ms,align in segments:
            if kind==1 and off<=at and at+len(data)<=off+fs:hits.append((at,va+at-off))
        at=raw.find(data,at+1)
    if address is None:check(len(hits)==1,'Unique640-word expected table')
    else:hits=[h for h in hits if h[1]==address];check(len(hits)==1,'Actual source input table address')
    return dict(words=count,bytes=len(data),file_offset=hits[0][0],vaddr=hits[0][1],sha256=hashlib.sha256(data).hexdigest())
code={pc:insn for pc,insn,_ in rows}
chain={0x103d0:0x67c5,0x103d6:0x26078793,0x103de:0xfcbe,0x10496:0x2c07b783,0x104b0:0x2c07b783}
check(all(code[p]==v for p,v in chain.items()),'Original input table address/load proof')
tables=dict(expected=table('expected',640),inputs=table('inputs',8,0x11520))
selected=[sum(mode==0 or mode==1 and i%2==1 or mode==2 and i%7==2 for i in range(128)) for mode in range(3)]
check(selected==[128,64,18],'Selected counts CAP128')
calls=3*7*3*sum(3 if k==0 else 1 for k in kinds)
fp=3*7*3*3*10
lower=dict(output_SD=130*calls,output_LD=130*calls,per_word_compare=130*calls,
    FP_input_SD=256*fp,mask_clear_SD=16*2205,mask_bit_SB=sum(selected)*735,helper_instructions=13*calls)
check(calls==5985 and fp==1890 and sum(lower.values())==3085425,'Static counts/lower')
history=next(x for x in json.loads((C/'resume03_report.json').read_text())['results'] if x['name']=='rvv_matrix_e64_m8')
sources=[elf,asm,header,dis,oracle,A/'recovery22/report.json',A/'recovery22/rvv_matrix_e64_m8',C/'manifest.json',C/'resume03_report.json',Path(__file__)]
out=dict(status='STATIC_FULL_SOURCE_IDENTIFIED_3M_CONTRACT_CONFLICT_NOT_RTL_FAILURE',
    source_C_verbatim_recovered=False,binary_equivalent_reconstruction=identity,
    source_pins={str(p):sha(p) for p in sources},historical_board=history,current_M9_acceptance=False,
    scope=dict(SEW=64,LMUL='m8',CAP=128,vtype=27,calls=calls,integer_calls=4095,FP_calls=fp,
        results=calls*128,guards=calls*2,vstart=calls,helpers=calls*13,output_bytes=1040,
        output_u64_words=130,output_reads=calls*130,physical_group_bytes=1024,
        groups=dict(a=list(range(8,16)),b=list(range(16,24)),vd=list(range(24,32))),
        vl_lengths=[0,1,2,3,64,127,128],physical_mask_bytes=128,vlm_bytes=16,upper_mask_zero_bytes=112,
        mask_selected=selected,FP_u64_store_per_call=256,FP_u64_stores=fp*256),
    helpers=helpers,FP_tables=tables,budget=dict(required_counts=lower,lower_bound=sum(lower.values()),
        gate=3000000,minimum_excess=85425,
        conditioned_on='Complete original mask bitset store sequence, every output word initialized/read/compared, no extra RVV/checksum',
        not_actual_compiled_or_measured=True,excluded='gold loads, RNG, ABI, call setup, pointer/index/loop, vstart branch, boot, return, failure fallback'),
    ROM=dict(flat_bytes=calls*1040,blocks_per_call=17,indices_uint16_bytes=calls*17*2,
        last_block_valid_bytes=16,unique_blocks_not_enumerated=True,
        envelope_fixed_bytes=381258,max_blocks_for_conditional_1MiB_envelope=10426),
    Host_runs=0,compile_runs=0,reference_runs=0,DUT_runs=0)
with (HERE/'STATIC_EVIDENCE.json').open('x') as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps({k:out[k] for k in ('status','scope','budget','ROM')},indent=2))

