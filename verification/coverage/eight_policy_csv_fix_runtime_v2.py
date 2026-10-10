"""Offline CSV/runtime seal and exact native roundtrip successor; never launches DVE."""
import argparse
import ast
from collections import Counter
import hashlib
import inspect
import json
from pathlib import Path
import re
from types import SimpleNamespace

import eight_policy_csv_fix_runtime as prior

require = prior.require
DEFAULT = prior.frozen.OUT / 'eight-policy-csv-fixed-729-agent-20261006-01'
DEFAULT_SEAL = 'f965477b2bfeace138c85563245b7f4e70e0701a0b3ad4499e85ef29a58301bb'
QUOTED = r'"((?:\\[\x20-\x7e]|[^"\\\n])*)"'


def records(raw):
    """Retain every serialized record attribute; only record/block order is ignored."""
    parsed = []
    identities = set()
    for owner, chunk in prior.eight.metric.blocks(raw):
        scope, module, metric, kind = owner
        annotation = None
        count = 0
        for line in chunk.decode('ascii').splitlines()[2:]:
            match = re.fullmatch('ANNOTATION: '+QUOTED, line)
            if match:
                require(annotation is None, 'Repeated/unconsumed annotation')
                annotation = match[1]
                continue
            if kind == 'Branch':
                match = re.fullmatch(r'Branch ([0-9]+) "([0-9]+)" '+QUOTED+
                                    r' \(([0-9]+)\) '+QUOTED, line)
            else:
                match = re.fullmatch(r'Condition ([0-9]+) "([0-9]+)" '+QUOTED+
                                    r' \(([0-9]+) "([01]+)"\)', line)
            require(match is not None and annotation is not None,
                    'Unknown/incomplete native record or attribute')
            native, checksum, expression, selector, signature = match.groups()
            identity = (scope, kind, native, selector)
            require(identity not in identities, 'Duplicate native identity')
            identities.add(identity)
            parsed.append((scope, module, metric, kind, native, checksum,
                           expression, selector, signature, annotation))
            annotation = None
            count += 1
        require(count > 0 and annotation is None, 'Empty block/dangling annotation')
    return parsed


def compare(left, right):
    a, b = records(left), records(right)
    require(Counter(a) == Counter(b), 'Exact native identity/attribute multiset differs')
    canonical = json.dumps(sorted(a), ensure_ascii=True, separators=(',', ':')).encode('ascii')
    return dict(records=len(a), kinds=dict(Counter(r[3] for r in a)),
                canonical_sha256=hashlib.sha256(canonical).hexdigest(),
                exact_attributes_equal=True, exact_bytes_equal=left == right,
                record_order_equal=a == b)


def sealed_runtime(output, seal):
    """The CSV plan and runtime facade have separate, mandatory expected hashes."""
    output = Path(output).absolute()
    require(output.parent == prior.frozen.OUT and output.resolve() == output,
            'Unsafe successor evidence path')
    plan = prior.frozen.load_sealed(output / prior.PLAN, seal)
    require(plan['schema'] == 'EIGHT_CSV_DEPENDENCY_ONLY_SUCCESSOR_V1' and
            plan['output'] == str(output) and
            (plan['targets'], plan['protected'], plan['audited']) == prior.COUNTS,
            'CSV plan identity differs')
    path = output / 'runtime-plan.json'
    require(str(path) in plan['pins'], 'Missing independently pinned runtime seal')
    runtime_seal = plan['pins'][str(path)]
    runtime = prior.frozen.load_sealed(path, runtime_seal)
    require(runtime['output'] == str(output) and runtime['population'] == plan['population'] and
            runtime['admission_sha256'] == plan['admission_sha256'],
            'Runtime population/admission identity differs')
    return plan, runtime, runtime_seal


