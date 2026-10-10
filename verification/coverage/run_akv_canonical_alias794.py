"""One native alias run, immutable input authority, bounded foreground worker."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from types import FunctionType

import preflight_akv_canonical_alias794 as case
import collect_akv_canonical_alias794 as collector
import run_akv_entropy as old

life,require=old.life,case.require
PRE=life.OUT/'akv-canonical-alias794-preflight-agent-20261008-02'
PRE_SHA='0a1608bb9176452aad21efd75256bb3315742e4d3c3b44e5adf2be7aa7b56e98'
ELF=PRE/'input.elf'
BASE,BASE_SHA=case.static.BASE,case.static.BASE_SHA
PROBE=Path(__file__).with_name('akv_canonical_alias794_probe.tcl').resolve()
NAME='akv_canonical_alias794'
BUDGET=900


def command(output):
    return FunctionType(old.command.__code__,dict(old.command.__globals__,ELF=ELF,PROBE=PROBE,NAME=NAME))(output)


def compiled_probe(ledger):
    s=case.static;db=Path(ledger[0])/'snps/coverage/db'
    defs=s.definitions(*(s.shape.xml(db/p) for p in ('design/verilog.design.xml',
        'shape/tgl.verilog.info.xml','shape/tgl.verilog.shape.xml')),list(s.FIELDS))
    rows=json.loads((BASE/'combined-toggle-bits.json').read_bytes())
    nodes={k:s.typed.typed_nodes(v['shape'],rows[k])[0] for k,v in defs.items()}
    matched={}
    for name,width in collector.WIDTHS.items():
        scope=s.SCOPE+('.i_read_engine' if name.startswith('i_read_engine.') else '')
        leaf=name.removeprefix('i_read_engine.')
        if leaf=='read_range_tag':
            children=[n for n in nodes[scope] if n['name'].startswith(leaf+'.')]
            require({n['name']:n['logical_width'] for n in children}==
                    {'read_range_tag.index':6,'read_range_tag.role':2},'Exact packed role/index tag members')
            matched[name]=dict(width=8,children={n['name']:n['logical_width'] for n in children})
        else:
            found=[n for n in nodes[scope] if n['name']==leaf]
            require(len(found)==1 and found[0]['logical_width']==width,'Exact compiled probe width: '+name)
            matched[name]=dict(width=width,checksum=rows[scope]['checksum'])
    return matched


def historical(ledger,base,newhash):
    from admit_stride_metadata768 import dedup
    p=BASE/'elf-ledger-dedup.json';h=base['output_pins'][str(p)];audit=life.read_bound(p,h)
    authority=life.merge_pins(base['input_pins'],base['output_pins'])
    require(audit['ledger_members']==793 and len(audit['members'])==793
            and [m['vdb'] for m in audit['members']]==ledger[1:794], 'Sealed793 ELF audit prefix')
    require(all(authority.get(p)==h for p,h in audit['pins'].items()),'Audit inherited authority')
    require(all(m['ELF_candidates'] and newhash not in m['ELF_candidates'].values() for m in audit['members']), 'Historical ELF duplicate')
    suffix=dedup([ledger[0],ledger[794]],newhash,authority)
    require(all(authority.get(p)==h for p,h in suffix['pins'].items()), 'Actual794 suffix authority')
    return life.merge_pins({str(p):h},suffix['pins']),dict(members=794,duplicate=False,
        inherited_audit_sha256=h,suffix=suffix['members'],historical_raw_VDBs_not_recollected=True)


def prepare(output):
    output=Path(output).absolute()
    require(output.parent==life.OUT and output.resolve()==output and not output.exists()
            and not output.with_name(output.name+'.prepared.json').exists(), 'Fresh direct worker output')
    pre=life.read_bound(PRE/'preflight-manifest.json',PRE_SHA)
    require(pre['status']=='AKV_CANONICAL_ALIAS794_PREFLIGHT_PASS_NOT_VCS' and pre['input_elf']==str(ELF)
        and pre['dut_checks']==4247 and pre['expected_commands']==10 and pre['expected_ecalls']==2
        and pre['coverage_admitted'] is False and pre['software_reference_is_not_native_Spike'] is True,'Exact preflight contract')
    life.check(pre['pins']);life.check(pre['output_pins'])
    targets=case.static.review();base=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    require(base['coverage_admitted'] is True,'Admitted794 baseline')
    lp=BASE/'combined-inputs.txt';require(case.sha(lp)==base['output_pins'][str(lp)], '794 ledger hash')
    ledger=lp.read_text().splitlines();require(len(ledger)==len(set(ledger))==795,'Exact794 population')
    pins=life.merge_pins(pre['pins'],pre['output_pins']);pins=life.merge_pins(pins,targets['input_pins'])
    pins=life.merge_pins(pins,{str(PRE/'preflight-manifest.json'):PRE_SHA,str(BASE/'admission-manifest.json'):BASE_SHA})
    hp,dedup=historical(ledger,base,case.sha(ELF));pins=life.merge_pins(pins,hp)
    image=life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(len(image['image'])==66 and image['simv']==str(life.IMAGE),'Exact frozen simv66')
    pins=life.merge_pins(pins,image['image']);pins=life.merge_pins(pins,{str(life.PLAN):life.PLAN_SEAL})
    bookpath=case.old.BUILD/'build-source-pins.json';book=life.read_bound(bookpath,pins[str(bookpath)])
    snapshot=life.OUT/'old-image-source-evidence-20261006-01/ara_dispatcher.sv'
    pins=life.merge_pins(pins,{str(snapshot):book[str(life.ROOT/'hardware/src/ara_dispatcher.sv')]})
    pins,source=collector.old.isa.base.source_contract(book,pins)
    csr=life.ROOT/'hardware/deps/cva6/core/csr_regfile.sv'
    collector.old.isa.base.source_anchors(csr.read_text(),["satp_q <= {CVA6Cfg.XLEN{1'b0}};",'priv_lvl_d = mstatus_q.mpp;',
        'mstatus_d.mpp = priv_lvl_q;',"mstatus_d.mpie = 1'b1;"])
    anchor=collector.old.isa.base.source_anchors
    anchor((life.ROOT/'hardware/src/vlsu/vlsu.sv').read_text(),[
        '.command_descriptor_address_i (pe_req_i.scalar_op)', '.command_selector_i (pe_req_i.scalar_op)',
        '.command_tile_start_i (pe_req_i.stride)'])
    anchor((life.ROOT/'hardware/src/vlsu/akv/akv_engine.sv').read_text(),[
        'typedef struct packed { akv_range_role_e role; logic [5:0] index; } akv_range_tag_t;'])
    anchor((life.ROOT/'hardware/src/vlsu/qbs/qbs_read_engine.sv').read_text(),[
        'assign translation_complete = plan_state_q == QBS_PLAN_TRANSLATE && en_ld_st_translation_i && (mmu_exception_valid_i || mmu_valid_i);',
        'QBS_PLAN_TRANSLATE: begin if (!mmu_exception_valid_i && (!en_ld_st_translation_i || mmu_valid_i) && physical_range_allowed_i) begin ar_addr_q <= planned_ar_addr;',
        'ar_cursor_vaddr_q <= planner_cursor_q;'])
    probe_contract=compiled_probe(ledger)
    for module in tuple(sys.modules.values()):
        f=getattr(module,'__file__',None)
        if f:
            p=Path(f).resolve()
            if p.suffix=='.py' and (p.parent==Path(__file__).resolve().parent or p.is_relative_to(life.ROOT/'verification/ara_verify')):
                pins=life.merge_pins(pins,{str(p):case.sha(p)})
    pins=life.merge_pins(pins,{str(PROBE):case.sha(PROBE),str(Path(__file__).with_name('test_akv_canonical_alias794_runtime.py').resolve()):case.sha(Path(__file__).with_name('test_akv_canonical_alias794_runtime.py')),
        str(collector.old.CONVERTER):collector.old.CONVERTER_SHA})
    model,dry=collector.replay(ELF.read_bytes(),pre['symbols']);life.check(pins)
    return dict(case=NAME,pins=pins,preflight=pre,command=command(output),timeout_s=BUDGET,wave_limit_bytes=64*1024*1024,
        baseline_tests=794,baseline=str(BASE),baseline_sha256=BASE_SHA,targets=targets,source_proof=source,
        historical_ELF_dedup=dedup,dry_model=dry,expected_requests=len(model.requests),collector_ready=True,
        probe_contract=probe_contract,selector_descriptor_same_source=True,
        translation_sampling='preedge TRANSLATE valid acceptance -> same-posedge settled AR registers',
        budget_basis=dict(native_model_steps=dry['steps'],software_adapter_steps=120799,
            comparable_float_scalar_steps=36957,comparable_wall_s=162,scaled_scalar_s=round(dry['steps']*162/36957,2),
            scope='Estimate, not measured runtime. Includes margin for MMU/custom/VPD; one900s attempt, no retry'),
        EDA_launched=False,coverage_admitted=False,automatic_retry=False,future_admission_requires_latest_rebase=True)


def verify(output,seal):
    p=Path(output).absolute().with_name(Path(output).name+'.prepared.json');m=life.read_bound(p,seal)
    require(m['case']==NAME and m['collector_ready'] is True and m['baseline_sha256']==BASE_SHA
        and m['preflight']==life.read_bound(PRE/'preflight-manifest.json',PRE_SHA)
        and m['command']==command(Path(output).absolute()) and m['timeout_s']==BUDGET
        and m['automatic_retry'] is False and m['coverage_admitted'] is False,'Exact frozen worker contract')
    life.check(m['pins'])
    if (Path(output)/'manifest.json').exists():require(json.loads((Path(output)/'manifest.json').read_bytes())==m,'Actual manifest')
    return m


def run(output,seal):
    output=Path(output).absolute();require(not output.exists(),'Fresh execution output');m=verify(output,seal)
    output.mkdir();life.save(output/'manifest.json',m);p=None
    try:
        with (output/'console.log').open('x') as log:
            p=subprocess.Popen(m['command'],cwd=output,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            live=FunctionType(old.live_identity.__code__,dict(old.live_identity.__globals__,ELF=ELF))(p,output,m)
            live['budget_s']=BUDGET;life.save(output/'started.json',live)
            p.wait(timeout=BUDGET);require(p.returncode==0,'Nonzero simulation exit')
        life.check(m['pins']);wave=output/'entropy-ranges.vpd'
        require(wave.is_file() and 0<wave.stat().st_size<=m['wave_limit_bytes'],'Final wave limit')
        life.save(output/'simulation-status.json',dict(status='SIMULATION_EXITED_NOT_ADMITTED',returncode=0,timeout=False,pid=p.pid,coverage_admitted=False))
    except BaseException as e:
        if p is not None and p.poll() is None:os.killpg(p.pid,signal.SIGKILL);p.wait()
        life.save(output/'simulation-status.json',dict(status='SIMULATION_FAILED_NOT_ADMITTED',reason=str(e),
            timeout=isinstance(e,subprocess.TimeoutExpired),coverage_admitted=False));raise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('prepare','verify','run'));p.add_argument('--output',type=Path,required=True);p.add_argument('--prepared-seal')
    a=p.parse_args();require((a.mode!='prepare')==bool(a.prepared_seal),'Explicit execution/check seal')
    if a.mode=='prepare':
        m=prepare(a.output);f=a.output.absolute().with_name(a.output.name+'.prepared.json');life.save(f,m)
        print(json.dumps(dict(prepared=str(f),seal=case.sha(f),pins=len(m['pins']),native_steps=m['dry_model']['steps'],EDA_launched=False)))
    elif a.mode=='verify':verify(a.output,a.prepared_seal);print('VERIFY_PASS_NO_EDA')
    else:run(a.output,a.prepared_seal)
