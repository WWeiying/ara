"""Source-derived packed VCD aliases; no simulation, qualification or admission."""
import argparse
import json
import re
from pathlib import Path
from types import FunctionType, SimpleNamespace

import collect_csr_satp_sepc786 as original

life, require = original.life, original.require
RUN = life.OUT / 'csr-satp-sepc786-old-image-agent-20261008-02'
HOLD = life.OUT / 'csr-satp-sepc786-qualified-agent-20261008-01'
BOOK_SHA = '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'
COLLECTOR_SHA = '4028dccabd3e49bf40e8a04b050fabae23cee5fba155bd0a465cafed1f780833'
EXPECTED = {
    'scoreboard_entry_t': (438, {'trans_id': (373, 371)}),
    'fu_data_t': (207, {'trans_id': (2, 0), 'operand_a': (194, 131), 'operand_b': (130, 67)}),
    'mstatus_rv_t': (64, {'mprv': (17, 17), 'mie': (3, 3)}),
    'csr_reg_q': (13, {'valid': (0, 0)})}


def clean(text):
    return re.sub(r'//[^\n]*|/\*.*?\*/', '', text, flags=re.S)


def unique(pattern, text):
    matches = re.findall(pattern, text, re.S)
    require(len(matches) == 1, 'Missing/ambiguous source declaration: ' + pattern)
    return matches[0]


def integer(expr, params):
    expr = expr.strip()
    if expr.isdigit(): return int(expr)
    m = re.fullmatch(r'([\w.]+)(?:\s*-\s*(\d+))?', expr)
    require(m is not None and m[1] in params, 'Unsupported packed bound: ' + expr)
    return params[m[1]] - int(m[2] or 0)


def enum_width(text, name):
    bounds = unique(r'typedef\s+enum\s+logic\s*\[([^\]]+)\]\s*\{[^}]*\}\s*' + name + r'\s*;', text)
    left, right = bounds.split(':')
    require(left.strip().isdigit() and right.strip() == '0', 'Unsupported enum bound')
    return int(left) + 1


def packed(body, types, params):
    fields = []
    for statement in body.split(';'):
        if not statement.strip(): continue
        m = re.fullmatch(r'\s*(\w+)\s*(?:\[([^\]]+)\])?\s+(\w+)\s*', statement)
        require(m is not None, 'Unsupported/signed/array packed field')
        kind, bounds, name = m.groups()
        require(name not in [f[0] for f in fields], 'Duplicate packed field')
        if kind == 'logic':
            if bounds:
                left, right = bounds.split(':')
                l, r = integer(left, params), integer(right, params)
                require(l >= r == 0 or (l >= r >= 0 and left.strip().isdigit()), 'Packed range direction')
                width = l - r + 1
            else: width = 1
        else:
            require(bounds is None and kind in types, 'Unknown packed field type')
            width = types[kind]
        require(width > 0, 'Nonpositive field width')
        fields.append((name, width))
    total = sum(w for _, w in fields); offset = total; result = {}
    for name, width in fields:
        result[name] = [offset - 1, offset - width]; offset -= width
    return {'width': total, 'fields': result}


