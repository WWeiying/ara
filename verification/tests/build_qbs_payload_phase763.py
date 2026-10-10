"""Two Q3/M8 commands with new compact-beat ownership, complete existing gold."""
import argparse
import json
from pathlib import Path
from types import FunctionType, SimpleNamespace

import build_gap113_payload_full8 as frozen
import build_qbs_payload_toggle_alt762 as values
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'coverage'))
import prove_qbs_even_start_hits762 as mapping

common,ROOT=frozen.common,frozen.ROOT
APP=ROOT/'apps/qbs_payload_phase763'
ASK=(12,0)
BASE=ROOT/'verification/out/operand-mask-data-defined-policy-admitted763-agent-20261007-01'
BASE_SHA='962d7292ff80e5fffe4fd8e8e8de00938c32dca3a92d21e179b8cf59f915200c'
STATIC=ROOT/'verification/out/qbs-even-start-hit-static762-agent-20261007-02.json'
STATIC_SHA='e00a593df5e8fc302484209d22965d9cfc9a133a472966beb2a63a481120164d'


def fixture(phase):
    w,a,gold=values.fixture(phase)
    relocated=bytearray([0x5a]*2496)
    relocated[64+ASK[phase]:64+ASK[phase]+2336]=a[68:2404]
    return w,bytes(relocated),gold


def templates():
    body,oracle,assembly=frozen.templates()
    body=frozen.replace_one(body,'c->activation_skew == 4',
                            'c->activation_skew == (current == 0 ? 12u : 0u)')
    return body,oracle,assembly


def prediction():
    common.require(common.sha(STATIC)==STATIC_SHA and common.sha(BASE/'admission-manifest.json')==BASE_SHA,
                   'Explicit static/current763 seal')
    evidence=json.loads(STATIC.read_bytes())
    manifest=json.loads((BASE/'admission-manifest.json').read_bytes())
    bits_path=BASE/'combined-bits.json'
    common.require(common.sha(bits_path)==manifest['output_pins'][str(bits_path)],'Formal763 bitmap pin')
    bits=json.loads(bits_path.read_bytes())
    common.require(len(bits['tests'])==len(set(bits['tests']))==763,'Actual763 population')
    oldbits=json.loads((ROOT/'verification/out/load-ni-tlb-offline-admitted-762-agent-20261007-01/combined-bits.json').read_bytes())
    common.require(bits['tests'][:762]==oldbits['tests'],'Exact762 prefix')
    snapshots=[]
    for phase,skew in enumerate(ASK):
        for offset,first,take in mapping.compact_range(0x80000040+skew,2336):
            hit=set()
            for writer in range(take):
                context,o=mapping.mapping.activation_target(offset+writer,8,4,256)
                plane,byte=mapping.mapping.activation_location(o,4,256)
                if plane==2:hit.add((context//4,context%4,byte,16+writer))
            snapshots.append((phase,offset,first,take,hit))
    targets=[]
    for scope,data in evidence['scopes'].items():
        bank=1 if 'bank1.i_payload_buffer' in scope else 0
        for item in data['records']:
            if not item['classification'].startswith('HOLD') or item['declaration_line']!='381' or item['bit']<16:continue
            key,slot,side=mapping.mapping.identity(item['signal'],item['bit'])
            owner=(bank,key[1],key[3],item['bit'])
            states=[owner in snapshot[4] for snapshot in snapshots]
            # Explicit ordered witness0->1->0, not just a union of feasible bits.
            triples=[i for i in range(1,len(states)-1) if states[i] and not states[i-1] and not states[i+1]]
            if not triples:continue
            index=triples[0]
            record=dict(item,scope=scope,ordered_beats=[list(snapshots[n][:4]) for n in (index-1,index,index+1)],
                        expected_hit_values=[0,1,0])
            targets.append(record)
    common.require(len(targets)==144 and sum(len(t['missing_serialized_coordinates']) for t in targets)==288,
                   'Exact novel144 physical side-hit targets')
    # Check the sole formal763 suffix too, without re-reading762 historical logs.
    native=list((Path(bits['tests'][-1])/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    common.require(len(native)==1,'One admitted763 native Toggle member')
    tree=mapping.mapping.ET.fromstring(mapping.mapping.gzip.open(native[0],'rb').read())
    rows={n.get('name'):n for n in tree.iter('instance_data')}
    for target in targets:
        row=rows[target['scope']]
        common.require(row.get('chksum')=='3657545390' and len(row.get('value'))==66340 and
                       all(row.get('value')[c]=='0' for c in target['missing_serialized_coordinates']),
                       'Predicted target already hit in763')
    return dict(baseline=763,baseline_manifest_sha256=BASE_SHA,source_evidence_sha256=STATIC_SHA,
        targets=targets,physical_bits=144,raw_directions=288,
        suffix_toggle_pin={str(native[0]):common.sha(native[0])},
        hypothesis='Two DIRECT Q8K M8 streams at basephase12/0 instead of4. Every accepted compact beat captures original writer index; newer side hit depends only valid target+location, not selected_word arbitration.',
        qualification_required='Complete native512 destination bytes, all8192 VRF snapshot bytes/CSR/guards/request-response/uop lifecycle and terminal; no Spike custom ISA claim or automatic admission.',
        official_percent_prediction=False,pending_hit_gain_claim=False)


def inputs_header():
    lines=[]
    for phase in (0,1):
        w,a,_=fixture(phase)
        for name,blob in (('weights',w),('activation',a)):
            words=[int.from_bytes(blob[i:i+8],'little') for i in range(0,len(blob),8)]
            lines.append('static const uint64_t gap110_%s%d[%d]={%s};'%(name,phase,len(words),
                ','.join('UINT64_C(%s)'%hex(x) for x in words)))
    return '\n'.join(lines)+'\n'


class Build(common.Build):
    def __init__(self,out):
        super().__init__(out)
        self.bind_sources([Path(__file__),Path(__file__).with_name('test_qbs_payload_phase763.py'),
            APP/'main.c',Path(values.__file__),Path(mapping.__file__),Path(mapping.mapping.__file__),
            STATIC,BASE/'admission-manifest.json',BASE/'combined-bits.json'])
        (out/'full8_inputs.h').write_text(inputs_header())


def build(out):
    expected=prediction()
    ns=dict(vars(frozen),APP=APP,fixture=fixture,templates=templates)
    ns['common']=SimpleNamespace(**dict(vars(common),Build=Build))
    result=FunctionType(frozen.build.__code__,ns)(out)
    path=out/'preflight-manifest.json';record=json.loads(path.read_bytes())
    common.save(out/'target-prediction.json',expected)
    record.update(case=APP.name,baseline=763,activation_skews=list(ASK),
        activation_distinct_bytes_per_context=2,source_alignment_hypothesis=expected['hypothesis'],
        prediction_sha256=common.sha(out/'target-prediction.json'),
        output_pins=common.pins(p for p in out.iterdir() if p.is_file() and p.name!='preflight-manifest.json'))
    common.save(path,record)
    result['seal']=common.sha(path)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    print(json.dumps(build(parser.parse_args().output.resolve())))
