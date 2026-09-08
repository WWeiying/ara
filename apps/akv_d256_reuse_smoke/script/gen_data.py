#!/usr/bin/env python3
"""Preload deterministic bit-exact test inputs; not a performance workload."""

import struct


def emit(name, values, directive):
    print(f'.section .data,"aw",@progbits\n.balign 64\n.global {name}\n{name}:')
    values = list(values)
    for first in range(0, len(values), 8):
        print(f'  {directive} ' + ', '.join(hex(v) for v in values[first:first + 8]))


def f32(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def main():
    emit('query', ((0x3000 + (h * 113 + d * 29) % 2048) |
                  (0x8000 if (h + d) % 3 == 0 else 0)
                  for h in range(8) for d in range(288)), '.half')
    emit('key', ((0x2800 + (t * 173 + d * 37) % 3072) |
                (0x8000 if (t + d) % 5 == 0 else 0)
                for t in range(65) for d in range(288)), '.half')
    emit('value', ((0x2400 + (t * 71 + d * 53) % 4096) |
                  (0x8000 if (t + d) % 7 == 0 else 0)
                  for t in range(65) for d in range(288)), '.half')
    emit('initial_accum', (((h * 197 + d * 101) % 0x4800) |
                          (0x8000 if (h + d) % 3 == 0 else 0)
                          for h in range(8) for d in range(256)), '.half')
    emit('weights', (f32((13 + (h * 53 + t * 7) % 100) / 1024)
                     for h in range(8) for t in range(64)), '.word')
    emit('old_scale', (f32((817 + h * 17) / 1024) for h in range(8)), '.word')
    emit('token_scale', (f32(0.0 if t == 0 else
                            (0.8125 + h / 128 if (t + h) % 7 == 0 else 1.0))
                         for h in range(8) for t in range(64)), '.word')
    emit('online_weights', (f32(0.0 if (t + h) % 11 == 0 else
                               (13 + (h * 53 + t * 7) % 100) / 1024)
                            for h in range(8) for t in range(64)), '.word')


if __name__ == '__main__':
    main()
