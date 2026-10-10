"""Compiled serializer binding for success-only AKV canonical alias metadata."""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import targeted_toggle_evidence_v2 as shape
import rank_cva6_scalar_data767 as typed
import run_scalar_slot_rotation792 as shared

life,require=shared.life,shared.require
BASE=life.OUT/'itlb-ppn-aba-offline-admitted794-parent-20261008-01'
BASE_SHA='02ee7424a6b21d8073097d8a6389be4393d76fc7a3ab31ce410f1c24f70de8cf'
SCOPE='ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_akv_engine'
FIELDS={SCOPE:['context_q_base_q','context_k_base_q','context_v_base_q','q_read_address_q','k_read_address_q','v_read_address_q','mmu_vaddr_o'],
 SCOPE+'.i_read_engine':['range_fifo_q[0].vaddr','range_fifo_q[1].vaddr','burst_fifo_q[0].cursor_vaddr','burst_fifo_q[1].cursor_vaddr','ar_cursor_vaddr_q','mmu_vaddr_o']}
ALIASES=[[0x2555555000+4096*i for i in range(3)],[(~(0x2555555000+4096*i))&((1<<64)-4096) for i in range(3)]]


def canonical(v):
    return 0<=v<1<<64 and v>>39==((1<<25)-1 if v>>38&1 else 0)


def definitions(design,info,definitions,scopes):
    nodes={n.get('id'):(n,m) for m in design.findall('srcdef') for n in m.findall('srcinst')}
    require(len(nodes)==sum(len(m.findall('srcinst')) for m in design.findall('srcdef')),'Unique compiled instance IDs')
    def path(k,seen=()):
        require(k not in seen,'Hierarchy cycle'); n,m=nodes[k]; parent=n.get('pid')
        return (path(parent,seen+(k,))+'.' if parent in nodes else '')+n.get('name')
    result={}
    for scope in scopes:
        instances=[(k,m) for k,(n,m) in nodes.items() if path(k)==scope]
        checksum=[n.get('chksum') for n in info.iter('instance_data') if n.get('name')==scope]
        require(len(instances)==len(checksum)==1,'Unique exact compiled scope/checksum')
        key,module=instances[0]; matches=[]
        for d in definitions.findall('tgldef'):
            if d.get('chksum')!=checksum[0]: continue
            native=list(d.iter('tglinst'))
            if d.get('name')==module.get('name'):
                require(not native or any(n.get('name')==scope and n.get('id')==key for n in native),'Explicit instance conflict')
                matches.append(d)
            elif d.get('id')==module.get('id') and d.get('name','').startswith(module.get('name')+' ( parameter '):
                require(sum(n.get('name')==scope and n.get('id')==key for n in native)==1,'Parameterized name requires exact explicit instance identity')
                matches.append(d)
        require(len(matches)==1,'Unique compiled module/checksum/explicit instance shape')
        result[scope]=dict(checksum=checksum[0],shape=ET.tostring(matches[0],encoding='unicode'),
            module=dict(module.attrib),instance_id=key,
            binding='Compiled serializer identity only; never a native GUI selector')
    return result


def review():
    m=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    require(m['coverage_admitted'] is True,'Admitted794 authority')
    paths=[BASE/'combined-inputs.txt',BASE/'combined-toggle-bits.json',BASE/'status.json']
    pins={str(BASE/'admission-manifest.json'):BASE_SHA}
    for p in paths: pins[str(p)]=m['output_pins'][str(p)]
    life.check(pins)
    ledger=paths[0].read_text().splitlines(); require(len(ledger)==len(set(ledger))==795,'Exact794 population')
    require(json.loads(paths[2].read_bytes())['aggregate_passed']==794,'Formal794 status')
    rows=json.loads(paths[1].read_bytes()); db=Path(ledger[0])/'snps/coverage/db'
    files=[db/n for n in ('design/verilog.design.xml','shape/tgl.verilog.info.xml','shape/tgl.verilog.shape.xml')]
    for p in files: pins[str(p)]=m['input_pins'][str(p)]
    life.check(pins); defs=definitions(*(shape.xml(p) for p in files),list(FIELDS))
    bookpath=life.OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
    require(life.digest(bookpath)=='6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b','Frozen sourcebook')
    book=json.loads(bookpath.read_bytes()); pins[str(bookpath)]=life.digest(bookpath)
    for rel in ('hardware/src/vlsu/akv/akv_engine.sv','hardware/src/vlsu/qbs/qbs_read_engine.sv','hardware/src/vlsu/vlsu.sv','hardware/include/akv_pkg.sv'):
        p=life.ROOT/rel; pins[str(p)]=book[str(p)]
    fields=[]
    for scope,names in FIELDS.items():
        require(defs[scope]['checksum']==rows[scope]['checksum'],'Compiled/raw checksum')
        nodes,arrays=typed.typed_nodes(defs[scope]['shape'],rows[scope])
        for name in names:
            found=[n for n in nodes if n['name']==name]
            require(len(found)==1 and found[0]['logical_width']==64 and found[0]['left']=='63' and found[0]['right']=='0','Exact full64 non-array field')
            n=found[0]; start=n['serialized_offset']; changed=ALIASES[0][0]^ALIASES[1][0]
            coordinates=[p for p in n['missing_coordinates'] if changed>>(63-(p-start)//2)&1]
            fields.append(dict(scope=scope,name=name,checksum=rows[scope]['checksum'],width=64,offset=start,
                full_coordinates=list(range(start,start+128)),missing=n['missing_coordinates'],alias_changed_missing=coordinates))
    life.check(pins)
    return dict(status='COMPILED_COORDINATES_BOUND_SUCCESS_ALIAS_CASE_NOT_RUN',baseline=794,baseline_seal=BASE_SHA,input_pins=pins,
        fields=fields,aliases=ALIASES,total_capacity=13*128,remaining=sum(len(f['missing']) for f in fields),
        alias_changed_missing_upper_bound=sum(len(f['alias_changed_missing']) for f in fields),
        both_FIFO_slots_require_actual_accepted_capture=True,GUI_direction_pair_order_not_assumed=True,
        physical_AR_address_high_bits_NOT_targets=True,EDA_launched=False,coverage_admitted=False,
        not_official_percentage=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--output',required=True,type=Path); a=p.parse_args()
    result=review(); result['input_pins'][str(Path(__file__).resolve())]=life.digest(Path(__file__))
    life.save(a.output.absolute(),result); print(json.dumps(dict(output=str(a.output),remaining=result['remaining'],
        alias_changed_missing_upper_bound=result['alias_changed_missing_upper_bound'],seal=life.digest(a.output))))
