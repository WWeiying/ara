"""Composable exact gap71 app admission and independent runtime adapter."""
from pathlib import Path
import sys
sys.dont_write_bytecode=True
import audit_gap71_custom as audit
import coverage_evidence as evidence
import run_checked_extension as checked
SCRIPT=Path(__file__).resolve()
ROOT=evidence.full.ROOT
_RAW_CASE_NAMES=audit.CASE_NAMES
CASE_NAMES=['app:'+n for n in _RAW_CASE_NAMES]
require=evidence.require
_hooks=None

def sealed_precheck(item,proof,delegate):
    record=Path(item['precheck']['record']);out=record.parent;name=item['name'].removeprefix('app:')
    require(name in _RAW_CASE_NAMES and out.parent==ROOT/'verification/out' and out.name.startswith('gap71-custom-preflight-') and record.name==name+'.precheck.json','foreign evidence')
    draft_path=out/'selection.checked-draft.json';seals=proof.read(out/'draft.sha256.json')
    require(set(seals)=={str(draft_path),str(out/'checked-precheck.json'),str(out/'artifact_hashes.json')},'seal set differs');proof.hashes(seals)
    draft=proof.read(draft_path);cases=[c for c in draft['cases'] if c['name']==item['name']]
    require(cases==[item] and type(item['timeout_s']) is int and item['timeout_s'] in (300,1800) and draft['vcs_launched'] is False and draft['full_admission_deferred'] is True and draft['baseline']==str(ROOT/'verification/out/closure90-current-20261005-01'),'exact sealed case/base/budget differs')
    require(len({c['name'] for c in draft['cases']})==len(draft['cases']) and all(c['name'] in CASE_NAMES for c in draft['cases']),'draft case identity differs')
    saved=proof.read(out/'checked-precheck.json')[item['name']]
    replay=evidence.Evidence();replay.pin(draft_path)
    for label in ('tool_hashes.json','link-inputs.json','protected-inputs.json','artifact_hashes.json'):replay.hashes(evidence.full.read(out/label))
    result=delegate(item,replay)
    require(saved['status']=='PASS' and result==saved['result'] and replay.files==saved['checked_files'] and bool(replay.files),'sealed exact replay differs')
    current=delegate(item,proof);require(current==result,'native admission result differs');proof.hashes(saved['checked_files'])
    run=proof.read(out/'execution-proof.json')[name]
    require(run['status']=='PASS' and run['custom_instruction_execution_prechecked'] is False and run['vcs_launched'] is False and run['vcs_timeout_s']==item['timeout_s'],'wrong proof scope')
    require(run['dut']['elf']==item['binary'] and run['dut']['elf_sha256']==item['binary_sha256'],'selected ELF differs')
    for kind,soft in (('dut',False),('spike',True)):
        obj=proof.read(out/(name+'.'+kind+'.metadata.log'))[0]
        blob=proof.pin(run[kind]['elf'],run[kind]['elf_sha256']).read_bytes()
        require(audit.metadata(obj,blob,name,soft)==run[kind]['metadata'],'linked source/ELF metadata differs')
    src=ROOT/'apps'/name/'main.c'
    require(proof.pin(out/(name+'.source.snapshot')).read_bytes()==proof.pin(src).read_bytes(),'source snapshot differs')
    require(audit.validate_log(proof.pin(run['stdout']).read_text(),name,'software-reference')==run['uart'],'software stdout differs')
    require(audit.spike_trace(proof.pin(run['trace_log']).read_text(),name,run['spike']['metadata'])==run['trace'],'software trace differs')
    command=run['command'];require(command[1:]==['--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu','--pmpregions=0','-l','--log-commits',run['spike']['elf']],'Spike command differs')
    tools=proof.read(out/'tool_hashes.json');proof.pin(command[0],tools[command[0]])
    commands=proof.read(out/'commands.json');matching=[c for c in commands if c['command']==command]
    require(len(matching)==1 and matching[0]['stdout']==run['stdout'] and matching[0]['stderr']==run['trace_log'],'actual Spike invocation differs')
    require(all(c['status']=='PASS' and c['returncode']==0 for c in commands),'failed prep command');proof.hashes(matching[0]['log_hashes'])
    require(any(c['command'][2:3]==[str(ROOT/'verification/tests/test_gap71_custom.py')] and '--preflight' in c['command'] for c in commands),'missing real-trace unit tests')
    baseline=proof.read(out/'baseline-targets.json');require(baseline['passed']==654 and baseline['coverage_status']=='COMPLETE' and baseline['image_bytes_rehashed'] is False and len(baseline['targets'])==22,'baseline/targets differ')
    proof.hashes(baseline['checked_files'])
    for p in (SCRIPT,Path(audit.__file__),Path(checked.__file__),Path(evidence.__file__)):proof.pin(p)
    return current

