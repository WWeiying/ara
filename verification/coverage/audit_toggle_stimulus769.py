"""Reuse741 cache, append actual769 suffixes; conservative outside-waiver-field ranking."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import targeted_toggle_evidence_v2 as t
import rank_ordinary_rvv_toggle766 as frozen
import queue_fp312_first_full_family as queue

ROOT,OUT,require=frozen.ROOT,frozen.OUT,t.require
BASE=OUT/'mfpu-restart-word-boundary-offline-admitted-770-agent-20261007-01'
PREPARED=OUT/'native-batch-full768-v3-prepared-agent-20261007-02/combined.el'
LZC=OUT/'fma-lzc-assigned23132-native-agent-20261007-01/first.el'


def exclusions(text):
    fields=set();whole=set();scope=None;has_points=False
    def close():
        if scope is not None and not has_points:whole.add(scope)
    for raw in text.splitlines():
        line=raw.strip()
        if not line or line.startswith('//'):continue
        if line.startswith('INSTANCE:'):
            close();scope=line.split(':',1)[1].strip();has_points=False;continue
        if line.startswith(('CHECKSUM:','ANNOTATION:')):continue
        require(scope is not None,'EL record has no scope')
        has_points=True
        if line.startswith('Toggle '):
            m=re.fullmatch(r'Toggle (?:(?:0to1|1to0) )?(\S+)(?: (?:\[-?\d+(?::-?\d+)?\])+)? "(?:logic|reg|net) ([^"]+)"',line)
            require(m is not None,'Unknown typed EL encoding')
            fields.add((scope,m[1]))
        else:require(line.split()[0] in ('Line','Branch','Condition','FSM','Fsm','State','Transition'),'Unknown exclusion directive')
    close();return fields,whole


def overlaps(scope,name,fields,whole):
    if any(scope==s or scope.startswith(s+'.') for s in whole):return True
    return any(name==n or n.startswith(name+'[') for n in fields.get(scope,()))


def collect():
    pins={}
    def pin(p,h=None):
        actual=t.digest(p);require(h is None or h==actual,'Frozen input drift: '+str(p));pins[str(p)]=actual
    pin(BASE/'admission-manifest.json');manifest=json.loads((BASE/'admission-manifest.json').read_bytes())
    require(manifest['coverage_admitted'] is True,'Formal769 not admitted')
    ledger_path=BASE/'combined-inputs.txt';pin(ledger_path,manifest['output_pins'][str(ledger_path)])
    ledger=ledger_path.read_text().splitlines();require(len(ledger)==len(set(ledger))==771,'Exact770 ledger')
    pin(frozen.CACHE,frozen.CACHE_SHA);cache=json.loads(frozen.CACHE.read_bytes())
    prior=next(Path(p) for p in cache['input_pins'] if p.endswith('/inputs.txt'))
    pin(prior,cache['input_pins'][str(prior)]);require(ledger[:742]==prior.read_text().splitlines(),'Exact741 prefix')
    union={s:{k:r[k] for k in ('width','checksum','bits')} for s,r in cache['instances'].items()};scopes=list(union)
    for vdb in ledger[742:]:
        paths=list((Path(vdb)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'));require(len(paths)==1,'One actual suffix')
        p=paths[0];pin(p,manifest['input_pins'][str(p)]);sample,h=t.rows(p,scopes);require(h==pins[str(p)],'Read drift')
        union=t.union(union,sample)
    pin(PREPARED);pin(LZC)
    source_family=queue.family();pins.update(source_family['source_pins'])
    fields,whole=exclusions(PREPARED.read_text());f,w=exclusions(LZC.read_text());fields|=f;whole|=w
    f,w=exclusions(source_family['el']);fields|=f;whole|=w
    by_scope={}
    for s,n in fields:by_scope.setdefault(s,set()).add(n)
    fields=by_scope
    db=Path(ledger[0])/'snps/coverage/db';paths=[db/'design/verilog.design.xml',db/'shape/tgl.verilog.info.xml',db/'shape/tgl.verilog.shape.xml']
    book=json.loads(frozen.CONFIG.read_bytes());pin(frozen.CONFIG,frozen.CONFIG_SHA)
    for p in paths:pin(p,book['pins'][str(p)])
    design,info,shape=(t.xml(p) for p in paths)
    nodes={i.get('id'):(i,m) for m in design.findall('srcdef') for i in m.findall('srcinst')}
    def path(key):
        i,_=nodes[key];parent=i.get('pid');return (path(parent)+'.' if parent in nodes else '')+i.get('name')
    modules={path(k):m for k,(_,m) in nodes.items()}
    rows=[];held=[]
    for scope,row in union.items():
        module=modules[scope];matches=[d for d in shape.findall('tgldef') if d.get('chksum')==row['checksum'] and
            d.get('name','').split(' (')[0]==module.get('name','').split(' (')[0]]
        if len(matches)!=1:held.append(dict(scope=scope,matching_shapes=len(matches)));continue
        definition=matches[0];offset=0;objects=[];raw_missing=row['width']-bin(int(row['bits'],16)).count('1')
        binary=format(int(row['bits'],16),'0%db'%row['width'])
        for n in definition.find('tglshape'):
            if n.tag=='arrays':continue
            require(n.tag in ('node','vectornode'),'Unknown binary node')
            width=1 if n.tag=='node' else abs(int(n.get('left'))-int(n.get('right')))+1
            zeros=[offset+k for k,b in enumerate(binary[offset:offset+2*width]) if b=='0']
            if zeros and not overlaps(scope,n.get('name'),fields,whole):
                objects.append(dict(kind=n.tag,**n.attrib,logical_bits=width,serialized_offset=offset,
                                    missing_slots=len(zeros),missing_coordinates=zeros))
            offset+=2*width
        require(offset==row['width'],'Complete serialization mapping')
        if objects:rows.append(dict(scope=scope,module=module.get('name'),checksum=row['checksum'],
            module_checksum=module.get('chksum'),raw_missing_slots=raw_missing,
            eligible_missing_slots=sum(n['missing_slots'] for n in objects),
            objects=sorted(objects,key=lambda n:-n['missing_slots']),
            arrays_separately_unbound=[dict(kind=n.tag,**n.attrib) for n in definition.iter('arrays')]))
    pin(Path(__file__).resolve())
    for p,h in pins.items():require(t.digest(p)==h,'Final pin drift')
    return dict(status='STATIC770_OUTSIDE_PREPARED_WAIVER_FIELD_UNION_NOT_FUNCTIONAL_QUALIFICATION',population=770,
        formal_manifest_sha256=pins[str(BASE/'admission-manifest.json')],cache_population=741,actual_suffixes=29,
        scopes=sorted(rows,key=lambda s:-s['eligible_missing_slots']),held_shapes=held,pins=pins,
        prepared_union=[str(PREPARED),str(LZC),'Source-declared queue312 family; no native qualification claimed'],
        subtraction='Conservative: any field with a prepared partial/directional waiver is removed in full; pure observer ancestors also removed. No claim of exact remaining official denominator.',
        coordinate_semantics='Serialized paired coordinates only, not DVE native direction IDs. Arrays omitted from this binary cache and not assigned fabricated coverage.',
        official_percentage=None,EDA_launched=False,RTL_modified=False)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    require(not a.output.exists(),'Fresh static output');r=collect()
    with a.output.open('x') as f:json.dump(r,f,indent=2);f.write('\n')
    print('AUDIT_READY',t.digest(a.output),len(r['scopes']),flush=True)
    for s in r['scopes'][:18]:print(s['eligible_missing_slots'],s['scope'],[(n['name'],n['missing_slots']) for n in s['objects'][:3]])
