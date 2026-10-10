"""One positive Q2/Q8 ROW command; integer gold versus existing QBS C oracle. No EDA."""
import argparse
import ast
import json
from pathlib import Path
import struct
import subprocess

import build_gap38_i8_f16_lane3 as common
from types import SimpleNamespace

ROOT=common.ROOT
APP=ROOT/'apps/qbs_k2_row_pending781'
WORD=0x06b5045b


def seed_bytes():return b''.join(struct.pack('<I',0x12340000+i) for i in range(1024))


def uart_gate(metadata,blob):
    path=ROOT/'verification/tests/build_qbs_payload_matrix4_uart.py'
    tree=ast.parse(path.read_text())
    funcs=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('signed','printf_gate')]
    common.require(len(funcs)==2,'Existing UART gate exact functions')
    namespace={'base':SimpleNamespace(common=common)}
    exec(compile(ast.Module(body=funcs,type_ignores=[]),str(path),'exec'),namespace)
    return namespace['printf_gate'](metadata,blob)


def q(row,k,i):return (i+3*row+k*(i//16+1))&3
def s(row,k,g):return (3*g+row+k)%7+1
def minimum(row,k,g):return (5*g+row+2*k)%7+1
def a(ctx,k,i):return (5*i+3*ctx+2*k)%15-7


def fixture():
    weight=bytearray([0xa5]*1536);activation=bytearray([0x5a]*2496)
    for row in range(8):
        for k in range(2):
            b=bytearray(84)
            for g in range(16):b[g]=s(row,k,g)|(minimum(row,k,g)<<4)
            for i in range(256):
                half,rem=divmod(i,128);group,lane=divmod(rem,16)
                b[16+32*half+16*(group&1)+lane]|=q(row,k,i)<<(2*(group//2))
            struct.pack_into('<HH',b,80,0x3c00,0x3c00)
            start=74+(2*row+k)*84;weight[start:start+84]=b
    for ctx in range(4):
        for k in range(2):
            start=64+(2*ctx+k)*292
            struct.pack_into('<I',activation,start,0x3f800000)
            for i in range(256):activation[start+4+i]=a(ctx,k,i)&255
            for g in range(16):
                struct.pack_into('<h',activation,start+260+2*g,
                    sum(a(ctx,k,i) for i in range(16*g,16*g+16)))
    image=bytearray(seed_bytes())
    # M1--M4 clears the complete destination group, unlike M8 tail-preservation.
    image[1024:1536]=bytes(512)
    values=[]
    for ctx in range(4):
        for row in range(8):
            dot=0;mins=0
            for k in range(2):
                for g in range(16):
                    dot+=s(row,k,g)*sum(q(row,k,i)*a(ctx,k,i) for i in range(16*g,16*g+16))
                    mins+=minimum(row,k,g)*sum(a(ctx,k,i) for i in range(16*g,16*g+16))
                    common.require(max(abs(dot),abs(mins),abs(dot-mins))<2**23,'Exact FP32 intermediates')
            value=dot-mins;values.append(value)
            struct.pack_into('<f',image,1024+128*ctx+4*row,value)
    return bytes(weight),bytes(activation),bytes(image),values


def header():
    w,a_,gold,_=fixture();lines=[]
    for name,data,const in [('seed',seed_bytes(),True),('weight',w,False),
        ('activation',a_,False),('weight_expected',w,True),('activation_expected',a_,True),('gold',gold,True)]:
        values=[int.from_bytes(data[i:i+8],'little') for i in range(0,len(data),8)]
        lines.append('%suint64_t %s[%d] __attribute__((aligned(64)))={%s};'%
            ('const ' if const else '',name,len(values),','.join('UINT64_C(%s)'%hex(v) for v in values)))
    return '\n'.join(lines)+'\n'


def build(out):
    common.require(not out.exists() and out.parent==ROOT/'verification/out','Fresh output')
    out.mkdir();b=common.Build(out);b.sources={}
    assembly_source=ROOT/'apps/qbs_gap110_q3_r4_tail/execute.S'
    probe=ROOT/'verification/coverage/qbs_k2_row_pending781_probe.tcl'
    book=ROOT/'verification/out/repaired-aligned-build-20260930-01/build-source-pins.json'
    expected=common.read(book)['files'] if 'files' in common.read(book) else common.read(book)
    # Bind exactly the source paths represented by this candidate, not a new historical replay.
    source_paths=['hardware/src/vlsu/qbs/'+n+'.sv' for n in
        ('qbs_read_engine','qbs_engine','qbs_block_adapter','qbs_payload_buffer','qbs_compute_engine','qbs_descriptor_decoder')]
    source_paths+=['hardware/include/qbs_pkg.sv']
    for name in source_paths:
        entry=expected.get(name,expected.get(str(ROOT/name)))
        if isinstance(entry,dict):entry=entry.get('sha256')
        common.require(common.sha(ROOT/name)==entry,'Frozen source '+name)
    ref=ROOT/'verification/qbs/qbs_ref.c'
    b.bind_sources([Path(__file__),ROOT/'verification/tests/build_qbs_payload_matrix4_uart.py',Path(common.__file__),
        Path(__file__).with_name('test_qbs_k2_row_pending781.py'),APP/'main.c',assembly_source,
        ref,ref.with_suffix('.h'),probe,book,*[ROOT/p for p in source_paths]])
    (out/'fixture.h').write_text(header())
    assembly=assembly_source.read_text().split('MATRIX_EXEC 0,')[0].replace('gap110_','matrix_')
    assembly+='\nMATRIX_EXEC 0, 8, 0x06b5045b\n'
    (out/'execute.S').write_text(assembly)
    inc=['-I'+str(out)]
    host_obj=b.compile(APP/'main.c','host-main',[*inc,'-DMATRIX_HOST=1','-Wno-misleading-indentation'],host=True)
    ref_obj=b.compile(ref,'host-ref',host=True)
    host=out/'host';b.link([b.host,host_obj,ref_obj,'-lm','-o',host],'host.link')
    log=b.run([host],'host-checks').stdout.decode()
    common.require(log.splitlines()==['QBS_PENDING checks=7 errors=0',
        'PASSED: qbs_k2_row_pending781 commands=1 errors=0'],'Independent Q2 integer/native gold')
    mutations=('weight','activation','vrf','dest','tail','guard','csr','descriptor','sourceguard')
    for kind in mutations:
        result=subprocess.run([host,kind],capture_output=True,timeout=10)
        (out/('negative-'+kind+'.log')).write_bytes(result.stdout+result.stderr)
        common.require(result.returncode==1 and b'FAILED:' in result.stdout,'Mutation escaped '+kind)
    objects=[b.compile(b.common/n,'dut-'+n) for n in ('crt0.S','printf.c','string.c','serial.c','util.c','print_trap_cause.c')]
    objects+=[b.compile(APP/'main.c','dut-main',inc),b.compile(out/'execute.S','dut-execute')]
    elf=out/(APP.name+'.elf');b.bind_sources([b.common/'link.ld'])
    b.link([b.cc,*b.flags,'-fuse-ld=lld','-static','-nostartfiles','-Wl,--gc-sections','-T'+str(b.common/'link.ld'),
        *objects,'-lm','-L'+str(b.llvm/'lib/generic'),'-lclang_rt.builtins-riscv64','-o',elf],'dut.link')
    meta=json.loads(b.run([b.llvm/'bin/llvm-readobj','--elf-output-style=JSON','--sections','--symbols',elf],'dut.metadata').stdout)[0]
    symbols={r['Symbol']['Name']['Name']:r['Symbol'] for r in meta['Symbols']};blob=elf.read_bytes()
    def at(name):
        sym=symbols[name]
        sections=[r['Section'] for r in meta['Sections'] if r['Section']['Type']['Name']!='SHT_NOBITS' and
            r['Section']['Address']<=sym['Value'] and sym['Value']+sym['Size']<=r['Section']['Address']+r['Section']['Size']]
        common.require(len(sections)==1,'Unique ELF '+name);sec=sections[0]
        start=sec['Offset']+sym['Value']-sec['Address'];return blob[start:start+sym['Size']]
    for name,data in [('seed',seed_bytes()),('weight',fixture()[0]),('activation',fixture()[1]),
        ('weight_expected',fixture()[0]),('activation_expected',fixture()[1]),('gold',fixture()[2])]:
        common.require(at(name)==data and symbols[name]['Value']%64==0,'Exact ELF data '+name)
    pc=symbols['matrix_qbexec_site0']['Value'];code=at('matrix_exec0')
    common.require(code.count(struct.pack('<I',WORD))==1,'Exactly one M4 custom encoding')
    common.require((symbols['weight']['Value']+74)%16==10 and (symbols['activation']['Value']+64)%16==0,'Exact first-lane phases')
    proof=uart_gate(meta,blob);common.save(out/'uart-proof.json',proof)
    b.run([b.llvm/'bin/llvm-objdump','-d',elf],'dut.disassembly')
    fit=ROOT/'verification/coverage/check_elf_fit.py';b.bind_sources([fit])
    b.run([ROOT/'verification/tools/soc-venv/bin/python',fit,'--elf',elf,'--ram-bytes','0x200000','--output',out/'elf-fit.json'],'elf-fit')
    record=dict(status='HOST_NATIVE_QBS_GOLD_ELF_READY_NOT_DUT_PASS',binary=str(elf),binary_sha256=common.sha(elf),
        baseline=781,m=4,n=8,k_blocks=2,weight_profile=7,activation_profile=1,weight_layout=1,activation_layout=1,
        wp=10,ap=0,commands=1,host_checks=7,dut_checks=6,host_negative_tests=len(mutations),
        full_vrf_bytes=4096,csr_values=12,source_readback_bytes=4032,active_outputs=32,
        active_result_bytes=128,legacy_m4_zero_tail_bytes=384,sites=[dict(pc=pc,word=WORD)],uart_proof=proof,
        conditional_prediction_directions=222,prediction_is_not_measured_gain=True,
        primary_missing_coordinates=[21532,21533],primary_hit='gen_write_merge[0].gen_bank_plane[2].gen_bank_row[2].gen_byte_merge[5].hit[13]',
        pending_witness=dict(context=2,k_block=1,range_offset=1460,offset=28,take=16,
            condition='older slot empty; slot1 selects word0',remaining=0xff00,pending_writer=13,pending_word=1,pending_byte_lane=5),
        budget_s=600,custom_spike_pass=False,full_scalar_ISA_verified=False,vcs_launched=False,coverage_admitted=False,rtl_changed=False)
    record['input_pins']={**b.sources,**b.tools,**b.link_inputs};common.verify(record['input_pins'])
    record['output_pins']=common.pins(p for p in out.iterdir() if p.is_file())
    common.save(out/'preflight-manifest.json',record)
    return dict(manifest=str(out/'preflight-manifest.json'),seal=common.sha(out/'preflight-manifest.json'),elf_sha256=common.sha(elf))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    print(json.dumps(build(parser.parse_args().output.resolve())),flush=True)
