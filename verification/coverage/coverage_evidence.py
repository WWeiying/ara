"""Read-only admission checks for the checked extension adapter.

Optional case.precheck: {format, record, source_hashes?, log?}. Formats are
scalar-spike-v1, csr-spike-v1, rvv-spike-v1 and accel-host-v1. Paths use the
existing runner's repository-relative convention. Without precheck, only the
unambiguous gap35 native evidence filenames below are recognized. No commands
or simulations are executed here; host PASS is not a custom-instruction PASS.
"""
import importlib.util
from pathlib import Path
import re

import run_targeted_extension as base

full = base.full
require = full.require


class Evidence:
    """Keep the hashes that were actually checked, including unlisted ledgers."""

    def __init__(self):
        self.files = {}
        self.plans = {}
        self.collections = {}

    def pin(self, path, expected=None):
        path = full.absolute(path).absolute()
        require(path.is_file(), f'missing evidence: {path}')
        key = str(path)
        digest = full.base.sha256(path)
        require(expected is None or digest == expected, f'evidence hash differs: {path}')
        require(key not in self.files or self.files[key] == digest, f'evidence changed: {path}')
        self.files[key] = digest
        return path

    def hashes(self, files):
        require(isinstance(files, dict) and files, 'empty evidence hash map')
        for path, digest in files.items():
            require(isinstance(digest, str) and re.fullmatch('[0-9a-f]{64}', digest),
                    f'invalid evidence digest: {path}')
            self.pin(path, digest)

    def read(self, path):
        path = self.pin(path)
        value = full.read(path)
        self.pin(path)
        return value

    def plan(self, directory):
        directory = directory.resolve(strict=True)
        if directory not in self.plans:
            path = directory / 'plan.json'
            hashes = self.read(directory / 'plan.sha256.json')
            require(str(path) in hashes, f'unbound producer plan: {path}')
            self.hashes(hashes)
            self.plans[directory] = self.read(path)
        return self.plans[directory]

    def collection(self, directory, image, seen=None):
        directory = directory.resolve(strict=True)
        seen = set() if seen is None else seen
        require(directory not in seen, 'cyclic baseline chain')
        if directory in self.collections:
            return self.collections[directory]
        seen.add(directory)
        record = self.read(directory / 'collection.json')
        require(record['status'] in ('PASS', 'COMPLETE_WITH_FAILURES'), 'unfinished baseline')
        require(record['image'] == image, 'baseline collection image differs')
        self.hashes(record['reports'])
        plan = self.plan(directory)
        require(plan['image'] == image, 'baseline plan image differs')
        prior = (plan.get('source_selection') or {}).get('baseline')
        layouts = [directory / name for name in ('combined-dve', 'dve')
                   if str(directory / name / 'summary.csv') in record['reports']]
        require(len(layouts) == 1, f'unsupported historical report layout: {directory}')
        report_dir = layouts[0]
        for name in ('summary.csv', 'selected_tests.txt', 'waiver_status.json'):
            require(str(report_dir / name) in record['reports'], f'unbound baseline report: {report_dir}/{name}')
        inputs = report_dir / 'inputs.txt'
        # The gap33 extension schema predates inputs/ledger report pins. Bind
        # these explicitly now; this is not permission to skip their contents.
        require(str(inputs) in record['reports'] or (prior and report_dir.name == 'combined-dve' and
                not (directory / 'all-passed-outcomes.json').exists()), 'unbound baseline inputs')
        listing = self.pin(inputs).read_text().splitlines()
        require(len(listing) == record['passed'] + 1 and len(set(listing)) == len(listing) and
                listing[0] == plan['design_vdb'], 'historical DVE membership differs')
        for name in ('all-outcomes.json', 'all-passed-outcomes.json'):
            if (directory / name).exists():
                self.pin(directory / name)
        if prior:
            self.collection(Path(prior), image, seen)
        self.collections[directory] = record
        return record

    def ledger(self, directory, image, seen=None):
        directory = directory.resolve(strict=True)
        seen = set() if seen is None else seen
        require(directory not in seen, 'cyclic baseline ledger')
        seen.add(directory)
        collection = self.collection(directory, image)
        saved = directory / 'all-passed-outcomes.json'
        if saved.exists():
            require(str(saved) in collection['reports'], 'unbound baseline ledger')
            rows = self.read(saved)
        else:
            rows = [r for r in self.read(directory / 'all-outcomes.json') if r['status'] == 'PASS']
            if len(rows) != collection['passed']:
                prior = self.plan(directory)['source_selection']['baseline']
                rows = self.ledger(Path(prior), image, seen) + rows
        require(len(rows) == collection['passed'], 'baseline count differs')
        require(len({r['name'] for r in rows}) == len(rows), 'duplicate baseline names')
        return rows

    def baseline_row(self, row, image, simv):
        kind = row.get('kind')
        require(kind in ('directed', 'random', 'replay', 'uvm', 'axpy'),
                f'unsupported historical row type: {kind}')
        require(row.get('status') == 'PASS' and row.get('passed_only') is True and
                row.get('vdb_valid') is True and row.get('reused') is False and
                row.get('returncode') == 0, 'baseline row is not independent PASS')
        self.hashes(row['files'])
        vdb = Path(row['vdb']).resolve(strict=True)
        targets = [p for p in vdb.parents if p.parent.name == 'results' and p.name == row['name']]
        require(len(targets) == 1, 'unsupported historical result layout')
        target = targets[0]
        directory = target.parent.parent
        plan = self.plan(directory)
        self.collection(directory, image)
        require(plan['image'] == image and plan['simv'] == simv, 'producer image differs')
        cases = [c for c in plan['cases'] if c['name'] == row['name']]
        require(len(cases) == 1, 'missing/ambiguous producer case')
        case = cases[0]
        for key in ('kind', 'elf_sha256', 'coverage_test', 'contract'):
            require(row[key] == case[key], f'baseline {key} differs from producer')
        require(case['contract'] == full.contract(case), 'producer contract differs')
        require(self.read(directory / 'outcomes' / (row['name'] + '.json')) == row,
                'baseline differs from independent producer outcome')
        self.pin(case['frozen_elf'], row['elf_sha256'])

        def bound(path):
            require(str(path) in row['files'], f'baseline row does not bind {path}')
            return path

        if kind in ('directed', 'random', 'replay'):
            summaries = self.read(bound(target / 'summary.json'))
            require(len(summaries) == 1, 'baseline summary count differs')
            summary = summaries[0]
            require(full.batch.classify(summary, row['returncode']) == 'PASS' and
                    summary['name'] == case['source_name'], 'baseline summary is not this case PASS')
            artifact = Path(summary['artifact_dir']).resolve(strict=True)
            require(artifact.is_relative_to(target), 'foreign baseline artifact')
            expected_vdb = artifact / ('work/code.vdb' if kind == 'directed' else 'code.vdb')
            require(vdb == expected_vdb, 'baseline VDB not bound to audited artifact')
            metadata = self.read(bound(artifact / 'inputs.json'))
            require(metadata['simv']['image_sha256'] == plan['wrapper_image'], 'baseline metadata image differs')
            require(metadata['binary']['sha256'] == row['elf_sha256'], 'baseline metadata ELF differs')
            self.pin(bound(artifact / 'input.elf'), row['elf_sha256'])
            if kind != 'directed':
                require(metadata['spike']['sha256'] == case['spike_sha256'], 'baseline Spike differs')
            full.batch.audit_ok(self.read(bound(target / 'independent_audit.json')), case, artifact)
            if case.get('fault_vstart_probe'):
                capture = self.read(bound(target / 'fault_vstart_capture.json'))
                diagnostic = case['diagnostic_probe']
                digest = plan['files'].get(diagnostic, case['source_files'].get(diagnostic))
                require(digest is not None, 'unbound fault-vstart diagnostic')
                self.pin(diagnostic, digest)
                self.pin(bound(artifact / 'run.vcs.log'), capture['log_sha256'])
                require(capture['status'] == 'CAPTURE_CONFIRMED' and
                        full.probe_capture(artifact, Path(diagnostic)) == capture,
                        'baseline fault-vstart capture differs')
        else:
            require(vdb == target / 'code.vdb', 'foreign UVM VDB')
            report = self.read(bound(target / 'uvm_result.json'))
            require(full.uvm_verdict(row['returncode'], report) == 'PASS' and not report.get('issues'),
                    'baseline UVM verdict failed')
            require(self.read(bound(target / 'independent_uvm_audit.json')) == report,
                    'baseline independent UVM audit differs')
            require(report['elf_sha256'] == row['elf_sha256'] and report['sim_image_sha256'] == image,
                    'baseline UVM identity differs')
            require(row.get('simulator_returncode') in (None, 0), 'baseline simulator failed')
            self.pin(bound(target / 'work/input.elf'), row['elf_sha256'])
            log_path = self.pin(bound(target / 'work/run.vcs.log'), report['log_sha256'])
            self.pin(bound(target / 'work/vector_trace.csv'), report['vector_trace_sha256'])
            log = log_path.read_text(errors='replace')
            reset = case.get('reset', {})
            require(report['reset_kind'] == reset.get('kind'), 'baseline reset contract differs')
            if reset.get('kind') == 'state':
                require(full.reset_target_matches(log, reset['target']), 'baseline reset target differs')
            if case.get('cycle_limit') is not None:
                require(full.cycles(log_path) <= case['cycle_limit'], 'baseline cycle limit exceeded')
            if case.get('required_markers'):
                require(all(m in log for m in case['required_markers']) and not
                        re.search(r'^FAIL(?:[ :]|$)|FAILED|Fatal:|Error:', log, re.M),
                        'baseline required markers failed')


