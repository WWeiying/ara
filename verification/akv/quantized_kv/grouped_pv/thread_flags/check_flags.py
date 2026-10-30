"""Diagnostic acceptance, not a replacement for any graph checker."""
import re


def require(ok, message):
    if not ok:
        raise ValueError(message)


def check_log(text):
    require(not re.search(r'GROUPED_GGML_FAIL|GGML_ASSERT|Assertion[^\n]*failed|'
                          r'Kernel panic|Segmentation fault|Illegal instruction|terminate called', text),
            'Guest failure')
    rows = [line for line in re.split(r'\r?\n', text) if any(prefix in line for prefix in
            ('THREAD_FLAGS', 'GGML_RISCV_QUANT_KV', 'GUEST_TEST_EXIT'))]
    require(len(rows) == 19, 'Missing or extra diagnostic records')
    require(rows[0] == 'THREAD_FLAGS_BEGIN kind=q4_0 layout=token_major visible=128 threads=2 calls=16 '
            'quant_kv=0 grouped=unset initial_fcsr=8 initial_vcsr=5', 'Wrong diagnostic setup')
    flags, digests = [], set()
    for call, line in enumerate(rows[1:17]):
        match = re.fullmatch(rf'THREAD_FLAGS_CALL call={call} outputs=1536 fcsr=(\d+) vcsr=5 '
                             r'digest=([0-9a-f]{16}) exact=1', line)
        require(match is not None, 'Wrong call/CSR/output record')
        value = int(match[1])
        require(value <= 31 and value & 8, 'FRM or preexisting sticky flag changed')
        flags.append(value)
        digests.add(match[2])
    require(len(digests) == 1, 'Complete-output digest changed')
    require(rows[17] == 'THREAD_FLAGS_COMPLETE calls=16 outputs_each=1536 all_bits_equal=1 '
            'quant_kv=0 grouped=unset performance=not_measured', 'Incomplete diagnostic')
    require(rows[18] == 'GUEST_TEST_EXIT=0', 'Guest did not exit successfully')
    observed = sorted(set(flags))
    return dict(state='DIAGNOSTIC_COMPLETE', calls=16, outputs_each=1536, all_bits_equal=True,
                parent_fcsr=flags, observed_fcsr=observed, quant_kv=False, grouped=False,
                hypothesis_supported=observed == [9, 11],
                interpretation='observed_9_11_same_program' if observed == [9, 11] else
                'inconclusive' if len(observed) == 1 else 'other_flag_variation_requires_review',
                rtl_performance=False)
