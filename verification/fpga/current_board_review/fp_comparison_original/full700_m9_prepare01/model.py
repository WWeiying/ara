"""Original first700; immutable independently reviewed integer FP16 comparator."""
import importlib.util
from functools import lru_cache
from newscope import PREVIOUS, BOUND

_spec = importlib.util.spec_from_file_location('sealed_682_comparator', PREVIOUS / 'model.py')
_old = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_old)
CAP, INPUT, compare, require = _old.CAP, _old.INPUT, _old.compare, _old.require


@lru_cache(maxsize=1)
def model():
    rows = []
    for seed in range(32):
        for op in range(10):
            for vl in (0, 1, 2, 3, 256, 511, 512):
                for mode in range(4):
                    for sticky in range(2):
                        a = [INPUT[(i+seed+7*(seed//16)) % 16] for i in range(CAP)]
                        b = [INPUT[(i*3+seed*5+seed//16) % 16 if op < 4 else seed % 16]
                             for i in range(CAP)]
                        flags, allowed = sticky, []
                        for i in range(CAP):
                            bit, nv = compare(op if op < 4 else op-4, a[i], b[i] if op < 4 else b[0])
                            old = (a[i//16] >> (i % 16)) & 1
                            allowed.append([bit] if i < vl else [old] if vl == 0 else sorted({old, 1, bit}))
                            if i < vl:
                                flags |= nv
                        rows.append(dict(ordinal=len(rows)+1, seed=seed, op=op, vl=vl, mode=mode,
                                         sticky=sticky, vstart=0, a=a, b=b,
                                         mask=[(255, 170, 36, 0)[mode]]*128,
                                         allowed=allowed, flags=flags))
                        if len(rows) == BOUND:
                            require((seed, op, vl, mode, sticky) == (1, 2, 3, 1, 1), 'Source endpoint700')
                            return dict(rows=rows, calls=BOUND, capacity=CAP, predecessors=BOUND-1,
                                        result_bits=BOUND*CAP, guards=BOUND*2)
