"""Remaining eleven authorized SEW/stage fixtures; frozen driver, at most eight concurrent VCS."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import re
import run_external_reset_fixture as shared

life,require=shared.life,shared.require
PRE=life.OUT/'fpu-active-reset-matrix-preflight745-agent-20261007-01'
PRE_SHA='2f77429d088359d1f0904b125e31bb61ea26e45cb6d76804a2270a1341991e33'
BASE=life.OUT/'external-reset-fpu-half-offline-admitted-746-agent-20261007-01'
BASE_SHA='edcc5b1614dd65c51c8e9c69f1ce60bb9196101eea89330c59fde05238a96ddb'
STAGES={'RF':(4,12),'EX1':(5,7),'EX2':(6,8),'WB_REQ':(7,15)}
CASES=[(sew,stage) for sew in (16,32,64) for stage in STAGES if (sew,stage)!=(16,'EX2')]
PLAN=life.OUT/'fpu-external-reset-matrix-remaining11-746-agent-20261007-01.prepared.json'


def select(pre,sew,stage):
    require((sew,stage) in CASES,'Only remaining eleven cases authorized')
    row=next(r for r in pre['cases'] if r['sew']==sew)
    chosen=[t for t in pre['targets'] if '.gen_lanes[0].' in t['scope'] and '.gen_num_lanes[0].' in t['scope']]
    require(len(chosen)==1,'Exact lane0/slot0 required');scope=chosen[0]['scope']
    format_name={16:'half',32:'single',64:'double'}[sew]
    guard=scope+'.'+('vfdsu_ex2_'+format_name if stage=='EX2' else 'vfdsu_dp_fdiv_busy')
    active=[t for t in pre['targets'] if int(re.search(r'gen_num_lanes\[([0-9]+)\]',t['scope'])[1])<64//sew]
    require(len(active)==row['active_cores'],'Precision active-controller set differs')
    ara='ara_tb.dut.i_ara_soc.i_system.i_ara'
    objects=['ara_tb.clk','ara_tb.rst_n',ara+'.axi_req_o',ara+'.axi_resp_i',chosen[0]['state_signal'],guard,
             scope+'.vfdsu_ex2_'+format_name]
    objects=list(dict.fromkeys(objects+[t['state_signal'] for t in active]))
    return dict(ext_target=chosen[0]['state_signal'],ext_value=STAGES[stage][0],ext_guard=guard,ext_dump_objects=objects),row,active


def text(c):
    require(all(re.fullmatch(r'ara_tb(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[[0-9]+\])*)+',p) for p in c['ext_dump_objects'])
            and c['ext_target'] in c['ext_dump_objects'] and c['ext_guard'] in c['ext_dump_objects'], 'Unsafe selection')
    return 'set ext_target {%s}\nset ext_value %d\nset ext_guard {%s}\nset ext_dump_objects {%s}\n'%(
        c['ext_target'],c['ext_value'],c['ext_guard'],' '.join(c['ext_dump_objects']))


def command(out,row,entry,stage):
    name='vfpu_reset_sew%d_%s'%(row['sew'],stage.lower())
    return [str(life.IMAGE),'-l','run.vcs.log','+NO_FSDB','+ntb_random_seed=1','+PRELOAD='+row['ELF'],
        '+TESTCASE='+name,'+COMMIT_TOHOST=80001000','+COMMIT_TRACE='+str(out/'commit_trace.csv'),
        '+VECTOR_TRACE='+str(out/'vector_trace.csv'),'-cm','line+cond+fsm+tgl+branch','-cm_dir',str(out/'code.vdb'),
        '-cm_name',name,'+ARA_UVM_TRACE_LIMIT=100000','+ARA_CONTRACT_TRACE_LIMIT=100000','-ucli','-do',str(entry)]


def prepare():
    require(not PLAN.exists(),'Fresh matrix plan only')
    pre=life.read_bound(PRE/'preflight.json',PRE_SHA)
    require(pre['status']=='THREE_SPIKE679_PASS_NATIVE_RESET_NOT_EXECUTED' and pre['stages']=={s:list(v) for s,v in STAGES.items()},
            'Exact frozen stage semantics required')
    image=life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(image['simv']==str(life.IMAGE) and len(image['image'])==66,'Frozen66 image required')
    baseline=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    bits=life.read_bound(BASE/'combined-bits.json',baseline['output_pins'][str(BASE/'combined-bits.json')])
    require(len(bits['tests'])==len(set(bits['tests']))==746,'Formal746 required')
    pins=life.merge_pins(pre['pins'],image['image'])
    pins=life.merge_pins(pins,{str(PRE/'preflight.json'):PRE_SHA,str(life.PLAN):life.PLAN_SEAL,str(BASE/'admission-manifest.json'):BASE_SHA,
        str(BASE/'combined-bits.json'):baseline['output_pins'][str(BASE/'combined-bits.json')],str(shared.focused.DOC):shared.focused.DOC_SHA,
        str(shared.focused.CONVERTER):shared.focused.CONVERTER_SHA})
    for p in (shared.DRIVER,shared.DRIVER_TEST,Path(__file__).resolve(),Path(__file__).with_name('test_run_fpu_external_reset_matrix.py'),
              Path(life.__file__).resolve(),Path(shared.__file__).resolve()):
        pins=life.merge_pins(pins,{str(p):life.digest(p)})
    life.check(pins);records=[]
    for sew,stage in CASES:
        c,row,active=select(pre,sew,stage)
        require(pins.get(row['ELF'])==row['ELF_sha256'] and Path(row['ELF']).is_file(),'Frozen case ELF differs')
        out=life.OUT/('fpu-external-reset-sew%d-%s-old-image-746-agent-20261007-01'%(sew,stage.lower()))
        require(not out.exists(),'No existing case output')
        selection=out.with_name(out.name+'.selection.tcl');entry=out.with_name(out.name+'.entry.tcl')
        with selection.open('x') as f:f.write(text(c))
        with entry.open('x') as f:f.write('if {[file exists external-reset-selection.tcl]} {error "Existing selection"}\n'+
            'file copy {'+str(selection)+'} external-reset-selection.tcl\nsource {'+str(shared.DRIVER)+'}\n')
        local=life.merge_pins(pins,{str(p):life.digest(p) for p in (selection,entry)})
        records.append(dict(output=str(out),case='sew%d_%s'%(sew,stage),sew=sew,stage=stage,selection=c,preflight_case=row,
            command=command(out,row,entry,stage),pins=local,timeout_s=600,selection_sha256=life.digest(selection),
            reset_cycles=4,reset_pin='ara_tb.rst_n',wave_byte_limit=64*1024*1024,coverage_admitted=False,uvm_check_report_pass=False,
            targets=[dict(t,baseline_hit=bool(int(bits['metrics']['fsm'][t['scope']]['bits'],16)&(1<<(16-STAGES[stage][1])))) for t in active]))
    life.save(PLAN,dict(schema='FPU_SHARED_EXTERNAL_RESET_REMAINING11_V1',cases=records,max_parallel=8,
        baseline=str(BASE),baseline_seal=BASE_SHA,preflight_seal=PRE_SHA,pins=pins,qualification_required=True,coverage_admitted=False))
    print('PREPARED11 '+life.digest(PLAN),flush=True)


def one(record,seal):
    out=Path(record['output']);require(not out.exists(),'No retry/overwrite')
    record=dict(record,pins=life.merge_pins(record['pins'],{str(PLAN):seal}))
    print('START '+record['case']+' '+str(out),flush=True)
    try:
        life.run(out,record)
        require(life.digest(out/'external-reset-selection.tcl')==record['selection_sha256'],'Executed selection differs')
        wave=out/'external-reset.vpd';require(wave.is_file() and 0<wave.stat().st_size<=record['wave_byte_limit'],'Focused wave limit')
        lines=[line for line in (out/'console.log').read_text().splitlines() if line.startswith('EXT_RESET_')]
        expected=['EXT_RESET_READY %s %d'%(record['selection']['ext_target'],record['selection']['ext_value']),
            'EXT_RESET_TARGET %s %d'%(record['selection']['ext_target'],record['selection']['ext_value']), 'EXT_RESET_ASSERT',
            *['EXT_RESET_LOW_EDGE %d'%i for i in range(1,5)],'EXT_RESET_RELEASE','EXT_RESET_DONE']
        require(lines==expected,'Exact executed stage/reset markers differ')
        life.save(out/'reset-capture.json',dict(status='TERMINAL_STAGE_RESET_CAPTURE_NOT_QUALIFIED',markers=lines,
            wave_sha256=life.digest(wave),coverage_admitted=False,uvm_check_report_pass=False))
        result=dict(case=record['case'],status='TERMINAL_CAPTURE_PENDING_ARCHITECTURE_QUALIFICATION',output=str(out))
    except Exception as exc:
        result=dict(case=record['case'],status='FAILED_NOT_ADMITTED',reason=str(exc),output=str(out))
        if out.exists():life.save(out/'reset-capture-failure.json',result)
    print('TERMINAL '+str(result),flush=True)
    return result


def run(seal):
    plan=life.read_bound(PLAN,seal)
    require(plan['schema']=='FPU_SHARED_EXTERNAL_RESET_REMAINING11_V1' and plan['max_parallel']==8 and
            [(r['sew'],r['stage']) for r in plan['cases']]==CASES and len(CASES)==11,'Exact bounded matrix contract required')
    life.check(plan['pins'])
    require(all(not Path(r['output']).exists() for r in plan['cases']),'No matrix retry')
    results=[]
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures=[pool.submit(one,r,seal) for r in plan['cases']]
        for f in as_completed(futures):results.append(f.result())
    life.check(plan['pins'])
    life.save(PLAN.with_name(PLAN.name+'.terminal.json'),dict(schema=plan['schema'],plan_seal=seal,cases=results,
        max_parallel=8,coverage_admitted=False,architecture_qualification_pending=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepare',action='store_true');p.add_argument('--run-seal')
    a=p.parse_args();require(bool(a.prepare)!=bool(a.run_seal),'Prepare or one matrix run')
    if a.prepare:prepare()
    else:run(a.run_seal)
