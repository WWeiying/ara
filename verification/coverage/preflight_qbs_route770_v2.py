"""Close K-block range residues without changing the sealed K=1 host review."""
from collections import Counter
import json
from pathlib import Path
import preflight_qbs_route770 as p

REPORT=p.OUT/'qbs-route-domain-host-preflight770-agent-20261007-02.json'
PRIOR_SHA='ba572114f744baff41840e3d4cbbb5676333eb870e38081d895f98959c9b256e'


def extra_k_domain():
    domain={0:set(),1:set()}
    # ROW Q8_0 block34*K moves a valid range by2 mod4. Other block292
    # and packed storage272/2336 sizes are multiples of4/16 respectively.
    for profile in ('Q4_0','Q5_0','Q8_0_WEIGHT','IQ4_NL'):
        for phase in range(0,16,4):
            c=p.configuration(profile,'ROW',0,phase)
            effective=dict(c,activation_phase=(phase+2)%16)
            for bank in range(2):
                for beat in p.streams(effective,'activation',bank):
                    for slot in range(2):domain[bank].update(p.overapprox(beat,'activation',slot))
    return domain


def collect():
    p.need(p.digest(p.REPORT)==PRIOR_SHA,'Sealed K1 review')
    r=json.loads(p.REPORT.read_bytes())
    for path,sha in r['pins'].items():p.need(p.digest(path)==sha,'Prior pin drift')
    extra=extra_k_domain();counts=Counter();changed=[]
    for n in r['fields_with_exact_missing_coordinates']:
        bank,role,coord=p.parse_node(n['scope'],{'name':n['name']})
        groups=n['classification_missing_coordinates']
        removed=[]
        for i in groups.get('structural_no_legal_byte_mapping',[]):
            bit=(i-n['attributes']['serialized_offset'])//2
            if (role,coord(bit)) in extra[bank]:removed.append(i)
        if removed:
            groups['structural_no_legal_byte_mapping']=[i for i in groups['structural_no_legal_byte_mapping'] if i not in set(removed)]
            groups.setdefault('legal_mapping_pending_or_schedule_unresolved',[]).extend(removed)
            groups['legal_mapping_pending_or_schedule_unresolved'].sort()
            changed.append({'scope':n['scope'],'name':n['name'],'coordinates':removed})
        for category,positions in groups.items():counts[category]+=len(positions)
    p.need(sum(counts.values())==13428,'Exact full routing gap partition')
    r['status']='STATIC_K_ALL_RESIDUES_SOURCE_REVIEW_NO_NATIVE_OR_PROGRAM_QUALIFICATION'
    r['classification_counts']=dict(counts)
    r['K_block_domain_correction']={'prior_K1_seal':PRIOR_SHA,'changed_structural_to_unresolved':changed,
        'lemma':'Q8_0 ROW effective phase=(activation_base + (context*K_blocks+k)*34)%16. Enumerating even range phases closes K0..255 residues; descriptor activation_base itself remains4-aligned. Q8_K block292 shifts by4; M4/M8 packed block4/8*34 or292 shifts by0mod16. Weight phases already enumerate all8 even residues.'}
    r['simulation_recommended']=False
    r['decision']='Cancel dedicated QBS VCS: selected legal K1 trace gives106 actual missing positions, only112 upper-bound directions. Retain as optional piggyback descriptor after full numerical/ELF/Spike/VRF/CSR preflight; unresolved capacity is not a forecast.'
    r['protected']='All routing control/ports/flags/storage/abort/error paths remain protected. Structural mapping classification does not create a waiver; no temporal all-cycle source-constant promotion.'
    r['pins'][str(p.REPORT)]=PRIOR_SHA
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_preflight_qbs_route770_v2.py')):r['pins'][str(path)]=p.digest(path)
    for path,sha in r['pins'].items():p.need(p.digest(path)==sha,'Final pin closure')
    return r


if __name__=='__main__':
    import argparse
    a=argparse.ArgumentParser();a.add_argument('mode',choices=['prepare','verify']);a.add_argument('--seal');args=a.parse_args()
    if args.mode=='prepare':
        p.need(not REPORT.exists(),'Fresh02 only');r=collect();REPORT.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n')
        print(json.dumps({'report':str(REPORT),'seal':p.digest(REPORT),'counts':r['classification_counts'],'pins':len(r['pins']),'simulation_recommended':False}))
    else:
        p.need(args.seal and p.digest(REPORT)==args.seal,'Exact02 seal');p.need(json.loads(REPORT.read_bytes())==collect(),'Full02 replay equality');print('QBS_ROUTE02_SOURCE_HOST_REPLAY_PASS_NO_DUT_QUALIFICATION')
