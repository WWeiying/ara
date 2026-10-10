"""735 reader-defaults successor; reuse exact v2 preparation, never launch DVE."""
from pathlib import Path
from types import FunctionType
import eight_policy_epoch_735_report_v2 as prior

SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_eight_policy_epoch_735_report_v3.py')
ROOT = prior.ROOT
PLAN = 'epoch-readiness-735-v3-plan.json'
SOURCE_SEAL = '73a9ac50c15b53a8ff3f71382dc9166d3d3742da60882bd032353e2a6f16c8a6'
require = prior.require


class Wiring(prior.wiring.Wiring):
    def __init__(self, pins, byte_paths, json_paths, context_factory=None, *, links=None,
                 max_bytes=768 * 1024 * 1024):
        super().__init__(pins, byte_paths, json_paths, context_factory,
                         links=links, max_bytes=max_bytes)

    def check_inputs(self, config, *, boundary=None):
        return super().check_inputs(config, boundary=boundary)


wiring = prior.clone(prior.wiring, Wiring=Wiring)


def dependencies():
    return tuple(dict.fromkeys((*prior.dependencies(), SCRIPT, TEST, ROOT / prior.PLAN)))


save = FunctionType(prior.save.__code__, dict(prior.save.__globals__, PLAN=PLAN),
                    'save', prior.save.__defaults__, prior.save.__closure__)
report = prior.clone(prior.report, wiring=wiring, SCRIPT=SCRIPT, TEST=TEST, PLAN=PLAN,
                     dependencies=dependencies, save=save)


def prepare(output):
    output = Path(output).absolute()
    require(output == ROOT, 'Only exact completed735 v2 preparation may be reused')
    source = report.Builder().load_sealed(output / prior.PLAN, SOURCE_SEAL)
    require(source['population'] == 735 and source['output'] == str(output) and
            source['admission_seal'] == prior.prior.SEAL and
            (source['targets'], source['protected'], source['audited']) == (5892, 17774, 23666),
            'Prepared735 source authority differs')
    return report.prepare_reader_entry(output, source['fixed_seal'])


def main():
    import argparse
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'check', 'verify'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal')
    args = parser.parse_args()
    if args.mode == 'prepare':
        require(args.seal is None, 'Reader preparation uses fixed exact v2 authority')
        result = dict(status='READER_PREPARED_CHECK_REQUIRED_NO_DVE', population=735,
                      seal=prepare(args.output))
    else:
        require(args.seal, 'Explicit reader seal required')
        result = report.check(args.output.absolute(), args.seal, args.mode == 'verify')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
