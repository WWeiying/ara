#!/usr/bin/env python3
"""Gap69 sealed evidence hook. No simulation launch and no checked.SCRIPT changes."""
import argparse
import json
from pathlib import Path

import audit_gap69_vf as audit
import coverage_evidence as evidence

SCRIPT = Path(__file__).resolve()
ROOT = evidence.full.ROOT
_hooks = None


def sealed_precheck(item, proof, delegate):
    directory = Path(item['precheck']['record']).resolve().parent
    audit.require(directory.parent == ROOT/'verification/out' and
                  directory.name.startswith('gap69-vf-preflight-') and item['timeout_s'] == 300,
                  'wrong evidence directory or budget')
    seal = proof.read(directory/'draft.sha256.json')
    audit.require(set(seal) == {str(directory/n) for n in
                  ('selection.checked-draft.json','checked-precheck.json','artifact_hashes.json')}, 'wrong seal set')
    proof.hashes(seal)
    saved = proof.read(directory/'checked-precheck.json')
    audit.require(saved['status'] == 'PASS' and saved['read_only_validation'] and
                  saved['vcs_launched'] is False, 'not checked immutable Spike-only evidence')
    proof.hashes(saved['checked_files'])
    artifacts = proof.read(directory/'artifact_hashes.json')
    proof.hashes(artifacts)
    original = proof.read(directory/'selection.checked-draft.json')['cases']
    audit.require(original == [item], 'sealed case changed; compose baseline outside the original case')
    for filename in ('tool_hashes.json','link-inputs.json','source_hashes.json','protected-inputs.json'):
        proof.hashes(proof.read(directory/filename))
    replay = evidence.Evidence()
    replay.pin(directory/'selection.checked-draft.json')
    for filename in ('tool_hashes.json','link-inputs.json','protected-inputs.json','artifact_hashes.json'):
        replay.hashes(evidence.full.read(directory/filename))
    result = delegate(item, replay)
    audit.require(result == saved['result'] and replay.files == saved['checked_files'],
                  'exact standard result/file-set replay differs')
    audit.require(delegate(item,proof) == result, 'selected standard precheck differs')
    record = proof.read(item['precheck']['record'])
    audit.require(len(record) == 1, 'not exactly one Spike record')
    record = record[0]
    audit.require(record['checks'] == audit.CHECKS and record['vcs_launched'] is False, 'record scope differs')
    log = proof.pin(record['log'],record['log_sha256']).read_text()
    trace = proof.pin(record['trace_log'],record['trace_sha256']).read_text()
    source = next(p for p in item['sources'] if Path(p).name == audit.NAME.split(':')[1]+'.c')
    audit.check_log(log,source)
    execution = proof.read(directory/'execution-proof.json')
    for name, key in (('dut','binary'),('spike','spike_binary')):
        elf = proof.pin(record[key],record[key+'_sha256'] if key == 'binary' else record['spike_sha256'])
        obj = json.loads(proof.pin(directory/(name+'.metadata.log')).read_text())[0]
        checked = audit.metadata(obj,elf.read_bytes())
        audit.require(checked == execution[name]['metadata'], 'independent ELF replay differs')
    replay = audit.trace_check(trace,execution['spike']['metadata'])
    audit.require(execution['trace'] == replay and execution['vcs_timeout_s'] <= 300 and
                  execution['vcs_launched'] is False, 'trace/timeout replay differs')
    audit.require(result == saved['result'], 'standard precheck replay differs')
    commands = proof.read(directory/'commands.json')
    runs = [r for r in commands if r['command'] == record['command']]
    audit.require(len(runs) == 1 and runs[0]['status'] == 'PASS' and runs[0]['returncode'] == 0 and
                  runs[0]['stdout'] == record['log'] and runs[0]['stderr'] == record['trace_log'] and
                  runs[0]['seconds'] == record['seconds'], 'Spike producer execution differs')
    proof.hashes(runs[0]['log_hashes'])
    return result


def install_hooks():
    """Chain only evidence hooks; never modify checked.SCRIPT or any runner."""
    global _hooks
    if _hooks is None:
        delegate = evidence.precheck
        prior_row = evidence.Evidence.baseline_row

        def chained(item, proof):
            return sealed_precheck(item,proof,delegate) if item.get('name') == audit.NAME else delegate(item,proof)

        chained.delegate = delegate

        def baseline_row(proof,row,image,simv):
            result = prior_row(proof,row,image,simv)
            if row.get('name') == audit.NAME.split(':')[1]:
                target = next(p for p in Path(row['vdb']).parents if p.parent.name == 'results' and p.name == row['name'])
                plan = proof.plan(target.parent.parent)
                runtime_proof(target.parent.parent,plan,row,proof)
            return result

        evidence.precheck = chained
        evidence.Evidence.baseline_row = baseline_row
        _hooks = dict(precheck=chained,baseline_row=baseline_row)
    return _hooks


def runtime_proof(output, plan, row, proof=None):
    """Parent worker/aggregation entrypoint. Missing any bound runtime input rejects."""
    proof = proof or evidence.Evidence()
    target = Path(output)/'results'/audit.NAME.split(':')[1]
    summary_path = target/'summary.json'
    audit.require(str(summary_path) in row['files'], 'unbound runtime summary')
    summary = proof.read(proof.pin(summary_path,row['files'][str(summary_path)]))
    audit.require(len(summary) == 1 and summary[0]['name'] == audit.NAME, 'wrong runtime case')
    artifact = Path(summary[0]['artifact_dir']).resolve(strict=True)
    audit.require(artifact.is_relative_to(target.resolve()), 'foreign runtime artifact')
    paths = dict(stdout=artifact/'work/run.vcs.log',vector=artifact/'work/vector_trace.csv',
                 commit=artifact/'commit_trace.csv',elf=artifact/'input.elf')
    for path in paths.values():
        audit.require(str(path) in row['files'], 'unbound/missing gap69 runtime evidence: '+str(path))
        proof.pin(path,row['files'][str(path)])
    case = next(c for c in plan['cases'] if c['source_name'] == audit.NAME)
    proof.pin(paths['elf'],case['elf_sha256'])
    selection = proof.read(plan['source_selection']['selection'])
    item = next(c for c in selection['cases'] if c['name'] == audit.NAME)
    install_hooks()
    sealed_precheck(item,proof,_hooks['precheck'].delegate)
    directory = Path(item['precheck']['record']).parent
    execution = proof.read(directory/'execution-proof.json')
    source = str(ROOT/'apps/riscv-tests/isa/rv64uv/vgap69_vf_odd_vd.c')
    stdout = audit.vcs_stdout(paths['stdout'].read_text(),source)
    vector = audit.vcs_vector(paths['vector'].read_text(),paths['commit'].read_text(),execution['dut']['metadata'])
    return dict(status='PASS',schema='gap69-vf-stdout-vector-trap-v1',stdout=stdout,vector=vector,
                files={str(p):proof.files[str(p)] for p in paths.values()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selection',required=True,type=Path)
    args = parser.parse_args()
    install_hooks()
    proof = evidence.Evidence()
    selected = proof.read(args.selection)
    results = [evidence.precheck(item,proof) for item in selected['cases']]
    print(json.dumps(dict(status='PASS',results=results,checked_files=len(proof.files),
                          read_only=True,vcs_launched=False),indent=2))


if __name__ == '__main__': main()
