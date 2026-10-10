"""Compact four Q6 jobs: independent logical integer/C-ref gold, actual ELF; no VCS."""
import argparse
import json
from pathlib import Path
import struct
import subprocess
import sys

import build_gap38_i8_f16_lane3 as common
import audit_gap110_q3_r4 as audit
sys.path.insert(0,str(common.ROOT/'verification/coverage'))
import select_qbs_payload_matrix764 as selected

ROOT=common.ROOT
APP=ROOT/'apps/qbs_payload_matrix4'
PLAN=ROOT/'verification/out/qbs-payload-greedy8-proposal764-agent-20261007-01.json'
PLAN_SHA='10655e55300a6a4c71fab69db42362c16c892baf9b8441953fdf09482b60305e'
WP=(14,6,10,2);AP=(8,12,8,8);LAYOUT=(2,2,1,1)


def quant(row,i):return ((17*i+7*row)&63)-32
def scale(row,g):return (3*g+row)%9-4
def activation(phase,ctx,i):return -86 if ((i//32)^(ctx&1)^(phase&1))&1==0 else 85


def fixture(phase):
    common.require(type(phase) is int and 0<=phase<4,'Four exact jobs')
    weight=bytearray([0xa5]*2048);act=bytearray([0x5a]*2496)
    for r in range(8):
        b=bytearray(210)
        for i in range(256):
            half,rem=divmod(i,128);quarter,lane=divmod(rem,32);q=quant(r,i)+32
            low=64*half+32*(quarter&1)+lane;high=32*half+lane
            b[low]|=(q&15)<<(4*(quarter//2));b[128+high]|=(q>>4)<<(2*quarter)
        for g in range(16):b[192+g]=scale(r,g)&255
        struct.pack_into('<H',b,208,0x3c00)
        start=64+WP[phase]+210*r;weight[start:start+210]=b
    start=64+AP[phase]
    for c in range(8):
        struct.pack_into('<I',act,start+4*c,0x3f800000)
        for i in range(256):act[start+32+8*i+c]=activation(phase,c,i)&255
        for g in range(16):struct.pack_into('<h',act,start+2080+16*g+2*c,sum(activation(phase,c,i) for i in range(16*g,16*g+16)))
    gold=[]
    for c in range(8):
        for r in range(8):
            dot=0
            for g in range(16):
                dot+=scale(r,g)*sum(quant(r,i)*activation(phase,c,i) for i in range(16*g,16*g+16))
                common.require(abs(dot)<2**23,'Exact bounded FP32 intermediate')
            gold.append(int.from_bytes(struct.pack('<f',dot),'little'))
    return bytes(weight),bytes(act),gold


def seed_bytes():return b''.join(struct.pack('<I',0x12340000+i) for i in range(1024))


def expected_frame(phase):
    image=bytearray(seed_bytes());gold=fixture(phase)[2]
    for c in range(8):
        for r in range(8):struct.pack_into('<I',image,1024+128*c+4*r,gold[8*c+r])
    return bytes(image)


def header():
    lines=['typedef struct {unsigned wp,ap,layout;const uint64_t *weight,*activation,*expected;} matrix_case_t;']
    def array(name,blob):
        vals=[int.from_bytes(blob[i:i+8],'little') for i in range(0,len(blob),8)]
        lines.append('const uint64_t %s[%d] __attribute__((aligned(64)))={%s};'%(name,len(vals),','.join('UINT64_C(%s)'%hex(v) for v in vals)))
    array('seed',seed_bytes())
    for phase in range(4):
        w,a,_=fixture(phase);array('weight%d'%phase,w);array('activation%d'%phase,a);array('gold%d'%phase,expected_frame(phase))
    lines.append('static const matrix_case_t cases[4]={'+','.join('{%d,%d,%d,weight%d,activation%d,gold%d}'%(WP[i],AP[i],LAYOUT[i],i,i,i) for i in range(4))+'};')
    return '\n'.join(lines)+'\n'


def build(out):
    common.require(not out.exists() and out.parent==ROOT/'verification/out','Fresh output')
    plan=common.read(PLAN);common.require(common.sha(PLAN)==PLAN_SHA and plan['baseline']==764,'Typed764 plan')
    commands=plan['commands'][:4]
    common.require([(c['weight_profile_enum'],c['weight_phase'],c['activation_phase']) for c in commands]==
                   [(2,WP[i],AP[i]) for i in range(4)],'Exact first4 Q6 jobs')
    targets=[t for c in commands for t in c['fresh_typed_coordinates']]
    common.require(len(targets)==2320,'Exact first4 union')
    source={(t['scope'],t['raw_coordinate']):t for t in plan['targets']}
    target_records=[source[t['scope'],t['raw_coordinate']] for t in targets]
    out.mkdir();b=common.Build(out)
    ref=ROOT/'verification/qbs/qbs_ref.c';old=ROOT/'apps/qbs_gap110_q3_r4_tail/execute.S'
    b.bind_sources([Path(__file__),Path(__file__).with_name('test_qbs_payload_matrix4.py'),APP/'main.c',
        ref,ref.with_suffix('.h'),ROOT/'apps/common/qbs_abi.h',old,PLAN,Path(common.__file__),Path(audit.__file__)])
    (out/'matrix_data.h').write_text(header())
    assembly=old.read_text().split('MATRIX_EXEC 0,')[0].replace('gap110_','matrix_')
    assembly+='\n'+'\n'.join('MATRIX_EXEC %d, 8, 0x0eb5045b'%i for i in range(4))+'\n'
    (out/'execute.S').write_text(assembly)
    inc=['-I'+str(out)]
    host_obj=b.compile(APP/'main.c','host-main',[*inc,'-DMATRIX_HOST=1'],host=True)
    ref_obj=b.compile(ref,'host-ref',host=True)
    host=out/'host';b.link([b.host,host_obj,ref_obj,'-lm','-o',host],'host.link')
    log=b.run([host],'host-checks').stdout.decode()
    common.require(log.splitlines()==['QBS_MATRIX phase=%d checks=%d errors=0'%(i,7*(i+1)) for i in range(4)]+
        ['PASSED: qbs_payload_matrix4 commands=4 errors=0'],'Actual all-format C reference/logical gold mismatch')
    negatives=[]
    for phase in range(4):
        for kind in ('vrf','dest','guard','csr','descriptor','source'):
            r=subprocess.run([host,kind,str(phase)],capture_output=True,timeout=10)
            common.require(r.returncode==1 and b'FAILED: qbs_payload_matrix4' in r.stdout,'Negative escaped '+kind)
            p=out/('negative-%d-%s.log'%(phase,kind));p.write_bytes(r.stdout+r.stderr);negatives.append(str(p))
    objects=[b.compile(b.common/n,'dut-'+n) for n in ('crt0.S','printf.c','string.c','serial.c','util.c','print_trap_cause.c')]
    objects+=[b.compile(APP/'main.c','dut-main',inc),b.compile(out/'execute.S','dut-execute')]
    elf=out/(APP.name+'.elf');b.bind_sources([b.common/'link.ld'])
    b.link([b.cc,*b.flags,'-fuse-ld=lld','-static','-nostartfiles','-Wl,--gc-sections','-T'+str(b.common/'link.ld'),
        *objects,'-lm','-L'+str(b.llvm/'lib/generic'),'-lclang_rt.builtins-riscv64','-o',elf],'dut.link')
    meta=json.loads(b.run([b.llvm/'bin/llvm-readobj','--elf-output-style=JSON','--sections','--symbols',elf],'dut.metadata').stdout)[0]
    syms={r['Symbol']['Name']['Name']:r['Symbol'] for r in meta['Symbols']};blob=elf.read_bytes();sites=[]
    def at(addr,size):
        sections=[r['Section'] for r in meta['Sections'] if r['Section']['Type']['Name']!='SHT_NOBITS' and
            r['Section']['Address']<=addr and addr+size<=r['Section']['Address']+r['Section']['Size']]
        common.require(len(sections)==1,'Unique ELF bytes');s=sections[0]
        start=s['Offset']+addr-s['Address'];return blob[start:start+size]
    for phase in range(4):
        func=syms['matrix_exec%d'%phase];pc=syms['matrix_qbexec_site%d'%phase]['Value'];code=at(func['Value'],func['Size'])
        words=[];pcs=[];pos=0
        while pos<len(code):
            length=4 if int.from_bytes(code[pos:pos+2],'little')&3==3 else 2
            common.require(pos+length<=len(code),'Complete ELF instructions');pcs.append(func['Value']+pos)
            words.append(int.from_bytes(code[pos:pos+length],'little'));pos+=length
        common.require(words[pcs.index(pc)]==0x0eb5045b and any(words[i] in (0x42a1,0x00800293) and
            words[i+1]==0x0102f057 for i in range(len(words)-1)),'Exact M8/VL8')
        words[pcs.index(pc)]=0x08b5045b;audit.audit_execution(words,pcs,pc)
        sites.append(dict(pc=pc,word=0x0eb5045b))
        for name,expected in [('weight%d'%phase,fixture(phase)[0]),('activation%d'%phase,fixture(phase)[1]),
                              ('gold%d'%phase,expected_frame(phase)),('seed',seed_bytes())]:
            sym=syms[name];common.require(sym['Size']==len(expected) and sym['Value']%64==0 and
                at(sym['Value'],sym['Size'])==expected,'Exact static seed/source/gold '+name)
    fit=ROOT/'verification/coverage/check_elf_fit.py';b.bind_sources([fit])
    b.run([ROOT/'verification/tools/soc-venv/bin/python',fit,'--elf',elf,'--ram-bytes','0x200000',
        '--output',out/'elf-fit.json'],'elf-fit')
    target=dict(baseline=764,baseline_seal=selected.model.BASE_SHA,commands=commands,targets=target_records,
        mapping_directions=2320,side_metadata_directions=896,conditional_main_directions=1424,
        measured_gain=None,official_percentage=False)
    common.save(out/'target-prediction.json',target)
    # Source recurrence/compiled shape evidence is shared and checked once, not old full ELF replay.
    inputs={**plan['pins'],**b.sources,**b.tools,**b.link_inputs};common.verify(inputs)
    record=dict(status='MATRIX4_HOST_NATIVE_STATIC_ELF_READY_NOT_DUT_PASS',binary=str(elf),binary_sha256=common.sha(elf),
        input_pins=inputs,output_pins=common.pins(p for p in out.iterdir() if p.is_file()),commands=4,sites=sites,
        baseline=764,m=8,n=8,k_blocks=1,wp=list(WP),ap=list(AP),layout=list(LAYOUT),host_checks=28,
        host_negative_tests=24,dut_checks=24,full_vrf_bytes=16384,initial_seed_bytes_verified=4096,
        source_readback_bytes=18176,csr_values=48,flags=[0]*4,budget_s=600,
        custom_spike_pass=False,full_scalar_ISA_verified=False,vcs_launched=False,coverage_admitted=False,
        rtl_changed=False,software_work_bound='Per job512 full VRF64-bit comparisons+568 complete source64-bit reads, no runtime packing/gold/seed-image generation or source memcpy; four jobs. Previous2 dynamic jobs CPU220.880s; hard600s, no retry.')
    common.save(out/'preflight-manifest.json',record)
    return dict(manifest=str(out/'preflight-manifest.json'),seal=common.sha(out/'preflight-manifest.json'),elf_sha256=common.sha(elf))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    print(json.dumps(build(a.output.resolve())),flush=True)
