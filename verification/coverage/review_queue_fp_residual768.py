"""Frozen-source whole-field candidates; exact768 zeros and existing766 EL difference."""
import argparse
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import queue_fp_temporaries_static as old
import rank_ordinary_rvv_toggle766 as rank
import targeted_toggle_evidence_v2 as tgl
import prove_mask_store_snapshot_zero as lexical

ROOT,OUT,require,digest=old.ROOT,old.OUT,tgl.require,tgl.digest
BASE=OUT/'stride-metadata-full64-offline-admitted-768-agent-20261007-01'
BASE_SHA='1add5889916fd9cfe2bb6e95368a2a86d43f1d0ac27ac4cf89786639cb6f4198'
RANK=OUT/'ordinary-rvv-toggle-ranking766-agent-20261007-01.json'
RANK_SHA='861293d0d6adb01bdcec1acee8366ff087120d67fca6e7cb9466eeca69713853'
BUILD_SHA='6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'
KINDS=('alu_a','alu_b','mfpu_a','mfpu_b','mfpu_c','st_mask_a','slide_addrgen_a','mask_b','mask_m')
FP8={'fp8[%d].%s'%(i,f) for i in range(4) for f in ('s','e','m')}


def source_contract(queue,stage):
    old.source_contract(queue)
    clean=lexical.clean(queue);compact=re.sub(r'\s+','',clean)
    require('fp8_tfp8[4];fp16_tfp16[2];fp32_tfp32;' in compact,'Global declarations differ')
    require(compact.count('automaticfp8_tfp8=ibuf_operand[8*select+16*e+:8];')==1,
            'Distinct EW8 lexical local shadow declaration')
    # Whole/partial global-array writers: include += and nonblocking assignments.
    assignments=re.findall(r'\b(fp8|fp16|fp32)\s*((?:(?:\[[^]]+\]|\.[a-zA-Z_]\w*)\s*)*)\s*(<=|\+=|-=|=)\s*([^;]+);',clean)
    assignments=[(n,re.sub(r'\s+','',indices),op,rhs.strip()) for n,indices,op,rhs in assignments]
    expected=[('fp8','[i]','=','\'0'),('fp16','[i]','=','\'0'),('fp32','','=','\'0'),
              ('fp8','','=','ibuf_operand[8*select + 16*e +: 8]'),
              ('fp16','.s','=','fp8.s'),('fp16','.e','=','(fp8.e - 7) + 15'),
              ('fp16','.m','=','{fp8.m, 7\'b0}'),
              ('fp16','[e]','=','ibuf_operand[8*select + 32*e +: 16]'),
              ('fp32','','=','ibuf_operand[8*select +: 32]')]
    require(assignments==expected,'Complete FP assignment inventory differs')
    local=compact.split('automaticfp8_tfp8=',1)[1].split('{EW16,',1)[0]
    require('automaticfp16_tfp16;' in local and 'conv_operand[16*e+:16]=fp16;' in local,
            'Local shadow namespace and consumption differ')
    blocks={m.group(2):m.group(1) for m in re.finditer(r'operand_queue\s*#\((.*?)\)\s+(i_operand_queue_\w+)\s*\(',lexical.clean(stage),re.S)}
    require(set(blocks)=={'i_operand_queue_'+k for k in KINDS},'Exactly nine producers')
    for kind in KINDS:
        value='FPUSupport' if kind.startswith('mfpu') else 'FPUSupportNone'
        matches=re.findall(r'\.FPUSupport\s*\(\s*(\w+)\s*\)',blocks['i_operand_queue_'+kind])
        require(matches==[value],'Explicit instance FPU parameter: '+kind)
    # State-free induction: defaults execute on every settled always_comb
    # evaluation, then only a permitted nonzero writer can alter that field.
    table=[]
    for support in (0,56):
        for eew in range(4):
            for wide in (False,True):
                table.append(dict(support=support,eew=eew,wide_conversion=wide,
                    global_fp8_nonzero_writer=False,
                    global_fp16_nonzero_writer=bool(support and wide and eew==1),
                    global_fp32_nonzero_writer=bool(support and wide and eew==2)))
    return dict(assignment_inventory=assignments,parameter_bindings={k:0 if not k.startswith('mfpu') else 56 for k in KINDS},
                abstract_writer_table=table,proof_scope='Valid reset, settled evaluation, known legal control/config; no X/delta claim',
                fp8_shadow_is_not_global=True,arbitrary_data_allowed=True)


