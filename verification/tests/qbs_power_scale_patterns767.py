"""Positive normal power scales, signed native quants; no DUT or gain claim."""
import argparse
import json
from pathlib import Path
import struct
import build_qbs_payload_residual4_766 as previous

common=previous.common
ROOT=previous.ROOT
BASE=ROOT/'verification/out/qbs-payload-residual4-offline-admitted-767-agent-20261007-01'
BASE_SHA='a4dac6fb073fc665cb8f274557d04c8d2bf3ad9291a70bda03bcfdce3542b405'
PROFILE=(2,2,7,7)
SIZE=(210,210,84,84)
WE=( -14,-13,-11,-7,0,1,9,15 )
AE=( -64,-32,-1,0,1,16,32,64 )


def byte_permutation(i,offset):
    value=(73*i+offset)&255
    return ((value<<3)|(value>>5))&255


def activation(phase,ctx,i):return byte_permutation(i,17*ctx+71*phase)-128
def quant(phase,row,i):
    x=byte_permutation(i,37*row+29*phase)
    return (x&63)-32 if phase<2 else x&3
def scale(phase,row,g):return ((29*g+37*row+73*phase)&255)-128 if phase<2 else (5*g+7*row+phase)&15
def minimum(phase,row,g):return (11*g+3*row+5*phase)&15


def exact32(integer,power):
    common.require(type(integer) is int and type(power) is int,'Exact integer/power types')
    if integer==0:return 0
    magnitude=abs(integer);length=magnitude.bit_length()
    common.require(length<=24,'No silently rounded integer significand')
    exponent=power+length-1
    common.require(-126<=exponent<=127,'Normal finite output only')
    return ((integer<0)<<31)|((exponent+127)<<23)|((magnitude<<(24-length))&0x7fffff)


