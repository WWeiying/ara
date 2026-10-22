"""Pinned-source producer-domain review; no native exclusion or EDA actions."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'verification/out'
BOOK = OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json'
BOOK_SHA = '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'
DIAGNOSTIC = OUT / 'vector-flow794-static-agent-20261008-02.json'
DIAGNOSTIC_SHA = 'c08a4f895b615903cb63e16225a0e0770aa53d59eb1c8b803d8a9375437181fd'
DOMAIN = {'OpQueueConversionNone', 'OpQueueConversionSExt2',
          'OpQueueConversionZExt2', 'OpQueueReductionZExt',
          'OpQueueConversionWideFP2'}
FORBIDDEN = {'OpQueueConversionSExt4', 'OpQueueConversionSExt8',
             'OpQueueConversionZExt4', 'OpQueueConversionZExt8'}
LEAVES = {'21': ('OpQueueConversionZExt8', 'EW8', 55),
          '18': ('OpQueueConversionZExt4', 'EW16', 58),
          '17': ('OpQueueConversionZExt4', 'EW8', 59),
          '9': ('OpQueueConversionSExt8', 'EW8', 67),
          '6': ('OpQueueConversionSExt4', 'EW16', 70),
          '5': ('OpQueueConversionSExt4', 'EW8', 71)}
SOURCES = ['hardware/src/ara_dispatcher.sv', 'hardware/src/ara_sequencer.sv',
           'hardware/src/segment_sequencer.sv', 'hardware/src/ara.sv',
           'hardware/src/lane/lane.sv', 'hardware/src/lane/lane_sequencer.sv',
           'hardware/src/lane/operand_requester.sv',
           'hardware/src/lane/operand_queues_stage.sv',
           'hardware/src/lane/operand_queue.sv', 'hardware/include/ara_pkg.sv',
           'hardware/deps/common_cells/src/fifo_v3.sv',
           'hardware/deps/common_cells/src/spill_register.sv',
           'hardware/deps/common_cells/src/spill_register_flushable.sv',
           'hardware/src/common_cells_compat/fall_through_register_v1.sv',
           'hardware/deps/common_cells/include/common_cells/registers.svh',
           'hardware/include/ara/ara_typedef.svh']


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code(text):
    # Preserve line numbers for this pinned-source lexical assignment audit.
    return re.sub(r'/\*.*?\*/|//[^\n]*',
                  lambda m: '\n' * m[0].count('\n'), text, flags=re.S)


def vs1_writes(text):
    text = code(text)
    pattern = r'(?:\b\w+\.conversion_vs1\s*=(?!=)\s*([^;]+);|\bconversion_vs1\s*:\s*([^,}]+))'
    return [dict(line=text[:m.start()].count('\n') + 1,
                 rhs=(m[1] or m[2]).strip()) for m in re.finditer(pattern, text)]


def domain_gate(text):
    writes = vs1_writes(text)
    require(writes and all(w['rhs'] in DOMAIN for w in writes),
            'Unreviewed conversion_vs1 producer')
    require({w['rhs'] for w in writes} == DOMAIN, 'Producer audit lost a reviewed domain member')
    return writes


def target_gate(point, items):
    require(point['native_id'] == '5' and point['vector'] in LEAVES,
            'Foreign branch leaf')
    conversion, eew, raw_index = LEAVES[point['vector']]
    require(point['raw_index'] == raw_index, 'Foreign serializer position')
    vector = point['native_vector']['vector']
    active = {n.get('name').strip() for n in items
              if vector[-int(n.get('index'))] == '1'}
    require(active == {conversion, eew}, 'Wrong conversion/EEW compiled path')
    require(conversion in FORBIDDEN, 'Active producer cannot be waived')


def collect():
    require(sha(BOOK) == BOOK_SHA and sha(DIAGNOSTIC) == DIAGNOSTIC_SHA,
            'Frozen authority drift')
    book = json.loads(BOOK.read_text())
    diagnostic = json.loads(DIAGNOSTIC.read_text())
    pins = dict(diagnostic['input_pins'])
    pins[str(BOOK)] = BOOK_SHA
    pins[str(DIAGNOSTIC)] = DIAGNOSTIC_SHA
    texts, source_binding = {}, []
    for relative in SOURCES:
        original = ROOT / relative
        expected = book[str(original)]
        path = original
        if sha(path) != expected:
            path = OUT / 'old-image-source-evidence-20261006-01' / path.name
        require(sha(path) == expected, 'Frozen source mismatch: ' + relative)
        pins[str(path)] = expected
        texts[original.name] = path.read_text()
        source_binding.append(dict(original=str(original), evidence=str(path), sha256=expected))
    dispatch = texts['ara_dispatcher.sv']
    writes = domain_gate(dispatch)
    require(len(vs1_writes(texts['ara_sequencer.sv'])) == 1 and
            vs1_writes(texts['ara_sequencer.sv'])[0]['rhs'] == 'ara_req_i.conversion_vs1',
            'Sequencer field forwarding changed')
    lane = code(texts['lane_sequencer.sv'])
    require(lane.count('operand_request[AluA] =') == 2,
            'Additional AluA aggregate producer')
    require("conv       : (vfu_operation_d.vl == '0) ? OpQueueReductionZExt : pe_req.conversion_vs1" in lane and
            'conv      : OpQueueConversionNone' in lane and
            'operand_request_push[AluA] = pe_req.use_vs1;' in lane,
            'AluA producer contract changed')
    require(not re.search(r'operand_request\[AluA\]\.conv\s*=', lane),
            'Additional AluA conversion override')
    require('.data_i    (pe_req_i' in lane and '.data_o    (pe_req' in lane and
            'fall_through_register_v1 #(' in lane, 'PE fall-through binding changed')
    fall_through = code(texts['fall_through_register_v1.sv'])
    require(".FALL_THROUGH(1'b1)" in fall_through and
            '.dtype       (T)' in fall_through and '.data_i,' in fall_through and
            '.data_o,' in fall_through, 'PE fall-through data producer changed')
    requester = code(texts['operand_requester.sv'])
    require('conv      : operand_request_i[requester_index].conv' in requester and
            not re.search(r'operand_queue_cmd_\w+[^;\n]*\.conv\s*=', requester),
            'Requester conversion override')
    fifo = code(texts['fifo_v3.sv'])
    require("mem_q <= {FifoDepth{dtype'('0)}};" in fifo and
            'mem_n[write_pointer_q] = data_i;' in fifo and
            'mem_n           = mem_q;' in fifo,
            'FIFO reset/write/hold proof changed')
    enum = code(texts['ara_pkg.sv'])
    require(re.search(r'typedef enum logic\s*\[\$clog2\(NumConversions\)-1:0\]\s*\{\s*OpQueueConversionNone,', enum),
            'Reset enum zero no longer None')
    from inventory_operand_debug import Design
    c = json.loads((OUT / 'current-population794-soc61-parent-20261008-01/config.json').read_text())
    design = Design(Path(c['input_ledger'][0]))
    targets, complements = [], []
    for lane_index in range(4):
        scope = ('ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[%d].i_lane.'
                 'i_operand_queues.i_operand_queue_alu_a') % lane_index
        definition = design.definition(scope, 'branch')
        require(definition.get('chksum') == '1417162425', 'Foreign compiled module')
        group = next(n for n in definition.iter('branch_spec') if n.get('id') == '5')
        selected = [x for x in diagnostic['gaps'] if x['scope'] == scope and
                    x['metric'] == 'branch' and x['point']['native_id'] == '5' and
                    x['point']['vector'] in LEAVES]
        require(len(selected) == 6, 'Missing/duplicate exact target')
        for entry in selected:
            target_gate(entry['point'], list(group.iter('branch_citem')))
            targets.append(dict(scope=scope, module_checksum=definition.get('chksum'),
                                group_checksum=group.get('chksum'), **entry['point']))
        all_vectors = list(group.iter('branch_vector'))
        require(len(all_vectors) == 46 and {n.get('id') for n in all_vectors} ==
                {str(i) for i in range(46)}, 'Incomplete group shape complement')
        complements.append(dict(scope=scope, group='5', total_vectors=46,
                                protected_vectors=[str(n.get('id')) for n in all_vectors
                                                   if n.get('id') not in LEAVES]))
    require(len(targets) == 24 and all(len(x['protected_vectors']) == 40 for x in complements),
            'Exact target/complement partition')
    for path, expected in pins.items():
        require(sha(Path(path)) == expected, 'Input pin drift: ' + path)
    pins[str(Path(__file__).resolve())] = sha(Path(__file__).resolve())
    return dict(status='SOURCE_ONLY_EXACT_BRANCH24_STRUCTURALLY_UNREACHABLE_CANDIDATE',
                population=794, input_pins=pins, source_binding=source_binding,
                conversion_vs1_all_explicit_writes=writes, dispatcher_domain=sorted(DOMAIN),
                use_vs1_all_explicit_writes=[dict(line=dispatch[:m.start()].count('\n')+1,
                                                rhs=m[1].strip()) for m in re.finditer(
                                                    r'ara_req\.use_vs1\s*=\s*([^;]+);', dispatch)],
                proof=[
                    'Dispatcher default plus every explicit conversion_vs1 producer is in DOMAIN, independent of use_vs1, opcode legality, vtype, VL/vstart, mask and error/abort state.',
                    'Idle and maintenance requests copy the default before decoding. Backend/blocked muxes and segment sequencer copy whole requests; segment rewrites do not touch conversion_vs1.',
                    'Ara sequencer default/reset are zero; the sole populated conversion_vs1 is forwarded; retry/hold copies preserve it. Ara/lane ports forward the same packed request.',
                    'Lane PE fall-through register is a typed fifo_v3 with FALL_THROUGH=1: zero-reset entries, domain-only writes, or direct domain input. AluA VFU_Alu command is DOMAIN or ReductionZExt when lane VL=0, with push gated use_vs1. MaskUnit AluA conversion is None; other/default paths are zero. Operand-request registers hold/copy/zero entire requests, including abort/flush.',
                    'Requester default command is zero, populated conv is forwarded, length/scale/slide/snapshot/flush logic does not override conv.',
                    'Command FIFO reset initializes all entries to zero=None. Push writes only domain commands; hold/pop/flush/pointer reads do not manufacture conversion values, including empty/stale reads.',
                    'Each target leaf requires conv in FORBIDDEN. DOMAIN intersection FORBIDDEN is empty; EEW, signedness, select and SupportIntExt4/8 cannot satisfy the missing conjunct.'
                ], targets=targets, group5_protected_complement=complements,
                protection='All other Branch vectors, metrics, scopes, interfaces, live conversion data/control remain untouched.',
                limitations=['Pinned-source review and finite-domain induction, not a formal-tool certificate.',
                             'Post-reset operation; no X-startup exclusion.',
                             'Native point-label/metric identity qualification and parent approval still required before any EL.'],
                native_qualified=False, EDA_started=False, EL_created=False,
                official_percentage=None, MFPU_B12_status='DEFERRED_NOT_REVIEWED_IN_THIS_PACKET',
                supersedes='01 was a draft receipt before closing the PE fall-through and macro source dependencies; use this replay only.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), 'Preserve existing evidence')
    result = collect()
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(result['status'], sha(args.output))
