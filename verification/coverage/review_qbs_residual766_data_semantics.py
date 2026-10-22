"""Refine data-name heuristics using sealed formal766 typed coordinates."""
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / 'verification/out/qbs-engine-full102-residual766-static-agent-20261007-01.json'
AUDIT_SHA = 'b6fefc0d350ed0ca4d3add37f3b6a43fd6cb4a79742dc2384d9f297abd5a8cca'
OUT = ROOT / 'verification/out/qbs-engine-residual766-data-semantics-agent-20261007-01.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_verified():
    if sha(AUDIT) != AUDIT_SHA:
        raise ValueError('sealed audit mismatch')
    data = json.loads(AUDIT.read_text())
    for path, expected in data['pins'].items():
        if sha(path) != expected:
            raise ValueError('source/compiled/population pin mismatch: ' + path)
    return data


def split_selection(field, source):
    attrs = field['attributes']
    if (field['width'] != 9 or field['kind'] != 'vectornode'
            or attrs.get('left') != '8' or attrs.get('right') != '0'
            or attrs.get('portnode') != '0' or attrs.get('excluded') != '0'):
        raise ValueError('selection shape changed')
    line = field['source_binding']['line']
    terminal = field['name'].rsplit('.', 1)[-1]
    if terminal not in ('selected', 'older', 'newer'):
        raise ValueError('not a reviewed selection field')
    if f'wire [8:0] {terminal} = StreamWriteData' not in source.splitlines()[line - 1]:
        raise ValueError('selection declaration/source line mismatch')
    required = ('{(|hit), stream_data', '{(|hit[15:0]), stream_weight_side',
                '{(|hit[31:16]), stream_weight_side',
                '{(|hit[15:0]), stream_activation_side',
                '{(|hit[31:16]), stream_activation_side',
                'byte_valid = source_valid && selected[8]',
                'use_newer ? newer[7:0] : older[7:0]')
    if not all(token in source for token in required):
        raise ValueError('data/valid fanout changed')
    slots = field['missing_coordinates']
    offset = field['raw_offset']
    if len(slots) != field['missing'] or len(set(slots)) != len(slots):
        raise ValueError('duplicate/missing coordinates')
    if any(not offset <= p < offset + 18 for p in slots):
        raise ValueError('coordinate outside whole object')
    return {
        'scope': field['scope'], 'name': field['name'],
        'attributes': attrs, 'checksum': field['checksum'],
        'source_binding': field['source_binding'], 'raw_offset': offset,
        'data_7_0_missing': sum((p - offset) // 2 < 8 for p in slots),
        'valid_8_missing': sum((p - offset) // 2 == 8 for p in slots),
        'missing_coordinates': slots, 'waiver_candidate': False,
    }


def review(data):
    source = (ROOT / 'hardware/src/vlsu/qbs/qbs_payload_buffer.sv').read_text()
    fields = data['all_typed_fields']
    selections = [split_selection(p, source) for p in fields
                  if p['module'] == 'qbs_payload_buffer'
                  and p['name'].rsplit('.', 1)[-1] in ('selected', 'older', 'newer')]
    sram = [p for p in fields if p['module'] == 'qbs_payload_sram'
            and p['name'] in ('wdata_i', 'rdata_o')]
    groups = {}
    for p in selections:
        key = re.sub(r'\[\d+\]', '[]', p['name'])
        g = groups.setdefault(key, dict(objects=0, data_7_0_missing=0, valid_8_missing=0))
        g['objects'] += 1
        g['data_7_0_missing'] += p['data_7_0_missing']
        g['valid_8_missing'] += p['valid_8_missing']
    arrays = data['all_arrays_without_binary_coordinate']
    if any(p['missing'] is not None or 'raw_offset' in p for p in arrays):
        raise ValueError('unmapped array was assigned invented coordinates')
    name_data = [p for p in fields if p['classification'].startswith('DATA')]
    by_module = Counter()
    for p in name_data:
        by_module[p['module']] += p['missing']
    return dict(
        status='SOURCE_BOUND_DATA_SEMANTICS_STATIC_REVIEW_NO_EDA',
        population=data['population'], parent_seal=AUDIT_SHA,
        all_parent_pins_verified=len(data['pins']),
        typed_sram_data_objects=len(sram),
        typed_sram_data_bits=sum(p['width'] for p in sram),
        typed_sram_data_missing=sum(p['missing'] for p in sram),
        sram_objects=sram, selection_groups=groups, selections=selections,
        selection_data_missing=sum(p['data_7_0_missing'] for p in selections),
        selection_valid_missing=sum(p['valid_8_missing'] for p in selections),
        unmapped_arrays=len(arrays), array_missing_capacity=None,
        heuristic_data_name_missing_by_module=dict(by_module),
        heuristic_data_names_are_not_candidate_or_entropy_proof=True,
        interpretation=[
            'Selection bit8 is hit validity; byte data are bits7:0. Validity is protected control.',
            'All serialized SRAM wdata/rdata and selection byte data are already hit; this does not certify unmapped memory arrays.',
            'Low fixture byte entropy is observed, but is not evidence of a remaining large physical SRAM/data Toggle gap.',
            'The parent optional A/complement/A pattern has no demonstrated high-gain data target; do not prioritize it on the data-name ranking alone.',
            'rr_arb_tree format data, phase, tag, offset and blocked-cycle counters need separate reachability proof; no blanket skip.',
        ],
        top50_table=str(AUDIT.with_suffix('.top50.csv')),
        constant_candidates_unchanged=data['source_constant_candidate_missing'],
        no_simulation=True, no_EDA=True, coverage_admitted=False,
        official_denominator=None, predicted_gain=None,
        pins={str(AUDIT): AUDIT_SHA,
              str(AUDIT.with_suffix('.top50.csv')): sha(AUDIT.with_suffix('.top50.csv')),
              str(Path(__file__).resolve()): sha(__file__),
              str(Path(__file__).with_name('test_review_qbs_residual766_data_semantics.py')):
                  sha(Path(__file__).with_name('test_review_qbs_residual766_data_semantics.py'))},
    )


if __name__ == '__main__':
    result = review(load_verified())
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(output=str(OUT), sha256=sha(OUT),
                          data_missing=result['selection_data_missing'],
                          valid_missing=result['selection_valid_missing'],
                          sram_missing=result['typed_sram_data_missing'])))
