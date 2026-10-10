"""Read-only producer classification, not a gain forecast or waiver proof."""
import argparse
from collections import Counter
from pathlib import Path
import json
import preflight_sv39_fault_alternating771 as p

def classify(scope,name):
    if name.startswith(('qbs_','akv_')):
        return 'OTHER_SCENARIO','Custom producer must own QBS/AKV transaction; none issued here.'
    if 'fof' in name or 'vstart' in name:
        return 'OTHER_SCENARIO','This ordinary VL1 first-element fault has FOF=0 and fault vstart=0.'
    if name.startswith('store_b_exception'):
        return 'OTHER_SCENARIO','B-response error producer is distinct from MMU invalid-leaf page fault.'
    if name.startswith(('icache_','misaligned_')) or name=='ptw_access_exception':
        return 'OTHER_SCENARIO','Code mapping valid, target64-aligned, invalid leaf is page not access fault.'
    if name.endswith(('.gva','.tinst','.tval2')):
        return 'CONSTANT_PROOF_REQUIRED','RVH0 suggests inactive guest metadata; full writer/config proof required, no exclusion.'
    if name.endswith('.cause'):
        return 'MIXED_SEMANTIC_BITS','Current values13/15 use bits0..3 only; cause63..4 require separate all-writer proof, not expected gain.'
    if name.endswith(('.tval','.valid')) or name.startswith('exception_slot_'):
        return 'CURRENT_SCENARIO_PATH','Ordinary shared MMU/addrgen/dispatcher fault producer; actual toggles still require measured OR.'
    raise ValueError('Unclassified field '+scope+' '+name)

def prepare(output):
    original=p.OUT/'sv39-fault-alternating-static-targets771-agent-20261007-01.json'
    before=json.loads(original.read_bytes());assert before['baseline_seal']==p.BASE_SHA
    pins={str(original):p.life.digest(original),str(Path(__file__).resolve()):p.life.digest(Path(__file__)),
      str(p.BASE/'admission-manifest.json'):p.BASE_SHA,str(p.shared.SOURCE):p.shared.SOURCE_SHA}
    book=p.life.read_bound(p.shared.SOURCE,p.shared.SOURCE_SHA)
    for rel in ('hardware/src/vlsu/addrgen.sv','hardware/src/vlsu/vlsu.sv','hardware/src/vlsu/vstu.sv',
      'hardware/deps/cva6/core/load_store_unit.sv','hardware/deps/cva6/core/cva6_mmu/cva6_mmu.sv'):
        path=p.ROOT/rel;pins[str(path)]=book[str(path)]
    p.life.check(pins);groups=Counter();rows=[]
    for item in before['candidates']:
        category,reason=classify(item['scope'],item['name']);groups[category]+=len(item['positions'])
        row=dict(item,category=category,producer_reason=reason,expected_gain=None)
        if category=='MIXED_SEMANTIC_BITS':
            row['logical_current_case_bits']=[0,1,2,3]
            row['logical_outside_case_bits']=list(range(4,64))
            row['raw_low_bit_coordinate_mapping']='NOT_PROVED; entire cause raw vector is not target gain.'
        rows.append(row)
    assert len(rows)==121 and sum(groups.values())==7622
    p.life.save(output,dict(status='READONLY_PRODUCER_CLASSIFICATION_NOT_WAIVER_OR_GAIN',baseline=771,
      baseline_seal=p.BASE_SHA,records=rows,diagnostic_pool_slots_by_category=dict(groups),pins=pins,
      current_case='RVV unit-stride VL1 invalid leaf,4loads/4stores cause13/15, no scalar LSU-specific promise',
      source_chain=['load_store_unit.sv439..462 shared MMU accelerator arbitration',
        'cva6_mmu.sv655..698 PTW page fault producer',
        'addrgen.sv1213..1249 buffer exception +zero-address exception token;520..536 propagation',
        'vlsu.sv998..1001 normal exception arbitration'],
      known_values=dict(FOF=0,vstart=0,RVH=0,cause=[13,15]),
      gain_authority='Actual compatible candidateVDB OR exact admitted771; no forecast from7622 slots.',
      waiver_applied=False,EDA_launched=False,running_manifest_modified=False))
    print(p.life.digest(output),dict(groups))

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--output',type=Path,required=True)
    prepare(a.parse_args().output.resolve())
