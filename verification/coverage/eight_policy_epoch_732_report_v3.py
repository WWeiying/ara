"""Bounded disk snapshot successor; no source re-read or larger RAM allowance."""
import hashlib
import os
from pathlib import Path
import tempfile
from types import FunctionType, SimpleNamespace

import eight_policy_epoch_732_report as prior

SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_eight_policy_epoch_732_report_v3.py')
PLAN = 'epoch-readiness-v3-plan.json'


class SpoolingCapture(prior.wiring.CapturePhase):
    """Source SHA and snapshot use the same stream; only consumed bytes use RAM."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.spool = tempfile.TemporaryFile()
        self.offsets, self.content, self.json_content = {}, {}, {}
        self.disk_limit = 8 * 1024 * 1024 * 1024

    def capture(self, name, expected=None):
        name = os.fspath(name)
        binding = self.bindings.get(name)
        endpoint = binding[0] if binding else None
        if endpoint not in self.byte_endpoints or endpoint in self.captures:
            return super().capture(name, expected)
        self.spool.seek(0, os.SEEK_END)
        offset = self.spool.tell()
        parent = self

        class Tee:
            def __init__(self, stream):
                self.stream = stream

            def fileno(self):
                return self.stream.fileno()

            def read(self, size):
                block = self.stream.read(size)
                prior.require(parent.spool.tell() + len(block) <= parent.disk_limit,
                              'Disk snapshot budget exceeded')
                parent.spool.write(block)
                return block

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.stream.close()

        proxy = SimpleNamespace(**dict(vars(os), fdopen=lambda *a, **k: Tee(os.fdopen(*a, **k))))
        original = prior.wiring.CapturePhase.capture
        function = FunctionType(original.__code__, dict(original.__globals__, os=proxy),
                                original.__name__, original.__defaults__, original.__closure__)
        self.byte_endpoints.remove(endpoint)
        try:
            actual = function(self, name, expected)
            self.offsets[endpoint] = (offset, self.spool.tell() - offset)
            return actual
        finally:
            self.byte_endpoints.add(endpoint)

    def bytes(self, path):
        endpoint = self.capture(path)
        self.guard(endpoint in self.byte_endpoints, 'Undeclared snapshot byte role')
        digest = self.captures[endpoint]
        if digest not in self.content:
            offset, count = self.offsets[endpoint]
            self.guard(self.retained + count <= self.limit, 'Consumed byte RAM budget exceeded')
            self.spool.seek(offset)
            raw = self.spool.read(count)
            self.guard(len(raw) == count and hashlib.sha256(raw).hexdigest() == digest,
                       'Disk snapshot bytes changed')
            self.content[digest] = raw
            self.retained += count
        raw = self.content[digest]
        self.raw[endpoint] = raw
        self.buffers[id(raw)] = (raw, endpoint)
        return raw

    def loads(self, data, *args, **kwargs):
        self.guard(not self.failed and not args and not kwargs, 'Failed/unreviewed parser')
        record = self.buffers.get(id(data))
        self.guard(record is not None and record[0] is data and record[1] in self.json_endpoints,
                   'Undeclared captured JSON role')
        endpoint = record[1]
        digest = self.captures[endpoint]
        if digest not in self.json_content:
            self.json_content[digest] = super().loads(data)
        self.parsed[endpoint] = self.json_content[digest]
        return self.parsed[endpoint]

    def close(self):
        self.spool.close()


class PrivateWiring(prior.wiring.Wiring):
    enter = FunctionType(prior.wiring.Wiring.enter.__code__,
                         dict(prior.wiring.Wiring.enter.__globals__, CapturePhase=SpoolingCapture),
                         'enter')


def dependencies():
    return (*prior.dependencies(), SCRIPT, TEST)


private_wiring = SimpleNamespace(**dict(vars(prior.wiring), Wiring=PrivateWiring))
namespace = dict(vars(prior), SCRIPT=SCRIPT, TEST=TEST, PLAN=PLAN,
                 dependencies=dependencies, wiring=private_wiring)
for name, function in vars(prior).items():
    if name != 'dependencies' and isinstance(function, FunctionType) and function.__module__ == prior.__name__:
        namespace[name] = FunctionType(function.__code__, namespace, name,
                                       function.__defaults__, function.__closure__)
globals().update({name: value for name, value in namespace.items() if not name.startswith('__')
                  and name not in ('prior', 'Path', 'FunctionType')})


if __name__ == '__main__':
    main()
