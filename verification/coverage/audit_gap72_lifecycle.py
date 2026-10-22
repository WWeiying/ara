"""Independent gap72 custom lifecycle, raw shape, ELF and trace oracles."""
import csv
import json
from pathlib import Path
import re
import struct
import sys
from custom_backend_lifetime import custom_write_lifetimes

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
CASE_NAMES = ('qbs_gap72_fill_abort', 'akv_gap72_tile_range')
SCHEMA = 'gap72-custom-lifecycle-runtime-v1'
BASE = ROOT / 'verification/out/closure90-current-20261005-01'
INVENTORY = ROOT / 'verification/out/closure90-zero-inventory-654-20261005-01'
DESIGN = ROOT / 'verification/out/repaired-aligned-build-20260930-01/sim/simv.vdb'
SCOPE = 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.'
SHAPES = {'qbs_engine': ('2161536777', 423), 'akv_engine': ('2836473276', 392)}
POINTS = [('qbs_engine', '150', '111', 379), ('qbs_engine', '150', '101', 381),
          ('akv_engine', '59', '001', 153)]
WORDS = {'gap72_qbs_site': 0x00b5045b, 'gap72_akv_full_site': 0x00b5605b,
         'gap72_akv_refill_site': 0x02a0605b, 'gap72_akv_load_site': 0x0005345b,
         'gap72_akv_release_site': 0x0000505b}
STEPS = {CASE_NAMES[0]: 6, CASE_NAMES[1]: 7}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text())


def csv_rows(path):
    with Path(path).open(newline='') as stream:
        yield from csv.DictReader(stream)


def sequence(name):
    require(name in CASE_NAMES, 'foreign gap72 case')
    keys = (['gap72_qbs_site'] * 6 if name == CASE_NAMES[0] else
            ['gap72_akv_full_site', 'gap72_akv_load_site', 'gap72_akv_refill_site',
             'gap72_akv_load_site', 'gap72_akv_full_site', 'gap72_akv_load_site',
             'gap72_akv_release_site'])
    return [(key, WORDS[key], int(i in (1, 2) if name == CASE_NAMES[0] else i in (2, 3)))
            for i, key in enumerate(keys)]


def golden(name, phase):
    seed = b''.join(struct.pack('<I', 0x43720000 ^ (phase << 12) ^ i) for i in range(1024))
    output = bytearray(seed)
    if name == CASE_NAMES[0] and phase in (0, 3, 4, 5):
        output[1024:1152] = struct.pack('<I', 0x43800000 if phase == 0 else 0x44000000) + bytes(124)
    elif name == CASE_NAMES[1] and phase in (1, 5):
        row = 0 if phase == 1 else 1
        output[1024:1152] = b''.join(struct.pack('<H', 0x3800 + row * 0x80 + c) for c in range(64))
    return seed, bytes(output)


def validate_log(text, name, host=False, negative=False):
    require(not re.search(r'(?im)^\s*(?:FAIL(?:ED)?\b|Error:|Fatal:)', text), 'failure in stdout')
    steps = STEPS[name]
    checks = 4 * steps + (1 if host else 4) + int(negative)
    require(re.findall(r'^PASSED: .*$', text, re.M) ==
            [f'PASSED: {name} checks={checks} errors=0'], 'PASS count/identity differs')
    require(re.findall(r'^G72_END .*$', text, re.M) ==
            [f'G72_END operations={steps} vrf_words={steps * 1024} scope=' +
             ('SOFTWARE_REFERENCE_ONLY' if host else 'DUT_CUSTOM')], 'sample scope/cardinality differs')
    return dict(checks=checks, operations=steps, vrf_words=steps * 1024,
                custom_executed=not host)


