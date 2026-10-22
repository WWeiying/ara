"""Two native Q3/Q8 commands; fixed checker reuse, no VCS/EDA invocation."""
import argparse
import json
from pathlib import Path
import struct
from types import FunctionType, SimpleNamespace

import build_gap113_payload_full8 as frozen

common, ROOT = frozen.common, frozen.ROOT
APP = ROOT/'apps/qbs_payload_toggle_alt762'
TARGET = ROOT/'verification/out/qbs-payload-data-toggle-static762-agent-20261007-01.json'
BASE = ROOT/'verification/out/load-ni-tlb-offline-admitted-762-agent-20261007-01'


def activation_byte(phase, context, index):
    common.require(type(phase) is int and phase in (0,1) and type(context) is int and
                   0<=context<8 and type(index) is int and 0<=index<256, 'Recipe bounds')
    return 0x55 if ((index//32) ^ (context&1) ^ phase)&1 else 0xaa


def fixture(phase):
    weight, initial, _ = frozen.fixture(phase)
    activation = bytearray(initial)
    values=[]
    for c in range(8):
        raw=[activation_byte(phase,c,i) for i in range(256)]
        signed=[x if x<128 else x-256 for x in raw];values.append(signed)
        for i,x in enumerate(raw):activation[68+32+8*i+c]=x
        for g in range(16):struct.pack_into('<h',activation,68+2080+16*g+2*c,sum(signed[16*g:16*g+16]))
    gold=[]
    for c in range(8):
        for r in range(8):
            dot=0
            for i in range(256):
                scale=(16*r+i//16)&63;packet,lane=divmod(i,32)
                quant=((i+3*r+packet)&3)+4*(((lane+32*r)>>packet)&1)
                if phase:scale,quant=63-scale,7-quant
                dot+=(scale-32)*(quant-4)*values[c][i]
                common.require(abs(dot)<2**23,'Exact integer intermediate overflow')
            gold.append(struct.unpack('<I',struct.pack('<f',dot))[0])
    return weight,bytes(activation),gold


def inputs_header():
    lines=[]
    for phase in (0,1):
        w,a,_=fixture(phase)
        for name,blob in (('weights',w),('activation',a)):
            words=[int.from_bytes(blob[i:i+8],'little') for i in range(0,len(blob),8)]
            lines.append('static const uint64_t gap110_%s%d[%d]={%s};' %
                         (name,phase,len(words),','.join('UINT64_C(%s)'%hex(x) for x in words)))
    return '\n'.join(lines)+'\n'


class Build(common.Build):
    def __init__(self,out):
        super().__init__(out)
        self.bind_sources([Path(__file__),Path(__file__).with_name('test_qbs_payload_toggle_alt762.py'),
                           APP/'main.c',TARGET,BASE/'admission-manifest.json',BASE/'combined-bits.json'])
        (out/'full8_inputs.h').write_text(inputs_header())


def build(out):
    target=json.loads(TARGET.read_bytes());bits=json.loads((BASE/'combined-bits.json').read_bytes())
    common.require(target['baseline']==762 and len(bits['tests'])==len(set(bits['tests']))==762,
                   'Not explicit formal762')
    common.require(sum(len(r['missing_serialized_coordinates']) for s in target['scopes'].values()
                       for r in s['pure_data_missing'])==32,'Exact pure-data target changed')
    namespace=dict(vars(frozen),APP=APP,fixture=fixture)
    namespace['common']=SimpleNamespace(**dict(vars(common),Build=Build))
    result=FunctionType(frozen.build.__code__,namespace)(out)
    path=out/'preflight-manifest.json';record=json.loads(path.read_bytes())
    # Original body/host labels are provenance, not evidence that the old fixture ran.
    record.update(case=APP.name,baseline=762,baseline_manifest_sha256=common.sha(BASE/'admission-manifest.json'),
                  source_target=str(TARGET),source_target_sha256=common.sha(TARGET),
                  recipe='ALTERNATING_32_QUANT_BLOCKS_55_AA_PER_CONTEXT_THEN_PHASE_COMPLEMENT',
                  activation_distinct_bytes_per_context=2,
                  target_direction_positions=32,guaranteed_coverage_gain=False,
                  no_general_hit_mask_gain_claim=True,initialization='STATIC_CONST',
                  inherited_host_terminal_label='qbs_gap113_payload_full8',
                  spike='NOT_EXECUTED_CUSTOM_QBS_UNSUPPORTED',full_scalar_isa_verified=False)
    common.save(path,record);result['seal']=common.sha(path)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    print(json.dumps(build(p.parse_args().output.absolute())))
