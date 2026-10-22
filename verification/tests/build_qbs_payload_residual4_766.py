"""Four fresh formal766 mappings, independent logical gold and native C reference."""
import argparse
import inspect
import json
from pathlib import Path
import struct

import build_qbs_payload_matrix4 as base
import build_qbs_payload_matrix4_uart as uart

common=base.common
ROOT=base.ROOT
APP=ROOT/'apps/qbs_payload_residual4_766'
PLAN=ROOT/'verification/out/qbs-payload-residual-greedy-formal766-agent-20261007-01.json'
PLAN_SHA='b3724d2b64c2fc6159d4403986aebbbae4e9d9adc1993b938e9ed766a726c07e'
BASE_SOURCE_SHA='77444a234bcd294f0000fe27aa77c3424c1ccc17da9c294436457ccb6c00f48a'
WP=(4,4,12,10)
AP=(8,8,8,8)
LAYOUT=(2,1,1,2)
PROFILE=(5,2,2,7)
SIZE=(110,210,210,84)


def logical(phase,row,i):
    if phase in (1,2):return base.quant(row,i)*base.scale(row,i//16)
    if phase==0:return (((17*i+7*row)&7)-4)*base.scale(row,i//16)
    g=i//16
    return ((17*i+7*row)&3)*((3*g+row)%7+1)-((5*g+row)%7+1)


def packed_row(phase,row):
    if phase in (1,2):
        w=base.fixture(0)[0];return w[64+base.WP[0]+210*row:64+base.WP[0]+210*(row+1)]
    b=bytearray(SIZE[phase])
    if phase==0:
        for i in range(256):
            packet,lane=divmod(i,32);q=((17*i+7*row)&7)-4
            b[32+32*(packet//4)+lane]|=(q&3)<<(2*(packet%4))
            if q>=0:b[lane]|=1<<packet
        for g in range(16):
            region,within=divmod(g,4);s=base.scale(row,g)+32
            b[96+(region%2)*4+within]|=(s&15)<<(4*(region//2))
            b[104+within]|=(s>>4)<<(2*region)
        struct.pack_into('<H',b,108,0x3c00)
    else:
        for g in range(16):b[g]=((3*g+row)%7+1)|(((5*g+row)%7+1)<<4)
        for i in range(256):
            half,rem=divmod(i,128);group,lane=divmod(rem,16)
            b[16+32*half+16*(group&1)+lane]|=((17*i+7*row)&3)<<(2*(group//2))
        struct.pack_into('<HH',b,80,0x3c00,0x3c00)
    return bytes(b)


def fixture(phase):
    common.require(type(phase) is int and 0<=phase<4,'Exact four commands')
    weight=bytearray([0xa5]*2048);act=bytearray([0x5a]*2496)
    old_act=base.fixture(phase)[1]
    act[64+AP[phase]:64+AP[phase]+2336]=old_act[64+base.AP[phase]:64+base.AP[phase]+2336]
    for row in range(8):
        start=64+WP[phase]+SIZE[phase]*row
        weight[start:start+SIZE[phase]]=packed_row(phase,row)
    gold=[]
    for ctx in range(8):
        for row in range(8):
            dot=0
            for i in range(256):
                dot+=logical(phase,row,i)*base.activation(phase,ctx,i)
                common.require(abs(dot)<2**23,'Exact integer FP32 accumulation bound')
            gold.append(int.from_bytes(struct.pack('<f',dot),'little'))
    return bytes(weight),bytes(act),gold


def expected_frame(phase):
    image=bytearray(base.seed_bytes());gold=fixture(phase)[2]
    for ctx in range(8):
        for row in range(8):struct.pack_into('<I',image,1024+128*ctx+4*row,gold[8*ctx+row])
    return bytes(image)


def header():
    lines=['typedef struct {unsigned wp,ap,layout,profile,weight_bytes;const uint64_t *weight,*activation,*expected;} matrix_case_t;']
    def array(name,data):
        values=[int.from_bytes(data[i:i+8],'little') for i in range(0,len(data),8)]
        lines.append('const uint64_t %s[%d] __attribute__((aligned(64)))={%s};'%(name,len(values),','.join('UINT64_C(%s)'%hex(v) for v in values)))
    array('seed',base.seed_bytes())
    for phase in range(4):
        w,a,_=fixture(phase);array('weight%d'%phase,w);array('activation%d'%phase,a);array('gold%d'%phase,expected_frame(phase))
    lines.append('static const matrix_case_t cases[4]={'+','.join('{%d,%d,%d,%d,%d,weight%d,activation%d,gold%d}'%(WP[i],AP[i],LAYOUT[i],PROFILE[i],8*SIZE[i],i,i,i) for i in range(4))+'};')
    return '\n'.join(lines)+'\n'


def build(out):
    common.require(common.sha(Path(base.__file__))==BASE_SOURCE_SHA,'Frozen builder drift')
    source=inspect.getsource(base.build)
    replacements={
        "plan['baseline']==764":"plan['baseline']==766",
        "[(2,WP[i],AP[i]) for i in range(4)]":"[(PROFILE[i],WP[i],AP[i]) for i in range(4)]",
        "c['fresh_typed_coordinates']":"c['fresh_coordinates']",
        "len(targets)==2320":"len(targets)==504",
        "baseline=764,baseline_seal=selected.model.BASE_SHA":"baseline=766,baseline_seal=plan['baseline_seal']",
        "mapping_directions=2320,side_metadata_directions=896,conditional_main_directions=1424":"mapping_directions=504,side_metadata_directions=204,conditional_main_directions=300",
        "baseline=764,m=8":"baseline=766,m=8",
    }
    for old,new in replacements.items():
        common.require(source.count(old)==1,'Exact reviewed builder substitution '+old)
        source=source.replace(old,new)
    namespace=dict(vars(base));namespace.update(APP=APP,PLAN=PLAN,PLAN_SHA=PLAN_SHA,WP=WP,AP=AP,LAYOUT=LAYOUT,PROFILE=PROFILE,
        fixture=fixture,expected_frame=expected_frame,header=header)
    exec(compile(source,str(Path(__file__).resolve()),'exec'),namespace)
    result=namespace['build'](out)
    # UART proof consumes the actual newly linked ELF, never the prior image.
    metadata=json.loads((out/'dut.metadata.log').read_bytes())[0]
    proof=uart.printf_gate(metadata,Path(result['manifest']).parent.joinpath(APP.name+'.elf').read_bytes())
    common.save(out/'uart-proof.json',proof)
    record=common.read(out/'preflight-manifest.json')
    extra=[Path(__file__),Path(__file__).with_name('test_qbs_payload_residual4_766.py'),Path(uart.__file__),ROOT/'apps/common/printf.h']
    record['input_pins'].update(common.pins(extra))
    record.update(profile=list(PROFILE),weight_block_bytes=list(SIZE),uart_proof=proof,
        software_work_bound='Same four-command full VRF/CSR/guard/source observer as measured148.680s; different Q3/Q2 latency unmeasured. Hard600s. No VCS launch.',
        predicted_gain=504,measured_gain=None)
    record['output_pins']=common.pins(p for p in out.iterdir() if p.is_file() and p.name!='preflight-manifest.json')
    common.verify(record['input_pins']);common.save(out/'preflight-manifest.json',record)
    result['seal']=common.sha(out/'preflight-manifest.json')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    print(json.dumps(build(parser.parse_args().output.resolve())),flush=True)
