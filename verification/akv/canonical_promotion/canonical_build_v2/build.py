#!/usr/bin/env python3
"""Exact canonical graph successor; compile only after parent approval."""
import argparse
import hashlib
import importlib.util
from pathlib import Path
import sys
from types import FunctionType

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
FROZEN_SHA = '99063bec061c3417cddb2a17555d5348822d05779c1c65406d668551017762fa'


def load(name, path, sha=None):
    if sha is not None and hashlib.sha256(path.read_bytes()).hexdigest() != sha:
        raise ValueError('Frozen helper drift: ' + str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def clone(function, replacements):
    namespace = dict(function.__globals__)
    namespace.update(replacements)
    result = FunctionType(function.__code__, namespace, function.__name__,
                          function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    return result


original = load('canonical_build_v2_frozen', HERE.parent / 'canonical_soc/build.py', FROZEN_SHA)
graph = load('canonical_build_v2_graph', HERE.parent / 'canonical_graph_v2/graph.py')
FILES = tuple(HERE / n for n in ('build.py', 'test_build.py', 'README.md'))


def source_inputs():
    pins = {str(path): sha for path, sha in graph.inputs().items()}
    original.verify(pins)
    for path in FILES:
        pins[str(path)] = original.digest(path)
    return pins


def auxiliary_inputs(tools):
    pins = original.auxiliary_inputs(tools)
    for path, sha in source_inputs().items():
        original.require(path not in pins or pins[path] == sha, 'Conflicting v2 input pin: ' + path)
        pins[path] = sha
    return pins


run = clone(original.run, dict(expected_graph=graph.expected_graph, auxiliary_inputs=auxiliary_inputs))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=7200)
    parser.add_argument('--execute', action='store_true', help='Compile only, after actual canonical promotion')
    run(parser.parse_args())
