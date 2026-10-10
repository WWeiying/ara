"""Exact frozen preflight successor: disable loop unrolling, preserve the app."""
import hashlib
from pathlib import Path
import types

PREDECESSOR = Path(__file__).with_name('build_store_fifo_burst_preflight.py')
PREDECESSOR_SHA = '51e99d6a82f47298a72588cf3dd5b2864b71500a8df504d6521346fc8c7fa1fb'
REPLACEMENTS = (
    ("'-fno-slp-vectorize',", "'-fno-slp-vectorize', '-fno-unroll-loops',"),
    ("'test_store_fifo_burst_preflight.py'", "'test_store_fifo_burst_preflight_v2.py'"),
)


def adapted_source(raw):
    if hashlib.sha256(raw).hexdigest() != PREDECESSOR_SHA:
        raise ValueError('Frozen predecessor changed')
    source = raw.decode('ascii')
    for old, new in REPLACEMENTS:
        if source.count(old) != 1:
            raise ValueError('Not one exact replacement')
        source = source.replace(old, new, 1)
    return source


library = types.ModuleType('store_fifo_burst_v2_frozen_adapter')
library.__file__ = str(Path(__file__).resolve())
exec(compile(adapted_source(PREDECESSOR.read_bytes()), str(PREDECESSOR), 'exec'), library.__dict__)
original_binding = library.target_binding


def target_binding():
    targets, pins = original_binding()
    # The transformed program and the inherited tests retain their frozen owners.
    pins = library.life.merge_pins(pins, {
        str(PREDECESSOR): PREDECESSOR_SHA,
        str(Path(__file__).with_name('test_store_fifo_burst_preflight.py')):
            '7afae8b7976f7f6218283d8058a755691b13b69dc807b7606f3ee4cb25744967',
        str(Path(__file__).resolve()): library.life.digest(Path(__file__)),
    })
    library.life.check(pins)
    return targets, pins


library.target_binding = target_binding

if __name__ == '__main__':
    library.main()
