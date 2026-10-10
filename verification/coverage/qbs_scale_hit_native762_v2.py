"""Exact empty protected-scope checksum adapter; frozen01 remains unchanged."""
import argparse
import json
from pathlib import Path
import re
from types import FunctionType, SimpleNamespace

import qbs_scale_hit_native762 as old

SOURCE_SHA = '6d53d1559a577decab0c648a87aed0fce4904669030af6c0f3666b4dfbfb16b7'
FIRST = old.life.OUT/'qbs-bank0-scale-hit120-native762-agent-20261007-01/first.el'
FIRST_SHA = 'dbde618ec5aec995fa1fbce6cdf5051ffa6dcb27e0b170597ad42ad606285043'


def parse_el(text, config):
    lines = text.splitlines()
    seen = set()
    for index, line in enumerate(lines):
        match = re.fullmatch(r'CHECKSUM: "(\d+)"',line.strip())
        if match is None: continue
        old.require(index+1 < len(lines) and lines[index+1].strip().startswith('INSTANCE:'),
                    'Empty module-only checksum lacks immediate scope binding')
        scope = lines[index+1].split(':',1)[1].strip()
        instance = next((i for i in config['instances'] if i['scope'] == scope),None)
        old.require(instance is not None and instance['signals'] == [] and
                    match[1] == instance['design_module_checksum'] and scope not in seen,
                    'Module-only checksum forbidden for target/unknown/duplicate scope')
        seen.add(scope)
        # Only normalize the checksum of a known empty protected scope. The
        # frozen parser still rejects any metric/bit subsequently put there.
        lines[index] = 'CHECKSUM: "'+match[1]+' '+instance['toggle_checksum']+'"'
    return old.parse_el('\n'.join(lines),config)


def candidate(config):
    return old.primitive.candidate(dict(config,instances=[i for i in config['instances'] if i['signals']]))


def backend():
    old.require(old.life.digest(Path(old.__file__)) == SOURCE_SHA, 'Frozen01 source drift')
    namespace = dict(vars(old),__file__=str(Path(__file__).resolve()),parse_el=parse_el)
    def save(path, value):
        if path.name == 'config.json':
            additions = {str(Path(old.__file__).resolve()):SOURCE_SHA,str(FIRST):FIRST_SHA,
                         str(Path(__file__).with_name('test_qbs_scale_hit_native762_v2.py')):
                             old.life.digest(Path(__file__).with_name('test_qbs_scale_hit_native762_v2.py'))}
            value['pins'] = old.life.merge_pins(value['pins'],additions)
            value['native_format_adapter'] = 'ONLY_KNOWN_EMPTY_PROTECTED_SCOPE_MODULE_ONLY_CHECKSUM'
            value['failed01_first_is_format_evidence_not_roundtrip_receipt'] = True
            old.life.check(value['pins'])
        old.life.save(path,value)
    namespace['life'] = SimpleNamespace(**dict(vars(old.life),save=save))
    namespace['primitive'] = SimpleNamespace(**dict(vars(old.primitive),candidate=candidate))
    for name in ('checked_config','prepare','verify','run'):
        namespace[name] = FunctionType(getattr(old,name).__code__,namespace)
    return namespace


def offline_first():
    old.require(old.life.digest(FIRST) == FIRST_SHA, 'Native format evidence drift')
    directory = FIRST.parent
    c = old.checked_config(directory,'0790000f2b500dd658b2ed0003f1e74dc9489c3456dfcb2274748ad73b33686d')
    actual = parse_el(FIRST.read_text(),c)
    expected = old.parse_el((directory/'candidate.el').read_text(),c)
    old.require(actual == expected and len(actual) == 240, 'Actual first is not exact240')
    old.require((directory/'initial-empty.el').read_bytes() ==
                (directory/'cleanup-empty.el').read_bytes() == b'', 'Failed01 cleanup not empty')
    return dict(status='FAILED01_FIRST_EXACT240_OFFLINE_FORMAT_CHECK_NOT_ROUNDTRIP',
                first_sha256=FIRST_SHA,physical_bits=120,directions=240,
                new_EDA_started=False,reset_reload_verified=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode',choices=('offline-first','prepare','check','run','verify','el'))
    parser.add_argument('--output',type=Path)
    parser.add_argument('--seal')
    parser.add_argument('--file')
    args = parser.parse_args()
    if args.mode == 'offline-first':
        print(json.dumps(offline_first()))
        return
    old.require(args.output is not None,'Output required')
    out = args.output.resolve()
    ns = backend()
    if args.mode == 'el':
        config = json.loads((out/'config.json').read_bytes())
        print(json.dumps(dict(bit_directions=len(parse_el((out/args.file).read_text(),config)))))
    elif args.mode == 'check':
        ns['checked_config'](out,args.seal)
        print('QBS_SCALE_HIT120_V2_PREPARED_CHECK_PASS_NO_EDA')
    elif args.mode == 'prepare': ns['prepare'](out)
    else: ns[args.mode](out,args.seal)


if __name__ == '__main__': main()
