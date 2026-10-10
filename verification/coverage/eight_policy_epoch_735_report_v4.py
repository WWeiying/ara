"""Measured735 source-read closure; unchanged pin and product/native validators."""
import hashlib
import json
import os
from pathlib import Path
from types import FunctionType

import eight_policy_epoch_735_report_v3 as prior

SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_eight_policy_epoch_735_report_v4.py')
ROOT = prior.ROOT
PLAN = 'epoch-readiness-735-v4-plan.json'
AUDIT = ROOT / 'host-byte-role-audit-v4.json'
SOURCE_SEAL = '3dc96b012c734be5fd8fbed0688429f150e1a6a4933f5da517e34a5198bff35c'
base = prior.prior.prior.wiring_base
require = prior.require


class DiagnosticPhase(base.CapturePhase):
    """Diagnostic only: exact-SHA deferred reads expose the real reader closure.

    The formal v4 reader does NOT use this implementation. All initial pin
    reads use the original streaming hash and identity gates; consumed bytes
    are separately rehashed with the same endpoint and descriptor guards.
    """
    def __init__(self, pins, byte_paths, json_paths, links, *, max_bytes=768 * 1024 * 1024):
        byte_paths, json_paths = set(byte_paths), set(json_paths)
        require(json_paths <= byte_paths <= set(pins), 'Diagnostic roles must be sealed')
        super().__init__(pins, (), (), links, max_bytes=max_bytes)
        self.read_endpoints = {self.bindings[p][0] for p in byte_paths}
        self.json_endpoints = {self.bindings[p][0] for p in json_paths}
        self.consumed = {}
        self.leases = {}
        self.endpoint_leases = {}
        self.peak = 0
        self.consumer_reads = 0

    def release(self, data):
        key = id(data)
        record = self.buffers.get(key)
        if record and self.endpoint_leases.get(record[1]) == key:
            self.endpoint_leases.pop(record[1])
        self.retained -= self.leases.pop(key, 0)
        self.buffers.pop(key, None)

    def register(self, data, endpoint, size):
        old = self.endpoint_leases.get(endpoint)
        if old is not None:
            self.release(self.buffers[old][0])
        self.guard(self.retained + size <= self.limit, 'Diagnostic simultaneous read budget exceeded')
        self.buffers[id(data)] = (data, endpoint)
        self.leases[id(data)] = size
        self.endpoint_leases[endpoint] = id(data)
        self.retained += size
        self.peak = max(self.peak, self.retained)

    def bytes(self, path):
        try:
            name = os.fspath(path)
            endpoint = self.capture(name)
            self.guard(endpoint in self.read_endpoints, 'Undeclared diagnostic byte read')
            info = self.endguards[endpoint]
            self.guard(self.retained + info[3] <= self.limit, 'Diagnostic simultaneous read budget exceeded')
            digest = hashlib.sha256()
            data = bytearray()
            with os.fdopen(os.open(endpoint, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
                self.guard(base._identity(os.fstat(stream.fileno())) == info, 'Changed before diagnostic read')
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    data.extend(block)
                    self.guard(len(data) <= info[3], 'Grew during diagnostic read')
                    digest.update(block)
                self.guard(base._identity(os.fstat(stream.fileno())) == info, 'Changed during diagnostic read')
            self.guard(len(data) == info[3] and digest.hexdigest() == self.pins[name],
                       'Diagnostic consumed SHA differs')
            self.capture(name)
            payload = bytes(data)
            self.consumer_reads += 1
            self.consumed[name] = dict(sha256=self.pins[name], endpoint=endpoint, size_bytes=len(payload))
            if endpoint in self.json_endpoints:
                self.register(payload, endpoint, len(payload))
            return payload
        except Exception:
            self.failed = True
            raise

    def text(self, path, encoding='utf-8', errors='strict'):
        self.guard(encoding in (None, 'utf-8', 'UTF-8') and errors in (None, 'strict'),
                   'Only strict diagnostic UTF8 text')
        data = self.bytes(path)
        try:
            value = data.decode('utf-8')
        except Exception:
            self.release(data)
            self.failed = True
            raise
        endpoint = self.bindings[os.fspath(path)][0]
        self.release(data)
        if endpoint in self.json_endpoints:
            self.register(value, endpoint, len(data))
        return value

    def loads(self, data, *args, **kwargs):
        try:
            return super().loads(data, *args, **kwargs)
        finally:
            self.release(data)

    def finish(self):
        result = super().finish()
        result.update(diagnostic_only=True, consumed=self.consumed,
                      consumer_reads=self.consumer_reads, peak_simultaneous_json_bytes=self.peak)
        return result


diagnostic_enter = FunctionType(base.Wiring.enter.__code__,
    dict(base.Wiring.enter.__globals__, CapturePhase=DiagnosticPhase), 'enter')


class DiagnosticWiring(prior.Wiring):
    enter = diagnostic_enter


def source_plan():
    plan = prior.report.Builder().load_sealed(ROOT / prior.PLAN, SOURCE_SEAL)
    require(plan['population'] == 735 and plan['output'] == str(ROOT) and
            plan['admission_seal'] == prior.prior.prior.SEAL and
            (plan['targets'], plan['protected'], plan['audited']) == (5892, 17774, 23666),
            'Exact735 source plan differs')
    return plan


def audit():
    require(not AUDIT.exists(), 'Fresh role audit only')
    source = source_plan()
    wiring = prior.prior.clone(prior.wiring, Wiring=DiagnosticWiring)
    reader = prior.prior.clone(prior.report, wiring=wiring,
        dependencies=prior.dependencies, save=prior.save, family=prior.report.family)
    checked = reader.check(ROOT, SOURCE_SEAL)
    consumed = checked['epoch']['consumed']
    source_name = str(ROOT / prior.PLAN)
    require(set(consumed) <= set(source['byte_paths']) | {source_name}, 'Unexpected role consumption')
    retained = sorted(set(consumed) - {source_name})
    sizes = {p: Path(p).stat().st_size for p in source['byte_paths']}
    original_endpoints = {}
    consumed_endpoints = {}
    for p, size in sizes.items():
        endpoint = os.path.realpath(p)
        original_endpoints[endpoint] = size
        if p in consumed:
            consumed_endpoints[endpoint] = size
    result = dict(schema='735_MEASURED_SOURCE_BYTE_ROLES_V1', diagnostic_only=True,
        source_plan_sha256=SOURCE_SEAL, source_pins=source['pins'],
        consumed=consumed, byte_paths=retained,
        json_paths=sorted(set(retained) & set(source['json_paths'])),
        hash_only_paths=sorted(set(source['pins']) - set(retained)),
        original_declared_bytes=sum(sizes.values()),
        original_endpoint_bytes=sum(original_endpoints.values()),
        measured_endpoint_bytes=sum(consumed_endpoints.values()),
        largest_paths=[dict(path=p, size_bytes=sizes[p],
                           role='consume' if p in consumed else 'stream_hash_only')
                       for p in sorted(sizes, key=sizes.get, reverse=True)[:40]],
        script_sha256=prior.report.Builder().sha(SCRIPT),
        test_sha256=prior.report.Builder().sha(TEST), check=checked,
        generated_verified=False, launch_approved=False)
    prior.prior.prior.report_original.save(AUDIT, result)
    return prior.report.Builder().sha(AUDIT), result


def dependencies():
    return tuple(dict.fromkeys((*prior.dependencies(), SCRIPT, TEST, AUDIT, ROOT / prior.PLAN)))


def restrict_roles(value, source, audit_data, audit_seal):
    require(audit_data['source_pins'] == source['pins'], 'Role source pin inventory differs')
    require(set(audit_data['byte_paths']) <= set(source['byte_paths']) and
            set(audit_data['json_paths']) <= set(source['json_paths']), 'Unreviewed measured read role')
    require(all(value['pins'].get(p) == h for p, h in source['pins'].items()),
            'Role restriction removed/changed a source pin')
    allowed = set(audit_data['byte_paths']) | {str(AUDIT), str(ROOT / prior.PLAN)}
    result = dict(value)
    result['byte_paths'] = sorted(set(value['byte_paths']) & allowed)
    result['json_paths'] = sorted(set(value['json_paths']) & set(result['byte_paths']))
    result['measured_read_roles'] = dict(audit_sha256=audit_seal,
        source_plan_sha256=SOURCE_SEAL, diagnostic_not_generated_approval=True,
        original_source_pins_preserved=len(source['pins']),
        measured_endpoint_bytes=audit_data['measured_endpoint_bytes'])
    require(result['pins'] == value['pins'], 'Role restriction mutated pin checks')
    return result


def save(path, value):
    if path.name == PLAN:
        audit_data = report.Builder().load_sealed(AUDIT, AUDIT_SEAL)
        source = source_plan()
        require(audit_data['schema'] == '735_MEASURED_SOURCE_BYTE_ROLES_V1' and
                audit_data['source_plan_sha256'] == SOURCE_SEAL and
                audit_data['source_pins'] == source['pins'] and
                audit_data['script_sha256'] == report.Builder().sha(SCRIPT) and
                audit_data['test_sha256'] == report.Builder().sha(TEST), 'Measured roles authority differs')
        value = restrict_roles(value, source, audit_data, AUDIT_SEAL)
    prior.prior.prior.report_original.save(path, value)


# Formal validation uses the original capture implementation and the v3 defaults.
report = prior.prior.clone(prior.report, PLAN=PLAN, SCRIPT=SCRIPT, TEST=TEST,
                           dependencies=dependencies, save=save, family=prior.report.family)
AUDIT_SEAL = None


def prepare(audit_seal):
    global AUDIT_SEAL
    require(audit_seal and len(audit_seal) == 64, 'Explicit measured role audit seal required')
    AUDIT_SEAL = audit_seal
    source = source_plan()
    return report.prepare_reader_entry(ROOT, source['fixed_seal'])


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('audit', 'prepare', 'check', 'verify'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal')
    args = parser.parse_args()
    require(args.output.absolute() == ROOT, 'Only explicit735 output')
    if args.mode == 'audit':
        require(args.seal is None, 'Audit source plan seal is fixed')
        seal, result = audit()
        result = dict(status='MEASURED_ROLES_DIAGNOSTIC_NOT_REPORT_APPROVAL', seal=seal,
            original_bytes=result['original_declared_bytes'], measured_bytes=result['measured_endpoint_bytes'])
    elif args.mode == 'prepare':
        result = dict(status='READER_PREPARED_CHECK_REQUIRED_NO_DVE', seal=prepare(args.seal))
    else:
        require(args.seal, 'Exact readiness seal required')
        result = report.check(ROOT, args.seal, args.mode == 'verify')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
