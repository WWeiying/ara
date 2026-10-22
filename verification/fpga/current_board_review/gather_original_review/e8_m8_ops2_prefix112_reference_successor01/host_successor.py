#!/usr/bin/env python3
"""Offline corrupted-trace controls, using only the new reference raw log."""
import hashlib
import re
import sys

sys.dont_write_bytecode = True
from reference_check import HERE, model, audit_trace, require
from run_reference import OLD, read, save, sha, check_pins


def main():
    out = HERE/'host'
    out.mkdir()
    pins = read(HERE/'input_pins.json')
    check_pins(pins)
    proof = read(OLD/'source_elf_proof.json')
    from pathlib import Path
    elf = Path(proof['spike_elf']['path'])
    raw = read(HERE/'reference/reference.json')
    require(sha(HERE/'reference/commits.log') == raw['commit_sha256'], 'New raw drift')
    routine = proof['spike_routine']
    pcs = {r['pc'] for r in routine}
    output = int(raw['addresses']['output'], 16)
    pat = re.compile(r'core\s+0:\s+\d\s+(0x[0-9a-f]+)\s+\((0x[0-9a-f]+)\)(.*)')
    rdpat = re.compile(r'\bx(\d+)\s+(0x[0-9a-f]+)')
    readpat = re.compile(r'\bmem\s+(0x[0-9a-f]+)\s*$')
    first, entries, records, digest = [], 0, 0, hashlib.sha256()
    truncated = out/'old_5m_no_htif_semantic_projection.trace'
    # Preserve every scalar store, helper instruction, CSR/vector update, relevant
    # argument register assignment and scalar oracle read. Remove only unrelated
    # scalar computation. The unfiltered first5M bytes must match the old trace.
    with (HERE/'reference/commits.log').open('rb') as source, truncated.open('x') as dest:
        for binary in source:
            if records == 5_000_000:
                break
            digest.update(binary)
            line = binary.decode('ascii')
            match = pat.match(line)
            if not match:
                continue
            records += 1
            pc, code, rest = int(match[1],16), int(match[2],16), match[3]
            rd, load = rdpat.search(rest), readpat.search(rest)
            is_output = load and rd and output <= int(load[1],16) < output+1026
            if pc == routine[0]['pc']:
                entries += 1
            keep = (pc in pcs or code & 127 == 35 or is_output or
                    (rd and int(rd[1]) in (*range(10,18),28)) or
                    re.search(r'\bv\d+\s+0x|\bc\d+_(vstart|vl|vtype)', rest))
            if keep:
                dest.write(line)
                if entries < 2:
                    first.append(line)
    old_sha = read(OLD/'reference/not_completed.json')['commit_sha256']
    require(records == 5_000_000 and digest.hexdigest() == old_sha,
            'New first5M raw bytes differ from pinned old truncated trace')
    require(entries == 112, 'Old-bound fixture must preserve all112 helper calls')
    gold = model()
    cases = [('old_5m_no_htif', truncated, 'Incomplete calls/asm/oracle/exit')]

    def mutate(name, predicate, transform, reason):
        lines = list(first)
        for i, line in enumerate(lines):
            match = pat.match(line)
            if match and predicate(match):
                lines[i] = transform(line, match)
                break
        else:
            raise ValueError('Missing negative injection point: '+name)
        require(lines != first, 'Ineffective corruption')
        path = out/(name+'.trace')
        path.write_text(''.join(lines))
        cases.append((name, path, reason))

    def output_at(match, address):
        load = readpat.search(match[3])
        return load and int(load[1],16) == address and int(match[2],16) & 127 == 3

    mutate('wrong_encoding', lambda m: int(m[1],16)==routine[8]['pc'],
           lambda line,m: line.replace(m[2], '0x308fbc57',1), '13asm order/encoding')
    for name, address in [('wrong_result',output+1), ('wrong_guard0',output), ('wrong_guard1',output+1025)]:
        mutate(name, lambda m,a=address: output_at(m,a),
               lambda line,m: rdpat.sub(lambda r:'x'+r[1]+' 0x00000000000000ff',line,count=1), 'Output mismatch')
    mutate('wrong_vstart', lambda m: int(m[1],16)==routine[9]['pc'],
           lambda line,m: rdpat.sub(lambda r:'x'+r[1]+' 0x0000000000000001',line,count=1), 'vstart did not reset')
    mutate('missing_oracle', lambda m: output_at(m,output+1), lambda line,m:'',
           'Incomplete calls/asm/oracle/exit')
    results = []
    for name, path, reason in cases:
        try:
            audit_trace(path, elf, gold)
        except ValueError as error:
            require(reason in str(error), 'Wrong rejection '+name+': '+str(error))
            results.append(dict(name=name,status='REJECTED_AS_EXPECTED',reason=str(error),
                                path=str(path),sha256=sha(path)))
            print(name, 'REJECTED_AS_EXPECTED', flush=True)
        else:
            raise ValueError('Invalid reference accepted: '+name)
    check_pins(pins)
    report = dict(status='PASS_7_SUCCESSOR_NEGATIVE_CONTROLS', tests=results,
        old_full_trace_not_reparsed=True, new_first_5000000_bytes_sha256=digest.hexdigest(),
        matches_old_truncated_raw_sha256=True, old_5m_fixture_is_semantic_projection=True,
        original112_Host12_reused_by_hash=sha(OLD/'host/host_gate.json'),
        raw_complete_positive=sha(HERE/'reference/reference.json'),
        checker_only_ceiling_changed=True, inputs_unchanged=True, reference_attempts=1, dut=False)
    save(out/'host_gate.json', report)
    retired = raw['firmware_retired_to_htif_store']
    artifacts = {str(p):sha(p) for p in sorted(HERE.rglob('*')) if p.is_file()}
    save(HERE/'artifact_pins.json', artifacts)
    save(HERE/'READY.json', dict(status='REFERENCE_SUCCESSOR112_READY_PENDING_INDEPENDENT_REVIEW_NOT_DUT',
        reference=str(HERE/'reference/reference.json'), reference_sha256=sha(HERE/'reference/reference.json'),
        host_gate_sha256=sha(out/'host_gate.json'), input_pins_sha256=sha(HERE/'input_pins.json'),
        artifact_pins_sha256=sha(HERE/'artifact_pins.json'),
        admission_sha256=sha(HERE.parent/'e8_m8_ops2_prefix112_reference_admission01/review.json'),
        reused_source_proof_sha256=sha(OLD/'source_elf_proof.json'),
        soc_elf=proof['soc_elf'], spike_elf=proof['spike_elf'],
        calls=112, predecessors=111, fullcap_results=114688, guards=224, returned_vstart=112,
        helper_retire_counts=raw['routine_retire_counts'], target_encoding='30803c57',
        source0=185, original_stopped_tuple=None, full2688=False, linux=False, dut=False,
        old_prepare_remains_not_completed=True, no_recompile=True, old_pins_unchanged=True,
        reference_attempts=1, reference_limits=raw['limits'],
        instruction_cost=dict(measured_firmware_retired=retired, measured_spike_seconds=raw['elapsed_s'],
            estimated_vcs_seconds_at273=retired/273, estimated_vcs_plus20percent=retired/273*1.2,
            measured_vcs_for_this_case=False, dut_timeout_unchanged=9000, dut_admitted=False)))
    print('REFERENCE_SUCCESSOR112_READY_PENDING_INDEPENDENT_REVIEW_NOT_DUT', flush=True)


if __name__ == '__main__':
    main()
