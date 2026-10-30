"""Consume one frozen ordinary baseline after promotion; never launch tools."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OLD = ROOT / 'verification/akv/paired_heads/ordinary_resource'
HISTORY = ROOT / 'verification/out/ordinary-rvv-unified-20261025-01/historical-source'
ARCHIVE = HERE.parent / 'historical_inputs/archive-01'
ARCHIVE_SHA = 'd958c77b3e6e966b7e2b22920d6cbc3358466defc65abcef71a8299a3b4c1674'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(OLD))
contract = load('promotion_ordinary_frozen_contract', OLD / 'contract.py')
a = load('promotion_ordinary_history_archive', HERE.parent / 'historical_inputs/archive.py')
s = contract.s


class Consumer:
    def __init__(self, archive=ARCHIVE):
        self.archive = a.Archive(archive, ARCHIVE_SHA)
        s.require(self.archive.root == ROOT, 'Wrong historical root')
        self.history = contract.HistoricalSources(ROOT, HISTORY, s)
        self.history.checked_pins()
        self.cloned = self.validators()

    def translate(self, pins):
        # Five hardware/build identities and two software identities stay disjoint.
        return self.history.translate(self.archive.mapped_pins(pins))

    def verify(self, pins):
        s.verify_pins(self.translate(pins))

    def validators(self):
        clone = contract.HistoricalSources.clone
        original, context = contract.original, contract.context
        build = clone(original.checked_build, verify_pins=self.verify)
        image = clone(original.checked_image, verify_pins=self.verify)
        prior = SimpleNamespace(**dict(vars(original), checked_build=build,
                                      checked_image=image, verify_pins=self.verify))
        context_tools = SimpleNamespace(**dict(vars(context.s), verify_pins=self.verify))
        prerequisite = clone(context.checked_prerequisite, prior=prior, s=context_tools)
        private_context = SimpleNamespace(**dict(vars(context), checked_prerequisite=prerequisite))
        evidence = clone(contract.consumed_evidence, s=prior)
        checked = clone(contract.checked_baseline, original=prior, context=private_context,
                        s=prior, consumed_evidence=evidence)
        return SimpleNamespace(build=build, image=image, prerequisite=prerequisite,
                               evidence=evidence, baseline=checked)

    def support_pins(self):
        pins = {str(self.archive.payload / p): h for p, h in self.archive.report['payload'].items()}
        s.merge_pins(pins, s.hashes([self.archive.directory / 'manifest.json']))
        s.merge_pins(pins, self.history.checked_pins())
        files = [*HERE.glob('*.py'), HERE / 'README.md', Path(a.__file__),
                 Path(contract.__file__), OLD / 'historical_sources.py', Path(sys.executable).resolve()]
        for module in tuple(sys.modules.values()):
            name = getattr(module, '__file__', None)
            if name:
                path = Path(name).resolve()
                if path.is_relative_to(ROOT) and path.is_file():
                    files.append(path)
        s.merge_pins(pins, s.hashes(files))
        return pins

    def checked_baseline(self, directory=contract.DEFAULT_BASELINE, build=contract.DEFAULT_BUILD):
        directory, build = Path(directory).resolve(strict=True), Path(build).resolve(strict=True)
        s.require(directory == contract.DEFAULT_BASELINE and build == contract.DEFAULT_BUILD,
                  'Only the reviewed frozen ordinary baseline/build are admitted')
        before = self.support_pins()
        s.verify_pins(before)
        # Raw keys must survive intermediate prerequisite containment checks.
        report, parsed, records, raw_pins = self.cloned.baseline(directory, build)
        pins = self.translate(raw_pins)
        s.merge_pins(pins, before)
        a.Archive(self.archive.directory, ARCHIVE_SHA)
        s.require(self.support_pins() == before, 'Consumer dependency inventory drift')
        s.verify_pins(pins)
        return report, parsed, records, pins


def checked_baseline(directory=contract.DEFAULT_BASELINE, build=contract.DEFAULT_BUILD):
    """Same four-value contract, with seven historical keys translated in final pins."""
    return Consumer().checked_baseline(directory, build)
