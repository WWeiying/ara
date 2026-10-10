"""Remaining770 ranking and exact internal format-result constants; no EDA."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re

import review_masku_vl_constant770 as pins_api
import review_qbs_accum_config_constants767 as lemma
import prove_mask_store_snapshot_zero as lexical
import audit_toggle_stimulus769 as audit_api

ROOT, OUT, require, digest = pins_api.ROOT, pins_api.OUT, pins_api.require, pins_api.digest
REPORT = OUT/'mfpu-disabled-format-results176-source-review770-agent-20261007-01.json'
PADDING = OUT/'vlsu-address-padding51-static770-agent-20261007-01.json'
PARENT = 'ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[%d].i_lane.i_vfus.i_vmfpu.fpu_gen.i_fpnew_bulk'
MAX = (1<<64)-1


def active_formats(group):
    require(group in range(5),'Exact five operation groups')
    return {0,1,2} if group in (0,2) else {0} if group in (1,3) else set()


def source_contract(texts):
    clean={n:lexical.clean(t) for n,t in texts.items()}
    v=clean['vmfpu.sv'];pkg=clean['fpnew_pkg.sv'];top=clean['fpnew_top.sv'];block=clean['fpnew_opgroup_block.sv'];arb=clean['rr_arb_tree.sv']
    units=v.split('localparam fpu_implementation_t FPUImplementation',1)[1].split('PipeConfig:',1)[0].split('UnitTypes:',1)[1]
    require(re.findall(r'default:\s*(\w+)',units)==['PARALLEL','MERGED','PARALLEL','MERGED','DISABLED'],'Exact vector operation-unit binding')
    require('.Implementation(FPUImplementation)' in re.sub(r'\s+','',v),'Actual vector instance implementation forwarding')
    require(re.search(r'localparam\s+logic\s+DONT_CARE\s*=\s*1\x27b1\s*;',pkg),'Literal one, not unknown DontCare')
    require('typedeflogic[0:NUM_FP_FORMATS-1]fmt_logic_t;' in re.sub(r'\s+','',pkg),'Ascending FP format mask orientation')
    require(re.search(r'ADDMUL\s*,\s*DIVSQRT\s*,\s*NONCOMP\s*,\s*CONV\s*,\s*DOTP',pkg),'Exact opgroup enumeration')
    for item in ('.FmtUnitTypes  ( Implementation.UnitTypes[opgrp] )', '.FpFmtMask     ( Features.FpFmtMask',
                 '.OpGroup       ( fpnew_pkg::opgroup_e\x27(opgrp)'):
        require(item in top,'Actual per-opgroup forwarding')
    writes=lexical.writes(block,('fmt_outputs','arbiter_output'))
    result_writes=[w for w in writes if w['lhs']=='fmt_outputs[fmt].result']
    require(len(result_writes)==2 and all(w['operator']=='=' and w['rhs']=="'{default:fpnew_pkg::DONT_CARE}" for w in result_writes),'Exact two literal drivers')
    require(re.findall(r'\.result_o\s*\(\s*(fmt_outputs\[[^]]+\]\.result)\s*\)',block)==
            ['fmt_outputs[fmt].result','fmt_outputs[FMT].result'],'Exactly two dynamic result producer connections')
    for item in ('if (FpFmtMask[fmt] && (FmtUnitTypes[fmt] == fpnew_pkg::PARALLEL))',
                 'end else if (FpFmtMask[fmt] && ANY_MERGED && !IS_FIRST_MERGED)',
                 'end else if (!FpFmtMask[fmt] || (FmtUnitTypes[fmt] == fpnew_pkg::DISABLED))',
                 "assign fmt_out_valid[fmt] = 1'b0;", '.req_i  ( fmt_out_valid', '.data_i ( fmt_outputs',
                 '.data_o ( arbiter_output'):
        require(item in block,'Complete disabled/merged-unused result driving cone')
    for item in ('assign req_d = req_i;',
                 'assign sel =  ~req_d[l*2] | req_d[l*2+1] & rr_q[NumLevels-1-level];',
                 'assign data_nodes[Idx0]  = (sel) ? data_i[l*2+1] : data_i[l*2];',
                 "assign data_nodes[Idx0]  = DataType'('0);",
                 'assign sel =  ~req_nodes[Idx1] | req_nodes[Idx1+1] & rr_q[NumLevels-1-level];',
                 'assign data_nodes[Idx0]  = (sel) ? data_nodes[Idx1+1] : data_nodes[Idx1];'):
        require(item in arb,'Exact combinational arbiter propagation lemma')
    return dict(result_literal_writes=result_writes,
        units=['PARALLEL','MERGED','PARALLEL','MERGED','DISABLED'],
        enabled_formats=[0,1,2],format_names=['FP32','FP64','FP16'],
        active_result_producers={str(g):sorted(active_formats(g)) for g in range(5)},
        reasoning='PARALLEL exposes enabled formats0/1/2; MERGED exposes first enabled format0 only, other slots are literal-one placeholders; DOTP disabled exposes none. Disabled/unused valid bits are zero independently of data, operation, rounding, flush, or backpressure.',
        arbiter_reasoning='Reused pinned symbolic tree exhausts all permitted request masks and all8 encoded priorities, including idle. Active results are independent ANY_RESULT symbols, never sampled constants. Out-of-range leaves are zero, not DontCare one.',
        library_storage_preserved='No rr_q/rr_d/req/sel/index/gnt or pipeline/memory state is selected; only combinational .result copies.')


def rule(scope,name):
    m=re.fullmatch(re.escape(PARENT).replace('%d',r'(\d+)')+r'\.gen_operation_groups\[(\d+)\]\.i_opgroup_block(\.i_arbiter)?',scope)
    if not m:return None
    lane,g=int(m[1]),int(m[2]);require(lane in range(4) and g in range(5),'Only four vector lanes/five groups')
    active=active_formats(g)
    if m[3]:
        n=re.fullmatch(r'gen_arbiter\.data_nodes\[(\d+)\]\.result',name)
        constants=lemma.constant_nodes(6,active,MAX)
        if n and int(n[1]) in constants:return constants[int(n[1])],'SYMBOLIC_COMBINATIONAL_FORMAT_TREE',lane,g
    else:
        n=re.fullmatch(r'fmt_outputs\[(\d+)\]\.result',name)
        if n and int(n[1]) in set(range(6))-active:return MAX,'DISABLED_OR_MERGED_UNUSED_LITERAL_ONE',lane,g
        if not active and name=='arbiter_output.result':return 0,'DISABLED_DOTP_PADDED_ARBITER_ROOT_ZERO',lane,g
    return None


def collect():
    pins={}
    def pin(path,expected=None):
        h=digest(path);require(expected is None or h==expected,'Pinned input drift '+str(path));pins[str(path)]=h
    pin(pins_api.AUDIT,pins_api.AUDIT_SHA);audit=json.loads(pins_api.AUDIT.read_bytes())
    for p,h in audit['pins'].items():pin(Path(p),h)
    pin(pins_api.REPORT,'8b2496d8a38f297658cbc91187d0961c3bbfc048f29518af2c35c50de02c66a5')
    mask=json.loads(pins_api.REPORT.read_bytes());pin(PADDING);padding=json.loads(PADDING.read_bytes())
    require(padding['baseline']==mask['population']==audit['population']==770 and len(padding['candidates'])==51,'Exact additional prepared source groups')
    for p,h in padding['pins'].items():pin(Path(p),h)
    subtraction=defaultdict(set)
    for n in mask['candidates']:subtraction[n['scope'],n['name']].update(n['missing_positions'])
    for n in padding['candidates']:
        shape=n['shape'];offset=shape['serialized_offset']
        require((shape['left'],shape['right'])==('127','0') and (n['selected_left'],n['selected_right'])==(127,64),'Exact addresspadding upper-half coordinates')
        subtraction[n['scope'],n['name']].update(range(offset+128,offset+256))
    removed=Counter();ranking=defaultdict(lambda:dict(scopes=0,objects=0,missing_positions=0));scope_ranks=[]
    for s in audit['scopes']:
        remaining=[]
        for n in s['objects']:
            overlap=set(n['missing_coordinates']) & subtraction[s['scope'],n['name']]
            removed['additional_source_candidate_positions']+=len(overlap)
            keep=sorted(set(n['missing_coordinates'])-overlap)
            if keep:remaining.append(dict(n,remaining_coordinates=keep,remaining_missing=len(keep)))
        if not remaining:continue
        v=ranking[s['module']];v['scopes']+=1;v['objects']+=len(remaining);v['missing_positions']+=sum(n['remaining_missing'] for n in remaining)
        scope_ranks.append(dict(scope=s['scope'],module=s['module'],checksum=s['checksum'],
            missing_positions=sum(n['remaining_missing'] for n in remaining),objects=len(remaining),
            top=[dict(name=n['name'],missing_positions=n['remaining_missing'],portnode=n['portnode']) for n in remaining[:3]]))
    require(removed['additional_source_candidate_positions']==1024+6528,'Complete maskzero2/addresspadding51 subtraction')
    book=json.loads(pins_api.BOOK.read_bytes());pin(pins_api.BOOK,pins_api.BOOK_SHA);texts={}
    for rel in ('hardware/src/lane/vmfpu.sv','hardware/deps/fpnew/src/fpnew_pkg.sv','hardware/deps/fpnew/src/fpnew_top.sv',
                'hardware/deps/fpnew/src/fpnew_opgroup_block.sv','hardware/deps/common_cells/src/rr_arb_tree.sv'):
        path=ROOT/rel;pin(path,book[str(path)]);texts[path.name]=path.read_text()
    proof=source_contract(texts)
    db=OUT/'repaired-aligned-build-20260930-01/sim/simv.vdb/snps/coverage/db'
    shape=pins_api.typed.xml(db/'shape/tgl.verilog.shape.xml');sourcepath=db/'auxiliary/verilog.sourceinfo.xml';pin(sourcepath)
    files={n.get('id'):n.get('name') for n in pins_api.typed.xml(sourcepath).iter('fileinfo')}
    fields,whole=audit_api.exclusions(audit_api.PREPARED.read_text());f,w=audit_api.exclusions(audit_api.LZC.read_text());fields|=f;whole|=w
    existing=defaultdict(set)
    for scope,name in fields:existing[scope].add(name)
    candidates=[];inventories=[];groups=Counter()
    for s in audit['scopes']:
        picked=[]
        for n in s['objects']:
            selected=rule(s['scope'],n['name'])
            if selected is None:continue
            value,why,lane,g=selected
            require(n['kind']=='vectornode' and n['portnode']=='0' and n['excluded']=='0' and n['type']=='1' and
                    (n['left'],n['right'])==('63','0') and n['logical_bits']==64,'Exact internal numerical64, no status/tag/control/port')
            require(n['missing_slots']==128 and n['missing_coordinates']==list(range(n['serialized_offset'],n['serialized_offset']+128)),'Exact whole-result missing in actual770')
            require(not audit_api.overlaps(s['scope'],n['name'],existing,whole) and not subtraction[s['scope'],n['name']],'No prepared/native/source-group duplication')
            declaration=files[n['file']]
            storage=files[n['aux_file']]
            expected='hardware/deps/common_cells/src/rr_arb_tree.sv' if s['module']=='rr_arb_tree' else 'hardware/deps/fpnew/src/fpnew_opgroup_block.sv'
            require(declaration==str(ROOT/'hardware/deps/fpnew/src/fpnew_opgroup_block.sv') and n['line_num']=='72' and
                    storage==str(ROOT/expected) and n['aux_line_num']==('126' if s['module']=='rr_arb_tree' else '223' if n['name']=='arbiter_output.result' else '80'),
                    'Exact struct result declaration and separate actual storage declaration source IDs')
            picked.append(n['name']);groups[g]+=128
            candidates.append(dict(scope=s['scope'],name=n['name'],lane=lane,opgroup=g,checksum=s['checksum'],
                attributes={k:v for k,v in n.items() if k not in ('missing_coordinates','missing_slots','logical_bits','serialized_offset')},
                source_type_file=declaration,source_type_line=int(n['line_num']),
                source_storage_file=storage,source_storage_line=int(n['aux_line_num']),constant_hex=hex(value),proof_rule=why,
                logical_bits=64,missing_serialized_positions=n['missing_coordinates'],native_label=None))
        if not picked:continue
        defs=[d for d in shape.findall('tgldef') if d.get('chksum')==s['checksum'] and d.get('name','').split(' (')[0]==s['module']]
        require(len(defs)==1,'Exact module/checksum compiled identity');d=defs[0];params=d.get('param',d.get('name'))
        g=next(c['opgroup'] for c in candidates if c['scope']==s['scope'])
        if s['module']=='fpnew_opgroup_block':
            for key,val in (('OpGroup',g),('Width',64),('FpFmtMask',56),('FmtUnitTypes',0 if g==4 else 1365 if g in (0,2) else 2730),('NUM_FORMATS',6)):
                require(re.search(r'\b'+key+'='+str(val)+r'(?=[, )])',params),'Actual compiled operation/format specialization '+key)
            if g in (1,3):require('ANY_MERGED=1' in params and 'gen_parallel_slices[0].IS_FIRST_MERGED=1' in params,'Actual first merged format0')
        else:
            for key,val in (('NumIn',6),('LockIn',0),('IdxWidth',3)):
                require(re.search(r'\b'+key+'='+str(val)+r'(?=[, )])',params),'Compiled arbiter geometry/lock')
        inventories.append(dict(scope=s['scope'],module=s['module'],checksum=s['checksum'],compiled_parameters=params,
            target_names=picked,protected=[dict(kind=n.tag,**n.attrib) for n in d.find('tglshape') if n.get('name') not in picked],
            protected_descendant_scopes='All descendants and library state; no descendant-wide waiver',
            native_binding_status='Fresh exact full inventory and five-stage EL/complement mandatory; no native qualification inferred'))
    require(len(candidates)==176 and len(inventories)==40 and sum(groups.values())==22528,'Exact substantial residual group')
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_review_mfpu_disabled_results770.py'),Path(lemma.__file__),Path(lexical.__file__)):pin(path)
    for p,h in pins.items():require(digest(Path(p))==h,'Final source/raw pin drift')
    return dict(status='FROZEN770_DISABLED_FORMAT_INTERNAL_RESULTS_STATIC_ONLY',baseline=770,
        ranking_after_additional_subtractions=[dict(module=k,**v) for k,v in sorted(ranking.items(),key=lambda x:-x[1]['missing_positions'])[:20]],
        largest_scope_ranking=sorted(scope_ranks,key=lambda s:-s['missing_positions'])[:20],
        already_prepared_subtraction='Pinned full768V3 EL + LZC EL + source queueFP312 already removed in audit; additional exact coordinate subtraction maskzero2=1024, addresspadding51=6528. Partial padding leaves lower address bits active.',
        source_proof=proof,selected_one_group=dict(description='Vector MFPU disabled/merged-unused format numerical result placeholders and source-proven constant combinational arbiter copies',
            scopes=40,objects=176,logical_bits=11264,missing_serialized_positions=22528,by_opgroup_missing=dict(groups)),
        candidates=candidates,full_scope_complements=inventories,
        symbolic_tree_constants={str(g):{str(k):hex(v) for k,v in lemma.constant_nodes(6,active_formats(g),MAX).items()} for g in range(5)},
        protected='All ports/active format results/tag fields/FMA flags/rounding/control/handshake/arbiter state/dynamic library storage and all other metrics.',
        other_large_groups_not_blanket_candidates=['C910 pack54144 positions are special-value/rounding/sign-dependent: no whole-module or reliability waiver.',
            'Performance/verification monitors and CVXIF interface payloads rank high but are outside this numerical-source candidate.',
            'QBS adapters/payload storage are legal dynamic data; no current-case-unused justification.',
            'Remaining vaddr lower64 gaps remain stimulus candidates, not padding constants.'],
        native_qualified=False,EDA_launched=False,RTL_modified=False,coverage_admitted=False,official_percentage=None,pins=pins)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--verify',action='store_true');a=parser.parse_args();r=collect()
    if a.verify:require(json.loads(REPORT.read_bytes())==r,'Independent static replay differs')
    else:
        require(not REPORT.exists(),'Fresh review artifact only')
        with REPORT.open('x') as f:json.dump(r,f,indent=2);f.write('\n')
    print(json.dumps(dict(output=str(REPORT),seal=digest(REPORT),group=r['selected_one_group'],pins=len(r['pins']))))
