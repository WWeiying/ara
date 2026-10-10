#!/usr/bin/env python3
"""New, separately frozen FENCE.T admission using direct-commit RVFI evidence.

The old rejected run and checker remain unchanged. UART architectural checks,
every retired opcode against ELF, all capture stores, and native controller
activity must agree. Neither static preflight nor an old-log replay admits a
VDB. Other cases retain their independent checked-extension contracts.
"""
import gzip
from pathlib import Path
import xml.etree.ElementTree as ET

import fence_rvfi_audit as rvfi
import gap37_csr_admission as csr
import run_fence_checked_extension as legacy

checked = legacy.checked
full = legacy.full
require = full.require
SCRIPT = Path(__file__).resolve()
OBSERVER_SOURCES = (
    'hardware/deps/cva6/core/cva6.sv',
    'hardware/deps/cva6/core/cva6_rvfi.sv',
    'hardware/deps/cva6/core/cva6_rvfi_probes.sv',
    'hardware/deps/cva6/core/commit_stage.sv',
    'hardware/deps/cva6/core/issue_read_operands.sv',
    'hardware/src/ara_system.sv',
    'hardware/tb/ara_commit_monitor.sv',
)


def precheck(item, proof):
    proof.pin(Path(csr.__file__))
    if csr.handles(item):
        result = csr.precheck(item, proof)
        proof.pin(SCRIPT)
        proof.pin(Path(legacy.__file__))
        proof.pin(Path(checked.__file__))
        proof.pin(Path(rvfi.__file__))
        return result
    result = legacy.precheck(item, proof)
    if item.get('precheck', {}).get('format') != 'cva6-fence-static-v1':
        return result
    directory = Path(item['precheck']['record']).resolve().parent
    binding = proof.read(directory / 'rtl_source_match.json')
    manifest = proof.pin(binding['compile_manifest'], binding['sha256'])
    compiled = {r['path']: r['sha256'] for r in proof.read(manifest)['files']}
    for relative in OBSERVER_SOURCES:
        source = full.ROOT / relative
        require(str(source) in compiled, 'RVFI source missing from compiled manifest')
        proof.pin(source, compiled[str(source)])
    proof.pin(SCRIPT)
    proof.pin(Path(rvfi.__file__))
    proof.pin(Path(legacy.__file__))
    result['runtime_contract'] = 'fence-rvfi-elf-capture-controller-v1'
    return result


def controller_proof(output, plan, row, replay=False):
    db = Path(plan['design_vdb']) / 'snps/coverage/db'
    listing = output / 'inputs/fence-rvfi-runtime-vdbs.txt'
    contents = plan['design_vdb'] + '\n' + row['vdb'] + '\n'
    if replay:
        require(listing.read_text() == contents, 'controller replay membership differs')
    else:
        with listing.open('x') as stream:
            stream.write(contents)
    full.check(plan['design_files'])
    sample = legacy.bitmaps.collect(listing, metrics=('line', 'fsm'))
    info_path = db / 'auxiliary/verilog.sourceinfo.xml'
    info = ET.parse(info_path).getroot()
    ids = [n.get('id') for n in info.iter('fileinfo')
           if Path(n.get('name')).resolve() == legacy.SOURCE.resolve()]
    require(len(ids) == 1, 'ambiguous native controller source')
    shape_path = db / 'shape/line.verilog.shape.xml'
    with gzip.open(shape_path) as stream:
        root = ET.parse(stream).getroot()
    cached = sample['metrics']['line'][legacy.INSTANCE]
    definitions = [d for d in root.iter('linedef') if d.get('chksum') == cached['checksum']]
    require(cached['checksum'] is not None and len(definitions) == 1,
            'ambiguous controller line definition')
    states = legacy.line_activity(definitions[0], cached, ids[0], legacy.SOURCE.read_text())
    fsm = sample['metrics']['fsm'][legacy.INSTANCE]
    baseline = full.read(Path(plan['baseline_bits']))['metrics']['fsm'][legacy.INSTANCE]
    require((fsm['width'], fsm['checksum']) == (baseline['width'], baseline['checksum']),
            'controller FSM shape differs')
    require(int(fsm['bits'], 16) & ~int(baseline['bits'], 16), 'no new controller FSM activity')
    files = full.pins([info_path, shape_path, listing])
    for relative, digest in sample['design'].items():
        path = str(db / relative)
        require(plan['design_files'].get(path) == digest, 'controller design evidence changed')
        files[path] = digest
    files[str(plan['baseline_bits'])] = plan['files'][str(plan['baseline_bits'])]
    files.update(sample['input_hashes'])
    full.check(files)
    return {'controller_arms': states, 'raw_fsm_bits': fsm,
            'baseline_fsm_bits': baseline, 'files': files}


