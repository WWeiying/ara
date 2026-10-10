"""Exact frozen runner adapter for the exported-bootstrap preflight."""
from pathlib import Path
import run_readonly_csr_simulation as frozen

life, require = frozen.life, frozen.require
FROZEN_SHA = '32033510cd39838db8adafed04bc0bcabca351f8f5b785121231085ca0b135e7'


def adapted_source(source):
    replacements = (
        ('import build_readonly_csr_preflight as preflight', 'import build_readonly_csr_preflight_v2 as preflight'),
        ("'test_run_readonly_csr_simulation.py'", "'test_run_readonly_csr_simulation_v2.py'"),
        ('deps = (Path(__file__).resolve(),', 'deps = (Path(' + repr(str(Path(frozen.__file__).resolve())) +
         '), Path(__file__).resolve(),'))
    result = source
    for old, new in replacements:
        require(result.count(old) == 1 and new not in result, 'Exact frozen runner replacement required')
        result = result.replace(old, new, 1)
    check = result
    for old, new in reversed(replacements): check = check.replace(new, old, 1)
    require(check == source, 'Unrelated runner changes rejected')
    return result


def load_adapter():
    path = Path(frozen.__file__).resolve()
    require(life.digest(path) == FROZEN_SHA, 'Frozen runner drift')
    ns = dict(__file__=str(Path(__file__).resolve()), __name__='readonly_csr_runner_adapter')
    exec(compile(adapted_source(path.read_text()), str(path), 'exec'), ns)
    return ns


if __name__ == '__main__': load_adapter()['main']()
