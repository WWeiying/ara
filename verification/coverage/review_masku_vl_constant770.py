"""Two internal disabled VL-mask fields; frozen source/shape, no native execution."""
import argparse
import json
from pathlib import Path
import re

import rank_ordinary_rvv_toggle766 as frozen
import targeted_toggle_evidence_v2 as typed
import audit_toggle_stimulus769 as prior
import prove_mask_store_snapshot_zero as lexical

ROOT, OUT, require, digest = frozen.ROOT, frozen.OUT, typed.require, typed.digest
SCOPE = 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.i_masku_operands'
TARGETS = ('deshuffled_vl_bit_mask','shuffled_vl_bit_mask')
ALL = TARGETS + ('bit_enable_mask_o',)
AUDIT = OUT/'toggle-outside-prepared-union770-static-agent-20261007-01.json'
AUDIT_SHA = 'c6dd804cbee8e8d872c6058da0defb8e1c0facd1ca816caf8326e6b12105f036'
BOOK = OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
BOOK_SHA = '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'
REPORT = OUT/'masku-vl-disabled-internal2-source-review770-agent-20261007-01.json'


def block(source, start):
    tokens = list(re.finditer(r'\b(begin|end)\b',source[start:]))
    require(tokens and tokens[0][1]=='begin','Expected actual begin block')
    depth=0
    for token in tokens:
        depth += 1 if token[1]=='begin' else -1
        if depth==0:return source[start:start+token.end()],start+token.end()
    raise ValueError('Unclosed source block')


def source_contract(text, parent, package):
    source=lexical.clean(text);compact=re.sub(r'\s+','',source)
    require(compact.count('localparamintunsignedVlBitMaskEnable=0')==1,'Frozen localparam must disable VL mask')
    require('localparamintunsignedDATAPATH_WIDTH=NrLanes*ELEN;' in compact,'Datapath width derivation')
    require("localparamintunsignedELEN=64;" in re.sub(r'\s+','',lexical.clean(package)),'Frozen ELEN64')
    for name in TARGETS:require('logic[DATAPATH_WIDTH-1:0]'+name+';' in compact,'Internal declaration '+name)
    inventory=lexical.writes(text,ALL)
    expected=[('deshuffled_vl_bit_mask','=',"'0"),('shuffled_vl_bit_mask','=',"'0"),('bit_enable_mask_o','=',"'0"),
        ('deshuffled_vl_bit_mask[i]','=',"1'b1"),
        ('shuffled_vl_bit_mask[8*src_operand_byte_shuffle_index+:8]','=','deshuffled_vl_bit_mask[8*b+:8]'),
        ('bit_enable_mask_o[8*src_operand_byte_shuffle_index+:8]','=','shuffled_vl_bit_mask[8*src_operand_byte_shuffle_index+:8]'),
        ('shuffled_vl_bit_mask','=',"'0"),('bit_enable_mask_o','=',"'0"),
        ('bit_enable_mask_o[8*src_operand_byte_shuffle_index+:8]','&=','masku_operand_m_o[mask_operand_byte_shuffle_lane_index][8*mask_operand_byte_shuffle_lane_offset+:8]')]
    require([(w['lhs'],w['operator'],w['rhs']) for w in inventory]==expected,'Complete whole/partial/compound write inventory')
    regions=[]
    for match in re.finditer(r'\balways_comb\s+begin\b',source):
        b,_=block(source,source.index('begin',match.start()))
        if lexical.writes(b,ALL):regions.append(b)
    require(len(regions)==1 and len(lexical.writes(regions[0],ALL))==9,'One complete combinational driver; no reset/clock/override driver')
    gates=list(re.finditer(r'\bif\s*\(VlBitMaskEnable\)\s+begin\b',regions[0]))
    require(len(gates)==2,'Exactly two disabled writer guards')
    guarded=[]
    for gate in gates:
        b,end=block(regions[0],regions[0].index('begin',gate.start()))
        guarded.append(lexical.writes(b,ALL))
    require([(w['lhs'],w['operator'],w['rhs']) for w in guarded[0]]==expected[3:4] and
            [(w['lhs'],w['operator'],w['rhs']) for w in guarded[1]]==expected[4:6],'All nonzero writers strictly inside disabled guards')
    _,end=block(regions[0],regions[0].index('begin',gates[1].start()))
    tail=regions[0][end:]
    require(re.match(r'\s*else\s+begin\b',tail) is not None,'Disabled else branch retained')
    otherwise,_=block(tail,tail.index('begin'))
    require([(w['lhs'],w['operator'],w['rhs']) for w in lexical.writes(otherwise,ALL)]==expected[6:8],'Disabled path whole-zero assignments')
    p=lexical.clean(parent)
    instance=re.search(r'\bmasku_operands\s*#\((.*?)\)\s*i_masku_operands\s*\((.*?)\);',p,re.S)
    require(instance and re.findall(r'\.(\w+)\s*\(',instance[1])==['NrLanes','pe_req_t','pe_resp_t'] and
            re.search(r'\.NrLanes\s*\(\s*NrLanes\s*\)',instance[1]),'Actual parent binding; no configuration override')
    require(re.findall(r'\.bit_enable_mask_o\s*\(\s*(\w+)\s*\)',instance[2])==['bit_enable_mask'],'Protected output fanout')
    return dict(all_writes=inventory,disabled_guard_writer_lines=[[w['line'] for w in lexical.writes(text,ALL)
        if w['lhs']==x['lhs'] and w['rhs']==x['rhs']] for group in guarded for x in group],
        parameter_proof='VlBitMaskEnable is frozen literal localparam0, not an omitted/default-overridable parameter; compiled tgldef does not directly list it.',
        invariant='Both internal vectors are zero after every settled always_comb evaluation: whole-zero defaults, all nonzero writers under literal-false guards, and shuffled whole-zero else. No storage/reset/override path exists.',
        input_domain='All legal vl/vstart/operation/EEW/VM/mask/data, including abort/error/reset paths; not restricted to current tests. No pre-settle delta/X or forced-value claim.',
        protected_output_proof='bit_enable_mask_o also defaults/else zero; its enabled copies are disabled, and its remaining &= cannot set a zero bit. It remains protected because it is an interface.',
        parent_output_connection='bit_enable_mask_o -> i_masku.bit_enable_mask (kept, not selected)')