def covered_fields(text,scopes):
    result=set();scope=None
    for line in text.splitlines():
        line=line.strip()
        if line.startswith('INSTANCE:'):scope=line.split(':',1)[1].strip()
        if scope not in scopes or not line.startswith('Toggle '):continue
        m=re.fullmatch(r'Toggle (?:(0to1|1to0) )?(\S+)(?: \[-?\d+(?::-?\d+)?\])? "logic ([^"]+)"',line)
        require(m is not None,'Unsupported queue EL syntax')
        # Any existing partial exclusion blocks the whole-field candidate.
        for name in old.fields():
            if m[2]==name or m[2].startswith(name+'['):result.add((scope,name))
    return result


def candidate_names(kind):
    return old.fields() if not kind.startswith('mfpu') else FP8


def typed_width(name,node):
    fmt=int(re.search(r'fp(8|16|32)',name)[1]);field=name.rsplit('.',1)[1]
    width={'s':1,'e':{8:5,16:5,32:8}[fmt],'m':{8:2,16:10,32:23}[fmt]}[field]
    require(node.get('name')==name and node.get('portnode')=='0' and node.get('excluded')=='0','Exact internal unexcluded field')
    require(node.tag==('node' if field=='s' else 'vectornode'),'Exact compiled field kind')
    if field!='s':require(node.get('left')==str(width-1) and node.get('right')=='0','Exact ordered field width')
    return width