def diagnostic(output, seal):
    output = Path(output).absolute()
    plan, runtime, runtime_seal = sealed_runtime(output, seal)
    observed = {}
    def pinned(path):
        path = Path(path)
        require(path.resolve() == path and not path.is_symlink() and str(path) in plan['pins'],
                'Missing/aliased diagnostic source pin: ' + str(path))
        require(prior.frozen.sha(path) == plan['pins'][str(path)], 'Diagnostic source drift')
        observed[str(path)] = plan['pins'][str(path)]
        return path.read_bytes()
    config = json.loads(pinned(output / 'config.json'))
    sources = dict(six=pinned(Path(runtime['six_output']) / 'combined.el'),
                   lzc=pinned(prior.eight.SOURCE_PROOF / 'candidate60.el'),
                   snapshot=pinned(prior.eight.MASK_EL))
    left, right = [(output / name).read_bytes() for name in ('applied.el', 'reloaded.el')]
    summary = compare(left, right)
    # Existing per-policy native identity/parameter binders, not a record-count substitute.
    bindings = [prior.eight.split_bind(raw, config, sources, runtime['snapshot_candidates'])
                for raw in (left, right)]
    log = (output / 'DVEfiles/dve_gui.log').read_text()
    errors = [line for line in log.splitlines() if re.match(r'(?:SEVEN|EIGHT)_(?:ERROR|FAILED)', line)]
    files = [output / name for name in ('applied.el', 'reloaded.el', 'status.json', 'DVEfiles/dve_gui.log')]
    files += [Path(__file__).resolve(), Path(__file__).with_name('test_eight_policy_csv_fix_runtime_v2.py')]
    return dict(status='OFFLINE_NATIVE_ROUNDTRIP_DIAGNOSTIC_NOT_QUALIFICATION',
                csv_plan_sha256=seal, runtime_plan_sha256=runtime_seal,
                population=plan['population'], comparison=summary,
                native_binding_checks_passed=True, native_binding_results=bindings,
                gui_failure_markers=errors, original_status=json.loads((output / 'status.json').read_bytes()),
                full_protected_and_report_verification=False, application_approval=False,
                aggregate_admission=False, simulations_started=False, dve_started=False,
                input_pins={**observed, **{str(p):prior.frozen.sha(p) for p in files},
                            str(output / prior.PLAN):seal,
                            str(output / 'runtime-plan.json'):runtime_seal})


def read_config(output, seal):
    sealed_runtime(output, seal)
    return prior.read_config(output, seal)


def semantic_equal(left, right):
    compare(left, right)
    return True


def verifier(output, seal):
    """Change only seal dispatch and the exact export equality predicate."""
    output = Path(output).absolute()
    _, _, runtime_seal = sealed_runtime(output, seal)
    facade = SimpleNamespace(**vars(prior.frozen))
    def load(path, expected):
        if Path(path) == output / 'runtime-plan.json':
            require(expected == seal, 'Unexpected CSV/runtime seal dispatch')
            return prior.frozen.load_sealed(path, runtime_seal)
        return prior.frozen.load_sealed(path, expected)
    facade.load_sealed = load
    tree = ast.parse(inspect.getsource(prior.eight.verify))
    needle = ast.parse("f.read_bytes()==(output/'applied.el').read_bytes()", mode='eval').body
    class Replace(ast.NodeTransformer):
        count = 0
        def visit_Compare(self, node):
            if ast.dump(node) == ast.dump(needle):
                self.count += 1
                return ast.copy_location(ast.parse(
                    "semantic_equal(f.read_bytes(),(output/'applied.el').read_bytes())", mode='eval').body, node)
            return self.generic_visit(node)
    adapter = Replace()
    tree = adapter.visit(tree)
    require(adapter.count == 1, 'Frozen native equality boundary differs')
    namespace = dict(vars(prior.eight), frozen=facade, read_config=read_config,
                     semantic_equal=semantic_equal)
    exec(compile(ast.fix_missing_locations(tree), str(Path(__file__)), 'exec'), namespace)
    return namespace['verify']


def verify(output, seal):
    output = Path(output).absolute()
    # Keep the original GUI failure as a hard rejection, never offline approval.
    log = (output / 'DVEfiles/dve_gui.log').read_text()
    require(not re.search(r'(?:SEVEN|EIGHT)_(?:ERROR|FAILED)', log), 'Original GUI session failed')
    result = verifier(output, seal)(output, seal)
    require(log.splitlines().count('EIGHT_CSV_WRITER_INSTALLED') == 1,
            'Missing CSV-before-init evidence')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('diagnose', 'verify'))
    parser.add_argument('--output', type=Path, default=DEFAULT)
    parser.add_argument('--seal', default=DEFAULT_SEAL)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    result = diagnostic(args.output, args.seal) if args.mode == 'diagnose' else verify(args.output, args.seal)
    if args.report:
        report = args.report.absolute()
        require(args.mode == 'diagnose' and report.parent == prior.frozen.OUT and
                report.resolve() == report and not report.exists(), 'Fresh external diagnostic JSON required')
        with report.open('x') as stream:
            json.dump(result, stream, indent=2, sort_keys=True)
            stream.write('\n')
        print(json.dumps(dict(report=str(report), sha256=prior.frozen.sha(report),
                              status=result['status'], comparison=result['comparison'])))
    else:
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
