"""Static e32/m8 counterpart; no model execution, Host, compiler or simulation."""
import hashlib,json,re,struct
from pathlib import Path
HERE=Path(__file__).resolve().parent;A=HERE.parent
C=Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_extended04')
E=C/'overlay/opt/ara-tests/rvv_matrix_e32_m8';S=C/'rvv_matrix_e32_m8.S';H=C/'e32/operations.h'
D=A/'recovery22/rvv_matrix_e32_m8_decode/original.dis'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def check(ok,msg):
    if not ok:raise ValueError(msg)
check(sha(E)=='ab307903f1da301801731456464a9358f5f85a0bb4cdcff1a7657f88a833f8f2','Exact ELF')
check(sha(S)=='562ee87b61684f0d53d2ca9ee85cd5e1c2fba9964c1f43ee335fdbf84be332dd','Exact assembly')
check(sha(H)=='2b3cce9dcdaaa6bc6e556ae4d2c013325ed48c473858c1984751c867a58f4b7b','Exact header')
recovery=json.loads((A/'recovery22/report.json').read_text())
identity=next(x for x in recovery['results'] if x['name']=='rvv_matrix_e32_m8')
check(identity['exact_elf_equal'] and identity['disassembly_equal'] and sha(A/'recovery22/rvv_matrix_e32_m8')==sha(E),'Recovered binary identity')
raw=E.read_bytes();assembly=S.read_text();header=H.read_text()
rows=[(int(m[1],16),int(m[2],16),m[3]) for m in re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+([^\n]+)',D.read_text(),re.M)]
common=[0x013772d7,0x02056407,0x0205e807,0x02066c07,0x02b78007,0x0136f2d7,0x4e1d,0x00881073,None,0x00802573,0x013772d7,0x02066c27,0x8082]
helpers=[]
for i in range(len(rows)-12):
    w=rows[i:i+13]
    if any(v is not None and w[j][1]!=v for j,v in enumerate(common)):continue
    n=len(helpers);lines=assembly.split('op_'+str(n)+':\n')[1].split('.global')[0].strip().splitlines()
    check(len(lines)==13 and lines[8].split()[0]==w[8][2].split()[0],'Source helper order')
    code=b''.join(insn.to_bytes(4 if insn&3==3 else 2,'little') for _,insn,_ in w)
    check(len(code)==48 and raw.count(code)==1,'Full helper unique bytes')
    helpers.append(dict(op=n,pc=w[0][0],target_pc=w[8][0],target_insn=w[8][1],sha256=hashlib.sha256(code).hexdigest()))
configs=[insn>>20&2047 for _,insn,_ in rows if insn&127==87 and insn>>12&7==7]
check(len(helpers)==35 and len(configs)==106 and set(configs)=={19},'Actual35helpers and vtype0x13')
check(raw.count(b'\xfd\x52'+(0x0132f557).to_bytes(4,'little')+b'\x82\x80')==1,'Capacity bytes')
kinds=[int(v) for v in re.search(r'^#define OPERATION_KINDS (.+)$',header,re.M)[1].split(',')]
check(len(kinds)==35 and kinds.count(0)==30,'Original35ops')
expected=[int(v,16) for v in re.findall(r'UINT64_C\(0x([0-9a-fA-F]+)\)',re.search(r'fp_expected\[10\]\[64\]\s*=\s*\{(.*?)\};',header,re.S)[1])]
check(len(expected)==640 and all(v<2**32 for v in expected),'Original FP32 bits, not64bit table')
table=b''.join(v.to_bytes(4,'little') for v in expected)
check(raw.count(table)==1,'Unique original2560B FP expected table')
offset=raw.index(table)
phoff=struct.unpack_from('<Q',raw,32)[0];size,num=struct.unpack_from('<HH',raw,54)
vaddr=[]
for i in range(num):
    kind,flags,off,va,pa,fs,ms,align=struct.unpack_from('<IIQQQQQQ',raw,phoff+i*size)
    if kind==1 and off<=offset and offset+len(table)<=off+fs:vaddr.append(va+offset-off)
check(len(vaddr)==1,'Full FP table inside ELF LOAD')
selection=[sum(mode==0 or mode==1 and i%2==1 or mode==2 and i%7==2 for i in range(256)) for mode in range(3)]
check(selection==[256,128,37],'CAP256 masks')
calls=3*7*3*sum(3 if k==0 else 1 for k in kinds);fp=1890
floor=dict(output_SD=129*calls,output_LD=129*calls,full64bit_compare=129*calls,FP_ordered_SW=512*fp,
    mask_clear_SD=16*2205,mask_bit_SB=sum(selection)*735,helper_instructions=13*calls)
check(calls==5985 and sum(floor.values())==3706395,'Static lower contract')
hist=next((x for x in json.loads((C/'resume03_report.json').read_text())['results'] if x['name']=='rvv_matrix_e32_m8'),None)
sources=[E,S,H,D,A/'recovery22/report.json',A/'recovery22/rvv_matrix_e32_m8',A/'recovery22/reconstructed_oracle.c',C/'manifest.json',C/'resume03_report.json',Path(__file__)]
result=dict(status='STATIC_E32_M8_3M_CONTRACT_CONFLICT_NOT_RTL_FAILURE',
    identity=identity,source_C_verbatim_recovered=False,source_pins={str(p):sha(p) for p in sources},
    historical_board=hist,current_M9_accepted=False,
    scope=dict(SEW=32,LMUL='m8',CAP=256,vtype=19,calls=calls,integer_calls=4095,FP_calls=fp,
        results=calls*256,guards=calls*2,vstart=calls,helper_instructions=calls*13,
        group_registers=8,group_bytes=1024,output_bytes=1032,output_u64_words=129,output_reads=129*calls,
        typed_sentinel='0000005b',packed_sentinel='0000005b0000005b',guard_offsets=[0,1028],
        vl_lengths=[0,1,2,3,128,255,256],mask_bytes=128,vlm_bytes=32,upper_mask_zero_bytes=96,
        selected=selection,FP_words32_each_call=512,FP_SW_total=512*fp),
    helpers=helpers,fp_table=dict(words=640,bytes=2560,file_offset=offset,vaddr=vaddr[0],sha256=hashlib.sha256(table).hexdigest()),
    budget=dict(required_floor=floor,total=3706395,gate=3000000,minimum_excess=706395,
        conditioned_on='Original a[i],b[i] alternating SW order, full per-call checks, original mask bitset SB sequence; no added RVV',
        excluded='gold loads, RNG, loops/indexing, call/ABI, vstart check, startup/fallback',not_actual_CFG_or_reference=True),
    ROM=dict(flat_bytes=1032*calls,blocks_per_call=17,last_block_valid_bytes=8,indices_uint16_bytes=17*calls*2,unique_blocks_not_enumerated=True),
    Host_runs=0,compile_runs=0,reference_runs=0,DUT_runs=0)
with (HERE/'E32_M8_STATIC_EVIDENCE.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps({k:result[k] for k in ('status','scope','budget','historical_board')},indent=2))

