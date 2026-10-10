"""Read-only ACC source closure and dormant native14 preparation; no EDA entry point."""
from collections import Counter
import copy
import json
from pathlib import Path
import re

import old_image_source_snapshot as snapshot
import review_qbs_cause_deep_cone as cone
import review_rvh0_exception_fields771 as members
import review_scoreboard_cause796_readonly_agent_20261008 as prior

u = prior.util
OLD = prior.OUTPUT
OLD_SHA = 'b24c492c5ab13a7bff29abefd8c476c984cfea4934f97248cf39dcdf280c2907'
REPORT = u.OUT / 'scoreboard-cause796-acc-closure-agent-20261008-02.json'
PREP = u.OUT / 'scoreboard-cause796-native14-prepared-agent-20261008-02'
ARCHIVE = u.OUT / 'old-image-source-evidence-20261006-01'
DISPATCH = 'hardware/src/ara_dispatcher.sv'
PROTECTED = [0, 1, 2, 3, 4, 5, 63]
DB = u.BUILD / 'sim/simv.vdb/snps/coverage/db'


def need(ok, message):
    if not ok:
        raise ValueError(message)


def check_pins(pins):
    for path, sha in pins.items():
        need(u.digest(Path(path)) == sha, 'Evidence pin drift: ' + path)


def contract(text, expected):
    clean = cone.q.clean(text)
    for root in {n.split('.cause')[0] for n in expected}:
        need(not re.search(r'(?<![\w.])' + re.escape(root) +
            r'(?:\.cause)?(?:\s*\[[^;]+?\])?\s*(?:\|=|&=|\^=|\+=|-=|\*=|/=|<<=|>>=)', clean),
            'Unreviewed compound cause/whole writer')
    rows = cone.writers(text, expected)
    need(Counter((r['lhs'], r['rhs']) for r in rows) ==
         Counter((lhs, rhs) for lhs, values in expected.items() for rhs in values),
         'Unreviewed whole/cause/slice writer')
    return rows


