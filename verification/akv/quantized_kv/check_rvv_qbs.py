#!/usr/bin/env python3
"""Strict target transcript and independent host score replay; not deployment approval."""
import ctypes
import re

CAP = 'QUANT_KV_CAP source=actual_ggml_rvv profiles=2 heads=2 tokens=4 d=128 commands=16'
QUERY = re.compile(r'QUANT_KV_QUERY kind=([01]) head=([01]) bytes=136 fcsr=([0-9]+) vcsr=5 hex=([0-9a-f]{272})')
SCORE = re.compile(r'QUANT_KV_SCORE kind=([01]) head=([01]) token=([0-9]+) '
    r'rvv=([0-9a-f]{8}) qbs=([0-9a-f]{8}) ref=([0-9a-f]{8}) '
    r'rvv_flags=([0-9]+) qbs_flags=([0-9]+) ref_flags=([0-9]+) equal=([01]) errors=0')
SUITE = re.compile(r'QUANT_KV_SUITE_PASS comparisons=16 q8_differences=([0-8]) '
    r'q4_differences=([0-8]) hardware_reference_exact=1 deployment_accepted=0')
TOKENS = (0, 63, 64, 127)


def require(condition, message):
    if not condition:
        raise ValueError(message)


class HostOracle:
    def __init__(self, library):
        self.library = ctypes.CDLL(str(library))
        self.call = self.library.quant_kv_host_score
        self.call.argtypes = [ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p,
                              ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32)]
        self.call.restype = ctypes.c_int

    def __call__(self, kind, weights, query):
        require(len(weights) == (72 if kind else 136) and len(query) == 136, 'Oracle input extent')
        w, a = ctypes.create_string_buffer(weights), ctypes.create_string_buffer(query)
        bits, flags = ctypes.c_uint32(), ctypes.c_uint32()
        require(self.call(kind, w, a, ctypes.byref(bits), ctypes.byref(flags)) == 0,
                'Host reference rejected descriptor')
        return bits.value, flags.value


def check_transcript(text, key_data, oracle):
    """Checks every exported query and score; caller separately checks DUT protocol/work."""
    queries, scores, differences = [], [], [0, 0]
    declared = suite = terminal = False
    severity = set()
    for line in text.splitlines():
        require(not re.search(r'Fatal:|Error:|\b(?:FAIL|FAILED|TIMEOUT)\b', line, re.I), 'Failure text')
        if 'UVM_ERROR' in line or 'UVM_FATAL' in line:
            m = re.fullmatch(r'(UVM_ERROR|UVM_FATAL)\s*:\s*0', line)
            require(m is not None and m[1] not in severity, 'UVM error/duplicate summary')
            severity.add(m[1])
        if 'Core Test' in line:
            require(line == 'Core Test *** SUCCESS *** (tohost = 0)' and suite and not terminal, 'Core termination')
            terminal = True
        if 'QUANT_KV_' not in line:
            continue
        require(not terminal, 'Program record after termination')
        if line == CAP:
            require(not declared and not queries and not suite, 'Duplicate capability record')
            declared = True
        elif QUERY.fullmatch(line):
            m = QUERY.fullmatch(line)
            index = len(queries)
            require(declared and not suite and index < 4 and len(scores) == index * 4 and
                    (int(m[1]), int(m[2])) == divmod(index, 2) and int(m[3]) <= 31,
                    'Query order/FRM/extent')
            queries.append(dict(kind=int(m[1]), head=int(m[2]), fcsr=int(m[3]), hex=m[4]))
        elif SCORE.fullmatch(line):
            m = SCORE.fullmatch(line)
            index = len(scores)
            kind, head = divmod(index // 4, 2)
            require(declared and not suite and index < 16 and len(queries) == index // 4 + 1 and
                    (int(m[1]), int(m[2]), int(m[3])) == (kind, head, TOKENS[index % 4]),
                    'Score order/identity')
            rvv, hw, ref = (int(m[i], 16) for i in (4, 5, 6))
            rf, hf, ff = (int(m[i]) for i in (7, 8, 9))
            require(all((x & 0x7f800000) != 0x7f800000 for x in (rvv, hw, ref)) and
                    max(rf, hf, ff) <= 31, 'Nonfinite score/FRM')
            row_bytes = 72 if kind else 136
            offset = (head * 256 + TOKENS[index % 4]) * row_bytes
            weights = key_data[kind][offset:offset + row_bytes]
            expected, flags = oracle(kind, weights, bytes.fromhex(queries[-1]['hex']))
            require(hw == ref == expected and hf == ff == flags, 'Independent host bits/flags mismatch')
            equal = int(rvv == hw and rf == hf)
            require(int(m[10]) == equal, 'Incorrect equality claim')
            differences[kind] += 1 - equal
            scores.append(dict(kind=kind, head=head, token=TOKENS[index % 4], rvv_bits=rvv,
                               qbs_bits=hw, rvv_flags=rf, qbs_flags=hf, equal=bool(equal)))
        elif SUITE.fullmatch(line):
            m = SUITE.fullmatch(line)
            require(declared and not suite and len(scores) == 16 and len(queries) == 4 and
                    list(map(int, m.groups())) == differences, 'Suite count/order/difference mismatch')
            suite = True
        else:
            raise ValueError('Malformed quantized KV record')
    require(declared and suite and terminal and severity == {'UVM_ERROR', 'UVM_FATAL'}, 'Incomplete transcript')
    return dict(state='HOST_NUMERICAL_REPLAY_PASS', queries=queries, scores=scores,
                differences=dict(q8_0=differences[0], q4_0=differences[1]),
                deployment_approved=False, performance_measured=False)
