"""Frozen-source structural candidates only; no native capture or waiver approval."""
import argparse
import hashlib
import json
import re
from pathlib import Path

import build_operand_index_snapshot_preflight as context
from closure_point_inventory import points, read_xml

ROOT, OUT = context.ROOT, context.OUT
BASE = context.BASE
ROLES = ('AluA', 'AluB', 'MulFPUA', 'MulFPUB', 'MulFPUC',
         'MaskB', 'MaskM', 'StA', 'SlideAddrGenA')


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def clean(text):
    # Keep offsets and line numbers; strings/comments cannot create writes.
    pattern = r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"'
    return re.sub(pattern, lambda m: ''.join('\n' if c == '\n' else ' '
                                             for c in m.group()), text)


def writes(text, names):
    source = clean(text)
    pattern = (r'\b(' + '|'.join(map(re.escape, names)) +
               r')(\s*\[[^\]\n]+\])?(\s*\.\s*\w+(?:\s*\[[^\]\n]+\])?)*'
               r'\s*(<=|\+=|-=|&=|\|=|=(?!=))\s*([^;]+);')
    records = []
    for match in re.finditer(pattern, source):
        lhs = source[match.start():match.start(4)]
        records.append(dict(lhs=re.sub(r'\s+', '', lhs), operator=match[4],
                            rhs=re.sub(r'\s+', '', match[5]),
                            line=source.count('\n', 0, match.start()) + 1))
    return records


def source_contract(package, sequencer, requester, lane):
    """A narrow checked source ledger, not a general SystemVerilog theorem engine.

    The sidecar additionally requires exact frozen bytes for every source. The
    lexical ledger documents all writes to the relevant storage on those bytes.
    """
    enum = re.search(r'typedef\s+enum\s+logic\s*\[[^\]]+\]\s*\{([^}]+)\}\s*opqueue_e',
                     clean(package))
    require(enum and tuple(v.strip() for v in enum[1].split(',')) == ROLES,
            'Operand enum differs')
    require("NrOperandQueues = 9;" in package, 'Queue count differs')
    producer = writes(sequencer, ('operand_request',))
    zero = [v for v in producer if v['lhs'] == 'operand_request']
    require(len(zero) == 1 and zero[0]['rhs'] == "'0" and zero[0]['operator'] == '=',
            'Producer global default is not zero')
    literal_lines = {}
    for role, count in (('MaskM', 6), ('StA', 1)):
        selected = [v for v in producer if v['lhs'].startswith('operand_request[' + role + ']')]
        literals = [v for v in selected if v['lhs'] == 'operand_request[' + role + ']']
        require(len(literals) == count, 'Whole literal inventory differs: ' + role)
        for record in literals:
            rhs = record['rhs']
            require(record['operator'] == '=' and rhs.startswith("'{") and rhs.endswith('}')
                    and "default:'0" in rhs and 'source_snapshot_replay' not in rhs,
                    'Nonzero/unknown whole producer: ' + role)
        for record in selected:
            if record in literals:
                continue
            field = record['lhs'].split('].', 1)[-1]
            require(field in ('vl', 'vstart', 'vs', 'eew', 'hazard'),
                    'Unproved role field write: ' + record['lhs'])
        literal_lines[role] = [v['line'] for v in literals]
    for record in producer:
        lhs = record['lhs']
        if lhs == 'operand_request' or any(lhs.startswith('operand_request[' + r + ']') for r in ROLES):
            continue
        require(lhs in ('operand_request[q].hazard_source_lifetime',
                        'operand_request[q].hazard_wait_complete'),
                'Unproved dynamic producer write: ' + lhs)

    queue = writes(sequencer, ('operand_request_d', 'operand_request_o'))
    expected_queue = [
        ('operand_request_d[queue]', '=', 'operand_request_o[queue]'),
        ('operand_request_d[queue]', '=', "'0"),
        ('operand_request_d[queue]', '=', 'operand_request[queue]'),
        ('operand_request_o', '<=', "'0"),
        ('operand_request_o', '<=', 'operand_request_d')]
    require([(v['lhs'], v['operator'], v['rhs']) for v in queue] == expected_queue,
            'Queue hold/clear/push/reset propagation differs')
    metadata = writes(requester, ('requester_metadata_tmp', 'requester_metadata_d',
                                 'requester_metadata_q'))
    tmp = [v for v in metadata if v['lhs'] == 'requester_metadata_tmp']
    require(len(tmp) == 1 and tmp[0]['operator'] == '=' and
            'source_snapshot_replay:operand_request_i[requester_index].source_snapshot_replay,'
            in tmp[0]['rhs'], 'Metadata input replay propagation differs')
    whole = [v for v in metadata if '.' not in v['lhs'] and v not in tmp]
    require([(v['lhs'], v['operator'], v['rhs']) for v in whole] == [
        ('requester_metadata_d[requester_index]', '=', 'requester_metadata_q[requester_index]'),
        ('requester_metadata_d[requester_index]', '=', 'requester_metadata_tmp'),
        ('requester_metadata_d[requester_index]', '=', 'requester_metadata_tmp'),
        ('requester_metadata_d[requester_index]', '=', "'0"),
        ('requester_metadata_q[requester_index]', '<=', "'0"),
        ('requester_metadata_q[requester_index]', '<=', 'requester_metadata_d[requester_index]')],
        'Metadata whole-storage propagation differs')
    for record in metadata:
        if record in whole or record in tmp:
            continue
        require(record['lhs'].startswith('requester_metadata_d[requester_index].') and
                record['lhs'].split('].', 1)[1].split('[', 1)[0] in
                ('waw_hazard_counter', 'addr', 'source_snapshot_index', 'len', 'hazard',
                 'hazard_source_lifetime', 'hazard_wait_complete'),
                'Unproved metadata field write: ' + record['lhs'])
    valid = writes(requester, ('source_snapshot_replay_valid_o',))
    require([(v['lhs'], v['operator'], v['rhs']) for v in valid] == [
        ('source_snapshot_replay_valid_o[requester_index]', '=', "1'b0"),
        ('source_snapshot_replay_valid_o[requester_index]', '=', '!stall[requester_index]')],
        'Replay-valid output writers differ')
    require(re.search(r'if\s*\(requester_metadata_q\[requester_index\]\.source_snapshot_replay\)'
                      r'\s*begin\s+source_snapshot_replay_valid_o\[requester_index\]\s*=',
                      clean(requester)), 'Nonzero valid output is not replay gated')
    require(not writes(lane, ('operand_request',)), 'Lane overwrites sequencer request')
    for port in ('operand_request_o', 'operand_request_i'):
        require(len(re.findall(r'\.' + port + r'\s*\(\s*operand_request\s*\)', clean(lane))) == 1,
                'Lane direct route differs: ' + port)
    require('logic source_snapshot_replay;' in lane, 'Compiled command field missing')
    require('source_snapshot_replay: pe_req.source_snapshot_replay_vs2' in sequencer,
            'Protected port8 producer missing')
    return dict(literal_lines=literal_lines, producer_writes=producer,
                queue_writes=queue, metadata_writes=metadata, valid_writes=valid,
                invariant='After reset, MaskM6/StA7 producer, queued command, metadata replay '
                          'and replay_valid are zero on every normal two-state cycle. '
                          'Hold, clear, push, dequeue, replacement and flush preserve zero.',
                scope_limits='Frozen elaboration only; no pre-reset/X-state claim; '
                             'does not prove unrelated conversions or exclude whole queues.')


