"""Source-only FP32 padding and bounded alignment witnesses; no native actions."""
import argparse
import csv
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import review_c910_qbs_pattern795 as gold
import targeted_toggle_evidence_v2 as native
import rank_cva6_scalar_data767 as typed

ROOT = gold.ROOT
OUT = gold.OUT
PACKET = OUT / 'c910-qbs-pattern795-independent-review-agent-20261008-01.json'
PACKET_SHA = 'c04263b64abccfc66eea767145356c70167aa17026b4c95bc11c0dbf19cf8a64'
NAMES = ('product_shifted', 'addend_after_shift', 'addend_sticky_bits',
         'sum_shifted', 'sum_sticky_bits')


def need(condition, message):
    if not condition:
        raise ValueError(message)


def padding_bits(precision, width):
    need(type(precision) is int and precision == 24 and width == 76,
         'Exact compiled FP32 precision and product width')
    return [0, 1] + list(range(2 * precision + 2, width))


def pair_positions(offset, bits):
    # Established raw serializer convention, NOT a native direction-ID mapping.
    return sorted(offset + 2 * bit + slot for bit in bits for slot in (0, 1))


def alignment(a, b, c):
    """Accepted finite same-sign DOT FMA arithmetic only, not a pipeline model."""
    operands = (a, b, c)
    need(all(type(x) is int and 0 <= x < 1 << 32 for x in operands), 'FP32 words')
    exps = [(x >> 23) & 255 for x in operands]
    need(all(e != 255 for e in exps), 'Finite domain')
    need((a >> 31) ^ (b >> 31) == c >> 31 or not (c & 0x7fffffff),
         'Witness model deliberately excludes effective subtraction')
    mant = [(x & 0x7fffff) | ((1 << 23) if e else 0)
            for x, e in zip(operands, exps)]
    prod_exp = (2 - 127 if not mant[0] or not mant[1] else
                exps[0] + int(exps[0] == 0) + exps[1] + int(exps[1] == 0) - 127)
    add_exp = exps[2] + int(exps[2] == 0)
    difference = add_exp - prod_exp
    shift = 76 if difference <= -49 else (27 - difference if difference <= 26 else 0)
    joined = (mant[2] << 76) >> shift
    addend, sticky = joined >> 24, joined & ((1 << 24) - 1)
    product = mant[0] * mant[1] << 2
    summed = (product + addend) & ((1 << 76) - 1)
    lower = summed & ((1 << 51) - 1)
    zeros = 51 - lower.bit_length() if lower else 0
    if difference <= 0:
        normal = prod_exp - zeros + 1 >= 0 and lower != 0
        norm_shift = 26 + zeros if normal else (26 + prod_exp) & 127
        norm_exp = prod_exp - zeros + 1 if normal else 0
    else:
        norm_shift, norm_exp = shift, max(prod_exp, add_exp)
    shifted = (summed << norm_shift) & ((1 << 77) - 1)
    adjusted = shifted
    if shifted & (1 << 76):
        adjusted >>= 1
    elif not shifted & (1 << 75) and norm_exp > 1:
        adjusted <<= 1
    return dict(exponent_difference=difference, addend_shamt=shift,
                norm_shamt=norm_shift, product_shifted=product,
                addend_after_shift=addend, addend_sticky_bits=sticky,
                sum_shifted=shifted, sum_sticky_bits=adjusted & ((1 << 51) - 1))