def collect():
    need(u.digest(OLD) == OLD_SHA, 'Previous frozen review seal')
    old = json.loads(OLD.read_bytes())
    bound = snapshot.validate(u.ROOT, ARCHIVE)
    book = json.loads((u.BUILD / 'build-source-pins.json').read_bytes())
    pins = dict(old['input_pins'])
    # The live dispatcher is historical drift evidence, never compiled proof.
    pins.pop(str(u.ROOT / DISPATCH))
    pins.update(bound['evidence_pins'])
    pins[str(OLD)] = OLD_SHA
    paths = set(prior.FILES) | set(cone.CONTRACT) | set(members.EXTRA) | {
        'hardware/include/ara/intf_typedef.svh', 'hardware/include/ara_pkg.sv'}
    texts, bindings = {}, []
    for rel in sorted(paths):
        original = u.ROOT / rel
        path = Path(bound['source_aliases'].get(str(original), {}).get('snapshot', original))
        need(u.digest(path) == book[str(original)], 'Original compiled source mismatch: ' + rel)
        texts[rel] = path.read_text()
        pins[str(path)] = book[str(original)]
        bindings.append(dict(original=str(original), evidence=str(path), sha256=book[str(original)]))
    writers = cone.source_contract(texts)
    extra = members.extra_contract(texts)
    for rel, rows in extra.items():
        writers.setdefault(rel, []).extend(rows)
    dispatch_expected = {
        'acc_resp_o.exception': ['ara_resp.exception'] * 11,
        'acc_resp_o.exception.cause': ['riscv::ILLEGAL_INSTR']}
    dispatch_rows = contract(texts[DISPATCH], dispatch_expected)
    root_rows = cone.writers(texts[DISPATCH], ['acc_resp_o'])
    need(len(root_rows) == 1 and root_rows[0]['line'] == 1100 and
         root_rows[0]['rhs'].endswith("default : '0 }") and
         'exception' not in root_rows[0]['rhs'], 'Dispatcher whole default must zero exception')
    writers[DISPATCH] = root_rows + dispatch_rows
    seq = 'hardware/src/ara_sequencer.sv'
    writers[seq] += contract(texts[seq], {'ara_resp_o': ["'0"]})
    edges = {
        DISPATCH: ['.ara_resp_i(ara_resp_i)', '.ara_resp_o(ara_resp)'],
        'hardware/src/ara.sv': ['.ara_resp_i (ara_resp)', '.ara_resp_o (ara_resp)',
            '.acc_resp_o (acc_resp_o.acc_resp)',
            '.addrgen_exception_i (addrgen_exception)', '.addrgen_exception_o (addrgen_exception)',
            '.mmu_exception_i (acc_mmu_exception)',
            'assign acc_resp_o.acc_mmu_req.acc_mmu_misaligned_ex = acc_mmu_misaligned_ex;',
            'assign acc_mmu_exception = acc_req_i.acc_mmu_resp.acc_mmu_exception;'],
        'hardware/src/ara_system.sv': ['.cvxif_req_o (acc_req', '.cvxif_resp_i (acc_resp',
            '.acc_req_i (acc_req', '.acc_resp_o (acc_resp'],
        'hardware/src/vlsu/vlsu.sv': ['.addrgen_exception_o (normal_addrgen_exception)',
            '.store_b_exception_o (store_b_exception)',
            '.fault_mmu_exception_o(qbs_fault_mmu_exception)',
            '.fault_mmu_exception_o (akv_fault_mmu_exception)', '.mmu_exception_i,',
            "mmu_misaligned_ex_o = 1'b0;", 'mmu_misaligned_ex_o = normal_mmu_misaligned_ex;'],
        'hardware/src/vlsu/addrgen.sv': ["assign mmu_misaligned_ex_o = '0;"],
        cone.ENGINE: ['.fault_mmu_exception_o (read_fault_mmu_exception)', '.mmu_exception_i,'],
        'hardware/src/vlsu/akv/akv_engine.sv': [
            '.fault_mmu_exception_o (read_fault_mmu_exception)', '.mmu_exception_i,'],
        cone.CORE + 'acc_dispatcher.sv': [
            'assign acc_exception_o = acc_resp_i.acc_resp.exception;',
            'assign acc_mmu_req_o = acc_resp_i.acc_mmu_req;',
            'assign acc_req_o.acc_mmu_resp = acc_mmu_resp_i;'],
        cone.CORE + 'cva6.sv': ['.acc_mmu_resp_o (acc_mmu_resp)',
            '.acc_mmu_resp_i (acc_mmu_resp)',
            '.ex_ex_i (ex_ex_ex_id)', '.acc_exception_o (acc_exception_ex_id)',
            'assign ex_ex_ex_id[ACC_WB] = acc_exception_ex_id;',
            'assign ex_ex_ex_id[FPU_WB] = fpu_exception_ex_id;',
            'assign ex_ex_ex_id[STORE_WB] = store_exception_ex_id;',
            'assign ex_ex_ex_id[LOAD_WB] = load_exception_ex_id;',
            'assign ex_ex_ex_id[FLU_WB] = flu_exception_ex_id;'],
        cone.CORE + 'issue_stage.sv': ['.ex_i (ex_ex_i)', '.fwd_o (fwd)', '.fwd_i (fwd)'],
    }
    for rel, tokens in edges.items():
        compact = re.sub(r'\s+', '', texts[rel])
        need(all(re.sub(r'\s+', '', t) in compact for t in tokens), 'Source connection changed: ' + rel)
    macro = texts['hardware/include/ara/intf_typedef.svh']
    need('logic                    acc_mmu_misaligned_ex;' in macro,
         'Misalignment is unsigned scalar, not arbitrary exception')
    values = {}
    all_rows = [r for rows in writers.values() for r in rows]
    for name in sorted(set(re.findall(r'riscv::(\w+)', ' '.join(r['rhs'] for r in all_rows)))):
        m = re.search(r'\b' + name + r'\s*=\s*(\d+)\s*;', texts[cone.CORE + 'include/riscv_pkg.sv'])
        need(m is not None and int(m[1]) < 64, 'Unbounded cause constant: ' + name)
        values[name] = int(m[1])
    shape = u.xml(DB / 'shape/tgl.verilog.shape.xml')
    selected_modules = {'ara_dispatcher', 'segment_sequencer', 'ara_sequencer', 'vlsu',
                        'qbs_engine', 'qbs_read_engine', 'akv_engine', 'cva6_mmu',
                        'scoreboard', 'issue_stage', 'decoder', 'issue_read_operands'}
    compiled = [dict(n.attrib) for n in shape.iter('tgldef') if n.get('name') in selected_modules]
    mmu = next(n for n in compiled if n['name'] == 'cva6_mmu')
    cone.bound_configuration(texts[cone.CORE + 'include/cv64a6_imafdcv_sv39_config_pkg.sv'],
        texts[cone.CORE + 'include/build_config_pkg.sv'], texts['hardware/src/ara_soc.sv'], mmu['param'])
    need(next(n for n in compiled if n['name'] == 'segment_sequencer')['param'].startswith('SegSupport=1,'),
         'Compiled segment branch')
    closed = copy.deepcopy(old['HOLD'])
    for row in closed:
        row['status'] = 'SOURCE_PROVEN_AFTER_RESET_NOT_NATIVE_APPROVED'
        row['chain'] = 'PINNED_ACC_WB4_AND_ALL_PRODUCERS_SCOREBOARD_RESET_COPY_INDUCTION'
    need(len(closed) == 46 and sum(r['selected_slots'] for r in closed) == 5244, 'Exact46 inventory')
    pins[str(Path(__file__).resolve())] = u.digest(Path(__file__).resolve())
    for helper in (snapshot, cone, members):
        p = Path(helper.__file__).resolve(); pins[str(p)] = u.digest(p)
    test_path = Path(__file__).with_name('test_review_scoreboard_acc796_closure_agent_20261008.py')
    pins[str(test_path)] = u.digest(test_path)
    report = dict(status='SOURCE_CLOSED60_NOT_NATIVE_QUALIFIED', population=796,
        previous_frozen_review=str(OLD), previous_review_unchanged=True,
        source_snapshot=bound, compiled_source_bindings=bindings, compiled_definitions=compiled,
        complete_ACC_whole_cause_writer_contracts=writers, finite_ACC_LSU_cause_values=values,
        writer_source_excerpts={rel: [dict(line=r['line'],
            text='\n'.join(texts[rel].splitlines()[max(0, r['line'] - 3):r['line'] + 5]))
            for r in rows] for rel, rows in writers.items()},
        source_connection_tokens=edges, previously_independent14=old['eligible'], newly_closed46=closed,
        inherited_scalar_decode_complete_source_reference_inventory={rel: inventory
            for rel, inventory in old['source_reference_and_bulk_writer_inventory'].items()
            if rel != DISPATCH},
        physical_bits_per_copy=57, slots_per_copy=114, physical_mask=hex(prior.MASK),
        newly_closed_physical_bits=2622, newly_closed_slots=5244,
        total_source_proven_copies=60, total_source_proven_physical_bits=3420,
        total_source_proven_slots=6840, native_preparation_copies=14,
        inherited_scalar_decode_routing_proofs={k: v for k, v in old['source_proofs'].items()
            if k not in ('ACC4_HOLD', 'scoreboard_conditional_induction')},
        ACC_induction='All data phases, not valid-only: default0 or finite sync code <64, '
            'or full copy of a bounded input. MMU misaligned storage, read/QBS/AKV fault storage, '
            'addrgen MMU storage, store-B output, sequencer exception storage and segment response '
            'storage have explicit zero reset/default and only enumerated copy/clear/hold writers. '
            'Dispatcher exception default0 + eleven Ara copies + illegal2; core forwards FULL cause '
            'to ACC_WB4. Accelerator is enabled, not config-disabled.',
        scoreboard_induction=old['source_proofs']['scoreboard_conditional_induction'].split(
            'ACC4 missing compiled proof')[0] + 'ACC4 premise now bound to archived compiled source; '
            'all five producer premises closed. Copies preserve cause[62:6]=0 after valid reset.',
        protected=old['protected'], dedup=old['dedup'], configuration_boundary=old['config_boundary'],
        validity_boundary=old['validity_boundary'],
        future_invalidation='Any build/source/config/type/producer change requires re-review, including '
            'RVH1, CLIC1, custom accelerator exception inputs or CVXIF enable. No transfer to future RVH1.',
        opaque_compiled_config='CVA6Cfg=-1 is an opaque composite serialization, NOT a numeric feature '
            'value. Bind features through original source-pinned package/SoC forwarding and actual '
            'compiled type, module and MMU HYP_EXT0 evidence. Source and compiled evidence are not additive.',
        native_qualified=False, EDA_started=False, RTL_changed=False, population_EL_changed=False,
        measured_gain=None, official_denominator=None, DCSR_native_deferred=True, input_pins=pins)
    check_pins(pins)
    return report


