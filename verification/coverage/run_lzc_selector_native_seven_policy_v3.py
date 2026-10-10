"""Reviewed lifecycle entry for the initialization-scope-only successor."""
from pathlib import Path
from types import FunctionType

import run_lzc_selector_native_seven_policy_v2 as predecessor
import lzc_selector_native_seven_policy_runtime_v3 as generic

SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_run_lzc_selector_native_seven_policy_v3.py')
for _name, _value in vars(predecessor).items():
    if isinstance(_value, FunctionType) and _value.__module__ in (predecessor.__name__, predecessor.prior.__name__):
        globals()[_name] = FunctionType(_value.__code__, globals(), _name,
                                       _value.__defaults__, _value.__closure__)
    elif not _name.startswith('__') and _name not in ('SCRIPT', 'TEST', 'generic'):
        globals().setdefault(_name, _value)


if __name__ == '__main__':
    generic.check_scope_adapter()
    main()
