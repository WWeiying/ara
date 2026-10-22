"""Source-bound partial-object candidate only: nine read payloads, never a native waiver."""
import argparse
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import run_stride_metadata767 as shared

life,require,ROOT,OUT=shared.life,shared.require,shared.ROOT,shared.OUT
REQUESTER=ROOT/'hardware/src/lane/operand_requester.sv'
PACKAGE=ROOT/'hardware/include/ara_pkg.sv'
BOOK=OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
RANK=OUT/'ordinary-rvv-toggle-ranking766-agent-20261007-01.json'
RANK_SHA='861293d0d6adb01bdcec1acee8366ff087120d67fca6e7cb9466eeca69713853'
QUEUES=['AluA','AluB','MulFPUA','MulFPUB','MulFPUC','MaskB','MaskM','StA','SlideAddrGenA']
VFUS=['VFU_Alu','VFU_MFpu','VFU_SlideUnit','VFU_MaskUnit','VFU_LoadUnit','VFU_StoreUnit','VFU_None']


def source_contract(source,package):
    # Exact writer inventory, not a keyword-only check or a general SV theorem prover.
    clean=re.sub(r'/\*.*?\*/|//[^\n]*','',source,flags=re.S)
    pclean=re.sub(r'/\*.*?\*/|//[^\n]*','',package,flags=re.S)
    require(re.search(r'NrOperandQueues\s*=\s*9\s*;',pclean),'Nine read ports')
    for typedef,names in (('opqueue_e',QUEUES),('vfu_e',VFUS)):
        m=re.search(r'typedef\s+enum\s+logic\s*\[[^\n]+\]\s*\{([^}]+)\}\s*'+typedef,pclean)
        require(m and [x.strip() for x in m[1].split(',')]==names,'Exact enum order: '+typedef)
    require('localparam NrGlobalMasters = 5;' in clean and 'localparam NrMasters = NrOperandQueues + NrGlobalMasters;' in clean,'Writer bounds')
    require(re.search(r'for\s*\(genvar requester_index = 0; requester_index < NrOperandQueues; requester_index\+\+\)',clean),'Read generate range')
    writers=re.findall(r'\b(operand_payload\s*(?:\[[^;\n]+?\])?(?:\.[A-Za-z_]\w*)?)\s*(?:<=|=(?!=))\s*([^;]*);',clean)
    expected=['operand_payload[requester_index]']*2+['operand_payload[NrOperandQueues + '+v+']' for v in
                 ('VFU_Alu','VFU_MFpu','VFU_MaskUnit','VFU_SlideUnit','VFU_LoadUnit')]
    require([x.strip() for x,_ in writers]==expected,'Unexpected payload writer/partial override')
    require(writers[0][1].strip()=="'0",'Read idle/default must be full zero')
    fields=re.findall(r'(\w+)\s*:\s*([^,}]+)',writers[1][1])
    require([(a,b.strip()) for a,b in fields]==[
        ('addr',"requester_metadata_q[requester_index].addr >> $clog2(NrBanks)"),
        ('opqueue',"opqueue_e'(requester_index)"),('default',"'0")],'Read packet fields/default changed')
    require(writers[1][1].strip().startswith("'{") and writers[1][1].strip().endswith('}'),'Complete assignment pattern')
    require(clean.count('.data_i ({operand_payload[')==2 and '.data_o (operand_payload' not in clean,
            'Arbiters consume payload; no extra output writer')
    for _,rhs in writers[2:]:
        require(re.search(r"wen\s*:\s*1'b1",rhs),'Global write semantics changed')
    return dict(read_writer_count=2,global_writer_count=5,read_indices=list(range(9)),write_indices=list(range(9,14)),
        writers=[dict(lhs=lhs.strip(),rhs=rhs.strip()) for lhs,rhs in writers],
        queue_names=QUEUES,proof='Every generated read slot is assigned whole zero on every combinational evaluation; '
        'the only subsequent read-slot assignment sets addr/opqueue with all other fields zero. '
        'Five full write packets have disjoint indices9..13; no partial or additional payload writer exists.',
        reset_boundary='Valid reset and settled combinational evaluation; not an X/delta/initialization exclusion claim')


def compiled(scope,record,shape):
    matches=[d for d in shape.findall('tgldef') if d.get('chksum')==record['checksum'] and
             d.get('name','').split(' (')[0]==record['module'].split(' (')[0]]
    require(len(matches)==1,'Exact family/checksum typed definition')
    root=matches[0];targets=[];protected=[];offset=0
    for node in root.find('tglshape'):
        if node.tag=='arrays':
            protected.append(dict(kind='arrays',definition=ET.tostring(node,encoding='unicode')));continue
        require(node.tag in ('node','vectornode'),'Unknown typed definition')
        width=1 if node.tag=='node' else abs(int(node.get('left'))-int(node.get('right')))+1
        obj=dict(kind=node.tag,**node.attrib,logical_bits=width,serialized_offset=offset)
        m=re.fullmatch(r'operand_payload\[([0-8])\]\.(wdata|be|wen)',node.get('name',''))
        if m:
            field=m[2];expected={'wdata':64,'be':8,'wen':1}[field]
            require(width==expected and node.get('portnode')=='0' and node.get('excluded')=='0','Exact internal target shape')
            if field!='wen':require((node.get('left'),node.get('right'))==(str(expected-1),'0'),'Exact vector bounds')
            obj.update(scope=scope,checksum=record['checksum'],queue=int(m[1]),field=field)
            targets.append(obj)
        else:protected.append(obj)
        offset+=2*width
    require(offset==record['serialized_width'] and len(targets)==27 and
            {(t['queue'],t['field']) for t in targets}=={(q,f) for q in range(9) for f in ('wdata','be','wen')},'Complete27, not only unhit selection')
    return targets,protected


