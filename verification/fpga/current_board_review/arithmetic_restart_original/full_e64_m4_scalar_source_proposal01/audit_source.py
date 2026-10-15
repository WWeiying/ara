"""Static text/list/layout proof only, never execute or compile a C helper."""
import difflib
import hashlib
import json
from pathlib import Path
import re
import struct

HERE = Path(__file__).resolve().parent
A = HERE.parent
C = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_extended04')
SOURCE = A / 'recovery22/reconstructed_oracle.c'
MODEL = A / 'full_e64_m4_source_model01'
E32 = A / 'full_e32_m2_scalar_candidate01/scalar_setup.h'


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    output = HERE / 'STATIC_PROOF.json'
    require(not output.exists(), 'Do not overwrite a previous static proof')
    original, proposed = SOURCE.read_text(), (HERE / 'case_proposal.c').read_text()
    require(sha(SOURCE) == '7483f9dfde7012f7b800314fe1765f8cee9836fbcfbdc16fc641554397884e91', 'Original C identity')
    require(sha(MODEL / 'generated01/result.json') == '984e9bfa457dd1178b4fe60e7b0c3e4aef7114190b4ec4439a8f554785635a43', 'Exact m4 model')
    require(sha(MODEL / 'fp_period_proposal.h') == 'cfe2af2df0bd9a2bb9b4fbf526cd5061f568fa42f98e3819f0e1423e7fa06da8', 'Existing exact FP128 proposal')
    require(sha(E32) == '12dea4d7c5b857ca58a6305fc3a3032b9c000c1c62f8e186ad43fd7bf6e4d5b5', 'Reviewed e32 mask source')
    expected = original
    edits = [
        ('#include "operations.h"\nstatic word a[1024], b[1024], out[1026];\nstatic uint8_t mask[128];',
         '#if SEW != 64\n#error This proposal is exclusively the original e64/m4 CAP64 program\n#endif\n#include "operations.h"\n#include "mask_setup.h"\n#include "packed_output.h"\n#include "../full_e64_m4_source_model01/fp_period_proposal.h"\nstatic word a[1024], b[1024], out[1026] __attribute__((aligned(8)));\nstatic uint8_t mask[128] __attribute__((aligned(8)));'),
        ('if(!cap || cap>1024){', 'if(cap!=64){'),
        ('                for(unsigned i=0;i<128;++i)mask[i]=0;\n                for(unsigned i=0;i<cap;++i)\n                    if(selected(mode,i))mask[i/8]|=1u<<(i%8);',
         '                e64m4_initialize_mask(mask,mode);'),
        ('                    if(op>=25)\n                        for(unsigned i=0;i<cap;++i) {\n                            a[i]=fp_inputs[(i+seed)%8];\n                            b[i]=fp_inputs[(i*3+seed)%8];\n                        }',
         '                    if(op>=25)e64_m4_refresh_fp(a,b,fp_inputs,seed);'),
        ('                    for(unsigned i=0;i<cap+2;++i)out[i]=sentinel;',
         '                    e64m4_initialize_output(out);'),
        ('                    unsigned packed=0;',
         '                    if(e64m4_packed_mismatch(out,checks)) {\n                    unsigned packed=0;'),
        ('                    ++checks;', '                    } else elements+=cap;\n                    ++checks;'),
    ]
    for old, new in edits:
        require(expected.count(old) == 1, 'Unique allowed source replacement')
        expected = expected.replace(old, new)
    require(expected.rstrip('\n') == proposed.rstrip('\n'), 'Only seven enumerated source edits')
    require(original.split('static void failure(', 1)[1].split('void probe_main', 1)[0] ==
            proposed.split('static void failure(', 1)[1].split('void probe_main', 1)[0], 'Original diagnostic unchanged')
    oracle = original.split('                    unsigned packed=0;', 1)[1].split('                    ++checks;', 1)[0]
    actual = proposed.split('                    unsigned packed=0;', 1)[1].split('                    } else elements+=cap;', 1)[0]
    require(oracle == actual, 'Original whole fallback body unchanged')
    mask = (HERE / 'mask_setup.h').read_text()
    clear = list(map(int, re.findall(r'    E64M4_MASK_CLEAR\((\d+)\);', mask)))
    require(clear == list(range(0, 128, 8)), '16 ascending disjoint clear spans')
    require('__builtin_memcpy(mask + (offset), &zero, 8);' in mask and
            'mask[(index) / 8u] |' in mask and 'E64M4_MASK_BARRIER();' in mask,
            'Actual memcpy / cumulative byte RMW / barrier body')
    e32 = E32.read_text()
    mask_results = []
    for mode in range(3):
        body = mask.split(f'(mode == {mode}) {{', 1)[1].split('}', 1)[0]
        selected = list(map(int, re.findall(r'E64M4_MASK_BIT\((\d+)\);', body)))
        wanted = [i for i in range(64) if mode == 0 or (i % 2 == 1 if mode == 1 else i % 7 == 2)]
        inherited = list(map(int, re.findall(r'E32M2_MASK_BIT\((\d+)u\);', e32.split(f'(mode=={mode}) {{', 1)[1].split('}', 1)[0])))
        require(selected == wanted == inherited, 'Own CAP64 proof and exact inherited selected order')
        memory, expected_mask = bytearray([0xa5] * 128), bytearray(128)
        events = []
        for offset in clear:
            memory[offset:offset + 8] = bytes(8)
            events.append([offset, 8, 0])
        require(memory == bytes(128), 'Clear complete before any selected write')
        for index in selected:
            offset = index // 8
            memory[offset] |= 1 << (index % 8)
            expected_mask[offset] = sum(1 << (j % 8) for j in wanted if j <= index and j // 8 == offset)
            require(memory == expected_mask, 'Every intermediate cumulative mask state')
            events.append([offset, 1, memory[offset]])
        model_mask = (MODEL / 'generated01/masks128.bin').read_bytes()[128 * mode:128 * (mode + 1)]
        require(memory == model_mask and memory[8:] == bytes(120), 'Own m4 final mask and upper bytes')
        mask_results.append(dict(mode=mode, selected_indices=selected, clear_stores=16,
                                 byte_updates=len(selected), events=events, final_mask_hex=memory.hex()))
    packed = (HERE / 'packed_output.h').read_text()
    init = packed.split('e64m4_initialize_output', 1)[1].split('/* Volatile', 1)[0]
    bases = list(map(int, re.findall(r'E64M4_OUTPUT_EIGHT\((\d+)\);', init)))
    tails = list(map(int, re.findall(r'E64M4_OUTPUT_STORE\((\d+)\);', init)))
    require([b + j for b in bases for j in range(8)] + tails == list(range(66)), 'All66 fresh output stores')
    compare = packed.split('e64m4_packed_mismatch', 1)[1]
    loop, tail = compare.split('    const volatile uint64_t *current = output + 64;', 1)
    require(re.findall(r'E64M4_OUTPUT_COMPARE\((\d+)\);', loop) == list(map(str, range(8))), '8 words/fullblock')
    require(re.findall(r'E64M4_OUTPUT_COMPARE\((\d+)\);', tail) == ['0', '1'], 'Only16 actual tail bytes')
    require('block < 8' in loop and 'return' not in loop and 'return different != 0;' in tail,
            'All66 observations, no mismatch early exit')
    require('different |= actual ^ wanted;' in packed and 'output + 64' in packed,
            'No byte-loss or truncated upper guard')
    model = json.loads((MODEL / 'generated01/result.json').read_text())
    require((model['calls'], model['dictionary_blocks'], model['words_per_call']) == (5985, 1986, 66), 'Exact m4 data contract')
    ids = (MODEL / 'generated01/indices_u16le.bin').read_bytes()
    require(len(ids) == 107730 and max(struct.unpack('<53865H', ids)) == 1985, 'Real uint16 dictionary bounds')
    paths = [SOURCE, E32, A / 'e32_m2_scalar_source_review01/REVIEW.md',
             C / 'rvv_matrix_e64_m4.S', C / 'e64/operations.h', C / 'overlay/opt/ara-tests/rvv_matrix_e64_m4',
             MODEL / 'fp_period_proposal.h', MODEL / 'proposal_static_check.json', MODEL / 'generated01/result.json',
             MODEL / 'generated01/dictionary64.bin', MODEL / 'generated01/indices_u16le.bin',
             MODEL / 'generated01/gold_u64le.bin', HERE / 'case_proposal.c', HERE / 'mask_setup.h',
             HERE / 'packed_output.h', HERE / 'audit_source.py']
    report = dict(status='STATIC_SOURCE_INTEGRATION_CHECKED_PENDING_INDEPENDENT_REVIEW_NOT_HOST_NOT_COMPILED',
                  allowed_source_edits=len(edits), original_fallback_body_identical=True,
                  original_failure_function_identical=True, original_linux_wrapper_unchanged=True,
                  mask_groups=2205, groups_each_mode=735, clear_SD_intended=35280,
                  selected_SB_required=77175, fp_calls=1890, fp_ordered_u64_writes=241920,
                  output_words_each=66, dictionary_ids_each=9, dictionary_last_valid_bytes=16,
                  dictionary_definition_status='EXTERN_ONLY_NOT_EMITTED_NOT_LINKED',
                  mask_proof=mask_results, input_pins={str(p): sha(p) for p in paths},
                  note='Source text/permutation/layout proof only. No C helper, Host binary, compiler, reference or DUT run.')
    output.write_text(json.dumps(report, indent=2) + '\n')
    (HERE / 'source_integration.diff').write_text(''.join(difflib.unified_diff(
        original.splitlines(True), proposed.splitlines(True), fromfile=str(SOURCE), tofile=str(HERE / 'case_proposal.c'))))
    print(json.dumps({k: report[k] for k in ('status', 'allowed_source_edits', 'selected_SB_required', 'fp_ordered_u64_writes')}))


if __name__ == '__main__':
    main()
