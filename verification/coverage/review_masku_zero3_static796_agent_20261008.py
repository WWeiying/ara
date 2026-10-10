"""Read-only frozen796 reachability review; no simulator or exclusion writer."""
import json
import gzip
import hashlib
from pathlib import Path
from types import SimpleNamespace
import xml.etree.ElementTree as ET


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def xml(path):
    data = Path(path).read_bytes()
    return ET.fromstring(gzip.decompress(data) if data[:2] == b'\x1f\x8b' else data)


BASE_ROOT = Path(__file__).resolve().parents[2]
source_review = SimpleNamespace(
    ROOT=BASE_ROOT, OUT=BASE_ROOT / 'verification/out', digest=digest, require=require,
    typed=SimpleNamespace(xml=xml),
    SCOPE='ara_tb.dut.i_ara_soc.i_system.i_ara.i_masku.i_masku_operands',
    BOOK=BASE_ROOT / 'verification/out/repaired-aligned-build-20260930-01/build-source-pins.json')

ROOT = source_review.ROOT
OUT = source_review.OUT
AUDIT = OUT / 'toggle796-net-static-agent-20261008-01.json'
OUTPUT = OUT / 'masku-zero3-static796-agent-20261008-01.json'
NAMES = ('bit_enable_mask_o', 'deshuffled_vl_bit_mask', 'shuffled_vl_bit_mask')


