"""Offline raw mutation utilities; work when the original delta omits fflags."""
import re


def insert_nv(line):
    pattern = r'\bc1_fflags\s+0x[0-9a-f]+'
    if re.search(pattern, line):
        return re.sub(pattern, 'c1_fflags 0x0000000000000010', line, count=1)
    return line.rstrip('\n') + ' c1_fflags 0x0000000000000010\n'
