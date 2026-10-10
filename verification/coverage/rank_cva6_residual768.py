"""Exact768 CVA6 binary/typed residual; MDA and official denominator stay separate."""
import argparse
from collections import Counter
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import rank_cva6_scalar_data767 as old

t, ROOT, OUT = old.t, old.ROOT, old.OUT
BASE = OUT / 'stride-metadata-full64-offline-admitted-768-agent-20261007-01'
SEAL = '1add5889916fd9cfe2bb6e95368a2a86d43f1d0ac27ac4cf89786639cb6f4198'
SOURCE_FILES = (
    'hardware/src/ara_soc.sv', 'hardware/deps/cva6/core/include/build_config_pkg.sv',
    'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
    'hardware/deps/cva6/core/include/ariane_pkg.sv', 'hardware/deps/cva6/core/include/riscv_pkg.sv',
    'hardware/deps/cva6/core/decoder.sv', 'hardware/deps/cva6/core/id_stage.sv',
    'hardware/deps/cva6/core/scoreboard.sv', 'hardware/deps/cva6/core/issue_stage.sv',
    'hardware/deps/cva6/core/issue_read_operands.sv', 'hardware/deps/cva6/core/instr_realign.sv',
    'hardware/deps/cva6/core/frontend/frontend.sv', 'hardware/deps/cva6/core/frontend/instr_queue.sv')


def domain(scope):
    if any(x in scope for x in ('csr_regfile', '.i_cva6_rvfi', '.rvfi')): return 'OTHER_OWNER_CSR_RVFI'
    if any(x in scope for x in ('.lsu_i', '.gen_cache', '.i_cache')): return 'OTHER_OWNER_LSU_PTW_CACHE'
    if '.i_frontend' in scope: return 'FETCH'
    if '.id_stage_i' in scope: return 'DECODE'
    if '.i_scoreboard' in scope: return 'SCOREBOARD'
    if '.issue_stage_i' in scope: return 'ISSUE'
    return 'OTHER_CVA6_DOMAIN'


def classify(name):
    if any(x in name for x in ('tval', 'cause', 'gva', 'tinst')):
        return 'EXCEPTION_RETAIN_UNLESS_COMPLETE_PRODUCER_PROOF'
    if any(x in name for x in ('address', 'addr', '.pc', 'target')):
        return 'ADDRESS_RETAIN_NO_OBSERVED_RANGE_WAIVER'
    if any(x in name for x in ('preview_data', 'acc_preview_data')):
        return 'VSET_BOUND_CANDIDATE_REQUIRES_ARCH_PRODUCER_PROOF'
    return 'SOURCE_REVIEW_REQUIRED'