def compiled_points(design, bits):
    root = read_xml(design.db / 'shape/cond.verilog.shape.xml')
    candidates, protected = [], []
    for lane in range(4):
        scope = ('ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[%d].i_lane.'
                 'i_operand_requester') % lane
        require(design.source(scope)['resolved_path'] ==
                str(ROOT / 'hardware/src/lane/operand_requester.sv'), 'Compiled owner differs')
        for metric in ('cond', 'branch'):
            row = bits['metrics'][metric][scope]
            definition = (next(n for n in root if n.get('id') == design.hierarchy[scope].get('id'))
                          if metric == 'cond' else design.definition(scope, metric))
            require(row['width'] == (1256 if metric == 'cond' else 752) and
                    row['checksum'] == definition.get('chksum') ==
                    ('1592560956' if metric == 'cond' else '1229254119'), 'Compiled shape differs')
            for point in points(metric, definition, row['width']):
                for port in (6, 7, 8):
                    if metric == 'cond':
                        expression = point['expression']
                        selected = (('operand_request_i[%d].source_snapshot_replay ?' % port)
                                    in expression or 'source_snapshot_replay_valid_o[%d]' % port
                                    in expression)
                        target = selected and ((point['line'] == '427' and point['vector'] == '1')
                                              or (point['line'] in ('359', '535') and
                                                  point['vector'] == '01'))
                    else:
                        leaves = [e for e in point['expressions'] if e.get('exprstr') ==
                                  'requester_metadata_q[%d].source_snapshot_replay' % port]
                        selected = bool(leaves)
                        require(len(leaves) <= 1, 'Ambiguous replay leaf')
                        target = selected and point['native_vector']['vector'][-int(leaves[0]['index'])] == '1'
                    if not selected:
                        continue
                    hit = bool(int(row['bits'], 16) & (1 << (row['width'] - 1 - point['raw_index'])))
                    record = dict(scope=scope, metric=metric, port=port, role=ROLES[port],
                                  width=row['width'], checksum=row['checksum'], hit_before=hit,
                                  point=point, native_GUI_bound=False)
                    if target and port in (6, 7):
                        require(not hit, 'Structural candidate already hit')
                        candidates.append(record)
                    else:
                        protected.append(record)
    require(len(candidates) == 32 and len({(r['scope'], r['metric'], r['point']['raw_index'])
                                        for r in candidates}) == 32, 'Incomplete candidate inventory')
    require(all(sum(r['port'] == port and r['metric'] == metric for r in candidates) ==
                (12 if metric == 'cond' else 4) for port in (6, 7) for metric in ('cond', 'branch')),
            'Role candidate population differs')
    return candidates, protected