def native_targets(proof):
    import closure_point_inventory as inventory
    checkpoint = proof.read(BASE / 'checkpoint.json')
    collection = proof.read(BASE / 'collection.json')
    require(checkpoint['coverage_status'] == 'COMPLETE' and checkpoint['aggregate_passed'] == 654 and
            collection['status'] == 'PASS' and collection['passed'] == collection['total'] == 654,
            'latest 654 is not complete')
    proof.hashes(collection['reports'])
    diagnostic = proof.read(INVENTORY / 'inventory.json')
    proof.pin(INVENTORY / 'zeros.csv')
    require(diagnostic['baseline'] == str(BASE) and diagnostic['passed'] == 654,
            'foreign diagnostic inventory')
    proof.hashes(diagnostic['report_pins'])
    source_pins = proof.read(ROOT / 'verification/out/repaired-aligned-build-20260930-01/build-source-pins.json')
    # The diagnostic already validates source IDs against this frozen build.
    bits = proof.read(BASE / 'combined-bits.json')
    path = DESIGN / 'snps/coverage/db/shape/cond.verilog.shape.xml'
    proof.pin(path)
    shape = inventory.read_xml(path)
    result = []
    for module, identifier, vector, raw in POINTS:
        checksum, width = SHAPES[module]
        scope = SCOPE + 'i_' + module
        definition = [n for n in shape if n.get('chksum') == checksum]
        require(len(definition) == 1, 'missing/ambiguous native shape')
        rows = inventory.points('cond', definition[0], width)
        matches = [p for p in rows if p['native_id'] == identifier and p['vector'] == vector]
        require(len(matches) == 1 and matches[0]['raw_index'] == raw, 'raw vector reversal differs')
        point = matches[0]
        target = [p for p in diagnostic['source_points'] if p['scope'] == scope and
                  p['metric'] == 'cond' and p['raw_index'] == raw]
        require(len(target) == 1 and target[0]['native_id'] == identifier and
                target[0]['vector'] == vector and target[0]['native_dve_qualified'] is False,
                '654 diagnostic point differs')
        current = bits['metrics']['cond'][scope]
        require(current['width'] == width and current['checksum'] in (None, checksum), 'raw shape drift')
        union = format(int(current['bits'], 16), f'0{width}b')
        require(union[raw] == '0', 'candidate is no longer zero in latest 654')
        source = Path(target[0]['source'])
        proof.pin(source, target[0]['source_sha256'])
        result.append(dict(point, module=module, scope=scope, checksum=checksum, width=width,
            source=str(source), source_sha256=target[0]['source_sha256'], hit_654=0,
            native_dve_qualified=False, candidate_gain_measured=False))
    for path in ('hardware/include/qbs_pkg.sv', 'hardware/include/akv_pkg.sv',
                 'hardware/src/vlsu/qbs/qbs_activation_context.sv',
                 'hardware/src/vlsu/qbs/qbs_compute_engine.sv',
                 'hardware/src/vlsu/qbs/qbs_read_engine.sv', 'hardware/src/vlsu/vlsu.sv',
                 'verification/coverage/closure_point_inventory.py',
                 'verification/coverage/closure_scorecard.py'):
        proof.pin(ROOT / path)
    require(source_pins, 'empty frozen build manifest')
    return dict(status='STILLZERO_654_STATIC_ONLY', baseline=str(BASE), passed=654,
                design_vdb=str(DESIGN), targets=result,
                version_shape=dict(nr_lanes=4, vlen_bits=1024,
                    qbs=dict(descriptor_version=2, m=1, n=[1, 5], k_blocks=1,
                             layout='ROW_MAJOR', activation='Q8_K', weight='Q4_K',
                             context_id=0, generations=[0x71, 0x72, 0x73]),
                    akv=dict(command_version='V2', descriptor_version=1, q_rows=1,
                             head_dim=64, kv_length=3, tile_starts=[0, 3, 1])),
                measured_gain=None, native_qualification='pending parent native review')


