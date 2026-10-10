"""Finite Q2 then Q6 ROW/K2 fixtures; independent packed-byte integer gold. No EDA."""
import argparse
import json
from pathlib import Path
import struct
import subprocess

import build_qbs_k2_row_pending781 as old

common,ROOT=old.common,old.ROOT
APP=ROOT/'apps/qbs_pending_two_phase783'
WORDS=(0x06b5045b,0x0eb5045b)
PROBE=ROOT/'verification/coverage/qbs_pending_two_phase783_probe.tcl'
MUTATIONS=('weight','activation','vrf','dest','tail','guard','csr','descriptor','sourceguard')


def q6_value(row,k,i):return (7*i+3*row+11*k)%63-31
def q6_scale(row,k,g):return ((g+row+k)%7+1)*(-1 if g&1 else 1)


def decode_q6(block):
    common.require(len(block)==210 and block[208:]==b'\x00\x3c','Q6 exact finite scale layout')
    values=[]
    for i in range(256):
        low=(block[(i//128)*64+i%64]>>((i%128//64)*4))&15
        high=(block[128+(i//128)*32+i%32]>>((i%128//32)*2))&3
        values.append((low|high<<4)-32)
    scales=[b-256 if b&128 else b for b in block[192:208]]
    return values,scales


def fixture():
    first=old.fixture();weight=bytearray([0xa5]*3520);activation=bytearray([0x5a]*4864)
    for row in range(8):
        for k in range(2):
            block=bytearray(210)
            for i in range(256):
                u=q6_value(row,k,i)+32;half,within=divmod(i,128);quarter,lane=divmod(within,32)
                block[half*64+(quarter&1)*32+lane]|=(u&15)<<(4 if quarter>=2 else 0)
                block[128+half*32+lane]|=(u>>4)<<(2*quarter)
            for g in range(16):block[192+g]=q6_scale(row,k,g)&255
            struct.pack_into('<H',block,208,0x3c00)
            decoded,scales=decode_q6(block)
            common.require(decoded==[q6_value(row,k,i) for i in range(256)] and
                scales==[q6_scale(row,k,g) for g in range(16)],'Pack/decode all Q6 coefficients')
            start=74+(2*row+k)*210;weight[start:start+210]=block
    for ctx in range(8):
        for k in range(2):
            start=76+(2*ctx+k)*292
            struct.pack_into('<I',activation,start,0x3f800000)
            for i in range(256):activation[start+4+i]=old.a(ctx,k,i)&255
            for g in range(16):struct.pack_into('<h',activation,start+260+2*g,
                sum(old.a(ctx,k,i) for i in range(16*g,16*g+16)))
    image=bytearray(old.seed_bytes());results=[]
    # Gold reads the emitted packed bytes, not qbs_ref or a DUT observation.
    for ctx in range(8):
        for row in range(8):
            total=0
            for k in range(2):
                start=74+(2*row+k)*210;values,scales=decode_q6(weight[start:start+210])
                start=76+(2*ctx+k)*292;block=activation[start:start+292]
                common.require(block[:4]==b'\x00\x00\x80\x3f','Exact Q8 FP32 scale')
                a=[b-256 if b&128 else b for b in block[4:260]]
                for g in range(16):
                    common.require(struct.unpack_from('<h',block,260+2*g)[0]==sum(a[16*g:16*g+16]),'Q8 subgroup sum')
                    subtotal=sum(values[i]*a[i] for i in range(16*g,16*g+16))*scales[g]
                    common.require(abs(subtotal)<2**23,'Exact finite FP32 group subtotal')
                    total+=subtotal;common.require(abs(total)<2**23,'Exact finite FP32 accumulation')
            results.append(total);struct.pack_into('<f',image,1024+128*ctx+4*row,total)
    return [(first[0],first[1],first[2],first[3]),(bytes(weight),bytes(activation),bytes(image),results)]


def header():
    lines=['typedef struct { uint64_t *weight,*activation; const uint64_t *weight_expected,*activation_expected,*gold; unsigned m,weight_bytes,activation_bytes,weight_container,activation_container,activation_offset; } phase_t;']
    arrays=[('seed',old.seed_bytes(),True)]
    for phase,(w,a,g,_) in enumerate(fixture()):
        arrays.extend([(f'weight{phase}',w,False),(f'activation{phase}',a,False),
            (f'weight_expected{phase}',w,True),(f'activation_expected{phase}',a,True),(f'gold{phase}',g,True)])
    for name,data,const in arrays:
        values=[int.from_bytes(data[i:i+8],'little') for i in range(0,len(data),8)]
        lines.append('%suint64_t %s[%d] __attribute__((aligned(64)))={%s};'%
            ('const ' if const else '',name,len(values),','.join('UINT64_C(%s)'%hex(v) for v in values)))
    lines.append('const phase_t cases[2]={{weight0,activation0,weight_expected0,activation_expected0,gold0,4,1344,2336,1536,2496,64},{weight1,activation1,weight_expected1,activation_expected1,gold1,8,3360,4672,3520,4864,76}};')
    return '\n'.join(lines)+'\n'


def source_contract():
    book=ROOT/'verification/out/repaired-aligned-build-20260930-01/build-source-pins.json'
    common.require(common.sha(book)=='6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b','Frozen build book')
    expected=common.read(book);expected=expected.get('files',expected)
    paths=[ROOT/'hardware/include/qbs_pkg.sv']+[ROOT/('hardware/src/vlsu/qbs/'+n+'.sv') for n in
        ('qbs_profile_decoder','qbs_read_engine','qbs_engine','qbs_block_adapter','qbs_payload_buffer','qbs_compute_engine','qbs_descriptor_decoder')]
    for path in paths:
        sha=expected.get(str(path),expected.get(str(path.relative_to(ROOT))))
        if isinstance(sha,dict):sha=sha.get('sha256')
        common.require(common.sha(path)==sha,'Frozen source '+path.name)
    decoder=paths[1].read_text()
    for token in ('ql_index = half * 64 + ((quarter & 1) != 0 ? 32 : 0) + lane;',
        'qh_index = 128 + half * 32 + lane;', 'weight_byte(row, 192 + group_index_o)', 'weight_byte(row, 208)'):
        common.require(token in decoder,'Exact Q6 RTL byte layout '+token)
    pkg=paths[0].read_text()
    for token in ("QBS_WEIGHT_PROFILE_Q6_K = 4'd2",'qbs_weight_block_bytes = 210',
                  'QbsActivationBaseAlignmentLog2 = 2','QbsWeightBaseAlignmentLog2 = 1'):
        common.require(token in pkg,'Frozen profile/alignment '+token)
    return [book,*paths]


def build(out):
    common.require(not out.exists() and out.parent==ROOT/'verification/out','Fresh output')
    paths=source_contract();out.mkdir();b=common.Build(out);b.sources={}
    asm=ROOT/'apps/qbs_gap110_q3_r4_tail/execute.S';ref=ROOT/'verification/qbs/qbs_ref.c'
    b.bind_sources([Path(__file__),Path(__file__).with_name('test_qbs_pending_two_phase783.py'),
        Path(old.__file__),Path(common.__file__),ROOT/'verification/tests/build_qbs_payload_matrix4_uart.py',
        APP/'main.c',asm,PROBE,ref,ref.with_suffix('.h'),*paths])
    (out/'fixture.h').write_text(header())
    (out/'execute.S').write_text(asm.read_text().split('MATRIX_EXEC 0,')[0].replace('gap110_','matrix_')+
        '\nMATRIX_EXEC 0, 8, 0x06b5045b\nMATRIX_EXEC 1, 8, 0x0eb5045b\n')
    inc=['-I'+str(out)]
    main=b.compile(APP/'main.c','host-main',[*inc,'-DMATRIX_HOST=1','-Wno-misleading-indentation'],host=True)
    host=out/'host';b.link([b.host,main,b.compile(ref,'host-ref',host=True),'-lm','-o',host],'host.link')
    log=b.run([host],'host-checks').stdout.decode()
    common.require(log.splitlines()==['QBS_TWO_PHASE phase=0 checks=7 errors=0','QBS_TWO_PHASE phase=1 checks=14 errors=0',
        'PASSED: qbs_pending_two_phase783 commands=2 errors=0'],'Two checkpoint integer/native gold')
    for phase in range(2):
        for mutation in MUTATIONS:
            result=subprocess.run([host,mutation,str(phase)],capture_output=True,timeout=10)
            (out/('negative-%d-%s.log'%(phase,mutation))).write_bytes(result.stdout+result.stderr)
            common.require(result.returncode==1 and b'FAILED:' in result.stdout,'Negative '+str(phase)+' '+mutation)
    objects=[b.compile(b.common/n,'dut-'+n) for n in ('crt0.S','printf.c','string.c','serial.c','util.c','print_trap_cause.c')]
    objects+=[b.compile(APP/'main.c','dut-main',inc),b.compile(out/'execute.S','dut-execute')]
    elf=out/(APP.name+'.elf');b.bind_sources([b.common/'link.ld'])
    b.link([b.cc,*b.flags,'-fuse-ld=lld','-static','-nostartfiles','-Wl,--gc-sections','-T'+str(b.common/'link.ld'),
        *objects,'-lm','-L'+str(b.llvm/'lib/generic'),'-lclang_rt.builtins-riscv64','-o',elf],'dut.link')
    meta=json.loads(b.run([b.llvm/'bin/llvm-readobj','--elf-output-style=JSON','--sections','--symbols',elf],'dut.metadata').stdout)[0]
    symbols={r['Symbol']['Name']['Name']:r['Symbol'] for r in meta['Symbols']};blob=elf.read_bytes()
    def at(name):
        sym=symbols[name];sections=[r['Section'] for r in meta['Sections'] if r['Section']['Type']['Name']!='SHT_NOBITS' and
            r['Section']['Address']<=sym['Value'] and sym['Value']+sym['Size']<=r['Section']['Address']+r['Section']['Size']]
        common.require(len(sections)==1,'Unique ELF '+name);sec=sections[0]
        start=sec['Offset']+sym['Value']-sec['Address'];return blob[start:start+sym['Size']]
    common.require(at('seed')==old.seed_bytes(),'ELF initialized seed')
    sites=[]
    for phase,(w,a,g,_) in enumerate(fixture()):
        for name,data in [('weight',w),('activation',a),('weight_expected',w),('activation_expected',a),('gold',g)]:
            name+=str(phase);common.require(at(name)==data and symbols[name]['Value']%64==0,'Exact ELF '+name)
        code=at('matrix_exec'+str(phase));common.require(code.count(struct.pack('<I',WORDS[phase]))==1,'Sole phase custom')
        common.require((symbols['weight'+str(phase)]['Value']+74)%16==10 and
            (symbols['activation'+str(phase)]['Value']+(76 if phase else 64))%16==(12 if phase else 0),'Concrete pointer phases')
        sites.append(dict(pc=symbols['matrix_qbexec_site'+str(phase)]['Value'],word=WORDS[phase]))
    uart=old.uart_gate(meta,blob);common.save(out/'uart-proof.json',uart)
    b.run([b.llvm/'bin/llvm-objdump','-d',elf],'dut.disassembly')
    fit=ROOT/'verification/coverage/check_elf_fit.py';b.bind_sources([fit])
    b.run([ROOT/'verification/tools/soc-venv/bin/python',fit,'--elf',elf,'--ram-bytes','0x200000','--output',out/'elf-fit.json'],'elf-fit')
    record=dict(status='TWO_PHASE_HOST_INTEGER_GOLD_QBS_CROSSCHECK_ELF_READY_NOT_DUT_PASS',
        binary=str(elf),binary_sha256=common.sha(elf),commands=2,host_checks=14,dut_checks=12,host_negative_tests=18,
        phases=[dict(profile='Q2_K',m=4,wp=10,ap=0,weight_block_bytes=84,active_outputs=32),
                dict(profile='Q6_K',m=8,wp=10,ap=12,weight_block_bytes=210,active_outputs=64)],
        n=8,k_blocks=2,weight_layout='ROW',activation_layout='ROW',activation_profile='Q8_K',
        activation_block_bytes=292,full_vrf_checkpoint_bytes=[4096,4096],csr_values_per_checkpoint=12,
        all_source_container_bytes_per_checkpoint=12416,sites=sites,uart_proof=uart,
        independent_gold='Python packed-byte integer dot/min, exact finite FP32; QBS reference crosscheck only',
        candidate_mapping_upper_bound=4120,upper_bound_is_not_gain=True,
        budget_s=600,VPD_limit_bytes=67108864,custom_spike_pass=False,full_scalar_ISA_verified=False,
        native_pending_overwrite_proven=False,history_ELF_dedup_pending=True,vcs_launched=False,coverage_admitted=False,RTL_changed=False)
    record['input_pins']={**b.sources,**b.tools,**b.link_inputs};common.verify(record['input_pins'])
    record['output_pins']=common.pins(p for p in out.iterdir() if p.is_file())
    common.save(out/'preflight-manifest.json',record)
    return dict(manifest=str(out/'preflight-manifest.json'),seal=common.sha(out/'preflight-manifest.json'),elf_sha256=common.sha(elf))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    print(json.dumps(build(p.parse_args().output.resolve())),flush=True)
