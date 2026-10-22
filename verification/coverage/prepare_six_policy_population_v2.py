"""Sealed population successor: exact R1 cc->gcc tool identity, no broad aliases."""
import json
from pathlib import Path

import prepare_six_policy_population as prior

frozen, require = prior.frozen, prior.require
private = prior.private
SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_prepare_six_policy_population_v2.py')
CC = '/usr/bin/cc'
CC_SHA = '472ed0bac12ba95f15d484b506ff1b32cc089cc47f5253a7ff0697667501f322'
LINKS = dict(frozen.INHERITED_TOOL_LINKS, **{CC: 'gcc'})


def tool_link_identity(path):
    path = Path(path).absolute()
    if str(path) != CC:
        return frozen.tool_link_identity(path)
    require(path.is_symlink() and str(path.readlink()) == 'gcc', 'Exact cc->gcc link required')
    resolved = path.resolve(strict=True)
    require(str(resolved) == '/usr/bin/gcc' and resolved.is_file() and not resolved.is_symlink()
            and frozen.sha(resolved) == CC_SHA, 'Sealed cc resolved bytes differ')
    return dict(link_target='gcc', resolved=str(resolved), sha256=CC_SHA)


class Context(prior.Context):
    def pin(self, pins, path, expected=None):
        if str(Path(path).absolute()) != CC:
            return super().pin(pins, path, expected)
        require(expected == CC_SHA, 'cc requires exact sealed expected hash')
        identity = tool_link_identity(path)
        require(pins.get(CC, CC_SHA) == CC_SHA, 'cc pin conflict')
        pins[CC] = CC_SHA
        frozen.four.pin(pins, identity['resolved'], CC_SHA)
        return Path(path).absolute()

    def source_binding(self, pins):
        result = super().source_binding(pins)
        admission = frozen.load_sealed(self.admission / 'admission-manifest.json', self.seal)
        ledger = self.admission / 'evidence-pins.json'
        expected = admission['output_pins'][str(ledger)]
        require(frozen.sha(ledger) == expected and json.loads(ledger.read_bytes()).get(CC) == CC_SHA,
                'Additional link not bound by formal admission ledger')
        identity = tool_link_identity(CC)
        self.pin(pins, CC, CC_SHA)
        for path in (SCRIPT, TEST, Path(prior.__file__).resolve(),
                     SCRIPT.with_name('run_six_policy_population.py'),
                     SCRIPT.with_name('test_run_six_policy_population.py')):
            self.pin(pins, path)
        result['additional_admission_tool_link'] = {CC: identity}
        result['additional_link_role'] = 'Historical producer provenance only, never an EDA launch tool'
        return result

    def namespace(self):
        return dict(super().namespace(), INHERITED_TOOL_LINKS=LINKS,
                    tool_link_identity=tool_link_identity)


def read_config(output, seal):
    config = frozen.load_sealed(output / 'config.json', seal)
    context = Context(config['admitted_base'], config['admission_manifest_sha256'], config['population'])
    context.check_config(config, output)
    return context, config


prepare = prior.prepare


def verify(output, seal):
    return prior.private(prior.verify, read_config=read_config)(output, seal)


def main(argv=None):
    return prior.private(prior.main, Context=Context, read_config=read_config, verify=verify)(argv)


if __name__ == '__main__':
    main()
