#!/usr/bin/env python3
"""Gap73 sealed accel-host gate and independent actual-custom runtime contract."""
import argparse
import json
from pathlib import Path

import audit_gap73_akv as audit
import coverage_evidence as evidence

NAME = audit.NAME
CASE_NAMES = [audit.TEST]
_hooks = None


def sealed_precheck(item, proof, delegate):
    directory = Path(item['precheck']['record']).resolve().parent
    audit.require(directory.parent==audit.ROOT/'verification/out' and
                  directory.name.startswith('gap73-akv-preflight-') and
                  type(item['timeout_s']) is int and item['timeout_s'] in (300,1800),
                  'foreign output or unsupported sealed budget')
    seal = proof.read(directory/'draft.sha256.json')
    audit.require(set(seal)=={str(directory/n) for n in
                  ('selection.checked-draft.json','checked-precheck.json','artifact_hashes.json')},'seal set differs')
    proof.hashes(seal)
    draft = proof.read(directory/'selection.checked-draft.json')
    audit.require(draft['cases']==[item] and draft['vcs_launched'] is False,'sealed case changed')
    saved = proof.read(directory/'checked-precheck.json')
    audit.require(saved['status']=='PASS' and saved['vcs_launched'] is False and
                  saved['custom_instruction_execution_prechecked'] is False,'host cannot claim custom execution')
    proof.hashes(saved['checked_files'])
    artifacts = proof.read(directory/'artifact_hashes.json'); proof.hashes(artifacts)
    replay = evidence.Evidence(); replay.pin(directory/'selection.checked-draft.json')
    for name in ('tool_hashes.json','link-inputs.json','protected-inputs.json','artifact_hashes.json'):
        hashes = proof.read(directory/name); proof.hashes(hashes); replay.hashes(hashes)
    result = delegate(item,replay)
    audit.require(result==saved['result'] and replay.files==saved['checked_files'],'exact standard host replay differs')
    audit.require(delegate(item,proof)==result,'selected standard precheck differs')
    record = proof.read(item['precheck']['record'])
    audit.require(record['custom_instruction_execution_prechecked'] is False and
                  record['vcs_launched'] is False and record['host_result']==
                  'PASSED: '+audit.NAME+' checks=%d errors=0'%audit.HOST_CHECKS,'host result scope differs')
    execution = proof.read(directory/'execution-proof.json')
    host = audit.host_oracle(proof.pin(directory/'host-oracle.log').read_text())
    elf = audit.elf_audit(proof.pin(item['binary'],item['binary_sha256']).read_bytes())
    audit.require(execution['host']==host and execution['elf']==elf and execution['vcs_timeout_s']==item['timeout_s'] and
                  execution['custom_execution']=='PENDING_VCS' and execution['spike_custom_execution'] is False,
                  'independent oracle/ELF/scope differs')
    native = audit.native_targets(proof,proof.read(directory/'native-targets.json')['inventory'])
    audit.require(native==proof.read(directory/'native-targets.json'),'latest diagnostic target proof differs')
    commands = proof.read(directory/'commands.json')
    audit.require(commands and all(c['returncode']==0 and c['status']=='PASS' and 0<c['timeout_s']<=120
                                  for c in commands),'failed/unbounded preflight')
    for suffix,argv in (('host-results',[str(directory/'host')]),
                        ('host-oracle',[str(directory/'host'),'--oracle'])):
        producers = [c for c in commands if c['command']==argv]
        audit.require(len(producers)==1 and producers[0]['stdout']==str(directory/(suffix+'.log')),
                      'host producer missing/ambiguous')
        proof.hashes(producers[0]['log_hashes'])
    unit = proof.read(directory/'unit-results.json')
    audit.require(unit['status']=='PASS' and unit['fixture_scope']=='SYNTHETIC_NOT_DUT' and
                  unit['tests_run']>=15 and unit['c_mutations_rejected']==audit.NEGATIVES,'negative fixture gates missing')
    contract = proof.read(directory/'runtime-contract.json')
    audit.require(contract['schema']==audit.SCHEMA and contract['custom_execution_prechecked'] is False and
                  contract['vcs_timeout_s']==item['timeout_s'] and contract['checked_script_mutated'] is False,'custom contract differs')
    return result


def install_hooks():
    """Evidence hooks only; parent retains checked.SCRIPT and owns simulator scheduling."""
    global _hooks
    if _hooks is not None: return _hooks
    delegate,prior_row = evidence.precheck,evidence.Evidence.baseline_row
    def precheck(item, proof):
        return sealed_precheck(item,proof,delegate) if item.get('name')==audit.TEST else delegate(item,proof)
    def baseline_row(proof,row,image,simv):
        result = prior_row(proof,row,image,simv)
        if row.get('name')==audit.NAME:
            matches = [p for p in Path(row['vdb']).parents if p.parent.name=='results' and p.name==audit.NAME]
            audit.require(len(matches)==1,'ambiguous runtime producer')
            output = matches[0].parent.parent
            runtime_proof(output,proof.plan(output),row,proof)
        return result
    precheck.delegate,baseline_row.delegate = delegate,prior_row
    evidence.precheck,evidence.Evidence.baseline_row = precheck,baseline_row
    _hooks = dict(precheck=precheck,baseline_row=baseline_row,runtime_proof=runtime_proof)
    return _hooks


