"""Frozen-source diagnostic candidates and compiled capacity, never an EL approval."""
import argparse
import json
from pathlib import Path
import re

import queue_constant_native as q

ROOT, OUT = q.life.ROOT, q.life.OUT
PREFIX = 'ara_tb.dut.i_ara_soc.i_system.i_ara'


def references(text, name):
    pattern = re.compile(r'(?<![\w$])' + re.escape(name) + r'(?![\w$])')
    return [dict(line=i, text=line.strip()) for i, line in enumerate(text.splitlines(), 1)
            if pattern.search(line) and not line.lstrip().startswith('//')]


def collect():
    book = OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json'
    original = json.loads(book.read_bytes())
    pins = {str(book): q.life.digest(book)}
    texts = {}
    for rel in ('hardware/src/vlsu/vlsu.sv', 'hardware/src/vlsu/qbs/qbs_engine.sv',
                'hardware/src/vlsu/qbs/qbs_compute_engine.sv',
                'hardware/src/vlsu/qbs/qbs_read_engine.sv',
                'hardware/src/vlsu/akv/akv_engine.sv', 'hardware/src/ara_sequencer.sv',
                'hardware/src/ara_system.sv', 'hardware/src/ara.sv'):
        path = ROOT / rel
        q.require(q.life.digest(path) == original[str(path)], 'Frozen source differs: ' + rel)
        pins[str(path)] = original[str(path)]
        texts[path.name] = path.read_text()
    capture = OUT / 'queue-constant-native-744-agent-20261007-03'
    config = q.life.read_bound(capture / 'config.json',
        'b2d53834d046de0a722342dfdce8dbdacc7c3898c2abb21e9618d8adae0dd7a6')
    pins[str(capture / 'config.json')] = q.life.digest(capture / 'config.json')
    base = Path(config['design']) / 'snps/coverage/db'
    design = q.Design(Path(config['design']))
    info = q.toggle.xml(base / 'shape/tgl.verilog.info.xml')
    shape = q.toggle.xml(base / 'shape/tgl.verilog.shape.xml')
    checks = {n.get('name'): n.get('chksum') for n in info.iter('instance_data')}
    definitions = {n.get('chksum'): n for n in shape.findall('tgldef')}
    for rel in ('shape/tgl.verilog.info.xml', 'shape/tgl.verilog.shape.xml',
                'design/verilog.design.xml'):
        path = base / rel
        q.require(str(path) in config['pins'], 'Unbound compiled shape')
        pins[str(path)] = config['pins'][str(path)]
    q.life.check(pins)
    groups = []

    def group(label, scope, names, source, rationale, status):
        nodes = {n.get('name'): n for n in definitions[checks[scope]].iter()
                 if n.tag in ('node', 'vectornode')}
        fields, absent = [], []
        for name in sorted(set(names)):
            if name not in nodes:
                absent.append(name)
                continue
            node = nodes[name]
            width = 1 if node.tag == 'node' else abs(int(node.get('left')) - int(node.get('right'))) + 1
            fields.append(dict(name=name, bits=width, directions=2 * width,
                compiled=dict(node.attrib), source_references=references(texts[source], name)))
        groups.append(dict(group=label, scope=scope, status=status, source=str(ROOT / (
            'hardware/src/' + ('vlsu/' + ('qbs/' if source.startswith('qbs_') else
             'akv/' if source.startswith('akv_') else '') if source != 'ara_sequencer.sv' else '') + source)),
            rationale=rationale, module_checksum=design.hierarchy[scope].get('chksum'),
            toggle_checksum=checks[scope], fields=fields, absent_from_toggle_shape=absent,
            bits=sum(f['bits'] for f in fields), directions=sum(f['directions'] for f in fields)))

    for source, suffix in (('qbs_engine.sv', '.i_vlsu.i_qbs_engine'),
                           ('qbs_compute_engine.sv', '.i_vlsu.i_qbs_engine.i_compute_engine'),
                           ('qbs_read_engine.sv', '.i_vlsu.i_qbs_engine.i_read_engine')):
        names = re.findall(r'logic \[31:0\]\s+(probe_\w+_q)\s*;', texts[source])
        group('complete_observation_probe_counters', PREFIX + suffix, names, source,
              'Each complete 32-bit field resets/clears/self-accumulates from product inputs; '
              'read only by its own update and VLSU QBS_PERF display. No product feedback.',
              'SOURCE_REVIEW_ELIGIBLE_NATIVE_REQUIRED')

    vlsu = texts['vlsu.sv']
    for source, child in (('qbs_engine.sv', 'i_qbs_engine'), ('akv_engine.sv', 'i_akv_engine')):
        header = texts[source].split(');', 1)[0]
        tail = header[header.index('output logic                         busy_o,'):]
        names = re.findall(r'output logic \[[^]]+\]\s+(\w+_o)', tail)
        group('complete_performance_output_fields', PREFIX + '.i_vlsu.' + child,
              names, source,
              'Whole performance output fields, not miss-selected bits. Engine readers include '
              'self-update/max and phase-accounting assertions, not product decision sinks; '
              'parent sinks are diagnostic display/AKV summary. Internal backing aliases need '
              'separate exact transitive binding before an all-counter-family EL.',
              'SOURCE_REVIEW_CANDIDATE_NATIVE_REQUIRED')
        connections = {}
        port_block = vlsu.split(') ' + child + ' (', 1)[1].split('\n  );', 1)[0]
        for name in names:
            matches = re.findall(r'\.' + re.escape(name) + r'\s*\(\s*((?:qbs|akv)_\w+)\s*\)', port_block)
            q.require(len(matches) == 1, 'Ambiguous diagnostic parent connection: ' + name)
            connections[name] = matches[0]
        group('parent_performance_wire_fields', PREFIX + '.i_vlsu', connections.values(),
              'vlsu.sv', 'Parent aliases of exact selected performance ports; all occurrences '
              'recorded for full-read verification. No output from VLSU or CSR response.',
              'SOURCE_REVIEW_CANDIDATE_NATIVE_REQUIRED')
        groups[-1]['producer_connections'] = connections

    scope = PREFIX + '.i_vlsu'
    nodes = [n.get('name') for n in definitions[checks[scope]].iter()
             if n.tag in ('node', 'vectornode')]
    snapshot = [n for n in nodes if n.startswith('gen_akv_integration_assertions.akv_consumed_request_q.')]
    group('entire_verification_request_snapshot', scope, snapshot, 'vlsu.sv',
          'Copy captured from pe_req_i, never a functional request producer; only whole-request '
          'stable assertion compares it. Assertion/fatal remains enabled. Actual pe_req/control protected.',
          'SOURCE_REVIEW_ELIGIBLE_NATIVE_REQUIRED')
    groups[-1]['whole_struct_source_references'] = references(vlsu, 'akv_consumed_request_q')
    group('AKV_print_summary', scope,
          ['gen_akv_integration_assertions.akv_perf_summary_q.' + n for n in re.findall(
              r'longint unsigned (\w+);', vlsu[vlsu.index('typedef struct {', vlsu.index('gen_akv_integration_assertions')):
              vlsu.index('} akv_perf_summary_t;')])], 'vlsu.sv',
          'All longint fields reset/accumulate/print; no hardware consumer. Missing compiled nodes '
          'contribute ZERO to candidate capacity, not a claimed 2048-bit reduction.',
          'SOURCE_ONLY_NO_COMPILED_TARGETS')
    groups[-1]['whole_struct_source_references'] = references(vlsu, 'akv_perf_summary_q')
    group('RVV_backend_observer_metadata', PREFIX + '.i_sequencer',
          ['verify_vinsn_alloc', 'verify_vinsn_done'], 'ara_sequencer.sv',
          'Only driven from allocation/completion state and connected to input-only '
          'ara_commit_monitor backend_alloc_i/backend_done_i; checks remain live.',
          'SOURCE_REVIEW_ELIGIBLE_NATIVE_REQUIRED')
    eligible = [g for g in groups if g['status'] != 'SOURCE_ONLY_NO_COMPILED_TARGETS']
    q.life.check(pins)
    return dict(status='FROZEN_SOURCE_SINK_COMPILED_CAPACITY_REVIEW_NOT_NATIVE_QUALIFIED',
        groups=groups, total_objects=sum(len(g['fields']) for g in eligible),
        total_bits=sum(g['bits'] for g in eligible),
        total_bit_directions=sum(g['directions'] for g in eligible),
        capacity_semantics='Logical compiled bits/directions, NOT official denominator or score gain; '
            'port aliases count separately only where compiler emits distinct nodes.',
        source_sink_notes=[
            'No unhit=>unreachable claim; this is integration diagnostic scope, whole selected fields.',
            'Summary struct not compiled as Toggle fields. No invented capacity.',
            'Internal metric backing registers/child statistics and arch metadata transport remain HOLD '
            'until their complete transitive consumers are reviewed; do not blanket-select perf/verify names.'
        ], protected=[
            'vinsn_retired_q clears read_list/write_list/read_mask; functional despite retirement name',
            'VFU instruction counters, FIFO occupancy, context indices, descriptor/dot_metadata and pointers',
            'architectural CSR values including cycle/instret, requests/results/flags/fault payloads',
            'all product control and all assertion/error/fatal/PASS gates'],
        native_qualified=False, application_approved=False, EDA_started=False, pins=pins)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    q.require(a.output.parent.resolve() == OUT and not a.output.exists(), 'Fresh evidence output only')
    data = collect()
    data['pins'][str(Path(__file__).resolve())] = q.life.digest(Path(__file__).resolve())
    q.life.save(a.output, data)
    print(json.dumps(dict(output=str(a.output), seal=q.life.digest(a.output),
        objects=data['total_objects'], bits=data['total_bits'], directions=data['total_bit_directions'])))