def runtime_proof(output, plan, row, replay=False):
    case = next(c for c in plan['cases'] if c['name'] == legacy.NAME)
    target = output / 'results' / legacy.NAME
    summary = full.read(target / 'summary.json')[0]
    artifact = Path(summary['artifact_dir']).resolve(strict=True)
    require(artifact.is_relative_to(target), 'foreign FENCE.T artifact')
    work = artifact / 'work'
    log = work / 'run.vcs.log'
    trace = artifact / 'commit_trace.csv'
    legacy_trace = work / 'trace_hart_0_commit.log'
    for path in (log, trace, legacy_trace):
        require(str(path) in row['files'], 'unbound original runtime artifact: ' + str(path))
        full.check({str(path): row['files'][str(path)]})
    selection = full.read(Path(plan['source_selection']['selection']))
    item = next(c for c in selection['cases'] if c['name'] == 'app:' + legacy.NAME)
    record_path = Path(item['precheck']['record'])
    record = full.read(record_path)
    metadata_path = record_path.parent / 'elf_metadata.json'
    elf = Path(case['frozen_elf'])
    full.check({str(elf): record['elf_sha256']})
    # Check the metadata/oracle before use, not only during eventual aggregation.
    for path in (record_path, metadata_path, Path(rvfi.__file__), SCRIPT, legacy.SOURCE):
        require(str(path) in plan['files'], 'unbound FENCE.T runtime input: ' + str(path))
        full.check({str(path): plan['files'][str(path)]})
    uart = legacy.builder().validate_log(log.read_text(errors='strict'))
    commits = rvfi.audit(trace.read_text(errors='strict'), full.read(metadata_path)[0],
                        elf.read_bytes(), record['elf_audit']['sites'])
    control = controller_proof(output, plan, row, replay=replay)
    files = full.pins([log, trace, legacy_trace, record_path, metadata_path, elf, legacy.SOURCE])
    files.update(control.pop('files'))
    expected = {**plan['design_files'], **plan['files'], str(elf): record['elf_sha256'], **row['files']}
    require(all(expected.get(p, h) == h for p, h in files.items()),
            'runtime evidence changed after audit')
    full.check(files)
    return {'status': 'PASS', 'schema': 'fence-rvfi-elf-capture-controller-v1',
            'scope': 'scalar architecture and real controller activity; not security proof',
            'uart': uart, 'commit_evidence': commits, **control, 'files': files,
            'legacy_trace': 'preserved for diagnosis; known microreset identity mismatch, not oracle'}


def summarize(output, plan):
    for case in plan['cases']:
        if case['name'] == csr.NAME:
            row = full.read(output / 'outcomes' / (csr.NAME + '.json'))
            if row['status'] == 'PASS':
                report = output / 'results' / csr.NAME / 'csr_runtime_audit.json'
                require(str(report) in row['files'], 'unbound CSR runtime proof')
                full.check({str(report): row['files'][str(report)]})
                proof = full.read(report)
                require(proof.get('status') == 'PASS' and proof.get('files'), 'missing CSR runtime proof')
                require(all(row['files'].get(p) == h for p, h in proof['files'].items()),
                        'CSR runtime proof differs from original outcome')
                full.check(proof['files'])
                require(csr.runtime_proof(output, plan, row) == proof, 'CSR runtime proof replay differs')
            continue
        if case['name'] != legacy.NAME:
            continue
        row = full.read(output / 'outcomes' / (legacy.NAME + '.json'))
        if row['status'] != 'PASS':
            continue
        report = output / 'results' / legacy.NAME / 'fence_runtime_audit.json'
        require(str(report) in row['files'], 'unbound FENCE.T runtime proof')
        full.check({str(report): row['files'][str(report)]})
        proof = full.read(report)
        require(proof.get('schema') == 'fence-rvfi-elf-capture-controller-v1' and
                proof.get('status') == 'PASS', 'missing strict RVFI proof schema')
        require(proof['uart']['checks'] == 458 and proof['uart']['failures'] == 0 and
                proof['uart']['rounds'] == 2, 'incomplete architectural selfcheck proof')
        commit = proof['commit_evidence']
        require(commit['status'] == 'PASS' and commit['capture_stores_checked'] == 130 and
                commit['exact_pc4_resume'] is True and commit['legacy_trace_used_as_oracle'] is False,
                'incomplete direct-commit capture proof')
        require(len(proof['controller_arms']) == 6 and proof['files'], 'missing controller proof')
        require(all(row['files'].get(p) == h for p, h in proof['files'].items()),
                'runtime proof inputs differ from originating outcome')
        full.check(proof['files'])
        # Reconstruct the canonical required file set and all checks, rather
        # than trusting a status/counter-only report with missing inputs.
        require(runtime_proof(output, plan, row, replay=True) == proof,
                'FENCE.T runtime proof replay differs')
    return legacy.ORIGINAL_SUMMARIZE(output, plan)


def worker(output, name):
    rc = legacy.worker(output, name)
    if rc or name != csr.NAME:
        return rc
    path = output / 'outcomes' / (name + '.json')
    row = full.read(path)
    if row['status'] != 'PASS':
        return rc
    plan = checked.frozen(output)
    report = output / 'results' / name / 'csr_runtime_audit.json'
    try:
        proof = csr.runtime_proof(output, plan, row)
        full.save(report, proof)
        row['files'].update(proof['files'])
    except Exception as error:
        full.save(report, {'status': 'REJECTED', 'reason': f'{type(error).__name__}: {error}'})
        row.update(status='INFRASTRUCTURE_ERROR', passed_only=False,
                   reason='CSR extra admission failed; preserve evidence and stop affected queue')
        rc = 1
    row['files'].update(full.pins([report]))
    full.save(path, row)
    full.batch.publish(output, row)
    return rc


def main():
    checked.SCRIPT = SCRIPT
    legacy.evidence.precheck = precheck
    legacy.runtime_proof = runtime_proof
    full.worker = worker
    checked.summarize = summarize
    return checked.main()


if __name__ == '__main__':
    raise SystemExit(main())
