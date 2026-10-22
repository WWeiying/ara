"""735 historical mask capture closure supplement; no DVE launch."""
from pathlib import Path
from types import FunctionType

import eight_policy_epoch_735_report_v5 as prior

SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_eight_policy_epoch_735_report_v6.py')
ROOT = prior.ROOT
PLAN = 'epoch-readiness-735-v6-plan.json'
AUDIT = ROOT / 'host-byte-role-audit-v6.json'
require = prior.require
base = prior.prior.base
CAPTURE = ROOT.parent / 'mask-store-cond24-native-prepared-agent-725-20261006-01'
CONFIG = CAPTURE / 'config.json'
FIRST = CAPTURE / 'first.el'
CONFIG_SHA = '79d3fab018b585106a88ff50cfa6bf4ba1a143051422a19598602a03fa99c7b5'
FIRST_SHA = 'c11b89f8ae115a50c83bd409d57d003c768991ae589656c021c5209cdb9f44a8'


def merge(pins, additions):
    result = dict(pins)
    for name, sha in additions.items():
        require(result.get(name, sha) == sha, 'Historical closure pin conflict: ' + name)
        result[name] = sha
    return result


def closure(pins, byte_paths, json_paths):
    # These are fixed historical authorities, not hashes of current replacements.
    fixed = {str(CONFIG): CONFIG_SHA, str(FIRST): FIRST_SHA}
    phase = base.CapturePhase(fixed, fixed, [str(CONFIG)], {})
    config = phase.loads(phase.bytes(CONFIG))
    phase.bytes(FIRST)
    phase.finish()
    require(config['output'] == str(CAPTURE) and
            config['schema'] == 'MASK_STORE_COND24_PREPARED_V1' and
            config['launch_supported'] is False and config['application_approval'] is False,
            'Historical prepared capture scope differs')
    require(isinstance(config['pins'], dict) and config['pins'], 'Missing historical transitive pins')
    combined = merge(merge(pins, fixed), config['pins'])
    return combined, sorted(set(byte_paths) | set(fixed)), sorted(set(json_paths) | {str(CONFIG)})


def source_plan():
    value = prior.prior.source_plan()
    pins, byte_paths, json_paths = closure(value['pins'], value['byte_paths'], value['json_paths'])
    return dict(value, pins=pins, byte_paths=byte_paths, json_paths=json_paths)


class Wiring(prior.Wiring):
    def __init__(self, pins, byte_paths, json_paths, *args, **kwargs):
        pins, byte_paths, json_paths = closure(pins, byte_paths, json_paths)
        super().__init__(pins, byte_paths, json_paths, *args, **kwargs)


class DiagnosticWiring(Wiring):
    def enter(self, phase):
        prior.prior.diagnostic_enter(self, phase)
        if self.context is not None:
            prior.bind_owner_paths(self)


def dependencies():
    return tuple(dict.fromkeys((*prior.dependencies(), SCRIPT, TEST, CONFIG, FIRST, AUDIT)))


local = prior.clone_functions(prior.prior, SCRIPT=SCRIPT, TEST=TEST, PLAN=PLAN, AUDIT=AUDIT,
    DiagnosticWiring=DiagnosticWiring, dependencies=dependencies, source_plan=source_plan)


def save(path, value):
    if path.name == PLAN:
        pins, byte_paths, json_paths = closure(value['pins'], value['byte_paths'], value['json_paths'])
        value = dict(value, pins=pins, byte_paths=byte_paths, json_paths=json_paths,
            historical_mask_closure={str(CONFIG): CONFIG_SHA, str(FIRST): FIRST_SHA})
    local.save(path, value)


formal_wiring = prior.prior.prior.prior.clone(prior.prior.prior.wiring, Wiring=Wiring)
report = prior.prior.prior.prior.clone(prior.report, wiring=formal_wiring,
    PLAN=PLAN, SCRIPT=SCRIPT, TEST=TEST, dependencies=dependencies, save=save,
    family=prior.report.family)
for function in vars(local).values():
    if isinstance(function, FunctionType) and function.__globals__.get(function.__name__) is function:
        function.__globals__['report'] = report
        function.__globals__['AUDIT_SEAL'] = None
local.report = report


if __name__ == '__main__':
    local.main()
