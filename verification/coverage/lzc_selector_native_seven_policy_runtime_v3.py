"""Frozen724 serialization runtime successor: initialization array scope only."""
from pathlib import Path
from types import FunctionType

import lzc_selector_native_seven_policy_runtime_v2 as prior

SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_lzc_selector_native_seven_policy_runtime_v3.py')
TCL = SCRIPT.with_suffix('.tcl')
PREDECESSOR_TCL_SHA = '2141a997707543774683c1b8f64e5edffc988d16ebc8f56b0e970f752d3975c0'
PREDECESSOR_PY_SHA = '11627f032dce60547fd5ffa493708b2bbee6d3f0d41640d4a3da0f7a7d2a9cc6'
OLD = '    global env seven_rows seven_target_positions seven_before_complete\n'
NEW = '    global env seven_rows seven_target_positions seven_before_complete lpa_binding lpa_expected\n'

for _name, _value in vars(prior).items():
    if isinstance(_value, FunctionType) and _value.__module__ == prior.__name__:
        globals()[_name] = FunctionType(_value.__code__, globals(), _name,
                                       _value.__defaults__, _value.__closure__)
    elif not _name.startswith('__') and _name not in ('SCRIPT', 'TEST', 'TCL', 'prior'):
        globals().setdefault(_name, _value)

# The inherited normalization helpers refer to the original runtime as `prior`.
serialization_prior = prior
prior = serialization_prior.prior


def check_scope_adapter():
    require(frozen.sha(Path(serialization_prior.__file__).resolve()) == PREDECESSOR_PY_SHA
            and frozen.sha(serialization_prior.TCL) == PREDECESSOR_TCL_SHA,
            'Frozen scoping predecessor differs')
    raw = serialization_prior.TCL.read_bytes()
    require(raw.count(OLD.encode()) == 1 and TCL.read_bytes() == raw.replace(OLD.encode(), NEW.encode(), 1),
            'Successor must change exactly one initialization global declaration')


def successor_dependencies():
    check_scope_adapter()
    return (Path(serialization_prior.__file__).resolve(), Path(prior.__file__).resolve(),
            SCRIPT, TCL, TEST, SCRIPT.with_name('run_lzc_selector_native_seven_policy_v3.py'),
            SCRIPT.with_name('test_run_lzc_selector_native_seven_policy_v3.py'),
            SCRIPT.with_name('test_lzc_selector_native_seven_policy_runtime_v2.py'),
            SCRIPT.with_name('run_lzc_selector_native_seven_policy_v2.py'),
            SCRIPT.with_name('test_run_lzc_selector_native_seven_policy_v2.py'))


if __name__ == '__main__':
    check_scope_adapter()
    main()
