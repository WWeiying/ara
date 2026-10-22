"""Static frozen QBS cause-domain audit. No native exclusions or EDA."""
import argparse
import copy
import json
import re
import unittest
from collections import Counter
from pathlib import Path

import audit_qbs_engine_residual766 as q
import review_qbs_residual766_data_semantics as sealed

ROOT = q.ROOT
CORE = 'hardware/deps/cva6/core/'
LSU = CORE + 'load_store_unit.sv'
MMU = CORE + 'cva6_mmu/cva6_mmu.sv'
PMP = CORE + 'pmp/src/pmp_data_if.sv'
ENGINE = 'hardware/src/vlsu/qbs/qbs_engine.sv'
READ = 'hardware/src/vlsu/qbs/qbs_read_engine.sv'
OUT = q.OUT / 'qbs-cause-deep-cone-source-review766-agent-20261007-01.json'

# Complete whole-struct/cause writer multisets, including inactive configuration branches.
CONTRACT = {
    LSU: {
        'cva6_misaligned_exception': [
            "{ {CVA6Cfg.XLEN{1'b0}}, {CVA6Cfg.XLEN{1'b0}}, {CVA6Cfg.GPLEN{1'b0}}, {32{1'b0}}, 1'b0, 1'b0 }"],
        'cva6_misaligned_exception.cause': ['riscv::' + x for x in (
            'LD_ADDR_MISALIGNED', 'ST_ADDR_MISALIGNED', 'LOAD_PAGE_FAULT',
            'STORE_PAGE_FAULT', 'LOAD_GUEST_PAGE_FAULT', 'STORE_GUEST_PAGE_FAULT')],
        'misaligned_exception': ['cva6_misaligned_exception',
            'acc_mmu_req_i.acc_mmu_misaligned_ex', 'cva6_misaligned_exception'],
        'acc_mmu_resp_o.acc_mmu_exception': ["'0", 'mmu_exception'],
        'pmp_exception': ["'0", 'misaligned_exception'],
    },
    MMU: {
        'lsu_exception_o': ['misaligned_ex_q'],
        'lsu_exception_o.cause': ['riscv::' + x for x in (
            'STORE_GUEST_PAGE_FAULT', 'STORE_PAGE_FAULT', 'LOAD_GUEST_PAGE_FAULT',
            'LOAD_PAGE_FAULT', 'STORE_GUEST_PAGE_FAULT', 'STORE_PAGE_FAULT',
            'LOAD_GUEST_PAGE_FAULT', 'LOAD_PAGE_FAULT', 'ST_ACCESS_FAULT', 'LD_ACCESS_FAULT')],
        'misaligned_ex_n': ['misaligned_ex_i'],
        'misaligned_ex_q': ["'0", 'misaligned_ex_n'],
    },
    PMP: {'lsu_exception_o': ['lsu_exception_i'],
          'lsu_exception_o.cause': ['riscv::ST_ACCESS_FAULT', 'riscv::LD_ACCESS_FAULT']},
    READ: {'planner_fault_mmu_exception': ["'0", 'mmu_exception_i'],
           'fault_mmu_exception_q': ["'0", 'planner_fault_mmu_exception', "'0"],
           'fault_mmu_exception_o': ['fault_mmu_exception_q']},
    ENGINE: {'fault_mmu_exception_d': ['fault_mmu_exception_q', 'read_fault_mmu_exception',
                "'0", "'0", 'read_fault_mmu_exception'],
             'fault_mmu_exception_q': ["'0", 'fault_mmu_exception_d', "'0"],
             'fault_mmu_exception_o': ['fault_mmu_exception_q']},
    'hardware/src/ara.sv': {'acc_mmu_exception': [
        'acc_req_i.acc_mmu_resp.acc_mmu_exception', "'0"]},
    CORE + 'acc_dispatcher.sv': {'acc_req_o.acc_mmu_resp': ['acc_mmu_resp_i']},
    'hardware/src/vlsu/vlsu.sv': {'qbs_terminal_exception': ["'0", 'qbs_fault_mmu_exception'],
        'qbs_terminal_exception.cause': [
            'qbs_fault_is_validation ? riscv::ILLEGAL_INSTR : riscv::LD_ACCESS_FAULT']},
}


def need(ok, message):
    if not ok:
        raise ValueError(message)