def collect():
    pins = {}

    def pin(path, expected=None):
        actual = source_review.digest(path)
        source_review.require(expected is None or actual == expected, 'Pin drift: ' + str(path))
        pins[str(path)] = actual
        return path

    audit = json.loads(pin(AUDIT).read_bytes())
    source_review.require(audit['population'] == 796, 'Exact population')
    for name, expected in audit['pins'].items():
        pin(Path(name), expected)
    book = json.loads(source_review.BOOK.read_bytes())
    texts = {}
    for rel in ('hardware/src/masku/masku_operands.sv',
                'hardware/src/masku/masku.sv', 'hardware/include/ara_pkg.sv'):
        path = ROOT / rel
        texts[rel] = pin(path, book[str(path)]).read_text()
    prior_path = OUT / 'masku-vl-disabled-internal2-source-review770-agent-20261007-01.json'
    prior = json.loads(pin(prior_path, '8b2496d8a38f297658cbc91187d0961c3bbfc048f29518af2c35c50de02c66a5').read_bytes())
    for rel in texts:
        path = ROOT / rel
        require(prior['pins'][str(path)] == book[str(path)], 'Prior proof uses same frozen source')
    proof = prior['source_proof']
    manifest_path = next(Path(p) for p in audit['pins'] if p.endswith('/admission-manifest.json'))
    manifest = json.loads(manifest_path.read_bytes())
    config_path = next(Path(p) for p in audit['pins'] if p.endswith('/config.json'))
    config = json.loads(config_path.read_bytes())
    ledger_path = manifest_path.parent / 'combined-inputs.txt'
    ledger = ledger_path.read_text().splitlines()
    source_review.require(len(ledger) == len(set(ledger)) == 797 and ledger == config['input_ledger'],
                          'Exact frozen796 membership')
    bitmap_path = manifest_path.parent / 'combined-toggle-bits.json'
    union = json.loads(bitmap_path.read_bytes())[source_review.SCOPE]
    source_review.require(union['checksum'] == '1400516067', '796 target union checksum')
    db = OUT / 'repaired-aligned-build-20260930-01/sim/simv.vdb/snps/coverage/db'
    design_path = db / 'design/verilog.design.xml'
    design = source_review.typed.xml(pin(design_path, manifest['input_pins'][str(design_path)]))
    pin(db.parents[3] / 'simv', '2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3')
    shape = source_review.typed.xml(db / 'shape/tgl.verilog.shape.xml')
    definitions = [d for d in shape.findall('tgldef')
                   if d.get('name') == 'masku_operands' and d.get('chksum') == '1400516067']
    source_review.require(len(definitions) == 1, 'Unique compiled definition')
    definition = definitions[0]
    params = dict(p.split('=', 1) for p in definition.get('param').split(','))
    source_review.require(params['NrLanes'] == '4' and params['DATAPATH_WIDTH'] == '256',
                          'Frozen compiled width')
    source_review.require('VlBitMaskEnable' not in params, 'Review direct parameter metadata if present')
    nodes = {n.get('id'): (n, m) for m in design.findall('srcdef') for n in m.findall('srcinst')}

    def full(key):
        node, _ = nodes[key]
        parent = node.get('pid')
        return (full(parent) + '.' if parent in nodes else '') + node.get('name')

    hierarchy = {full(k): (n, m) for k, (n, m) in nodes.items()}
    module = hierarchy[source_review.SCOPE][1]
    source_review.require(module.get('name') == 'masku_operands' and
                          module.get('chksum') == '4132557224', 'Actual compiled child instance')
    objects = []
    for name in NAMES:
        rows = [o for o in audit['objects'] if o['scope'] == source_review.SCOPE and
                o['attributes']['name'] == name]
        source_review.require(len(rows) == 1, 'Exact residual object')
        row = rows[0]
        attrs = row['attributes']
        field = next(n for n in definition.find('tglshape') if n.get('name') == name)
        source_review.require(all(attrs[k] == field.get(k) for k in field.attrib), 'Compiled node binding')
        offset = attrs['serialized_offset']
        source_review.require(attrs['left'] == '255' and attrs['right'] == '0' and
                              attrs['logical_width'] == 256 and
                              row['coordinates'] == list(range(offset, offset + 512)) and
                              row['both_direction_EL_removed'] == row['single_direction_EL_HOLD'] == 0,
                              'Exact residual pairs, not native direction IDs')
        binary = format(int(union['bits'], 16), '0%db' % union['width'])
        source_review.require(binary[offset:offset + 512] == '0' * 512,
                              'All target pair positions missing in actual796 union')
        reason = {
            'deshuffled_vl_bit_mask': 'Whole-zero line179; only one-writer line187 is guarded by literal-false line184.',
            'shuffled_vl_bit_mask': 'Whole-zero line180 and line213; copy line209 is guarded by literal-false line208.',
            'bit_enable_mask_o': 'Whole-zero line181 and line214; copy line211 is disabled; line218 AND cannot set a zero bit.',
        }[name]
        objects.append(dict(name=name, compiled_attributes=dict(field.attrib),
                            source_sha256=row['expected_frozen_source_sha256'],
                            classification='CONFIGURATION_DISABLED_CONSTANT_ZERO_NOT_WIDTH_PADDING',
                            proof=reason, native_EL_qualified=False, approved796_EL_removed=0,
                            legal_input_domain='All legal RVV VL/vstart/SEW/LMUL/VM/op and mask/data; reset/abort do not create another writer.',
                            software_gain_lower_bound=0, software_gain_upper_bound=0,
                            bits=[dict(physical_bit=b, serialized_pair=[offset + 2*b, offset + 2*b + 1],
                                       settled_value=0, reachable_one=False, input_pattern_for_one=None,
                                       proof_ref=name, new_toggle_lower_bound=0, new_toggle_upper_bound=0)
                                  for b in range(256)]))
    pin(Path(__file__).resolve())
    for name, expected in pins.items():
        source_review.require(source_review.digest(Path(name)) == expected, 'Final pin drift')
    return dict(status='FROZEN796_MASKU_ZERO3_SOURCE_PROVEN_NO_USEFUL_RVV_CASE', population=796,
                scope=source_review.SCOPE, toggle_checksum='1400516067', module_checksum='4132557224',
                compiled_parameters=params, compiled_VlBitMaskEnable_direct_metadata_present=False,
                effective_VlBitMaskEnable=0,
                effective_value_basis='Non-overridable literal localparam in SHA-bound compiled source and exact parent instance; not inferred from missing hits.',
                validation_scope='Pinned796 report, ledger membership, target union pair slots, compiled hierarchy/shape, source and image; not a full independent union reconstruction.',
                source_proof=proof, objects=objects, physical_bits=768,
                residual_unnamed_serialized_pair_slots=1536, software_gain_lower_bound=0,
                software_gain_upper_bound=0, official_denominator=None, measured_gain=None,
                native_EL_policy='Two internals remain native-pending; output port protected. Parent alias native qualification does not qualify child output. No EL generated or applied.',
                checker_policy='No new case and no checker changes. Existing strictSpike/native evidence remains untouched; static proof is not execution or a checker pass.',
                limitations=['Settled legal execution only; no force, pre-settle X/delta or tool initial-X transition claim.',
                             'Pair positions are not named native 0to1/1to0 IDs and are not a DVE denominator.'],
                EDA_started=False, RTL_changed=False, frozen_tools_changed=False, pins=pins)


if __name__ == '__main__':
    source_review.require(not OUTPUT.exists(), 'Fresh agent-owned output only')
    result = collect()
    with OUTPUT.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(dict(output=str(OUTPUT), sha256=source_review.digest(OUTPUT),
                         physical_bits=result['physical_bits'], software_gain=0, EDA_started=False)))
