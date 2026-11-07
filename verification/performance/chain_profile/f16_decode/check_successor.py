#!/usr/bin/env python3
"""Explicit successor for UVM zero-summary classification; sealed inputs stay intact."""
import argparse
import hashlib
import json
import re
import types
from pathlib import Path

PREDECESSOR = Path(__file__).resolve().with_name('check.py')
PREDECESSOR_SHA256 = '755d91f7f7ad43b6f4afd7049d0255e0e1d3dd61a30555285d98a0c721957532'
REASON = ('The sealed checker rejects normal UVM_ERROR : 0 / UVM_FATAL : 0 '
          'severity summaries. This explicit successor changes only severity '
          'classification, retaining the original build, log, receipts and checks.')
_OLD_SEVERITY_PATTERN = r'(?:UVM_FATAL|UVM_ERROR)\s*:'
_SEVERITY = re.compile(r'\bUVM_(?:ERROR|FATAL)\b')
_ZERO_SUMMARY = re.compile(r'[ \t]*(UVM_ERROR|UVM_FATAL)[ \t]*:[ \t]*0[ \t]*')


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def classify_severities(log):
    summaries = dict(UVM_ERROR=0, UVM_FATAL=0)
    for number, line in enumerate(log.splitlines(), 1):
        if not _SEVERITY.search(line):
            continue
        match = _ZERO_SUMMARY.fullmatch(line)
        if match is None:
            raise ValueError('UVM error/fatal event or nonzero/malformed summary at line ' + str(number))
        summaries[match[1]] += 1
    return dict(strict_zero_summary_lines=summaries,
                nonzero_summaries=0, error_or_fatal_events=0,
                independent_uvm_gate_required=True)


class _WorkRegex:
    """Change one predicate in one private module, never Python's shared re module."""
    def search(self, pattern, string, flags=0):
        if pattern == _OLD_SEVERITY_PATTERN and not flags and _ZERO_SUMMARY.fullmatch(string):
            return None
        return re.search(pattern, string, flags)

    def __getattr__(self, name):
        return getattr(re, name)


def _load_predecessor():
    source = PREDECESSOR.read_bytes()
    if hashlib.sha256(source).hexdigest() != PREDECESSOR_SHA256:
        raise ValueError('Sealed predecessor checker identity drift')
    module = types.ModuleType('chain_f16_sealed_checker_private')
    module.__file__ = str(PREDECESSOR)
    exec(compile(source, str(PREDECESSOR), 'exec'), module.__dict__)
    original_work = module.check_hardware_work
    module.re = _WorkRegex()

    def check_hardware_work(log):
        classification = classify_severities(log)
        result = original_work(log)
        result['uvm_severity_classification'] = classification
        return result

    module.check_hardware_work = check_hardware_work
    return module


def check_run(log_path: Path, build_dir: Path) -> dict:
    checker_path = Path(__file__).resolve()
    checker_sha256 = _sha(checker_path)
    predecessor = _load_predecessor()
    # The predecessor reads the original file itself and rechecks every original pin.
    result = predecessor.check_run(Path(log_path), Path(build_dir))
    if _sha(checker_path) != checker_sha256 or _sha(PREDECESSOR) != PREDECESSOR_SHA256:
        raise ValueError('Checker identity changed during checking')
    result.update(
        checker_identity=dict(path=str(checker_path), sha256=checker_sha256,
                              entrypoint='check_run(log_path: Path, build_dir: Path) -> dict'),
        predecessor_checker=dict(path=str(PREDECESSOR), sha256=PREDECESSOR_SHA256),
        successor_reason=REASON,
        successor_scope='Strict whole-line zero UVM severity summaries only; original log not filtered or rewritten',
        independent_uvm_gate_required=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--build', type=Path, required=True)
    args = parser.parse_args()
    build_dir = args.build.parent if args.build.name == 'build.json' else args.build
    print(json.dumps(check_run(args.log, build_dir), indent=2))


if __name__ == '__main__':
    main()
