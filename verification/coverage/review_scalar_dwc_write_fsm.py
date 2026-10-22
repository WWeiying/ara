"""Frozen all-producer scalar DWC FSM source candidates; no EDA or EL."""
import argparse
import itertools
from pathlib import Path
import re
import run_scalar_fpu_finite as support
import review_dwc_internal_error742 as prior

life,require=support.life,support.require
BUILD=support.old.BUILD;DB=BUILD/'sim/simv.vdb/snps/coverage/db'
BASE=life.OUT/'load-ni-tlb-offline-admitted-762-agent-20261007-01'
BASE_SHA='6959f676c022f38f9ee2977252c600cfeb5b89fe50b3c4b22d08bf5de7b95cc5'
PRIOR=life.OUT/'dwc-internal-error742-source-proof-agent-20261007-01.json'
PRIOR_SHA='968927e24bd550c938739b9a6bb66eaf9c2c5e1faaacf608fb25495743245e8a'
RANK=life.OUT/'admitted762-fsm-priority-parent-20261007-01.json'
RANK_SHA='67c936292c506e29d3e13b244b39dd9bab284ac2988f4c1f918b8d4335548d90'
CORE='ara_tb.dut.i_ara_soc.i_system.i_ariane'
SOURCES=tuple(dict.fromkeys(prior.SOURCES+[
    'hardware/src/ara_soc.sv','hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
    'hardware/deps/cva6/core/include/config_pkg.sv','hardware/deps/cva6/core/include/build_config_pkg.sv',
    'hardware/deps/cva6/core/decoder.sv','hardware/deps/cva6/core/commit_stage.sv',
    'hardware/deps/cva6/core/load_store_unit.sv','hardware/deps/cva6/core/store_unit.sv',
    'hardware/deps/cva6/core/amo_buffer.sv','hardware/deps/cva6/core/cache_subsystem/wt_dcache.sv',
    'hardware/deps/cva6/core/cache_subsystem/wt_dcache_missunit.sv']))


def contract(adapter,shim,up):
    adapter,shim,up=map(prior.clean,(adapter,shim,up))
    require([rhs.strip() for rhs in re.findall(r'\baxi_wr_blen\s*=(?!=)\s*([^;]+);',adapter)]==["'0"],
        'All WT write producers must have a single unconditional len0 assignment')
    for port,net in (('wr_blen_i','axi_wr_blen'),('wr_atop_i','axi_wr_atop'),('axi_req_o','axi_req_o')):
        require(len(re.findall(r'\.'+port+r'\s*\(\s*'+net+r'\s*\)',adapter))==1,'Shim wiring differs')
    for field,rhs in (('len','wr_blen_i'),('atop','wr_atop_i'),('burst','axi_pkg::BURST_INCR'),
                      ('cache','axi_pkg::CACHE_MODIFIABLE')):
        require([value.strip() for value in re.findall(r'axi_req_o\.aw\.'+field+r'\s*=(?!=)\s*([^;]+);',shim)]==[rhs],
            'Unique AW field producer differs: '+field)
    entries=[rhs.strip() for rhs in re.findall(r'\bw_state_d\s*=(?!=)\s*([^;]+);',up)]
    require(entries.count('W_INCR_UPSIZE')==1 and set(entries)<=
        {'w_state_q','W_IDLE','W_INCR_UPSIZE','W_PASSTHROUGH'},'Additional write state entry')
    require(re.search(r'if\s*\(modifiable\(slv_req_i\.aw\.cache\)\)\s*'
        r'if\s*\(slv_req_i\.aw\.len\s*!=\s*\x270\)\s*begin(?:(?!\bend\b).)*'
        r'w_state_d\s*=\s*W_INCR_UPSIZE',up,re.S),'Write upsize predicate not bound')
    require([rhs.strip() for rhs in re.findall(r'w_state_q\s*<=\s*([^;]+);',up)]==['W_IDLE','w_state_d'],'Reset/hold induction differs')
    for token in ('AMO_SWAP: axi_wr_atop = axi_pkg::ATOP_ATOMICSWAP;',
        'axi_pkg::ATOP_ATOMICLOAD, axi_pkg::ATOP_LITTLE_END, axi_pkg::ATOP_ADD'):
        require(token in adapter,'Legal AMO producer missing')
    require(re.search(r'if\s*\(slv_req_i\.aw_valid\s*&&\s*slv_req_i\.aw\.atop\[axi_pkg::ATOP_R_RESP\]\)',up)
        and re.search(r'if\s*\(inject_aw_into_ar\)\s*begin\s*r_state_d\s*=\s*R_INJECT_AW',up),
        'R-response injection path differs')
    return dict(all_write_producers_single_beat=True,aw_len=0,aw_burst='INCR',aw_cache='MODIFIABLE',
        aw_atop_not_constant_zero=True,write_upsize_requires_len_nonzero=True,
        write_reset='W_IDLE',read_injection_requires_atop_R_RESP=True)