def prepare(output):
    output = output.absolute()
    require(output.parent == OUT and not output.exists() and output.resolve() == output,
            'Fresh independent sidecar required')
    pins = {}
    def pin(path, expected=None):
        path = Path(path).absolute()
        require(path.resolve() == path and not path.is_symlink(), 'Aliased proof input')
        sha = digest(path)
        require(expected is None or sha == expected, 'Frozen pin differs: ' + str(path))
        pins[str(path)] = sha
        return path
    build = json.loads(pin(context.old.BUILD / 'build-source-pins.json').read_bytes())
    texts = {}
    sources = {}
    for key, relative in (
            ('package', 'hardware/include/ara_pkg.sv'),
            ('sequencer', 'hardware/src/lane/lane_sequencer.sv'),
            ('requester', 'hardware/src/lane/operand_requester.sv'),
            ('lane', 'hardware/src/lane/lane.sv')):
        original = ROOT / relative
        chosen = (OUT / 'old-image-source-evidence-20261006-01/lane_sequencer.sv'
                  if key == 'sequencer' else original)
        sources[key] = str(pin(chosen, build[str(original)]))
        texts[key] = chosen.read_text()
    contract = source_contract(**texts)
    manifest = json.loads(pin(BASE / 'admission-manifest.json',
        'c7070c02860d4a6f5e12f405f926cd19fc6e6498d1905298e5e32826ee3a8ae0').read_bytes())
    bitpath = BASE / 'combined-bits.json'
    bits = json.loads(pin(bitpath, manifest['output_pins'][str(bitpath)]).read_bytes())
    require(len(bits['tests']) == len(set(bits['tests'])) == 724, 'Not exact formal724 bitmap')
    design = context.s.Design(context.old.BUILD / 'sim/simv.vdb')
    for relative, sha in bits['design'].items():
        pin(design.db / relative, sha)
    for relative in ('auxiliary/verilog.sourceinfo.xml', 'shape/line.verilog.info.xml',
                     'shape/branch.verilog.info.xml', 'shape/tgl.verilog.info.xml',
                     'shape/tgl.verilog.shape.xml'):
        pin(design.db / relative)
    for lane_id in range(4):
        lane_scope = ('ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[%d].i_lane' % lane_id)
        for scope, relative in ((lane_scope, 'hardware/src/lane/lane.sv'),
                                (lane_scope + '.i_lane_sequencer',
                                 'hardware/src/lane/lane_sequencer.sv')):
            require(design.source(scope)['resolved_path'] == str(ROOT / relative),
                    'Compiled producer/route owner differs')
    candidates, protected = compiled_points(design, bits)
    for path in (Path(__file__).resolve(), Path(__file__).with_name('test_prove_mask_store_snapshot_zero.py')):
        pin(path)
    # Bind the actual local helper implementations used for XML/bitmap mapping.
    import sys
    for module in list(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if path and Path(path).suffix == '.py' and ROOT / 'verification' in Path(path).absolute().parents:
            pin(path)
    for path, sha in pins.items():
        require(digest(path) == sha, 'Input changed during proof construction')
    result = dict(schema='MASKM6_STA7_SNAPSHOT_ZERO_STRUCTURAL_CANDIDATES_V1',
        status='STRUCTURAL32_NATIVE_QUALIFICATION_REQUIRED_NOT_APPROVED',
        baseline=str(BASE), historical_tests=724, pins=pins, sources=sources,
        source_contract=contract, candidates=candidates, protected=protected,
        counts=dict(candidates=32, cond=24, branch=8, protected=len(protected)),
        port8_protected=True, native_GUI_bound=False, exclusions_generated=False,
        coverage_admitted=False, EDA_started=False,
        obligations=['Exact native scope/expression/vector binding and roundtrip.',
                     'Protect all listed noncandidate rows, especially port8.',
                     'Rebind newest bitmap and check existing policies for overlap before application.'])
    with output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    return dict(output=str(output), seal=digest(output), status=result['status'], counts=result['counts'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.output)))


if __name__ == '__main__':
    main()