def elf_audit(metadata, blob, name):
    symbols = {r['Symbol']['Name']['Name']: r['Symbol'] for r in metadata['Symbols']}
    def code(address, size):
        matches = []
        for row in metadata['Sections']:
            s = row['Section']
            if s['Flags']['Value'] & 4 and s['Address'] <= address and address + size <= s['Address'] + s['Size']:
                off = s['Offset'] + address - s['Address']
                matches.append(blob[off:off + size])
        require(len(matches) == 1 and len(matches[0]) == size, 'PC outside unique executable section')
        return matches[0]
    sites = {}
    wanted = {s[0] for s in sequence(name)}
    for key in wanted:
        pc = symbols[key]['Value']
        require(pc % 4 == 0 and int.from_bytes(code(pc, 4), 'little') == WORDS[key], 'raw opcode/PC differs')
        sites[key] = dict(pc=pc, word=WORDS[key])
    body_symbol = symbols['gap72_execute']
    body = code(body_symbol['Value'], body_symbol['Size'])
    require(len(body) % 4 == 0, 'compressed custom payload')
    words = [int.from_bytes(body[i:i + 4], 'little') for i in range(0, len(body), 4)]
    require(all(w & 3 == 3 for w in words), 'non32bit payload instruction')
    customs = [w for w in words if w & 127 == 0x5b]
    require(sorted(customs) == sorted(WORDS[k] for k in wanted), 'foreign/duplicate custom opcode')
    width = 6 if name == CASE_NAMES[0] else 5
    transfers = {'loads': [], 'stores': []}
    for w in words:
        if w & 127 in (7, 39) and (w >> 12) & 7 == width:
            transfers['loads' if w & 127 == 7 else 'stores'].append((w >> 7) & 31)
    require(transfers == {'loads': [0, 8, 16, 24], 'stores': [0, 8, 16, 24]}, 'incomplete full VRF image')
    capture = symbols['gap72_capture']['Value']
    csr_ids = [0xc20, 0xc21, 0x008, 0x003, 0x00f, 0x180]
    csr_sites = []
    for i, csr in enumerate(csr_ids):
        pc = capture + i * 8
        word = (csr << 20) | 0x22f3
        require(int.from_bytes(code(pc, 4), 'little') == word, 'post-custom CSR ordering differs')
        csr_sites.append(dict(pc=pc, word=word, csr=csr))
    layout = {k: symbols[k]['Value'] for k in ('__gap72_stack_bottom', '__gap72_stack_top',
              '__gap72_tail_weights', '__gap72_tail_end', '__gap72_app_end', 'rvtest_init')}
    require(layout['__gap72_stack_bottom'] == 0x80100040 and layout['__gap72_stack_top'] == 0x80110000 and
            layout['__gap72_tail_weights'] == 0x801ffdc0 and layout['__gap72_tail_end'] == 0x80200000 and
            layout['__gap72_app_end'] <= 0x800e0000, 'illegal memory layout')
    for section_name in ('.gap72_tail', '.gap72_stack'):
        sec = [r['Section'] for r in metadata['Sections'] if r['Section']['Name']['Name'] == section_name]
        require(len(sec) == 1 and sec[0]['Type']['Name'] == 'SHT_NOBITS', 'reserved memory has file payload')
    # Reuse the immutable CRT-hook decoder, not its case-specific opcode checker.
    start = symbols['_start']['Value']
    reset = code(start, symbols['trap_vector']['Value'] - start)
    mret = reset.find(bytes.fromhex('73002030'))
    calls = []
    for pos in range(0, mret - 13, 2):
        a, b = [int.from_bytes(reset[pos + off:pos + off + 4], 'little') for off in (0, 4)]
        if a & 0xfff == 0x297 and b & 0xfffff == 0x28293:
            hi, lo = a & 0xfffff000, b >> 20
            hi -= 1 << 32 if hi & 0x80000000 else 0
            lo -= 4096 if lo & 0x800 else 0
            if start + pos + hi + lo == layout['rvtest_init']:
                require(reset[pos + 8:pos + 14] == bytes.fromhex('638302008292'), 'CRT hook call differs')
                calls.append(start + pos + 12)
    require(mret >= 0 and len(calls) == 1, 'stack relocation hook not before CRT MRET')
    return dict(status='PASS_STATIC_ONLY', sites=sites, csr_sites=csr_sites, layout=layout,
                transfers=transfers, hook_call_pc=calls[0], custom_executed=False)


def software_trace(text, name):
    require('exception' not in text.lower(), 'Spike software reference trapped')
    words = [int(w, 16) for w in re.findall(r'^core\s+0:\s+0x[0-9a-f]+\s+\(0x([0-9a-f]+)\)', text, re.M)]
    require(words and all(w & 127 != 0x5b for w in words), 'Spike executed custom or trace is empty')
    commits = len(re.findall(r'^core\s+0:\s+[0-3]\s+0x', text, re.M))
    require(commits > 0, 'missing real Spike commits')
    return dict(status='PASS', instructions=len(words), retired=commits, custom_instructions=0,
                name=name, scope='Spike SOFTWARE_REFERENCE_ONLY; no custom ISA claim')