def writers(text, names):
    clean = q.clean(text)
    result = []
    for name in sorted({n.split('.cause')[0] for n in names}):
        # Capture bit writes too: they cannot silently evade the cause writer contract.
        pattern = (r'(?<![\w.])' + re.escape(name)
                   + r'(?P<member>\.\w+)?(?P<slice>\s*\[[^;=]+\])?\s*'
                   + r'(?P<op><=|=(?!=))\s*(?P<rhs>[^;]+);')
        for match in re.finditer(pattern, clean):
            member = match['member'] or ''
            if member and member != '.cause':
                continue
            need(not match['slice'], 'Unreviewed partial cause/struct write')
            result.append(dict(lhs=name + member, op=match['op'],
                rhs=re.sub(r'\s+', ' ', match['rhs']).strip(),
                line=clean[:match.start()].count('\n') + 1))
    return result


def source_contract(texts):
    result = {}
    for path, expected in CONTRACT.items():
        actual = writers(texts[path], expected)
        need(Counter((p['lhs'], p['rhs']) for p in actual) ==
             Counter((lhs, rhs) for lhs, values in expected.items() for rhs in values),
             'Unknown producer/override/reset/forwarding: ' + path)
        result[path] = actual
    guards = {
        LSU: ['localparam HYP_EXT = CVA6Cfg.RVH ? 1 : 0;', '.HYP_EXT       (HYP_EXT)',
              'if (CVA6Cfg.MmuPresent) begin : gen_mmu',
              'if (CVA6Cfg.MmuPresent && CVA6Cfg.RVH && en_ld_st_g_translation_i && !en_ld_st_translation_i && lsu_ctrl.g_overflow) begin',
              '.lsu_exception_o(pmp_exception)', '.lsu_exception_i     (pmp_exception)',
              '.lsu_exception_o     (mmu_exception)', '.misaligned_ex_i(misaligned_exception)'],
        MMU: ['if(CVA6Cfg.RVH && en_ld_st_g_translation_i && (!dtlb_gpte_q.w || d_g_st_access_err || !dtlb_gpte_q.d)) begin',
              'if (CVA6Cfg.RVH && d_g_st_access_err) begin'],
    }
    for path, tokens in guards.items():
        need(all(t in texts[path] for t in tokens), 'Configuration/producer guard changed')
    data_body = texts[MMU].split('lsu_exception_o = misaligned_ex_q;', 1)[1]
    need(data_body.count('if (CVA6Cfg.RVH && ptw_error_at_g_st) begin') == 2,
         'PTW guest guards changed')
    return result


def declaration(attributes, source_files, book):
    path = source_files[attributes['aux_file']]
    need(q.digest(path) == book[str(path)], 'Declaration source pin drift')
    line = int(attributes['aux_line_num'])
    text = path.read_text().splitlines()[line - 1]
    root = attributes['name'].split('.')[0]
    need(re.search(r'\b' + re.escape(root) + r'\b', text) is not None,
         'Alias declaration does not match actual source line')
    return dict(path=str(path), sha256=book[str(path)], line=line, text=text)


def candidate(field, source_files, book):
    a = field['attributes']
    need(field['kind'] == 'vectornode' and field['width'] == 64
         and a['left'] == '63' and a['right'] == '0' and a['excluded'] == '0'
         and field['name'].endswith('.cause'), 'Not exact compiled64 cause')
    coordinates = [field['raw_offset'] + 2 * bit + slot
                   for bit in range(4, 64) for slot in range(2)]
    need(set(coordinates) <= set(field['missing_coordinates']),
         'Observed upper cause toggle contradicts invariant')
    return dict(scope=field['scope'], name=field['name'], checksum=field['checksum'],
                design_checksum=field['design_checksum'], kind=field['kind'],
                attributes=a, declaration_binding=declaration(a, source_files, book),
                type_origin=field['source_binding'], type_origin_not_assignment_evidence=True,
                candidate_range=[63, 4], constant_value=0,
                missing_coordinates=coordinates, missing_serialized_positions=len(coordinates),
                low_3_0_valid_tval_all_other_members_protected=True,
                port_range_requires_separate_native_authorization=a['portnode'] != '0')


def bound_configuration(cfg, build, soc, compiled_mmu_param):
    need('localparam CVA6ConfigHExtEn = 0;' in cfg and 'RVH: bit\'(CVA6ConfigHExtEn)' in cfg
         and 'cfg.RVH = CVA6Cfg.RVH;' in build, 'RVH configuration not proven')
    modifier = soc.split('function automatic config_pkg::cva6_user_cfg_t gen_usr_cva6_config', 1)[1].split('endfunction', 1)[0]
    need('cfg.RVH' not in q.clean(modifier), 'SoC overrides RVH')
    need('HYP_EXT=0,' in compiled_mmu_param, 'Compiled RVH/HYP binding not zero')


