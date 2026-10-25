"""Admit one exact simulator command header before the frozen semantic parser.

The caller must derive expected_argv from the reviewed build and original
simulation recipe, not trust the log header itself. Raw files remain unchanged
and must be supplied directly to the independent UVM checker.
"""
from pathlib import Path
import re
import shlex
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'reader_fault_gate'))
import executor_common as c


def command_body(text, target, expected_argv):
    c.require(type(target) is int and target > 0 and target % 64 == 0,
              'Invalid command-bound target')
    c.require(isinstance(expected_argv, (list, tuple)) and expected_argv,
              'Reviewed simulator argv required')
    argv = list(map(str, expected_argv))
    c.require(Path(argv[0]).name == 'simv' and
              argv.count(f'+READER_FAULT_TARGET={target:x}') == 1 and
              sum(a.startswith('+READER_FAULT_TARGET=') for a in argv) == 1,
              'Wrong simulator/target in reviewed argv')
    c.require(text.startswith('Command: ') and '\n' in text and
              len(re.findall(r'^Command:', text, re.M)) == 1,
              'Need exactly one leading simulator command record')
    header, body = text.split('\n', 1)
    c.require(not header.endswith('\\') and '\r' not in header and '\x00' not in header,
              'Unsupported/malformed simulator command header')
    c.require(shlex.split(header[len('Command: '):]) == argv,
              'Simulator command record differs from reviewed argv')
    return body


def check_log(text, rtl, target, expected_argv):
    return c.check.check_log(command_body(text, target, expected_argv), rtl, target)


def check_log_and_cycles(text, rtl, path, target, expected_argv):
    # Only the verified command envelope is separated; every runtime line is
    # still processed by the unchanged original log and waveform checkers.
    return c.check.check_log_and_cycles(
        command_body(text, target, expected_argv), rtl, path, target)