def integer_pair(phase,row,ctx):
    dot=sum(scale(phase,row,i//16)*quant(phase,row,i)*activation(phase,ctx,i) for i in range(256))
    aux=0 if phase<2 else sum(minimum(phase,row,i//16)*activation(phase,ctx,i) for i in range(256))
    common.require(max(abs(dot),abs(aux),abs(dot-aux))<2**23,'Exact I2F and final affine difference bound')
    return dot,aux


def fixture(phase):
    common.require(type(phase) is int and 0<=phase<4,'Exact four commands')
    w=bytearray([0xa5]*2048);a=bytearray([0x5a]*2496)
    for row in range(8):
        b=bytearray(SIZE[phase]);we=WE[(row+phase)%8]
        if phase<2:
            for i in range(256):
                half,rem=divmod(i,128);quarter,lane=divmod(rem,32);q=quant(phase,row,i)+32
                b[64*half+32*(quarter&1)+lane]|=(q&15)<<(4*(quarter//2))
                b[128+32*half+lane]|=(q>>4)<<(2*quarter)
            for g in range(16):b[192+g]=scale(phase,row,g)&255
            struct.pack_into('<H',b,208,(we+15)<<10)
        else:
            for g in range(16):b[g]=scale(phase,row,g)|(minimum(phase,row,g)<<4)
            for i in range(256):
                half,rem=divmod(i,128);group,lane=divmod(rem,16)
                b[16+32*half+16*(group&1)+lane]|=quant(phase,row,i)<<(2*(group//2))
            struct.pack_into('<HH',b,80,(we+15)<<10,(we+15)<<10)
        w[64+SIZE[phase]*row:64+SIZE[phase]*(row+1)]=b
    for ctx in range(8):
        struct.pack_into('<I',a,64+4*ctx,(AE[(ctx+phase)%8]+127)<<23)
        for i in range(256):a[64+32+8*i+ctx]=activation(phase,ctx,i)&255
        for g in range(16):struct.pack_into('<h',a,64+2080+16*g+2*ctx,sum(activation(phase,ctx,i) for i in range(16*g,16*g+16)))
    gold=[]
    for ctx in range(8):
        for row in range(8):
            dot,aux=integer_pair(phase,row,ctx)
            gold.append(exact32(dot-aux,WE[(row+phase)%8]+AE[(ctx+phase)%8]))
    return bytes(w),bytes(a),gold


def frame(phase):
    image=bytearray(previous.base.seed_bytes());gold=fixture(phase)[2]
    for ctx in range(8):
        for row in range(8):struct.pack_into('<I',image,1024+128*ctx+4*row,gold[8*ctx+row])
    return bytes(image)


def header():
    lines=['typedef struct {unsigned wp,ap,layout,profile,weight_bytes;const uint64_t *weight,*activation,*expected;} matrix_case_t;']
    def array(name,data):
        values=[int.from_bytes(data[i:i+8],'little') for i in range(0,len(data),8)]
        lines.append('const uint64_t %s[%d] __attribute__((aligned(64)))={%s};'%(name,len(values),','.join('UINT64_C(%s)'%hex(v) for v in values)))
    array('seed',previous.base.seed_bytes())
    for phase in range(4):
        w,a,_=fixture(phase);array('weight%d'%phase,w);array('activation%d'%phase,a);array('gold%d'%phase,frame(phase))
    lines.append('static const matrix_case_t cases[4]={'+','.join('{0,0,2,%d,%d,weight%d,activation%d,gold%d}'%(PROFILE[p],8*SIZE[p],p,p,p) for p in range(4))+'};')
    return '\n'.join(lines)+'\n'


def prepare_host(out):
    common.require(out.parent==ROOT/'verification/out' and not out.exists(),'Fresh Host-only diagnostic')
    manifest=common.read(BASE/'admission-manifest.json');common.require(common.sha(BASE/'admission-manifest.json')==BASE_SHA,'Formal767 seal')
    source_pins=common.read(ROOT/'verification/out/repaired-aligned-build-20260930-01/build-source-pins.json')
    rels=['hardware/include/qbs_pkg.sv','hardware/src/vlsu/qbs/qbs_profile_decoder.sv',
          'hardware/src/vlsu/qbs/qbs_profile_engine_int.sv','hardware/src/vlsu/qbs/qbs_compute_engine.sv','hardware/src/vlsu/qbs/qbs_fp_accumulator.sv']
    pins={str(ROOT/r):source_pins[str(ROOT/r)] for r in rels};common.verify(pins)
    out.mkdir();b=common.Build(out);ref=ROOT/'verification/qbs/qbs_ref.c';app=previous.APP/'main.c'
    b.bind_sources([Path(__file__),Path(__file__).with_name('test_qbs_power_scale_patterns767.py'),app,ref,ref.with_suffix('.h'),ROOT/'apps/common/qbs_abi.h',
        Path(previous.__file__),Path(previous.base.__file__),Path(common.__file__),ROOT/'verification/out/repaired-aligned-build-20260930-01/build-source-pins.json'])
    (out/'matrix_data.h').write_text(header())
    obj=b.compile(app,'host-main',['-I'+str(out),'-DMATRIX_HOST=1'],host=True)
    ref_obj=b.compile(ref,'host-ref',host=True);exe=out/'host'
    b.link([b.host,obj,ref_obj,'-lm','-o',exe],'host.link')
    log=b.run([exe],'host-checks').stdout.decode()
    common.require(log.splitlines()==['QBS_MATRIX phase=%d checks=%d errors=0'%(p,7*(p+1)) for p in range(4)]+['PASSED: qbs_payload_matrix4 commands=4 errors=0'],'Independent C reference/native gold mismatch')
    for phase in range(4):
        for kind in ('vrf','dest','guard','csr','descriptor','source'):
            import subprocess
            result=subprocess.run([exe,kind,str(phase)],capture_output=True,timeout=10)
            common.require(result.returncode==1 and b'FAILED:' in result.stdout,'Negative escaped')
            (out/('negative-%d-%s.log'%(phase,kind))).write_bytes(result.stdout+result.stderr)
    commands=[]
    for phase in range(4):
        pairs=[integer_pair(phase,r,c) for c in range(8) for r in range(8)]
        commands.append(dict(profile_enum=PROFILE[phase],m=8,n=8,k_blocks=1,layout='R4_BLOCK_MAJOR',
            weight_half_exponents=[WE[(r+phase)%8] for r in range(8)],activation_fp32_exponents=[AE[(c+phase)%8] for c in range(8)],
            integer_pairs=pairs,expected_bits=fixture(phase)[2],fflags=0,zero_or_nonfinite_scale_allowed=False))
    pins.update(b.sources);pins.update(b.tools);pins[str(BASE/'admission-manifest.json')]=BASE_SHA;common.verify(pins)
    record=dict(status='HOST_NUMERIC_C_REFERENCE_PASS_COMPILED_TARGETS_PENDING_NOT_VCS_READY',baseline=767,baseline_seal=BASE_SHA,
        input_pins=pins,output_pins=common.pins(p for p in out.iterdir() if p.is_file()),commands=commands,
        host_checks=28,negative_tests=24,budget_s=600,measured_gain=None,predicted_gain=None,coverage_admitted=False,vcs_launched=False,
        coordination='Helmholtz owns full102 ranking; join these operand values only with his exact compiled zero coordinates before ELF/runner preparation.',
        protected='All control/valid/ready/BE, unused VRF, CSR and source guards retained. No data or metadata waiver.',
        proof='Exact signed integers <2^23; positive normal power-of-two FP16 d/dmin and FP32 activation d; all I2F/MUL/FMA intermediates normal finite exact. Affine dmin=d, preserving exact integer subtraction.',
        source_chain='profile_decoder -> profile_engine_int subtotal/results -> compute_engine request -> fp_accumulator I2F/MUL/FMADD. Source hashes match frozen build.',
        candidate_objects=['request_dot_i','request_aux_i','request_weight_d_i','request_weight_dmin_i','request_activation_d_i',
            'fp_operands','fp_result','entry_dot_value_q','entry_aux_value_q','entry_scale_value_q','entry_min_scale_value_q','entry_work_value_q','accumulator_data_q'])
    common.save(out/'host-plan.json',record)
    return dict(path=str(out/'host-plan.json'),seal=common.sha(out/'host-plan.json'),host_checks=28,negative_tests=24,vcs_launched=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    print(json.dumps(prepare_host(parser.parse_args().output.resolve())),flush=True)