def perf_expected(name, i):
    fault = i in ((1, 2) if name == CASE_NAMES[0] else (2, 3))
    result = dict(seq=i + 1, success=int(not fault), fault=int(fault),
                  validation_fault=int(i == 2 if name == CASE_NAMES[0] else fault),
                  validation_error=(18 if i == 2 else 0) if name == CASE_NAMES[0] else
                                   (11 if i == 2 else 12 if i == 3 else 0),
                  read_fault=5 if name == CASE_NAMES[0] and i == 1 else 0)
    if name == CASE_NAMES[0]:
        access = [1, 1, 2, 1, 2, 3][i]
        reuse = i in (4, 5)
        result.update(m=1, n=5 if i == 1 else 1, vlen=1024, lanes=4,
            activation_access=access, context_fill_count=int(i in (0, 3)),
            context_reuse_count=int(reuse), context_reuse_block_count=int(reuse),
            context_read_bytes=292 if reuse else 0, activation_axi_bytes_saved=292 if reuse else 0,
            context_validation_fault_count=int(i == 2),
            payload_bytes=[452, 884, 16, 452, 160, 160][i],
            read_ranges=[3, 7, 1, 3, 2, 2][i])
        if fault:
            result['commit_groups'] = 0
    else:
        cmd = [4, 2, 5, 2, 4, 2, 3][i]
        full, load = cmd == 4, i in (1, 5)
        result.update(command=cmd, context_ready=int(i in (0, 1, 4, 5)), full=0, refill=0,
            load=int(cmd == 2), release=int(cmd == 3), v2_full=int(full), v2_refill=int(cmd == 5),
            v2_row_load=int(cmd == 2), v2_column_load=0, v2_rejected=int(i in (2, 3)),
            q_external_bytes=128 if full else 0, kv_external_bytes=768 if i == 0 else 512 if i == 4 else 0,
            replay_bytes=128 if load else 0, read_ranges=8 if i == 0 else 6 if i == 4 else 0,
            read_payload_bytes=960 if i == 0 else 704 if i == 4 else 0, translations=0)
        if not full:
            result.update(ar=0, r_beats=0)
    return result


def perf_records(text, name):
    prefix = '[QBS_PERF] ' if name == CASE_NAMES[0] else '[AKV_PERF] '
    lines = [s for s in text.splitlines() if s.startswith(prefix.rstrip())]
    require(len(lines) == STEPS[name], 'terminal PERF cardinality differs')
    rows = []
    for i, line in enumerate(lines):
        tokens = line[len(prefix):].split()
        require(line.startswith(prefix) and all(re.fullmatch('[a-z][a-z0-9_]*=[0-9]+', t) for t in tokens),
                'malformed PERF fields')
        row = {k: int(v) for k, v in (t.split('=') for t in tokens)}
        require(len(row) == len(tokens) and row.get('busy_cycles', 0) > 0 and 'id' in row,
                'duplicate/missing PERF identity')
        require(all(row.get(k) == v for k, v in perf_expected(name, i).items()),
                f'{name} phase {i} outcome/payload/context differs')
        if name == CASE_NAMES[0] and i not in (1, 2):
            require(row.get('commit_groups', 0) > 0, 'successful QBS has no result commit')
        rows.append(row)
    return rows




