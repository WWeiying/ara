"""735 fixed-worker IPC boundary; no blanket Path writes or child capture claim."""
import re
import sys
import hashlib
import os
from pathlib import Path
from types import FunctionType, MethodType

import eight_policy_epoch_735_report_v7 as prior

SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_eight_policy_epoch_735_report_v8.py')
ROOT = prior.ROOT
PLAN = 'epoch-readiness-735-v8-plan.json'
AUDIT = ROOT / 'host-byte-role-audit-v8.json'
require = prior.require
base = prior.prior.prior.prior.base
TOOL_READS = {
    '/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/bin/dve':
        '5569ad017057029a00c09e22e29ec45ed0fdc1d3f26a01fbd62051ab6c2f6d9e',
    '/usr/bin/xvfb-run': 'b7ed85056b81e27ce2da8abbd13867c9687a23b342b18e8cfc6d3bc91dddcc54',
    '/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/gui/dve/linux64/bin/dve.exe':
        '96c4a9ad127821f21bfea04f3af62b8483b8c6fe630fe51dacb014fbb41d59ef',
    '/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/gui/dve/bin/getarch_dve':
        'fae1c68b3c8161799c423d15b1f80755220f6bb35f39b4805c9cc689fcb7c13b',
}


def tool_roles(pins, byte_paths):
    require(all(pins.get(p) == h for p, h in TOOL_READS.items()), 'Missing/conflicting sealed tool role')
    return sorted(set(byte_paths) | set(TOOL_READS))


def source_plan():
    value = prior.source_plan()
    return dict(value, byte_paths=tool_roles(value['pins'], value['byte_paths']))


