"""Same experiment, explicit scalar VRF publication; no retry of original run."""
from pathlib import Path
import run_gap114_fsm as core

core.APP=core.life.ROOT/'apps/riscv-tests/isa/rv64uv/vgap114_spec_load_flush_v2.c'
core.PRE=core.life.OUT/'gap114-spec-load-flush-preflight-742-20261007-02'
core.RUN=core.life.OUT/'gap114-spec-load-flush-old-image-742-20261007-02'
original_build=core.build


def build():
    pre,bits=original_build()
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_run_gap114_fsm_v2.py'),
              core.APP.with_name('vgap114_spec_load_flush.c')):
        pre['pins']=core.life.merge_pins(pre['pins'],{str(p):core.life.digest(p)})
    core.life.check(pre['pins'])
    # A fresh successor record; retain the original generated preflight unchanged.
    core.life.save(core.PRE/'successor-preflight.json',pre)
    pre['pins'][str(core.PRE/'successor-preflight.json')]=core.life.digest(core.PRE/'successor-preflight.json')
    return pre,bits


core.build=build
if __name__=='__main__':
    try:core.main()
    except Exception as exc:
        dest=core.RUN if core.RUN.exists() else core.PRE
        if dest.exists() and not (dest/'failure.json').exists():
            core.life.save(dest/'failure.json',dict(reason=str(exc),no_retry=True,coverage_admitted=False))
        raise
