"""Offline group contract only; native pane/attribute acquisition is not yet qualified."""
import re


def check_groups(signal, full_bits, target_bits, rows, active):
    """Rows: (exact source-bound name, excluded_0to1, excluded_1to0)."""
    full, targets = set(full_bits), set(target_bits)
    if not targets <= full or not full:
        raise ValueError('Source-bound target/full complement differs')
    found = set()
    for name, rise, fall in rows:
        match = re.fullmatch(re.escape(signal)+r'\[(\d+)(?::(\d+))?\]', name)
        if match is None:
            raise ValueError('Foreign or non-vector source-bound identity')
        left,right = int(match[1]),int(match[2] or match[1])
        if left < right:
            raise ValueError('Reversed native range')
        bits = set(range(right,left+1))
        if not bits <= full or found & bits:
            raise ValueError('Out-of-bound/overlapping native group')
        selected = bits & targets
        if selected and selected != bits:
            raise ValueError('HOLD: group crosses target/retained boundary')
        if rise not in ('0','1') or fall not in ('0','1'):
            raise ValueError('Unknown direction exclusion attribute')
        expected = str(int(active and bool(selected)))
        if rise != fall or rise != expected:
            raise ValueError('Group direction attributes differ')
        found |= bits
    if found != full:
        raise ValueError('Incomplete bit complement')
    return found