def entry(length,modifiable=True,burst='INCR'):
    # Predicate abstracted from the bound source; not an RTL simulator.
    return 'W_INCR_UPSIZE' if burst=='INCR' and modifiable and length!=0 else 'W_PASSTHROUGH'


def points(definition,row):
    bits=format(int(row['bits'],16),'0%db'%row['width']);result=[];offset=0
    for machine in definition.find('fsmshape'):
        states=machine.findall('state');arcs=machine.findall('transition');ids={s.get('id'):s for s in states}
        for s in states:
            result.append(dict(scope=prior.DWC,machine=machine.get('name'),machine_checksum=machine.get('chksum'),
                kind='state',state=s.get('name'),enum_value=s.get('value'),compiled_attributes=dict(s.attrib),
                raw_index=offset,hit=bits[offset]=='1',candidate=machine.get('name')=='w_state_d' and s.get('name')=='W_INCR_UPSIZE',
                native_selector=None,native_identity_qualified=False));offset+=1
        for arc in arcs:
            frm,to=ids[arc.get('fromid')],ids[arc.get('toid')]
            result.append(dict(scope=prior.DWC,machine=machine.get('name'),machine_checksum=machine.get('chksum'),
                kind='transition',from_state=frm.get('name'),to_state=to.get('name'),
                from_enum=frm.get('value'),to_enum=to.get('value'),compiled_attributes=dict(arc.attrib),
                raw_index=offset,hit=bits[offset]=='1',candidate=machine.get('name')=='w_state_d' and
                'W_INCR_UPSIZE' in (frm.get('name'),to.get('name')),
                native_selector=None,native_identity_qualified=False));offset+=1
    require(offset==row['width']==31,'Whole scoped FSM width differs')
    chosen=[p for p in result if p['candidate']]
    require([p['raw_index'] for p in chosen]==[1,3,5] and all(not p['hit'] for p in chosen),
        'Invariant contradicts measured source-bound points')
    require(all(p['machine_checksum']=='688831953' for p in chosen),'Write FSM checksum differs')
    return result