def trace_oracle(commit_path, vector_path, elf, name):
    sys.path.insert(0, str(ROOT / 'verification'))
    from ara_verify import vector_commit as vc
    pending, customs, retired, csr_reads = {}, [], [], []
    starts, exceptions, reqs, resps, last = [], 0, 0, 0, 0
    csr_by_pc = {s['pc']: s for s in elf['csr_sites']}
    for row in csv_rows(commit_path):
        cycle, event = int(row['cycle']), row['event']
        require(cycle >= last, 'commit cycles regress')
        last = cycle
        word, pc, key = int(row['insn'], 16), int(row['pc'], 16), int(row['trans_id'])
        if event == 'arch_start':
            starts.append((int(row['order']), word))
        elif event == 'cvx_req':
            require(key not in pending, 'duplicate live request')
            entry = dict(word=word, request_cycle=cycle, id=key)
            pending[key] = entry
            reqs += 1
            if word & 127 == 0x5b:
                customs.append(entry)
        elif event == 'cvx_resp':
            require(key in pending, 'orphan response')
            entry = pending.pop(key)
            entry.update(response_cycle=cycle, fault=int(row['trap']))
            exceptions += int(row['trap']); resps += 1
            require(entry['word'] & 127 == 0x5b or not int(row['trap']), 'noncustom vector exception')
        elif event == 'retire':
            if word & 127 == 0x5b:
                retired.append((pc, word, int(row['trap'])))
            if pc in csr_by_pc:
                require(not int(row['trap']) and word == csr_by_pc[pc]['word'], 'CSR PC/opcode/trap differs')
                csr_reads.append((pc, int(row['rd_wdata'], 16), cycle))
    expected = sequence(name)
    require(not pending and reqs == resps and exceptions == 2 and
            [(r['word'], r.get('fault')) for r in customs] == [(w, f) for _, w, f in expected],
            'custom request response conservation/order differs')
    require(retired == [(elf['sites'][k]['pc'], w, 0) for k, w, f in expected if not f],
            'custom successful retirement PC/word differs')
    want_csrs = [32, 16, 0, 0x40, 5, 0] if name == CASE_NAMES[0] else [64, 8, 0, 0x40, 5, 0]
    require(len(csr_reads) == 6 * STEPS[name], 'immediate CSR trace cardinality differs')
    for phase in range(STEPS[name]):
        actual = csr_reads[phase * 6:(phase + 1) * 6]
        require([(p, v) for p, v, c in actual] == list(zip(csr_by_pc, want_csrs)) and
                min(c for p, v, c in actual) >= customs[phase]['response_cycle'], 'post-custom CSR values/order differ')
    lanes, vlen, activities = vc._parse_vector_trace(Path(vector_path))
    require((lanes, vlen) == (4, 1024), 'vector trace shape differs')
    custom_starts = [(seq, w) for seq, w in starts if w & 127 == 0x5b]
    require([w for _, w in custom_starts] == [w for _, w, _ in expected], 'architectural custom order differs')
    custom_write_lifetimes(vector_path, custom_starts)
    images = []
    for phase, (seq, word) in enumerate(custom_starts):
        seed, want = golden(name, phase)
        loads = [(n, w) for n, w in starts if n < seq and w & 127 == 7][-4:]
        require(len(loads) == 4 and [(w >> 7) & 31 for n, w in loads] == [0, 8, 16, 24], 'full seed load order differs')
        observed = {}
        for n, w in loads:
            require(n in activities, 'seed load missing vector evidence')
            require(activities[n].allocations > 0 and activities[n].completions > 0,
                    'seed load allocation/completion missing')
            writes = vc._architectural_bytes(activities[n].writes, lanes, vlen)
            base = ((w >> 7) & 31) * 128
            require(len(writes) == 1024 and all(value == seed[reg * 128 + byte] and
                    base <= reg * 128 + byte < base + 1024 for (reg, byte), (value, wr) in writes.items()),
                    'seed VRF byte oracle differs')
            observed.update({reg * 128 + byte: value for (reg, byte), (value, wr) in writes.items()})
        active = activities.get(seq)
        writes = vc._architectural_bytes(active.writes if active else [], lanes, vlen)
        changes = want != seed
        require(not changes or (active and active.allocations > 0 and active.completions > 0),
                'successful custom allocation/completion missing')
        require(len(writes) == (128 if changes else 0), 'fault/nonload wrote VRF or successful destination incomplete')
        for (reg, byte), (value, wr) in writes.items():
            offset = reg * 128 + byte
            require(1024 <= offset < 1152 and value == want[offset], 'independent numerical VRF result differs')
            observed[offset] = value
        require(len(observed) == 4096 and bytes(observed[i] for i in range(4096)) == want,
                'full VRF/tail/source-register recovery oracle differs')
        images.append(dict(phase=phase, arch_seq=seq, seed_bytes=4096, custom_write_bytes=len(writes)))
    return dict(status='PASS', requests=reqs, responses=resps, exceptions=exceptions,
                last_cycle=last, custom=customs, independent_vrf=images,
                csr_reads=[list(sample) for sample in csr_reads])
