"""Frozen 600s runner adaptation for the rodata-only preflight successor."""
from pathlib import Path
import run_readonly_csr_simulation_v2 as prior

life, require = prior.life, prior.require
PRIOR_SHA = 'dbe4a6206f0e9fdbd5c42028a83ceacc70a6334d7a832bc3593db23973837eb0'


def load_adapter():
    require(life.digest(Path(prior.__file__)) == PRIOR_SHA and
            life.digest(Path(prior.frozen.__file__)) == prior.FROZEN_SHA, 'Frozen runner predecessor drift')
    source = prior.adapted_source(Path(prior.frozen.__file__).read_text())
    for old, new in (('import build_readonly_csr_preflight_v2 as preflight',
                      'import build_readonly_csr_preflight_v3 as preflight'),
                     ("'test_run_readonly_csr_simulation_v2.py'", "'test_run_readonly_csr_simulation_v3.py'")):
        require(source.count(old) == 1 and new not in source, 'Exact two successor bindings required')
        source = source.replace(old, new, 1)
    old = 'deps = (Path('
    require(source.count(old) == 1, 'Exact runner dependency insertion required')
    source = source.replace(old, 'deps = (Path(' + repr(str(Path(prior.__file__).resolve())) + '), Path(', 1)
    ns = dict(__file__=str(Path(__file__).resolve()), __name__='readonly_csr_final_runner_adapter')
    exec(compile(source, str(Path(prior.frozen.__file__)), 'exec'), ns)
    original = ns['prepare']
    def prepare(out, directory, seal):
        manifest = original(out, directory, seal)
        manifest['raw_gain_requires_latest_formal_population_at_least'] = 734
        return manifest
    ns['prepare'] = prepare
    return ns


if __name__ == '__main__': load_adapter()['main']()
