#!/usr/bin/env python3
"""Prepare only: independent native selector experiments, never old-image waivers."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from closure_point_inventory import points, read_xml
from inventory_operand_debug import Design, ROOT
from inventory_lzc_selector_branches_705 import structural_node
from lzc_padding_proof import SOURCE_SHA256

HERE = Path(__file__).resolve().parent
OUT = ROOT / 'verification/out'
SOURCE = ROOT / 'hardware/deps/common_cells/src/lzc.sv'
BUILD = OUT / 'repaired-aligned-build-20260930-01'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, data):
    with path.open('x') as stream:
        stream.write(data if isinstance(data, str) else json.dumps(data, indent=2) + '\n')


def condition_definition(design, scope):
    db = design.db
    if not hasattr(design, 'lsn_cond_info'):
        design.lsn_cond_info = read_xml(db / 'shape/cond.verilog.info.xml')
        design.lsn_cond_shape = read_xml(db / 'shape/cond.verilog.shape.xml')
    info = design.lsn_cond_info
    checksums = [n.get('chksum') for n in info.iter('instance_data') if n.get('name') == scope]
    require(len(checksums) == 1, 'Missing/ambiguous condition checksum')
    module = design.hierarchy[scope]
    matches = [n for n in design.lsn_cond_shape
               if n.get('chksum') == checksums[0] and n.get('id') == module.get('id')]
    require(len(matches) == 1, 'Missing/ambiguous condition definition')
    return matches[0]


def compiled_points(design, scope, metric):
    node = condition_definition(design, scope) if metric == 'cond' else design.definition(scope, metric)
    width = (sum(int(n.get('totalbranches')) for n in node.iter('branch_spec'))
             if metric == 'branch' else
             sum(int(n.find('truth_table').get('nrows')) for n in node.iter('expr_monitored')))
    return node, points(metric, node, width)


def compiled_parameters(node):
    raw = node.get('param')
    if raw is None:
        name = node.get('name', '')
        require(name.count('( parameter ') == 1, 'Missing compiled parameters')
        raw = name.split('( parameter ', 1)[1].rsplit(')', 1)[0].strip()
    require(' + ' not in raw, 'Ambiguous compiled parameter family')
    result = {}
    for field in raw.split(','):
        key, sep, value = field.strip().partition('=')
        require(sep and key not in result, 'Malformed compiled parameters')
        result[key] = int(value)
    return result


def binding():
    branch_path = OUT / 'lzc-selector-branch-candidates-705-20261006-01.json'
    cond_path = OUT / 'lzc-selector-condition-candidates-705-20261006-01.json'
    bitmap_path = OUT / 'gap96-offline-admitted-705-20261006-01/combined-bits.json'
    status_path = bitmap_path.parent / 'status.json'
    pins = {}

    def pin(path, expected=None):
        value = sha(path)
        require(expected is None or value == expected, 'Input drift: ' + str(path))
        require(str(path) not in pins or pins[str(path)] == value, 'Conflicting pin')
        pins[str(path)] = value

    for path in (branch_path, cond_path, bitmap_path, status_path, BUILD / 'build-source-pins.json'):
        pin(path)
    pin(SOURCE, SOURCE_SHA256)
    branch = json.loads(branch_path.read_bytes())
    cond = json.loads(cond_path.read_bytes())
    bitmap = json.loads(bitmap_path.read_bytes())
    status = json.loads(status_path.read_bytes())
    require(status['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY' and status['aggregate_passed'] == 705,
            'Not raw705 admitted root')
    require(len(bitmap['tests']) == len(set(bitmap['tests'])) == 705, 'Wrong raw705 population')
    require(json.loads((BUILD / 'build-source-pins.json').read_bytes())[str(SOURCE)] == SOURCE_SHA256,
            'Not old-image LZC source')
    require(branch['candidate_count'] == len(branch['rows']) == 60 and not branch['native_qualified']
            and not branch['exclusions_applied'], 'Branch inventory not structural-only')
    for mapping in (branch['pins'], cond['input_sha256']):
        for path, expected in mapping.items():
            pin(Path(path), expected)
    require(cond['tests'] == bitmap['tests'], 'Condition population is not exact raw705')
    design = Design(BUILD / 'sim/simv.vdb')
    for relative, expected in bitmap['design'].items():
        pin(design.db / relative, expected)
    candidates = [dict(scope=r['scope'], metric='branch', point=r['point'], parameters=r['parameters'])
                  for r in branch['rows']]
    conditions = [r for r in cond['rows'] if r['decision'] in
                  ('STRUCTURAL_CANDIDATE_NATIVE_REQUIRED', 'HOLD_TERNARY_NATIVE_SEMANTICS')]
    require(Counter(r['decision'] for r in cond['rows']) == {
        'RETAIN_HIT': 22, 'STRUCTURAL_CANDIDATE_NATIVE_REQUIRED': 60,
        'HOLD_TERNARY_NATIVE_SEMANTICS': 60}, 'Not latest705 condition rebind')
    require(Counter(r['point']['attributes']['optype'] for r in conditions) == {'16': 60, '23': 60},
            'Wrong condition population')
    parameters = {r['scope']: r['parameters'] for r in branch['rows']}
    candidates += [dict(scope=r['point']['scope'], metric='cond', point=r['point'],
                        parameters=parameters[r['point']['scope']]) for r in conditions]
    protected, cache, seen, parameter_cache = [], {}, set(), {}
    for row in candidates:
        scope, metric, point = row['scope'], row['metric'], row['point']
        key = scope, metric, point['raw_index']
        require(key not in seen, 'Duplicate candidate')
        seen.add(key)
        require(design.source(scope)['resolved_path'] == str(SOURCE), 'Foreign compiled source')
        require(row['parameters']['WIDTH'] in (10, 23) and row['parameters']['MODE'] == 1,
                'Wrong compiled parameter family')
        if scope not in parameter_cache:
            parameter_cache[scope] = compiled_parameters(design.definition(scope, 'tgl'))
        require(parameter_cache[scope] == row['parameters'], 'Compiled WIDTH/MODE/coordinates drift')
        if (scope, metric) not in cache:
            node, population = compiled_points(design, scope, metric)
            record = bitmap['metrics'][metric][scope]
            require(record['checksum'] == node.get('chksum') and record['width'] == len(population),
                    'Raw705 metric shape differs')
            cache[scope, metric] = population
            protected.append(dict(scope=scope, metric=metric, checksum=node.get('chksum'), points=population))
        bound = cache[scope, metric][point['raw_index']]
        require(all(point.get(k) == v for k, v in bound.items()), 'Candidate compiled identity drift')
        record = bitmap['metrics'][metric][scope]
        require(not (int(record['bits'], 16) & (1 << (record['width'] - 1 - point['raw_index']))),
                'Candidate now hit in raw705; retain')
        probe = bound if metric == 'branch' else dict(bound, attributes={
            'generate_info': bound['spec']['generate_info'], 'totalbranches': '2'},
            expression=next(r['point']['expression'] for r in branch['rows']
                            if r['scope'] == scope and r['point']['attributes']['generate_info'] ==
                            bound['spec']['generate_info']))
        require(structural_node(probe, row['parameters']['WIDTH']) is not None, 'Not padded-left selector')
    for path in (Path(__file__).resolve(), HERE / 'lzc_selector_native_capture.tcl'):
        pin(path)
    for path, expected in list(pins.items()):
        pin(Path(path), expected)
    return dict(status='STATIC_BOUND_NATIVE_UNQUALIFIED', candidates=candidates, protected=protected,
                pins=pins, source_sha256=SOURCE_SHA256, old_image_exclusions=False,
                limitation='Two-state proof only. No native arm/vector semantics inferred.')


def calibration_sv(width, selector, parity):
    middle = 1 << ((width - 1).bit_length() - 1)
    index = parity if selector else middle + parity
    value = 1 << (width - 1 - index)
    top = f'lzc_selector_native_w{width}_s{selector}_p{parity}'
    text = f'''`timescale 1ns/1ps
module {top};
  wire [{width-1}:0] input_bits = {width}'h{value:x};
  wire [{(width-1).bit_length()-1}:0] count;
  wire empty;
  lzc #(.WIDTH({width}), .MODE(1)) dut
    (.in_i(input_bits), .cnt_o(count), .empty_o(empty));
  initial begin
    #1;
    if (dut.gen_lzc.sel_nodes[1] !== 1'b{selector} ||
        dut.gen_lzc.index_nodes[0] !== {index} || count !== {index} || empty !== 1'b0)
      $fatal(1, "LZC_SELECTOR_NATIVE_SEMANTIC_FAILURE");
    $display("LZC_SELECTOR_NATIVE_OBSERVED width={width} selector={selector} index={index} parity={parity}");
    #1;
    $finish;
  end
endmodule
'''
    return top, text


def prepare(output):
    require(output.parent == OUT and not output.exists(), 'Fresh direct verification/out directory required')
    record = binding()
    output.mkdir()
    write(output / 'binding.json', record)
    experiments = []
    for width in (10, 23):
        for selector in (0, 1):
            for parity in (0, 1):
                top, sv = calibration_sv(width, selector, parity)
                case = output / top
                case.mkdir()
                write(case / (top + '.sv'), sv)
                compile_command = ['timeout', '120s', 'vcs', '-full64', '-sverilog', '-cm', 'branch+cond+tgl+line',
                                   '-cm_dir', str(case / 'simv.vdb'),
                                   '+incdir+' + str(SOURCE.parent.parent / 'include'),
                                   str(SOURCE.parent / 'cf_math_pkg.sv'), str(SOURCE),
                                   str(case / (top + '.sv')), '-top', top, '-o', str(case / 'simv')]
                experiments.append(dict(top=top, width=width, selector=selector, parity=parity,
                                        cwd=str(case), compile_argv=compile_command,
                                        run_argv=['timeout', '120s', str(case / 'simv'), '-cm', 'branch+cond+tgl+line',
                                                  '-cm_name', top], timeout_seconds=120))
    write(output / 'experiments.json', dict(status='PREPARED_PARENT_APPROVAL_REQUIRED',
          experiments=experiments, native_qualified=False, application_approval=False,
          next='Approve isolated VCS calibration first; bind-case prepares DVE captures afterward.'))
    print(json.dumps(dict(status='PREPARED_NO_TOOLS_LAUNCHED', branch=60, op16=60, op23=60,
                          protected_positions=sum(len(r['points']) for r in record['protected']),
                          experiments=len(experiments))))


def tcl_word(value):
    value = str(value)
    require(not any(c in value for c in '{}\\\n\r'), 'Unsafe Tcl word')
    return '{' + value + '}'


def bind_case(case, output):
    require(case.parent.parent == OUT and case.name.startswith('lzc_selector_native_'), 'Standalone case only')
    require(output.parent == case and not output.exists(), 'Fresh capture directory inside standalone case')
    prepared = json.loads((case.parent / 'experiments.json').read_bytes())
    matches = [r for r in prepared['experiments'] if r['cwd'] == str(case)]
    require(len(matches) == 1, 'Unprepared calibration')
    experiment = matches[0]
    binding_record = json.loads((case.parent / 'binding.json').read_bytes())
    for path, expected in binding_record['pins'].items():
        require(sha(path) == expected, 'Prepared input drift: ' + path)
    top, sv = calibration_sv(experiment['width'], experiment['selector'], experiment['parity'])
    require((case / (top + '.sv')).read_text() == sv, 'Calibration source drift')
    log = (case / 'simulation.log').read_text()
    index = experiment['parity'] if experiment['selector'] else (
        1 << ((experiment['width'] - 1).bit_length() - 1)) + experiment['parity']
    marker = (f"LZC_SELECTOR_NATIVE_OBSERVED width={experiment['width']} "
              f"selector={experiment['selector']} index={index} parity={experiment['parity']}")
    require(log.count(marker) == 1 and 'LZC_SELECTOR_NATIVE_SEMANTIC_FAILURE' not in log and
            'Fatal' not in log and '$fatal' not in log, 'Missing independent semantic observation')
    design = Design(case / 'simv.vdb')
    scope = top + '.dut'
    require(design.source(scope)['resolved_path'] == str(SOURCE), 'Foreign standalone LZC')
    parameters = compiled_parameters(design.definition(scope, 'tgl'))
    require(parameters.get('WIDTH') == experiment['width'] and parameters.get('MODE') == 1,
            'Standalone compiled WIDTH/MODE differs')
    tests = list((design.db / 'testdata').iterdir())
    require(len(tests) == 1 and tests[0].is_dir() and tests[0].name == top, 'Exactly one standalone test required')
    groups, targets = [], []
    for metric in ('branch', 'cond'):
        _, population = compiled_points(design, scope, metric)
        for p in population:
            if metric == 'branch':
                groups.append([metric, p['native_id'], p['vector'], p['expression']])
                coord = p['attributes'].get('generate_info')
            else:
                groups.append([metric, p['native_id'], p['vector'], p['expression']])
                coord = p['spec'].get('generate_info')
            if p['line'] == '95' and coord == 'level=0,l=0' and (metric == 'branch' or
                    p['attributes'].get('optype') in ('16', '23')):
                targets.append(len(groups) - 1)
    require(len(targets) == 6, 'Root calibration shape differs; do not guess IDs')
    require(len({tuple(r[:3]) for r in groups}) == len(groups), 'Duplicate compiled native row')
    expressions = {}
    for metric, identity, vector, expression in groups:
        if metric == 'cond':
            require(expression not in expressions or expressions[expression] == identity,
                    'Ambiguous native condition expression; record API limitation, do not guess')
            expressions[expression] = identity
    output.mkdir()
    words = ['set lsn_scope ' + tcl_word(scope), 'set lsn_vdb ' + tcl_word(case / 'simv.vdb'),
             'set lsn_test ' + tcl_word(str(case / 'simv') + '/' + top),
             'set lsn_output ' + tcl_word(output), 'set lsn_rows {']
    words += ['  {' + ' '.join(tcl_word(v) for v in r) + '}' for r in groups]
    words += ['}', 'set lsn_targets {' + ' '.join(map(str, targets)) + '}']
    write(output / 'selection.tcl', '\n'.join(words) + '\n')
    pins = {str(p): sha(p) for p in (SOURCE, SOURCE.parent / 'cf_math_pkg.sv',
            case / 'simulation.log', case / (top + '.sv'), case / 'simv',
            output / 'selection.tcl', HERE / 'lzc_selector_native_capture.tcl')}
    pins.update({str(p): sha(p) for p in design.db.rglob('*') if p.is_file()})
    write(output / 'capture-plan.json', dict(status='PREPARED_PARENT_APPROVAL_REQUIRED', pins=pins,
          experiment=experiment, rows=groups, targets=targets, timeout_seconds=300,
          command=['timeout', '300s', 'xvfb-run', '-a', 'dve', '-full64', '-cov', '-script',
                   str(HERE / 'lzc_selector_native_capture.tcl')],
          environment={'LZC_SELECTOR_NATIVE_SELECTION': str(output / 'selection.tcl')},
          application_approval=False, native_qualified=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('--output', type=Path, required=True)
    p = sub.add_parser('bind-case')
    p.add_argument('--case', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'prepare':
        prepare(args.output.absolute())
    else:
        bind_case(args.case.absolute(), args.output.absolute())


if __name__ == '__main__':
    main()