def runtime_proof(output,plan,row,proof=None):
    """Parent calls this only for genuine, non-reused PASS; never launches tools."""
    proof=proof if proof is not None else evidence.Evidence()
    full=checked.full;name=row['name'];require(name in _RAW_CASE_NAMES,'foreign runtime case')
    require(plan.get('checked_extension')==checked.VERSION,'checked plan required')
    cases=[c for c in plan['cases'] if c['name']==name and c['source_name']=='app:'+name];require(len(cases)==1,'runtime identity differs');case=cases[0]
    require(row.get('status')=='PASS' and row.get('returncode')==0 and row.get('passed_only') is True and row.get('vdb_valid') is True and row.get('reused') is False and row.get('kind')==case['kind']=='directed','real fresh PASS required')
    require(row['contract']==case['contract']==full.contract(case),'runtime contract differs')
    # The parent's proof already contains runtime bytes, which are not plan inputs.
    preflight=evidence.Evidence()
    selection=Path(plan['source_selection']['selection']);preflight.pin(selection,plan['files'][str(selection)])
    items=[i for i in preflight.read(selection)['cases'] if i['name']=='app:'+name];require(len(items)==1,'selection differs')
    admitted=evidence.precheck(items[0],preflight)
    require(all(plan['files'].get(p)==h for p,h in preflight.files.items()),'preflight inputs not frozen')
    proof.hashes(preflight.files)
    directory=Path(items[0]['precheck']['record']).parent
    run=proof.read(directory/'execution-proof.json')[name];info=run['dut']['metadata']
    require(plan['design_vdb']==proof.read(directory/'baseline-targets.json')['design_vdb'],'design differs')
    require(row['elf_sha256']==case['elf_sha256']==admitted['elf_sha256'],'runtime ELF differs')
    proof.pin(case['frozen_elf'],admitted['elf_sha256'])
    target=Path(output).resolve(strict=True)/'results'/name
    def bound(path):
        require(str(path) in row['files'],'unbound runtime artifact: '+str(path));return proof.pin(path,row['files'][str(path)])
    summary=proof.read(bound(target/'summary.json'));require(len(summary)==1 and summary[0]['name']=='app:'+name and full.batch.classify(summary[0],row['returncode'])=='PASS','summary differs')
    artifact=Path(summary[0]['artifact_dir']).resolve(strict=True);require(artifact==target/'tests'/('app_'+name),'foreign artifact')
    work=artifact/'work';require(Path(row['vdb']).resolve()==work/'code.vdb','foreign VDB')
    inputs=proof.read(bound(artifact/'inputs.json'));require(inputs['binary']['sha256']==admitted['elf_sha256'] and inputs['simv']['image_sha256']==plan['wrapper_image'],'input metadata differs')
    proof.pin(bound(artifact/'input.elf'),admitted['elf_sha256']);full.batch.audit_ok(proof.read(bound(target/'independent_audit.json')),case,artifact)
    original=proof.read(bound(artifact/'command.json'));launch=proof.read(bound(work/'gap71-command.json'));actual=proof.read(bound(work/'coverage.command.json'))
    require(launch==dict(command=perf_command(original['command'],name,work),cwd=str(work),timeout_s=case['timeout_s']),'launch differs')
    require(actual==dict(command=[plan['simv'],*launch['command'][1:],'-cm','line+cond+fsm+tgl+branch','-cm_dir',str(work/'code.vdb'),'-cm_name',name],cwd=str(work)) and original['command'][0]==plan['wrapper'],'real simulator/tools differ')
    trace=bound(artifact/'commit_trace.csv');vector=bound(work/'vector_trace.csv')
    ts=proof.read(bound(artifact/'trace_summary.json'));require(ts.get('status')=='VALID' and ts.get('retire_count',0)>0,'invalid scalar trace')
    log=bound(work/'run.vcs.log').read_text();uart=audit.validate_log(log,name,'custom-dut')
    cycles=audit.runtime_traces(trace,vector,name,info)
    perf=audit.runtime_perf(log,name)
    files=runtime_files(proof,row,target)
    return dict(status='PASS',schema=audit.RUNTIME_SCHEMA,name='app:'+name,uart=uart,traces=cycles,perf=perf,
        elf_sha256=admitted['elf_sha256'],files=files,internal_target_hits_measured=False,
        scope='Actual custom request/response/retire + exact independent VRF bytes + ELF/source-bound full software checks; collector owns raw gain')

