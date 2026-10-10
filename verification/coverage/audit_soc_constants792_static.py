"""Closed source-constant candidates; formal792 raw minus qualified791 EL. No EDA."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import targeted_toggle_evidence_v2 as t
import rank_cva6_scalar_data767 as typed
import report_global777_compact as native

ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'verification/out'
BASE=OUT/'scalar-misalign-offline-admitted792-agent-20261008-01'
BASE_SHA='0aadd9e4fa71a5a582830a043fedc67669b0f53cea866a1b8147a5526c8f81f4'
REPORT=OUT/'current-population791-inherited785-parent-20261008-01'
QUAL_SHA='ad675368b58524794a04cc7518374eaf025382e7687f57dd60f2bb9986cba1e3'
BOOK=OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
BOOK_SHA='6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'
CORE='ara_tb.dut.i_ara_soc.i_system.i_ariane'
SYSTEM='ara_tb.dut.i_ara_soc.i_system'


def targets():
    result=[]
    def add(family,scope,names,value='0',width=64):
        for name in names:result.append(dict(family=family,scope=scope,name=name,value=value,width=width))
    add('BOOT_FIXED',SYSTEM,['boot_addr_i'],'0x80000000')
    for scope in (CORE,CORE+'.csr_regfile_i',CORE+'.controller_i'):
        add('BOOT_FIXED',scope,['boot_addr_i'],'0x80000000')
    add('HART_ZERO',SYSTEM,['hart_id_i'],width=3)
    add('HART_ZERO',SYSTEM,['hart_id'])
    for scope in (CORE,CORE+'.csr_regfile_i',CORE+'.id_stage_i',CORE+'.issue_stage_i',CORE+'.issue_stage_i.i_issue_read_operands'):
        add('HART_ZERO',scope,['hart_id_i'])
    driver=CORE+'.issue_stage_i.i_issue_read_operands.i_cvxif_issue_register_commit_if_driver'
    add('HART_ZERO',driver,['hart_id_i','issue_req_o.hartid','register_o.hartid','commit_o.hartid'])
    for scope in (CORE+'.issue_stage_i.i_issue_read_operands',CORE+'.issue_stage_i'):
        add('HART_ZERO',scope,['x_issue_req_o.hartid','x_register_o.hartid','x_commit_o.hartid'])
    add('HART_ZERO',CORE,['x_issue_req.hartid','x_register.hartid','x_commit.hartid'])
    add('FLU_CAUSE_ZERO',CORE+'.ex_stage_i.branch_unit_i',['branch_exception_o.cause'])
    add('FLU_CAUSE_ZERO',CORE+'.ex_stage_i',['flu_exception_o.cause'])
    add('FLU_CAUSE_ZERO',CORE,['flu_exception_ex_id.cause','ex_ex_ex_id[0].cause'])
    add('FLU_CAUSE_ZERO',CORE+'.issue_stage_i',['ex_ex_i[0].cause'])
    add('FLU_CAUSE_ZERO',CORE+'.issue_stage_i.i_scoreboard',['ex_i[0].cause'])
    add('FLU_CAUSE_ZERO',CORE+'.gen_perf_counter.perf_counters_i',['branch_exceptions_i.cause'])
    add('FPU_TVAL_ZERO',CORE+'.ex_stage_i.fpu_gen.fpu_i',['fpu_exception_o.tval'])
    add('FPU_TVAL_ZERO',CORE+'.ex_stage_i',['fpu_exception_o.tval'])
    add('FPU_TVAL_ZERO',CORE,['fpu_exception_ex_id.tval','ex_ex_ex_id[3].tval'])
    add('FPU_TVAL_ZERO',CORE+'.issue_stage_i',['ex_ex_i[3].tval'])
    add('FPU_TVAL_ZERO',CORE+'.issue_stage_i.i_scoreboard',['ex_i[3].tval'])
    add('CVXIF_DISABLED_OUTPUT_ZERO',CORE+'.ex_stage_i',['x_result_o','x_exception_o.cause','x_exception_o.tval'])
    add('CVXIF_DISABLED_OUTPUT_ZERO',CORE,['x_result_ex_id','x_exception_ex_id.cause','x_exception_ex_id.tval'])
    add('READ_WDATA_ZERO',CORE+'.ex_stage_i.lsu_i.i_load_unit',['req_port_o.data_wdata'])
    add('READ_WDATA_ZERO',CORE+'.ex_stage_i.lsu_i.gen_mmu.i_cva6_mmu.i_ptw',['req_port_o.data_wdata'])
    add('READ_WDATA_ZERO',CORE+'.ex_stage_i.lsu_i.gen_mmu.i_cva6_mmu',['req_port_o.data_wdata'])
    for scope in (CORE+'.ex_stage_i.lsu_i',CORE+'.ex_stage_i'):
        add('READ_WDATA_ZERO',scope,['dcache_req_ports_o[0].data_wdata','dcache_req_ports_o[1].data_wdata'])
    add('READ_WDATA_ZERO',CORE,['dcache_req_ports_ex_cache[0].data_wdata','dcache_req_ports_ex_cache[1].data_wdata',
                              'dcache_req_ports_acc_cache[0].data_wdata','dcache_req_ports_acc_cache[1].data_wdata',
                              'dcache_req_to_cache[0].data_wdata','dcache_req_to_cache[1].data_wdata','dcache_req_to_cache[2].data_wdata'])
    add('READ_WDATA_ZERO',CORE+'.gen_accelerator.i_acc_dispatcher',['acc_dcache_req_ports_o[0].data_wdata',
        'acc_dcache_req_ports_o[1].data_wdata','dcache_req_ports_i[0].data_wdata','dcache_req_ports_i[1].data_wdata'])
    return result


def source_guard(texts):
    def expect(file,pattern):t.require(re.search(pattern,texts[file],re.S),'Source contract '+file+': '+pattern)
    expect('ara_soc.sv',r"DRAMBase\s*=\s*64'h8000_0000")
    expect('ara_soc.sv',r"assign hart_id\s*=\s*'0;")
    expect('ara_soc.sv',r'\.boot_addr_i\s*\(DRAMBase\s*\).*?\.hart_id_i\s*\(hart_id\s*\)')
    expect('ara_system.sv',r"assign hart_id\s*=\s*\{'0, hart_id_i\};")
    expect('ara_system.sv',r'\.boot_addr_i\s*\(boot_addr_i\s*\).*?\.hart_id_i\s*\(hart_id\s*\)')
    expect('cv64a6_imafdcv_sv39_config_pkg.sv',r'CVA6ConfigCvxifEn\s*=\s*0;')
    expect('cv64a6_imafdcv_sv39_config_pkg.sv',r"RVZCMT:\s*bit'\(0\)")
    expect('build_config_pkg.sv',r'cfg.CvxifEn\s*=\s*CVA6Cfg.CvxifEn;')
    expect('build_config_pkg.sv',r'cfg.RVZCMT\s*=\s*CVA6Cfg.RVZCMT;')
    fn=texts['ara_soc.sv'].split('function automatic config_pkg::cva6_user_cfg_t gen_usr_cva6_config',1)[1].split('endfunction',1)[0]
    t.require(not re.search(r'cfg\.(CvxifEn|RVZCMT|XLEN)\s*=',fn),'Config field overridden')
    expect('riscv_pkg.sv',r'INSTR_ADDR_MISALIGNED\s*=\s*0;')
    expect('branch_unit.sv',r'branch_exception_o.cause\s*=\s*riscv::INSTR_ADDR_MISALIGNED;')
    expect('ariane_pkg.sv',r'FLU_WB\s*=\s*0;')
    expect('ariane_pkg.sv',r'FPU_WB\s*=\s*3;')
    expect('cva6.sv',r'assign ex_ex_ex_id\[FLU_WB\]\s*=\s*flu_exception_ex_id;')
    expect('cva6.sv',r'assign ex_ex_ex_id\[FPU_WB\]\s*=\s*fpu_exception_ex_id;')
    expect('fpu_wrap.sv',r"assign fpu_exception_o.tval\s*=\s*'0;")
    expect('ex_stage.sv',r"end else begin : gen_no_cvxif\s*assign x_result_ready_o = '0;.*?assign x_exception_o\s*=\s*'0;.*?assign x_result_o\s*=\s*'0;")
    for name in ('load_unit.sv','cva6_ptw.sv'):
        expect(name,r"assign req_port_o.data_wdata\s*=\s*'0;")
    expect('acc_dispatcher.sv',r"assign acc_dcache_req_ports_o\s*=\s*'0;")
    expect('cvxif_issue_register_commit_if_driver.sv',r'issue_req_o.hartid\s*=\s*hart_id_i;')
    expect('cvxif_issue_register_commit_if_driver.sv',r'assign register_o.hartid\s*=\s*issue_req_o.hartid;')
    expect('cvxif_issue_register_commit_if_driver.sv',r'assign commit_o.hartid\s*=\s*issue_req_o.hartid;')


def evidence():
    pins={}
    def read(path,sha):
        t.require(t.digest(path)==sha,'Bound input drift: '+str(path));pins[str(path)]=sha
        return path.read_bytes()
    book=json.loads(read(BOOK,BOOK_SHA));texts={}
    files=['hardware/src/ara_soc.sv','hardware/src/ara_system.sv']
    files+=['hardware/deps/cva6/core/'+n for n in ('cva6.sv','ex_stage.sv','branch_unit.sv','fpu_wrap.sv',
        'issue_stage.sv','issue_read_operands.sv','scoreboard.sv','id_stage.sv','controller.sv','csr_regfile.sv',
        'cvxif_issue_register_commit_if_driver.sv','load_unit.sv','load_store_unit.sv','acc_dispatcher.sv',
        'cva6_mmu/cva6_ptw.sv','cva6_mmu/cva6_mmu.sv','perf_counters.sv',
        'include/riscv_pkg.sv','include/ariane_pkg.sv','include/build_config_pkg.sv','include/cv64a6_imafdcv_sv39_config_pkg.sv')]
    for relative in files:
        path=ROOT/relative;texts[path.name]=read(path,book[str(path)]).decode()
    source_guard(texts)
    admission=json.loads(read(BASE/'admission-manifest.json',BASE_SHA));authority=dict(admission['input_pins'],**admission['output_pins'])
    ledger=read(BASE/'combined-inputs.txt',authority[str(BASE/'combined-inputs.txt')]).decode().splitlines()
    t.require(admission['coverage_admitted'] is True and len(ledger)==len(set(ledger))==793,'Formal792 ledger')
    union=json.loads(read(BASE/'combined-toggle-bits.json',authority[str(BASE/'combined-toggle-bits.json')]))
    q=json.loads(read(REPORT/'qualification.json',QUAL_SHA))
    t.require(q['population']==q['actual_selected_tests']==791 and all(q[k] is True for k in
        ('complete_approved_EL_bitmask_union','all_other_bits_protected','raw_reset_final_equal','applied_reloaded_equal')),'Qualified791 native report')
    c=json.loads(read(REPORT/'config.json',q['config_seal']))
    t.require(ledger[:-1]==c['input_ledger'],'Exact791 prefix, one792 suffix')
    ep=REPORT/'applied.el';others,masks=native.semantic(read(ep,q['output_pins'][str(ep)]).decode())
    whole={s for s,ch,m,line in others if line=='WHOLE_SCOPE'};owners=defaultdict(set)
    for s,ch,n,k,d,p,z in masks:owners[s].add(n)
    db=Path(ledger[0])/'snps/coverage/db';tree=[]
    for rel in ('design/verilog.design.xml','shape/tgl.verilog.info.xml','shape/tgl.verilog.shape.xml'):
        path=db/rel;read(path,authority[str(path)]);tree.append(t.xml(path))
    scopes={x['scope'] for x in targets() if x['scope'] in union}
    candidates=[];held=[];already=[];totals=defaultdict(lambda:dict(fields=0,logical_bits=0,raw_missing=0))
    for scope in sorted(scopes):
        if any(scope==s or scope.startswith(s+'.') for s in whole):already.append(dict(scope=scope,reason='APPROVED_WHOLE_SCOPE'));continue
        try:
            checks,defs=t.definitions(*tree,[scope])
            t.require(union[scope]['checksum']==checks[scope],'Toggle info checksum')
            nodes,arrays=typed.typed_nodes(defs[scope]['shape'],union[scope])
        except ValueError as error:
            held.append(dict(scope=scope,reason=str(error)));continue
        names={n['name']:n for n in nodes};t.require(len(names)==len(nodes),'Unique typed fields')
        for target in [v for v in targets() if v['scope']==scope]:
            name=target['name']
            if any(name==n or name.startswith(n+'.') or n.startswith(name+'.') for n in owners[scope]):
                already.append(dict(target,reason='EXISTING_EL_OWNERSHIP_OR_PARTIAL_HOLD'));continue
            if name not in names:
                held.append(dict(target,reason='NO_EXACT_SERIALIZED_NODE_OR_MDA'));continue
            node=names[name]
            t.require(node['logical_width']==target['width'],'Exact source/compiled width')
            item=dict(target,module=defs[scope]['module'],toggle_checksum=checks[scope],compiled_attributes=node,
                raw_missing=node['missing_slots'],static_reason='Closed producer constant and exact direct port/wire propagation',
                constant_after_combinational_settling=True,initial_X_or_delta_instrumentation_qualified=False,
                native_binding_qualified=False,excluded=False)
            candidates.append(item);total=totals[target['family']]
            total['fields']+=1;total['logical_bits']+=target['width'];total['raw_missing']+=node['missing_slots']
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_audit_soc_constants792_static.py')):
        read(path,t.digest(path))
    for path,sha in pins.items():t.require(t.digest(path)==sha,'Read-end drift')
    return dict(status='SOURCE_BOUND_STATIC_CONSTANT_CANDIDATES792_NOT_NATIVE_APPROVED',population=792,
        manifest_seal=BASE_SHA,native_report_seal=QUAL_SHA,capacity=dict(totals),candidates=candidates,
        existing_EL_removed_or_held=already,shape_or_MDA_HOLD=held,input_pins=pins,
        source_proofs={
            'BOOT_FIXED':'ara_soc DRAMBase -> system -> cva6 -> csr/controller inputs; frontend rst_addr_ctrl_if NOT included',
            'HART_ZERO':'SoC hart_id=0 -> zero-extended system hart_id -> CVA6/issue input -> driver hartid -> direct issue/register/commit copies',
            'FLU_CAUSE_ZERO':'branch_unit sole cause writer = INSTR_ADDR_MISALIGNED(0) -> ex_stage FLU -> FLU_WB0 -> issue ex_ex_i0 -> scoreboard ex_i0; no stored exception mux fields included',
            'FPU_TVAL_ZERO':'fpu_wrap explicit tval=0; ex_stage no-FPU branch also0 -> FPU_WB3 -> issue and scoreboard input; fflags/cause remain dynamic',
            'CVXIF_DISABLED_OUTPUT_ZERO':'Frozen imafdcv CvxifEn0 preserved through build_config/SoC; ex_stage gen_no_cvxif explicit output0 -> CVA6 wires; floating inputs/rd/we NOT included',
            'READ_WDATA_ZERO':'PTW/load_unit explicit req_port_o.data_wdata0 -> MMU/LSU/execute/CVA6 ports0/1; acc_dispatcher entire output0 -> CVA6 acc ports and cache slot2; no store port2 wdata included'},
        protected=['all noncandidate fields and descendants','all memory addresses/read data/store data','all dynamic FPU cause/fflags/status',
            'all scoreboard stored exception/result fields','all unknown/unassigned CVXIF inputs including x_result_i',
            'id_stage RVZCMT0 unassigned dcache request outputs: X is NOT zero','partial EL overlaps/MDA/ambiguous definitions',
            'RR190/class-padding/FPNEW90/QBSbank1 group_hit: no additions'],
        alignment_and_index_subfields='HOLD until complete writer proof and exact native selected-bit mapping; not counted',
        official_denominator=None,predicted_percentage=None,EDA_started=False,waivers_applied=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    path=p.parse_args().output.resolve();t.require(path.parent==OUT and not path.exists(),'Fresh static output')
    result=evidence()
    with path.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(output=str(path),sha256=t.digest(path),capacity=result['capacity'],candidates=len(result['candidates']),HOLD=len(result['shape_or_MDA_HOLD']))),flush=True)