def validate_node(node,name):
    require(name in TARGETS and node.tag=='vectornode' and node.get('name')==name and
            node.get('portnode')=='0' and node.get('excluded')=='0' and node.get('type')=='1' and
            (node.get('left'),node.get('right'))==('255','0'),'Only exact internal logic[255:0] candidates')


def collect():
    pins={}
    def pin(p,h=None):
        actual=digest(p);require(h is None or h==actual,'Pin drift '+str(p));pins[str(p)]=actual
        if p.suffix=='.json':return json.loads(p.read_bytes())
        if p.suffix in ('.sv','.el','.py','.txt','.tcl'):return p.read_text()
        return None
    audit=pin(AUDIT,AUDIT_SHA);require(audit['population']==770,'Formal770 audit')
    # Recheck raw evidence and existing EL inputs instead of inferring constants from absence of hits.
    for p,h in audit['pins'].items():pin(Path(p),h)
    book=pin(BOOK,BOOK_SHA);texts={}
    for rel in ('hardware/src/masku/masku_operands.sv','hardware/src/masku/masku.sv','hardware/include/ara_pkg.sv'):
        p=ROOT/rel;texts[rel]=pin(p,book[str(p)])
    proof=source_contract(texts['hardware/src/masku/masku_operands.sv'],texts['hardware/src/masku/masku.sv'],texts['hardware/include/ara_pkg.sv'])
    row=next(s for s in audit['scopes'] if s['scope']==SCOPE)
    db=OUT/'repaired-aligned-build-20260930-01/sim/simv.vdb/snps/coverage/db'
    shape=typed.xml(db/'shape/tgl.verilog.shape.xml');design=typed.xml(db/'design/verilog.design.xml')
    srcpath=db/'auxiliary/verilog.sourceinfo.xml';pin(srcpath);sourceinfo=typed.xml(srcpath)
    file=next(n for n in sourceinfo.iter('fileinfo') if n.get('id')=='558')
    require(file.get('name')==str(ROOT/'hardware/src/masku/masku_operands.sv'),'Actual source file558, not parent instantiation')
    defs=[d for d in shape.findall('tgldef') if d.get('name')=='masku_operands' and d.get('chksum')==row['checksum']]
    require(len(defs)==1,'Unique compiled type/checksum')
    definition=defs[0];params=dict(x.split('=',1) for x in definition.get('param').split(','))
    require(params['NrLanes']=='4' and params['DATAPATH_WIDTH']=='256','Actual compiled geometry')
    nodes={n.get('id'):(n,m) for m in design.findall('srcdef') for n in m.findall('srcinst')}
    def full(key):
        n,_=nodes[key];parent=n.get('pid');return (full(parent)+'.' if parent in nodes else '')+n.get('name')
    hierarchy={full(k):(n,m) for k,(n,m) in nodes.items()}
    require(SCOPE in hierarchy and hierarchy[SCOPE][1].get('name')=='masku_operands' and
            hierarchy[SCOPE][1].get('chksum')==row['module_checksum'],'Exact compiled fullscope/module')
    fields={n.get('name'):n for n in definition.find('tglshape')};missing={n['name']:n for n in row['objects']}
    ef=set();whole=set();prepared=[]
    for name in audit['prepared_union'][:2]:
        path=Path(name);text=pin(path,audit['pins'][str(path)]);f,w=prior.exclusions(text);ef|=f;whole|=w;prepared.append(str(path))
    # Queue312 is disjoint and was already source-bound by the pinned audit.
    require(not any(s==SCOPE or s.startswith(SCOPE+'.') for s,n in ef),'No local prepared Toggle members')
    byscope={}
    for s,n in ef:byscope.setdefault(s,set()).add(n)
    candidates=[];already=[]
    for name in TARGETS:
        node=fields[name];validate_node(node,name)
        require(node.get('file')=='558' and node.get('line_num')==str(71 if name==TARGETS[0] else 72),'Actual declaration-bound node')
        m=missing[name];require(m['logical_bits']==256 and m['missing_slots']==512 and
            m['missing_coordinates']==list(range(m['serialized_offset'],m['serialized_offset']+512)),'Entire exact770 missing pair range')
        item=dict(scope=SCOPE,name=name,kind=node.tag,attributes=dict(node.attrib),checksum=row['checksum'],
            module_checksum=row['module_checksum'],logical_bits=256,source_file=str(ROOT/'hardware/src/masku/masku_operands.sv'),
            source_declaration_line=int(node.get('line_num')),serialized_offset=m['serialized_offset'],
            missing_positions=m['missing_coordinates'],missing_slots=512,
            native_request=dict(type='Toggle',names=[name],width=256,bounds=[255,0],source='logic '+name,
                expected_excluded_before=0,source_constant=0,port_exception_allowed=False,
                identity_binding='PENDING actual native token/name/ranges/type/checksum; typed EL full-vector or exact both-direction members only'))
        (already if prior.overlaps(SCOPE,name,byscope,whole) else candidates).append(item)
    protected=[dict(kind=n.tag,**n.attrib) for n in definition.find('tglshape') if n.get('name') not in {c['name'] for c in candidates}]
    require(fields['bit_enable_mask_o'].get('portnode')=='3' and any(n['name']=='bit_enable_mask_o' for n in protected),'Output interface must remain protected')
    children=[]
    for scope,(node,module) in hierarchy.items():
        if scope.startswith(SCOPE+'.'):
            children.append(dict(scope=scope,module=module.get('name'),module_checksum=module.get('chksum'),all_fields_protected=True))
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_review_masku_vl_constant770.py'),
              Path(prior.__file__),Path(lexical.__file__),Path(typed.__file__)):pin(p)
    for p,h in pins.items():require(digest(Path(p))==h,'Final pin drift')
    return dict(status='FROZEN770_INTERNAL_ZERO2_SOURCE_PROVEN_NATIVE_PENDING',population=770,
        formal_seal=audit['formal_manifest_sha256'],source_proof=proof,compiled_scope=SCOPE,
        compiled_parameters=params,compiled_VlBitMaskEnable_direct_metadata_present=False,
        sourceinfo_file558=dict(file.attrib),candidates=candidates,already_prepared=already,
        gross_three_object_missing_positions=1536,protected_output_missing_positions=512,
        prepared_internal_missing_positions=sum(i['missing_slots'] for i in already),
        net_candidate_missing_positions=sum(i['missing_slots'] for i in candidates),
        candidate_logical_bits=sum(i['logical_bits'] for i in candidates),
        local_inventory_count=len(fields),local_protected_count=len(protected),local_protected=protected,
        protected_children=children,prepared_EL_inputs=prepared,
        protected_scope_policy='Only exact two internal fields. Every other local scalar/vector/array, all child scopes, parent aliases, ports, data/control/reset/flags/handshake and non-Toggle metrics preserved.',
        native_acceptance_required='Actual exact target identities and full local/child inventories; five initial/apply/reset/reload/final native saves and authoritative typed EL members; all non-target excluded flags unchanged and zero new complement exclusions. No current native qualification claim.',
        positions_are_serialized_not_DVE_denominator=True,official_percentage=None,
        EDA_launched=False,RTL_modified=False,waivers_applied=False,pins=pins)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--verify',action='store_true');a=p.parse_args()
    result=collect()
    if a.verify:require(json.loads(REPORT.read_bytes())==result,'Independent static replay differs')
    else:
        require(not REPORT.exists(),'Fresh independent review only')
        with REPORT.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(dict(output=str(REPORT),seal=digest(REPORT),candidates=len(result['candidates']),
                         net_missing_positions=result['net_candidate_missing_positions'],pins=len(result['pins']))))
