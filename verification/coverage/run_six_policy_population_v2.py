"""Private reuse of sealed one-shot runner for the exact cc-link successor."""
from pathlib import Path
from types import FunctionType

import run_six_policy_population as prior
import prepare_six_policy_population_v2 as successor

# Every own helper shares this private namespace; neither frozen module is mutated.
globals().update({name: value for name, value in vars(prior).items() if not name.startswith('__')})
generic = successor
SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_run_six_policy_population_v2.py')
for name, function in tuple(vars(prior).items()):
    if isinstance(function, FunctionType) and function.__module__ == prior.__name__:
        globals()[name] = FunctionType(function.__code__, globals(), function.__name__,
                                      function.__defaults__, function.__closure__)


if __name__ == '__main__':
    main()