def runtime_proof(output, plan, row, proof=None):
    proof = proof or evidence.Evidence()
    audit.require(row['name']==audit.NAME and row['status']=='PASS' and row['returncode']==0 and
                  row['passed_only'] and row['vdb_valid'] and row['reused'] is False,'independent runner PASS required')
    cases = [c for c in plan['cases'] if c['source_name']==audit.TEST]
    audit.require(len(cases)==1 and type(cases[0]['timeout_s']) is int and
                  cases[0]['timeout_s'] in (300,1800),'wrong runtime case/budget')
    case = cases[0]
    audit.require(row['elf_sha256']==case['elf_sha256'] and row['contract']==case['contract']==evidence.full.contract(case),
                  'runtime ELF/contract differs')
    target = Path(output).resolve()/'results'/audit.NAME
    def bound(path):
        audit.require(str(path) in row['files'],'unbound runtime input: '+str(path))
        return proof.pin(path,row['files'][str(path)])
    summary = proof.read(bound(target/'summary.json'))
    audit.require(len(summary)==1 and summary[0]['name']==audit.TEST,'runtime summary differs')
    artifact = Path(summary[0]['artifact_dir']).resolve(strict=True)
    audit.require(artifact.is_relative_to(target),'foreign artifact')
    paths = dict(stdout=artifact/'work/run.vcs.log',vector=artifact/'work/vector_trace.csv',
                 commit=artifact/'commit_trace.csv',elf=artifact/'input.elf')
    for path in paths.values(): bound(path)
    proof.pin(paths['elf'],case['elf_sha256'])
    selection = proof.read(plan['source_selection']['selection'])
    items = [c for c in selection['cases'] if c['name']==audit.TEST]
    audit.require(len(items)==1,'runtime selected case differs')
    audit.require(items[0]['timeout_s']==case['timeout_s'],'runtime sealed budget differs')
    install_hooks(); sealed_precheck(items[0],proof,_hooks['precheck'].delegate)
    directory = Path(items[0]['precheck']['record']).parent
    targets = proof.read(directory/'native-targets.json')
    audit.require(plan['design_vdb']==targets['design_vdb'],'runtime design differs')
    launch = proof.read(bound(artifact/'work/coverage.command.json'))
    command = launch['command']
    vector_args = [v.split('=',1)[1] for v in command if v.startswith('+VECTOR_TRACE=')]
    audit.require(Path(launch['cwd']).resolve()==artifact/'work' and len(vector_args)==1 and
                  (Path(vector_args[0]) if Path(vector_args[0]).is_absolute() else
                   Path(launch['cwd'])/vector_args[0]).resolve()==paths['vector'],
                  'vector path must resolve to the bound file from actual simulator cwd')
    audit.require(command[0]==plan['simv'] and command.count('+AKV_PERF')==1 and command.count('+NO_FSDB')==1 and
                  [v for v in command if v.startswith('+TESTCASE=')]==['+TESTCASE='+audit.NAME],
                  'required bounded PERF/vector profile absent')
    info = audit.elf_audit(paths['elf'].read_bytes())
    stdout = audit.stdout_audit(paths['stdout'].read_text(),info)
    commit = audit.commit_audit(paths['commit'].read_text(),info)
    vector = audit.vector_audit(paths['vector'].read_text(),commit['commands'])
    audit.require(stdout['busy_cycles']<=commit['last_cycle'],'command cycles exceed trace')
    audit.require(stdout['perf'] and all(stdout['perf'][p]['id']==c['vid'] for p,c in enumerate(vector['custom_groups'])),
                  'PERF command IDs and independent backend VIDs differ')
    contract = re_contract(paths['stdout'].read_text())
    audit.require((commit['requests'],commit['responses'],commit['exceptions'])==contract,'stdout/trace conservation differs')
    from coverage_bitmap_delta import read_metric
    vdb = Path(row['vdb'])
    native = list(vdb.glob('snps/coverage/db/testdata/*/cond.verilog.data.xml'))
    audit.require(len(native)==1 and str(native[0]) in row['vdb_files'],'unbound native condition data')
    data = read_metric(proof.pin(native[0],row['vdb_files'][str(native[0])]))[audit.SCOPE]
    audit.require((data['width'],data['checksum'])==(targets['width'],targets['checksum']),'native condition shape differs')
    bits = format(int(data['bits'],16),'0%db'%data['width'])
    raw = [dict(raw_index=i,baseline=0,runtime=int(bits[i]),native_dve_qualified=False) for i in audit.RAW]
    return dict(status='PASS',schema=audit.SCHEMA,stdout=stdout,commit=commit,vector=vector,
                native_candidates=raw,raw_gain_claimed=False,native_dve_qualified=False,
                files={str(p):proof.files[str(p)] for p in [*paths.values(),native[0]]},
                scope='Actual custom contract passed independently; raw positions remain diagnostic pending native DVE qualification')


def re_contract(log):
    import re
    return tuple(map(int,re.findall(r'^\[ARA_CONTRACT\] requests=(\d+) responses=(\d+) exceptions=(\d+)',log,re.M)[0]))


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--selection',required=True,type=Path)
    args = parser.parse_args(); install_hooks(); proof = evidence.Evidence()
    results = [evidence.precheck(c,proof) for c in proof.read(args.selection)['cases']]
    print(json.dumps(dict(status='PASS',results=results,checked_files=len(proof.files),
                         read_only=True,vcs_launched=False,custom_execution_prechecked=False),indent=2))


if __name__=='__main__': main()
