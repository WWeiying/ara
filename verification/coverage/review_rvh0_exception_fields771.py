"""Frozen RVH0 exception member audit; never writes an EL or launches EDA."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

import review_qbs_cause_deep_cone as prior
import targeted_toggle_evidence_v2 as native

ROOT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration')
OUT = ROOT / 'verification/out/rvh0-exception-members-source-review771-agent-20261007-01.json'
TARGETS = ROOT / 'verification/out/sv39-fault-alternating-static-targets771-agent-20261007-01.json'
BOOK = ROOT / 'verification/out/repaired-aligned-build-20260930-01/build-source-pins.json'
DISPATCH = ROOT / 'verification/out/old-image-source-evidence-20261006-01/ara_dispatcher.sv'
MEMBERS = ('gva', 'tinst', 'tval2')
EXTRA = {
    'hardware/src/vlsu/addrgen.sv': {
        'addrgen_exception_o': ["'0", 'mmu_exception_q', 'mmu_exception_q'],
        'addrgen_exception_o.cause': ["'0"] + ['is_load(pe_req_q.op) ? riscv::LD_ADDR_MISALIGNED : riscv::ST_ADDR_MISALIGNED'] * 2,
        'mmu_exception_d': ['mmu_exception_q', "'0", 'mmu_exception_i'],
        'mmu_exception_q': ["'0", 'mmu_exception_d']},
    'hardware/src/vlsu/vstu.sv': {
        'store_b_exception_d': ["'0"], 'store_b_exception_d.cause': ['riscv::ST_ACCESS_FAULT'] * 2,
        'store_b_exception_o': ["'0", 'store_b_exception_d']},
    'hardware/src/vlsu/akv/akv_engine.sv': {
        'fault_mmu_exception_o': ['fault_mmu_exception_q'],
        'fault_mmu_exception_q': ["'0"] * 3 + ['read_fault_mmu_exception']},
    'hardware/src/vlsu/vlsu.sv': {
        'addrgen_exception_o': ["'0", 'qbs_terminal_exception', 'akv_terminal_exception',
            'store_b_exception.valid ? store_b_exception : normal_addrgen_exception'],
        'akv_terminal_exception': ["'0", 'akv_fault_mmu_exception'],
        'akv_terminal_exception.cause': ['akv_fault_is_validation ? riscv::ILLEGAL_INSTR : riscv::LD_ACCESS_FAULT']},
    'hardware/src/ara_sequencer.sv': {
        'addrgen_exception_d': ['addrgen_exception_q', "'0", 'addrgen_exception_i', 'addrgen_exception_i'],
        'addrgen_exception_q': ["'0", 'addrgen_exception_d'],
        'ara_resp_o.exception': ['WaitForStoreB ? addrgen_exception_d : (addrgen_ack_i ? addrgen_exception_i : addrgen_exception_q)']},
    'hardware/src/segment_sequencer.sv': {
        'ara_resp_d': ['ara_resp_q', 'ara_resp_i', 'ara_resp_i'],
        'ara_resp_o': ['ara_resp_i', 'ara_resp_q', 'ara_resp_i'],
        'ara_resp_q': ["'0", 'ara_resp_d']},
}


def extra_contract(texts):
    evidence = {}
    for path, expected in EXTRA.items():
        rows = prior.writers(texts[path], expected)
        need(Counter((r['lhs'], r['rhs']) for r in rows) ==
             Counter((lhs, rhs) for lhs, values in expected.items() for rhs in values),
             'Unreviewed whole producer/hold/reset: ' + path)
        member_writes(texts[path], {n.split('.cause')[0] for n in expected})
        evidence[path] = rows
    return evidence


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def need(ok, message):
    if not ok:
        raise ValueError(message)


def rvh_required(condition):
    condition = condition.strip()
    if condition == 'CVA6Cfg.RVH':
        return True
    depth = 0; parts = []; start = 0; operators = []
    for m in re.finditer(r'\(|\)|&&|\|\|', condition):
        if m[0] == '(':
            depth += 1
        elif m[0] == ')':
            depth -= 1
        elif depth == 0:
            parts.append(condition[start:m.start()]); start = m.end(); operators.append(m[0])
    if not operators:
        if condition.startswith('(') and condition.endswith(')'):
            return rvh_required(condition[1:-1])
        return False
    parts.append(condition[start:])
    # Mixed top-level operators need a proper Boolean parser, not this narrow lemma.
    if '||' in operators:
        return False
    return any(rvh_required(part) for part in parts)


def rvh_bodies(text):
    """Locate positive RVH then-bodies; else arms are deliberately excluded."""
    clean = prior.q.clean(text)
    spans = []
    for match in re.finditer(r'\bif\s*\(', clean):
        start = match.end(); depth = 1; end = start
        while depth and end < len(clean):
            depth += (clean[end] == '(') - (clean[end] == ')')
            end += 1
        need(depth == 0, 'Unbalanced if expression')
        condition = clean[start:end - 1]
        if not rvh_required(condition):
            continue
        body = end + len(clean[end:]) - len(clean[end:].lstrip())
        if re.match(r'begin\b', clean[body:]):
            level = 0
            for token in re.finditer(r'\b(begin|end)\b', clean[body:]):
                level += 1 if token[0] == 'begin' else -1
                if level == 0:
                    spans.append((body, body + token.end()))
                    break
            else:
                raise ValueError('Unbalanced RVH begin/end')
        else:
            spans.append((body, clean.index(';', body) + 1))
    return clean, spans


def member_writes(text, roots):
    clean, spans = rvh_bodies(text)
    result = []
    for root in roots:
        pattern = r'(?<![\w.])' + re.escape(root) + r'\.(gva|tinst|tval2)(\s*\[[^;=]+\])?\s*(?:<=|=(?!=))\s*([^;]+);'
        for m in re.finditer(pattern, clean):
            need(not m[2], 'Unreviewed partial member assignment')
            rhs = re.sub(r'\s+', ' ', m[3]).strip()
            guarded = any(a <= m.start() < b for a, b in spans)
            need(rhs in ("'0", "1'b0") or guarded,
                 'Nonzero exception member writer without RVH guard: ' + m[0])
            result.append(dict(root=root, member=m[1], rhs=rhs,
                               line=clean[:m.start()].count('\n') + 1,
                               disabled_by_RVH0=guarded))
    return result


def collect():
    book = json.loads(BOOK.read_bytes())
    old = json.loads(prior.OUT.read_bytes())
    pins = {str(BOOK): digest(BOOK), str(prior.OUT): digest(prior.OUT), str(TARGETS): digest(TARGETS)}
    for path, sha in old['pins'].items():
        need(digest(path) == sha, 'Prior source evidence drift: ' + path)
        pins[path] = sha
    paths = set(prior.CONTRACT) | {
        prior.CORE + 'include/cv64a6_imafdcv_sv39_config_pkg.sv',
        prior.CORE + 'include/build_config_pkg.sv', 'hardware/src/ara_soc.sv',
        'hardware/src/ara_system.sv', 'hardware/src/vlsu/vstu.sv', 'hardware/src/vlsu/addrgen.sv',
        'hardware/src/ara_sequencer.sv', 'hardware/src/segment_sequencer.sv',
        'hardware/src/vlsu/akv/akv_engine.sv'}
    texts = {}
    for relative in paths:
        path = ROOT / relative
        need(digest(path) == book[str(path)], 'Frozen source pin mismatch: ' + relative)
        pins[str(path)] = book[str(path)]; texts[relative] = path.read_text()
    need(digest(DISPATCH) == book[str(ROOT / 'hardware/src/ara_dispatcher.sv')], 'Frozen dispatcher snapshot')
    pins[str(DISPATCH)] = digest(DISPATCH)
    prior.bound_configuration(texts[prior.CORE + 'include/cv64a6_imafdcv_sv39_config_pkg.sv'],
        texts[prior.CORE + 'include/build_config_pkg.sv'], texts['hardware/src/ara_soc.sv'],
        old['compiled_mmu_binding']['param'])
    macro = (ROOT / 'hardware/include/ara/intf_typedef.svh').read_text()
    need('logic                    acc_mmu_misaligned_ex;' in macro,
         'Accelerator misalignment must be unsigned scalar, not exception data')
    scalar_chain = {
        'hardware/src/ara.sv': ['logic acc_mmu_misaligned_ex,',
            'assign acc_resp_o.acc_mmu_req.acc_mmu_misaligned_ex = acc_mmu_misaligned_ex;',
            '.mmu_misaligned_ex_o        (acc_mmu_misaligned_ex'],
        prior.CORE + 'acc_dispatcher.sv': ['assign acc_mmu_req_o = acc_resp_i.acc_mmu_req;'],
        'hardware/src/vlsu/vlsu.sv': ['mmu_misaligned_ex_o = normal_mmu_misaligned_ex;',
            "mmu_misaligned_ex_o = 1'b0;", '.mmu_misaligned_ex_o (normal_mmu_misaligned_ex'],
        'hardware/src/vlsu/addrgen.sv': ["assign mmu_misaligned_ex_o = '0;"]}
    for path, snippets in scalar_chain.items():
        compact = re.sub(r'\s+', '', texts[path])
        need(all(re.sub(r'\s+', '', s) in compact for s in snippets), 'Scalar producer chain changed: ' + path)
    need(re.search(r'logic\s+gva\s*;\s*\\\s*logic\s+valid\s*;', macro) is not None,
         'Exception valid must be packed LSB, gva above it')
    whole_evidence = prior.source_contract(texts)
    extra_evidence = extra_contract(texts)
    producers = {
        prior.LSU: ['cva6_misaligned_exception'],
        prior.MMU: ['lsu_exception_o', 'icache_areq_o.fetch_exception'],
        prior.PMP: ['lsu_exception_o', 'icache_areq_o.fetch_exception'],
        'hardware/src/vlsu/vstu.sv': ['store_b_exception_d', 'store_b_exception_o'],
        'hardware/src/vlsu/addrgen.sv': ['addrgen_exception_o'],
    }
    writes = {p: member_writes(texts[p], roots) for p, roots in producers.items()}
    need("icache_areq_o.fetch_exception = '0;" in texts[prior.MMU], 'Fetch exception default')
    need("store_b_exception_d     = '0;" in texts['hardware/src/vlsu/vstu.sv'] and
         "store_b_exception_o <= '0;" in texts['hardware/src/vlsu/vstu.sv'], 'Store error reset/default')
    # Immutable source pin closure binds the reviewed forwarding paths as well as producers.
    forwards = {
        'hardware/src/vlsu/vstu.sv': ["store_b_exception_o <= store_b_exception_d;"],
        'hardware/src/vlsu/vlsu.sv': ["akv_terminal_exception = '0;", 'akv_terminal_exception = akv_fault_mmu_exception;',
            "addrgen_exception_o = '0;", '? store_b_exception : normal_addrgen_exception;'],
        'hardware/src/vlsu/akv/akv_engine.sv': ["fault_mmu_exception_q <= '0;", 'fault_mmu_exception_q <= read_fault_mmu_exception;'],
        'hardware/src/ara_sequencer.sv': ["ara_resp_o       = '0;", "addrgen_exception_q <= '0;", 'addrgen_exception_d = addrgen_exception_i;'],
        'hardware/src/segment_sequencer.sv': ['ara_resp_o       = ara_resp_i;', "ara_resp_q       <= '0;", 'ara_resp_d = ara_resp_i;']}
    for path, snippets in forwards.items():
        need(all(s in texts[path] for s in snippets), 'Forwarding closure changed: ' + path)
    dispatch = DISPATCH.read_text()
    need("default       : '0" in dispatch and '.ara_resp_o(ara_resp)' in dispatch and
         'acc_resp_o.exception = ara_resp.exception;' in dispatch, 'Dispatcher producer/forward binding')
    dispatch_rows = prior.writers(dispatch, ['acc_resp_o.exception'])
    need(Counter((r['lhs'], r['rhs']) for r in dispatch_rows) ==
         Counter({('acc_resp_o.exception', 'ara_resp.exception'): 11,
                  ('acc_resp_o.exception.cause', 'riscv::ILLEGAL_INSTR'): 1}), 'Dispatcher complete exception writer set')
    member_writes(dispatch, ['acc_resp_o.exception'])
    ranking = json.loads(TARGETS.read_bytes())
    db = BOOK.parent / 'sim/simv.vdb/snps/coverage/db'
    identity = json.loads(prior.q.IDENTITY.read_bytes())
    design_path = db / 'design/verilog.design.xml'
    need(digest(design_path) == identity['pins'][str(design_path)], 'Frozen compiled design')
    pins[str(design_path)] = digest(design_path)
    mmus = [n for n in native.xml(design_path).findall('srcdef') if n.get('name', '').split(' (')[0] == 'cva6_mmu']
    need(len(mmus) == 1 and mmus[0].get('chksum') == '1976186923', 'Actual compiled MMU design identity differs')
    simv = BOOK.parent / 'sim/simv'
    simv_sha = '2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3'
    need(digest(simv) == simv_sha, 'Frozen executable image')
    pins[str(simv)] = simv_sha
    sourceinfo = db / 'auxiliary/verilog.sourceinfo.xml'
    need(digest(sourceinfo) == identity['pins'][str(sourceinfo)], 'Compiled sourceinfo identity')
    pins[str(sourceinfo)] = digest(sourceinfo)
    source_files = {n.get('id'): Path(n.get('name')) for n in native.xml(sourceinfo).iter('fileinfo')}
    candidates = [n for n in ranking['candidates'] if n['name'].split('.')[-1] in MEMBERS]
    need(len(candidates) == 60 and len({(n['scope'], n['name']) for n in candidates}) == 60, 'Exact member alias inventory')
    shape_path = db / 'shape/tgl.verilog.shape.xml'
    need(digest(shape_path) == identity['pins'][str(shape_path)], 'Frozen shape identity')
    pins[str(shape_path)] = digest(shape_path)
    definitions = native.xml(shape_path).findall('tgldef')
    mmu_shapes = [n for n in definitions if n.get('name') == 'cva6_mmu']
    need(len(mmu_shapes) == 1 and dict(mmu_shapes[0].attrib) == old['compiled_mmu_binding'],
         'Actual compiled RVH0 toggle/config identity differs')
    inventories = []
    for scope in sorted({n['scope'] for n in candidates}):
        selected = [n for n in candidates if n['scope'] == scope]
        matches = [d for d in definitions if d.get('chksum') == selected[0]['checksum']]
        need(len(matches) == 1, 'Unique exact compiled toggle definition')
        definition = matches[0]; offset = 0; by_name = {}; arrays = []
        for node in definition.find('tglshape'):
            if node.tag == 'arrays':
                arrays.append(dict(node.attrib)); continue
            need(node.tag in ('node', 'vectornode'), 'Unrecognized native scalar/vector shape')
            width = 1 if node.tag == 'node' else abs(int(node.get('left')) - int(node.get('right'))) + 1
            by_name[node.get('name')] = (dict(node.attrib), offset, width)
            offset += 2 * width
        for n in selected:
            a, start, width = by_name[n['name']]
            need(a == n['native'], 'Actual native typed identity mismatch')
            need(n['positions'] == list(range(start, start + 2 * width)), 'Exact paired missing member coordinates')
        inventories.append(dict(scope=scope, checksum=selected[0]['checksum'],
            compiled_module=definition.get('name'), typed_objects=len(by_name),
            selected_objects=len(selected), protected_other_objects=len(by_name) - len(selected),
            arrays_protected=arrays, complete_serialized_width=offset))
    counts = Counter()
    for n in candidates:
        member = n['name'].split('.')[-1]
        a = n['native']; width = 1 if member == 'gva' else abs(int(a['left']) - int(a['right'])) + 1
        need(width == {'gva': 1, 'tinst': 32, 'tval2': 41}[member] and len(n['positions']) == 2 * width,
             'Expected complete currently unhit typed member')
        n.update(constant_value=0, candidate_range=None if width == 1 else [width - 1, 0],
                 requires_fresh_native_binding=True, port_requires_explicit_native_authorization=a['portnode'] != '0')
        source_id = a.get('aux_file') or a['file']
        declaration_path = source_files[source_id]
        compiled_source_path = declaration_path
        if declaration_path == ROOT / 'hardware/src/ara_dispatcher.sv':
            declaration_path = DISPATCH
        need(digest(declaration_path) == book[str(compiled_source_path)], 'Exact compiled declaration source: ' + str(compiled_source_path))
        line = int(a.get('aux_line_num') or a['line_num'])
        n['declaration_binding'] = dict(path=str(declaration_path), line=line,
            compiled_source_path=str(compiled_source_path),
            text=declaration_path.read_text().splitlines()[line - 1], sha256=book[str(compiled_source_path)])
        need(re.search(r'\b' + re.escape(n['name'].split('.')[0]) + r'\b', n['declaration_binding']['text']) is not None,
             'Compiled node root not at bound declaration')
        pins[str(declaration_path)] = book[str(compiled_source_path)]
        counts[member] += len(n['positions'])
    for path in (Path(__file__).resolve(), Path(__file__).with_name('test_review_rvh0_exception_fields771.py')):
        pins[str(path)] = digest(path)
    for path, sha in pins.items():
        need(digest(path) == sha, 'Final pin drift')
    return dict(status='RVH0_EXCEPTION_MEMBERS_SOURCE_CANDIDATE_NOT_NATIVE_QUALIFIED',
        baseline=771, baseline_seal=ranking['baseline_seal'], compiled_mmu=old['compiled_mmu_binding'],
        compiled_mmu_design=dict(mmus[0].attrib),
        targets=candidates, fields=len(candidates), scopes=len({n['scope'] for n in candidates}),
        compiled_scope_inventories=inventories,
        actual_missing_positions=dict(counts), pins=pins, producer_member_writes=writes,
        whole_struct_cause_writer_evidence=whole_evidence, forwarding_source_evidence=forwards,
        complete_additional_whole_writer_evidence=extra_evidence,
        dispatcher_exception_writer_evidence=dispatch_rows,
        scalar_accelerator_producer_evidence=scalar_chain,
        induction='Reset/default zeros; nonzero producer member writes disabled by RVH0; accelerator scalar misalignment is zero-extended into the exception valid LSB; forwards/holds/FIFO captures preserve zero. Includes invalid, error, abort and flush cycles after reset.',
        protected=['tval entire width, including negative canonical high bits', 'valid', 'all cause bits pending per-alias extension review', 'all other fields, ports, arrays and children'],
        cause_status='Prior memory-only bounded cause proof remains valid, but no new cause aliases admitted by this member review. Core commit/CSR cause may include interrupt bit63 and must not inherit the memory-only lemma.',
        limitation='Exact source-first members only. No native labels guessed, no EL generated, no coverage denominator or percentage. Full before inventory, five-stage EL/complement validation and parent review required.',
        EDA_launched=False, RTL_modified=False, coverage_admitted=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('mode', choices=('prepare', 'verify')); p.add_argument('--seal'); args = p.parse_args()
    if args.mode == 'prepare':
        need(not OUT.exists(), 'Fresh independent output only')
        r = collect(); OUT.write_text(json.dumps(r, sort_keys=True, indent=2) + '\n')
        print(json.dumps(dict(path=str(OUT), seal=digest(OUT), fields=r['fields'], counts=r['actual_missing_positions'], pins=len(r['pins']))))
    else:
        need(args.seal == digest(OUT), 'Exact result seal')
        need(json.loads(OUT.read_bytes()) == collect(), 'Independent full replay')
        print('RVH0_EXCEPTION_SOURCE_REPLAY_PASS_NOT_NATIVE_QUALIFIED')