def config(report):
    shape = u.xml(DB / 'shape/tgl.verilog.shape.xml')
    design = u.xml(DB / 'design/verilog.design.xml')
    instances = {n.get('id'): n for n in design.iter('srcinst')}
    def scope(n):
        parent = instances.get(n.get('pid'))
        return (scope(parent) + '.' if parent is not None else '') + n.get('name')
    by_scope = {scope(n): d for d in design.iter('srcdef') for n in d.findall('srcinst')}
    rows = report['previously_independent14']
    groups = []
    for s in sorted({r['scope'] for r in rows}):
        selected = [r for r in rows if r['scope'] == s]
        defs = [n for n in shape.iter('tgldef') if n.get('chksum') == selected[0]['checksum']]
        need(len(defs) == 1, 'Unique compiled toggle definition')
        definition = defs[0]
        need(by_scope[s].get('name') == definition.get('name'), 'Compiled scope/module binding')
        inventory = [dict(kind=n.tag, attributes=dict(n.attrib)) for n in definition.find('tglshape')]
        targets = []
        for r in selected:
            node = next(n for n in inventory if n['attributes'].get('name') == r['name'])
            need(node['kind'] == 'vectornode' and all(
                r['compiled_attributes'][k] == v for k, v in node['attributes'].items()), 'Exact cause typed leaf')
            targets.append(dict(name=r['name'], kind='vectornode', attributes=node['attributes'],
                selected_bits=prior.BITS, protected_bits=PROTECTED, physical_mask=hex(prior.MASK),
                bits_count=57, directions=['0to1', '1to0'],
                port_native_binding_required=node['attributes'].get('portnode') != '0'))
        groups.append(dict(scope=s, module=definition.get('name'),
            design_checksum=by_scope[s].get('chksum'), toggle_checksum=definition.get('chksum'),
            compiled_parameters=definition.get('param'), targets=targets,
            complete_typed_scope_inventory=inventory,
            complement_rule='Every unselected object/array/member/direction unchanged; selected leaves '
                'retain bits[5:0] and63. Preserve packed/unpacked dimensions, never flatten MDA.'))
    return dict(status='DORMANT_CANDIDATE_ONLY_NOT_NATIVE_QUALIFIED', population=796,
        candidate_copies=14, physical_bits=798, unnamed_pair_slots=1596, groups=groups,
        input_pins=report['input_pins'],
        required_future_protocol=dict(stages=['before', 'selected', 'reset', 'reloaded', 'final'],
            exact_unique_native_handle_binding=True, per_bit_named_directions=True,
            no_serialized_pair_direction_inference=True, both_direction_readbacks=True,
            full_scope_complement_readbacks=True, global_reset_all_scopes=True,
            initial_reset_final_empty_EL=True, first_second_EL_semantically_identical=True,
            real_native_excluded_flags_and_delta_counts_required=True,
            port_alias_ambiguity_HOLD=True, startup_X_not_waived=True),
        prohibited=['ACC46 expansion', 'whole cause/exception/CSR/structure', 'mcause/scause',
                    'bit63', 'low6', 'assertknown', 'X-to-0', 'DCSR native', 'population application'],
        EDA_started=False, native_qualified=False, launcher_provided=False)


