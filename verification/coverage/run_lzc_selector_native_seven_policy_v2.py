"""One-shot frozen seven lifecycle with strict serialized-artifact successor."""
from pathlib import Path
from types import FunctionType

import run_lzc_selector_native_seven_policy as prior
import lzc_selector_native_seven_policy_runtime_v2 as generic

frozen, require = generic.frozen, generic.require
SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_run_lzc_selector_native_seven_policy_v2.py')

for _name, _value in vars(prior).items():
    if isinstance(_value, FunctionType) and _value.__module__ == prior.__name__:
        globals()[_name] = FunctionType(_value.__code__, globals(), _name,
                                       _value.__defaults__, _value.__closure__)
    elif not _name.startswith('__') and _name not in ('generic', 'SCRIPT', 'TEST'):
        globals().setdefault(_name, _value)


if __name__ == '__main__':
    main()
