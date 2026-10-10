#!/usr/bin/env python3
"""Exact gap68 sealed precheck hook; other cases delegate without changes."""
from pathlib import Path
import audit_gap68_system as audit
import coverage_evidence as evidence
import run_checked_extension as checked

SCRIPT=Path(__file__).resolve()
ROOT=evidence.full.ROOT
NAME=audit.NAME
require=evidence.require
_installed=False

def require_exact_replay(result,files,saved):
    require(saved.get('status')=='PASS' and saved.get('read_only_validation') is True,'not checked PASS')
    require(result==saved.get('result') and files and files==saved.get('checked_files'),'sealed precheck replay differs')

def sealed_precheck(item,proof,delegate):
    record=Path(item['precheck']['record']).absolute(); directory=record.parent
    require(directory.parent==ROOT/'verification/out' and directory.name.startswith('gap68-system-preflight-')
        and record.name=='spike_results.json','foreign gap68 evidence')
    draft_path=directory/'selection.checked-draft.json'
    seals=proof.read(directory/'draft.sha256.json')
    require(set(seals)=={str(draft_path),str(directory/'checked-precheck.json'),str(directory/'artifact_hashes.json')},'wrong seal set')
    proof.hashes(seals); draft=proof.read(draft_path); saved=proof.read(directory/'checked-precheck.json')
    require(draft['cases']==[item] and item['name']==NAME and item['timeout_s']==300,'parent changed sealed case')
    require(draft['status']=='CHECKED_DRAFT_SPIKE_ONLY_NOT_SUBMITTED' and draft['vcs_launched'] is False and
        draft['full_admission_deferred'] is True,'wrong preparation scope')
    replay=evidence.Evidence(); replay.pin(draft_path)
    for name in ('tool_hashes.json','link-inputs.json','protected-inputs.json','artifact_hashes.json'):
        replay.hashes(evidence.full.read(directory/name))
    result=delegate(item,replay); require_exact_replay(result,replay.files,saved)
    current=delegate(item,proof); require(current==result,'selected result differs'); proof.hashes(saved['checked_files'])
    execution=proof.read(directory/'execution-proof.json'); rows=proof.read(record)
    require(len(rows)==1,'wrong result set'); row=rows[0]
    require(row['test']==NAME and row['status']=='PASS' and row['returncode']==0 and
        row['checks']==audit.CHECKS and row['retired']==execution['trace']['retired'],'wrong Spike PASS')
    require(row['command']==audit.expected_command(execution['spike_tool'],row['spike_binary']),'wrong exact Spike command')
    require(row['binary']==item['binary'] and row['binary_sha256']==item['binary_sha256'],'ELF selection differs')
    for label,key,digest in (('dut','binary','binary_sha256'),('spike','spike_binary','spike_sha256')):
        require(execution[label]['elf']==row[key] and execution[label]['elf_sha256']==row[digest],'ELF binding differs')
        obj=proof.read(directory/(label+'.metadata.log'))[0]
        observed=audit.metadata(obj,proof.pin(row[key],row[digest]).read_bytes())
        require(observed==execution[label]['metadata'],'linked instruction/layout proof differs')
    require(execution['dut']['metadata']['payload_sha256']==execution['spike']['metadata']['payload_sha256'],'probe bytes differ')
    source=str(ROOT/'apps/riscv-tests/isa/rv64uv'/(NAME.split(':')[1]+'.c'))
    require(proof.pin(directory/'source.snapshot').read_bytes()==proof.pin(source).read_bytes(),'source snapshot differs')
    audit.check_log(proof.pin(row['log'],row['log_sha256']).read_text(),source)
    observed=audit.trace_check(proof.pin(row['trace_log'],row['trace_sha256']).read_text(),execution['spike']['metadata'])
    require(observed==execution['trace'] and execution['checks']==audit.CHECKS and execution['retired_limit']==35000
        and execution['vcs_timeout_s']==300 and execution['vcs_launched'] is False,'execution/count/budget differs')
    config=proof.read(directory/'config-audit.json')
    require(config['status']=='PASS' and config['pmp_regions']==0 and config['automatic_ad_updates'] is False
        and config['actual_execution']=='M' and sum(config['count_parts'].values())==audit.CHECKS,'wrong configuration')
    audit.validate_pmp_dts(proof.pin(config['dts_log'],config['dts_sha256']).read_text())
    commands=proof.read(directory/'commands.json'); runs=[r for r in commands if r['command']==row['command']]
    require(len(runs)==1 and runs[0]['status']=='PASS' and runs[0]['returncode']==0 and
        runs[0]['stdout']==row['log'] and runs[0]['stderr']==row['trace_log'] and runs[0]['seconds']==row['seconds'],
        'wrong Spike execution record'); proof.hashes(runs[0]['log_hashes'])
    require(all(r['status']=='PASS' and r['returncode']==0 for r in commands),'failed preparation command')
    for label in ('unit-tests','real-trace-unit-tests'):
        matching=[r for r in commands if r['stdout']==str(directory/(label+'.log'))]
        require(len(matching)==1 and matching[0]['command'][2]==str(ROOT/'verification/tests/test_gap68_system.py'),
                'missing unit test execution'); proof.hashes(matching[0]['log_hashes'])
    baseline=proof.read(directory/'baseline-targets.json')
    require(baseline['passed']==650 and baseline['coverage_status']=='COMPLETE' and
        baseline['status']=='PASS_LIGHTWEIGHT_PREPARATION_ONLY' and baseline['baseline']==draft['baseline'] and
        baseline['image_bytes_rehashed'] is False and baseline['full_admission_deferred'] is True,'baseline scope differs')
    for path in (SCRIPT,Path(audit.__file__),Path(checked.__file__),Path(evidence.__file__)): proof.pin(path)
    return current

def install_hooks():
    global _installed
    if _installed: return
    delegate=evidence.precheck
    def chained(item,proof):
        return sealed_precheck(item,proof,delegate) if item.get('name')==NAME else delegate(item,proof)
    evidence.precheck=chained
    _installed=True

def main():
    install_hooks(); return checked.main()

if __name__=='__main__': raise SystemExit(main())