def validate_config(candidate, expected):
    need(candidate == expected, 'Exact independent14 config/typed complement/protocol required')
    check_pins(expected['input_pins'])


def candidate_el(c):
    lines = []
    for g in c['groups']:
        lines += ['CHECKSUM: "' + g['design_checksum'] + ' ' + g['toggle_checksum'] + '"',
                  'INSTANCE: ' + g['scope'], 'ANNOTATION: "DORMANT source-proven cause[62:6] only"']
        for t in g['targets']:
            for bit in t['selected_bits']:
                lines.append('Toggle ' + t['name'] + ' [' + str(bit) + '] "logic ' + t['name'] + '[63:0]"')
    return '\n'.join(lines) + '\n'


def validate_el(text, c):
    groups = {g['scope']: g for g in c['groups']}
    expected = {(g['scope'], t['name'], b, d) for g in c['groups'] for t in g['targets']
                for b in t['selected_bits'] for d in ('0to1', '1to0')}
    found, blocks, checksum, current = set(), set(), None, None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('//'):
            continue
        if line.startswith('CHECKSUM:'):
            m = re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"', line)
            need(m is not None, 'Checksum syntax'); checksum = m.groups(); current = None
        elif line.startswith('INSTANCE:'):
            current = line.split(':', 1)[1].strip()
            need(current in groups and current not in blocks, 'Exact unique scope')
            g = groups[current]
            need(checksum == (g['design_checksum'], g['toggle_checksum']), 'Compiled EL checksums')
            blocks.add(current)
        elif line.startswith('ANNOTATION:'):
            need(re.fullmatch(r'ANNOTATION: "[^"\r\n]*"', line) is not None, 'Annotation syntax')
        else:
            m = re.fullmatch(r'Toggle (?:(0to1|1to0) )?([^\s"]+) \[(\d+)(?::(\d+))?\] "logic ([^"\r\n]+)"', line)
            need(current in groups and m is not None, 'Only exact partial typed Toggle')
            direction, name, left, right, declaration = m.groups()
            need(declaration == name + '[63:0]', 'Full typed declaration required')
            hi, lo = int(left), int(right or left)
            need(62 >= hi >= lo >= 6, 'Low6/bit63 protected')
            for bit in range(lo, hi + 1):
                for d in ([direction] if direction else ['0to1', '1to0']):
                    record = current, name, bit, d
                    need(record in expected and record not in found, 'Extra/protected/duplicate exclusion')
                    found.add(record)
    need(found == expected and blocks == set(groups), 'Complete exact both directions required')
    return len(found)


def write_json(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2); stream.write('\n')


if __name__ == '__main__':
    report = collect()
    c = config(report)
    validate_config(c, config(report))
    el = candidate_el(c)
    need(validate_el(el, c) == 1596, 'Exact native14 plan')
    need(not REPORT.exists() and not PREP.exists(), 'Never overwrite frozen evidence')
    PREP.mkdir()
    write_json(REPORT, report)
    c['input_pins'] = dict(c['input_pins'], **{str(REPORT): u.digest(REPORT)})
    write_json(PREP / 'config.json', c)
    with (PREP / 'candidate.el').open('x') as stream:
        stream.write(el)
    print('Source report:', REPORT, u.digest(REPORT))
    print('Dormant config:', PREP / 'config.json', u.digest(PREP / 'config.json'))
    print('No EDA/native launched; no population exclusions applied.')