def derive(sources):
    s = {n: clean(t) for n, t in sources.items()}
    cfg, build = s['config'], s['build']
    xlen = int(unique(r'localparam\s+CVA6ConfigXlen\s*=\s*(\d+)\s*;', cfg))
    slots = int(unique(r'localparam\s+CVA6ConfigNrScoreboardEntries\s*=\s*(\d+)\s*;', cfg))
    vlen = int(unique(r'VLEN:\s*unsigned\x27\((\d+)\)', cfg))
    require(xlen == vlen == 64 and slots == 8, 'Frozen XLEN/VLEN/scoreboard configuration')
    for token in ("XLEN: unsigned'(CVA6ConfigXlen)", "NrScoreboardEntries: unsigned'(CVA6ConfigNrScoreboardEntries)"):
        require(token in cfg, 'Config producer binding')
    for token in ('cfg.XLEN = CVA6Cfg.XLEN;', 'cfg.VLEN = CVA6Cfg.VLEN;',
                  'cfg.GPLEN = (CVA6Cfg.XLEN == 32) ? 34 : 41;',
                  'cfg.TRANS_ID_BITS = $clog2(CVA6Cfg.NrScoreboardEntries);'):
        require(token in build, 'Derived config binding')
    params = {'CVA6Cfg.XLEN': xlen, 'CVA6Cfg.VLEN': vlen,
              'CVA6Cfg.GPLEN': 34 if xlen == 32 else 41,
              'CVA6Cfg.TRANS_ID_BITS': (slots - 1).bit_length(),
              'REG_ADDR_SIZE': int(unique(r'localparam\s+(?:int\s+)?REG_ADDR_SIZE\s*=\s*(\d+)\s*;', s['ariane']))}
    types = {n: enum_width(s['ariane'], n) for n in ('cf_t', 'fu_t', 'fu_op')}
    types.update({n: enum_width(s['riscv'], n) for n in ('xlen_e', 'xs_t', 'priv_lvl_t')})
    require(types == dict(cf_t=3, fu_t=4, fu_op=8, xlen_e=2, xs_t=2, priv_lvl_t=2), 'Exact enum widths')
    layouts = {}
    for name in ('exception_t', 'branchpredict_sbe_t', 'scoreboard_entry_t', 'fu_data_t'):
        body = unique(r'(?:localparam|parameter)\s+type\s+' + name + r'\s*=\s*struct\s+packed\s*\{([^{}]*)\}', s['cva6'])
        layouts[name] = packed(body, types, params); types[name] = layouts[name]['width']
    body = unique(r'typedef\s+struct\s+packed\s*\{([^{}]*)\}\s*mstatus_rv_t\s*;', s['riscv'])
    layouts['mstatus_rv_t'] = packed(body, types, params)
    body = unique(r'struct\s+packed\s*\{([^{}]*)\}\s*csr_reg_n\s*,\s*csr_reg_q\s*;', s['buffer'])
    layouts['csr_reg_q'] = packed(body, types, params)
    require(re.search(r'riscv::mstatus_rv_t\s+mstatus_q\s*,\s*mstatus_d\s*;', s['csr']) is not None, 'mstatus instance type')
    bindings = ((s['cva6'], r'csr_regfile\s*#\((.*?)\)\s*csr_regfile_i\s*\((.*?)\);',
                 ('scoreboard_entry_t', 'scoreboard_entry_t'), ('commit_instr_i', 'commit_instr_id_commit[0]')),
                (s['cva6'], r'ex_stage\s*#\((.*?)\)\s*ex_stage_i\s*\((.*?)\);',
                 ('fu_data_t', 'fu_data_t'), None),
                (s['ex'], r'csr_buffer\s*#\((.*?)\)\s*csr_buffer_i\s*\((.*?)\);',
                 ('fu_data_t', 'fu_data_t'), ('fu_data_i', 'one_cycle_data')))
    for text, pattern, parameter, port in bindings:
        parameters, ports = unique(pattern, text)
        def connected(body, connection):
            name, value = connection
            return re.search(r'\.' + name + r'\s*\(\s*' + re.escape(value) + r'\s*\)', body) is not None
        require(connected(parameters, parameter) and (port is None or connected(ports, port)), 'Packed instance binding')
    require(re.search(r'fu_data_t\s+one_cycle_data\s*;', s['ex']) is not None, 'CSR operand carrier type')
    for name, (width, fields) in EXPECTED.items():
        require(layouts[name]['width'] == width and all(layouts[name]['fields'].get(f) == list(b) for f, b in fields.items()),
                'Source-derived width/offset differs: ' + name)
    return {'parameters': params, 'enum_widths': types, 'layouts': layouts}


