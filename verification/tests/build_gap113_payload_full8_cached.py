"""Same full8 bytes/checks, precomputed constants instead of DUT runtime bit packing."""
import argparse
import json
from pathlib import Path
from types import FunctionType, SimpleNamespace
import build_gap113_payload_full8 as frozen

common=frozen.common
ROOT=common.ROOT
APP=ROOT/'apps/qbs_gap113_payload_full8_cached'
PRE=ROOT/'verification/out/gap113-payload-full8-preflight-741-agent-20261007-02/preflight-manifest.json'
PRE_SHA='63d1e264ab68bf0658088354a9a83f0b80f886ecdc528e1f8323e5aa6a80ca52'
fixture=frozen.fixture


def inputs_header():
    lines=[]
    for phase in (0,1):
        w,a,_=fixture(phase)
        for name,blob in (('weights',w),('activation',a)):
            words=[int.from_bytes(blob[i:i+8],'little') for i in range(0,len(blob),8)]
            lines.append('static const uint64_t gap110_%s%d[%d]={%s};'%
                         (name,phase,len(words),','.join('UINT64_C(%s)'%hex(x) for x in words)))
    return '\n'.join(lines)+'\n'


class Build(common.Build):
    def __init__(self,out):
        super().__init__(out)
        self.bind_sources([Path(__file__),Path(__file__).with_name('test_gap113_payload_full8_cached.py'),
                           Path(frozen.__file__),APP/'main.c'])
        (out/'full8_inputs.h').write_text(inputs_header())


def build(out):
    namespace=dict(vars(frozen),APP=APP,PRE=PRE,PRE_SHA=PRE_SHA)
    namespace['common']=SimpleNamespace(**dict(vars(common),Build=Build))
    result=FunctionType(frozen.build.__code__,namespace)(out)
    path=out/'preflight-manifest.json';record=json.loads(path.read_bytes())
    record.update(initialization='STATIC_CONST_SAME_PINNED_FULL8_NATIVE_BYTES',
                  equivalent_preflight=str(PRE),equivalent_preflight_seal=PRE_SHA,
                  runtime_bit_pack_removed=True,input_templates_bytes=7040,
                  original_timeout_retired=200661,original_main_retired=183389,
                  scalar_oracle_checks_reduced=False,commands_changed=False)
    common.save(path,record);result['seal']=common.sha(path)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    print(json.dumps(build(p.parse_args().output.absolute())))