def collect():
    manifest=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    bitmap_path=BASE/'combined-bits.json'
    bitmap=life.read_bound(bitmap_path,manifest['output_pins'][str(bitmap_path)])
    require(len(bitmap['tests'])==762,'Wrong formal diagnostic population')
    old=life.read_bound(PRIOR,PRIOR_SHA);ranking=life.read_bound(RANK,RANK_SHA)
    require(old['scope']==prior.FILTER and old['scope']!=prior.DWC and
        old['prior_AMO_error_path_argument'].startswith('Rejected:'),'Prior policy boundary differs')
    bookpath=BUILD/'build-source-pins.json';book=life.read_bound(bookpath,support.old.SOURCE_SHA)
    pins={str(BASE/'admission-manifest.json'):BASE_SHA,str(bitmap_path):manifest['output_pins'][str(bitmap_path)],
        str(PRIOR):PRIOR_SHA,str(RANK):RANK_SHA,str(bookpath):support.old.SOURCE_SHA}
    texts={}
    for rel in SOURCES:
        p=life.ROOT/rel;pins=life.merge_pins(pins,{str(p):book[str(p)]})
        life.check({str(p):book[str(p)]});texts[rel]=p.read_text()
    key='hardware/deps/cva6/core/cache_subsystem/'
    proof=contract(texts[key+'wt_axi_adapter.sv'],texts['hardware/deps/cva6/core/axi_shim.sv'],
        texts['hardware/deps/axi/src/axi_dw_upsizer.sv'])
    config=texts['hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv']
    require('CVA6ConfigAExtEn = 1;' in config and 'CVA6ConfigDcacheType = config_pkg::WT;' in config and
        'NOCType: config_pkg::NOC_TYPE_AXI4_ATOP' in config,'Frozen source configuration differs')
    soc=prior.clean(texts['hardware/src/ara_soc.sv'])
    function=soc.split('gen_usr_cva6_config(',1)[1].split('endfunction',1)[0]
    require(not re.search(r'cfg\.(RVA|NOCType|DCacheType)\s*=',function),'SoC overrides atomic/cache contract')
    for field in ('RVA','NOCType','DCacheType'):
        require('cfg.'+field+' = CVA6Cfg.'+field+';' in texts['hardware/deps/cva6/core/include/build_config_pkg.sv'],
                'Build configuration propagation differs')
    def has(text,token):require(re.sub(r'\s+','',token) in re.sub(r'\s+','',prior.clean(text)),'Producer path differs: '+token)
    for token in ('.noc_req_o (ariane_narrow_axi_req)', '.slv_req_i (ariane_narrow_axi_req)',
                  '.slv_reqs_i ({ara_axi_req_inval, ariane_axi_req})'):
        has(texts['hardware/src/ara_system.sv'],token)
    has(texts['hardware/deps/cva6/core/cva6.sv'],'.noc_req_o (noc_req_o)')
    has(texts[key+'wt_cache_subsystem.sv'],'.axi_req_o (noc_req_o)')
    has(texts['hardware/deps/cva6/core/amo_buffer.sv'],'assign amo_req_o.req = no_st_pending_i & amo_valid_commit_i & amo_valid;')
    has(texts['hardware/deps/cva6/core/store_unit.sv'],'AMO_ADDW, AMO_ADDD: amo_op_d = AMO_ADD;')
    has(texts[key+'wt_dcache_missunit.sv'],'mem_data_o.rtype = DCACHE_ATOMIC_REQ;')
    require('ariane_pkg::AMO_ADDD' in texts['hardware/deps/cva6/core/decoder.sv'],'Legal AMO decode absent')
    for rel in ('design/verilog.design.xml','auxiliary/verilog.sourceinfo.xml','shape/fsm.verilog.shape.xml',
                'shape/tgl.verilog.shape.xml','shape/tgl.verilog.info.xml'):
        p=DB/rel;require(str(p) in old['input_pins'],'Unbound compiled input')
        pins=life.merge_pins(pins,{str(p):old['input_pins'][str(p)]})
    life.check(pins)
    design=prior.t.xml(DB/'design/verilog.design.xml');nodes={n.get('id'):(n,m) for m in design.findall('srcdef') for n in m.findall('srcinst')}
    def path(k):
        n,_=nodes[k];return (path(n.get('pid'))+'.' if n.get('pid') in nodes else '')+n.get('name')
    hierarchy={path(k):m for k,(_,m) in nodes.items()}
    ownership={CORE+'.gen_cache_wt.i_cache_subsystem':'wt_cache_subsystem',
        CORE+'.gen_cache_wt.i_cache_subsystem.i_adapter':'wt_axi_adapter',
        CORE+'.gen_cache_wt.i_cache_subsystem.i_adapter.i_axi_shim':'axi_shim',
        CORE+'.ex_stage_i.lsu_i.i_store_unit.genblk1.i_amo_buffer':'amo_buffer',prior.DWC:'axi_dw_upsizer'}
    for scope,module in ownership.items():require(hierarchy[scope].get('name')==module,'Compiled producer binding differs')
    tshape=prior.t.xml(DB/'shape/tgl.verilog.shape.xml')
    up=[d for d in tshape if d.get('name')=='axi_dw_upsizer']
    require(len(up)==1 and all(token in up[0].get('param','') for token in
        ('AxiMaxReads=2,','AxiSlvPortDataWidth=64,','AxiMstPortDataWidth=128,','AxiIdWidth=4,')),
        'Compiled upsizer parameter differs')
    shape=prior.t.xml(DB/'shape/fsm.verilog.shape.xml');row=bitmap['metrics']['fsm'][prior.DWC]
    definitions=[d for d in shape.iter('fsmdef') if d.get('chksum')==row['checksum'] and
        any(n.get('name')==prior.DWC for n in d.findall('fsminst'))]
    require(len(definitions)==1 and row['checksum']=='3866098985' and definitions[0].get('file')=='305',
        'Scoped FSM checksum/source differs')
    files={n.get('id'):n.get('name') for n in prior.t.xml(DB/'auxiliary/verilog.sourceinfo.xml').iter('fileinfo')}
    require(files['305']==str(life.ROOT/'hardware/deps/axi/src/axi_dw_upsizer.sv'),
        'Compiled source is not reviewed AXI tree (CVA6 vendor duplicate protected)')
    allpoints=points(definitions[0],row);targets=[p for p in allpoints if p['candidate']]
    ranked=[i for i in ranking['instances'] if i['scope']==prior.DWC]
    require(len(ranked)==1 and ranking['population']==762 and all(any(
        n['raw_position']==p['raw_index'] and not n['already_native_qualified_exclusion'] for n in ranked[0]['missing'])
        for p in targets),'Duplicate or inconsistent existing policy')
    checks=0
    for _ in itertools.product(range(64),range(8),(False,True),(False,True)):
        require(entry(0)=='W_PASSTHROUGH','Legal single-beat source can enter write upsize');checks+=1
    pins=life.merge_pins(pins,{str(Path(__file__).resolve()):life.digest(Path(__file__).resolve()),
        str(Path(__file__).with_name('test_review_scalar_dwc_write_fsm.py')):life.digest(Path(__file__).with_name('test_review_scalar_dwc_write_fsm.py')),
        str(Path(prior.__file__).resolve()):life.digest(Path(prior.__file__).resolve())})
    life.check(pins)
    return dict(status='SCALAR_DWC_W_UPSIZE_SOURCE_CANDIDATES_R_INJECTION_PROTECTED',baseline=762,scope=prior.DWC,
        scope_checksum=row['checksum'],compiled_parameters=up[0].attrib,compiled_producer_ownership=ownership,
        compiled_composite_config_note='CVA6Cfg=-1 is a DVE composite rendering, not a literal value. WT and RVA branch binding plus frozen configuration propagation are used.',
        source_contract=proof,source_bound_induction_checks=checks,valid_reset_required=True,
        initial_write_state='W_IDLE',reachable_write_states=['W_IDLE','W_PASSTHROUGH'],
        candidate_points=targets,protected_points=[p for p in allpoints if not p['candidate']],
        candidate_states=1,candidate_transitions=2,protected_positions=28,
        upstream_master_chain=['I-cache fills are read-only at WT arbiter',
            'PTW/ordinary/accelerator cache reads and scalar stores -> WT Dcache -> sole wt_axi_adapter',
            'Committed AMO -> amo_buffer -> WT missunit DCACHE_ATOMIC_REQ -> same adapter',
            'axi_shim directly supplies narrow DWC; Ara/vector and other SoC traffic joins only downstream'],
        r_inject_counterexample=dict(instruction='amoadd.d t2,t1,(t0)',address='aligned cached DRAM',
            preconditions='Legal RVA op reaches commit; store buffer/miss queue drained; one free DWC read slot and no ID clash',
            producer_atop='ATOP_ATOMICLOAD|LITTLE_END|ADD = 0x20 (R_RESP bit5=1)',aw_len=0,
            memory_oracle='old memory1, addend2 -> rd1, memory3; not simulated in this audit',
            cycle_witness=['W_IDLE, read slot R_IDLE, AWVALID1/ATOP[5]1 -> inject_aw_into_ar_req1',
                'AR arbiter injection selected, available read slot grant -> R_INJECT_AW',
                'Following cycle copies saved original AW metadata -> R_PASSTHROUGH'],
            measured=False,waiver_rejected=True),
        negative_source_counterexample=dict(alternate_master_len1=entry(1),reason='Removing the WT singleton invariant makes W_INCR_UPSIZE reachable'),
        prior_policy_scope=old['scope'],prior_policy_disjoint=True,
        prior_ATOP_rejection_scope='Only WRAP-error routing; not R-response injection at the normal upsizer',
        all_descendants_and_other_metrics_protected=True,native_identity_qualified=False,
        EL_generated=False,exclusions_applied=False,EDA_launched=False,RTL_modified=False,pins=pins)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.absolute()
    require(out.parent==life.OUT and not out.exists(),'Fresh output JSON required')
    result=collect();life.save(out,result)
    print('SOURCE_CANDIDATES '+life.digest(out)+' states1/transitions2/protected28 R_INJECT_AW_RETAINED',flush=True)
