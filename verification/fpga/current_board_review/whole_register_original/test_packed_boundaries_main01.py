"""Independent original geometry proof; not acceptance of a packed implementation."""
import hashlib
import json
from pathlib import Path


def main():
    source = Path(__file__).parent / 'prepared01/tuples.json'
    raw = source.read_bytes()
    original = json.loads(raw)
    cases, skips = [], []
    words = partial = empty = full = 0
    for seed in range(3):
        data = bytes((i * 37 + seed * 71 + 3) & 255 for i in range(1024))
        assert data == data[:256] * 4
        for op in range(20):
            for mode in range(5):
                n = 1 << (op // 4 if op < 16 else op - 16)
                width = 1 << (op % 4 if op < 16 else mode)
                if mode == 4 and op >= 16:
                    width = 1
                evl = n * 128 // width
                for index, start in enumerate((0, 1, evl // 2, evl, evl + 1)):
                    row = dict(seed=seed, op=op, mode=mode, index=index,
                               start=start, bytes=width, registers=n, evl=evl)
                    excluded = start > evl or start >= 1024 or (mode == 4 and op >= 16)
                    (skips if excluded else cases).append(row)
                    if excluded:
                        continue
                    lo, hi = 32 + start * width, 32 + n * 128
                    wanted = bytes(data[i - 32] if lo <= i < hi else 91
                                   for i in range(1088))
                    for offset in range(0, 1088, 8):
                        mask = sum(255 << (8 * j) for j in range(8)
                                   if lo <= offset + j < hi)
                        sentinel = int.from_bytes(b'\x5b' * 8, 'little')
                        payload = int.from_bytes(data[offset - 32:offset - 24], 'little') if mask else 0
                        value = (payload & mask) | (sentinel & (~mask & ((1 << 64) - 1)))
                        assert value.to_bytes(8, 'little') == wanted[offset:offset + 8]
                        if offset < 32 or offset >= 1056:
                            assert mask == 0
                        words += 1
                        empty += mask == 0
                        full += mask == (1 << 64) - 1
                        partial += mask not in (0, (1 << 64) - 1)
    assert cases == original['cases'] and skips == original['skipped']
    assert len(cases) == 1134 and len(skips) == 366 and words == 154224
    print(json.dumps(dict(status='PASS_GEOMETRY_ONLY_NOT_PACKED_IMPLEMENTATION',
                          calls=len(cases), exclusions=len(skips), words=words,
                          partial_words=partial, empty_words=empty, full_words=full,
                          source_sha256=hashlib.sha256(raw).hexdigest()), sort_keys=True))


if __name__ == '__main__':
    main()
