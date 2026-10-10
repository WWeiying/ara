#!/usr/bin/env python3
"""Sealed gap70 evidence hook. Never change checked.SCRIPT or launch a batch."""
from pathlib import Path

import audit_gap70_indexed as audit
import coverage_evidence as evidence
import run_checked_extension as checked

SCRIPT = Path(__file__).resolve()
ROOT = evidence.full.ROOT
NAME = audit.NAME
require = evidence.require
_installed = False


def require_exact_replay(result, files, saved):
    require(saved.get('status')=='PASS' and saved.get('read_only_validation') is True,
            'sealed preflight not checked PASS')
    require(result==saved.get('result'), 'sealed result differs')
    require(files and files==saved.get('checked_files'), 'sealed checked_files differs')


def sealed_precheck(item, proof, delegate):
    record = Path(item['precheck']['record']).absolute()
    directory = record.parent
    require(directory.parent==ROOT/'verification/out' and
            directory.name.startswith('gap70-indexed-preflight-') and
            record.name=='spike_results.json', 'unexpected gap70 evidence location')
    draft_path = directory/'selection.checked-draft.json'
    seals = proof.read(directory/'draft.sha256.json')
    require(set(seals)=={str(draft_path),str(directory/'checked-precheck.json'),
                        str(directory/'artifact_hashes.json')}, 'wrong seal set')
    proof.hashes(seals)
    saved, draft = proof.read(directory/'checked-precheck.json'), proof.read(draft_path)
    require(len(draft['cases'])==1 and item==draft['cases'][0] and item['name']==NAME and
            item['timeout_s']==300, 'parent must preserve exact sealed 300s case')
    replay = evidence.Evidence(); replay.pin(draft_path)
    for n in ('tool_hashes.json','link-inputs.json','protected-inputs.json','artifact_hashes.json'):
        replay.hashes(evidence.full.read(directory/n))
    result = delegate(item,replay)
    require_exact_replay(result,replay.files,saved)
    current = delegate(item,proof)
    require(current==result, 'selected precheck differs')
    proof.hashes(saved['checked_files'])
    rows = proof.read(record)
    require(len(rows)==1, 'wrong result set')
    row, execution = rows[0], proof.read(directory/'execution-proof.json')
    require(row['test']==NAME and row['status']=='PASS' and row['returncode']==0 and
            row['checks']==audit.CHECKS, 'wrong Spike PASS')
    command = audit.expected_command(execution['spike_tool'],row['spike_binary'])
    require(row['command']==command, 'wrong exact PMP0/MSU trace command')
    proof.pin(command[0],row['spike_tool_sha256'])
    require(row['binary']==item['binary'] and row['binary_sha256']==item['binary_sha256'], 'DUT ELF differs')
    for label,key,digest in (('dut','binary','binary_sha256'),('spike','spike_binary','spike_sha256')):
        require(execution[label]['elf']==row[key] and execution[label]['elf_sha256']==row[digest],
                'ELF binding differs')
        obj = proof.read(directory/(label+'.metadata.log'))[0]
        observed = audit.metadata(obj,proof.pin(row[key],row[digest]).read_bytes())
        require(observed==execution[label]['metadata'], 'ELF opcode/layout audit differs')
    require(audit.payload_identity(execution['dut']['metadata'])==
            audit.payload_identity(execution['spike']['metadata']), 'S/handler instruction identity differs')
    source = str(ROOT/'apps/riscv-tests/isa/rv64uv'/(NAME.split(':')[1]+'.c'))
    audit.check_log(proof.pin(row['log'],row['log_sha256']).read_text(),source)
    trace = audit.trace_check(proof.pin(row['trace_log'],row['trace_sha256']).read_text(),
                              execution['spike']['metadata'])
    require(trace==execution['trace'] and row['retired']==trace['retired'], 'trace proof differs')
    require(execution['checks']==audit.CHECKS and execution['retired_limit']==35000 and
            execution['vcs_timeout_s']==300 and execution['vcs_launched'] is False, 'count/budget/scope differs')
    config = proof.read(directory/'config-audit.json')
    require(config['status']=='PASS' and config['pmp_regions']==0, 'wrong PMP configuration')
    audit.validate_pmp_dts(proof.pin(config['dts_log'],config['dts_sha256']).read_text())
    commands = proof.read(directory/'commands.json')
    for cmd,stdout,stderr,seconds in (
        (command,row['log'],row['trace_log'],row['seconds']),
        ([command[0],command[1],'--priv=msu','--pmpregions=0','--dump-dts',command[-1]],
         config['dts_log'],None,None)):
        runs = [r for r in commands if r['command']==cmd]
        require(len(runs)==1 and runs[0]['status']=='PASS' and runs[0]['returncode']==0 and
                runs[0]['stdout']==stdout and (stderr is None or runs[0]['stderr']==stderr) and
                (seconds is None or runs[0]['seconds']==seconds), 'execution record differs')
        proof.hashes(runs[0]['log_hashes'])
    baseline = proof.read(directory/'baseline-targets.json')
    require(baseline['passed']==651 and baseline['status']=='PASS' and
            draft['baseline']==baseline['baseline'], 'wrong recovered651 baseline')
    for p in (SCRIPT,Path(audit.__file__),Path(checked.__file__),Path(evidence.__file__)):
        proof.pin(p)
    return current


def install_hooks():
    global _installed
    if _installed: return
    delegate = evidence.precheck

    def chained(item,proof):
        return sealed_precheck(item,proof,delegate) if item.get('name')==NAME else delegate(item,proof)

    evidence.precheck = chained
    _installed = True
