"""Narrow successor: cache immutable source expectations, never actual events."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OLD = HERE.parent / 'reference_entry01'
BASE_SHA = '127f35ed84cdc77ed1a2132d1a991a0bfd0e8922afb9299bed418d417da13e8a'
source = OLD / 'checker.py'
if hashlib.sha256(source.read_bytes()).hexdigest() != BASE_SHA:
    raise ValueError('Sealed FP32 checker drift')
spec = importlib.util.spec_from_file_location('sealed_fp32_reference_checker', source)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
require = base.require
parse_line = base.parse_line
word = base.word
MASK = base.MASK
DECODER = base.DECODER
elf_image = base.elf_image


def full_config():
    config = json.loads((HERE / 'spec.json').read_text())
    config['code'] = {int(k): v for k, v in config['code'].items()}
    gold = json.loads((HERE.parent / 'software01/generated01/model.json').read_text())['rows']
    return config, gold


class Checker(base.Checker):
    def __init__(self, config, gold):
        super().__init__(config, gold)
        self._setup_ordinal = None
        self._source_setup = None

    def setup_store(self, pc, address, value, width):
        require(self.cap == 3 and self.pre == 6 and self.step == 0 and self.active is None,
                'Fresh store phase')
        g = self.current()
        i = self.freshmap[pc]
        if self._setup_ordinal != self.calls:
            # Gold/spec are pinned, read-only inputs. The builder remains pure.
            expected = tuple(self.expected_setup(g))
            require(len(expected) == 49, 'Complete source expected setup')
            self._source_setup = expected
            self._setup_ordinal = self.calls
        require(i == self.fresh and (address, value, width) == self._source_setup[i],
                'Exact49 fresh store PC/order/value/width')
        self.fresh += 1
        self.counts['fresh_stores'] += 1


def audit(path):
    config, gold = full_config()
    check = Checker(config, gold)
    try:
        with path.open() as f:
            for line in f:
                check.consume(parse_line(line))
        return check.finish()
    except BaseException as error:
        raise ValueError(str(error) + ' context=' + repr(check.current_context)) from error
