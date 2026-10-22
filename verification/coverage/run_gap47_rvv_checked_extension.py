#!/usr/bin/env python3
"""Sealed gap47 precheck hook; preserve the parent runner and other case hooks."""
from pathlib import Path
import re

import coverage_evidence as evidence
import run_checked_extension as checked

SCRIPT = Path(__file__).resolve()
ROOT = evidence.full.ROOT
NAME = 'rvv:vgap47_sv39_indexed'
WORDS = {'gap47_indexed_load': 0x0f03e407, 'gap47_indexed_store': 0x0f03e627}
CHECKS = 123
require = evidence.require
_installed = False


def trace_check(trace, sites):
    require(set(sites) == set(WORDS), 'wrong indexed instruction sites')
    commits = [(int(m[1]), int(m[2], 16), int(m[3], 16)) for m in re.finditer(
        r'(?m)^core\s+\d+:\s+([0-3])\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)', trace)]
    for name, word in WORDS.items():
        site = sites[name]
        require(int(site['word'], 16) == word, 'wrong indexed instruction word')
        seen = [(mode, insn) for mode, pc, insn in commits if pc == int(site['pc'], 16)]
        require(seen == [(1, word)], 'indexed site must retire exactly once in S mode')
    require(sum(word in WORDS.values() for _, _, word in commits) == 2,
            'unexpected extra indexed target instruction')
    traps = re.findall(r'exception\s+(\w+)', trace)
    require(traps == ['trap_supervisor_ecall'], 'unexpected or missing architectural trap')
    return dict(indexed_commits=2, indexed_privilege=1,
                retired_log_entries=len(commits), traps=traps)


def require_exact_replay(result, files, saved):
    require(saved.get('status') == 'PASS' and saved.get('read_only_validation') is True,
            'sealed preflight is not a checked PASS')
    require(result == saved.get('result'), 'sealed precheck result differs')
    require(files and files == saved.get('checked_files'), 'sealed checked_files differs')


def sealed_precheck(item, proof, delegate):
    record = Path(item['precheck']['record']).absolute()
    directory = record.parent
    require(directory.parent == ROOT / 'verification/out' and
            directory.name.startswith('gap47-sv39-indexed-preflight-') and
            record.name == 'spike_results.json', 'unexpected gap47 preflight location')
    draft_path = directory / 'selection.checked-draft.json'
    seals = proof.read(directory / 'draft.sha256.json')
    require(set(seals) == {str(draft_path), str(directory / 'checked-precheck.json'),
                           str(directory / 'artifact_hashes.json')}, 'wrong seal set')
    proof.hashes(seals)
    saved = proof.read(directory / 'checked-precheck.json')
    draft = proof.read(draft_path)
    require(len(draft['cases']) == 1 and draft['cases'][0]['name'] == NAME,
            'wrong sealed candidate set')
    require(item == draft['cases'][0] and item['timeout_s'] == 300,
            'parent must preserve the sealed case exactly')
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
    require(len(records) == 1, 'wrong Spike result set')
    row = records[0]
    require(row['test'] == NAME and row['status'] == 'PASS' and row['returncode'] == 0 and
            row['checks'] == CHECKS, 'wrong Spike result')
    command = row['command']
    require(command == [execution['spike_tool'], '--isa=rv64gcv_zfh_zvfh_zvl1024b',
                        '-l', '--log-commits', row['spike_binary']], 'wrong Spike command')
    proof.pin(command[0], row['spike_tool_sha256'])
    proof.pin(row['spike_binary'], row['spike_sha256'])
    proof.pin(row['binary'], row['binary_sha256'])
    require(row['binary'] == item['binary'] and row['binary_sha256'] == item['binary_sha256'],
            'Spike/DUT ELF binding differs')
    require(execution['dut']['elf'] == row['binary'] and
            execution['dut']['elf_sha256'] == row['binary_sha256'] and
            execution['spike']['elf'] == row['spike_binary'] and
            execution['spike']['elf_sha256'] == row['spike_sha256'], 'execution ELF proof differs')
    trace_path = proof.pin(row['trace_log'], row['trace_sha256'])
    trace_result = trace_check(trace_path.read_text(), execution['spike']['sites'])
    require(trace_result == execution['trace'], 'exact Spike trace evidence differs')
    commands = proof.read(directory / 'commands.json')
    runs = [c for c in commands if c['command'] == command]
    require(len(runs) == 1 and runs[0]['status'] == 'PASS' and runs[0]['returncode'] == 0 and
            runs[0]['stdout'] == row['log'] and runs[0]['stderr'] == row['trace_log'] and
            runs[0]['seconds'] == row['seconds'], 'Spike execution record differs')
    proof.hashes(runs[0]['log_hashes'])
    for path in (SCRIPT, Path(checked.__file__), Path(evidence.__file__)):
        proof.pin(path)
    return current


def install_hooks():
    global _installed
    if _installed:
        return
    delegate = evidence.precheck

    def chained(item, proof):
        if item.get('name') == NAME:
            return sealed_precheck(item, proof, delegate)
        return delegate(item, proof)

    evidence.precheck = chained
    _installed = True


def main():
    install_hooks()
    return checked.main()


if __name__ == '__main__':
    raise SystemExit(main())
