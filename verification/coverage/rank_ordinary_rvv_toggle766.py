"""Read-only exact766 ordinary RVV Toggle ranking; serialized slots are not percentages."""
import argparse
import json
from pathlib import Path
import targeted_toggle_evidence_v2 as n

ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'verification/out'
BASE=OUT/'qbs-payload-matrix4-offline-admitted-766-agent-20261007-01'
BASE_SHA='bbad20298653af04606493c1e6c6433cf22bb9f532b4cc16f52922fe9b7bfb3b'
CONFIG=OUT/'native-batch-full766-agent-20261007-01/config.json'
CONFIG_SHA='ce709dbf1da6a16f16c8c10e7c2006c59429a3ff08c09237a3355a7267f53650'
CACHE=OUT/'toggle741-capacity-ranking-agent-20261007-01.json'
CACHE_SHA='8c9fe15bec6ae5dcd2e5e9dee9c461047db4109464d2c568e3ca5ec9b0bf0865'


def collect():
    pins={str(BASE/'admission-manifest.json'):BASE_SHA,str(CONFIG):CONFIG_SHA,str(CACHE):CACHE_SHA}
    for p,h in pins.items():n.require(n.digest(p)==h,'Frozen baseline/cache/config drift')
    manifest=json.loads((BASE/'admission-manifest.json').read_bytes());config=json.loads(CONFIG.read_bytes())
    ledger=BASE/'combined-inputs.txt';pins[str(ledger)]=manifest['output_pins'][str(ledger)]
    n.require(n.digest(ledger)==pins[str(ledger)],'Formal766 ledger drift')
    inputs=ledger.read_text().splitlines()
    n.require(len(inputs)==len(set(inputs))==767 and inputs==config['input_ledger'],'Exact766 membership required')
    cache=json.loads(CACHE.read_bytes());prior=next(Path(p) for p in cache['input_pins'] if p.endswith('/inputs.txt'))
    pins[str(prior)]=cache['input_pins'][str(prior)]
    n.require(n.digest(prior)==pins[str(prior)] and inputs[:742]==prior.read_text().splitlines(),'Sealed741 prefix differs')
    union={s:{k:r[k] for k in ('width','checksum','bits')} for s,r in cache['instances'].items()}
    scopes=list(union)
    for vdb in inputs[742:]:
        paths=list((Path(vdb)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        n.require(len(paths)==1,'One native suffix per admitted test')
        p=paths[0];n.require(n.digest(p)==config['pins'][str(p)],'Actual suffix pin drift')
        rows,h=n.rows(p,scopes);pins[str(p)]=h;union=n.union(union,rows)
    selected=[s for s in scopes if '.i_ara.' in s and 'i_qbs_engine' not in s and
              any(t in s for t in ('i_operand_queues','i_operand_requester','i_vlsu','i_sldu','i_dispatcher'))]
    # Dispatcher is a peer of i_ara children, not always under .i_ara.
    selected+= [s for s in scopes if s.endswith('.i_ara.i_ara_dispatcher') and s not in selected]
    db=Path(inputs[0])/'snps/coverage/db'
    paths=[db/'design/verilog.design.xml',db/'shape/tgl.verilog.info.xml',db/'shape/tgl.verilog.shape.xml']
    for p in paths:
        n.require(n.digest(p)==config['pins'][str(p)],'Exact compiled design/Toggle shape pin');pins[str(p)]=n.digest(p)
    design,info,shape=(n.xml(p) for p in paths)
    nodes={i.get('id'):(i,m) for m in design.findall('srcdef') for i in m.findall('srcinst')}
    def path(key):
        i,_=nodes[key];parent=i.get('pid')
        return (path(parent)+'.' if parent in nodes else '')+i.get('name')
    modules={path(key):m for key,(_,m) in nodes.items()}
    checks={i.get('name'):i.get('chksum') for i in info.iter('instance_data') if i.get('name') in selected}
    ranking=[]
    for scope in selected:
        row=union[scope];module=modules[scope]
        matches=[d for d in shape.findall('tgldef') if d.get('name')==module.get('name') and d.get('chksum')==checks[scope]]
        mapping='EXACT_MODULE_NAME_AND_CHECKSUM'
        if not matches:
            matches=[d for d in shape.findall('tgldef') if d.get('name','').split(' (')[0]==
                module.get('name','').split(' (')[0] and d.get('chksum')==checks[scope]]
            mapping='MERGED_PARAMETER_NAME_SAME_MODULE_FAMILY_CHECKSUM; NOT_PARAMETER_UNREACHABILITY_PROOF'
        n.require(checks[scope]==row['checksum'],'Compiled/data checksum drift')
        if len(matches)!=1:
            ranking.append(dict(scope=scope,module=module.get('name'),checksum=row['checksum'],
                serialized_width=row['width'],missing_slots=row['width']-bin(int(row['bits'],16)).count('1'),
                typed_mapping='HOLD_AMBIGUOUS_COMPILED_VARIANTS',matching_definitions=len(matches),objects=[]))
            continue
        root=matches[0];offset=0;objects=[]
        binary=format(int(row['bits'],16),'0%db'%row['width'])
        for node in root.find('tglshape'):
            if node.tag=='arrays':continue
            n.require(node.tag in ('node','vectornode'),'Unknown serialized shape node')
            width=1 if node.tag=='node' else abs(int(node.get('left'))-int(node.get('right')))+1
            value=binary[offset:offset+2*width]
            zeros=[offset+k for k,b in enumerate(value) if b=='0']
            if zeros:objects.append(dict(kind=node.tag,**node.attrib,logical_bits=width,
                serialized_offset=offset,missing_slots=len(zeros),missing_coordinates=zeros,
                pair_slot_order_not_native_direction=True))
            offset+=2*width
        n.require(offset==row['width'],'Complete binary serialization width')
        arrays=[dict(kind=a.tag,**a.attrib) for a in root.iter('arrays')]
        ranking.append(dict(scope=scope,module=module.get('name'),checksum=row['checksum'],
            typed_mapping=mapping,
            serialized_width=offset,missing_slots=offset-bin(int(row['bits'],16)).count('1'),
            objects=sorted(objects,key=lambda x:-x['missing_slots']),
            compiled_arrays_not_in_binary_serialization=arrays))
    combined=BASE/'combined-bits.json';pins[str(combined)]=manifest['output_pins'][str(combined)]
    n.require(n.digest(combined)==pins[str(combined)],'Formal four-metric union drift')
    full=json.loads(combined.read_bytes())
    counts={k:len(v) for k,v in full['metrics'].items()}
    pins[str(Path(__file__).resolve())]=n.digest(__file__)
    for p,h in pins.items():n.require(n.digest(p)==h,'End-of-read pin drift')
    return dict(status='FORMAL766_ORDINARY_RVV_SERIALIZED_TOGGLE_STATIC_RANKING',population=766,
        formal_four_metric_instance_counts=counts,binary_toggle_instances=len(union),pins=pins,
        cache_provenance='Sealed741 complete binary local OR, exact formal prefix plus rehashed25 admitted suffixes; '
                         'historical741 data not freshly recollected. Arrays separately unbound, no official denominator claim.',
        scopes=sorted(ranking,key=lambda x:-x['missing_slots']),EDA_launched=False,
        official_percentage=False,waivers_generated=False)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    n.require(not a.output.exists(),'Fresh evidence only');value=collect()
    with a.output.open('x') as s:json.dump(value,s,indent=2);s.write('\n')
    print('STATIC_RANKING_READY',n.digest(a.output),len(value['scopes']))
