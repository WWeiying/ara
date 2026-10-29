#!/usr/bin/env python3
"""Audit filelist ordering differences; does not admit a simulator image."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect(path):
    tokens = [s.strip() for s in path.read_text().splitlines() if s.strip()]
    defines, includes, sources = {}, set(), []
    for token in tokens:
        if token.startswith('+define+'):
            name, _, value = token[len('+define+'):].partition('=')
            if name in defines and defines[name] != value:
                raise ValueError('Conflicting definition: ' + name)
            defines[name] = value
        elif token.startswith('+incdir+'):
            includes.add(token[len('+incdir+'):])
        elif token.startswith('+'):
            raise ValueError('Unsupported option: ' + token)
        else:
            sources.append((token, dict(defines), sorted(includes)))
    return tokens, sources, includes


def audit(expected, actual):
    a, sa, ia = inspect(expected)
    b, sb, ib = inspect(actual)
    if Counter(a) != Counter(b) or sa != sb:
        raise ValueError('Source order or per-source macro/include environment differs')
    candidates = defaultdict(dict)
    for directory in ia | ib:
        root = Path(directory)
        for path in root.rglob('*'):
            if path.is_file():
                candidates[path.relative_to(root).as_posix()][str(path)] = digest(path)
    conflicts = {name: paths for name, paths in candidates.items()
                 if len(set(paths.values())) > 1}
    return dict(state='ORDER_AUDIT_NEEDS_INCLUDE_REVIEW' if conflicts else 'ORDER_AUDIT_PASS',
                source_count=len(sa), token_count=len(a),
                same_source_order_and_per_source_options=True,
                conflicting_include_candidates=conflicts,
                input_sha256={str(p): digest(p) for p in (expected, actual)},
                simulator_admitted=False, simulation_executed=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('expected', type=Path)
    parser.add_argument('actual', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.expected, args.actual)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(result['state'], 'include conflicts:', len(result['conflicting_include_candidates']))
