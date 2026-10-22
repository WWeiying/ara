"""Frozen source candidate / native partial-bit gates. No EDA launch mode."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

import ptw_rvh0_outputs156_local as ptw
import report_population796_alua_ptw as policy
import targeted_toggle_evidence_v2 as typed

life, need = ptw.life, ptw.need
HERE = Path(__file__).resolve().parent
SCRIPT = Path(__file__).resolve()
TCL = SCRIPT.with_suffix('.tcl')
TEST = HERE / 'test_c910_lane23_padding1424_local.py'
SCHEMA = 'C910_LANE23_PADDING1424_LOCAL_V1'
ANNOTATION = 'WIDTH16 C910 initial input padding only; settled post-reset; local qualification not application'
STAGES = ('before', 'applied', 'reset', 'reloaded', 'final')
VENDOR = 'hardware/deps/fpnew/vendor/openc910/C910_RTL_FACTORY/gen_rtl/vfdsu/rtl/'
SOURCES = ['hardware/deps/fpnew/src/' + n for n in
           ('fpnew_pkg.sv', 'fpnew_opgroup_multifmt_slice.sv', 'fpnew_divsqrt_th_64_multi.sv')]
SOURCES += [VENDOR + n for n in ('ct_vfdsu_top.v', 'ct_vfdsu_double.v',
            'ct_vfdsu_scalar_dp.v', 'ct_vfdsu_prepare.v', 'ct_vfdsu_ff1.v',
            'ct_vfdsu_srt.v', 'ct_vfdsu_srt_radix16_with_sqrt.v')]
BITS = {'initial_divisor_in': set(range(45)),
        'initial_remainder_in': set(range(42)) | {59, 60}}
WIDTHS = {'initial_divisor_in': 56, 'initial_remainder_in': 61}
CHILD = '.i_ct_vfdsu_top.x_ct_vfdsu_double.x_ct_vfdsu_srt.x_ct_vfdsu_srt_radix16_with_sqrt'
REPORT796 = life.OUT / 'current-population796-alua137-ptw156-agent-20261008-01'
CONFIG796_SHA = '062daf585d00ef170942b36f5a631dee7f4676af32fcbb4e5d8af86a8159badf'
QUAL796_SHA = 'f439bae9092c0a787ee8fb8177ee33277e6ec25f61ef0c198f5a8dce50807270'
EL796_SHA = '2704de24f115e289d8c1e60c3847dc39d7f7d13e955eb284ddc66f6fd42596c9'
API_RECORD = life.OUT / 'csr-reserved1193-native-agent-20261007-01'
API_PINS = {'DVEfiles/dve_gui.log': '5c2cfac285e39c11e3482b167711823de27e93c5c555600f48f2cd888c8c7587',
            'error.txt': '63626c83616437f33f24ee15177e8bc44abd26878151a01d2a3a1f49267c18fd',
            'bits-before.tsv': 'a928bf7f57bff04d503be75e30b8bf612fb604ffdbea5a59b72220ac0755b426'}


def scopes():
    return ['ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[%d].i_lane.i_vfus.i_vmfpu.'
            'fpu_gen.i_fpnew_bulk.gen_operation_groups[1].i_opgroup_block.gen_merged_slice.'
            'i_multifmt_slice.gen_num_lanes[%d].active_lane.lane_instance.'
            'gen_thmulti_c910_divsqrt.i_fpnew_divsqrt_th_64_c910' % (lane, sub) + CHILD
            for lane in range(4) for sub in (2, 3)]


def source_guard(texts, seals):
    # Seals lock all writers and inter-module wiring, not just matched excerpts.
    need(set(texts) == set(seals) == {Path(p).name for p in SOURCES}, 'Complete source chain')
    for name, text in texts.items():
        need(hashlib.sha256(text.encode()).hexdigest() == seals[name], 'Frozen source: ' + name)
    clean = {n: re.sub(r'/\*.*?\*/|//[^\n]*', '', t, flags=re.S) for n, t in texts.items()}
    compact = {n: re.sub(r'\s+', '', t) for n, t in clean.items()}
    def writers(file, name, expected):
        rows = re.findall(r'\b' + re.escape(name) + r'((?:\s*\[[^\]]+\]|\.\w+)*)\s*(<=|=(?!=))\s*([^;]+);', clean[file])
        rows = [tuple(re.sub(r'\s+', '', s) for s in row) for row in rows]
        need(rows == expected, 'Complete writer set: ' + file + ':' + name)
        return rows
    wrapper = compact['fpnew_divsqrt_th_64_multi.sv']
    section = wrapper.split('elseif(WIDTH==16)', 1)[1].split('endelsebegin', 1)[0]
    need(re.findall(r'divsqrt_fmt=([^;]+);', section) == ["4'b0010", "4'b0001", "4'b0010"],
         'WIDTH16 complete cases including default')
    need("`FFL(divsqrt_fmt_q,divsqrt_fmt,op_starting,'0)" in wrapper and
         ".idu_vfpu_rf_pipex_func({3'b0,divsqrt_fmt_q,11'b0,sqrt_op,div_op})" in wrapper and
         '.cpurst_b(rst_ni)' in wrapper, 'Format reset/capture and bit16/15 wiring')
    scalar = compact['ct_vfdsu_scalar_dp.v']
    for name, index in [('ex1_double', 16), ('ex1_single', 15)]:
        writers('ct_vfdsu_scalar_dp.v', name, [('', '<=', "1'b0"),
                ('', '<=', 'idu_vfpu_rf_pipex_func[%d]' % index)])
    need('always@(posedgevfdsu_sew_clkornegedgecpurst_b)beginif(!cpurst_b)begin' in scalar and
         'endelseif(idu_vfpu_rf_pipex_gateclk_sel)beginex1_div<=' in scalar,
         'Asynchronous reset and enabled capture/implicit hold')
    prepare_writers = {}
    def prepare_writer(name, bounds, rhs):
        prepare_writers[name] = writers('ct_vfdsu_prepare.v', name, [(bounds, '=', rhs)])
    for operand in (0, 1):
        name = 'ex1_oper%d' % operand
        fraction = 'ex1_double?%s[51:0]:ex1_single?{%s[22:0],29\'b0}:ex1_half?{%s[9:0],42\'b0}:{%s[6:0],45\'b0}' % ((name,) * 4)
        prepare_writer(name + '_frac', '[51:0]', fraction)
        normal = 'ex1_double?{1\'b1,%s[51:0]}:ex1_single?{1\'b1,%s[22:0],29\'b0}:ex1_half?{1\'b1,%s[9:0],42\'b0}:{1\'b1,%s[6:0],45\'b0}' % ((name,) * 4)
        prepare_writer('ex1_div_noid_nor_srt_op%d' % operand, '[52:0]', normal)
        prepare_writer('ex1_div_nor_srt_op%d' % operand, '[52:0]',
                       'ex1_op%d_id_nor?{ex1_oper%d_id_frac[51:0],1\'b0}:ex1_div_noid_nor_srt_op%d[52:0]' % ((operand,) * 3))
        prepare_writer('ex1_div_srt_op%d' % operand, '[52:0]', 'ex1_div_nor_srt_op%d[52:0]' % operand)
        instance = 'ct_vfdsu_ff1x_frac%d_expnt(' % operand
        need(instance in compact['ct_vfdsu_prepare.v'], 'Both actual denormal FF1 instances')
        connection = compact['ct_vfdsu_prepare.v'].split(instance, 1)[1].split(');', 1)[0]
        need('.fanc_shift_num(ex1_oper%d_id_frac[51:0])' % operand in connection and
             '.frac_num(ex1_oper%d_frac[51:0])' % operand in connection, 'Aligned fraction / FF1 output wiring')
    prepare_writer('ex1_divisor', '[52:0]', 'ex1_div_srt_op1[52:0]')
    prepare_writer('ex1_remainder', '[59:0]',
                   "{60{ex1_div}}&{5'b0,ex1_div_srt_op0[52:0],2'b0}|{60{ex1_sqrt}}&sqrt_remainder[59:0]")
    prepare_writer('sqrt_remainder', '[59:0]',
                   "(ex1_sqrt_expnt_odd)?{5'b0,ex1_sqrt_srt_op0[52:0],2'b0}:{6'b0,ex1_sqrt_srt_op0[52:0],1'b0}")
    prepare_writer('ex1_sqrt_srt_op0', '[52:0]', 'ex1_div_srt_op0[52:0]')
    ff1 = clean['ct_vfdsu_ff1.v']
    assignments = re.findall(r'fanc_shift_num\[51:0\]\s*=\s*([^;]+);', ff1)
    expected = ['frac_num[51:0]'] + ['{frac_num[%d:0],%d\'b0}' % (51 - s, s)
                                     for s in range(1, 52)] + ["{52'b0}", "{52'b0}"]
    need([re.sub(r'\s+', '', a) for a in assignments] == expected,
         'Every FF1 branch shifts left or returns zero')
    writers('ct_vfdsu_ff1.v', 'fanc_shift_num', [('[51:0]', '=', rhs) for rhs in expected])
    patterns = re.findall(r"52'b([01?]{52})\s*:", ff1)
    need(patterns == ['0' * s + '1' + '?' * (51 - s) for s in range(52)] + ['0' * 52],
         'All52 leading-one cases plus zero and default')
    srt = compact['ct_vfdsu_srt.v']
    need("assigninitial_divisor_in[55:0]={ex1_divisor[52:0],3'b000};" in srt and
         "assigninitial_remainder_in[60:0]={2'b00,ex1_remainder[59:1]};" in srt,
         'Exact initial concatenations')
    writers('ct_vfdsu_srt.v', 'initial_divisor_in', [('[55:0]', '=', "{ex1_divisor[52:0],3'b000}")])
    writers('ct_vfdsu_srt.v', 'initial_remainder_in', [('[60:0]', '=', "{2'b00,ex1_remainder[59:1]}")])
    return dict(boundary='After valid reset and combinational settling; no pre-reset X, delta, force or fault waiver',
        format='All WIDTH16 cases and default have double/single=0; both register stages reset0/capture/hold',
        normal='half fraction42 low zeros; bfloat/default45; both operands and hidden-bit path',
        denormal='Aligned fraction through all52 FF1 left shifts/zero/default then append0; at least42 low zeros',
        remainder='DIV append2; SQRT append1 or2; OR masks preserve at least43 low zeros',
        child='Divisor append3 gives44:0 zero; remainder drops bit0 and prefixes00 gives41:0 and60:59 zero',
        recurrence='No iterative remainder, quotient, root, boundary, reset, mode or clock exclusions',
        complete_prepare_writers=prepare_writers,
        proof_kind='Reviewed source induction plus complete padding-path writer checks and frozen full-source hashes; not formal proof')


def wrapper_gate(name):
    params = dict(re.findall(r'\b(FpFmtConfig|WIDTH)=(\d+)(?=,)', name))
    need(params == {'FpFmtConfig': '8', 'WIDTH': '16'}, 'Actual compiled8/16 wrapper')


def collision_gate(text):
    other, masks = policy.stable.semantic(text)
    for row in other:
        scope, _, _, directive = row
        need(not (directive == 'WHOLE_SCOPE' and
                  any(s == scope or s.startswith(scope + '.') for s in scopes())), 'Whole ancestor ownership')
    for scope, _, name, *_ in masks:
        if scope in scopes():
            need(not any(name == n or name.startswith(n + '.') or n.startswith(name + '.')
                         for n in BITS), 'Existing field/parent/partial ownership')


def evidence():
    pins = {}
    def read(p, seal):
        need(life.digest(p) == seal, 'Bound input drift: ' + str(p))
        pins[str(p)] = seal
        return p.read_bytes()
    book = json.loads(read(ptw.BOOK, ptw.BOOK_SHA))
    texts, seals = {}, {}
    for relative in SOURCES:
        p = life.ROOT / relative
        seals[p.name] = book[str(p)]
        texts[p.name] = read(p, seals[p.name]).decode()
    argument = source_guard(texts, seals)
    manifest = json.loads(read(policy.BASE, policy.BASE_SHA))
    need(manifest['coverage_admitted'] is True, 'Admitted796 baseline')
    ledger_path = policy.BASE.parent / 'combined-inputs.txt'
    ledger = read(ledger_path, manifest['output_pins'][str(ledger_path)]).decode().splitlines()
    need(len(ledger) == len(set(ledger)) == 797, 'Exact796 ledger')
    raw_path = policy.BASE.parent / 'combined-toggle-bits.json'
    raw = json.loads(read(raw_path, manifest['output_pins'][str(raw_path)]))
    qpath = policy.REPORT / 'qualification.json'
    q = json.loads(read(qpath, policy.REPORT_SHA))
    cpath = policy.REPORT / 'config.json'
    c = json.loads(read(cpath, q['config_seal']))
    elpath = policy.REPORT / 'combined.el'
    collision_gate(read(elpath, c['pins'][str(elpath)]).decode())
    # 795 remains a qualified reference, never relabeled as the current796 policy.
    current = json.loads(read(REPORT796 / 'config.json', CONFIG796_SHA))
    qualified = json.loads(read(REPORT796 / 'qualification.json', QUAL796_SHA))
    need(current['population'] == qualified['population'] == 796 and
         qualified['config_seal'] == CONFIG796_SHA and
         current['admission'] == dict(path=str(policy.BASE), sha256=policy.BASE_SHA), 'Latest exact796 report authority')
    current_el = REPORT796 / 'combined.el'
    need(current['pins'][str(current_el)] == EL796_SHA, 'Latest796 exact EL pin')
    current_text = read(current_el, EL796_SHA).decode()
    collision_gate(current_text)
    need(policy.stable.semantic(current_text) == policy.stable.semantic(
         read(REPORT796 / 'applied.el', qualified['output_pins'][str(REPORT796 / 'applied.el')]).decode()),
         'Latest796 actual applied semantic ownership')
    db = Path(ledger[0]) / 'snps/coverage/db'
    paths = [db / r for r in ('design/verilog.design.xml', 'shape/tgl.verilog.info.xml',
                             'shape/tgl.verilog.shape.xml')]
    for p in paths:
        read(p, manifest['input_pins'][str(p)])
    design, info, shape = [typed.xml(p) for p in paths]
    checks, defs = typed.definitions(design, info, shape, scopes())
    instances = []
    for scope in scopes():
        parent = scope[:-len(CHILD)]
        matches = [d for d in shape.findall('tgldef') if
                   any(n.get('name') == parent for n in d.findall('tglinst'))]
        need(len(matches) == 1, 'One compiled wrapper parameter definition')
        wrapper_gate(matches[0].get('name'))
        d = defs[scope]
        need(d['module']['name'] == 'ct_vfdsu_srt_radix16_with_sqrt' and
             d['module']['chksum'] == '406590228' and checks[scope] == raw[scope]['checksum'] == '3969040510'
             and raw[scope]['width'] == 20656, 'Compiled child/checksum/serialized width')
        nodes = [dict(kind=n.tag, **n.attrib) for n in ET.fromstring(d['shape']).find('tglshape')]
        need(len(nodes) == len({n['name'] for n in nodes}) == 210 and
             all(n['kind'] in ('node', 'vectornode') for n in nodes) and
             sum(2 * (1 if n['kind'] == 'node' else abs(int(n['left']) - int(n['right'])) + 1)
                 for n in nodes) == 20656, 'Complete binary210 child inventory')
        signals = []
        for name, width in WIDTHS.items():
            n = next(n for n in nodes if n['name'] == name)
            need(n['kind'] == 'vectornode' and n['left'] == str(width - 1) and n['right'] == '0'
                 and n['type'] == '3' and n['portnode'] == '2' and n['excluded'] == '0', 'Exact input geometry')
            signals.append(dict(name=name, kind='vectornode', left=width - 1, right=0))
        instances.append(dict(scope=scope, design_module_checksum=d['module']['chksum'],
            toggle_checksum=checks[scope], typed_objects=nodes, signals=signals,
            compiled_wrapper=matches[0].get('name'), wrapper_toggle_checksum=matches[0].get('chksum')))
    sample = Path(ledger[-1])
    dirs = list((sample / 'snps/coverage/db/testdata').iterdir())
    need(len(dirs) == 1 and dirs[0].is_dir() and not dirs[0].is_symlink(), 'One admitted native sample')
    for p in sample.rglob('*'):
        if p.is_file():
            read(p, manifest['input_pins'][str(p)])
    api = {n: read(API_RECORD / n, seal).decode() for n, seal in API_PINS.items()}
    need('gui_cov_tgl_double_click' in api['DVEfiles/dve_gui.log'] and
         '-tgl_transition string' in api['DVEfiles/dve_gui.log'] and
         'Full target objects bit complement missing' in api['error.txt'], 'Actual API help / failed vector precedent')
    life.check(pins)
    return dict(status='SOURCE1424_PROVEN_POST_RESET_NATIVE_HOLD', instances=instances, pins=pins,
        source_argument=argument, population=796, bits=712, directions=1424, target_fields=16,
        ownership_reference=dict(population=795, qualification_sha256=policy.REPORT_SHA),
        current_policy_collision=dict(population=796, config_sha256=CONFIG796_SHA,
            qualification_sha256=QUAL796_SHA, combined_EL_sha256=EL796_SHA, collision=False),
        native_API=dict(status='REAL_HELP_DOCUMENTED_VECTOR_BIT_CAPTURE_UNCONFIRMED',
            precedent=str(API_RECORD), scalar_rows_only=len(api['bits-before.tsv'].splitlines()) - 1,
            vector_precedent_failed=True, host_fixture_is_native_evidence=False),
        protected_objects=1664, retained_input_bits=224, native_input_bits=936,
        design=ledger[0], vdb=str(sample), test=str(sample.with_suffix('') / dirs[0].name),
        raw_physical_mapping=False, native_qualified=False, population_application=False, EDA_started=False)


def wanted(c):
    return {(i['scope'], n, b, d) for i in c['instances'] for n, bits in BITS.items()
            for b in bits for d in ('0to1', '1to0')}


def candidate(c):
    lines = []
    for i in c['instances']:
        lines += ['CHECKSUM: "%s %s"' % (i['design_module_checksum'], i['toggle_checksum']),
                  'INSTANCE: ' + i['scope'], 'ANNOTATION: "' + ANNOTATION + '"']
        for name, bits in BITS.items():
            for bit in sorted(bits):
                lines.append('Toggle %s [%d] "logic %s[%d:0]"' % (name, bit, name, WIDTHS[name] - 1))
    return '\n'.join(lines) + '\n'


def el_gate(text, c):
    need([i['scope'] for i in c['instances']] == scopes(), 'Exact eight instance contract')
    expected = {i['scope']: i for i in c['instances']}
    found, headers, annotations = set(), set(), set()
    scope = checksum = None
    pending = False
    for line in text.splitlines():
        if not line.strip():
            continue
        if line.startswith('CHECKSUM:'):
            need(not pending, 'Unused checksum block')
            checksum = line
            scope = None
            pending = True
        elif line.startswith('INSTANCE:'):
            scope = line[len('INSTANCE: '):]
            need(pending and scope in expected and scope not in headers, 'Unique exact child scope')
            i = expected[scope]
            need(checksum == 'CHECKSUM: "%s %s"' % (i['design_module_checksum'], i['toggle_checksum']),
                 'Exact checksum pair')
            headers.add(scope)
            pending = False
        elif line.startswith('ANNOTATION:'):
            need(scope and scope not in annotations and line == 'ANNOTATION: "' + ANNOTATION + '"',
                 'Unique exact scope annotation')
            annotations.add(scope)
        else:
            m = re.fullmatch(r'Toggle (?:(0to1|1to0) )?(\w+) \[(\d+)(?::(\d+))?\] "logic (\w+)\[(\d+):0\]"', line)
            need(scope and not pending and m is not None, 'Explicit partial Toggle only; no whole objects/IP')
            direction, name, left, right, declared, high = m.groups()
            need(name in BITS and declared == name and int(high) == WIDTHS[name] - 1, 'Exact field declaration')
            lo, hi = int(right or left), int(left)
            need(lo <= hi and set(range(lo, hi + 1)) <= BITS[name], 'No adjacent/dynamic input bit')
            for b in range(lo, hi + 1):
                for d in ((direction,) if direction else ('0to1', '1to0')):
                    key = scope, name, b, d
                    need(key not in found, 'Duplicate/overlapping direction')
                    found.add(key)
    need(not pending and headers == annotations == set(expected) and found == wanted(c)
         and len(found) == 1424, 'Exact1424 physical directions and8 annotated blocks')
    return sorted(found)


def bit_gate(text, i, stage, previous=None):
    need(stage in STAGES, 'Known phase')
    rows = list(csv.reader(io.StringIO(text), delimiter='\t'))
    need(rows and rows[0] == ['signal', 'bit', 'path', 'meta', 'name', 'coverage', '0to1', '1to0'], 'Native bit schema')
    found = {}
    for row in rows[1:]:
        need(len(row) == 8, 'Complete bit attributes')
        name, bit, path, meta, label, coverage, rise, fall = row
        need(name in WIDTHS and bit.isdecimal(), 'Only two exact native inputs')
        b = int(bit)
        need(0 <= b < WIDTHS[name] and label == '%s[%d]' % (name, b) and path and meta and
             rise in ('0', '1') and fall in ('0', '1'), 'Physical native bit and binary direction query')
        key = name, b
        need(key not in found, 'Duplicate physical bit')
        target = b in BITS[name]
        state = str(int(target and stage in ('applied', 'reloaded')))
        need(rise == fall == state, 'Target/protected direction exclusion state')
        if stage == 'before' and target:
            need(coverage == '0.00%', 'Native source constant already covered; no raw projection')
        identity = (path, meta, label)
        if previous is not None:
            need(key in previous and identity == previous[key][:3], 'Native token identity drift')
            if not target or stage in ('reset', 'final'):
                need(coverage == previous[key][3], 'Protected/reset bit coverage drift')
        found[key] = (*identity, coverage, rise, fall)
    need(set(found) == {(n, b) for n, w in WIDTHS.items() for b in range(w)}, 'Full117 bit complement')
    need(len({v[0] for v in found.values()}) == 117 and len({v[1] for v in found.values()}) == 117,
         'Native bit path/meta bijection')
    return found


def inventory(out, c, stage):
    for index, i in enumerate(c['instances']):
        actual = ptw.bind(i, (out / ('native_%s_%d.tsv' % (stage, index))).read_text())
        if stage != 'before':
            before = ptw.bind(i, (out / ('native_before_%d.tsv' % index)).read_text())
            ptw.soc.stage_gate(i, before, actual, stage)
        prior = None if stage == 'before' else bit_gate((out / ('bits_before_%d.tsv' % index)).read_text(), i, 'before')
        bit_gate((out / ('bits_%s_%d.tsv' % (stage, index))).read_text(), i, stage, prior)


def selection(c):
    text = ''.join('set mq_%s {%s}\n' % (k, c[k]) for k in ('design', 'vdb', 'test'))
    text += 'set mq_instances [list ' + ' '.join('[list {%s} [list %s]]' %
            (i['scope'], ' '.join('{%s}' % x for x in ptw.labels(i))) for i in c['instances']) + ']\n'
    return text + 'set tied_python {%s}\nset tied_helper {%s}\nset tied_seal $env(C1424_CONFIG_SEAL)\n' % (sys.executable, SCRIPT)


def prepare(out):
    need(out.parent == life.OUT and not out.exists(), 'Fresh independent output only')
    proof = evidence()
    template = life.read_bound(ptw.primitive.old.RUN / 'config.json', ptw.primitive.old.SEAL)
    pins = life.merge_pins(proof['pins'], template['pins'])
    pins[str(ptw.primitive.old.RUN / 'config.json')] = ptw.primitive.old.SEAL
    for module in list(sys.modules.values()):
        p = getattr(module, '__file__', None)
        if p and Path(p).resolve().parent == HERE:
            pins[str(Path(p).resolve())] = life.digest(p)
    pins.update(ptw.frozen.tcl_pins(TCL))
    pins[str(TEST)] = life.digest(TEST)
    c = dict(schema=SCHEMA, output=str(out), instances=proof['instances'], pins=pins,
        identity=template['identity'], timeout_seconds=900, directions=1424,
        population_application=False, automatic_retry=False, initial_X_qualified=False,
        **{k: proof[k] for k in ('design', 'vdb', 'test')})
    el = candidate(c)
    el_gate(el, c)
    life.check(pins)
    out.mkdir()
    life.save(out / 'source-proof.json', proof)
    for name, text in [('selection.tcl', selection(c)), ('candidate.el', el), ('native-bind.tcl', TCL.read_text())]:
        with (out / name).open('x') as stream:
            stream.write(text)
        if name.endswith('.tcl'):
            ptw.primitive.check_generated_tcl.check(out / name)
        pins[str(out / name)] = life.digest(out / name)
    pins[str(out / 'source-proof.json')] = life.digest(out / 'source-proof.json')
    life.save(out / 'config.json', c)
    return dict(output=str(out), seal=life.digest(out / 'config.json'), directions=1424, EDA_started=False,
                status='PREPARED_PARENT_REVIEW_REQUIRED_NATIVE_HOLD')


def check(out, seal):
    c = life.read_bound(out / 'config.json', seal)
    life.check(c['pins'])
    need(c['schema'] == SCHEMA and c['output'] == str(out) and c['directions'] == 1424 and
         c['timeout_seconds'] == 900 and c['population_application'] is False and
         c['automatic_retry'] is False and c['initial_X_qualified'] is False, 'Closed local contract')
    proof = evidence()
    need(all(c[k] == proof[k] for k in ('instances', 'design', 'vdb', 'test')), 'Source/typed/sample replay')
    need(json.loads((out / 'source-proof.json').read_bytes()) == proof, 'Exact source packet')
    origin = ptw.primitive.old.RUN / 'config.json'
    template = life.read_bound(origin, ptw.primitive.old.SEAL)
    need(c['identity'] == template['identity'], 'Sealed native executable roles')
    required = life.merge_pins(proof['pins'], template['pins'])
    required[str(origin)] = ptw.primitive.old.SEAL
    required.update(ptw.frozen.tcl_pins(TCL))
    need(all(c['pins'].get(p) == sha for p, sha in required.items()), 'Complete required dependency pins')
    for p in (SCRIPT, TEST, TCL):
        need(c['pins'].get(str(p)) == life.digest(p), 'Required source/test/Tcl pin')
    need((out / 'selection.tcl').read_text() == selection(c) and
         (out / 'native-bind.tcl').read_text() == TCL.read_text(), 'Exact native driver')
    el_gate((out / 'candidate.el').read_text(), c)
    return c


def verify(out, seal):
    c = check(out, seal)
    need(not (out / 'error.txt').exists(), 'Native failure recorded')
    terminal = json.loads((out / 'terminal.json').read_bytes())
    live = json.loads((out / 'live-identity.json').read_bytes())
    execution = json.loads((out / 'execution.json').read_bytes())
    ptw.terminal_gate(c, seal, out, terminal, live, execution)
    need(len(live) == 1, 'One actual sealed native executable')
    log = (out / 'DVEfiles/dve_gui.log').read_text()
    need(log.splitlines().count('C9101424_FIVE_PHASE_DONE') == 1 and
         not re.search(r'C9101424_FAILED|EK-CMD-\d+|extra characters after close-brace', log), 'Native completion')
    need((out / 'selected_tests.txt').read_text().splitlines() == [c['test']], 'Actual admitted sample selection')
    for stage in STAGES:
        inventory(out, c, stage)
    need(el_gate((out / 'first.el').read_text(), c) == el_gate((out / 'second.el').read_text(), c), 'Exact1424 reload')
    for name in ('initial-empty.el', 'reset-empty.el', 'final-empty.el'):
        need((out / name).read_bytes() == b'', 'Global empty EL')
    names = ['config.json', 'terminal.json', 'live-identity.json', 'execution.json', 'selected_tests.txt',
             'first.el', 'second.el', 'initial-empty.el', 'reset-empty.el', 'final-empty.el', 'DVEfiles/dve_gui.log']
    names += ['%s_%s_%d.tsv' % (prefix, stage, index) for prefix in ('native', 'bits')
              for stage in STAGES for index in range(8)]
    pins = life.merge_pins(c['pins'], {str(out / n): life.digest(out / n) for n in names})
    life.check(pins)
    return dict(status='C9101424_LOCAL_NATIVE_QUALIFIED_NOT_APPLIED', directions=1424,
        native_input_bits=936, protected_input_directions=448, protected_objects=1664,
        pins=pins, config_seal=seal, population_application=False, raw_physical_mapping=False,
        initial_X_qualified=False, official_gain=None)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'check', 'inventory', 'el', 'verify'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seal')
    p.add_argument('--stage', choices=STAGES)
    p.add_argument('--file', choices=('first.el', 'second.el'))
    a = p.parse_args()
    out = a.output.resolve()
    if a.mode == 'prepare':
        need(a.seal is None, 'Prepare is not launch approval')
        result = prepare(out)
    else:
        c = check(out, a.seal)
        if a.mode == 'inventory':
            inventory(out, c, a.stage)
        elif a.mode == 'el':
            need(a.file is not None, 'Explicit native export')
            el_gate((out / a.file).read_text(), c)
        result = verify(out, a.seal) if a.mode == 'verify' else dict(status=a.mode + '_PASS_NO_LAUNCH')
    print(json.dumps(result, indent=2), flush=True)