def collect():
    need(gold.digest(PACKET) == PACKET_SHA, 'Prior independent packet pin')
    packet = json.loads(PACKET.read_text())
    pins = dict(packet['input_pins'])
    pins[str(PACKET)] = PACKET_SHA
    for path, sha in pins.items():
        need(gold.digest(Path(path)) == sha, 'Pinned input changed: ' + path)
    shape_path = next(Path(p) for p in pins if p.endswith('/shape/tgl.verilog.shape.xml'))
    defs = [n for n in native.xml(shape_path).findall('tgldef') if n.get('chksum') == '3389058436']
    need(len(defs) == 1 and 'PRECISION_BITS=24' in defs[0].get('name'), 'Compiled FP32 definition')
    scope = packet['qbs']['targets'][0]['scope']
    bitmap_path = next(Path(p) for p in pins if p.endswith('/combined-toggle-bits.json'))
    row = json.loads(bitmap_path.read_text())[scope]
    need(row['checksum'] == '3389058436', 'Actual795 checksum')
    nodes, arrays = typed.typed_nodes(ET.tostring(defs[0], encoding='unicode'), row)
    selected = {n['name']: n for n in nodes if n['name'] in NAMES}
    need(len(selected) == 5, 'Exact five typed fields')
    product = selected['product_shifted']
    need(product['type'] == '1' and product['portnode'] == '0' and
         product['left'] == '75' and product['right'] == '0', 'Internal exact vector identity')
    zero_bits = padding_bits(24, product['logical_width'])
    zero_positions = pair_positions(product['serialized_offset'], zero_bits)
    need(set(zero_positions) <= set(product['missing_coordinates']), 'Source padding must be actually missing')
    need(len(zero_positions) == 56 and len(product['missing_coordinates']) == 62,
         'Measured raw split')
    source_path = ROOT / 'hardware/deps/fpnew/src/fpnew_fma.sv'
    manifest_path = next(Path(p) for p in pins if p.endswith('/admission-manifest.json'))
    manifest = json.loads(manifest_path.read_text())
    sourceinfo_path = next(Path(p) for p in manifest['input_pins']
                           if p.endswith('/auxiliary/verilog.sourceinfo.xml'))
    sourceinfo_sha = manifest['input_pins'][str(sourceinfo_path)]
    need(gold.digest(sourceinfo_path) == sourceinfo_sha, 'Frozen compiled sourceinfo')
    files = [n for n in native.xml(sourceinfo_path).findall('fileinfo')
             if n.get('id') == product['file']]
    need(len(files) == 1 and files[0].get('name') == str(source_path),
         'Actual compiled file381 must bind frozen FMA source')
    pins[str(sourceinfo_path)] = sourceinfo_sha
    need(all(n['file'] == product['file'] for n in selected.values()),
         'All five fields compiled from the same actual source')
    source = source_path.read_text()
    need(source.count('assign product_shifted = product << 2;') == 1 and
         source.count('assign product = mantissa_a * mantissa_b;') == 1 and
         'logic [2*PRECISION_BITS-1:0] product;' in source and
         'logic [3*PRECISION_BITS+3:0] product_shifted;' in source,
         'Frozen sole combinational producer and declared widths')
    # Historical failed capture is used ONLY for actual displayed object identity.
    prior = OUT / 'qbs-accum66-native-agent-20261007-01'
    config = json.loads((prior / 'config.json').read_text())
    inventory = [s for s in config['instances'] if s['scope'] == scope]
    need(len(inventory) == 1 and inventory[0]['toggle_checksum'] == row['checksum'],
         'Historical native scope binding')
    with (prior / 'native_before_5.tsv').open() as stream:
        labels = list(csv.reader(stream, delimiter='\t'))[1:]
    for name, node in selected.items():
        label = name + '[' + node['left'] + ':' + node['right'] + ']'
        matches = [r for r in labels if r[1] == label]
        need(len(matches) == 1 and matches[0][2:4] == [label, label], 'Exact actual native label')
    for path in (prior / 'config.json', prior / 'native_before_5.tsv'):
        pins[str(path)] = gold.digest(path)
    dense, tiny = 0x3f8e3000, 0x201
    tiny_dot, tiny_flags = gold.round32(gold.value(tiny) * 8)
    dense_dot, dense_flags = gold.round32(gold.value(dense) * 8)
    witnesses = [alignment(tiny, 0x41000000, dense_dot),
                 alignment(dense, 0x41000000, tiny_dot)]
    reachable = []
    for name, node in selected.items():
        one_bits = [b for b in range(node['logical_width'])
                    if any(w[name] >> b & 1 for w in witnesses)]
        positions = sorted(set(pair_positions(node['serialized_offset'], one_bits)) &
                           set(node['missing_coordinates']))
        reachable.append(dict(name=name, one_bits=one_bits,
                              missing_positions_with_one_witness=positions,
                              count=len(positions)))
    need(witnesses[1]['addend_sticky_bits'] == 0x1008 and
         witnesses[1]['addend_shamt'] == 76, 'Concrete tiny-addend sticky witness')
    pins[str(Path(__file__).resolve())] = gold.digest(Path(__file__).resolve())
    test_path = Path(__file__).with_name('test_review_qbs_fma_padding795.py')
    pins[str(test_path)] = gold.digest(test_path)
    return dict(status='SOURCE_PADDING_PROVED_HOST_ALIGNMENT_WITNESS_ONLY',
        baseline=795, baseline_seal=packet['baseline_seal'], EL_seal=packet['EL_seal'],
        pins=pins, scope=scope, checksum=row['checksum'], compiled_definition=defs[0].get('name'),
        compiled_source_file=dict(files[0].attrib),
        exact_product_object=product, constant_source_bits=zero_bits,
        constant_serialized_positions=zero_positions,
        dynamic_product_missing_positions=sorted(set(product['missing_coordinates']) - set(zero_positions)),
        constant_position_count=56, other_five_field_missing_positions_protected=208,
        source_proof='Unsigned 24x24 product is exactly48 bits. Sole assign into76-bit product_shifted shifts by2. [75:50] and[1:0] are zero for all defined operand bit patterns, including invalid/bubble/special data. No clock/reset/operation branch changes this producer. Unknown startup is not excluded or certified.',
        serialization='Existing raw convention: low logical bit first, two positions per bit; pair slots unnamed. Neither slot is assigned a native 0to1/1to0 ID. Native bit-range qualification not performed.',
        historical_native_status='Failed predecessor capture identity evidence ONLY; no five-stage qualification claim',
        arrays_protected=arrays, whole_scope_object_count=len(nodes),
        witnesses=witnesses, mutable_missing_witnesses=reachable,
        witnessed_missing_pair_positions=sum(r['count'] for r in reachable),
        exact_dot_gold=dict(tiny=hex(tiny_dot), tiny_fflags=tiny_flags,
                            dense=hex(dense_dot), dense_fflags=dense_flags),
        full_descriptor_gold=packet['qbs']['exact_rational_gold'],
        limitation='DOT FMA accepted-data model only; no speculative combinational pipeline transitions, no MIN-operation coverage predicted. Full descriptor/software/owner preflight not performed.',
        decision='Only a small concrete sticky witness; no high-yield software build or runtime justified. Keep all shifting/sticky fields and product[49:2] protected; no further constant waiver.',
        EDA_started=False, software_built=False, EL_created=False, native_qualified=False,
        measured_gain=None, official_denominator=None)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    need(not args.output.exists(), 'Fresh output required')
    result = collect()
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(gold.digest(args.output), result['witnessed_missing_pair_positions'])