def precheck(item, evidence):
    """Validate native saved prechecks, then return an explicit normalized schema."""
    name = item['name']
    stem = name.split(':', 1)[1]
    paths = [evidence.pin(p) for p in item['evidence']]
    sources = [evidence.pin(p) for p in item['sources']]
    require(paths and sources and item.get('source_audit'), 'missing source/evidence audit')

    def named(filename):
        matches = [p for p in paths if p.name == filename]
        require(len(matches) == 1, f'missing/ambiguous precheck evidence: {filename}')
        return matches[0]

    explicit = item.get('precheck')
    if explicit is None:
        candidates = []
        if stem.startswith('scalar_gap35_'):
            candidates.append({'format': 'scalar-spike-v1', 'record': str(named('spike_results.json')),
                               'source_hashes': str(named('sources.json'))})
        if stem.startswith('csr_gap35_'):
            candidates.append({'format': 'csr-spike-v1', 'record': str(named(stem + '.evidence.json')),
                               'source_hashes': str(named('source_hashes.json')),
                               'log': str(named(stem + '.spike.log'))})
        if stem.startswith('vgap35_'):
            candidates.append({'format': 'rvv-spike-v1', 'record': str(named('spike_results.json'))})
        if stem.startswith(('qbs_gap35_', 'akv_gap35_')):
            candidates.append({'format': 'accel-host-v1', 'record': str(named(stem + '.precheck.json'))})
        require(len(candidates) == 1, f'unsupported/ambiguous precheck format: {name}')
        explicit = candidates[0]
    schema = dict(explicit)
    fmt = schema['format']
    require(fmt in ('scalar-spike-v1', 'csr-spike-v1', 'rvv-spike-v1', 'accel-host-v1'),
            f'unsupported precheck format: {fmt}')
    record_path = evidence.pin(schema['record'])
    require(record_path in paths, 'precheck record not listed in evidence')
    record = evidence.read(record_path)
    if fmt in ('scalar-spike-v1', 'rvv-spike-v1'):
        require(isinstance(record, list), 'Spike results must be a list')
        matches = [r for r in record if r.get('test') == name]
        require(len(matches) == 1, 'missing/ambiguous Spike case record')
        record = matches[0]
    require(record.get('name' if fmt == 'accel-host-v1' else 'test') ==
            (stem if fmt == 'accel-host-v1' else name), 'precheck case identity differs')
    binary_key = 'binary' if fmt in ('rvv-spike-v1', 'accel-host-v1') else 'elf'
    elf = evidence.pin(item['binary'], record[binary_key + '_sha256'])
    require(evidence.pin(record[binary_key]) == elf, 'precheck ELF path differs')
    hashes = record.get('source_hashes')
    if fmt in ('scalar-spike-v1', 'csr-spike-v1'):
        source_path = evidence.pin(schema['source_hashes'])
        require(source_path in paths, 'source hash manifest not listed in evidence')
        hashes = evidence.read(source_path)
    evidence.hashes(hashes)
    hashed_sources = {full.absolute(p).resolve() for p in hashes}
    compiled = [p for p in sources if p.suffix.lower() in ('.c', '.h', '.s', '.ld', '.cc', '.cpp')]
    require(compiled and all(p.resolve() in hashed_sources for p in compiled),
            'precheck does not bind all declared compile sources')

    if fmt == 'accel-host-v1':
        require(name.startswith('app:'), 'host reference requires app case')
        require({full.absolute(p).resolve() for p in record['sources']} == hashed_sources,
                'host source manifest differs')
        require(full.absolute(record['host_reference']).resolve() in hashed_sources,
                'unbound host reference source')
        require(record['custom_instruction_execution_prechecked'] is False and
                record['vcs_launched'] is False, 'host precheck scope differs')
        log_path = evidence.pin(record['host_log'])
    else:
        require(name.startswith('rvv:'), 'Spike precheck requires rvv case')
        status = 'SPIKE_PASS_RTL_NOT_RUN' if fmt == 'scalar-spike-v1' else 'PASS'
        require(record['returncode'] == 0 and record['status'] == status, 'precheck is not Spike PASS')
        command = record['command']
        require(isinstance(command, list) and len(command) >= 3, 'missing Spike command')
        tool_hash = record.get('spike_tool_sha256')
        evidence.pin(command[0], tool_hash)
        spike = record.get('spike_binary', record.get('spike_elf', command[-1]))
        spike_hash = record['spike_elf_sha256'] if fmt == 'csr-spike-v1' else record['spike_sha256']
        require(evidence.pin(spike, spike_hash) == evidence.pin(command[-1]), 'Spike command ELF differs')
        log_path = evidence.pin(record.get('log', record.get('spike_log', schema.get('log'))))
    require(log_path in paths, 'precheck PASS log not listed in evidence')
    if schema.get('log'):
        require(evidence.pin(schema['log']) == log_path, 'precheck log path differs')
    log = log_path.read_text()
    require(not re.search(r'(?im)^\s*(?:FAIL(?:ED)?\b|Fatal:|Error:)', log), 'precheck log contains failure')
    if fmt == 'accel-host-v1':
        passed = re.findall(r'^PASSED: ' + re.escape(stem) + r' checks=([1-9][0-9]*) errors=0$', log, re.M)
        require(len(passed) == 1 and log.strip() == record['host_result'], 'host reference PASS differs')
    elif fmt == 'csr-spike-v1':
        validator = evidence.pin(full.ROOT / 'verification/tests/build_gap35_csr.py')
        require(str(validator) in hashes, 'CSR validator not bound to precheck')
        spec = importlib.util.spec_from_file_location('checked_csr_precheck', validator)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        observed = module.validate_log(stem, log)
        require(all(record.get(k) == v for k, v in observed.items()), 'CSR log/record differs')
    else:
        prefix = stem if fmt == 'scalar-spike-v1' else 'gap35'
        counts = re.findall(r'^' + re.escape(prefix) + r' checks=([1-9][0-9]*) failures=0$', log, re.M)
        require(len(counts) == 1, 'missing/failing selfcheck count')
        if fmt == 'scalar-spike-v1':
            marker = 'PASSED: ' + stem
        else:
            mains = [p for p in compiled if p.name == stem + '.c']
            require(len(mains) == 1, 'missing RVV test source')
            marker = 'PASSED: ' + str(mains[0]) + '!'
        require(log.splitlines().count(marker) == 1 and
                sum(line.startswith('PASSED:') for line in log.splitlines()) == 1, 'missing/ambiguous PASS marker')
    schema.update(record=str(record_path), log=str(log_path))
    return {'name': name, 'status': 'PASS', 'precheck': schema,
            'elf_sha256': record[binary_key + '_sha256'], 'log_sha256': evidence.files[str(log_path)],
            'scope': 'host-reference-only' if fmt == 'accel-host-v1' else 'Spike-only'}


def validate(selection):
    evidence = Evidence()
    spec = evidence.read(selection)
    original = evidence.plan(base.ORIGINAL)
    cases = [precheck(item, evidence) for item in spec['cases']]
    print(f'CHECKED prechecks: {len(cases)} PASS', flush=True)
    prior = full.absolute(spec['baseline']).resolve(strict=True)
    rows = evidence.ledger(prior, original['image'])
    for index, row in enumerate(rows, 1):
        try:
            evidence.baseline_row(row, original['image'], original['simv'])
        except Exception as error:
            raise ValueError(f'baseline {row.get("name")}: {error}') from error
        if index % 100 == 0:
            print(f'CHECKED baseline evidence: {index}/{len(rows)}', flush=True)
    inputs = evidence.pin(prior / 'combined-dve/inputs.txt')
    require(inputs.read_text().splitlines() == [original['design_vdb'], *[r['vdb'] for r in rows]],
            'baseline DVE membership differs')
    bits = evidence.read(spec['baseline_bits'])
    require(bits['tests'] == [r['vdb'] for r in rows], 'baseline bitmap membership differs')
    evidence.hashes(bits['input_hashes'])
    return evidence, rows, cases