def finish_phase(phase):
    result = type(phase).finish(phase)
    phase.guard(not getattr(phase, 'tail_hash_finished', False), 'Tail hash may run only once')
    checked, count = set(), 0
    try:
        for name in phase.pins:
            endpoint = phase.capture(name)
            if endpoint in checked:
                continue
            expected, info = phase.pins[name], phase.endguards[endpoint]
            digest, size = hashlib.sha256(), 0
            with os.fdopen(os.open(endpoint, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
                phase.guard(base._identity(os.fstat(stream.fileno())) == info, 'Tail descriptor changed before read')
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    size += len(block)
                    phase.guard(size <= info[3], 'Tail file grew')
                    digest.update(block)
                phase.guard(base._identity(os.fstat(stream.fileno())) == info, 'Tail descriptor changed during read')
            phase.guard(size == info[3] and digest.hexdigest() == expected, 'Fresh tail SHA differs')
            phase.capture(name)
            checked.add(endpoint)
            count += size
        # Recheck every literal/known-link binding after all endpoint reads.
        phase.check_pins(phase.pins)
        phase.tail_hash_finished = True
    except Exception:
        phase.failed = True
        raise
    result.update(fresh_tail_endpoint_hashes=len(checked), fresh_tail_bytes=count)
    return result
INVOKE_MODULES = {'apply_branch_combo_701', 'apply_branch_combo_five_701',
                  'apply_branch_combo_six_latest'}
BOUNDARY = ('Only fixed original invoke code writes derived config.json/native.el '
            'inside its private TemporaryDirectory. Original Python workers are NOT '
            'PathClosure-captured. Sealed inputs are checked before/after each worker; '
            'original bindings still compares exact records/binding/dependencies.')


def fixed_invoke(owner, function):
    module = sys.modules[function.__module__]
    original = module.invoke
    require(function.__code__ is original.__code__, 'Worker invoke code differs')
    script = str(module.SCRIPT)

    def invoke(group, config, raw, states=None):
        require(group in module.GROUPS and isinstance(config, dict) and type(raw) is bytes,
                'Foreign worker input contract')
        require(script in owner.phase.pins and str(Path(sys.executable)) in owner.phase.pins,
                'Unbound fixed worker/Python executable')
        if states is not None:
            for stage in module.STAGES:
                require(str(states / ('states_' + stage + '.tsv')) in owner.phase.pins,
                        'Unbound worker state observation')
        # Hash every declared input, not just helper code, before a non-captured child.
        owner.phase.check_pins(owner.phase.pins)
        try:
            result = original(group, config, raw, states)
        finally:
            owner.phase.check_pins(owner.phase.pins)
        require(isinstance(result, dict) and
                set(result) in ({'records', 'binding_sha256', 'audited', 'dependencies'},
                                {'records', 'binding_sha256', 'audited', 'dependencies', 'after_root_audited'}),
                'Unknown worker output schema')
        require(type(result['records']) is int and result['records'] == module.COUNTS[group][0] and
                re.fullmatch(r'[0-9a-f]{64}', result['binding_sha256']) and
                type(result['audited']) is int and result['audited'] == (sum(module.COUNTS[group]) if states else 0),
                'Worker records/binding/audit contract differs')
        if 'after_root_audited' in result:
            require(type(result['after_root_audited']) is int and
                    result['after_root_audited'] == (sum(module.COUNTS[group]) if states else 0),
                    'Worker after-root audit differs')
        dependencies = result['dependencies']
        require(isinstance(dependencies, dict) and dependencies and dependencies.get(script) == owner.phase.pins[script]
                and all(owner.phase.pins.get(p) == h for p, h in dependencies.items()),
                'Worker returned unbound/conflicting dependencies')
        owner.phase.check_pins(dependencies)
        owner.worker_ipc_boundaries.append(dict(script=script, script_sha256=owner.phase.pins[script],
            group=group, records=result['records'], binding_sha256=result['binding_sha256'],
            dependencies=dependencies, derived_files=['config.json', 'native.el'],
            child_reads_captured=False, sealed_source_checks='before_and_after',
            original_invoke_code=True, parent_exact_binding_check_retained=True))
        return result

    return invoke


class PathClosure(prior.PathClosure):
    def module(self, original, label):
        if getattr(original, '__name__', None) == 'dve_tool_identity':
            # Retain the existing ELF-header/streaming-seal adapter, not BytesIO fileno.
            return self.owner.tool
        return super().module(original, label)

    def function(self, original):
        if original.__name__ == 'invoke' and original.__module__ in INVOKE_MODULES:
            if original not in self.functions:
                self.functions[original] = fixed_invoke(self.owner, original)
            return self.functions[original]
        return super().function(original)


class Wiring(prior.Wiring):
    def __init__(self, pins, byte_paths, json_paths, *args, **kwargs):
        super().__init__(pins, tool_roles(pins, byte_paths), json_paths, *args, **kwargs)
        self.worker_ipc_boundaries = []
        PathClosure(self).install()

    def enter(self, phase):
        super().enter(phase)
        self.phase.finish = MethodType(finish_phase, self.phase)


class DiagnosticWiring(Wiring):
    def enter(self, phase):
        prior.DiagnosticWiring.enter(self, phase)
        self.phase.finish = MethodType(finish_phase, self.phase)


def dependencies():
    return tuple(dict.fromkeys(p for p in (*prior.dependencies(), SCRIPT, TEST, AUDIT)
                              if p != prior.AUDIT))


local = prior.prior.prior.clone_functions(prior.prior.prior.prior,
    SCRIPT=SCRIPT, TEST=TEST, PLAN=PLAN, AUDIT=AUDIT, DiagnosticWiring=DiagnosticWiring,
    dependencies=dependencies, source_plan=source_plan)


def save(path, value):
    if path.name == PLAN:
        pins, byte_paths, json_paths = prior.prior.closure(value['pins'], value['byte_paths'], value['json_paths'])
        byte_paths, json_paths = prior.read_roles(pins, byte_paths, json_paths)
        byte_paths = tool_roles(pins, byte_paths)
        value = dict(value, pins=pins, byte_paths=byte_paths, json_paths=json_paths,
            historical_mask_closure={str(prior.prior.CONFIG): prior.prior.CONFIG_SHA,
                                     str(prior.prior.FIRST): prior.prior.FIRST_SHA},
            isolated_worker_boundary=BOUNDARY, child_worker_reads_captured=False)
    local.save(path, value)


clone = prior.clone
formal_wiring = clone(prior.formal_wiring, Wiring=Wiring)
report = clone(prior.report, wiring=formal_wiring, PLAN=PLAN, SCRIPT=SCRIPT, TEST=TEST,
               dependencies=dependencies, save=save, family=prior.report.family)
for function in vars(local).values():
    if isinstance(function, FunctionType) and function.__globals__.get(function.__name__) is function:
        function.__globals__['report'] = report
        function.__globals__['AUDIT_SEAL'] = None
local.report = report


if __name__ == '__main__':
    local.main()
