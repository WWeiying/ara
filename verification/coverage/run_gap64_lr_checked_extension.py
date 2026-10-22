#!/usr/bin/env python3
"""Exact sealed gap64 hook; other cases and the parent checked runner delegate unchanged."""
from pathlib import Path

import audit_gap64_lr as audit
import coverage_evidence as evidence
import run_checked_extension as checked

SCRIPT = Path(__file__).resolve()
ROOT = evidence.full.ROOT
NAME = audit.NAME
require = evidence.require
_installed = False


def require_exact_replay(result, files, saved):
    require(saved.get('status') == 'PASS' and saved.get('read_only_validation') is True,
            'sealed preflight is not independently checked')
    require(result == saved.get('result'), 'sealed precheck result differs')
    require(files and files == saved.get('checked_files'), 'sealed checked_files differs')


def sealed_precheck(item, proof, delegate):
    record = Path(item['precheck']['record']).absolute()
    directory = record.parent
    require(directory.parent == ROOT / 'verification/out' and
            directory.name.startswith('gap64-lr-preflight-') and
            record.name == 'spike_results.json', 'unexpected gap64 evidence location')
    draft_path = directory / 'selection.checked-draft.json'
    seals = proof.read(directory / 'draft.sha256.json')
    require(set(seals) == {str(draft_path), str(directory / 'checked-precheck.json'),
                           str(directory / 'artifact_hashes.json')}, 'wrong seal set')
    proof.hashes(seals)
    saved, draft = proof.read(directory / 'checked-precheck.json'), proof.read(draft_path)
    require(len(draft['cases']) == 1 and item == draft['cases'][0] and item['name'] == NAME and
            item['timeout_s'] == 240, 'parent must preserve exact sealed 240s case')
    replay = evidence.Evidence()
    replay.pin(draft_path)
    for name in ('tool_hashes.json', 'link-inputs.json', 'protected-inputs.json', 'artifact_hashes.json'):
        replay.hashes(evidence.full.read(directory / name))
    result = delegate(draft['cases'][0], replay)
    require_exact_replay(result, replay.files, saved)
    current = delegate(item, proof)
    require(current == result, 'selected precheck result differs')
    proof.hashes(saved['checked_files'])

    execution = proof.read(directory / 'execution-proof.json')
    records = proof.read(record)
    require(len(records) == 1, 'unexpected Spike result set')
    row = records[0]
    require(row['test'] == NAME and row['status'] == 'PASS' and row['returncode'] == 0 and
            row['checks'] == audit.CHECKS, 'wrong Spike PASS')
    command = row['command']
    require(command == audit.expected_command(execution['spike_tool'], row['spike_binary']),
            'wrong PMP0/MSU/commit-log Spike command')
    proof.pin(command[0], row['spike_tool_sha256'])
    proof.pin(row['spike_binary'], row['spike_sha256'])
    proof.pin(row['binary'], row['binary_sha256'])
    require(row['binary'] == item['binary'] and row['binary_sha256'] == item['binary_sha256'],
            'selected DUT ELF differs')
    for label, key, digest in (('dut','binary','binary_sha256'), ('spike','spike_binary','spike_sha256')):
        require(execution[label]['elf'] == row[key] and execution[label]['elf_sha256'] == row[digest],
                'execution ELF binding differs')
        obj = proof.read(directory / (label + '.metadata.log'))[0]
        observed = audit.metadata(obj, proof.pin(row[key], row[digest]).read_bytes())
        require(observed == execution[label]['metadata'], 'ELF sites/layout proof differs')
    require(execution['dut']['metadata']['payload_sha256'] ==
            execution['spike']['metadata']['payload_sha256'], 'DUT/Spike LR instructions differ')
    source = str(ROOT / 'apps/riscv-tests/isa/rv64uv' / (NAME.split(':')[1]+'.c'))
    audit.check_log(proof.pin(row['log'], row['log_sha256']).read_text(), source)
    observed = audit.trace_check(proof.pin(row['trace_log'], row['trace_sha256']).read_text(),
                                 execution['spike']['metadata'])
    require(observed == execution['trace'], 'independent execution/retirement proof differs')
    require(execution['checks'] == audit.CHECKS and execution['vcs_timeout_s'] == 240 and
            execution['vcs_launched'] is False, 'scope/count/budget differs')
    config = proof.read(directory / 'config-audit.json')
    require(config['pmp_regions'] == 0 and config['lr_only'] is True and config['status'] == 'PASS',
            'wrong frozen configuration')
    audit.validate_pmp_dts(proof.pin(config['dts_log'], config['dts_sha256']).read_text())
    commands = proof.read(directory / 'commands.json')
    runs = [r for r in commands if r['command'] == command]
    require(len(runs) == 1 and runs[0]['status'] == 'PASS' and runs[0]['returncode'] == 0 and
            runs[0]['stdout'] == row['log'] and runs[0]['stderr'] == row['trace_log'] and
            runs[0]['seconds'] == row['seconds'], 'wrong exact Spike execution evidence')
    proof.hashes(runs[0]['log_hashes'])
    dts_cmd = [command[0], command[1], '--priv=msu', '--pmpregions=0', '--dump-dts', command[-1]]
    runs = [r for r in commands if r['command'] == dts_cmd]
    require(len(runs) == 1 and runs[0]['returncode'] == 0 and
            runs[0]['stdout'] == config['dts_log'], 'wrong configuration dump execution')
    proof.hashes(runs[0]['log_hashes'])
    baseline = proof.read(directory / 'baseline-targets.json')
    require(baseline['passed'] == 647 and baseline['coverage_status'] == 'COMPLETE' and
            draft['baseline'] == baseline['baseline'], 'wrong final baseline binding')
    for path in (SCRIPT, Path(audit.__file__), Path(checked.__file__), Path(evidence.__file__)):
        proof.pin(path)
    return current


def install_hooks():
    global _installed
    if _installed:
        return
    delegate = evidence.precheck

    def chained(item, proof):
        return sealed_precheck(item, proof, delegate) if item.get('name') == NAME else delegate(item, proof)

    evidence.precheck = chained
    _installed = True


def main():
    install_hooks()
    return checked.main()


if __name__ == '__main__':
    raise SystemExit(main())

