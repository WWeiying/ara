#!/usr/bin/env python3
"""Checked extension with a narrowly audited real CVA6 FENCE.T test.

FENCE.T is not supported by the standard ISA oracle. Admission is static ELF
validation before execution, then architectural selfcheck AND native control
coverage after execution. No instruction substitution or hardware PASS is
claimed by preflight. Existing frozen collectors remain untouched.
"""
import gzip
import importlib.util
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import run_checked_extension as checked
import coverage_bitmap_delta as bitmaps

full = checked.full
evidence = checked.evidence
require = full.require
SCRIPT = Path(__file__).resolve()
NAME = 'fence_t_gap36_smoke'
INSTANCE = 'ara_tb.dut.i_ara_soc.i_system.i_ariane.controller_i'
BUILDER = full.ROOT / 'verification/tests/build_gap36_fence.py'
SOURCE = full.ROOT / 'hardware/deps/cva6/core/controller.sv'
ORIGINAL_PRECHECK = evidence.precheck
ORIGINAL_WORKER = full.worker
ORIGINAL_SUMMARIZE = checked.summarize


def builder():
    spec = importlib.util.spec_from_file_location('fence_static_audit', BUILDER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def precheck(item, proof):
    if item.get('precheck', {}).get('format') != 'cva6-fence-static-v1':
        return ORIGINAL_PRECHECK(item, proof)
    require(item['name'] == 'app:' + NAME, 'unsupported custom static precheck')
    paths = {proof.pin(p) for p in item['evidence']}
    sources = {proof.pin(p) for p in item['sources']}
    schema = item['precheck']
    record_path = proof.pin(schema['record'])
    require(record_path in paths, 'static record not declared')
    record = proof.read(record_path)
    require(record['status'] == 'STATIC_ELF_AUDIT_PASS' and
            record['test'] == item['name'], 'wrong static audit identity')
    for key in ('spike_run', 'dut_run', 'hardware_golden_pass',
                'fence_emulation_or_nop_substitution'):
        require(record[key] is False, 'static precheck scope misrepresented')
    require(record['required_runtime_checks'] == 458 and record['required_rounds'] == 2,
            'FENCE.T selfcheck contract differs')
    require(0 < item['timeout_s'] <= 600, 'unbounded FENCE.T budget')
    elf = proof.pin(item['binary'], record['elf_sha256'])
    require(proof.pin(record['elf'], record['elf_sha256']) == elf, 'static ELF differs')
    directory = record_path.parent
    hashes = proof.read(directory / 'source_hashes.json')
    proof.hashes(hashes)
    require(sources == {Path(p).resolve() for p in hashes}, 'compile source set differs')
    require(BUILDER in sources, 'unbound static validator')
    metadata = proof.read(directory / 'elf_metadata.json')[0]
    audit = builder()
    require(audit.audit_elf(metadata, elf.read_bytes()) == record['elf_audit'],
            'linked ELF audit differs')
    negatives = proof.read(directory / 'negative_audits.json')
    require(audit.negative_audits(metadata, elf.read_bytes(), record['elf_audit']) == negatives,
            'negative static audit differs')
    rtl = proof.read(directory / 'rtl_source_match.json')
    manifest = proof.pin(rtl['compile_manifest'], rtl['sha256'])
    compiled = {r['path']: r['sha256'] for r in proof.read(manifest)['files']}
    require(all(compiled.get(p) == h for p, h in rtl['matches'].items()),
            'static RTL navigation not bound to compiled image')
    proof.hashes(rtl['matches'])
    proof.pin(SCRIPT)
    proof.pin(Path(checked.__file__))
    proof.pin(Path(bitmaps.__file__))
    return {'name': item['name'], 'status': 'PASS', 'precheck': schema,
            'elf_sha256': record['elf_sha256'], 'scope': 'static-ELF-only-not-model-PASS'}


def trace_sites(text, sites):
    commits = []
    for line in text.splitlines():
        match = re.match(r'^([0-3])\s+0x([0-9a-fA-F]+)\s+\(0x([0-9a-fA-F]+)\)', line)
        require(match is not None, 'malformed architectural commit trace')
        mode, pc, word = match.groups()
        commits.append((int(mode), int(pc, 16), int(word, 16)))
    require(sum(pc == 0x80000000 for _, pc, _ in commits) == 1, 'duplicate/missing initial boot')
    positions = []
    for site in sites:
        pc, resume, auipc = (int(site[k], 16) for k in ('fence_pc', 'resume_pc', 'auipc_pc'))
        indices = [i for i, (_, addr, _) in enumerate(commits) if addr == pc]
        require(len(indices) == 1, 'missing/duplicate FENCE.T commit')
        index = indices[0]
        require(index + 2 < len(commits), 'truncated post-fence commits')
        require(commits[index] == (3, pc, 0xb), 'FENCE.T opcode/privilege differs')
        require(commits[index + 1] == (3, resume, 0x0fefb823), 'first PC+4 capture store differs')
        require(commits[index + 2] == (3, auipc, 0x00000f17), 'PC+8 capture differs')
        require(sum(addr == resume for _, addr, _ in commits) == 1 and
                sum(addr == auipc for _, addr, _ in commits) == 1, 'duplicate resume')
        positions.append(index)
    require(len(positions) == 2 and positions == sorted(positions), 'fence rounds out of order')
    return {'commits': len(commits), 'fence_commit_indices': positions,
            'rounds': 2, 'privilege': 'M', 'exact_pc4_resume': True}


def line_activity(definition, row, file_id, source):
    bits = bin(int(row['bits'], 16))[2:].zfill(row['width'])
    require(len(bits) == row['width'], 'native line width differs')
    # Each assignment lies exclusively on one normal state transition. Native
    # linebb indices are explicit; no inferred branch/FSM bit ordering is used.
    anchors = {
        'IDLE_to_FLUSH_DCACHE': ('if (fence_t_i) fence_t_state_d = FLUSH_DCACHE;',
                                'fence_t_state_d = FLUSH_DCACHE;'),
        'FLUSH_DCACHE_to_DRAIN_REQS': ('if (flush_dcache_ack_i) fence_t_state_d = DRAIN_REQS;',
                                     'fence_t_state_d = DRAIN_REQS;'),
        'DRAIN_REQS_to_PAD': ('fence_t_state_d = PAD;', 'fence_t_state_d = PAD;'),
        'PAD_to_RST_UARCH': ("if (pad_cnt == '0) fence_t_state_d = RST_UARCH;",
                            'fence_t_state_d = RST_UARCH;'),
        'RST_UARCH_assert': ("rst_uarch_no    = 1'b0;", "rst_uarch_no = 1'b0;"),
        'RST_UARCH_counter_finish': ("rst_uarch_cnt_d = 4'b0;", "rst_uarch_cnt_d = 4'b0;"),
    }
    blocks = []
    seen = set()
    for block in definition.iter('linebb'):
        index = int(block.get('index'))
        require(index not in seen and 0 <= index < len(bits), 'bad native line index')
        seen.add(index)
        blocks.append(block)
    result = {}
    for label, (statement, signature) in anchors.items():
        lines = [i for i, text in enumerate(source.splitlines(), 1) if text.strip() == statement]
        require(len(lines) == 1, 'ambiguous controller state assignment: ' + label)
        matches = [b for b in blocks if b.get('file_id') == file_id and
                   b.get('line_num') == str(lines[0]) and b.get('line_ignore') == '0' and
                   ' '.join(b.get('bbsig', '').split()) == signature and any(
                       s.get('file_id') == file_id and s.get('line_num') == str(lines[0]) and
                       s.get('line_ignore') == '0' and s.get('line_type') == '1'
                       for s in b.findall('linestmt'))]
        require(len(matches) == 1, 'ambiguous/missing native assignment block: ' + label)
        indices = [int(matches[0].get('index'))]
        require(bits[indices[0]] == '1', 'unexercised controller assignment: ' + label)
        result[label] = {'line': lines[0], 'native_linebb_indices': indices,
                         'assignment_signature': signature,
                         'hit_indices': [i for i in indices if bits[i] == '1']}
    return result


def runtime_proof(output, plan, row):
    case = next(c for c in plan['cases'] if c['name'] == NAME)
    target = output / 'results' / NAME
    summary = full.read(target / 'summary.json')[0]
    artifact = Path(summary['artifact_dir']).resolve(strict=True)
    require(artifact.is_relative_to(target), 'foreign FENCE.T artifact')
    work = artifact / 'work'
    log, trace = work / 'run.vcs.log', work / 'trace_hart_0_commit.log'
    selection = full.read(Path(plan['source_selection']['selection']))
    item = next(c for c in selection['cases'] if c['name'] == 'app:' + NAME)
    record = full.read(Path(item['precheck']['record']))
    full.check({case['frozen_elf']: record['elf_sha256'], str(SOURCE):
                full.read(Path(item['precheck']['record']).parent / 'rtl_source_match.json')['matches'][str(SOURCE)]})
    uart = builder().validate_log(log.read_text(errors='strict'))
    commits = trace_sites(trace.read_text(), record['elf_audit']['sites'])
    db = Path(plan['design_vdb']) / 'snps/coverage/db'
    listing = output / 'inputs/fence-runtime-vdbs.txt'
    with listing.open('x') as stream:
        stream.write(plan['design_vdb'] + '\n' + row['vdb'] + '\n')
    sample = bitmaps.collect(listing, metrics=('line', 'fsm'))
    info_path = db / 'auxiliary/verilog.sourceinfo.xml'
    info = ET.parse(info_path).getroot()
    ids = [n.get('id') for n in info.iter('fileinfo') if Path(n.get('name')).resolve() == SOURCE.resolve()]
    require(len(ids) == 1, 'ambiguous native controller source')
    shape_path = db / 'shape/line.verilog.shape.xml'
    with gzip.open(shape_path) as stream:
        root = ET.parse(stream).getroot()
    cached = sample['metrics']['line'][INSTANCE]
    definitions = [d for d in root.iter('linedef') if d.get('chksum') == cached['checksum']]
    require(cached['checksum'] is not None and len(definitions) == 1, 'ambiguous controller line definition')
    states = line_activity(definitions[0], cached, ids[0], SOURCE.read_text())
    fsm = sample['metrics']['fsm'][INSTANCE]
    baseline = full.read(Path(plan['baseline_bits']))['metrics']['fsm'][INSTANCE]
    require((fsm['width'], fsm['checksum']) == (baseline['width'], baseline['checksum']), 'FSM shape differs')
    require(int(fsm['bits'], 16) & ~int(baseline['bits'], 16), 'no new controller FSM activity')
    files = full.pins([log, trace, info_path, shape_path, listing])
    files.update(sample['input_hashes'])
    return {'status': 'PASS', 'scope': 'architectural identity plus real controller activity; not security proof',
            'uart': uart, 'commit_evidence': commits, 'controller_arms': states,
            'raw_fsm_bits': fsm, 'baseline_fsm_bits': baseline, 'files': files}


def worker(output, name):
    rc = ORIGINAL_WORKER(output, name)
    if rc or name != NAME:
        return rc
    path = output / 'outcomes' / (name + '.json')
    row = full.read(path)
    if row['status'] != 'PASS':
        return rc
    plan = checked.frozen(output)
    report = output / 'results' / name / 'fence_runtime_audit.json'
    try:
        proof = runtime_proof(output, plan, row)
        full.save(report, proof)
        row['files'].update(proof['files'])
    except Exception as error:
        full.save(report, {'status': 'REJECTED', 'reason': f'{type(error).__name__}: {error}'})
        row.update(status='INFRASTRUCTURE_ERROR', passed_only=False,
                   reason='FENCE.T extra admission failed; investigate without weakening checker')
        rc = 1
    row['files'].update(full.pins([report]))
    full.save(path, row)
    full.batch.publish(output, row)
    return rc


def summarize(output, plan):
    for case in plan['cases']:
        if case['name'] != NAME:
            continue
        row = full.read(output / 'outcomes' / (NAME + '.json'))
        if row['status'] == 'PASS':
            report = output / 'results' / NAME / 'fence_runtime_audit.json'
            require(str(report) in row['files'], 'unbound FENCE.T runtime proof')
            proof = full.read(report)
            require(proof['status'] == 'PASS', 'FENCE.T lacks runtime proof')
            full.check(proof['files'])
    return ORIGINAL_SUMMARIZE(output, plan)


def main():
    checked.SCRIPT = SCRIPT
    evidence.precheck = precheck
    full.worker = worker
    checked.summarize = summarize
    return checked.main()


if __name__ == '__main__':
    raise SystemExit(main())