def runtime_files(proof,row,target):
    target=Path(target).resolve();vdb=Path(row['vdb']).resolve()
    return {p:h for p,h in proof.files.items() if
        (Path(p).resolve().is_relative_to(target) and row['files'].get(p)==h) or
        (Path(p).resolve().is_relative_to(vdb) and row.get('vdb_files',{}).get(p)==h)}

def perf_command(command,name,work):
    command=list(command);require(name in _RAW_CASE_NAMES and [x for x in command if x.startswith('+TESTCASE=')]==['+TESTCASE='+name] and command.count('+NO_FSDB')==1,'case/no-FSDB differs')
    perf='+AKV_PERF' if 'akv' in name else '+QBS_PERF'
    require(not any(x.startswith('+AKV_PERF') or x.startswith('+QBS_PERF') for x in command),'PERF override')
    vectors=[x for x in command if x.startswith('+VECTOR_TRACE=')]
    require(vectors in ([],['+VECTOR_TRACE='+str(work/'vector_trace.csv')]),'foreign vector trace')
    return command+[perf]+([] if vectors else ['+VECTOR_TRACE='+str(work/'vector_trace.csv')])

def install_hooks():
    global _hooks
    if _hooks is not None:return _hooks
    old=evidence.precheck;directed=checked.full.batch.directed
    def chained(item,proof):return sealed_precheck(item,proof,old) if item.get('name') in CASE_NAMES else old(item,proof)
    def with_trace(output,name):
        if name not in _RAW_CASE_NAMES:return directed(output,name)
        from ara_verify import runner
        import json
        plan=checked.full.read(Path(output)/'plan.json')
        budget=next(c['timeout_s'] for c in plan['cases'] if c['name']==name)
        original=runner._run_monitored
        def monitored(command,work,console,timeout,cancel):
            require(type(timeout) is int and timeout==budget and timeout in (300,1800),'gap71 sealed budget differs')
            actual=perf_command(command,name,work)
            with (work/'gap71-command.json').open('x') as stream:
                import json
                json.dump(dict(command=actual,cwd=str(work),timeout_s=timeout),stream,indent=2)
            return original(actual,work,console,timeout,cancel)
        runner._run_monitored=monitored
        try:return directed(output,name)
        finally:runner._run_monitored=original
    chained.delegate=old;with_trace.delegate=directed
    evidence.precheck=chained;checked.full.batch.directed=with_trace
    _hooks=dict(CASE_NAMES=CASE_NAMES,precheck=chained,directed=with_trace,runtime_proof=runtime_proof)
    return _hooks

def main():install_hooks();return checked.main()
if __name__=='__main__':raise SystemExit(main())