def source_proof():
    _, pins = original.runner.source_contract()
    book_path = original.oracle.inventory.BUILD / 'build-source-pins.json'
    require(life.digest(book_path) == BOOK_SHA, 'Frozen source book')
    book = json.loads(book_path.read_bytes()); root = life.ROOT / 'hardware/deps/cva6/core'
    names = dict(cva6='cva6.sv', buffer='csr_buffer.sv', csr='csr_regfile.sv', ex='ex_stage.sv',
                 ariane='include/ariane_pkg.sv', riscv='include/riscv_pkg.sv',
                 config='include/cv64a6_imafdcv_sv39_config_pkg.sv', build='include/build_config_pkg.sv')
    sources = {}
    for name, relative in names.items():
        path = root / relative
        require(str(path) in book and life.digest(path) == book[str(path)], 'Frozen layout source: ' + name)
        pins[str(path)] = book[str(path)]; sources[name] = path.read_text()
    require(life.digest(Path(original.__file__)) == COLLECTOR_SHA, 'Frozen original collector')
    pins[str(Path(original.__file__).resolve())] = COLLECTOR_SHA
    return dict(derive(sources), pins=pins)


def aliases(proof):
    owners = {original.CSR + '.commit_instr_i': 'scoreboard_entry_t',
              original.CSR + '.mstatus_q': 'mstatus_rv_t',
              original.BUFFER + '.fu_data_i': 'fu_data_t',
              original.BUFFER + '.csr_reg_q': 'csr_reg_q'}
    return {parent + '.' + field: dict(parent=parent, parent_width=EXPECTED[kind][0],
            left=proof['layouts'][kind]['fields'][field][0], right=proof['layouts'][kind]['fields'][field][1])
            for parent, kind in owners.items() for field in EXPECTED[kind][1]}


def declarations(decl, mapping):
    result = dict(decl); codes = {d['code'] for d in decl.values()}
    for i, (name, spec) in enumerate(mapping.items()):
        parent = decl.get(spec['parent'])
        require(parent is not None and parent['width'] == spec['parent_width'] and parent['type'] in ('wire', 'reg'),
                'Missing/wrong typed packed parent: ' + spec['parent'])
        require(name not in decl, 'Ambiguous pre-existing packed leaf')
        code = '__csr_packed_%d' % i
        require(code not in codes, 'Synthetic VCD code collision')
        result[name] = dict(width=spec['left'] - spec['right'] + 1, code=code, type=parent['type'])
    return result


def expand(state, decl, output, mapping):
    result = dict(state)
    for name, spec in mapping.items():
        bits = state.get(decl[spec['parent']]['code'], 'x')
        require(0 < len(bits) <= spec['parent_width'] and set(bits.lower()) <= set('01xz'), 'Invalid packed parent bits')
        bits = bits.lower().rjust(spec['parent_width'], bits[0] if bits[0] in 'xz' else '0')
        # SV packed structs place their first declared field at the MSB.
        result[output[name]['code']] = bits[spec['parent_width'] - 1 - spec['left']:spec['parent_width'] - spec['right']]
    return result


def vcd(path):
    mapping = aliases(source_proof())
    parser = FunctionType(original.wave.vcd.__code__, dict(original.wave.vcd.__globals__, ROOT='ara_tb', WIDTHS={'clk': 1, 'rst_n': 1}))
    stream = iter(parser(path)); tag, decl = next(stream)
    require(tag == 'declarations', 'VCD declaration header')
    output = declarations(decl, mapping); yield tag, output
    for time, before, after in stream:
        yield time, expand(before, decl, output, mapping), expand(after, decl, output, mapping)


def wave_audit(path, expected):
    audit = FunctionType(original.wave_audit.__code__, dict(original.wave_audit.__globals__, wave=SimpleNamespace(vcd=vcd)))
    return audit(path, expected)


