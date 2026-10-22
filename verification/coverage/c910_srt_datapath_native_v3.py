"""Private candidate-load successor; only actual native exports qualify scope."""
import argparse
import contextlib
import importlib.util
import io
from pathlib import Path
import re
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ORIGINAL = HERE / 'c910_srt_datapath_native.py'
ORIGINAL_SHA = 'e7d3cf19e46c28cf0a0290e16dafd9dca5eb695172e8249157f86ed992de90a5'
spec = importlib.util.spec_from_file_location('c910_native_private_v3', ORIGINAL)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
base.require(base.life.digest(ORIGINAL) == ORIGINAL_SHA, 'Frozen predecessor drift')
original_life = base.life
dependencies = {str(ORIGINAL): ORIGINAL_SHA,
                str(HERE / 'c910_srt_datapath_native.tcl'):
                '194889eb9a2a23f99fcb9731f52957e9bb8da7ea13d8c803256766710225bf36',
                str(HERE / 'test_c910_srt_datapath_native.py'):
                'bc72143ff95fd43691229cba1fd1e7a20b1efcce1e0ed6608dab8e78f06a6a1d'}


def merge_pins(left, right):
    return original_life.merge_pins(original_life.merge_pins(left, right), dependencies)


base.life = SimpleNamespace(**vars(original_life))
base.life.merge_pins = merge_pins
base.SCRIPT = Path(__file__).resolve()
base.TCL = base.SCRIPT.with_suffix('.tcl')
base.TEST = HERE / 'test_c910_srt_datapath_native_v3.py'
original_prepare, original_verify = base.prepare, base.verify


def calibration_kind(text, config):
    first = config['instances'][0]
    target = next(s for s in first['signals'] if s['name'] == 'cur_rem')
    base.require(target['source_type'] == 'reg', 'Calibration source is not reg')
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    meaningful = [line for line in lines if not line.startswith('ANNOTATION:')]
    base.require(len(meaningful) == 3 and meaningful[:2] == [
        'CHECKSUM: "%s %s"' % (first['design_module_checksum'], first['toggle_checksum']),
        'INSTANCE: ' + first['scope']], 'Calibration scope/checksum differs')
    for line in lines:
        if line.startswith('ANNOTATION:'):
            base.require(re.fullmatch(r'ANNOTATION: "[^"\r\n]*"', line), 'Bad annotation')
    match = re.fullmatch(r'Toggle cur_rem "(reg|logic) cur_rem\[60:0\]"', meaningful[2])
    base.require(match is not None, 'Calibration declaration differs')
    return match.group(1)


def candidate_text(config, kind):
    base.require(kind in ('reg', 'logic'), 'Unmeasured declaration kind')
    lines = []
    for instance in config['instances']:
        lines += ['CHECKSUM: "%s %s"' % (instance['design_module_checksum'],
                                         instance['toggle_checksum']),
                  'INSTANCE: ' + instance['scope']]
        for signal in instance['signals']:
            declared = 'logic' if kind == 'logic' else signal['source_type']
            lines.append('Toggle %s "%s %s[%d:%d]"' % (signal['name'], declared,
                         signal['name'], signal['left'], signal['right']))
    text = '\n'.join(lines) + '\n'
    base.parse_el(text, config)
    return text


def prepare(out):
    reference = base.life.OUT / 'fma-datapath-108-native-agent-20261007-02'
    result = base.life.read_bound(reference / 'capture-result.json',
                                  base.life.digest(reference / 'capture-result.json'))
    base.require(result['status'] == 'EXACT_108_FMA_TOGGLE_OBJECTS_NATIVE_ROUNDTRIP_PASS',
                 'FMA10802 not qualified')
    reference_pins = {str(reference / name): base.life.digest(reference / name)
                      for name in ('capture-result.json', 'config.json', 'first.el', 'second.el')}
    for name in ('config.json', 'first.el', 'second.el'):
        base.require(result['pins'][str(reference / name)] == reference_pins[str(reference / name)],
                     'FMA10802 native export drift')
    reference_config = base.json.loads((reference / 'config.json').read_bytes())
    base.require(base.fma.parse_el((reference / 'first.el').read_text(), reference_config) ==
                 base.fma.parse_el((reference / 'second.el').read_text(), reference_config),
                 'FMA10802 native signatures differ')
    original_save = base.life.save

    def save(path, data):
        if path == out / 'config.json':
            data = dict(data)
            data['pins'] = merge_pins(data['pins'], reference_pins)
            data['method'] = 'ONE_REG_NATIVE_CALIBRATION_THEN_EXACT_CANDIDATE_LOAD'
        original_save(path, data)

    base.life.save = save
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            original_prepare(out)
    finally:
        base.life.save = original_save
    config = base.life.read_bound(out / 'config.json', base.life.digest(out / 'config.json'))
    print(base.json.dumps(dict(output=str(out), seal=base.life.digest(out / 'config.json'),
                              objects=1264, pins=len(config['pins']))), flush=True)


def verify(out, seal):
    base.require(not (out / 'error.txt').exists(), 'Native error artifact present')
    config = base.life.read_bound(out / 'config.json', seal)
    kind = calibration_kind((out / 'calibration.el').read_text(), config)
    base.require((out / 'candidate.el').read_text() == candidate_text(config, kind),
                 'Candidate differs from calibrated exact inventory')
    base.require(base.parse_el((out / 'first.el').read_text(), config) ==
                 base.parse_el((out / 'candidate.el').read_text(), config),
                 'Native exported declarations differ from candidate')
    base.require((out / 'calibration-reset-empty.el').read_bytes() == b'',
                 'Calibration reset not empty')
    original_verify(out, seal)


base.prepare, base.verify = prepare, verify


def main():
    if len(base.os.sys.argv) > 1 and base.os.sys.argv[1] == 'candidate':
        parser = argparse.ArgumentParser()
        parser.add_argument('mode')
        parser.add_argument('--output', type=Path, required=True)
        args = parser.parse_args()
        out = args.output.absolute()
        config = base.json.loads((out / 'config.json').read_bytes())
        base.life.check(config['pins'])
        kind = calibration_kind((out / 'calibration.el').read_text(), config)
        with (out / 'candidate.el').open('x') as stream:
            stream.write(candidate_text(config, kind))
        print(base.json.dumps(dict(objects=1264, calibration_type=kind)))
    else:
        base.main()


if __name__ == '__main__':
    main()