def collect():
    audit = sealed.load_verified()
    book_path = q.f.BUILD / 'build-source-pins.json'
    book = q.load(book_path)
    paths = set(CONTRACT) | {
        'hardware/src/ara_system.sv', 'hardware/src/ara_soc.sv',
        'hardware/include/ara/intf_typedef.svh', CORE + 'cva6.sv',
        CORE + 'include/cv64a6_imafdcv_sv39_config_pkg.sv',
        CORE + 'include/build_config_pkg.sv', CORE + 'include/riscv_pkg.sv'}
    pins = {str(sealed.AUDIT): sealed.AUDIT_SHA, str(book_path): q.digest(book_path)}
    texts = {}
    for relative in sorted(paths):
        path = ROOT / relative
        need(q.digest(path) == book[str(path)], 'Frozen producer source mismatch: ' + relative)
        pins[str(path)] = book[str(path)]; texts[relative] = path.read_text()
    evidence = source_contract(texts)
    cfg = texts[CORE + 'include/cv64a6_imafdcv_sv39_config_pkg.sv']
    build = texts[CORE + 'include/build_config_pkg.sv']
    macro = texts['hardware/include/ara/intf_typedef.svh']
    need('logic                    acc_mmu_misaligned_ex;' in macro
         and 'logic [CVA6Cfg.XLEN-1:0] cause;' in macro, 'Accelerator misaligned scalar/type changed')
    edges = {
        CORE + 'cva6.sv': ['.acc_mmu_resp_o          (acc_mmu_resp)', '.acc_mmu_resp_i        (acc_mmu_resp)',
                          '.acc_req_o             (cvxif_req_o)'],
        'hardware/src/ara_system.sv': ['.cvxif_req_o      (acc_req', '.acc_req_i       (acc_req'],
        'hardware/src/ara.sv': ['.mmu_exception_i            (acc_mmu_exception'],
        'hardware/src/vlsu/vlsu.sv': ['.mmu_exception_i,', '.fault_mmu_exception_o(qbs_fault_mmu_exception)'],
        ENGINE: ['.mmu_exception_i,', '.fault_mmu_exception_o          (read_fault_mmu_exception)'],
    }
    for path, tokens in edges.items():
        need(all(t in texts[path] for t in tokens), 'Connection edge changed: ' + path)
    shape = q.f.xml(q.DB / 'shape/tgl.verilog.shape.xml')
    design = q.f.xml(q.DB / 'design/verilog.design.xml')
    sources = q.f.xml(q.DB / 'auxiliary/verilog.sourceinfo.xml')
    source_files = {p.get('id'): Path(p.get('name')) for p in sources.iter('fileinfo')}
    instances = {p.get('id'): p for p in design.iter('srcinst')}
    def scope(node):
        parent = instances.get(node.get('pid'))
        return (scope(parent) + '.' if parent is not None else '') + node.get('name')
    module_scopes = {d.get('name'): [scope(p) for p in d.findall('srcinst')]
                     for d in design.iter('srcdef')}
    mmu = next(p for p in shape.iter('tgldef') if p.get('name') == 'cva6_mmu')
    bound_configuration(cfg, build, texts['hardware/src/ara_soc.sv'], mmu.get('param'))
    # HYP_EXT is explicitly connected to LSU's RVH-derived localparam, not its MMU default.
    targets = [candidate(p, source_files, book) for p in audit['all_typed_fields']
               if p['name'].endswith('.cause')]
    need(len(targets) == 9, 'QBS exact cause inventory changed')
    upstream_aliases = []
    select = {
        'cva6_mmu': {'misaligned_ex_i', 'lsu_exception_o', 'misaligned_ex_n', 'misaligned_ex_q'},
        'pmp_data_if': {'lsu_exception_i', 'lsu_exception_o'},
        'load_store_unit': {'pmp_exception', 'mmu_exception', 'misaligned_exception',
                           'cva6_misaligned_exception', 'acc_mmu_resp_o'},
        'acc_dispatcher': {'acc_mmu_resp_i', 'acc_req_o'},
        'cva6': {'acc_mmu_resp', 'cvxif_req_o'},
        'ara_system': {'acc_req'}, 'ara': {'acc_req_i', 'acc_mmu_exception'},
        'vlsu': {'mmu_exception_i', 'qbs_fault_mmu_exception', 'qbs_terminal_exception'},
    }
    for definition in shape.iter('tgldef'):
        module = definition.get('name')
        if module not in select:
            continue
        offset = 0
        for node in definition.find('tglshape'):
            start = offset
            if node.tag in ('node', 'vectornode'):
                offset += 2 * (abs(int(node.get('left')) - int(node.get('right'))) + 1
                               if node.tag == 'vectornode' else 1)
            name = node.get('name', '')
            if not name.endswith('.cause') or name.split('.')[0] not in select[module]:
                continue
            a = dict(node.attrib)
            need(node.tag == 'vectornode' and a['left'] == '63' and a['right'] == '0',
                 'Upstream cause shape differs')
            upstream_aliases.append(dict(module=module, checksum=definition.get('chksum'),
                scopes=module_scopes[module], raw_offset=start, kind=node.tag,
                attributes=a, declaration_binding=declaration(a, source_files, book),
                inventory_only_not_waiver_target=True))
    # Every alias declaration source is pinned; type instantiation and producer evidence remain distinct.
    for p in targets + upstream_aliases:
        b = p['declaration_binding']; pins[b['path']] = b['sha256']
    cause_values = {}
    riscv = texts[CORE + 'include/riscv_pkg.sv']
    for name in ('LD_ADDR_MISALIGNED', 'LD_ACCESS_FAULT', 'ST_ADDR_MISALIGNED',
                 'ST_ACCESS_FAULT', 'LOAD_PAGE_FAULT', 'STORE_PAGE_FAULT', 'ILLEGAL_INSTR'):
        match = re.search(r'\b' + name + r'\s*=\s*(\d+)\s*;', riscv)
        need(match is not None, 'Missing finite cause literal')
        cause_values[name] = int(match[1])
    need(max(cause_values.values()) == 15, 'Cause upper invariant fails')
    return dict(status='QBS_CAUSE_SOURCE_BOUND_CONSTANT_RANGE_REVIEW_NO_EDA',
        conclusion='WORTH_PRECISE_PARTIAL_RANGE_NATIVE_REVIEW_NOT_NEW_STIMULUS',
        frozen_population=766, parent_pins_verified=len(audit['pins']), pins=pins,
        assumptions=['Frozen closed ara_tb/ara_soc compiled wiring, not a standalone QBS unit with unconstrained cause inputs.',
                     'Reset-inductive operational states; no internal force or fault injection into cause registers.'],
        compiled_mmu_binding=dict(mmu.attrib), compiled_rvh=0,
        whole_and_cause_writer_evidence=evidence, forwarding_edges=edges,
        conservative_cause_domain=[0, 2, 4, 5, 6, 7, 13, 15], literal_causes=cause_values,
        domain_note='Includes stale scalar/store and validation terminal causes; not a load-only set. Invalid cycles also bounded.',
        induction='Reset/default zero; each producer writes finite synchronous constants or bounded misalignment struct; MMU/PMP override only those constants; all forwards/holds/reset/abort preserve upper zero. RVH guest branches are compiled off.',
        interrupt_bit63_constant_zero=True, candidate_range=[63, 4],
        targets=targets, target_aliases=len(targets),
        candidate_source_bits=60 * len(targets),
        candidate_missing_serialized_positions=sum(p['missing_serialized_positions'] for p in targets),
        internal_candidate_missing_positions=sum(p['missing_serialized_positions'] for p in targets if p['attributes']['portnode'] == '0'),
        port_candidate_missing_positions=sum(p['missing_serialized_positions'] for p in targets if p['attributes']['portnode'] != '0'),
        upstream_aliases_inventory_only=upstream_aliases,
        guards=dict(other_typed_objects=len(audit['all_typed_fields']) - len(targets),
            arrays=len(audit['all_arrays_without_binary_coordinate']),
            retained_members=['cause[3:0]', 'valid', 'tval[63:0]', 'tval2', 'tinst', 'gva'],
            retained_paths=['all legal profiles/layouts/shapes', 'validation', 'translation',
                            'PMA', 'PMP', 'AXI response error', 'abort', 'fault arbitration', 'drain'],
            tval_negative_canonical_counterexample='0xffffffc000000000',
            tval_reason='MMU source sign-extends fault virtual addresses; negative canonical high bits can be one.'),
        official_denominator=None, official_percentage=None, coverage_admitted=False,
        native_qualified=False, no_EDA=True, no_simulation=True)


class NegativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.texts = {p: (ROOT / p).read_text() for p in CONTRACT}

    def test_actual_writer_contract(self):
        source_contract(self.texts)

    def test_interrupt_unknown_forward_and_partial_write_rejected(self):
        for extra in ("lsu_exception_o.cause = 64'h8000000000000005;",
                      'lsu_exception_o = csr_exception_i;',
                      "lsu_exception_o.cause[63] = 1'b1;"):
            texts = dict(self.texts); texts[MMU] += '\n' + extra
            with self.assertRaises(ValueError): source_contract(texts)

    def test_removed_guest_guards_rejected(self):
        texts = dict(self.texts)
        texts[MMU] = texts[MMU].replace('if (CVA6Cfg.RVH && ptw_error_at_g_st) begin',
                                       'if (ptw_error_at_g_st) begin')
        with self.assertRaises(ValueError): source_contract(texts)

    def test_new_fault_reset_value_rejected(self):
        texts = dict(self.texts)
        texts[READ] = texts[READ].replace("fault_mmu_exception_q <= '0;",
                                        "fault_mmu_exception_q <= '1;")
        with self.assertRaises(ValueError): source_contract(texts)

    def test_whole_forward_with_unknown_cause_rejected(self):
        texts = dict(self.texts)
        texts[ENGINE] = texts[ENGINE].replace(
            'fault_mmu_exception_d = read_fault_mmu_exception;',
            'fault_mmu_exception_d = mmu_interrupt_exception;')
        with self.assertRaises(ValueError): source_contract(texts)

    def test_rvh_config_override_and_compiled_mismatch_rejected(self):
        cfg = (ROOT / (CORE + 'include/cv64a6_imafdcv_sv39_config_pkg.sv')).read_text()
        build = (ROOT / (CORE + 'include/build_config_pkg.sv')).read_text()
        soc = (ROOT / 'hardware/src/ara_soc.sv').read_text()
        bound_configuration(cfg, build, soc, 'CVA6Cfg=-1,HYP_EXT=0,PPNWMin=29')
        for args in (
            (cfg.replace('CVA6ConfigHExtEn = 0;', 'CVA6ConfigHExtEn = 1;'), build, soc, 'HYP_EXT=0,'),
            (cfg, build, soc, 'HYP_EXT=1,'),
            (cfg, build, soc.replace('cfg.NrPMPEntries          = 0;', 'cfg.RVH = 1;'), 'HYP_EXT=0,'),
        ):
            with self.assertRaises(ValueError): bound_configuration(*args)

    def test_actual_bound_inventory(self):
        result = collect()
        self.assertEqual(result['target_aliases'], 9)
        self.assertEqual(result['candidate_missing_serialized_positions'], 1080)
        self.assertEqual(result['internal_candidate_missing_positions'], 600)
        self.assertEqual(result['port_candidate_missing_positions'], 480)
        self.assertEqual(result['candidate_range'], [63, 4])
        self.assertFalse(result['native_qualified'])

    def test_actual_coordinate_and_declaration_negatives(self):
        audit = sealed.load_verified()
        field = next(p for p in audit['all_typed_fields'] if p['name'].endswith('.cause'))
        sources = q.f.xml(q.DB / 'auxiliary/verilog.sourceinfo.xml')
        files = {p.get('id'): Path(p.get('name')) for p in sources.iter('fileinfo')}
        book = q.load(q.f.BUILD / 'build-source-pins.json')
        candidate(field, files, book)
        bad = copy.deepcopy(field)
        bad['missing_coordinates'].remove(bad['raw_offset'] + 126)
        with self.assertRaises(ValueError): candidate(bad, files, book)
        bad = copy.deepcopy(field)
        bad['attributes']['aux_file'] = '596'
        bad['attributes']['aux_line_num'] = '568'
        with self.assertRaises(ValueError): candidate(bad, files, book)
        bad = copy.deepcopy(field); bad['attributes']['left'] = '62'
        with self.assertRaises(ValueError): candidate(bad, files, book)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        unittest.main(argv=[__file__], verbosity=2)
    else:
        result = collect()
        result['pins'][str(Path(__file__).resolve())] = q.digest(__file__)
        OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
        print(json.dumps(dict(output=str(OUT), sha256=q.digest(OUT),
                             aliases=result['target_aliases'], missing=result['candidate_missing_serialized_positions'])))
