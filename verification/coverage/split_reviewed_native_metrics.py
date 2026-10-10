"""Exact-byte proposal splitter only; not a DVE reload or application verifier."""
import re


def require(ok, message):
    if not ok:
        raise ValueError(message)


def blocks(raw):
    require(type(raw) is bytes and raw and raw.endswith(b'\n') and
            not re.search(rb'[^\x0a\x20-\x7e]', raw), 'Noncanonical native bytes')
    require(raw.startswith(b'CHECKSUM:'), 'Unexpected native preamble')
    result = []
    for chunk in re.split(rb'(?m)(?=^CHECKSUM:)', raw):
        if not chunk:
            continue
        lines = chunk.decode('ascii').splitlines()
        checksum = re.fullmatch(r'CHECKSUM: "([0-9]+) ([0-9]+)"', lines[0])
        require(checksum and len(lines) >= 3, 'Invalid checksum/header')
        scope = re.fullmatch(r'INSTANCE: ?([A-Za-z_][A-Za-z0-9_]*(?:\[[0-9]+\])?'
                             r'(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[[0-9]+\])?)*)', lines[1])
        require(scope, 'Invalid native scope')
        kinds = set()
        for line in lines[2:]:
            if not line or line.startswith('//'):
                continue
            if line.startswith('ANNOTATION: "') and line.endswith('"'):
                continue
            directive = re.match(r'(Branch|Condition) [0-9]+ ', line)
            require(directive, 'Unknown native directive/type')
            kinds.add(directive[1])
        require(len(kinds) == 1, 'Whole-instance or mixed directive block')
        result.append(((scope[1], checksum[1], checksum[2], next(iter(kinds))), chunk))
    return result


def split_exact(raw, reviewed_sources):
    """Route by scope/module/metric/type, then preserve every approved source byte.

    Callers must hash-bind the reviewed_sources independently. Reordered or
    rewritten DVE exports intentionally require their existing semantic verifier,
    rather than gaining approval through this proposal-only utility.
    """
    require(reviewed_sources, 'No reviewed allowlist')
    owners, allowed = {}, {}
    output = {name: [] for name in reviewed_sources}
    for name, source in reviewed_sources.items():
        for identity, chunk in blocks(source):
            require(identity not in owners or owners[identity] == name, 'Ambiguous metric ownership')
            owners[identity] = name
            require(chunk not in allowed, 'Duplicate reviewed block')
            allowed[chunk] = name
    for identity, chunk in blocks(raw):
        require(identity in owners, 'Unknown scope/type/checksum')
        require(chunk in allowed, 'Changed or duplicate reviewed record block')
        owner = allowed.pop(chunk)
        require(owners[identity] == owner, 'Metric owner differs')
        output[owner].append(chunk)
    require(not allowed, 'Missing reviewed block')
    result = {name: b''.join(chunks) for name, chunks in output.items()}
    require(result == reviewed_sources, 'Reviewed per-policy order/bytes changed')
    return result
