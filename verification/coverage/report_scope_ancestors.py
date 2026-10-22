"""Recover selectable report ancestors from actual DVE row depth, not dots."""


def report_ancestors(rows, targets):
    stack, chains = [], {}
    for row in rows:
        raw_depth = row['Depth']
        if not isinstance(raw_depth, str) or not raw_depth.isascii() or not raw_depth.isdigit():
            raise ValueError('Invalid report depth')
        depth = int(raw_depth)
        if str(depth) != raw_depth or depth > len(stack):
            raise ValueError('Noncanonical or skipped report depth')
        name = row['Name']
        if not isinstance(name, str) or not name or name.strip() != name:
            raise ValueError('Invalid report node name')
        stack = stack[:depth] + [name]
        scope = '.'.join(stack)
        if scope in chains:
            raise ValueError('Duplicate report scope')
        chains[scope] = tuple('.'.join(stack[:i]) for i in range(1, len(stack) + 1))
    targets = set(targets)
    if not targets or not targets <= chains.keys():
        raise ValueError('Empty or missing target report scopes')
    return sorted({scope for target in targets for scope in chains[target]})