def collect():
    pins = {}
    def checked(path, sha):
        t.require(t.digest(path) == sha, 'Pin drift: ' + str(path)); pins[str(path)] = sha
        return path.read_bytes()
    manifest = json.loads(checked(BASE / 'admission-manifest.json', SEAL))
    ledger = BASE / 'combined-inputs.txt'
    inputs = checked(ledger, manifest['output_pins'][str(ledger)]).decode().splitlines()
    t.require(len(inputs) == len(set(inputs)) == 769, 'Not exact768')
    cache = json.loads(checked(old.CACHE, old.CACHE_SHA))
    prior = next(Path(p) for p in cache['input_pins'] if p.endswith('/inputs.txt'))
    t.require(inputs[:742] == checked(prior, cache['input_pins'][str(prior)]).decode().splitlines(), '741 prefix differs')
    scopes = [s for s in cache['instances'] if s == old.PREFIX or s.startswith(old.PREFIX + '.')]
    union = {s: {k: cache['instances'][s][k] for k in ('width', 'checksum', 'bits')} for s in scopes}
    for vdb in inputs[742:]:
        samples = list((Path(vdb) / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        t.require(len(samples) == 1, 'One suffix per admitted test')
        p = samples[0]; rows, sha = t.rows(p, scopes)
        t.require(sha == manifest['input_pins'][str(p)], 'Suffix Toggle drift')
        pins[str(p)] = sha; union = t.union(union, rows)
    db = Path(inputs[0]) / 'snps/coverage/db'
    paths = [db / 'design/verilog.design.xml', db / 'shape/tgl.verilog.info.xml', db / 'shape/tgl.verilog.shape.xml']
    for p in paths: checked(p, manifest['input_pins'][str(p)])
    design, info, shape = [t.xml(p) for p in paths]
    checks = {n.get('name'): n.get('chksum') for n in info.iter('instance_data') if n.get('name') in scopes}
    t.require(set(checks) == set(scopes), 'Missing actual Toggle instance')
    # Build source instance ownership once; a family+checksum merged shape is
    # disclosed, and cannot be used as parameter-unreachability proof.
    nodes = {n.get('id'): (n, m) for m in design.findall('srcdef') for n in m.findall('srcinst')}
    def path(key):
        n, _ = nodes[key]; parent = n.get('pid')
        return (path(parent) + '.' if parent in nodes else '') + n.get('name')
    modules = {path(key): m for key, (_, m) in nodes.items()}
    fields, summaries, arrays = [], [], []
    for scope in scopes:
        row = union[scope]; t.require(row['checksum'] == checks[scope], 'Actual shape checksum differs')
        module = modules[scope]; family = module.get('name', '').split(' (')[0]
        matches = [n for n in shape.findall('tgldef') if n.get('chksum') == checks[scope] and n.get('name') == module.get('name')]
        binding = 'EXACT_MODULE_AND_CHECKSUM'
        if not matches:
            matches = [n for n in shape.findall('tgldef') if n.get('chksum') == checks[scope] and n.get('name', '').split(' (')[0] == family]
            binding = 'MERGED_PARAMETER_NAMES_HOLD_PARAMETER_PROOF'
        if len(matches) != 1:
            summaries.append(dict(scope=scope, domain=domain(scope), checksum=checks[scope],
                                  status='HOLD_AMBIGUOUS_SHAPE', variants=len(matches))); continue
        root = matches[0]; objects, mda = old.typed_nodes(ET.tostring(root, encoding='unicode'), row)
        for n in objects:
            if n['missing_slots']:
                fields.append(dict(scope=scope, checksum=checks[scope], domain=domain(scope),
                    module_name=module.get('name'), binding=binding, **n,
                    source_domain_classification=classify(n['name']), candidate_approved=False))
        arrays.extend(dict(scope=scope, checksum=checks[scope], **a, binary_coordinates=None) for a in mda)
        summaries.append(dict(scope=scope, domain=domain(scope), checksum=checks[scope], binding=binding,
            width=row['width'], missing_slots=row['width']-bin(int(row['bits'], 16)).count('1'),
            arrays=len(mda)))
    book_path = OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json'
    book = json.loads(checked(book_path, manifest['input_pins'][str(book_path)])); sources = {}
    for rel in SOURCE_FILES:
        p = ROOT / rel; checked(p, book[str(p)])
        sources[rel] = dict(path=str(p), sha256=book[str(p)])
    for p in (Path(__file__), Path(__file__).with_name('test_rank_cva6_residual768.py'),
              Path(old.__file__)):
        pins[str(p)] = t.digest(p)
    totals = Counter()
    for r in summaries:
        if 'width' in r: totals[r['domain']] += r['missing_slots']
    for p, sha in pins.items(): t.require(t.digest(p) == sha, 'End-of-read drift')
    owned = {'DECODE', 'FETCH', 'ISSUE', 'SCOREBOARD'}
    return dict(schema='FORMAL768_FULL_CVA6_TYPED_BINARY_RESIDUAL_V1', population=768, pins=pins,
        source_pins=sources, instances=sorted(summaries, key=lambda n: -n.get('missing_slots', 0)),
        domain_missing_serialized_positions=dict(totals),
        owned_fields=sorted([f for f in fields if f['domain'] in owned], key=lambda f: -f['missing_slots']),
        all_fields=sorted(fields, key=lambda f: -f['missing_slots']), arrays=arrays,
        provenance='Exact sealed741 cached local binary OR plus27 pinned admitted suffixes; no array coverage inferred',
        nominal_positions_not_official_denominator=True, native_bit_direction_labels_bound=False,
        waivers_approved=False, native_probe_launched=False, simulation_launched=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); t.require(not args.output.exists(), 'Fresh output required')
    result = collect()
    with args.output.open('x') as stream: json.dump(result, stream, indent=2); stream.write('\n')
    print('FULL768_TYPED_READY', t.digest(args.output), len(result['instances']), len(result['owned_fields']))
