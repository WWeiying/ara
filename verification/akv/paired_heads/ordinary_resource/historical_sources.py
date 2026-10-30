"""Exact old ELF source recovery; never alias an old pin to current source bytes."""
import hashlib
from pathlib import Path
import subprocess
from types import FunctionType, SimpleNamespace

COMMIT = '585866f9661b0dc7adf9b9853746a983e884d0de'
SOURCES = {
    'software/akv/src/akv_v2_attention_rvv.S':
        '4afab7919fc05ea0cd3a54559f391532d24f4d0fa7fe8f7750caaa64aa185abe',
    'software/akv/src/akv_v2_native_riscv.c':
        'f345307eea2bcc888d9df951ff2c14982ff6821cbf0d00d870c04492052c75cb',
}


class HistoricalSources:
    def __init__(self, root, directory, tools):
        self.root, self.directory, self.s = root, directory, tools

    def bindings(self):
        return {str(self.root / name): dict(sha256=sha, archived=str(self.directory / Path(name).name))
                for name, sha in SOURCES.items()}

    def materialize(self):
        # Check both git objects before creating any archive; no checkout/write to sources.
        data = {}
        for name, sha in SOURCES.items():
            value = subprocess.check_output(['git', '-C', str(self.root), 'show', COMMIT + ':' + name], timeout=30)
            self.s.require(hashlib.sha256(value).hexdigest() == sha, 'Historical git object mismatch')
            data[name] = value
        self.directory.mkdir(parents=True, exist_ok=False)
        for name, value in data.items():
            (self.directory / Path(name).name).write_bytes(value)
        self.s.atomic_json(self.directory / 'bindings.json', dict(commit=COMMIT, bindings=self.bindings(),
            scope='Historical compiled ELF source only; current canonical software is not asserted byte-equal'))
        self.checked_pins()

    def checked_pins(self):
        receipt = self.directory / 'bindings.json'
        report = self.s.read_json(receipt)
        self.s.require(report.get('commit') == COMMIT and report.get('bindings') == self.bindings(),
                       'Historical source binding drift')
        pins = {str(self.directory / Path(name).name): sha for name, sha in SOURCES.items()}
        self.s.verify_pins(pins)
        self.s.merge_pins(pins, self.s.hashes([receipt]))
        return pins

    def translate(self, pins):
        out = dict(pins)
        for original, binding in self.bindings().items():
            if original in out:
                self.s.require(out.pop(original) == binding['sha256'], 'Unexpected historical source version')
                self.s.merge_pins(out, {binding['archived']: binding['sha256']})
        self.s.merge_pins(out, self.checked_pins())
        return out

    def verify(self, pins):
        self.s.verify_pins(self.translate(pins))

    @staticmethod
    def clone(function, **replacements):
        # Private function globals, identical frozen code; never patch imported modules.
        namespace = dict(function.__globals__, **replacements)
        return FunctionType(function.__code__, namespace, function.__name__, function.__defaults__, function.__closure__)

    def validators(self, original, context):
        build = self.clone(original.checked_build, verify_pins=self.verify)
        prior = SimpleNamespace(**dict(vars(original), checked_build=build))
        tools = SimpleNamespace(**dict(vars(context.s), verify_pins=self.verify))
        prerequisite = self.clone(context.checked_prerequisite, prior=prior, s=tools)
        return build, prerequisite
