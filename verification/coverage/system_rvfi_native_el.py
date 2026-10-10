"""Exact RVFI native serialization, including complete scalar direction pairs."""
import re

import capture_system_rvfi788_v3 as sealed


def records(text, config):
    sealed.contract(config)
    bindings = {p['compiled_name']: p for p in config['native_bindings'] if p['role'] == 'target'}
    pairs = {}
    whole = set()
    normalized = []
    pattern = re.compile(r'Toggle (0to1|1to0) (\S+)(?: \[([^\]]+)\])? "(net|wire|logic|reg) (\S+)"')
    for line in text.splitlines():
        match = pattern.fullmatch(line)
        if not match:
            if line.startswith('Toggle '):
                ordinary = re.fullmatch(r'Toggle (\S+) "(net|wire|logic|reg) (\S+)"', line)
                sealed.require(ordinary is not None, 'Unknown native toggle serialization')
                name = ordinary[1]
                sealed.require(name not in pairs and name not in whole, 'Duplicate/mixed whole-direction object')
                whole.add(name)
            normalized.append(line)
            continue
        direction, name, bit, kind, declaration = match.groups()
        binding = bindings.get(name)
        sealed.require(binding is not None and binding['width'] == 1, 'Directional object is foreign or not sole-bit')
        sealed.require(name not in whole, 'Duplicate/mixed whole-direction object')
        if name in sealed.mapping.TARGET_SCALARS:
            sealed.require(bit == '0' and declaration == binding['compiled_label'], 'Exact sole-bit vector index/bounds differ')
        else:
            sealed.require(binding['compiled_kind'] == 'node' and bit is None, 'Unexpected scalar bit selector')
        identity = (kind, declaration)
        if name not in pairs:
            pairs[name] = (identity, set())
            normalized.append('Toggle '+name+' "'+kind+' '+declaration+'"')
        previous, directions = pairs[name]
        sealed.require(previous == identity and direction not in directions, 'Duplicate/conflicting directional identity')
        directions.add(direction)
    sealed.require(all(directions == {'0to1', '1to0'} for _, directions in pairs.values()),
                   'Incomplete native direction pair')
    # The sealed parser still checks every scope/checksum/annotation/declaration and exact788 complement.
    return sealed.records('\n'.join(normalized), config)
