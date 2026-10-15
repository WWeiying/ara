#!/usr/bin/env python3
"""Classify the already captured instruction stream, with no execution."""
from collections import Counter
import json
import re
import sys

sys.dont_write_bytecode = True
from prepare import HERE, sha, save


def main():
    out = HERE / 'reference03M'
    assert not (out / 'CONFIG_DELTA.json').exists()
    review_path = HERE.parent / 'original_e16_mf4_reference_admission01/review.json'
    review = json.loads(review_path.read_text())
    approval = json.loads((out / 'approval.json').read_text())
    execution = json.loads((out / 'execution.json').read_text())
    assert sha(HERE / 'soc/program.elf') == review['soc_elf_sha256']
    assert sha(HERE / 'spike/program.elf') == review['spike_elf_sha256']
    assert review['limits'] == {'total_debug_steps': 3000000, 'seconds': 120,
                               'raw_bytes': 268435456, 'attempts': 1}
    assert approval['limits'] == {'steps': 3000000, 'seconds': 120, 'raw_bytes': 268435456}
    actual, = [s.split('=', 1)[1] for s in approval['command'] if s.startswith('--isa=')]
    assert actual == 'rv64gcv_zfh_zvfh_zvl1024b'
    assert review['isa'] == 'rv64gcv_zvfh_zvl1024b'
    assert sha(out / 'commits.log') == execution['raw']['commits.log']['sha256']
    line_re = re.compile(r'^core\s+0:\s+3\s+(0x[0-9a-f]+)\s+\((0x[0-9a-f]+)\)')
    total = 0
    scalar_fp = []
    vector_fp = Counter()
    for line in (out / 'commits.log').open():
        match = line_re.match(line)
        assert match
        total += 1
        pc, insn = int(match[1], 16), int(match[2], 16)
        opcode, funct3 = insn & 127, (insn >> 12) & 7
        # All scalar FP arithmetic/conversion/FMA; scalar FLH/FLW/FLD and stores.
        scalar = insn & 3 == 3 and (opcode in (0x43, 0x47, 0x4b, 0x4f, 0x53) or
                  (opcode in (0x07, 0x27) and funct3 in (1, 2, 3)))
        # RV64 C.FLD/C.FSD (and SP forms); RV64 C.LD/C.SD are integer.
        compressed_fp = insn & 3 in (0, 2) and insn >> 13 in (1, 5)
        if scalar or compressed_fp:
            scalar_fp.append({'ordinal': total, 'pc': hex(pc), 'insn': hex(insn)})
        if opcode == 0x57 and funct3 in (1, 5):
            vector_fp[f'{insn:08x}'] += 1
    assert total == 1860000
    assert scalar_fp == []
    assert dict(vector_fp) == {'0c881c57': 1}
    cost = review['static_cost_review']
    assert sha(cost['path']) == cost['sha256']
    save(out / 'CONFIG_DELTA.json', {
        'status': 'PROFILE_TEXT_DIFF_RECORDED_NO_RETRY_PENDING_INDEPENDENT_REVIEW',
        'actual_ISA': actual, 'later_written_review_ISA': review['isa'],
        'exact_profile_match': False,
        'authority': 'Prior explicit user FP16 profile and pre-execution3M authorization; later user permits recorded delta, independent review pending',
        'later_written_review_used_as_preexecution_file_gate': False,
        'review_path': str(review_path), 'review_sha256': sha(review_path),
        'cost_review': cost, 'actual_command': approval['command'],
        'ELF_and_resource_limits_match': True, 'source_oracle_ELF_changed': False,
        'raw_instruction_records_classified': total, 'scalar_FP_records': scalar_fp,
        'scalar_half_records': 0, 'vector_FP_encodings': dict(vector_fp),
        'classification_scope': 'all scalar FP opcodes/FMA/load/store and RV64 compressed FP; no scalar FP of any width executed',
        'inference': 'Extra scalar Zfh has no observed scalar-half instruction consumer in this concrete passing execution; not an exact-profile conformance claim',
        'pins': {str(p): sha(p) for p in (review_path, out / 'approval.json', out / 'execution.json',
                                        out / 'commits.log', HERE / 'config_delta.py')}})


if __name__ == '__main__':
    main()