def native_diagnostic(path, expected):
    # Extract through the original active-signal checks, but do not grant qualification.
    namespace = dict(original.wave_audit.__globals__, wave=SimpleNamespace(vcd=vcd),
                     owner_gate=lambda edges, want: list(edges))
    edges = FunctionType(original.wave_audit.__code__, namespace)(path, expected)
    pending, matched, differences = None, [], []
    for edge in edges:
        require(edge['commit'] == edge['buffer_commit'], 'Diagnostic commit handshake')
        require(edge['ready'] == int(not ((edge['buffer_valid'] or edge['issue']) and not edge['buffer_commit'])), 'Diagnostic ready formula')
        if edge['commit'] and edge['address'] in (0x180, 0x141):
            require(pending is not None and len(matched) < len(expected), 'Diagnostic owner missing/extra')
            want = expected[len(matched)]
            require(edge['ack'] & 1 and edge['pc'] == want['pc'] and
                    edge['address'] == pending['issue_address'] == want['csr'] and
                    edge['tid'] == pending['issue_tid'] and 0 <= edge['tid'] < 8 and
                    pending['cycle'] <= edge['cycle'] and
                    edge['wdata'] == pending['issue_operand'] == want['operand'] and
                    edge['rdata'] == want['old'] and edge['operation'] == want['operation'],
                    'Diagnostic field owner differs')
            differences.append(edge['cycle'] - want['cycle'])
            matched.append(dict(expected=want, issue=pending, commit=edge)); pending = None
        if edge['issue'] and edge['issue_address'] in (0x180, 0x141):
            require(pending is None and (not edge['buffer_valid'] or edge['buffer_commit']), 'Diagnostic occupied issue')
            pending = edge
        require(not (edge['flush'] and pending is not None), 'Diagnostic pending flush')
    require(pending is None and len(matched) == len(expected) == 30, 'Diagnostic incomplete owners')
    try:
        wave_audit(path, expected)
    except ValueError as error:
        strict_error = str(error)
    else:
        strict_error = None
    return dict(status='PACKED_FIELDS_DIAGNOSTIC_NOT_QUALIFICATION',
                matched_owners_except_cycle=len(matched), wave_minus_csv_cycle_deltas=differences,
                original_strict_gate_error=strict_error, qualification_passed=False, owners=matched)


def evidence():
    proof = source_proof()
    paths = [RUN / 'simulation-status.json', RUN / 'manifest.json', HOLD / 'failure.json', HOLD / 'csr-owner.vcd',
             Path(__file__).resolve(), Path(__file__).with_name('test_csr_satp_sepc_packed_adapter.py')]
    proof['pins'].update({str(p): life.digest(p) for p in paths})
    failure = json.loads((HOLD / 'failure.json').read_bytes())
    require(failure['status'] == 'QUALIFICATION_HOLD_NOT_ADMITTED' and failure['reason'] == 'Exact CSR probe declarations', 'Original HOLD changed')
    pre = life.read_bound(original.runner.PRE / 'preflight-manifest.json', original.runner.PRE_SEAL)
    reference = original.runner.reference(pre)
    rows = original.primitive.parse_rows(RUN / 'commit_trace.csv')
    expected = original.csr_expected(reference, rows, original.runner.source_contract()[0]['ops'])
    for path in (RUN / 'commit_trace.csv', original.runner.PRE / 'spike.trace', original.runner.PRE / 'preflight-manifest.json'):
        proof['pins'][str(path)] = life.digest(path)
    return dict(status='PACKED_LAYOUT_SOURCE_BOUND_ADAPTER_PREPARED_NOT_QUALIFIED',
                first_HOLD='Packed parent/leaf recording limitation; not evidence of RTL bug',
                aliases=aliases(proof), source_proof=proof, owner_gate='Unmodified original all30 owner gate',
                native_diagnostic=native_diagnostic(HOLD / 'csr-owner.vcd', expected),
                qualification_performed=False, simulation_performed=False)


if __name__ == '__main__':
    cli = argparse.ArgumentParser(); cli.add_argument('--output', type=Path, required=True)
    args = cli.parse_args(); result = evidence(); life.save(args.output, result)
    print(json.dumps(dict(status=result['status'], output=str(args.output), sha256=life.digest(args.output))))