def collect():
    pins={}
    def bound(p,h):
        require(digest(p)==h,'Input drift: '+str(p));pins[str(p)]=h
        return json.loads(p.read_bytes()) if p.suffix=='.json' else p.read_text()
    baseline=bound(BASE/'admission-manifest.json',BASE_SHA)
    ranking=bound(RANK,RANK_SHA)
    config=bound(rank.CONFIG,rank.CONFIG_SHA)
    book=bound(old.BUILD,BUILD_SHA);texts={}
    for rel in ('hardware/src/lane/operand_queue.sv','hardware/src/lane/operand_queues_stage.sv','hardware/include/ara_pkg.sv'):
        p=ROOT/rel;texts[rel]=bound(p,book[str(p)])
    proof=source_contract(texts['hardware/src/lane/operand_queue.sv'],texts['hardware/src/lane/operand_queues_stage.sv'])
    require("FPUSupportHalfSingleDouble = 6'b111000" in texts['hardware/include/ara_pkg.sv'],'Frozen format mask')
    ledger=bound(BASE/'combined-inputs.txt',baseline['output_pins'][str(BASE/'combined-inputs.txt')]).splitlines()
    require(len(ledger)==len(set(ledger))==769 and ledger[:767]==config['input_ledger'],'Exact766 prefix plus two members')
    scopes=[s for s in ranking['scopes'] if s['scope'].split('.')[-1] in {'i_operand_queue_'+k for k in KINDS}]
    require(len(scopes)==36,'Nine queues in four lanes')
    names=[s['scope'] for s in scopes]
    elpath=rank.CONFIG.parent/'combined.el'
    el=bound(elpath,config['pins'][str(elpath)])
    excluded=covered_fields(el,names)
    db=Path(ledger[0])/'snps/coverage/db'
    shape_path=db/'shape/tgl.verilog.shape.xml'
    require(digest(shape_path)==config['pins'][str(shape_path)],'Compiled shape drift')
    pins[str(shape_path)]=digest(shape_path);shape=tgl.xml(shape_path)
    suffix=None
    for member in ledger[767:]:
        paths=list((Path(member)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(paths)==1,'One admitted test per suffix');p=paths[0]
        sample,h=tgl.rows(p,names)
        require(h==baseline['input_pins'][str(p)],'Suffix pin differs');pins[str(p)]=h
        suffix=sample if suffix is None else tgl.union(suffix,sample)
    candidates=[];already=[];protected=[]
    for row in scopes:
        scope=row['scope'];kind=scope.split('i_operand_queue_')[-1]
        defs=[d for d in shape.findall('tgldef') if d.get('chksum')==row['checksum'] and d.get('name','').split(' (')[0]=='operand_queue']
        require(len(defs)==1,'Unique checksum/type shape');definition=defs[0]
        require((suffix[scope]['width'],suffix[scope]['checksum'])==(row['serialized_width'],row['checksum']),'Suffix compatibility')
        fields={n.get('name'):n for n in definition.find('tglshape') if n.tag in ('node','vectornode')}
        missing={n['name']:n for n in row['objects']}
        for name in sorted(candidate_names(kind)):
            require(name in fields,'Complete typed global field');node=fields[name]
            width=typed_width(name,node)
            item=dict(scope=scope,name=name,kind=node.tag,definition=dict(node.attrib),logical_bits=width,
                      checksum=row['checksum'],compiled_parameter_family=definition.get('name'))
            if (scope,name) in excluded:already.append(item);continue
            require(name in missing and missing[name]['missing_slots']==2*width,'Entire field constant candidate must be zero in766')
            coords=missing[name]['missing_coordinates']
            require(len(coords)==2*width and all(not (int(suffix[scope]['bits'],16) >> (row['serialized_width']-1-p))&1 for p in coords),
                    'Candidate unexpectedly hit by767/768')
            item.update(serialized_coordinates=coords,missing_slots=2*width,
                source_reason='FPU0 gates all nonzero global writers' if not kind.startswith('mfpu') else 'Global fp8 only default-zero writer; EW8 local shadow is a distinct variable',
                native_identity_status='HOLD_MERGED_0_56_SPECIALIZATION_BIND_FULL_COMPLEMENT' if kind.startswith('alu') else 'NATIVE_PENDING_GLOBAL_FIELD_VS_LOCAL_SHADOW')
            candidates.append(item)
        protected.append(dict(scope=scope,objects=[dict(kind=n.tag,**n.attrib) for n in definition.find('tglshape')
                if n.get('name') not in {i['name'] for i in candidates if i['scope']==scope}]))
    require(len(candidates)==312 and sum(i['logical_bits'] for i in candidates)==1152,'Expected residual capacity')
    require(len(already)==336,'Previously qualified16x21 temporaries retained, not duplicated')
    pins[str(Path(__file__).resolve())]=digest(__file__)
    pins[str(Path(__file__).with_name('test_review_queue_fp_residual768.py'))]=digest(Path(__file__).with_name('test_review_queue_fp_residual768.py'))
    for p,h in pins.items():require(digest(p)==h,'Final pin drift')
    return dict(status='SOURCE_CONSTANT_RESIDUAL_CANDIDATES_NATIVE_HOLD',formal_population=768,formal_seal=BASE_SHA,
        source_proof=proof,candidates=candidates,objects=312,logical_bits=1152,serialized_missing_slots=2304,
        groups=[dict(kind='ALU FPU0',scopes=8,objects=168,logical_bits=768,missing_slots=1536),
                dict(kind='MFPU global fp8',scopes=12,objects=144,logical_bits=384,missing_slots=768)],
        already_excluded=already,existing_EL_population=766,existing_EL_scope='Pinned actual full766 combined.el; no separate full768 native application claimed',
        protected_by_scope=protected,protected_categories=['valid FP16/32 temporaries in MFPU','rounding/flags/control/interfaces',
                'conv_operand/neutral/mask/tail data','LZC undriven/X values','all other objects/metrics/scopes'],
        native_next='Exact full objects only; disambiguate merged compiled specialization and global/local namespaces through actual native names/meta; all typed complement and five-stage excluded flags required',
        official_percentage=None,EDA_launched=False,waivers_generated=False,exclusions_applied=False,pins=pins)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    require(not a.output.exists(),'Fresh report only');value=collect()
    with a.output.open('x') as f:json.dump(value,f,indent=2);f.write('\n')
    print('STATIC_RESIDUAL_READY',digest(a.output),value['objects'],value['serialized_missing_slots'])
