"""Actual797 residual and conservative source-supported shortlist; no simulation."""
import argparse
import csv
import io
import json
from collections import Counter
from pathlib import Path
import xml.etree.ElementTree as ET

import audit_error_slave797_source as source
import targeted_toggle_evidence_v2 as native
import rank_cva6_scalar_data767 as typed
import report_global777_compact as policy


def collect():
    pins = {}

    def read(path, seal=None):
        data = path.read_bytes()
        actual = native.digest(path)
        source.need(seal is None or actual == seal, 'Evidence hash: ' + str(path))
        pins[str(path)] = actual
        return data

    q = json.loads(read(source.REPORT / 'qualification.json',
        '1ebc05103bc71ee6ec26d97e51ed4867fed3d35a21ee38490956c3ccadf2c5c6'))
    manifest = json.loads(read(source.ADMITTED / 'admission-manifest.json',
        '775485fa0a5cfbb8bb1715374e60d3228d341522b2df3c666754407b30ef55f4'))
    bitmap = source.ADMITTED / 'combined-toggle-bits.json'
    rows = json.loads(read(bitmap, manifest['output_pins'][str(bitmap)]))
    book_path = source.BUILD / 'build-source-pins.json'
    book = json.loads(read(book_path, '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'))
    for rel in ('hardware/deps/cva6/core/csr_regfile.sv',
                'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
                'hardware/src/masku/masku.sv', 'hardware/src/masku/masku_operands.sv',
                'hardware/src/lane/valu.sv'):
        path = source.ROOT / rel
        read(path, book[str(path)])
    config = json.loads(read(source.REPORT / 'config.json', q['config_seal']))
    ledger = config['input_ledger']
    source.need(q['population'] == 797 and len(ledger) == len(set(ledger)) == 798
                and len(rows) == 2989, 'Exact qualified797 scope/membership authority')
    shape_path = Path(ledger[0]) / 'snps/coverage/db/shape/tgl.verilog.shape.xml'
    read(shape_path, config['pins'][str(shape_path)])
    definitions = {}
    for d in native.xml(shape_path).findall('tgldef'):
        definitions.setdefault(d.get('chksum'), []).append(d)
    other, masks = policy.semantic(read(source.REPORT / 'combined.el',
        '2704de24f115e289d8c1e60c3847dc39d7f7d13e955eb284ddc66f6fd42596c9').decode())
    whole = {r[0] for r in other if r[3] == 'WHOLE_SCOPE'}
    opaque = {r[0] for r in other if r[3].startswith('Toggle ')}
    owners = {}
    for (scope, checks, name, kind, decl, prefix, direction), mask in masks.items():
        owners.setdefault((scope, name), []).append((prefix, direction, mask))
    errors = json.loads(read(source.OUT / 'error-slave797-constant-source-agent-20261008-01.json',
        '70cddd9c0c41b6fcfdd6b96feefa7a16793aeb494c221f7d6bf11e33fe6e40b1'))
    constants = {(t['scope'], t['name']): set(t['constant_bits']) for t in errors['targets']}
    registry_path = source.OUT / 'qbs-accumulator-config-constants-source-review767-agent-20261007-01.json'
    registry = json.loads(read(registry_path, config['pins'][str(registry_path)]))
    whole_constants = {(t['scope'], t['attributes']['name']) for t in registry['candidates']}
    hierarchy = {}
    path = source.REPORT / 'raw.csv'
    stack = []
    for r in csv.DictReader(io.StringIO(read(path, q['output_pins'][str(path)]).decode())):
        depth = int(r['Depth'])
        source.need(depth <= len(stack), 'Hierarchy depth continuity')
        stack = stack[:depth] + [r['Name']]
        scope = '.'.join(stack)
        source.need(scope not in hierarchy, 'Unique actual hierarchy scope')
        hierarchy[scope] = r
    families = {}
    diagnostic = []
    holds = []
    stats = Counter()
    for scope, row in rows.items():
        if not scope.startswith('ara_tb.dut.i_ara_soc.i_system.'):
            continue
        if any(scope == s or scope.startswith(s + '.') for s in whole):
            stats['whole_EL_scopes_removed'] += 1
            continue
        ds = definitions.get(row['checksum'], [])
        if len(ds) != 1 or scope in opaque:
            holds.append(dict(scope=scope, reason='Nonunique shape or opaque EL'))
            continue
        nodes, arrays = typed.typed_nodes(ET.tostring(ds[0], encoding='unicode'), row)
        if arrays:
            holds.append(dict(scope=scope, reason='MDA separate; not decoded as binary directions'))
        for node in nodes:
            name = node['name']
            if not node['missing_slots']:
                stats['saturated_fields_removed'] += 1
                continue
            lo = min(int(node.get('left', '0')), int(node.get('right', '0')))
            owned = owners.get((scope, name), [])
            both = {'0to1': 0, '1to0': 0}
            for prefix, direction, mask in owned:
                if prefix:
                    holds.append(dict(scope=scope, name=name, reason='MDA EL mapping HOLD'))
                    break
                both[direction] |= mask
            else:
                if both['0to1'] != both['1to0']:
                    holds.append(dict(scope=scope, name=name, reason='Partial-direction EL HOLD'))
                    continue
                removed = constants.get((scope, name), set())
                if (scope, name) in whole_constants:
                    stats['constant_registry_fields_removed'] += 1
                    continue
                if '.i_masku.i_masku_operands' in scope and name in (
                    'bit_enable_mask_o', 'deshuffled_vl_bit_mask', 'shuffled_vl_bit_mask'):
                    stats['VlBitMaskEnable0_fields_removed'] += 1
                    continue
                positions = []
                for p in node['missing_coordinates']:
                    bit = lo + (p - node['serialized_offset']) // 2
                    if bit in removed or both['0to1'] >> bit & 1:
                        stats['constant_or_EL_slots_removed'] += 1
                    else:
                        positions.append(p)
                if not positions:
                    continue
                item = dict(scope=scope, name=name, checksum=row['checksum'],
                    raw_missing=len(positions), coordinates=positions,
                    offset=node['serialized_offset'], logical_width=node['logical_width'],
                    missing_logical_bits=sorted({lo+(p-node['serialized_offset'])//2 for p in positions}),
                    actual_hierarchy_toggle=hierarchy.get(scope, {}).get('Toggle'))
                diagnostic.append(item)
                family, legal = None, set()
                if scope.endswith('.csr_regfile_i') and name in (
                    'mtvec_d', 'mtvec_q', 'stvec_d', 'stvec_q', 'rvfi_csr_o.mtvec_q', 'rvfi_csr_o.stvec_q'):
                    family, legal = 'TRAP_VECTOR_DIRECT_BASE_ROUNDTRIP', set(range(2, 64))
                elif scope.endswith('.i_masku') and name in ('viota_acc_d', 'viota_acc_q'):
                    family, legal = 'VIOTA_DENSE_VL1024_ENDPOINT', {10}
                if family:
                    selected = [p for p in positions if lo+(p-node['serialized_offset'])//2 in legal]
                    if selected:
                        target = dict(item, coordinates=selected, raw_missing=len(selected),
                            missing_logical_bits=sorted({lo+(p-node['serialized_offset'])//2 for p in selected}))
                        families.setdefault(family, []).append(target)
                continue
            continue
    ranking = [dict(family=f, missing_slots=sum(t['raw_missing'] for t in ts), targets=ts)
               for f, ts in families.items()]
    ranking.sort(key=lambda r: -r['missing_slots'])
    diagnostic.sort(key=lambda r: -r['raw_missing'])
    pins[str(Path(__file__).resolve())] = native.digest(Path(__file__).resolve())
    return dict(status='ACTUAL797_SOURCE_SUPPORTED_STIMULUS_SHORTLIST_NOT_GAIN_FORECAST', population=797,
        pins=pins, actual_hierarchy_rows=len(hierarchy), ranked_source_supported=ranking,
        unclassified_capacity_top30_NOT_REACHABILITY=diagnostic[:30], holds=holds, statistics=dict(stats),
        source_gates=['CSR direct-mode writes preserve bits63:2; RVS1, DirectVecOnly0, full XLEN64.',
            'viota d/q bit10 can rise at final dense VL1024 count; bits11:15 are NOT ranked. viota combinational bit10 already saturated.',
            'vcompress count is per output chunk and subtracts drained elements, not global cumulative popcount. High bits not claimed reachable.',
            'simd_red_operand lane!=0 and lane0 high32 are zero by valu lane/state gates; no wide-reduction entropy recommendation.',
            'AMO functional shortlist withdrawn by frozen SoC atomic filter; no AMOSWAP proposal.',
            'Normal stride fields are already saturated; dispatcher idle stride and maintenance stride are not ordinary memory targets.'],
        limitations=['Only individually source-supported families are ranked reachable; unknown residuals remain diagnostic/HOLD, not predicted gains.',
            'Alias slots are repeated instrumented observations, not independent physical bits or official denominator.',
            'Missing one member of a pair is not assigned a native direction label.',
            'All797 binary scopes use published verified union; no full history rebuild or new EDA.',
            'No historical ELF disassembly dedup yet; corpus source inspection and actual residuals do not prove complete mnemonic absence.'],
        EDA_started=False, simulation_started=False, RTL_changed=False, EL_generated=False,
        official_denominator=None, actual_new_hits=None)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    result = collect()
    with args.output.open('x') as stream:
        stream.write(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(output=str(args.output), sha256=native.digest(args.output),
        ranking=[(r['family'], r['missing_slots']) for r in result['ranked_source_supported']]), indent=2))
