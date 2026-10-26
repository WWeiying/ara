"""Check full-logit model pairing and actual four-row preparation selection."""
from collections import Counter
from pathlib import Path
import re
import sys
import json


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def check(text):
    require(not re.search(r'Q8K_MODEL_FAIL|Segmentation fault|Illegal instruction|Kernel panic', text), 'Guest failure')
    require(re.findall(r'^GUEST_TEST_EXIT=(\d+)\s*$', text, re.M) == ['0'], 'Missing or failed guest exit')
    active, begun, ended = None, [], []
    steps, preparations, calls = [[], []], [[], []], [[], []]
    comparisons, done = [], False
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('Q8K_MODEL_BEGIN '):
            require(line == f'Q8K_MODEL_BEGIN enabled={len(begun)}' and active is None and len(begun) < 2, 'Begin')
            active = len(begun); begun.append(active)
        elif line.startswith('Q8K_MODEL_END '):
            require(active is not None and line == f'Q8K_MODEL_END enabled={active}', 'End')
            require(len(steps[active]) == 6 and preparations[active], 'Missing model/preparation work')
            ended.append(active); active = None
        elif line.startswith('Q8K_MODEL_STEP '):
            m = re.fullmatch(r'Q8K_MODEL_STEP enabled=([01]) kind=([01]) step=([012]) token=(\d+) fcsr=(\d+) vcsr=(\d+) outputs=151936', line)
            require(m is not None and active is not None, 'Step syntax')
            mode, kind, step, token, fc, vc = map(int, m.groups())
            require(mode == active and (kind, step) == divmod(len(steps[active]), 3) and
                    token < 151936 and fc <= 31 and fc & 8 and vc <= 7, 'Step contract')
            steps[active].append((kind, step, token, fc, vc))
        elif line.startswith('GGML_RISCV_QBS_Q8K_M4_PREPARE '):
            m = re.fullmatch(r'GGML_RISCV_QBS_Q8K_M4_PREPARE enabled=([01]) path=(generic|rvv) k=(\d+)', line)
            require(m is not None and active is not None, 'Unscoped preparation')
            mode, path, k = m.groups()
            require(int(mode) == active and (active or path == 'generic') and int(k) > 0, 'Wrong preparation')
            preparations[active].append((path, int(k)))
        elif line.startswith('GGML_RISCV_QBS_CALL '):
            require(active is not None, 'Unscoped projection')
            calls[active].append(line)
        elif line.startswith('Q8K_MODEL_COMPARE '):
            index = len(comparisons)
            require(active is None and ended == [0, 1] and index < 6 and line ==
                    f'Q8K_MODEL_COMPARE kind={index//3} step={index%3} outputs=151936 bitwise=1 csr_equal=1 token_equal=1', 'Comparison')
            comparisons.append(line)
        elif line.startswith('Q8K_MODEL_SUITE_PASS'):
            require(not done and len(comparisons) == 6 and line ==
                    'Q8K_MODEL_SUITE_PASS comparisons=6 performance=not_measured', 'Suite')
            done = True
        elif 'Q8K_MODEL' in line:
            raise ValueError('Unknown protocol')
    require(done and ended == [0, 1] and active is None and steps[0] == steps[1], 'Incomplete or changed output/CSR')
    require(calls[0] and calls[0] == calls[1], 'Changed projection workload')
    require(Counter(k for _, k in preparations[0]) == Counter(k for _, k in preparations[1]), 'Changed preparation work')
    require(any(path == 'rvv' for path, _ in preparations[1]), 'Candidate never selected')
    return dict(state='PASS', comparisons=6, vocabulary=151936, preparation_calls_per_mode=len(preparations[0]),
                vector_preparation_calls=sum(p == 'rvv' for p, _ in preparations[1]),
                projection_calls_per_mode=len(calls[0]), rtl_performance=False, model_speedup_measured=False)


if __name__ == '__main__':
    print(json.dumps(check(Path(sys.argv[1]).read_text()), indent=2))