def review(out):
    require(out.parent==OUT and not out.exists(),'Fresh static report only')
    rank=life.read_bound(RANK,RANK_SHA);book=json.loads(BOOK.read_bytes())
    for p in (REQUESTER,PACKAGE):require(life.digest(p)==book[str(p)],'Frozen build source mismatch')
    proof=source_contract(REQUESTER.read_text(),PACKAGE.read_text())
    ledger,evidence=shared.baseline()
    db=Path(ledger[0])/'snps/coverage/db';shape_path=db/'shape/tgl.verilog.shape.xml'
    require(life.digest(shape_path)==rank['pins'][str(shape_path)],'Compiled shape SHA drift')
    shape=shared.toggle.xml(shape_path)
    rows=[r for r in rank['scopes'] if r['scope'].endswith('.i_operand_requester')]
    scopes={f'ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[{i}].i_lane.i_operand_requester' for i in range(4)}
    require(len(rows)==4 and {r['scope'] for r in rows}==scopes,'Exact four lanes')
    targets=[];protections={}
    for r in rows:
        t,p=compiled(r['scope'],r,shape);targets+=t;protections[r['scope']]=p
    cachepath=OUT/'toggle741-capacity-ranking-agent-20261007-01.json'
    cache=life.read_bound(cachepath,'8c9fe15bec6ae5dcd2e5e9dee9c461047db4109464d2c568e3ca5ec9b0bf0865')
    old=next(Path(p) for p in cache['input_pins'] if p.endswith('/inputs.txt'))
    require(life.digest(old)==cache['input_pins'][str(old)] and old.read_text().splitlines()==ledger[:742],'Exact cache prefix')
    merged={s:cache['instances'][s] for s in scopes}
    pins={str(p):life.digest(p) for p in (RANK,BOOK,REQUESTER,PACKAGE,shape_path,shared.BASE/'admission-manifest.json',
          shared.BASE/'combined-inputs.txt',cachepath,old,Path(__file__),Path(__file__).with_name('test_review_requester_read_payload767.py'),Path(shared.__file__))}
    for name in ledger[742:]:
        files=list((Path(name)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'));require(len(files)==1,'Suffix identity')
        sample,sha=shared.toggle.rows(files[0],scopes);require(evidence.get(str(files[0]))==sha,'767 raw Toggle pin')
        pins[str(files[0])]=sha;merged=shared.toggle.union(merged,sample)
    for t in targets:
        row=merged[t['scope']];require(row['checksum']==t['checksum'],'Actual checksum binding')
        coords=list(range(t['serialized_offset'],t['serialized_offset']+2*t['logical_bits']))
        t['raw767_missing_coordinates']=[i for i in coords if not int(row['bits'],16)&(1<<(row['width']-1-i))]
        require(len(t['raw767_missing_coordinates'])==len(coords),'A proven constant target was hit: review needed')
    life.check(pins)
    result=dict(status='SOURCE_BOUND_PARTIAL_OBJECT_CANDIDATE_NATIVE_HOLD',baseline=767,pins=pins,source_proof=proof,
        targets=targets,protected_by_scope=protections,scope_binary_rows=merged,exact_objects=108,objects_per_lane=27,
        wdata_be_objects=72,wdata_be_bits=2592,wdata_be_missing_serialized_slots=5184,
        separately_proven_read_wen_objects=36,read_wen_bits=36,read_wen_missing_serialized_slots=72,
        all_target_bits=2628,all_missing_serialized_slots=5256,
        protected='All write packets9..13, read addr/opqueue, returned VRF data, snapshots, handshake/hazards, '
                  'all other scalar/vector/array definitions, every Line/Branch/Condition/FSM and other scopes',
        native_requirements='Exact partial typed names/checksums/dimensions and complement; no whole requester/payload exclusion. '
                            'Native selection/save/reload/reset and every excluded-status complement still required.',
        direction_names_not_inferred_from_serialization=True,official_percentage=False,EDA_launched=False,
        exclusions_applied=False,native_qualified=False,sourceconstant_not_IEEE_trust=True)
    life.save(out,result);print(json.dumps(dict(report=str(out),seal=life.digest(out),objects=108,native='HOLD')))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();review(a.output.resolve())
